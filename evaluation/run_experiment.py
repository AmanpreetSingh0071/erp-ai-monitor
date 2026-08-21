"""
Three-Configuration Evaluation Runner  (v2: improved RQ1 routing)
=================================================================
Runs the 50-case ground truth set through three configurations and reports
detection metrics (RQ3), routing accuracy with a confusion matrix (RQ1), and
a confidence-calibration summary (RQ1 core question).

  Config A  rules only                  (baseline)
  Config B  Isolation Forest + rules     (hybrid detection)
  Config C  full agent: rules/IF gate + few-shot LLM semantic review +
            confidence-based routing

What changed from v1
--------------------
- The routing prompt now contains worked few-shot examples (illustrative and
  disjoint from the evaluation cases) so the model discriminates between
  AUTO_REMEDIATE / INVESTIGATE / ESCALATE instead of defaulting to the middle.
- Adds a 3x3 routing confusion matrix (expected vs predicted).
- Adds a confidence-calibration summary: mean confidence for correct vs
  incorrect routing, plus the spread of confidence values. This is the
  evidence base for RQ1 (can LLM confidence reliably drive routing?).
- Writes results_routing.csv (per-case) alongside results_detection.csv.

NOTE: because the prompt text changed, the LLM cache keys change, so Config C
will make fresh API calls on the next run (then cache again). Expect a few
minutes for the first v2 run.

Usage
-----
  python run_experiment.py
  python run_experiment.py --no-llm
  python run_experiment.py --delay 6
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
def cache_path(llm_name):
    """Per-model cache so different models never overwrite each other."""
    safe = llm_name.replace("/", "_").replace(":", "_")
    return f"llm_cache_{safe}.json"
ROUTING_LABELS = ["AUTO_REMEDIATE", "INVESTIGATE", "ESCALATE"]

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
    rng = np.random.default_rng(RANDOM_SEED)
    n = 600
    samples = []
    for _ in range(n):
        r = rng.random()
        if r < 0.70:
            retry = rng.integers(0, 3); delay = rng.uniform(0, 25)
        elif r < 0.85:
            retry = rng.integers(0, 3); delay = rng.uniform(30, 60)
        else:
            retry = rng.integers(3, 6); delay = rng.uniform(0, 25)
        samples.append([retry, delay])
    X = np.array(samples, dtype=float)
    model = IsolationForest(n_estimators=200, contamination=0.05,
                            random_state=RANDOM_SEED)
    model.fit(X)
    return model


def if_flags(model, case):
    X = np.array([[int(case["retry_count"]), int(case["delay_minutes"])]], dtype=float)
    return model.predict(X)[0] == -1


# -------------------------------------------------------------------
# LLM (Config C) WITH CACHING + RATE-LIMIT HANDLING
# -------------------------------------------------------------------
def load_cache(path):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            return {}
    return {}


def save_cache(cache, path):
    json.dump(cache, open(path, "w"), indent=2)


def build_eval_prompt(case):
    # Few-shot examples below are ILLUSTRATIVE and deliberately disjoint from
    # the evaluation cases (different scenarios) to avoid data leakage. They
    # teach the routing principle: risk + severity + clarity, not keyword match.
    return f"""You are an ERP integration monitoring agent (Oracle NetSuite, SAP, EDI).

A candidate event has been flagged by upstream detection. Decide whether it is a
GENUINE anomaly requiring action or a benign event that was over-flagged. If
genuine, classify the root cause and choose ONE routing decision.

How to choose the routing decision:

AUTO_REMEDIATE — matches a well-understood pattern with a safe, standard fix that
carries no financial or data-integrity risk; the system can act without a human.
  e.g. "A nightly inventory feed failed once after a brief network blip; the next
  scheduled attempt will retry." -> AUTO_REMEDIATE (confidence ~0.90)

