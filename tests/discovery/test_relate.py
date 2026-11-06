from discovery_support import allow, make_function, make_role
from verity_core.discovery.boundary import clean_table
from verity_core.discovery.names import function_id, role_id, role_name_of, table_id
from verity_core.discovery.relate import relations

TABLE = clean_table("verity-graph", "eu-north-1", "acct_0123abcd")
OTHER = clean_table("other", "eu-north-1", "acct_0123abcd")


def test_a_role_name_comes_from_the_end_of_its_arn():
    assert role_name_of("arn:aws:iam::acct_0123abcd:role/service-role/f-role") == "f-role"
    assert role_name_of("arn:aws:iam::acct_0123abcd:role/f-role") == "f-role"
    assert role_name_of("not-an-arn") is None


def test_a_function_assumes_its_role():
    found = relations([make_function("f")], [make_role("f-role", allow("logs:Put"))], [TABLE])
    assert found.assumes == {(function_id("f"), role_id("f-role"))}
    assert found.calls == set()


def test_a_role_that_was_not_collected_gives_no_edge():
    assert relations([make_function("f")], [], [TABLE]).assumes == frozenset()


def test_calls_come_from_resource_arns_in_allow_statements():
    role = make_role("f-role", allow("dynamodb:GetItem", TABLE.arn))
    found = relations([make_function("f")], [role], [TABLE, OTHER])
    assert found.calls == {(function_id("f"), table_id("verity-graph"))}


def test_a_wildcard_resource_makes_no_edge():
    role = make_role("f-role", allow("dynamodb:*", "*"))
    assert relations([make_function("f")], [role], [TABLE]).calls == frozenset()


def test_a_wildcard_inside_an_arn_matches_known_arns_only():
    role = make_role("f-role", allow("dynamodb:*", "arn:aws:dynamodb:*:*:table/verity-*"))
    found = relations([make_function("f")], [role], [TABLE, OTHER])
    assert found.calls == {(function_id("f"), table_id("verity-graph"))}


def test_deny_and_not_resource_statements_make_no_edge():
    role = make_role(
        "f-role",
        allow("dynamodb:GetItem", TABLE.arn, effect="Deny"),
        allow("dynamodb:GetItem", TABLE.arn, not_resource=True),
    )
    assert relations([make_function("f")], [role], [TABLE]).calls == frozenset()


def test_a_function_can_call_another_function_but_not_itself():
    f, g = make_function("f"), make_function("g")
    role = make_role("f-role", allow("lambda:InvokeFunction", [f.arn, g.arn]))
    found = relations([f, g], [role, make_role("g-role")], [])
    assert found.calls == {(function_id("f"), function_id("g"))}


def test_role_ids_stay_valid_for_names_with_special_characters():
    f = make_function("f", role="a+b@c")
    found = relations([f], [make_role("a+b@c")], [])
    ((_, role),) = found.assumes
    assert role.startswith("res:iam-role:global:a-b-c-")
