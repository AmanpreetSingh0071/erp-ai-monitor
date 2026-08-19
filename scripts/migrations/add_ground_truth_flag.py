"""
Add a --ground-truth flag to evaluation/run_experiment.py so a second, held-out
case set can be evaluated without touching the original 50-case run.

Also namespaces the output files by the case-set name, so running the realistic
validation set cannot overwrite the synthetic results already reported in the FPR.

Run from the evaluation/ folder:
    python add_ground_truth_flag.py
"""
import re
import sys
from pathlib import Path

P = Path("run_experiment.py")

def main():
    if not P.exists():
        sys.exit("Run this from the evaluation/ folder.")
    src = P.read_text()

    if "--ground-truth" in src:
        sys.exit("Already patched.")

    # 1. add the CLI flag next to --model
    anchor = '''    ap.add_argument("--model", default="llama-3.1-8b-instant",'''
    if anchor not in src:
        sys.exit("--model argument not found; file differs from expected.")
    src = src.replace(
        anchor,
        '''    ap.add_argument("--ground-truth", default="ground_truth.csv",
                    help="case set to evaluate. Use a separate file (e.g. "
                         "realistic_validation.csv) to run a held-out set "
                         "without touching the original results.")
''' + anchor,
        1,
    )

    # 2. pass it to load_cases and namespace the outputs
    old = """    cases = load_cases()"""
    new = """    cases = load_cases(args.ground_truth)
    # Namespace outputs by case set so a held-out run never overwrites the
    # synthetic results already reported.
    stem = os.path.splitext(os.path.basename(args.ground_truth))[0]
    suffix = "" if stem == "ground_truth" else f"_{stem}\""""
    if old not in src:
        sys.exit("load_cases() call not found.")
    src = src.replace(old, new, 1)

    src = src.replace(
        'routing_csv = f"results_routing_{safe_model}.csv"',
        'routing_csv = f"results_routing_{safe_model}{suffix}.csv"', 1)
    src = src.replace(
        'detection_csv = f"results_detection_{safe_model}.csv"',
        'detection_csv = f"results_detection_{safe_model}{suffix}.csv"', 1)

    P.write_text(src)
    print("Patched run_experiment.py")
    print("  --ground-truth <file>   evaluate a different case set")
    print("  outputs are suffixed with the case-set name, so the original")
    print("  results_*.csv files are never overwritten")

if __name__ == "__main__":
    main()