INVESTIGATE — the pattern is recognised but acting automatically is unsafe because
it touches financial records, could duplicate data, or the cause is ambiguous; a
human analyst should confirm first.
  e.g. "An integration produced an unexpected second posting and the downstream
  effect on the ledger is unclear." -> INVESTIGATE (confidence ~0.70)

ESCALATE — high severity, novel, or a persistent/repeated failure where autonomous
action is unsafe and a senior engineer is required.
  e.g. "A core integration has failed continuously for several hours with no
  recovery and is blocking month-end close." -> ESCALATE (confidence ~0.80)

NONE — benign/normal event that was over-flagged; no action required.
  e.g. "Elevated processing delay during a planned, expected maintenance window."
  -> NONE

Now assess THIS event:
  System:        {case['system']}
  Partner:       {case['partner']}
  Retry Count:   {case['retry_count']}
  Delay Minutes: {case['delay_minutes']}
  Signature:     {case['error_signature']}

Root cause categories: {", ".join(CATEGORIES)}

Set confidence_score to reflect genuine certainty in your routing decision:
  0.85-1.00 only when the decision is unambiguous
  0.60-0.84 when reasonably confident but some uncertainty remains
  below 0.60 when the event is unclear or you are guessing
Do NOT default to one value — vary it to reflect real certainty.

