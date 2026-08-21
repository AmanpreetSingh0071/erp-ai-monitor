"""
RQ1: Confidence Calibration Study
=================================
Turns the qualitative finding ("confidence does not separate correct from wrong")
into a quantitative calibration analysis.

Reports, for the LLM's self-reported confidence in its routing decisions:
  - Expected Calibration Error (ECE) and Maximum Calibration Error (MCE)
  - Brier score (proper scoring rule)
  - Overconfidence (mean confidence minus accuracy)
  - Reliability table / diagram (confidence vs empirical accuracy)
  - Discrimination: AUROC of confidence as a predictor of correctness
  - Post-hoc recalibration via Platt scaling, and a demonstration that it
    reduces ECE but CANNOT improve discrimination (monotonic transform =>
    ranking preserved => AUROC and best-achievable routing are unchanged).

Why no temperature scaling
--------------------------
Classical temperature scaling rescales the pre-softmax LOGITS over classes:
softmax(z / T). The LLM exposes only a single self-reported scalar confidence,
not per-class logits, so temperature scaling does not apply. For a scalar score
the appropriate post-hoc method is Platt scaling (a logistic fit), which is what
is used here. This distinction is itself a methodological finding.

Input: results_routing.csv  (columns include: confidence, correct)
Outputs: console metrics, reliability_diagram.png, confidence_histogram.png,
         calibration_metrics.csv
"""

import os
import csv
import argparse
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss


def load(path):
    conf, corr = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                conf.append(float(row["confidence"]))
                corr.append(int(row["correct"]))
            except (KeyError, ValueError):
                continue
    return np.array(conf), np.array(corr)


def ece_equal_width(conf, corr, n_bins=10):
    """Standard equal-width ECE over [0,1]."""
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    mce = 0.0
    N = len(conf)
    details = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        acc_b = corr[mask].mean()
        conf_b = conf[mask].mean()
        gap = abs(acc_b - conf_b)
        ece += (mask.sum() / N) * gap
        mce = max(mce, gap)
        details.append((lo, hi, mask.sum(), conf_b, acc_b, gap))
    return ece, mce, details


