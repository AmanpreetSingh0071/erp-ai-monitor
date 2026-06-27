"""
RQ1 Extension — Self-Consistency Confidence
===========================================
Tests whether an AGREEMENT-based uncertainty signal discriminates correct from
incorrect routing better than the model's SELF-REPORTED confidence (which was
found non-discriminative, AUROC 0.46).

Idea (Wang et al., 2022, self-consistency): query the LLM K times on the same
case at temperature > 0 so answers vary. The self-consistency score is the
fraction of samples agreeing with the modal (most frequent) routing decision.
The modal decision is the prediction; its agreement fraction is the new
confidence signal.

Hypothesis: cases the model answers consistently (e.g. 5/5) are more likely
correct than cases it answers inconsistently (e.g. 2/5), so self-consistency
should achieve AUROC > 0.5 — recovering discrimination that self-reported
confidence lacked.

Two possible findings, both defensible:
  (a) self-consistency AUROC >> 0.46  -> agreement-based confidence works where
      self-reported confidence fails (positive contribution).
  (b) self-consistency AUROC ~ 0.5    -> even agreement fails, implying the
      limit is the model's underlying competence, not just its self-reporting.

Every sample is cached (keyed by case + sample index + temperature), so the
first run makes the API calls and all re-runs are instant and reproducible.

Usage
-----
  # quick smoke test against the real API first (5 cases, 3 samples):
  python run_self_consistency.py --limit 5 --k 3
  # full run:
  python run_self_consistency.py --k 5 --temperature 0.7
"""

import os
import csv
import json
import math
import time
import hashlib
import argparse
from collections import Counter

import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROUTING_LABELS = ["AUTO_REMEDIATE", "INVESTIGATE", "ESCALATE"]
CATEGORIES = [
    "EDI_MAPPING_ERROR", "PARTNER_API_TIMEOUT", "NETSUITE_QUEUE_BACKLOG",
    "DUPLICATE_TRANSACTION", "AUTH_FAILURE", "RATE_LIMIT_EXCEEDED",
]
CACHE_FILE = "self_consistency_cache.json"


def load_anomaly_cases(path="ground_truth.csv"):
    cases = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["expected_detection"] == "ANOMALY":
                cases.append(r)
    return cases


def build_prompt(case):
    # Same few-shot routing prompt as the main experiment, for comparability.
    return f"""You are an ERP integration monitoring agent (Oracle NetSuite, SAP, EDI).

Classify the root cause and choose ONE routing decision for this event.

AUTO_REMEDIATE - well-understood pattern, safe standard fix, no financial/data risk.
INVESTIGATE    - recognised but touches financial records, could duplicate data, or
                 the cause is ambiguous; a human should confirm.
ESCALATE       - high severity, novel, or persistent failure; unsafe to act
                 autonomously, needs a senior engineer.

Event:
  System:        {case['system']}
  Partner:       {case['partner']}
  Retry Count:   {case['retry_count']}
  Delay Minutes: {case['delay_minutes']}
  Signature:     {case['error_signature']}

Root cause categories: {", ".join(CATEGORIES)}

Return ONLY JSON: {{"routing_decision": "AUTO_REMEDIATE | INVESTIGATE | ESCALATE"}}"""


def extract_routing(text):
    import re
    text = re.sub(r"^```(json)?", "", text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        d = json.loads(text)
        r = d.get("routing_decision", "").upper()
        if r in ROUTING_LABELS:
            return r
    except Exception:
        pass
    for lbl in ROUTING_LABELS:           # fallback: substring search
        if lbl in text.upper():
            return lbl
    return "INVESTIGATE"


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE))
        except Exception:
            return {}
    return {}


def save_cache(c):
    json.dump(c, open(CACHE_FILE, "w"), indent=2)


def sample_once(case, idx, llm, cache, temperature, delay):
    prompt = build_prompt(case)
    key = f"{case['case_id']}:s{idx}:T{temperature}:" + hashlib.sha256(prompt.encode()).hexdigest()[:12]
    if key in cache:
        return cache[key], True
    attempt = 0
    while True:
        try:
            resp = llm.invoke(prompt)
            routing = extract_routing(resp.content)
            break
        except Exception as e:
            msg = str(e)
            if "rate_limit" in msg or "429" in msg:
                import re
                m = re.search(r"try again in ([0-9.]+)s", msg)
                wait = (float(m.group(1)) + 1) if m else 20
                print(f"   rate limited, waiting {wait:.0f}s...")
                time.sleep(wait); attempt += 1
                if attempt > 5:
                    raise
                continue
            raise
    cache[key] = routing
    save_cache(cache)
    time.sleep(delay)
    return routing, False


