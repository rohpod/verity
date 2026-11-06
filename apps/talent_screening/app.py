"""Talent Screening: scores and ranks job applicants with a small logistic regression.

A REAL model, trained on SYNTHETIC data (see `training/train.py`), with pure-Python inference so
the zip needs no numerical library. It is decision support only: a person decides. The input
schema refuses unknown fields, so a protected attribute cannot reach the model. It calls no
provider, so it writes no usage records, and it logs counts only, never applicant data.
"""

import functools
import json
import logging
import math
import os
from pathlib import Path

log = logging.getLogger("talent_screening")


def sigmoid(z: float) -> float:
    """Numerically stable for large positive and negative z."""
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def probability(model: dict, features: dict) -> float:
    z = model["intercept"]
    for name, mean, scale, weight in zip(
        model["feature_names"], model["means"], model["scales"], model["coefficients"], strict=True
    ):
        z += weight * (_number(features[name], name) - mean) / scale
    return sigmoid(z)


def check_ranges(model: dict, features: dict) -> list[str]:
    """Refuses a value that cannot exist and lists the features outside what the model saw.

    The error names the feature, never the value, because the value is applicant data. A value
    outside the training range is ranked, not refused: refusing it would turn away applicants
    with long careers, which is an age proxy (ADR 0024, decision 6)."""
    outside = []
    for name in model["feature_names"]:
        value = _number(features[name], name)
        low, high = model["valid_ranges"][name]
        if not low <= value <= high:
            raise ValueError(f"{name} is outside the range that can exist")
        low, high = model["training_ranges"][name]
        if not low <= value <= high:
            outside.append(name)
    return sorted(outside)


def run(event: dict, model: dict) -> dict:
    names = set(model["feature_names"])
    applicants = event["applicants"]
    if not isinstance(applicants, list):
        raise ValueError("applicants must be a list")
    scored = []
    for applicant in applicants:
        ref = applicant.get("applicant_ref")
        if not isinstance(ref, str) or not ref:
            raise ValueError("applicant_ref is required")
        if set(applicant) != names | {"applicant_ref"}:
            raise ValueError(
                "each applicant must have applicant_ref and exactly the model features"
            )
        outside = check_ranges(model, applicant)
        scored.append((ref, probability(model, applicant), outside))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    log.info("scored %d applicants", len(scored))
    return {
        "model_id": model["model_id"],
        "model_version": model["model_version"],
        "decision_support_only": True,
        "synthetic_training_data": True,
        "ranking": [
            {
                "rank": i,
                "applicant_ref": ref,
                "score": score,
                "outside_training_range": outside,
            }
            for i, (ref, score, outside) in enumerate(scored, start=1)
        ],
    }


@functools.cache
def _model() -> dict:
    log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    path = Path(__file__).parent / os.environ["COEFFICIENTS_FILE"]
    return json.loads(path.read_text())


def handler(event, context):
    return run(event, _model())
