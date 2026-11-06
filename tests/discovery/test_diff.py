from datetime import timedelta

from discovery_support import allow, make_function, make_role
from factories import COMMON, T0
from verity_core.discovery.boundary import clean_table
from verity_core.discovery.diff import (
    config_hash,
    diff,
    expiring,
    function_config,
    role_config,
    table_config,
)
from verity_core.model.evidence import Evidence
from verity_core.model.ids import resource_id
from verity_core.model.nodes import AWSResource


def resource(name, hash_) -> AWSResource:
    return AWSResource(
        id=resource_id("lambda", "eu-north-1", name),
        resource_type="lambda",
        region="eu-north-1",
        name=name,
        config_hash=hash_,
        **COMMON,
    )


def test_the_hash_ignores_key_order():
    assert config_hash({"a": 1, "b": [1, 2]}) == config_hash({"b": [1, 2], "a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})


def test_a_function_hash_changes_with_env_names_but_not_with_anything_else():
    base = make_function("f", env=["A"])
    tags = {"k": "v"}
    same = config_hash(function_config(base, tags))
    assert config_hash(function_config(make_function("f", env=["A"]), dict(tags))) == same
    assert config_hash(function_config(make_function("f", env=["A", "B"]), tags)) != same
    assert config_hash(function_config(base, {"k": "w"})) != same
    # The description is free text and is not part of the config.
    assert (
        config_hash(function_config(make_function("f", env=["A"], description="x"), tags)) == same
    )


def test_a_function_hash_changes_with_its_code_and_role():
    base = make_function("f")
    other_code = base.__class__(**{**base.__dict__, "code_sha256": "y"})
    other_role = make_function("f", role="another")
    one = config_hash(function_config(base, {}))
    assert config_hash(function_config(other_code, {})) != one
    assert config_hash(function_config(other_role, {})) != one


def test_a_role_hash_ignores_statement_order_and_notices_a_change():
    a, b = allow("s3:Get", "x"), allow("logs:Put", "y")
    one = make_role("r", a, b)
    assert config_hash(role_config(one)) != config_hash(role_config(make_role("r", a)))
    assert config_hash(role_config(one)) == config_hash(role_config(make_role("r", a, b)))


def test_a_table_hash_covers_name_and_tags():
    table = clean_table("verity-graph", "eu-north-1", "acct_0123abcd")
    assert config_hash(table_config(table, {})) != config_hash(table_config(table, {"k": "v"}))


def test_diff_finds_new_changed_and_gone():
    stored = {
        r.id: r for r in (resource("same", "h1"), resource("edit", "h2"), resource("old", "h3"))
    }
    current = {
        resource_id("lambda", "eu-north-1", "same"): "h1",
        resource_id("lambda", "eu-north-1", "edit"): "h2-new",
        resource_id("lambda", "eu-north-1", "fresh"): "h4",
    }
    found = diff(stored, current)
    assert [i.rpartition(":")[2] for i in found.new] == ["fresh"]
    assert [i.rpartition(":")[2] for i in found.changed] == ["edit"]
    assert [i.rpartition(":")[2] for i in found.gone] == ["old"]


def test_a_stored_resource_with_no_hash_counts_as_changed():
    stored = {r.id: r for r in (resource("f", None),)}
    assert diff(stored, {resource_id("lambda", "eu-north-1", "f"): "h"}).changed


def snapshot(valid_until) -> Evidence:
    return Evidence.build(
        subject=resource_id("lambda", "eu-north-1", "f"),
        collector="crawler@0.1.0",
        collected_at=T0,
        valid_until=valid_until,
        kind="config_snapshot",
        content={"config_hash": "h"},
        **COMMON,
    )


def test_evidence_is_due_when_missing_or_within_the_refresh_window():
    now, refresh = T0 + timedelta(days=22), timedelta(days=8)
    assert expiring(None, now, refresh)
    assert expiring(snapshot(T0 + timedelta(days=30)), now, refresh)  # 8 days left
    assert not expiring(snapshot(T0 + timedelta(days=31)), now, refresh)  # 9 days left
    assert expiring(snapshot(T0 + timedelta(days=30)), T0 + timedelta(days=40), refresh)
