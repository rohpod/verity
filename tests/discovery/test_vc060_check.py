from datetime import UTC, datetime
from uuid import uuid4

from discovery_support import SIGNALS, allow, make_role
from verity_core.discovery.boundary import TrailEvent
from verity_core.discovery.usage import (
    check_vc060,
    granted_ai_actions,
    trail_shows_ai,
    usage_shows_ai,
)
from verity_core.model.enums import Source
from verity_core.model.usage import UsageRecord

AI = SIGNALS.ai_actions
SOURCES = SIGNALS.trail_event_sources
WHEN = datetime(2026, 11, 1, tzinfo=UTC)
INVOKE, STREAM = "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"


def event(
    role, name="Converse", source="bedrock.amazonaws.com", kind="AwsApiCall", error=None
) -> TrailEvent:
    return TrailEvent(source, name, WHEN, role, kind, error)


def granted(*statements):
    return granted_ai_actions(AI, statements)


def test_a_call_that_invokes_no_model_does_not_show_ai_use():
    assert not trail_shows_ai("r", [event("r", name="ListFoundationModels")], SOURCES, AI)
    assert not trail_shows_ai("r", [event("r", name="ListGuardrails")], SOURCES, AI)
    assert not trail_shows_ai("r", [event("r", name="GetFoundationModel")], SOURCES, AI)


def test_a_pattern_grant_resolves_to_the_listed_actions_it_covers():
    assert granted(allow("bedrock:InvokeModel")) == (INVOKE,)
    assert granted(allow("BEDROCK:invokemodel")) == (INVOKE,)
    assert granted(allow("bedrock:*Model")) == (INVOKE,)
    assert granted(allow("bedrock:Invoke?odel")) == (INVOKE,)
    assert granted(allow("bedrock:InvokeModel*")) == (INVOKE, STREAM)
    assert len(granted(allow("*"))) == 8
    assert len(granted(allow("bedrock:*"))) == 5
    assert granted(allow("bedrock:Get*"), allow("s3:*"), allow("bedrock:Converse")) == ()


def test_a_not_action_statement_grants_everything_it_does_not_exclude():
    broad = allow(["iam:*", "organizations:*"], not_action=True)
    assert len(granted(broad)) == 8
    assert granted(allow(["bedrock:*", "sagemaker:*"], not_action=True)) == ()
    assert granted(allow(["bedrock:InvokeModel"], not_action=True))[0] == "bedrock:InvokeAgent"


def test_deny_never_grants_and_is_not_subtracted():
    assert granted(allow("bedrock:InvokeModel", effect="Deny")) == ()
    both = granted(allow("bedrock:InvokeModel"), allow("bedrock:InvokeModel", effect="Deny"))
    assert both == (INVOKE,)


def test_an_unexercised_grant_fails():
    result = check_vc060(AI, [make_role("r", allow(INVOKE))], [], SOURCES)
    assert (result.outcome, result.granted, result.unused) == ("fail", (INVOKE,), (INVOKE,))


def test_converse_proves_invoke_model_and_converse_stream_proves_the_stream_action():
    roles = [make_role("r", allow(INVOKE))]
    assert check_vc060(AI, roles, [event("r", "Converse")], SOURCES).outcome == "pass"
    assert check_vc060(AI, roles, [event("r", "InvokeModel")], SOURCES).outcome == "pass"
    assert check_vc060(AI, roles, [event("r", "ConverseStream")], SOURCES).outcome == "fail"
    roles = [make_role("r", allow(STREAM))]
    assert check_vc060(AI, roles, [event("r", "ConverseStream")], SOURCES).outcome == "pass"
    assert check_vc060(AI, roles, [event("r", "Converse")], SOURCES).outcome == "fail"


def test_an_event_by_another_role_service_or_a_service_event_does_not_count():
    roles = [make_role("r", allow(INVOKE))]
    for odd in (
        event("other"),
        event("r", source="s3.amazonaws.com"),
        event("r", kind="AwsServiceEvent"),
        event("r", name="ListFoundationModels"),
    ):
        assert check_vc060(AI, roles, [odd], SOURCES).outcome == "fail"


