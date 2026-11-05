from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from factories import make_edge
from verity_core.graph.dynamodb import keys
from verity_core.model.edges import EdgeKey
from verity_core.model.enums import Direction, EdgeType, NodeType, Purpose, Role

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
OWNS = EdgeKey("person:a", EdgeType.OWNS, "sys:b", None)
APPLIES = EdgeKey("req:euaia:art4", EdgeType.APPLIES_TO, "sys:b", "provider")


def test_the_documented_key_formats():
    assert keys.node_pk("kestrel", "sys:b") == "T#kestrel#N#sys:b"
    assert keys.edge_sk(OWNS) == "E#OWNS#sys:b"
    assert keys.reverse_sk(OWNS) == "R#OWNS#person:a"
    assert keys.edge_sk(APPLIES) == "E#APPLIES_TO#sys:b#provider"
    assert keys.reverse_sk(APPLIES) == "R#APPLIES_TO#req:euaia:art4#provider"
    assert keys.gsi_type_pk("kestrel", NodeType.AI_SYSTEM) == "T#kestrel#TYPE#AISystem"
    assert keys.history_sk(T0, 3) == "H#2026-11-05T09:00:00.000000Z#0000000003"
    uid = UUID("12345678-1234-5678-1234-567812345678")
    assert keys.usage_sk(T0, uid) == f"U#2026-11-05T09:00:00.000000Z#{uid}"


def test_two_roles_between_one_pair_get_two_keys():
    provider = EdgeKey("req:a:b", EdgeType.APPLIES_TO, "sys:b", Role.PROVIDER.value)
    deployer = EdgeKey("req:a:b", EdgeType.APPLIES_TO, "sys:b", Role.DEPLOYER.value)
    assert keys.edge_sk(provider) != keys.edge_sk(deployer)
    assert keys.reverse_sk(provider) != keys.reverse_sk(deployer)
    purposes = {
        keys.edge_sk(EdgeKey("sys:a", EdgeType.PROCESSES, "ds:d", p.value)) for p in Purpose
    }
    assert len(purposes) == len(Purpose)


def test_prefixes_select_edges_by_type():
    assert keys.edge_prefix() == "E#" and keys.edge_prefix(EdgeType.OWNS) == "E#OWNS#"
    assert keys.reverse_prefix() == "R#" and keys.reverse_prefix(EdgeType.OWNS) == "R#OWNS#"
    sks = {t: keys.edge_sk(EdgeKey("sys:a", t, "sys:z", None)) for t in EdgeType}
    for wanted in EdgeType:
        selected = {t for t, sk in sks.items() if sk.startswith(keys.edge_prefix(wanted))}
        assert selected == {wanted}, wanted
    assert all(sk.startswith(keys.edge_prefix()) for sk in sks.values())


def test_timestamps_are_fixed_width_utc():
    plus_two = datetime(2026, 11, 5, 11, 0, tzinfo=timezone(timedelta(hours=2)))
    assert keys.format_ts(plus_two) == keys.format_ts(T0) == "2026-11-05T09:00:00.000000Z"
    assert len(keys.format_ts(T0)) == len(keys.format_ts(T0 + timedelta(microseconds=7)))
    with pytest.raises(ValueError, match="timezone-aware"):
        keys.format_ts(datetime(2026, 11, 5))


