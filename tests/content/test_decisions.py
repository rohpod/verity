import copy
import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from content_samples import at_scale, good_files, good_org, write_tree
from verity_core.content.lint import lint
from verity_core.content.loader import ContentError, load_content
from verity_core.content.seed import seed
from verity_core.graph.integrity import check_integrity
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import (
    AppliesCondition,
    EdgeType,
    EvidenceKind,
    Role,
    Source,
)

REAL = Path(__file__).parents[2] / "content"
STATEMENT = "Simulated sign-off by a fictional person. The control was checked."


def decision(**fields) -> dict:
    base = {
        "id": "d1",
        "kind": "verification",
        "decided_on": date(2026, 11, 5),
        "by": "person:l-ivanova",
        "valid_until": date(2027, 11, 5),
        "simulated": True,
        "statement": STATEMENT,
        "control": "VC-014",
        "scope": "sys:faq-bot",
        "status": "implemented",
    }
    return base | fields


def tree(tmp_path, *decisions, document=True) -> Path:
    """A content tree under `tmp_path/content`, so `evidence/` sits beside it."""
    files = copy.deepcopy(good_files())
    at_scale(files)
    files["org/kestrel.yaml"] = good_org()
    for d in decisions:
        files[f"decisions/{d['id']}.yaml"] = d
    if document:
        (tmp_path / "evidence").mkdir(exist_ok=True)
        (tmp_path / "evidence" / "dpa.md").write_text("A fictional agreement.")
    return write_tree(tmp_path / "content", files)


def load(tmp_path, *decisions, **kwargs):
    return load_content(tree(tmp_path, *decisions, **kwargs))


def codes(content) -> set[str]:
    return {i.code for i in lint(content)}


def test_a_verification_becomes_attestation_evidence_about_its_scope(tmp_path):
    content = load(tmp_path, decision())
    (ev,) = content.decisions
    assert ev.kind is EvidenceKind.ATTESTATION
    assert ev.subject == "sys:faq-bot"
    assert ev.collector == "person:l-ivanova"
    assert ev.source is Source.SIMULATED
    assert ev.collected_at == datetime(2026, 11, 5, tzinfo=UTC)
    assert ev.content_ref is None
    assert ev.content["decision_kind"] == "verification"
    assert ev.content["control"] == "ctl:VC-014"
    assert ev.content["scope"] == "sys:faq-bot"
    assert ev.content["status"] == "implemented"
    about = [e for e in content.edges if e.type is EdgeType.ABOUT]
    assert [(e.src, e.dst) for e in about] == [(ev.id, "sys:faq-bot")]


def test_a_decision_is_valid_through_the_whole_of_its_last_day(tmp_path):
    (ev,) = load(tmp_path, decision(valid_until=date(2026, 11, 6))).decisions
    assert ev.valid_until > datetime(2026, 11, 6, 23, 59, tzinfo=UTC)
    assert ev.valid_until < datetime(2026, 11, 7, tzinfo=UTC)