def auroc(scores, labels):
    """AUROC of a score predicting a binary label.

    Self-consistency scores are heavily tied (only a few distinct values), so
    correct mid-rank tie handling matters. Use sklearn when available; the
    fallback uses average ranks (Mann-Whitney U with tie correction)."""
    scores = np.asarray(scores, float); labels = np.asarray(labels, int)
    if len(set(labels.tolist())) < 2:
        return float("nan")
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(labels, scores))
    except Exception:
        pass
    # Fallback: average-rank (tie-corrected) Mann-Whitney U
    from scipy.stats import rankdata
    ranks = rankdata(scores)              # average ranks handle ties
    n_pos = int(labels.sum()); n_neg = len(labels) - n_pos
    rank_sum_pos = ranks[labels == 1].sum()
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def ece(scores, labels, n_bins=10):
    scores = np.asarray(scores, float); labels = np.asarray(labels, int)
    bins = np.linspace(0, 1, n_bins + 1); e = 0.0; N = len(scores)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i+1]
        m = (scores > lo) & (scores <= hi) if i > 0 else (scores >= lo) & (scores <= hi)
        if m.sum():
            e += (m.sum()/N) * abs(labels[m].mean() - scores[m].mean())
    return e


def entropy_certainty(counts, k):
    """1 - normalised Shannon entropy of the K-sample distribution.

    An alternative uncertainty signal to modal agreement: it uses the full
    answer distribution, so it can distinguish e.g. a 3/2 two-way split from a
    3/1/1 three-way split (which modal agreement cannot). Normalised by log(3)
    since there are three possible routing labels. Returns 1.0 for unanimous,
    lower for more diffuse distributions."""
    probs = [v / k for v in counts.values()]
    H = -sum(p * math.log(p) for p in probs if p > 0)
    return 1 - (H / math.log(3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5, help="samples per case")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--limit", type=int, default=0, help="limit cases (smoke test)")
    args = ap.parse_args()

    cases = load_anomaly_cases()
    if args.limit:
        cases = cases[:args.limit]

    from langchain_groq import ChatGroq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not set — cannot run self-consistency (needs live sampling).")
        return
    llm = ChatGroq(model="llama-3.1-8b-instant", api_key=api_key,
                   temperature=args.temperature)
    cache = load_cache()

    print(f"Self-consistency: {len(cases)} anomaly cases x K={args.k} samples "
          f"at temperature {args.temperature}")
    print(f"(~{len(cases)*args.k} calls on first run; cached thereafter)\n")

    rows = []
    for c in cases:
        samples = []
        for i in range(args.k):
            r, cached = sample_once(c, i, llm, cache, args.temperature, args.delay)
            samples.append(r)
        counts = Counter(samples)
        modal, modal_n = counts.most_common(1)[0]
        consistency = modal_n / args.k
        correct = int(modal == c["expected_routing"])
        rows.append({
            "case_id": c["case_id"],
            "expected_routing": c["expected_routing"],
            "modal_routing": modal,
            "consistency": consistency,
            "entropy_certainty": entropy_certainty(counts, args.k),
            "n_distinct": len(counts),
            "correct": correct,
            "samples": "|".join(samples),
        })
        print(f"  {c['case_id']}: {dict(counts)} -> modal={modal} "
              f"consistency={consistency:.2f} {'✓' if correct else '✗'}")

    # Metrics
    cons = [r["consistency"] for r in rows]
    ent = [r["entropy_certainty"] for r in rows]
    corr = [r["correct"] for r in rows]
    acc = np.mean(corr)
    sc_auroc = auroc(cons, corr)
    sc_auroc_ent = auroc(ent, corr)
    sc_ece = ece(cons, corr)

    # Escalation behaviour + uncertainty shape
    modal_routes = Counter(r["modal_routing"] for r in rows)
    threeway = sum(1 for r in rows if r["n_distinct"] >= 3)

    print("\n" + "=" * 56)
    print("SELF-CONSISTENCY RESULTS")
    print(f"  Routing accuracy (modal)      : {acc*100:.1f}%")
    print(f"  AUROC (modal consistency)     : {sc_auroc:.3f}")
    print(f"  AUROC (entropy certainty)     : {sc_auroc_ent:.3f}")
    print(f"  ECE  (consistency as conf)    : {sc_ece:.3f}")
    print(f"  Modal routing distribution    : {dict(modal_routes)}")
    print(f"  Cases with a 3-way split      : {threeway}/{len(rows)}"
          f"  ({'entropy adds info' if threeway else 'entropy == consistency here'})")

    print("\nCONTRAST WITH SELF-REPORTED CONFIDENCE (from earlier run):")
    print(f"  {'metric':<24}{'self-reported':>15}{'self-consistency':>18}")
    print(f"  {'Routing accuracy':<24}{'45.7%':>15}{acc*100:>17.1f}%")
    print(f"  {'AUROC':<24}{'0.461':>15}{sc_auroc:>18.3f}")
    if sc_auroc > 0.6:
        print("\n  => Self-consistency RECOVERS discrimination that self-reported")
        print("     confidence lacked: agreement tracks correctness. Positive result.")
    elif sc_auroc > 0.55:
        print("\n  => Self-consistency shows modest discrimination, an improvement")
        print("     over self-reported confidence but still limited.")
    else:
        print("\n  => Self-consistency does NOT recover discrimination: even agreement")
        print("     fails, implying the limit is model competence, not self-reporting.")

    # Accuracy by consistency level
    print("\nAccuracy by consistency level (all cases):")
    by_level = {}
    for r in rows:
        by_level.setdefault(r["consistency"], []).append(r["correct"])
    for lvl in sorted(by_level):
        v = by_level[lvl]
        print(f"  consistency {lvl:.2f}: accuracy {np.mean(v)*100:5.1f}%  (n={len(v)})")

    # Two-class scoped analysis: restrict to decisions the model can represent
    # (AUTO_REMEDIATE vs INVESTIGATE). The model almost never samples ESCALATE,
    # so ESCALATE-expected cases are near-unwinnable and depress every signal;
    # scoping to representable decisions gives a fair test of discrimination.
    two = [r for r in rows if r["expected_routing"] in ("AUTO_REMEDIATE", "INVESTIGATE")]
    if two:
        t_cons = [r["consistency"] for r in two]
        t_ent = [r["entropy_certainty"] for r in two]
        t_corr = [r["correct"] for r in two]
        print("\n" + "-" * 56)
        print("TWO-CLASS SCOPED  (expected AUTO or INVESTIGATE; ESCALATE-expected dropped)")
        print(f"  cases retained                : {len(two)}/{len(rows)}")
        print(f"  routing accuracy (modal)      : {np.mean(t_corr)*100:.1f}%")
        print(f"  AUROC (modal consistency)     : {auroc(t_cons, t_corr):.3f}")
        print(f"  AUROC (entropy certainty)     : {auroc(t_ent, t_corr):.3f}")
        t_by = {}
        for r in two:
            t_by.setdefault(r["consistency"], []).append(r["correct"])
        print("  accuracy by consistency level:")
        for lvl in sorted(t_by):
            v = t_by[lvl]
            print(f"     {lvl:.2f}: {np.mean(v)*100:5.1f}%  (n={len(v)})")
        print("\n  Interpretation: scoping to representable decisions is the fair test")
        print("  of whether agreement tracks correctness. Compare the two ladders:")
        print("  a steeper, higher scoped ladder means the weak overall signal is")
        print("  driven by the model's inability to represent ESCALATE, not by the")
        print("  uncertainty mechanism itself.")

    # CSV
    with open("results_self_consistency.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "expected_routing",
                          "modal_routing", "consistency", "entropy_certainty",
                          "n_distinct", "correct", "samples"])
        w.writeheader(); w.writerows(rows)

    # Plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        levels = sorted(by_level)
        accs = [np.mean(by_level[l]) * 100 for l in levels]
        ns = [len(by_level[l]) for l in levels]
        plt.figure(figsize=(8, 5))
        plt.bar([f"{l:.1f}" for l in levels], accs, color="#2563eb", alpha=0.85)
        for i, (a, n) in enumerate(zip(accs, ns)):
            plt.text(i, a + 2, f"n={n}", ha="center", fontsize=9)
        plt.xlabel(f"Self-consistency (agreement over K={args.k} samples)")
        plt.ylabel("Routing accuracy (%)")
        plt.title(f"Self-consistency vs accuracy  (AUROC={sc_auroc:.2f})\n"
                  "rising bars = agreement tracks correctness")
        plt.ylim(0, 105); plt.grid(axis="y", alpha=0.3)
        plt.tight_layout(); plt.savefig("self_consistency_curve.png", dpi=150)
        print("\n✅ Wrote results_self_consistency.csv and self_consistency_curve.png")
    except Exception as e:
        print(f"\n(plot skipped: {e})")


if __name__ == "__main__":
    main()
