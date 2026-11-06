"""Trains the Talent Screening model on SYNTHETIC data and writes what the Lambda ships.

Run with: uv run --group train python apps/talent_screening/training/train.py

The rows are invented here from a hidden logistic rule plus noise and are never written to disk.
There are no names, IDs or protected attributes. The output is `coefficients.json` (shipped) and
`golden.json` (held-out inputs with scikit-learn's probabilities, for the pure-Python test). Neither
file holds a timestamp, so a retrain gives the same files. This script is not in the zip.
"""

import json
import math
import random
import sys
from pathlib import Path

SEED = 20261106
ROWS = 2000
HOLDOUT = 0.2
GOLDEN_ROWS = 50
MODEL_ID = "model:screening-lr"
MODEL_VERSION = "1.0.0"
FEATURES = [
    "years_experience",
    "skills_match",
    "assessment_score",
    "certifications",
    "relevant_projects",
]
# What the model saw. Outside it an applicant is still ranked but flagged, because the score is an
# extrapolation. Refusing here would turn away anyone with over 20 years' experience: an age proxy.
TRAINING_RANGES = {
    "years_experience": (0, 20),
    "skills_match": (0.0, 1.0),
    "assessment_score": (30, 100),
    "certifications": (0, 5),
    "relevant_projects": (0, 10),
}
# What can exist. Outside it the request is refused (ADR 0024, decision 6).
VALID_RANGES = {
    "years_experience": (0, 60),
    "skills_match": (0.0, 1.0),
    "assessment_score": (0, 100),
    "certifications": (0, 60),
    "relevant_projects": (0, 60),
}
HERE = Path(__file__).resolve().parent


def generate(rng: random.Random, count: int) -> tuple[list[list[float]], list[int]]:
    rows, labels = [], []
    for _ in range(count):
        years, _, assessment, certifications, projects = TRAINING_RANGES.values()
        row = [
            float(rng.randint(*years)),
            round(rng.random(), 3),
            float(rng.randint(*assessment)),
            float(rng.randint(*certifications)),
            float(rng.randint(*projects)),
        ]
        z = -6.0 + 0.12 * row[0] + 3.0 * row[1] + 0.03 * row[2] + 0.25 * row[3] + 0.2 * row[4]
        z += rng.gauss(0, 0.5)
        rows.append(row)
        labels.append(1 if rng.random() < 1 / (1 + math.exp(-z)) else 0)
    return rows, labels


def build() -> tuple[dict, dict]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler

    rows, labels = generate(random.Random(SEED), ROWS)
    cut = int(ROWS * (1 - HOLDOUT))
    scaler = StandardScaler().fit(rows[:cut])
    model = LogisticRegression(tol=1e-10, max_iter=10000)
    model.fit(scaler.transform(rows[:cut]), labels[:cut])
    held = rows[cut:]
    probabilities = model.predict_proba(scaler.transform(held))[:, 1]
    auc = roc_auc_score(labels[cut:], probabilities)
    coefficients = {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "synthetic_training_data": True,
        "seed": SEED,
        "feature_names": FEATURES,
        "means": [float(v) for v in scaler.mean_],
        "scales": [float(v) for v in scaler.scale_],
        "coefficients": [float(v) for v in model.coef_[0]],
        "intercept": float(model.intercept_[0]),
        "auc": float(auc),
        "valid_ranges": {name: list(bounds) for name, bounds in VALID_RANGES.items()},
        "training_ranges": {name: list(bounds) for name, bounds in TRAINING_RANGES.items()},
    }
    golden = {
        "cases": [
            {"features": dict(zip(FEATURES, row, strict=True)), "probability": float(p)}
            for row, p in zip(held[:GOLDEN_ROWS], probabilities[:GOLDEN_ROWS], strict=True)
        ]
    }
    return coefficients, golden


def main(out_dir: Path = HERE.parent) -> None:
    """Writes `coefficients.json` to `out_dir` and `golden.json` to its `training/` folder."""
    coefficients, golden = build()
    (out_dir / "training").mkdir(exist_ok=True)
    (out_dir / "coefficients.json").write_text(json.dumps(coefficients, indent=2) + "\n")
    (out_dir / "training" / "golden.json").write_text(json.dumps(golden, indent=2) + "\n")
    print(f"holdout auc {coefficients['auc']:.4f}", file=sys.stderr)


if __name__ == "__main__":
    main()
