import json
from datetime import UTC, datetime
from urllib.parse import quote

import pytest
from discovery_support import CANARY, TRUST, trail_event
from verity_core.discovery.boundary import (
    BoundaryError,
    clean_function,
    clean_manifest,
    clean_role,
    clean_table,
    clean_tags,
    clean_trail_event,
    scrub,
)


def raw_function(**changes) -> dict:
    base = {
        "FunctionName": "f",
        "FunctionArn": "arn:aws:lambda:eu-north-1:123456789012:function:f",
        "Runtime": "python3.12",
        "Role": "arn:aws:iam::123456789012:role/f-role",
        "Handler": "app.handler",
        "CodeSha256": "abc",
        "MemorySize": 128,
        "Timeout": 10,
        "Architectures": ["arm64"],
        "Description": "Renders PDFs",
        "Environment": {"Variables": {"B": CANARY, "A": CANARY}},
    }
    return base | changes


def test_a_function_keeps_env_names_sorted_and_drops_the_values():
    function = clean_function(raw_function())
    assert function.env_names == ("A", "B")
    assert CANARY not in repr(function)


def test_a_function_without_env_vars_has_no_names():
    raw = raw_function()
    del raw["Environment"]
    assert clean_function(raw).env_names == ()


def test_account_ids_become_a_placeholder_in_every_kept_string():
    function = clean_function(raw_function())
    assert function.arn == "arn:aws:lambda:eu-north-1:<account>:function:f"
    assert function.role_arn == "arn:aws:iam::<account>:role/f-role"
    assert scrub("a 123456789012 b 1234567890123") == "a <account> b 1234567890123"


def test_the_description_is_scored_but_hidden_from_the_repr():
    function = clean_function(raw_function())
    assert function.description == "Renders PDFs"
    assert "Renders" not in repr(function)


def test_a_malformed_function_raises_a_fixed_message_without_its_content():
    bad = {"FunctionName": "f", "Environment": {"Variables": {"K": CANARY}}}
    with pytest.raises(BoundaryError) as caught:
        clean_function(bad)
    assert str(caught.value) == "malformed function record"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert CANARY not in repr(caught.value)


def test_a_wrongly_typed_field_cannot_leak_through_the_message():
    with pytest.raises(BoundaryError) as caught:
        clean_function(raw_function(MemorySize=CANARY))
    assert CANARY not in str(caught.value)


def test_tags_are_keyed_by_the_cleaned_arn():
    tags = clean_tags(
        [
            {
                "ResourceARN": "arn:aws:lambda:eu-north-1:123456789012:function:f",
                "Tags": [{"Key": "ai:system-id", "Value": "sys:x"}],
            }
        ]
    )
    assert tags == {"arn:aws:lambda:eu-north-1:<account>:function:f": {"ai:system-id": "sys:x"}}


def policy(*statements) -> dict:
    return {"Version": "2012-10-17", "Statement": list(statements)}


def role(inline=(), attached=()):
    raw = {
        "RoleName": "r",
        "Arn": "arn:aws:iam::123456789012:role/r",
        "AssumeRolePolicyDocument": TRUST,
    }
    return clean_role(raw, inline, attached)


def test_a_role_sorts_statements_actions_and_resources():
    a = {"Effect": "Allow", "Action": ["s3:Z", "s3:A"], "Resource": ["b", "a"]}
    b = {"Effect": "Allow", "Action": "logs:Put", "Resource": "*"}
    one = role(inline=[{"PolicyName": "p", "PolicyDocument": policy(a, b)}])
    two = role(inline=[{"PolicyName": "p", "PolicyDocument": policy(b, a)}])
    assert one == two
    assert one.policies[0].statements[1].actions == ("s3:A", "s3:Z")
    assert one.policies[0].statements[1].resources == ("a", "b")


def test_a_single_statement_dict_and_a_url_encoded_document_both_read():
    single = {"Effect": "Allow", "Action": "a:B", "Resource": "*"}
    encoded = quote(json.dumps({"Statement": [{"Effect": "Deny", "Action": "x:y"}]}))
    found = role(
        inline=[{"PolicyName": "p", "PolicyDocument": {"Statement": single}}],
        attached=[{"PolicyName": "m", "PolicyDocument": encoded}],
    )
    assert [p.kind for p in found.policies] == ["inline", "managed"]
    assert found.policies[1].statements[0].effect == "Deny"


def test_not_action_and_not_resource_statements_are_marked():
    statement = {"Effect": "Allow", "NotAction": "iam:*", "NotResource": "arn:x"}
    found = role(inline=[{"PolicyName": "p", "PolicyDocument": policy(statement)}])
    assert (found.statements[0].not_action, found.statements[0].not_resource) == (True, True)
    assert found.statements[0].actions == ("iam:*",)


def test_an_unknown_effect_is_refused():
    statement = {"Effect": "Maybe", "Action": "a:B", "Resource": "*"}
    with pytest.raises(BoundaryError):
        role(inline=[{"PolicyName": "p", "PolicyDocument": policy(statement)}])


def test_a_table_arn_is_built_without_the_account():
    table = clean_table("verity-graph", "eu-north-1")
    assert table.arn == "arn:aws:dynamodb:eu-north-1:<account>:table/verity-graph"


def manifest(value: str, name="/verity/manifests/x.yaml") -> dict:
    return {"Name": name, "Value": value}


def test_a_valid_manifest_reads():
    value = "system: sys:x\nresources:\n  - {type: lambda, name: b}\n  - {type: lambda, name: a}\n"
    found = clean_manifest(manifest(value))
    assert (found.system, found.functions) == ("sys:x", ("a", "b"))


@pytest.mark.parametrize(
    "value",
    [
        "system: [unclosed",
        "- just\n- a list\n",
        "system: sys:x\n",  # no resources
        "system: sys:x\nresources: []\n",
        "system: notanid\nresources:\n  - {type: lambda, name: a}\n",
        "system: res:lambda:x:y\nresources:\n  - {type: lambda, name: a}\n",
        "system: sys:x\nresources:\n  - {type: bucket, name: a}\n",
        "system: sys:x\nextra: 1\nresources:\n  - {type: lambda, name: a}\n",
    ],
)
def test_an_invalid_manifest_gives_none_and_nothing_else(value):
    assert clean_manifest(manifest(value)) is None


def test_a_manifest_with_no_value_is_invalid():
    assert clean_manifest({"Name": "/verity/manifests/x.yaml"}) is None


def test_a_trail_event_keeps_source_name_time_and_role_only():
    event = clean_trail_event(trail_event("support-assistant-role", name="Converse"))
    assert (event.event_source, event.event_name, event.role_name) == (
        "bedrock.amazonaws.com",
        "Converse",
        "support-assistant-role",
    )
    assert event.event_time == datetime(2026, 11, 1, tzinfo=UTC)
    assert event.event_type == "AwsApiCall"
    assert "prompt" not in repr(event)


def test_a_trail_event_without_detail_has_no_role():
    raw = trail_event("r") | {"CloudTrailEvent": "{}"}
    assert clean_trail_event(raw).role_name is None
    del raw["CloudTrailEvent"]
    assert clean_trail_event(raw).role_name is None


def test_a_trail_event_time_can_be_text():
    raw = trail_event("r") | {"EventTime": "2026-11-01T00:00:00+00:00"}
    assert clean_trail_event(raw).event_time == datetime(2026, 11, 1, tzinfo=UTC)
    json.dumps(raw)  # the raw shape is plain data
