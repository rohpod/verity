from datetime import UTC, datetime
from uuid import uuid4

from discovery_support import SIGNALS, allow, make_role
from verity_core.discovery.boundary import TrailEvent
from verity_core.discovery.usage import (
    check_vc060,
    granted_ai_actions,
    trail_action,
    trail_shows_ai,
    usage_shows_ai,
)
from verity_core.model.enums import Source
from verity_core.model.usage import UsageRecord

AI = SIGNALS.ai_actions
SOURCES = SIGNALS.trail_event_sources
WHEN = datetime(2026, 11, 1, tzinfo=UTC)


def event(role, name="Converse", source="bedrock.amazonaws.com") -> TrailEvent:
    return TrailEvent(source, name, WHEN, role)


def test_a_grant_overlaps_an_ai_action_in_either_direction():
    statements = [
        allow("bedrock:Converse"),
        allow("bedrock:*"),
        allow("*"),
        allow("BEDROCK:invokemodel"),
        allow("sagemaker:InvokeEndpoint"),
        allow("s3:GetObject"),
        allow("bedrock:ListFoundationModels"),
    ]
    assert granted_ai_actions(AI, statements) == (
        "*",
        "BEDROCK:invokemodel",
        "bedrock:*",
        "bedrock:Converse",
        "sagemaker:InvokeEndpoint",
    )


def test_deny_and_negated_statements_do_not_grant():
    statements = [allow("bedrock:Converse", effect="Deny"), allow("bedrock:Converse", negated=True)]
    assert granted_ai_actions(AI, statements) == ()


def test_an_unexercised_grant_fails():
    result = check_vc060(AI, [make_role("r", allow("bedrock:Converse"))], [], SOURCES)
    assert (result.outcome, result.granted, result.unused) == (
        "fail",
        ("bedrock:Converse",),
        ("bedrock:Converse",),
    )


def test_a_matching_trail_event_for_the_same_role_passes():
    roles = [make_role("r", allow("bedrock:Converse"))]
    result = check_vc060(AI, roles, [event("r")], SOURCES)
    assert (result.outcome, result.granted, result.unused) == ("pass", ("bedrock:Converse",), ())


def test_an_event_by_another_role_or_another_action_does_not_count():
    roles = [make_role("r", allow("bedrock:Converse"))]
    assert check_vc060(AI, roles, [event("other")], SOURCES).outcome == "fail"
    assert check_vc060(AI, roles, [event("r", name="InvokeModel")], SOURCES).outcome == "fail"
    assert (
        check_vc060(AI, roles, [event("r", source="s3.amazonaws.com")], SOURCES).outcome == "fail"
    )


def test_a_wildcard_grant_is_used_by_any_event_it_covers():
    roles = [make_role("r", allow("bedrock:*"))]
    assert check_vc060(AI, roles, [event("r", name="InvokeModel")], SOURCES).outcome == "pass"


def test_no_ai_grant_passes_with_nothing_granted():
    result = check_vc060(AI, [make_role("r", allow("dynamodb:GetItem"))], [], SOURCES)
    assert (result.outcome, result.granted, result.unused, result.unparsed) == (
        "pass",
        (),
        (),
        False,
    )


def test_a_not_action_allow_is_ignored_and_reported_as_unparsed():
    role = make_role("r", allow("iam:*", negated=True))
    result = check_vc060(AI, [role], [], SOURCES)
    assert (result.outcome, result.granted, result.unparsed) == ("pass", (), True)


def test_several_roles_are_judged_each_by_its_own_events():
    roles = [make_role("a", allow("bedrock:Converse")), make_role("b", allow("bedrock:Converse"))]
    result = check_vc060(AI, roles, [event("a")], SOURCES)
    assert result.unused == ("bedrock:Converse",)  # role b never used it


def test_the_content_names_the_control_and_the_scope_the_assessor_matches_on():
    result = check_vc060(AI, [make_role("r", allow("bedrock:Converse"))], [], SOURCES)
    assert result.content("sys:support-assistant") == {
        "control": "ctl:VC-060",
        "scope": "sys:support-assistant",
        "outcome": "fail",
        "granted": ["bedrock:Converse"],
        "unused": ["bedrock:Converse"],
        "unparsed": False,
    }


def test_trail_actions_and_signals():
    assert trail_action(event("r", name="InvokeModel")) == "bedrock:InvokeModel"
    assert trail_shows_ai("r", [event("r")], SOURCES)
    assert not trail_shows_ai("other", [event("r")], SOURCES)
    assert not trail_shows_ai(None, [event(None)], SOURCES)
    assert not trail_shows_ai("r", [event("r", source="s3.amazonaws.com")], SOURCES)


def test_usage_records_are_a_signal_but_never_part_of_the_vc060_check():
    record = UsageRecord(
        tenant="kestrel",
        usage_id=uuid4(),
        system_id="sys:a",
        provider_id="prov:p",
        model_id="model:m",
        timestamp=WHEN,
        token_estimate=1,
        source=Source.SIMULATED,
    )
    assert usage_shows_ai([record]) and not usage_shows_ai([])
    roles = [make_role("r", allow("bedrock:Converse"))]
    assert check_vc060(AI, roles, [], SOURCES).outcome == "fail"