def test_string_order_is_time_order():
    moments = [
        datetime(1999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
        T0,
        T0 + timedelta(microseconds=1),
        T0 + timedelta(seconds=1),
        T0 + timedelta(days=400),
        datetime(2100, 1, 1, tzinfo=UTC),
        datetime(2026, 11, 5, 11, 0, tzinfo=timezone(timedelta(hours=2))),  # equals T0
    ]
    by_time = sorted(moments)
    assert sorted(moments, key=keys.format_ts) == by_time


def test_history_sorts_oldest_first_and_by_numeric_version():
    stamped = [(T0 + timedelta(days=1), 1), (T0, 10), (T0, 9), (T0, 2)]
    ordered = sorted(stamped, key=lambda s: keys.history_sk(*s))
    assert ordered == [(T0, 2), (T0, 9), (T0, 10), (T0 + timedelta(days=1), 1)]


def test_usage_range_selects_exactly_the_half_open_interval():
    stamps = [T0 + timedelta(minutes=m) for m in (-5, 0, 0, 10, 10, 20, 30)]
    records = [(ts, uuid4()) for ts in stamps]
    since, until = T0 + timedelta(minutes=10), T0 + timedelta(minutes=20)
    for lo_bound, hi_bound in [(since, until), (since, None), (None, until), (None, None)]:
        low, high = keys.usage_sk_range(lo_bound, hi_bound)
        selected = {r for r in records if low <= keys.usage_sk(*r) <= high}
        expected = {
            r
            for r in records
            if (lo_bound is None or r[0] >= lo_bound) and (hi_bound is None or r[0] < hi_bound)
        }
        assert selected == expected, (lo_bound, hi_bound)


def test_the_unbounded_usage_range_covers_only_usage_items():
    low, high = keys.usage_sk_range(None, None)
    others = ["META", "E#OWNS#x", "R#OWNS#x", f"H#{keys.format_ts(T0)}#0000000001"]
    assert not any(low <= sk <= high for sk in others)
    assert low <= keys.usage_sk(T0, uuid4()) <= high


def test_kind_of_reads_the_sort_key():
    assert keys.kind_of("META") == "META"
    assert keys.kind_of(keys.edge_sk(OWNS)) == "E"
    assert keys.kind_of(keys.reverse_sk(OWNS)) == "R"
    assert keys.kind_of(keys.history_sk(T0, 1)) == "H"
    assert keys.kind_of(keys.usage_sk(T0, uuid4())) == "U"
    for bad in ("", "X#1", "META2", "e#lower"):
        with pytest.raises(ValueError):
            keys.kind_of(bad)


def test_one_tenant_prefix_never_matches_another_tenant():
    assert keys.tenant_prefix("a") == "T#a#"
    for other in ("a-b", "a.b", "ab", "a_b"):
        assert not keys.node_pk(other, "sys:x").startswith(keys.tenant_prefix("a"))


def test_estate_keys_split_unambiguously_on_the_delimiter(estate):
    graph = estate.load_graph()
    for node_id in graph.nodes:
        pk = keys.node_pk("kestrel", node_id)
        assert pk.count("#") == 3 and pk.split("#", 3)[3] == node_id
    for _, _, edge in graph.edges(data="record"):
        forward, reverse = keys.edge_sk(edge.key), keys.reverse_sk(edge.key)
        extra = 1 if edge.qualifier else 0
        assert forward.count("#") == reverse.count("#") == 2 + extra
        assert forward.split("#")[1] == reverse.split("#")[1] == edge.type.value


def test_plain_edges_have_no_trailing_separator():
    edge = make_edge(EdgeType.OWNS, "person:a", "sys:b")
    assert not keys.edge_sk(edge.key).endswith("#")


def test_neighbour_order_is_exactly_the_sort_key_order():
    from verity_core.graph.planning import neighbor_sort_key

    # Ids and qualifiers where one is a prefix of another, and with every separator character
    # an id may contain. If the tuple order and the key order disagreed, the two repositories
    # would return edges in different orders.
    nodes = ["a:b", "a:b-c", "a:b.c", "a:b_c", "a:b1", "a:bb", "a:b:c", "c:a"]
    all_keys = [
        EdgeKey(src, type_, dst, qualifier)
        for type_ in (EdgeType.OWNS, EdgeType.APPLIES_TO, EdgeType.ASSESSED, EdgeType.ASSESSES)
        for src in nodes[:4]
        for dst in nodes
        for qualifier in (None, "deployer", "provider")
        if src != dst
    ]
    out = sorted(all_keys, key=keys.edge_sk)
    assert out == sorted(all_keys, key=lambda k: neighbor_sort_key(k, Direction.OUT))
    incoming = sorted(all_keys, key=keys.reverse_sk)
    assert [(k.type, k.src, k.qualifier or "") for k in incoming] == [
        (k.type, k.src, k.qualifier or "")
        for k in sorted(all_keys, key=lambda k: neighbor_sort_key(k, Direction.IN))
    ]