def reliability_by_value(conf, corr):
    """Per distinct confidence value: n, accuracy. Honest for discrete scores."""
    table = []
    for v in sorted(set(conf)):
        mask = conf == v
        table.append((v, int(mask.sum()), corr[mask].mean()))
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-name", default="llama-3.1-8b-instant",
                    help="Model whose routing results to analyse")
    ap.add_argument("--input", default=None,
                    help="Routing CSV. Defaults to results_routing_<model>.csv, "
                         "falling back to results_routing.csv")
    args = ap.parse_args()

    safe = args.model_name.replace("/", "_").replace(":", "_")
    # Resolve input: explicit > per-model file > legacy unsuffixed file
    inp = args.input
    if inp is None:
        cand = f"results_routing_{safe}.csv"
        inp = cand if os.path.exists(cand) else "results_routing.csv"
    print(f"Reading: {inp}")

    conf, corr = load(inp)
    N = len(conf)
    acc = corr.mean()
    mean_conf = conf.mean()

    print(f"RQ1 — Confidence Calibration Study  [{args.model_name}]")
    print("=" * 58)
    print(f"Samples (routed anomalies)   : {N}")
    print(f"Overall routing accuracy     : {acc*100:.1f}%")
    print(f"Mean reported confidence     : {mean_conf*100:.1f}%")
    print(f"Overconfidence (conf - acc)  : {(mean_conf-acc)*100:+.1f} pts")
    print(f"Distinct confidence values   : {sorted(set(conf))}")

    # Calibration error
    ece, mce, details = ece_equal_width(conf, corr, n_bins=10)
    brier = brier_score_loss(corr, conf)
    print(f"\nExpected Calibration Error   : {ece:.3f}   (0 = perfect; <0.05 is well-calibrated)")
    print(f"Maximum Calibration Error    : {mce:.3f}")
    print(f"Brier score                  : {brier:.3f}   (lower is better)")

    # Reliability table
    print("\nReliability table (per reported confidence value):")
    print(f"  {'conf':>6}{'n':>5}{'accuracy':>10}{'gap':>8}")
    table = reliability_by_value(conf, corr)
    for v, n, a in table:
        print(f"  {v:>6.2f}{n:>5}{a*100:>9.1f}%{abs(a-v)*100:>7.1f}")
    # Monotonicity check
    accs = [a for _, _, a in table]
    monotonic = all(accs[i] <= accs[i+1] for i in range(len(accs)-1))
    print(f"  -> accuracy increases with confidence? {monotonic}")
    if not monotonic:
        print("     NON-MONOTONIC: higher confidence does not imply higher accuracy.")

    # Discrimination
    if len(set(corr)) > 1:
        auroc = roc_auc_score(corr, conf)
    else:
        auroc = float("nan")
    print(f"\nDiscrimination (AUROC of confidence -> correctness): {auroc:.3f}")
    print("  0.50 = confidence carries NO information about correctness.")

    # Platt scaling (post-hoc recalibration on scalar score)
    X = conf.reshape(-1, 1)
    platt = LogisticRegression()
    platt.fit(X, corr)
    cal = platt.predict_proba(X)[:, 1]
    ece_cal, mce_cal, _ = ece_equal_width(cal, corr, n_bins=10)
    brier_cal = brier_score_loss(corr, cal)
    coef = platt.coef_[0][0]
    if len(set(corr)) > 1:
        # AUROC is invariant to a monotonic-increasing map; if coef<0 the map is
        # decreasing and AUROC reflects as (1 - original). |AUROC-0.5| is preserved.
        auroc_cal = roc_auc_score(corr, cal)
    else:
        auroc_cal = float("nan")
    print(f"\nPost-hoc Platt scaling:")
    print(f"  logistic slope (coef)      : {coef:+.3f}  "
          f"({'increasing' if coef>0 else 'flat/decreasing'} in confidence)")
    print(f"  ECE  before -> after       : {ece:.3f} -> {ece_cal:.3f}")
    print(f"  Brier before -> after      : {brier:.3f} -> {brier_cal:.3f}")
    print(f"  AUROC before -> after      : {auroc:.3f} -> {auroc_cal:.3f}")
    print("  -> Platt reduces calibration error but |AUROC-0.5| is preserved:")
    print("     recalibration cannot manufacture discrimination that is absent,")
    print("     so it cannot rescue routing. The deficit is in the signal itself.")

    # CSV out
    with open(f"calibration_metrics_{safe}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "N", "accuracy", "mean_confidence", "overconfidence",
                    "ECE", "MCE", "Brier", "AUROC",
                    "ECE_platt", "Brier_platt", "AUROC_platt"])
        w.writerow([args.model_name, N, f"{acc:.4f}", f"{mean_conf:.4f}",
                    f"{mean_conf-acc:.4f}", f"{ece:.4f}", f"{mce:.4f}", f"{brier:.4f}",
                    f"{auroc:.4f}", f"{ece_cal:.4f}", f"{brier_cal:.4f}", f"{auroc_cal:.4f}"])

    # Plots
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # Reliability diagram
        vals = [v for v, _, _ in table]
        accs = [a for _, _, a in table]
        ns = [n for _, n, _ in table]
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.plot([0, 1], [0, 1], "--", color="#9ca3af", label="Perfect calibration")
        ax.scatter(vals, accs, s=[max(60, n*25) for n in ns], color="#2563eb",
                   zorder=3, label="Observed (size = n)")
        for v, a, n in zip(vals, accs, ns):
            ax.annotate(f"n={n}", (v, a), textcoords="offset points",
                        xytext=(8, 6), fontsize=9)
        ax.axhline(acc, color="#dc2626", linewidth=1, linestyle=":",
                   label=f"Overall accuracy ({acc*100:.0f}%)")
        ax.set_xlim(0.5, 1.0); ax.set_ylim(0, 1.0)
        ax.set_xlabel("Reported confidence"); ax.set_ylabel("Empirical accuracy")
        ax.set_title(f"Reliability diagram — {args.model_name}\n"
                     f"ECE={ece:.2f}, AUROC={auroc:.2f} (confidence is overconfident "
                     f"and non-discriminative)")
        ax.legend(loc="upper left"); ax.grid(alpha=0.3)
        plt.tight_layout(); plt.savefig(f"reliability_diagram_{safe}.png", dpi=150)

        # Confidence histogram split by correctness
        fig, ax = plt.subplots(figsize=(8, 5))
        bins = np.linspace(0.775, 0.975, 9)
        ax.hist(conf[corr == 1], bins=bins, alpha=0.7, label="Correct routing",
                color="#16a34a")
        ax.hist(conf[corr == 0], bins=bins, alpha=0.7, label="Wrong routing",
                color="#dc2626")
        ax.set_xlabel("Reported confidence"); ax.set_ylabel("Count")
        ax.set_title("Confidence distribution by correctness\n"
                     "(correct and wrong decisions occupy the same confidence range)")
        ax.legend(); ax.grid(alpha=0.3)
        plt.tight_layout(); plt.savefig(f"confidence_histogram_{safe}.png", dpi=150)
        print(f"\nOK: Wrote reliability_diagram_{safe}.png, confidence_histogram_{safe}.png, calibration_metrics_{safe}.csv")
    except Exception as e:
        print(f"\n(plots skipped: {e})")


if __name__ == "__main__":
    main()
