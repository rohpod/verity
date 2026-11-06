import pytest
from verity_core.model import ids
from verity_core.model.enums import NodeType


def test_every_node_type_has_a_unique_prefix():
    assert set(ids.PREFIXES) == set(NodeType)
    assert len(set(ids.PREFIXES.values())) == len(NodeType) == 18


def test_documented_examples():
    assert ids.system_id("talent-screening") == "sys:talent-screening"
    assert (
        ids.resource_id("lambda", "eu-north-1", "talent-screening")
        == "res:lambda:eu-north-1:talent-screening"
    )
    assert ids.resource_id("iam-role", "global", "crawler") == "res:iam-role:global:crawler"
    assert ids.framework_id("euaia") == "fw:euaia"
    assert ids.requirement_id("euaia", "art50-1") == "req:euaia:art50-1"
    assert ids.requirement_id("iso42001", "A.6.2.4") == "req:iso42001:A.6.2.4"
    assert ids.requirement_id("nistrmf", "MAP-1.1") == "req:nistrmf:MAP-1.1"
    assert ids.control_id("VC-014") == "ctl:VC-014"
    assert ids.person_id("a-singh") == "person:a-singh"


def test_ca_id_combines_control_and_scope():
    scope = ids.system_id("talent-screening")
    assert ids.ca_id(ids.control_id("VC-014"), scope) == "ca:VC-014:sys:talent-screening"


def test_ca_id_rejects_wrong_control_or_scope_type():
    with pytest.raises(ValueError):
        ids.ca_id(ids.system_id("x"), ids.system_id("y"))
    with pytest.raises(ValueError, match="cannot scope"):
        ids.ca_id(ids.control_id("VC-014"), ids.dataset_id("applicants"))


@pytest.mark.parametrize("node_type", list(NodeType))
def test_node_type_of_round_trips_every_prefix(node_type):
    assert ids.node_type_of(ids.make_id(node_type, "x")) is node_type


def test_ca_prefix_is_not_confused_with_cand():
    assert ids.node_type_of("ca:VC-001:org:kestrel") is NodeType.CONTROL_ASSESSMENT
    assert ids.node_type_of("cand:shadow-summariser") is NodeType.CANDIDATE


@pytest.mark.parametrize("bad", ["", "sys", "sys:", "nope:x", "sys:a#b", "sys:a b", ":x"])
def test_node_type_of_rejects_malformed_ids(bad):
    with pytest.raises(ValueError):
        ids.node_type_of(bad)


@pytest.mark.parametrize("part", ["", "a#b", "a:b", "a b", "a/b"])
def test_parts_reject_key_delimiters_and_separators(part):
    with pytest.raises(ValueError):
        ids.system_id(part)


def test_check_id_rejects_other_node_types():
    assert ids.check_id("sys:x", NodeType.AI_SYSTEM) == "sys:x"
    with pytest.raises(ValueError, match="expected"):
        ids.check_id("prov:x", NodeType.AI_SYSTEM)


def test_discovery_run_id_is_the_start_time_in_utc():
    from datetime import UTC, datetime, timedelta, timezone

    started = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
    assert ids.discovery_run_id(started) == "run:20261106T090000.000000Z"
    plus_two = started.astimezone(timezone(timedelta(hours=2)))
    assert ids.discovery_run_id(plus_two) == ids.discovery_run_id(started)
    with pytest.raises(ValueError, match="timezone-aware"):
        ids.discovery_run_id(datetime(2026, 11, 6, 9, 0))


def test_change_event_id_is_one_per_resource_per_run():
    from datetime import UTC, datetime

    run = ids.discovery_run_id(datetime(2026, 11, 6, 9, 0, tzinfo=UTC))
    one = ids.change_event_id(run, ids.resource_id("lambda", "eu-north-1", "a"))
    two = ids.change_event_id(run, ids.resource_id("lambda", "eu-north-1", "b"))
    assert one.startswith("chg:20261106T090000.000000Z:")
    assert len(one.rpartition(":")[2]) == 16
    assert one != two
    assert one == ids.change_event_id(run, ids.resource_id("lambda", "eu-north-1", "a"))
    assert ids.node_type_of(one) is NodeType.CHANGE_EVENT


def test_a_plain_role_name_is_its_own_part():
    assert ids.iam_role_part("verity-crawler_1.x") == "verity-crawler_1.x"


def test_role_names_with_iam_only_characters_give_valid_distinct_parts():
    first, second = ids.iam_role_part("a+b@c"), ids.iam_role_part("a,b=c")
    assert first != second
    assert first.startswith("a-b-c-") and second.startswith("a-b-c-")
    for part in (first, second):
        assert ids.resource_id("iam-role", "global", part)
    assert ids.iam_role_part("a+b@c") == first
