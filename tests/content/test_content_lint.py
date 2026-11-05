import pytest
from content_samples import broken, good_files, mapping, requirement, write_tree
from verity_core.content.lint import LintLimits, lint
from verity_core.content.loader import load_content

SMALL = LintLimits(min_controls=1, max_controls=10)


def issues_for(tmp_path, files, limits=SMALL):
    return lint(load_content(write_tree(tmp_path, files)), limits)


def codes(issues) -> set[str]:
    return {i.code for i in issues}


def test_the_good_sample_passes(tmp_path):
    assert issues_for(tmp_path, good_files()) == []


def test_empty_content_fails_the_control_count(tmp_path):
    (issue,) = lint(load_content(tmp_path))
    assert issue.code == "control_count"
    assert "0 controls; expected 25 to 35" in issue.message


def _set(files, framework, slug, **fields):
    requirement(files, framework, slug).update(fields)


def _long_iso(files):
    _set(files, "iso42001", "A.6", summary="word " * 50)


def _drop_mapping(files, framework, slug):
    files[f"mappings/{framework}.yaml"]["mappings"].remove(mapping(files, framework, slug))


CASES = {
    "placeholder_source": lambda f: f["frameworks/euaia.yaml"]["framework"].update(
        source_url="https://example.invalid/test-fixture"
    ),
    "source_url_not_https": lambda f: _set(
        f, "euaia", "art4", source_url="http://eur-lex.example.org/eu-ai-act"
    ),
    "eu_source_version": lambda f: _set(f, "euaia", "art4", source_version="2024/1689"),
    "date_in_summary": lambda f: _set(
        f, "euaia", "art50-1", summary="People are told from 2 August 2026 that it is an AI."
    ),
    "iso_summary_too_long": _long_iso,
    "iso_quoted_text": lambda f: _set(f, "iso42001", "A.6", summary='The "lifecycle" controls.'),
    "iso_normative_wording": lambda f: _set(
        f, "iso42001", "A.6", summary="The organisation shall control the lifecycle."
    ),
    "iso_not_public_listing": lambda f: _set(f, "iso42001", "A.6", verified_against="primary_text"),
    "iso_listing_sources": lambda f: _set(
        f,
        "iso42001",
        "A.6",
        listing_sources=["https://one.example.org/a", "https://one.example.org/b"],
    ),
    "syntactic_rationale": lambda f: mapping(f, "euaia", "art4").update(rationale_type="syntactic"),
    "rationale_too_short": lambda f: mapping(f, "euaia", "art4").update(rationale="Similar."),
    "equal_strength_low": lambda f: mapping(f, "euaia", "art4").update(strm="equal", strength=8),
    "sufficiency_must_be_full": lambda f: mapping(f, "euaia", "art4").update(sufficiency="partial"),
    "full_needs_cover": lambda f: mapping(f, "euaia", "art4").update(strm="intersects_with"),
    "unread_mapping_overclaims": lambda f: mapping(f, "iso42001", "A.8.2").update(strength=6),
    "unmapped_requirement": lambda f: _drop_mapping(f, "euaia", "art50-1"),
    "unmapped_control": lambda f: f["controls.yaml"]["controls"].append(
        {
            "code": "VC-099",
            "title": "Spare",
            "summary": "Nothing maps to this one.",
            "kind": "organisational",
            "scope_level": "system",
        }
    ),
    "email_like": lambda f: f["controls.yaml"]["controls"][0].update(
        summary="Ask someone@example.org for the training."
    ),
    "account_id_like": lambda f: f["controls.yaml"]["controls"][0].update(
        summary="Account 123456789012 is in scope."
    ),
}


@pytest.mark.parametrize("code", CASES)
def test_each_rule_fires_on_its_own_sample(tmp_path, code):
    found = codes(issues_for(tmp_path, broken(CASES[code])))
    assert code in found


@pytest.mark.parametrize("code", CASES)
def test_a_sample_breaks_only_its_own_rule_or_a_consequence(tmp_path, code):
    # Guards the samples: one change should not light up unrelated rules.
    allowed = {
        "equal_strength_low": set(),
        "unmapped_requirement": set(),
        "full_needs_cover": set(),
        "unmapped_control": set(),
        "iso_normative_wording": set(),
    }
    found = codes(issues_for(tmp_path, broken(CASES[code])))
    assert found - {code} <= allowed.get(code, set()), found


def test_a_negative_mapping_counts_as_reviewed(tmp_path):
    assert issues_for(tmp_path, good_files()) == []  # art25 has only no_relationship


def test_a_control_mapped_only_negatively_is_unmapped(tmp_path):
    def mutate(files):
        _drop_mapping(files, "iso42001", "A.6.2.4")  # VC-014 is left with art25's negative one

    found = issues_for(tmp_path, broken(mutate))
    assert [(i.code, i.subject) for i in found if i.code == "unmapped_control"] == [
        ("unmapped_control", "ctl:VC-014")
    ]


def test_a_partial_overlap_is_full_with_a_second_full_mapping(tmp_path):
    def mutate(files):
        mapping(files, "euaia", "art4").update(strm="intersects_with")
        files["mappings/euaia.yaml"]["mappings"].append(
            {
                **mapping(files, "euaia", "art4"),
                "control": "VC-014",
                "strm": "subset_of",
                "strength": 6,
            }
        )

    assert "full_needs_cover" not in codes(issues_for(tmp_path, broken(mutate)))


@pytest.mark.parametrize(
    "change",
    [
        {"strm": "subset_of", "strength": 5, "sufficiency": "full"},
        {"strm": "superset_of", "strength": 5, "sufficiency": "partial"},
        {"strm": "equal", "strength": 9, "sufficiency": "full"},
        {"strm": "intersects_with", "strength": 5, "sufficiency": "full"},
        {"strm": "no_relationship", "strength": None, "sufficiency": None},
    ],
)
def test_a_requirement_nobody_read_cannot_claim_more_than_an_overlap(tmp_path, change):
    files = broken(lambda f: mapping(f, "iso42001", "A.8.2").update(change))
    assert "unread_mapping_overclaims" in codes(issues_for(tmp_path, files))


def test_the_same_claim_is_fine_on_a_requirement_that_was_read(tmp_path):
    files = broken(lambda f: mapping(f, "euaia", "art4").update(strength=9, strm="equal"))
    assert "unread_mapping_overclaims" not in codes(issues_for(tmp_path, files))


def test_the_default_limits_expect_25_to_35_controls(tmp_path):
    (issue,) = [
        i for i in issues_for(tmp_path, good_files(), LintLimits()) if i.code == "control_count"
    ]
    assert "4 controls; expected 25 to 35" in issue.message


def test_issues_are_ordered_by_subject_then_code(tmp_path):
    issues = issues_for(
        tmp_path, broken(lambda f: [CASES[c](f) for c in ("email_like", "unmapped_control")])
    )
    assert issues == sorted(issues, key=lambda i: (i.subject, i.code))
