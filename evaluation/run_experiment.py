"""
Three-Configuration Evaluation Runner
=====================================
Runs the 50-case ground truth set through three system configurations and
reports detection metrics (RQ3) plus routing accuracy (RQ1, Config C only).

  Config A  rules only                  (baseline)
  Config B  Isolation Forest + rules     (hybrid detection)
  Config C  full agent: rules/IF gate + RAG-style LLM semantic review,
            confidence-based routing

Design
------
- Detection positive class = ANOMALY.
- Rule logic mirrors configs/rules.yaml: retry_count >= 3 OR delay_minutes >= 30.
- Isolation Forest is trained on a synthetic NORMAL distribution shaped as an
  "L" region (low retry OR low delay = normal). Real anomalies sit in the
  high-retry-AND-high-delay corner, so the IF can veto rule false positives on
  noisy-but-benign cases while keeping recall on genuine anomalies.
- Config C calls the LLM only for cases that pass the rule/IF gate, and every
  call is cached to llm_cache.json. First run is throttled to respect the Groq
  free-tier rate limit; re-runs are instant and deterministic.

Resilience
----------
- If GROQ_API_KEY is missing, Configs A and B still run and report fully;
  Config C is skipped with a clear message so RQ3 results are never blocked.

Usage
-----
  python run_experiment.py
  python run_experiment.py --no-llm        # force skip Config C
  python run_experiment.py --delay 6       # seconds between uncached LLM calls
"""

import os
import csv
import json
import time
import hashlib
import argparse

import numpy as np
from sklearn.ensemble import IsolationForest

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

RANDOM_SEED = 42
RETRY_THRESHOLD = 3
DELAY_THRESHOLD = 30
CACHE_FILE = "llm_cache.json"

CATEGORIES = [
    "EDI_MAPPING_ERROR", "PARTNER_API_TIMEOUT", "NETSUITE_QUEUE_BACKLOG",
    "DUPLICATE_TRANSACTION", "AUTH_FAILURE", "RATE_LIMIT_EXCEEDED",
]


# -------------------------------------------------------------------
# DATA
# -------------------------------------------------------------------
def load_cases(path="ground_truth.csv"):
    with open(path) as f:
        return list(csv.DictReader(f))


# -------------------------------------------------------------------
# DETECTION LOGIC
# -------------------------------------------------------------------
def rule_fires(case):
    return (int(case["retry_count"]) >= RETRY_THRESHOLD
            or int(case["delay_minutes"]) >= DELAY_THRESHOLD)


def train_isolation_forest():
    """Train IF on a synthetic NORMAL distribution (L-shaped region)."""
    rng = np.random.default_rng(RANDOM_SEED)
    n = 600
    samples = []
    for _ in range(n):
        r = rng.random()
        if r < 0.70:          # quiet: low retry, low delay
            retry = rng.integers(0, 3)
            delay = rng.uniform(0, 25)
        elif r < 0.85:        # noisy-delay: low retry, high delay (benign)
            retry = rng.integers(0, 3)
            delay = rng.uniform(30, 60)
        else:                 # noisy-retry: high retry, low delay (benign)
            retry = rng.integers(3, 6)
            delay = rng.uniform(0, 25)
        samples.append([retry, delay])
    X = np.array(samples, dtype=float)
    model = IsolationForest(
        n_estimators=200, contamination=0.05, random_state=RANDOM_SEED
    )
    model.fit(X)
    return model


def if_flags(model, case):
    X = np.array([[int(case["retry_count"]), int(case["delay_minutes"])]], dtype=float)
    return model.predict(X)[0] == -1   # -1 = outlier/anomaly


# -------------------------------------------------------------------
# LLM (Config C) WITH CACHING + RATE-LIMIT HANDLING
# -------------------------------------------------------------------
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE))
        except Exception:
            return {}
    return {}


def save_cache(cache):
    json.dump(cache, open(CACHE_FILE, "w"), indent=2)


