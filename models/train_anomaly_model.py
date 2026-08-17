"""
Isolation Forest Training: deployed detection model
===================================================
Trains the anomaly model used by the deployed backend and writes it to
models/anomaly_model.pkl.

The parameters here deliberately mirror train_isolation_forest() in
evaluation/run_experiment.py, so the model served by the demonstrator is
trained the same way as the one measured in the reported detection results.
Any change made here must be mirrored there, and in Appendix B of the report.

Training distribution: an L-shaped normal region. An event is treated as
normal when EITHER the retry count is low OR the delay is low, and becomes
anomalous only when both rise together. This encodes a piece of domain
knowledge: a single elevated signal is usually benign (a slow batch, a partner
service that recovers), whereas both signals rising together is the pattern
characteristic of a genuine failure.

  70% low retry (0-2)  and low delay (0-25)    core normal
  15% low retry (0-2)  and high delay (30-60)  slow but benign
  15% high retry (3-5) and low delay (0-25)    retried but benign

Parameters: 600 samples, 200 estimators, contamination 0.05, seed 42.
"""

import os

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

RANDOM_SEED = 42
N_SAMPLES = 600
N_ESTIMATORS = 200
CONTAMINATION = 0.05


def generate_normal_region(seed=RANDOM_SEED, n=N_SAMPLES):
    """Sample the L-shaped normal region described in Section 3.3."""
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n):
        r = rng.random()
        if r < 0.70:
            retry = rng.integers(0, 3)
            delay = rng.uniform(0, 25)
        elif r < 0.85:
            retry = rng.integers(0, 3)
            delay = rng.uniform(30, 60)
        else:
            retry = rng.integers(3, 6)
            delay = rng.uniform(0, 25)
        samples.append([retry, delay])
    return np.array(samples, dtype=float)


def train():
    X = generate_normal_region()
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=RANDOM_SEED,
    )
    model.fit(X)
    return model, X


def main():
    model, X = train()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(out_dir, "anomaly_model.pkl")
    joblib.dump(model, out_path)

    # Sanity check: a benign single-signal event should score as normal, an
    # event with both signals elevated should score as anomalous.
    benign = model.predict([[1.0, 40.0], [4.0, 5.0]])
    anomalous = model.predict([[5.0, 90.0], [6.0, 120.0]])

    print(f"Trained on {len(X)} samples from the L-shaped normal region")
    print(f"  estimators={N_ESTIMATORS} contamination={CONTAMINATION} seed={RANDOM_SEED}")
    print(f"  benign single-signal events  -> {benign}   (expect  1  1)")
    print(f"  both-signals-elevated events -> {anomalous}   (expect -1 -1)")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
