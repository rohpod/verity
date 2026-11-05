import copy
from pathlib import Path

import pytest
from content_samples import at_scale, good_files, write_tree
from verity_core.content.lint import lint
from verity_core.content.loader import ContentError, load_content

CONTENT = load_content(Path(__file__).parents[2] / "content")


def rule(**fields) -> dict:
    base = {
        "id": "r1",
        "requirements": ["req:euaia:art4"],
        "target": "organisation",
        "role": "held",
        "date": "euaia-example",
    }
    return base | fields


def load(tmp_path, *rules):
    files = copy.deepcopy(good_files())
    at_scale(files)
    files["rules/applicability.yaml"] = {
        "annex_iii_domains": {"employment": "Annex III, point 4"},
        "rules": list(rules),
    }
    return load_content(write_tree(tmp_path, files))


def codes(content) -> set[str]:
    return {i.code for i in lint(content)}


def test_a_good_rule_loads_and_lints_clean(tmp_path):
    assert codes(load(tmp_path, rule())) == set()


def test_the_real_rules_lint_clean_and_cover_the_planned_rule_ids():
    assert [r.id for r in CONTENT.rules.rules] == [
        "eu-literacy",
        "eu-disclosure",
        "eu-marking",
        "eu-high-risk-provider",
        "eu-high-risk-deployer",
        "adopted-frameworks",
    ]
    assert CONTENT.rules.annex_iii_domains == {"employment": "Annex III, point 4"}
    assert lint(CONTENT) == []


def test_lint_flags_an_unknown_requirement(tmp_path):
    content = load(tmp_path, rule(requirements=["req:euaia:art999"]))
    assert "rule_unknown_requirement" in codes(content)


def test_lint_flags_an_unknown_framework(tmp_path):
    content = load(tmp_path, rule(requirements=[], leaves_of=["nosuch"]))
    assert "rule_unknown_framework" in codes(content)


@pytest.mark.parametrize("field", ["date", "legacy_date"])
def test_lint_flags_an_unknown_date(tmp_path, field):
    content = load(tmp_path, rule(**{"date": "euaia-example", field: "euaia-nope"}))
    assert "rule_unknown_date" in codes(content)


def test_a_rule_needs_requirements_or_leaves_but_not_both(tmp_path):
    with pytest.raises(ContentError, match="requirements or leaves_of"):
        load(tmp_path, rule(leaves_of=["euaia"]))
    with pytest.raises(ContentError, match="requirements or leaves_of"):
        load(tmp_path, rule(requirements=[]))


def test_held_is_for_the_organisation(tmp_path):
    with pytest.raises(ContentError, match="held"):
        load(tmp_path, rule(target="system"))


def test_facts_are_about_a_system(tmp_path):
    with pytest.raises(ContentError, match="system"):
        load(tmp_path, rule(reads=["interacts_with_people"]))


def test_art_111_2_needs_a_date_and_a_high_risk_rule(tmp_path):
    with pytest.raises(ContentError, match="high-risk"):
        load(tmp_path, rule(target="system", role="provider", art_111_2=True))
    with pytest.raises(ContentError, match="need a date"):
        load(tmp_path, rule(date=None, legacy_date="euaia-example"))


def test_a_rule_cannot_name_an_unknown_fact(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, rule(target="system", role="provider", reads=["is_nice"]))


def test_a_rule_id_cannot_repeat(tmp_path):
    with pytest.raises(ContentError, match="twice"):
        load(tmp_path, rule(), rule())


def test_an_unknown_key_is_an_error(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, rule(salary=1))
