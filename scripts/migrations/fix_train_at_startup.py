"""
Train the detection model at startup instead of loading a pickle.

PROBLEM
    backend/main.py loads models/anomaly_model.pkl at startup, but that file is
    listed in .gitignore, so it is not in the repository. Whatever the deployed
    instance loads therefore comes from a build cache of unknown age, and cannot
    be shown to match the parameters documented in Appendix B.

    A pickle also couples the deployment to a scikit-learn version: a model
    written by 1.9.0 locally may not load under the 1.8.0 pinned in
    requirements.txt.

FIX
    Call train() from models/train_anomaly_model.py at startup. Training is
    deterministic (seed 42), takes milliseconds for 600 samples and 200
    estimators, and guarantees the served model is the documented one. The
    pickle is still written by running the script directly, for offline use.

Run from the repo root:
    python fix_train_at_startup.py
"""

import sys
from pathlib import Path

MAIN = Path("backend/main.py")

OLD = '''    print("🔄 Loading ML model...")

    try:
        model_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "anomaly_model.pkl"
        )

        if os.path.exists(model_path):
            model = joblib.load(model_path)
            print("✅ Model loaded")
        else:
            print("⚠️ Model missing")

    except Exception as e:
        print("❌ Model load error:", e)'''

NEW = '''    print("🔄 Training detection model...")

    # Trained in-process rather than loaded from a pickle. Training is
    # deterministic (seed 42) and takes milliseconds, so the served model is
    # provably the one described in Section 3.3 and Appendix B, rather than
    # whatever pickle happens to be present. It also removes a scikit-learn
    # version coupling between the training machine and the deployment.
    try:
        import importlib.util

        _tam_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "train_anomaly_model.py",
        )
        _spec = importlib.util.spec_from_file_location("train_anomaly_model", _tam_path)
        _tam = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_tam)

        model, _samples = _tam.train()
        print(
            f"✅ Model trained: L-region, {_tam.N_SAMPLES} samples, "
            f"{_tam.N_ESTIMATORS} estimators, seed {_tam.RANDOM_SEED}"
        )

    except Exception as e:
        print("❌ Model training error:", e)'''


def main():
    if not MAIN.exists():
        sys.exit("Run this from the repo root (the folder containing backend/).")
    src = MAIN.read_text()
    if "Training detection model" in src:
        sys.exit("Already patched.")
    if OLD not in src:
        sys.exit("Startup model-loading block not found; check backend/main.py manually.")
    MAIN.write_text(src.replace(OLD, NEW, 1))
    print("Patched backend/main.py: model is now trained at startup.")
    print("Expect on boot: '✅ Model trained: L-region, 600 samples, 200 estimators, seed 42'")


if __name__ == "__main__":
    main()
