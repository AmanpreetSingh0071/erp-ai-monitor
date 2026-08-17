"""
RQ1: Cross-Model Calibration Comparison
=======================================
Reads every calibration_metrics_<model>.csv in the folder and prints a
side-by-side table, so the scale comparison (e.g. 8B vs 70B vs 120B) can be
read at a glance. Run after calibration_analysis.py has been run for each model.
"""
import csv, glob, os

def main():
    files = sorted(glob.glob("calibration_metrics_*.csv"))
    # also include the legacy unsuffixed file if present
    if os.path.exists("calibration_metrics.csv"):
        files = ["calibration_metrics.csv"] + files
    if not files:
        print("No calibration_metrics_*.csv files found. Run calibration_analysis.py first.")
        return

    rows = []
    for fp in files:
        with open(fp) as f:
            for r in csv.DictReader(f):
                rows.append(r)

    if not rows:
        print("No rows found in metrics files.")
        return

    cols = ["model", "N", "accuracy", "mean_confidence", "overconfidence",
            "ECE", "AUROC", "ECE_platt", "AUROC_platt"]
    print(f"\n{'model':<26}{'N':>4}{'acc':>7}{'conf':>7}{'over':>7}"
          f"{'ECE':>7}{'AUROC':>7}{'ECE_pl':>8}{'AUROC_pl':>9}")
    print("-" * 88)
    for r in rows:
        def g(k):
            return r.get(k, "")
        try:
            print(f"{g('model')[:26]:<26}{int(float(g('N'))):>4}"
                  f"{float(g('accuracy'))*100:>6.1f}%"
                  f"{float(g('mean_confidence'))*100:>6.1f}%"
                  f"{float(g('overconfidence'))*100:>+6.1f}"
                  f"{float(g('ECE')):>7.3f}{float(g('AUROC')):>7.3f}"
                  f"{float(g('ECE_platt')):>8.3f}{float(g('AUROC_platt')):>9.3f}")
        except (ValueError, TypeError):
            print(f"{g('model'):<26} (could not parse row)")

    print("\nReading guide:")
    print("  acc      = routing accuracy        over     = overconfidence (conf - acc)")
    print("  ECE      = calibration error (0=perfect)     AUROC = discrimination (0.5=chance)")
    print("  *_pl     = after Platt recalibration")
    print("\nIf AUROC stays near 0.5 as model size grows, the limitation is intrinsic")
    print("to LLM self-reported confidence, not model scale. If AUROC rises with size,")
    print("calibration improves with scale. Either is a defensible RQ1 finding.")

if __name__ == "__main__":
    main()
