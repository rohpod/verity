"""Talent Screening: pure-Python inference against scikit-learn's output (ADR 0023)."""

import importlib.util
import json
import logging
from pathlib import Path

import pytest
from estate_support import ROOT, load_app

APP_DIR = ROOT / "apps" / "talent_screening"
app = load_app("apps/talent_screening")
MODEL = json.loads((APP_DIR / "coefficients.json").read_text())
GOLDEN = json.loads((APP_DIR / "training" / "golden.json").read_text())
PROTECTED = {"gender", "sex", "name", "age", "ethnicity", "race", "nationality", "religion"}


def applicant(ref, **overrides):
    fields = {
        "applicant_ref": ref,
        "years_experience": 5,
        "skills_match": 0.5,
        "assessment_score": 70,
        "certifications": 1,
        "relevant_projects": 3,
    }
    return {**fields, **overrides}


def test_pure_python_matches_the_golden_probabilities_within_1e_9():
    assert len(GOLDEN["cases"]) == 50
    for case in GOLDEN["cases"]:
        assert app.probability(MODEL, case["features"]) == pytest.approx(
            case["probability"], abs=1e-9
        )


def test_the_model_is_labelled_synthetic_and_has_no_protected_attribute():
    assert MODEL["synthetic_training_data"] is True
    assert MODEL["model_id"] == "model:screening-lr"
    assert not PROTECTED & set(MODEL["feature_names"])
    assert "timestamp" not in json.dumps(MODEL)


def test_ranking_is_highest_first_with_ties_broken_by_reference():
    strong = applicant("b", skills_match=0.95, assessment_score=95, years_experience=15)
    result = app.run({"applicants": [applicant("z"), strong, applicant("a")]}, MODEL)
    assert [r["applicant_ref"] for r in result["ranking"]] == ["b", "a", "z"]
    assert [r["rank"] for r in result["ranking"]] == [1, 2, 3]
    assert result["decision_support_only"] is True
    assert result["synthetic_training_data"] is True
    assert result["model_version"] == MODEL["model_version"]


@pytest.mark.parametrize(
    "bad",
    [
        applicant("a", gender="f"),
        {k: v for k, v in applicant("a").items() if k != "skills_match"},
        {k: v for k, v in applicant("a").items() if k != "applicant_ref"},
        applicant("a", skills_match="high"),
        applicant("a", skills_match=True),
        applicant("a", skills_match=float("nan")),
        applicant(""),
    ],
)
def test_unknown_or_missing_fields_and_bad_values_are_refused(bad):
    with pytest.raises(ValueError):
        app.run({"applicants": [bad]}, MODEL)


def test_the_sigmoid_is_stable_at_the_extremes():
    assert app.sigmoid(1000) == 1.0
    assert app.sigmoid(-1000) == 0.0
    assert app.sigmoid(0) == 0.5


def test_the_handler_loads_the_shipped_coefficients(monkeypatch):
    monkeypatch.setenv("COEFFICIENTS_FILE", "coefficients.json")
    app._model.cache_clear()
    result = app.handler({"applicants": [applicant("a")]}, None)
    assert result["ranking"][0]["applicant_ref"] == "a"


def test_applicant_data_is_never_logged(caplog, monkeypatch):
    monkeypatch.setenv("COEFFICIENTS_FILE", "coefficients.json")
    app._model.cache_clear()
    with caplog.at_level(logging.DEBUG):
        app.handler({"applicants": [applicant("VERITY-CANARY-7f3a")]}, None)
    assert "CANARY" not in caplog.text


def test_retraining_reproduces_the_shipped_files(tmp_path):
    """Needs scikit-learn: `uv run --group train pytest tests/apps`. Skipped in CI."""
    pytest.importorskip("sklearn")
    spec = importlib.util.spec_from_file_location("train", APP_DIR / "training" / "train.py")
    train = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(train)
    train.main(tmp_path)
    new = json.loads((tmp_path / "coefficients.json").read_text())
    assert new["feature_names"] == MODEL["feature_names"]
    for key in ("means", "scales", "coefficients"):
        assert new[key] == pytest.approx(MODEL[key], abs=1e-9)
    assert new["intercept"] == pytest.approx(MODEL["intercept"], abs=1e-9)
    assert new["auc"] == pytest.approx(MODEL["auc"], abs=1e-9)
    golden = json.loads((tmp_path / "training" / "golden.json").read_text())
    for a, b in zip(golden["cases"], GOLDEN["cases"], strict=True):
        assert a["features"] == b["features"]
        assert a["probability"] == pytest.approx(b["probability"], abs=1e-9)


def test_the_training_script_is_not_a_runtime_dependency():
    assert "sklearn" not in (APP_DIR / "app.py").read_text()
    assert Path(APP_DIR / "training" / "train.py").exists()