def test_the_decision_file_is_recorded_by_path_and_hash(tmp_path):
    root = tree(tmp_path, decision())
    (ev,) = load_content(root).decisions
    file = root / "decisions" / "d1.yaml"
    assert ev.content["decision_file"] == "content/decisions/d1.yaml"
    assert ev.content["file_sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()


def test_editing_a_decision_creates_new_evidence(tmp_path):
    (before,) = load(tmp_path, decision()).decisions
    (after,) = load(tmp_path, decision(statement=STATEMENT + " Again.")).decisions
    assert before.id != after.id


def test_a_real_sign_off_is_declared_not_simulated(tmp_path):
    (ev,) = load(tmp_path, decision(simulated=False, statement="Checked on site.")).decisions
    assert ev.source is Source.DECLARED


def test_an_attestation_is_attestation_evidence(tmp_path):
    d = decision(kind="attestation", status="partially_implemented")
    (ev,) = load(tmp_path, d).decisions
    assert ev.kind is EvidenceKind.ATTESTATION
    assert ev.content["decision_kind"] == "attestation"


def test_a_document_is_document_ref_evidence(tmp_path):
    d = decision(kind="document", path="evidence/dpa.md")
    d.pop("status")
    (ev,) = load(tmp_path, d).decisions
    assert ev.kind is EvidenceKind.DOCUMENT_REF
    assert ev.content["path"] == "evidence/dpa.md"


@pytest.mark.parametrize("path", ["notes/dpa.md", "../dpa.md", "/etc/passwd", "evidence/../x.md"])
def test_a_document_must_sit_under_evidence(tmp_path, path):
    d = decision(kind="document", path=path)
    d.pop("status")
    with pytest.raises(ContentError, match="evidence"):
        load(tmp_path, d)


def test_a_missing_document_is_an_error(tmp_path):
    d = decision(kind="document", path="evidence/missing.md")
    d.pop("status")
    with pytest.raises(ContentError, match="does not exist"):
        load(tmp_path, d)


def test_a_risk_tier_is_about_its_system(tmp_path):
    d = {
        "id": "t1",
        "kind": "risk_tier",
        "decided_on": date(2026, 11, 5),
        "by": "person:l-ivanova",
        "valid_until": date(2027, 11, 5),
        "simulated": True,
        "statement": STATEMENT,
        "system": "sys:faq-bot",
        "tier": "high_risk",
        "basis": "annex_iii",
    }
    content = load(tmp_path, d)
    (ev,) = content.decisions
    assert ev.subject == "sys:faq-bot"
    assert ev.content["tier"] == "high_risk"
    assert ev.content["basis"] == "annex_iii"
    assert "control" not in ev.content
    assert codes(content) == set()


def risk_tier(**fields) -> dict:
    base = {
        "id": "t1",
        "kind": "risk_tier",
        "decided_on": date(2026, 11, 5),
        "by": "person:l-ivanova",
        "valid_until": date(2027, 11, 5),
        "statement": STATEMENT,
        "system": "sys:faq-bot",
        "tier": "not_high_risk",
        "basis": "art6_3",
        "condition": "a",
        "profiling": False,
    }
    return base | fields


def test_art_6_3_with_a_condition_and_no_profiling_is_accepted(tmp_path):
    (ev,) = load(tmp_path, risk_tier()).decisions
    assert ev.content["condition"] == "a"
    assert ev.content["profiling"] is False


def test_art_6_3_refuses_profiling(tmp_path):
    with pytest.raises(ContentError, match="profiling"):
        load(tmp_path, risk_tier(profiling=True))


@pytest.mark.parametrize("missing", ["condition", "profiling"])
def test_art_6_3_needs_a_condition_and_a_profiling_answer(tmp_path, missing):
    d = risk_tier()
    d.pop(missing)
    with pytest.raises(ContentError, match="art6_3"):
        load(tmp_path, d)


def test_a_condition_belongs_to_art_6_3_only(tmp_path):
    with pytest.raises(ContentError, match="art6_3"):
        load(tmp_path, risk_tier(basis="annex_iii", tier="high_risk"))


def test_a_condition_must_be_a_to_d(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, risk_tier(condition="e"))


def test_a_decision_must_expire_after_it_is_made(tmp_path):
    with pytest.raises(ContentError, match="valid_until"):
        load(tmp_path, decision(valid_until=date(2026, 11, 5)))


@pytest.mark.parametrize("status", ["not_assessed", "not_applicable", "done"])
def test_a_person_decides_only_implemented_partial_or_not(tmp_path, status):
    with pytest.raises(ContentError):
        load(tmp_path, decision(status=status))


def test_an_unknown_field_is_an_error(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, decision(email="x"))


def test_an_unknown_kind_is_an_error(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, decision(kind="approval"))


def test_a_scope_must_be_an_organisation_system_or_provider(tmp_path):
    with pytest.raises(ContentError, match="not an organisation"):
        load(tmp_path, decision(scope="person:l-ivanova"))


def test_two_files_cannot_share_a_decision_id(tmp_path):
    root = tree(tmp_path, decision())
    (root / "decisions" / "copy.yaml").write_text(
        yaml.safe_dump(decision(), sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(ContentError, match="also in"):
        load_content(root)


def test_a_clean_decision_passes_lint(tmp_path):
    assert codes(load(tmp_path, decision())) == set()


def test_lint_flags_an_unknown_person(tmp_path):
    content = load(tmp_path, decision(by="person:nobody"))
    assert "decision_unknown_person" in codes(content)


def test_lint_flags_an_unknown_scope(tmp_path):
    assert "decision_unknown_scope" in codes(load(tmp_path, decision(scope="sys:nowhere")))


def test_lint_flags_an_unknown_control(tmp_path):
    assert "decision_unknown_control" in codes(load(tmp_path, decision(control="VC-099")))


def test_lint_flags_a_scope_of_the_wrong_level(tmp_path):
    # VC-001 is assessed for the organisation, not for a system.
    content = load(tmp_path, decision(control="VC-001", scope="sys:faq-bot"))
    assert "decision_scope_mismatch" in codes(content)


def test_lint_accepts_a_scope_of_the_right_level(tmp_path):
    assert codes(load(tmp_path, decision(control="VC-001", scope="org:kestrel"))) == set()


def test_lint_flags_a_simulated_statement_that_does_not_say_so(tmp_path):
    content = load(tmp_path, decision(statement="Checked and found implemented."))
    assert "simulated_not_labelled" in codes(content)


def test_seeding_writes_the_decisions_and_stays_sound(repo, clock, tmp_path):
    content = load(tmp_path, decision())
    seed(repo, content, clock)
    assert check_integrity(repo.load_graph()) == []
    (ev,) = content.decisions
    assert repo.get_node(ev.id) is not None


def test_seeding_decisions_twice_changes_nothing(repo, clock, tmp_path):
    content = load(tmp_path, decision())
    seed(repo, content, clock)
    clock.now += timedelta(minutes=5)
    assert seed(repo, content, clock).written == 0


def test_a_conditional_edge_keeps_the_identity_of_an_unconditional_one():
    def edge(**fields):
        return AppliesToEdge(
            src="req:euaia:art9",
            dst="sys:talent-screening",
            role=Role.PROVIDER,
            rule_id="eu-high-risk-provider",
            reason="Annex III employment system.",
            tenant="kestrel",
            source=Source.DERIVED,
            **fields,
        )

    plain = edge()
    conditional = edge(condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE)
    assert plain.key == conditional.key
    assert plain.condition is None


def test_a_system_can_record_its_last_significant_change(tmp_path):
    org = good_org()
    org["systems"][0]["significant_change_on"] = date(2028, 1, 10)
    files = copy.deepcopy(good_files())
    files["org/kestrel.yaml"] = org
    content = load_content(write_tree(tmp_path, files))
    system = next(n for n in content.estate if n.id == "sys:faq-bot")
    assert system.significant_change_on == date(2028, 1, 10)
    unchanged = next(n for n in content.estate if n.id == "sys:translator")
    assert unchanged.significant_change_on is None


# --- the demo decisions under content/decisions/ --------------------------------------------


@pytest.fixture(scope="module")
def real():
    return load_content(REAL)


def decided(real, decision_id):
    return next(e for e in real.decisions if e.content["decision_id"] == decision_id)


def test_the_real_decisions_pass_lint(real):
    assert lint(real) == []


def test_every_demo_decision_is_simulated_and_by_the_head_of_legal(real):
    assert len(real.decisions) == 5
    assert {e.source for e in real.decisions} == {Source.SIMULATED}
    assert {e.collector for e in real.decisions} == {"person:l-ivanova"}


def test_the_demo_risk_tiers(real):
    talent = decided(real, "risk-tier-talent-screening")
    coach = decided(real, "risk-tier-onboarding-coach")
    assert (talent.subject, talent.content["tier"], talent.content["basis"]) == (
        "sys:talent-screening",
        "high_risk",
        "annex_iii",
    )
    assert (coach.subject, coach.content["tier"], coach.content["basis"]) == (
        "sys:onboarding-coach",
        "not_high_risk",
        "not_listed",
    )


def test_the_demo_control_decisions(real):
    verified = decided(real, "verification-vc-032-talent-screening")
    attested = decided(real, "attestation-vc-001-kestrel")
    document = decided(real, "document-vc-050-mock-bedrock")
    assert (verified.content["control"], verified.subject, verified.content["status"]) == (
        "ctl:VC-032",
        "sys:talent-screening",
        "implemented",
    )
    assert (attested.content["control"], attested.subject, attested.content["status"]) == (
        "ctl:VC-001",
        "org:kestrel",
        "partially_implemented",
    )
    assert (document.content["control"], document.subject) == ("ctl:VC-050", "prov:mock-bedrock")
    assert document.kind is EvidenceKind.DOCUMENT_REF


def test_the_gaps_the_demo_needs_stay_open(real):
    subjects = {e.subject for e in real.decisions}
    assert "sys:candidate-cv-parser" not in subjects  # left undecided on purpose
    assert "prov:mock-openai" not in subjects  # no DPA on purpose


def test_the_demo_dpa_says_it_is_fictional():
    assert "fictional" in (REAL.parent / "evidence" / "dpa-mock-bedrock.md").read_text().lower()