def build_eval_prompt(case):
    return f"""You are an ERP integration monitoring agent (Oracle NetSuite, SAP, EDI).

A candidate event has been flagged by upstream detection. Decide whether it is a
GENUINE anomaly requiring action, or a benign/normal event that was over-flagged.
If genuine, classify the root cause and choose a routing decision.

Event:
  System:        {case['system']}
  Partner:       {case['partner']}
  Retry Count:   {case['retry_count']}
  Delay Minutes: {case['delay_minutes']}
  Signature:     {case['error_signature']}

Root cause categories: {", ".join(CATEGORIES)}

Routing rules:
  AUTO_REMEDIATE - known pattern, low business risk, safe to auto-fix
  INVESTIGATE    - recognised but carries financial/data risk or ambiguity
  ESCALATE       - high severity, novel, or repeated; unsafe to act autonomously
  NONE           - benign/normal event, no action required

Return ONLY valid JSON, no markdown:
{{
  "is_anomaly": true or false,
  "root_cause_category": "one of the categories above, or NONE if benign",
  "routing_decision": "AUTO_REMEDIATE | INVESTIGATE | ESCALATE | NONE",
  "confidence_score": 0.75
}}"""


def call_llm(case, llm, cache, delay):
    prompt = build_eval_prompt(case)
    key = case["case_id"] + ":" + hashlib.sha256(prompt.encode()).hexdigest()[:16]
    if key in cache:
        return cache[key], True   # cached -> no API call

    # Not cached: call with rate-limit backoff
    attempt = 0
    while True:
        try:
            resp = llm.invoke(prompt)
            content = resp.content
            break
        except Exception as e:
            msg = str(e)
            if "rate_limit" in msg or "429" in msg:
                wait = 20
                # try to parse "try again in Xs"
                import re
                m = re.search(r"try again in ([0-9.]+)s", msg)
                if m:
                    wait = float(m.group(1)) + 1
                print(f"   ⏳ rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
                attempt += 1
                if attempt > 5:
                    raise
                continue
            raise

    # parse JSON
    parsed = _extract_json(content)
    cache[key] = parsed
    save_cache(cache)
    time.sleep(delay)   # base throttle between uncached calls
    return parsed, False


def _extract_json(text):
    import re
    text = text.strip()
    # strip code fences
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    # fallback
    return {"is_anomaly": True, "root_cause_category": "NONE",
            "routing_decision": "ESCALATE", "confidence_score": 0.4}


# -------------------------------------------------------------------
# METRICS
# -------------------------------------------------------------------
def detection_metrics(cases, predictions):
    """predictions: dict case_id -> 'ANOMALY'|'NORMAL'. Positive = ANOMALY."""
    tp = fp = fn = tn = 0
    for c in cases:
        actual = c["expected_detection"]
        pred = predictions[c["case_id"]]
        if pred == "ANOMALY" and actual == "ANOMALY":
            tp += 1
        elif pred == "ANOMALY" and actual == "NORMAL":
            fp += 1
        elif pred == "NORMAL" and actual == "ANOMALY":
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return dict(TP=tp, FP=fp, FN=fn, TN=tn,
                precision=precision, recall=recall, f1=f1, fpr=fpr)


def routing_accuracy(cases, routing_preds):
    """Accuracy of routing on cases the system flagged as anomalies."""
    correct = total = 0
    for c in cases:
        if c["case_id"] in routing_preds:
            total += 1
            if routing_preds[c["case_id"]] == c["expected_routing"]:
                correct += 1
    return (correct / total if total else 0.0), correct, total


# -------------------------------------------------------------------
# RUN CONFIGS
# -------------------------------------------------------------------
def run_config_a(cases):
    return {c["case_id"]: ("ANOMALY" if rule_fires(c) else "NORMAL") for c in cases}


def run_config_b(cases, model):
    preds = {}
    for c in cases:
        # hybrid: rule must fire AND IF must agree it's an outlier
        preds[c["case_id"]] = "ANOMALY" if (rule_fires(c) and if_flags(model, c)) else "NORMAL"
    return preds


def run_config_c(cases, model, delay):
    """Gate with rule OR IF, then LLM semantic review. Returns (detection, routing)."""
    from langchain_groq import ChatGroq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None, None
    llm = ChatGroq(model="llama-3.1-8b-instant", api_key=api_key)
    cache = load_cache()

    detection, routing = {}, {}
    gated = 0
    for c in cases:
        candidate = rule_fires(c) or if_flags(model, c)
        if not candidate:
            detection[c["case_id"]] = "NORMAL"   # never reaches agent
            continue
        gated += 1
        parsed, was_cached = call_llm(c, llm, cache, delay)
        is_anom = bool(parsed.get("is_anomaly", True))
        detection[c["case_id"]] = "ANOMALY" if is_anom else "NORMAL"
        if is_anom:
            routing[c["case_id"]] = parsed.get("routing_decision", "ESCALATE")
        tag = "cached" if was_cached else "API"
        print(f"   [{tag}] {c['case_id']} -> anomaly={is_anom} route={parsed.get('routing_decision')}")
    print(f"   ({gated} cases reached the agent; {len(cases)-gated} gated out as normal)")
    return detection, routing


# -------------------------------------------------------------------
# REPORT
# -------------------------------------------------------------------
def print_metrics(name, m):
    print(f"\n{name}")
    print(f"  Precision : {m['precision']*100:5.1f}%")
    print(f"  Recall    : {m['recall']*100:5.1f}%")
    print(f"  F1 score  : {m['f1']*100:5.1f}%")
    print(f"  FPR       : {m['fpr']*100:5.1f}%   (false positive rate)")
    print(f"  TP={m['TP']} FP={m['FP']} FN={m['FN']} TN={m['TN']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip Config C")
    ap.add_argument("--delay", type=float, default=5.0,
                    help="seconds between uncached LLM calls (rate-limit safety)")
    args = ap.parse_args()

    cases = load_cases()
    print(f"Loaded {len(cases)} ground-truth cases.")

    model = train_isolation_forest()
    print("Isolation Forest trained on synthetic normal distribution.\n")

    results = {}

    print("=" * 60)
    print("CONFIG A — Rules only")
    a = run_config_a(cases)
    ma = detection_metrics(cases, a)
    results["A_rules"] = ma
    print_metrics("Config A (rules only)", ma)

    print("\n" + "=" * 60)
    print("CONFIG B — Isolation Forest + Rules")
    b = run_config_b(cases, model)
    mb = detection_metrics(cases, b)
    results["B_if_rules"] = mb
    print_metrics("Config B (IF + rules)", mb)

    routing_acc = None
    if not args.no_llm:
        print("\n" + "=" * 60)
        print("CONFIG C — Full agent (gate + LLM semantic review + routing)")
        det_c, route_c = run_config_c(cases, model, args.delay)
        if det_c is None:
            print("\n⚠️  GROQ_API_KEY not set — Config C skipped.")
            print("    Configs A and B above are complete. Set the key to run C.")
        else:
            mc = detection_metrics(cases, det_c)
            results["C_agent"] = mc
            print_metrics("Config C (full agent)", mc)
            acc, correct, total = routing_accuracy(cases, route_c)
            routing_acc = (acc, correct, total)
            print(f"\n  Routing accuracy (RQ1): {acc*100:.1f}%  ({correct}/{total} correct)")
    else:
        print("\n(Config C skipped via --no-llm)")

    # Write results table
    with open("results_detection.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["configuration", "precision", "recall", "f1", "fpr",
                    "TP", "FP", "FN", "TN"])
        for name, m in results.items():
            w.writerow([name,
                        f"{m['precision']:.4f}", f"{m['recall']:.4f}",
                        f"{m['f1']:.4f}", f"{m['fpr']:.4f}",
                        m["TP"], m["FP"], m["FN"], m["TN"]])

    print("\n" + "=" * 60)
    print("SUMMARY (detection — RQ3)")
    print(f"{'Config':<22}{'Prec':>7}{'Rec':>7}{'F1':>7}{'FPR':>7}")
    labels = {"A_rules": "A rules", "B_if_rules": "B IF+rules", "C_agent": "C agent"}
    for name, m in results.items():
        print(f"{labels.get(name, name):<22}"
              f"{m['precision']*100:6.1f}{m['recall']*100:7.1f}"
              f"{m['f1']*100:7.1f}{m['fpr']*100:7.1f}")
    if routing_acc:
        print(f"\nRQ1 routing accuracy (Config C): {routing_acc[0]*100:.1f}%")
    print("\n✅ Wrote results_detection.csv")


if __name__ == "__main__":
    main()
