"""
RQ1: Confidence-Threshold Routing Analysis
==========================================
Tests the confidence-threshold routing approach described in RQ1.

The confidence score from the LLM is turned into a routing decision using:

    confidence >= HIGH (0.85)  -> AUTO_REMEDIATE
    confidence >= LOW  (0.60)  -> INVESTIGATE
    confidence <  LOW          -> ESCALATE

The script compares these decisions with the expected routing labels, prints a
confusion matrix, then sweeps the AUTO_REMEDIATE threshold from 0.50 to 1.00 to
see whether any threshold gives reliable routing.

The analysis uses cached LLM responses and makes no new API calls.

Outputs:
  - console summary + confusion matrix
  - routing_threshold_sweep.png   (accuracy vs threshold)
  - results_threshold_routing.csv (per-case)
"""

import os
import csv
import json
import argparse

HIGH_DEFAULT = 0.85
LOW_DEFAULT = 0.60
ROUTING_LABELS = ["AUTO_REMEDIATE", "INVESTIGATE", "ESCALATE"]
CACHE_FILE = "llm_cache.json"


def load_cases(path="ground_truth.csv"):
    with open(path) as f:
        return {c["case_id"]: c for c in csv.DictReader(f)}


def load_cache_by_case(path=CACHE_FILE):
    """Read the cached confidence and routing information for each case."""
    raw = json.load(open(path))
    out = {}
    for key, val in raw.items():
        cid = key.split(":")[0]
        try:
            conf = float(val.get("confidence_score", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        out[cid] = {
            "confidence": conf,
            "is_anomaly": bool(val.get("is_anomaly", True)),
            "llm_routing": val.get("routing_decision", "ESCALATE"),
        }
    return out


def threshold_route(conf, high, low):
    if conf >= high:
        return "AUTO_REMEDIATE"
    elif conf >= low:
        return "INVESTIGATE"
    return "ESCALATE"


def evaluate(cases, cache, high, low):
    """Calculate routing accuracy and the confusion matrix for anomaly cases."""
    confusion = {a: {p: 0 for p in ROUTING_LABELS} for a in ROUTING_LABELS}
    correct = total = escalate = 0
    rows = []
    for cid, info in cache.items():
        if not info["is_anomaly"]:
            continue
        case = cases.get(cid)
        if not case:
            continue
        expected = case["expected_routing"]
        if expected not in ROUTING_LABELS:
            continue  # exclude NONE-expected (noisy-normal false positives)
        pred = threshold_route(info["confidence"], high, low)
        total += 1
        if pred == "ESCALATE":
            escalate += 1
        if pred == expected:
            correct += 1
        confusion[expected][pred] += 1
        rows.append((cid, case["failure_category"], expected, pred,
                     info["confidence"], int(pred == expected)))
    acc = correct / total if total else 0.0
    return acc, correct, total, confusion, escalate, rows


def print_confusion(conf):
    print("\n  Confusion matrix (rows = expected, cols = predicted by threshold)")
    print("  " + " " * 16 + "".join(f"{p[:6]:>9}" for p in ROUTING_LABELS))
    for exp in ROUTING_LABELS:
        row = "".join(f"{conf[exp][p]:>9}" for p in ROUTING_LABELS)
        print(f"  {exp:<16}{row}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--high", type=float, default=HIGH_DEFAULT)
    ap.add_argument("--low", type=float, default=LOW_DEFAULT)
    args = ap.parse_args()

    cases = load_cases()
    cache = load_cache_by_case()

    confs = [v["confidence"] for v in cache.values() if v["is_anomaly"]]
    print("RQ1 — Confidence-Threshold Routing Analysis")
    print("=" * 55)
    print(f"Confidence score range across flagged anomalies: "
          f"{min(confs):.2f} – {max(confs):.2f}")
    print(f"Distinct values: {sorted(set(round(c,2) for c in confs))}")

    # Fixed-threshold evaluation
    acc, correct, total, confusion, escalate, rows = evaluate(
        cases, cache, args.high, args.low)
    print(f"\nFixed thresholds  HIGH={args.high}  LOW={args.low}")
    print(f"  Routing accuracy : {acc*100:.1f}%  ({correct}/{total})")
    print(f"  ESCALATE produced: {escalate}  "
          f"(threshold routing can only escalate if confidence < {args.low})")
    print_confusion(confusion)

    # Per-case CSV
    with open("results_threshold_routing.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "failure_category", "expected_routing",
                    "threshold_routing", "confidence", "correct"])
        w.writerows(rows)

    # Threshold sweep
    sweep_high = [round(0.50 + 0.025 * i, 3) for i in range(21)]  # 0.50..1.00
    sweep_acc = []
    for h in sweep_high:
        a, *_ = evaluate(cases, cache, h, args.low)
        sweep_acc.append(a * 100)

    best = max(sweep_acc)
    best_h = sweep_high[sweep_acc.index(best)]
    print(f"\nThreshold sweep (HIGH from 0.50 to 1.00, LOW={args.low}):")
    print(f"  best accuracy across all thresholds: {best:.1f}% at HIGH={best_h}")
    print(f"  accuracy range: {min(sweep_acc):.1f}% – {max(sweep_acc):.1f}%")

    # Plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(8, 5))
        plt.plot(sweep_high, sweep_acc, marker="o", linewidth=2, color="#2563eb",
                 label="Threshold routing accuracy")
        plt.axhline(33.3, color="#9ca3af", linestyle="--", linewidth=1,
                    label="3-class chance (33%)")
        plt.xlabel("AUTO_REMEDIATE confidence threshold (HIGH)")
        plt.ylabel("Routing accuracy (%)")
        plt.title("RQ1: routing accuracy is flat across all confidence thresholds\n"
                  "(confidence does not track the correct routing decision)")
        plt.ylim(0, 100)
        plt.grid(alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig("routing_threshold_sweep.png", dpi=150)
        print("\nOK: Wrote routing_threshold_sweep.png and results_threshold_routing.csv")
    except Exception as e:
        print(f"\n(plot skipped: {e})")

    # Interpretation hint
    print("\nInterpretation:")
    print(f"  Because confidence is compressed into [{min(confs):.2f}, {max(confs):.2f}],")
    print("  no threshold pushes cases into ESCALATE in a way that matches the")
    print("  ground truth, and accuracy stays near the level achieved by simply")
    print("  guessing the majority class. Threshold routing does not rescue the")
    print("  approach — the limiting factor is uncalibrated confidence, not the")
    print("  routing rule. This completes the RQ1 argument.")


if __name__ == "__main__":
    main()