def test_a_wildcard_grant_fails_while_a_covered_action_is_unused():
    roles = [make_role("r", allow("bedrock:*"))]
    result = check_vc060(AI, roles, [event("r", "InvokeModel")], SOURCES)
    assert result.outcome == "fail" and STREAM in result.unused and INVOKE not in result.unused


def test_an_action_event_history_cannot_show_is_inconclusive_not_unused():
    roles = [make_role("r", allow("sagemaker:InvokeEndpoint"))]
    result = check_vc060(AI, roles, [], SOURCES)
    assert (result.outcome, result.unverifiable, result.unused) == (
        "inconclusive",
        ("sagemaker:InvokeEndpoint",),
        (),
    )
    both = [make_role("r", allow(["sagemaker:InvokeEndpoint", INVOKE]))]
    assert check_vc060(AI, both, [], SOURCES).outcome == "fail"


def test_a_role_the_crawler_cannot_see_makes_the_check_inconclusive():
    roles = [make_role("r", allow("dynamodb:GetItem"))]
    assert check_vc060(AI, roles, [], SOURCES).outcome == "pass"
    assert check_vc060(AI, roles, [], SOURCES, roles_unseen=1).outcome == "inconclusive"
    assert check_vc060(AI, [], [], SOURCES, roles_unseen=2).roles_unseen == 2


def test_an_unseen_role_does_not_hide_a_failure():
    roles = [make_role("r", allow(INVOKE))]
    assert check_vc060(AI, roles, [], SOURCES, roles_unseen=1).outcome == "fail"


def test_no_ai_grant_passes_with_nothing_granted():
    result = check_vc060(AI, [make_role("r", allow("dynamodb:GetItem"))], [], SOURCES)
    assert (result.outcome, result.granted, result.unused, result.unverifiable) == (
        "pass",
        (),
        (),
        (),
    )


def test_a_broad_not_action_role_fails():
    role = make_role("r", allow("iam:*", not_action=True))
    result = check_vc060(AI, [role], [], SOURCES)
    assert result.outcome == "fail" and len(result.granted) == 8


def test_several_roles_are_judged_each_by_its_own_events():
    roles = [make_role("a", allow(INVOKE)), make_role("b", allow(INVOKE))]
    result = check_vc060(AI, roles, [event("a")], SOURCES)
    assert (result.outcome, result.unused) == ("fail", (INVOKE,))  # role b never used it


def test_the_content_names_the_control_and_the_scope_the_assessor_matches_on():
    result = check_vc060(AI, [make_role("r", allow(INVOKE))], [], SOURCES)
    assert result.content("sys:support-assistant") == {
        "control": "ctl:VC-060",
        "scope": "sys:support-assistant",
        "outcome": "fail",
        "granted": [INVOKE],
        "unused": [INVOKE],
        "unverifiable": [],
        "roles_unseen": 0,
    }


def test_trail_signal():
    assert trail_shows_ai("r", [event("r")], SOURCES, AI)
    assert not trail_shows_ai("other", [event("r")], SOURCES, AI)
    assert not trail_shows_ai(None, [event(None)], SOURCES, AI)
    assert not trail_shows_ai("r", [event("r", source="s3.amazonaws.com")], SOURCES, AI)
    assert not trail_shows_ai("r", [event("r", kind="AwsServiceEvent")], SOURCES, AI)


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
    roles = [make_role("r", allow(INVOKE))]
    assert check_vc060(AI, roles, [], SOURCES).outcome == "fail"


def test_a_refused_call_does_not_count_as_use():
    role = make_role("r", allow("bedrock:InvokeModel"))
    refused = event("r", name="InvokeModel", error="AccessDenied")
    result = check_vc060(AI, [role], [refused], SOURCES)
    assert result.outcome == "fail"
    assert result.unused == (INVOKE,)
    assert not trail_shows_ai("r", [refused], SOURCES, AI)


def test_a_successful_call_still_proves_use_beside_a_failed_one():
    role = make_role("r", allow("bedrock:InvokeModel"))
    events = [event("r", name="InvokeModel", error="ThrottlingException"), event("r")]
    assert check_vc060(AI, [role], events, SOURCES).outcome == "pass"
    assert trail_shows_ai("r", events, SOURCES, AI)
