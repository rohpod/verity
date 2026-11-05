"""M4's validation criteria, run against the real files under `content/`."""

from collections import Counter
from dataclasses import fields
from datetime import timedelta
from pathlib import Path

import pytest
from verity_core.content.lint import lint
from verity_core.content.loader import load_content
from verity_core.content.seed import seed
from verity_core.graph.integrity import check_integrity
from verity_core.graph.traversals import DerivedLink, crosswalk
from verity_core.model.edges import MapsToEdge
from verity_core.model.enums import (
    EdgeType,
    NodeType,
    Source,
    StrmType,
    Sufficiency,
    VerifiedAgainst,
)
from verity_core.model.nodes import Policy, Risk

REAL = Path(__file__).parents[2] / "content"
ISO = ("iso42001", "iso27001")


@pytest.fixture(scope="module")
def content():
    return load_content(REAL)


def mappings(content):
    return [e for e in content.edges if isinstance(e, MapsToEdge)]


def maps(content, requirement, control):
    return any(m.src == requirement and m.dst == control for m in mappings(content))


def framework_of(requirement) -> str:
    return requirement.id.split(":")[1]


def leaves(content):
    parents = {e.dst for e in content.edges if e.type is EdgeType.PART_OF}
    return [r for r in content.requirements if r.id not in parents]


def test_the_content_passes_the_linter(content):
    assert lint(content) == []


def test_there_are_four_instruments_with_about_ten_requirements_each(content):
    per_framework = Counter(framework_of(r) for r in leaves(content))
    assert set(per_framework) == {"euaia", "nistrmf", "iso42001", "iso27001"}
    assert all(8 <= count <= 13 for count in per_framework.values()), per_framework


def test_the_library_is_seeded_and_kept_apart_from_the_estate(content):
    records = [*content.frameworks, *content.requirements, *content.controls, *mappings(content)]
    assert {r.source for r in records} == {Source.SEEDED}


def test_every_iso_entry_says_it_rests_on_a_public_listing(content):
    iso = [r for r in content.requirements if framework_of(r) in ISO]
    assert iso
    assert {r.verified_against for r in iso} == {VerifiedAgainst.PUBLIC_LISTING}
    assert content.copyrighted == set(ISO)


def test_nothing_else_rests_on_a_public_listing(content):
    others = [r for r in content.requirements if framework_of(r) not in ISO]
    assert {r.verified_against for r in others} == {VerifiedAgainst.PRIMARY_TEXT}


def test_no_iso_requirement_can_show_as_satisfied(content):
    # Satisfied needs a non-empty full set (D2), and nobody has read the ISO text (ADR 0018).
    iso_mappings = [m for m in mappings(content) if m.src.split(":")[1] in ISO]
    assert iso_mappings
    assert {m.sufficiency for m in iso_mappings} == {Sufficiency.PARTIAL}


def test_no_mapping_claims_equal(content):
    # The hub is in our own words, so no control here is claimed to be the same as a requirement.
    assert StrmType.EQUAL not in {m.strm for m in mappings(content)}


@pytest.mark.parametrize(
    ("story", "requirement", "control"),
    [
        ("Support: disclosure", "req:euaia:art50-1", "ctl:VC-040"),
        ("Support: synthetic text", "req:euaia:art50-2", "ctl:VC-041"),
        ("Support: logging", "req:euaia:art12", "ctl:VC-030"),
        ("Support: unused AI permission", "req:iso27001:A.8.2", "ctl:VC-060"),
        ("Talent: bias", "req:euaia:art10-2fg", "ctl:VC-014"),
        ("Talent: bias", "req:nistrmf:MEASURE-2.11", "ctl:VC-014"),
        ("Talent: data governance", "req:euaia:art10-2ah", "ctl:VC-012"),
        ("Talent: human oversight", "req:euaia:art14", "ctl:VC-032"),
        ("Talent: technical documentation", "req:euaia:art11", "ctl:VC-020"),
        ("Talent: informing workers", "req:euaia:art26-7", "ctl:VC-034"),
        ("Contract: DPA", "req:iso42001:A.10.3", "ctl:VC-050"),
        ("Contract: vendor risk", "req:nistrmf:MANAGE-3.1", "ctl:VC-051"),
        ("Contract: transfer", "req:iso27001:A.5.34", "ctl:VC-053"),
        ("Organisation: literacy", "req:euaia:art4", "ctl:VC-001"),
    ],
)
def test_each_governance_story_has_a_mapped_requirement(content, story, requirement, control):
    assert maps(content, requirement, control), story


def test_a_derived_link_has_no_strm_type():
    assert "strm" not in {f.name for f in fields(DerivedLink)}


def test_similar_sounding_is_not_treated_as_related(content):
    (negative,) = (m for m in mappings(content) if m.strm is StrmType.NO_RELATIONSHIP)
    assert (negative.src, negative.dst) == ("req:euaia:art13", "ctl:VC-040")


def test_every_risk_has_a_mitigation_and_every_policy_a_control(content):
    mitigated = {e.src for e in content.edges if e.type is EdgeType.MITIGATED_BY}
    implementing = {e.src for e in content.edges if e.type is EdgeType.IMPLEMENTS}
    assert {n.id for n in content.estate if isinstance(n, Risk)} == mitigated
    assert {n.id for n in content.estate if isinstance(n, Policy)} == implementing


def test_every_date_cites_the_official_journal_and_is_verified(content):
    assert len(content.dates) >= 6
    assert all(d.source_url.startswith("https://eur-lex.europa.eu/eli/") for d in content.dates)


def test_both_high_risk_routes_have_a_date(content):
    ids = {d.id for d in content.dates}
    assert {"euaia-high-risk-annex-iii", "euaia-high-risk-annex-i"} <= ids
    assert "euaia-art50-2-legacy" in ids


def test_the_crosswalk_works_on_real_content_and_never_composes_no_relationship(
    repo, clock, content
):
    seed(repo, content, clock)
    graph = repo.load_graph()

    logging = crosswalk(graph, "req:euaia:art12", "fw:iso42001")
    assert [link.target_requirement_id for link in logging] == ["req:iso42001:A.6.2.8"]
    assert logging[0].via_control_id == "ctl:VC-030"
    assert logging[0].strength == 5  # the weaker spoke (D6)

    # Art. 13 reaches Art. 50(1)'s control only through its no_relationship mapping.
    assert "req:euaia:art50-1" not in {
        link.target_requirement_id for link in crosswalk(graph, "req:euaia:art13", "fw:euaia")
    }
    for requirement in content.requirements:
        for framework in content.frameworks:
            for link in crosswalk(graph, requirement.id, framework.id):
                assert StrmType.NO_RELATIONSHIP not in (link.left.strm, link.right.strm)


def test_seeding_everything_twice_changes_nothing(repo, clock, content):
    first = seed(repo, content, clock)
    assert first.written == len(content.nodes()) + len(content.edges)
    assert check_integrity(repo.load_graph()) == []
    versions = {n.id: n.version for n in repo.nodes_by_type(NodeType.REQUIREMENT)}

    clock.now += timedelta(minutes=5)
    again = seed(repo, content, clock)

    assert again.written == 0
    assert {n.id: n.version for n in repo.nodes_by_type(NodeType.REQUIREMENT)} == versions
    assert all(len(repo.history(i)) == 1 for i in versions)
