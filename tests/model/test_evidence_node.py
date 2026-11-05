from datetime import datetime, timedelta

import pytest
from factories import T0, evidence
from pydantic import ValidationError
from verity_core.model import ids
from verity_core.model.enums import EvidenceKind
from verity_core.model.evidence import INLINE_EVIDENCE_MAX_BYTES, Evidence, content_sha256
from verity_core.model.nodes import parse_node


def test_build_computes_id_and_sha256():
    e = evidence()
    assert e.sha256 == content_sha256({"runtime": "python3.12"})
    assert e.id.startswith("ev:")


def test_recollecting_identical_content_creates_a_new_node_with_the_same_hash():
    first = evidence()
    later = evidence(collected_at=T0 + timedelta(days=1), valid_until=T0 + timedelta(days=40))
    assert later.id != first.id
    assert later.sha256 == first.sha256


def test_evidence_is_immutable():
    with pytest.raises(ValidationError):
        evidence().sha256 = "0" * 64


def test_survives_a_json_round_trip():
    e = evidence()
    assert parse_node(e.model_dump(mode="json")) == e


def fields(e: Evidence) -> dict:
    return e.model_dump()


def test_a_mismatched_id_is_rejected():
    with pytest.raises(ValidationError, match="does not match its hashed fields"):
        Evidence(**fields(evidence()) | {"id": "ev:" + "0" * 32})


def test_a_mismatched_inline_sha256_is_rejected():
    with pytest.raises(ValidationError, match="does not match the inline content"):
        Evidence(**fields(evidence()) | {"sha256": "0" * 64})


def test_tampered_content_is_rejected():
    with pytest.raises(ValidationError):
        Evidence(**fields(evidence()) | {"content": {"runtime": "python3.13"}})


def test_content_and_content_ref_are_mutually_exclusive_and_required():
    with pytest.raises(ValueError):
        evidence(content=None)
    with pytest.raises(ValidationError, match="exactly one"):
        Evidence(**fields(evidence()) | {"content_ref": "evidence/x.json"})


def test_content_ref_evidence_uses_the_file_hash():
    e = evidence(
        content=None,
        content_ref="evidence/dpa-openai.pdf",
        file_sha256="c" * 64,
        kind=EvidenceKind.DOCUMENT_REF,
        collector=ids.person_id("a-singh"),
    )
    assert e.sha256 == "c" * 64 and e.content is None


@pytest.mark.parametrize("ref", ["/etc/passwd", "evidence/../secrets.json", "other/x.json", ""])
def test_content_ref_must_stay_under_evidence(ref):
    with pytest.raises(ValidationError, match="under evidence/"):
        evidence(content=None, content_ref=ref, file_sha256="c" * 64)


def test_inline_content_over_the_cap_is_rejected():
    big = {"blob": "x" * INLINE_EVIDENCE_MAX_BYTES}
    with pytest.raises(ValidationError, match="over"):
        evidence(content=big)


@pytest.mark.parametrize("collector", ["crawler@", "robot", "person:", "sys:x", "cli"])
def test_bad_collectors_are_rejected(collector):
    with pytest.raises(ValidationError):
        evidence(collector=collector)


@pytest.mark.parametrize("collector", ["crawler@0.1.0", "cli@0.2.0", "person:a-singh"])
def test_good_collectors_are_accepted(collector):
    assert evidence(collector=collector).collector == collector


def test_valid_until_must_be_after_collected_at():
    with pytest.raises(ValidationError, match="valid_until"):
        evidence(valid_until=T0)


def test_subject_must_be_a_valid_id():
    with pytest.raises(ValidationError):
        evidence(subject="not an id")


def test_naive_collected_at_is_rejected():
    with pytest.raises(ValidationError):
        Evidence(**fields(evidence()) | {"collected_at": datetime(2026, 11, 5)})