Return ONLY valid JSON, no markdown:
{{
  "is_anomaly": true or false,
  "root_cause_category": "one category above, or NONE if benign",
  "routing_decision": "AUTO_REMEDIATE | INVESTIGATE | ESCALATE | NONE",
  "confidence_score": 0.00
}}"""


def call_llm(case, llm, cache, delay, cache_file):
    prompt = build_eval_prompt(case)
    key = case["case_id"] + ":" + hashlib.sha256(prompt.encode()).hexdigest()[:16]
    if key in cache:
        return cache[key], True

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
                import re
                m = re.search(r"try again in ([0-9.]+)s", msg)
                if m:
                    wait = float(m.group(1)) + 1
                print(f"   rate limited, waiting {wait:.0f}s...")
                time.sleep(wait); attempt += 1
                if attempt > 5:
                    raise
                continue
            raise

    parsed = _extract_json(content)
    cache[key] = parsed
    save_cache(cache, cache_file)
    time.sleep(delay)
    return parsed, False


def _extract_json(text):
    import re
    text = text.strip()
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
    return {"is_anomaly": True, "root_cause_category": "NONE",
            "routing_decision": "ESCALATE", "confidence_score": 0.4}


# -------------------------------------------------------------------
# METRICS
# -------------------------------------------------------------------
def detection_metrics(cases, predictions):
    tp = fp = fn = tn = 0
    for c in cases:
        actual = c["expected_detection"]; pred = predictions[c["case_id"]]
        if pred == "ANOMALY" and actual == "ANOMALY": tp += 1
        elif pred == "ANOMALY" and actual == "NORMAL": fp += 1
        elif pred == "NORMAL" and actual == "ANOMALY": fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return dict(TP=tp, FP=fp, FN=fn, TN=tn,
                precision=precision, recall=recall, f1=f1, fpr=fpr)


def routing_accuracy(cases, routing_preds):
    correct = total = 0
    for c in cases:
        if c["case_id"] in routing_preds:
            total += 1
            if routing_preds[c["case_id"]] == c["expected_routing"]:
                correct += 1
    return (correct / total if total else 0.0), correct, total


def routing_confusion(cases, routing_preds):
    matrix = {a: {p: 0 for p in ROUTING_LABELS} for a in ROUTING_LABELS}
    for c in cases:
        exp = c["expected_routing"]
        if exp not in ROUTING_LABELS:
            continue
        pred = routing_preds.get(c["case_id"])
        if pred not in ROUTING_LABELS:
            continue
        matrix[exp][pred] += 1
    return matrix


def print_confusion(matrix):
    print("\n  Routing confusion matrix (rows = expected, cols = predicted)")
    header = "  " + " " * 16 + "".join(f"{p[:6]:>9}" for p in ROUTING_LABELS)
    print(header)
    for exp in ROUTING_LABELS:
        row = "".join(f"{matrix[exp][p]:>9}" for p in ROUTING_LABELS)
        print(f"  {exp:<16}{row}")


def calibration_summary(cases, routing_preds, conf_by_case):
    corr_conf, wrong_conf = [], []
    for c in cases:
        cid = c["case_id"]
        if cid not in routing_preds or cid not in conf_by_case:
            continue
        if c["expected_routing"] not in ROUTING_LABELS:
            continue
        conf = conf_by_case[cid]
        if routing_preds[cid] == c["expected_routing"]:
            corr_conf.append(conf)
        else:
            wrong_conf.append(conf)
    all_conf = corr_conf + wrong_conf
    print("\n  Confidence calibration (RQ1):")
    if all_conf:
        print(f"    distinct confidence values used : {sorted(set(round(x,2) for x in all_conf))}")
        print(f"    spread (min / max)              : {min(all_conf):.2f} / {max(all_conf):.2f}")
    if corr_conf:
        print(f"    mean confidence when CORRECT    : {np.mean(corr_conf):.2f}  (n={len(corr_conf)})")
    if wrong_conf:
        print(f"    mean confidence when WRONG      : {np.mean(wrong_conf):.2f}  (n={len(wrong_conf)})")
    if corr_conf and wrong_conf:
        gap = np.mean(corr_conf) - np.mean(wrong_conf)
        print(f"    separation (correct - wrong)    : {gap:+.2f}")
        if gap <= 0.05:
            print("    -> confidence does NOT separate correct from incorrect routing.")
            print("       Routing on raw LLM confidence alone is unreliable (key RQ1 finding).")
        else:
            print("    -> confidence shows some separation; calibration is partially informative.")


# -------------------------------------------------------------------
# RUN CONFIGS
# -------------------------------------------------------------------
def run_config_a(cases):
    return {c["case_id"]: ("ANOMALY" if rule_fires(c) else "NORMAL") for c in cases}


def run_config_b(cases, model):
    return {c["case_id"]: ("ANOMALY" if (rule_fires(c) and if_flags(model, c)) else "NORMAL")
            for c in cases}


def run_config_c(cases, model, delay, llm_name):
    from langchain_groq import ChatGroq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None, None, None
    llm = ChatGroq(model=llm_name, api_key=api_key)
    cache_file = cache_path(llm_name)
    cache = load_cache(cache_file)

    detection, routing, conf_by_case = {}, {}, {}
    gated = 0
    for c in cases:
        candidate = rule_fires(c) or if_flags(model, c)
        if not candidate:
            detection[c["case_id"]] = "NORMAL"
            continue
        gated += 1
        parsed, was_cached = call_llm(c, llm, cache, delay, cache_file)
        is_anom = bool(parsed.get("is_anomaly", True))
        detection[c["case_id"]] = "ANOMALY" if is_anom else "NORMAL"
        try:
            conf_by_case[c["case_id"]] = float(parsed.get("confidence_score", 0.5))
        except (TypeError, ValueError):
            conf_by_case[c["case_id"]] = 0.5
        if is_anom:
            routing[c["case_id"]] = parsed.get("routing_decision", "ESCALATE")
        tag = "cached" if was_cached else "API"
        print(f"   [{tag}] {c['case_id']} -> anomaly={is_anom} "
              f"route={parsed.get('routing_decision')} conf={parsed.get('confidence_score')}")
    print(f"   ({gated} cases reached the agent; {len(cases)-gated} gated out as normal)")
    return detection, routing, conf_by_case


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
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--ground-truth", default="ground_truth.csv",
                    help="case set to evaluate. Use a separate file (e.g. "
                         "realistic_validation.csv) to run a held-out set "
                         "without touching the original results.")
    ap.add_argument("--model", default="llama-3.1-8b-instant",
                    help="Groq chat model for Config C (e.g. llama-3.3-70b-versatile, "
                         "openai/gpt-oss-120b)")
    args = ap.parse_args()
    safe_model = args.model.replace("/", "_").replace(":", "_")

    cases = load_cases(args.ground_truth)
    # Namespace outputs by case set so a held-out run never overwrites the
    # synthetic results already reported.
    stem = os.path.splitext(os.path.basename(args.ground_truth))[0]
    suffix = "" if stem == "ground_truth" else f"_{stem}"
    print(f"Loaded {len(cases)} ground-truth cases.")
    print(f"LLM for Config C: {args.model}")
    model = train_isolation_forest()
    print("Isolation Forest trained on synthetic normal distribution.\n")

    results = {}

    print("=" * 60); print("CONFIG A — Rules only")
    a = run_config_a(cases); ma = detection_metrics(cases, a)
    results["A_rules"] = ma; print_metrics("Config A (rules only)", ma)

    print("\n" + "=" * 60); print("CONFIG B — Isolation Forest + Rules")
    b = run_config_b(cases, model); mb = detection_metrics(cases, b)
    results["B_if_rules"] = mb; print_metrics("Config B (IF + rules)", mb)

    routing_acc = None
    if not args.no_llm:
        print("\n" + "=" * 60)
        print("CONFIG C — Full agent (gate + few-shot LLM review + routing)")
        det_c, route_c, conf_c = run_config_c(cases, model, args.delay, args.model)
        if det_c is None:
            print("\nWARNING: GROQ_API_KEY not set — Config C skipped.")
        else:
            mc = detection_metrics(cases, det_c)
            results["C_agent"] = mc
            print_metrics("Config C (full agent)", mc)

            acc, correct, total = routing_accuracy(cases, route_c)
            routing_acc = (acc, correct, total)
            print(f"\n  Routing accuracy (RQ1): {acc*100:.1f}%  ({correct}/{total} correct)")
            print_confusion(routing_confusion(cases, route_c))
            calibration_summary(cases, route_c, conf_c)

            # per-case routing CSV (per-model filename)
            routing_csv = f"results_routing_{safe_model}{suffix}.csv"
            with open(routing_csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["case_id", "failure_category", "expected_routing",
                            "predicted_routing", "confidence", "correct"])
                for c in cases:
                    cid = c["case_id"]
                    if cid in route_c:
                        pred = route_c[cid]
                        w.writerow([cid, c["failure_category"], c["expected_routing"],
                                    pred, conf_c.get(cid, ""),
                                    int(pred == c["expected_routing"])])
    else:
        print("\n(Config C skipped via --no-llm)")

    detection_csv = f"results_detection_{safe_model}{suffix}.csv"
    with open(detection_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["configuration", "precision", "recall", "f1", "fpr",
                    "TP", "FP", "FN", "TN"])
        for name, m in results.items():
            w.writerow([name, f"{m['precision']:.4f}", f"{m['recall']:.4f}",
                        f"{m['f1']:.4f}", f"{m['fpr']:.4f}",
                        m["TP"], m["FP"], m["FN"], m["TN"]])

    print("\n" + "=" * 60); print("SUMMARY (detection — RQ3)")
    print(f"{'Config':<22}{'Prec':>7}{'Rec':>7}{'F1':>7}{'FPR':>7}")
    labels = {"A_rules": "A rules", "B_if_rules": "B IF+rules", "C_agent": "C agent"}
    for name, m in results.items():
        print(f"{labels.get(name, name):<22}"
              f"{m['precision']*100:6.1f}{m['recall']*100:7.1f}"
              f"{m['f1']*100:7.1f}{m['fpr']*100:7.1f}")
    if routing_acc:
        print(f"\nRQ1 routing accuracy (Config C): {routing_acc[0]*100:.1f}%")
    print(f"\nOK: Wrote {detection_csv}"
          + (f" and {routing_csv}" if routing_acc else ""))


if __name__ == "__main__":
    main()
