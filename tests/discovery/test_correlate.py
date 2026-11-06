from discovery_support import SIGNALS, make_function
from verity_core.discovery.boundary import CollectedManifest
from verity_core.discovery.correlate import CandidateSpec, Link, candidates, in_manifest, links
from verity_core.discovery.signals import Score
from verity_core.model.enums import AiLikelihood as L

KNOWN = {"sys:a", "sys:b"}


def arn(function) -> str:
    return function.arn


def manifest(system, *names) -> CollectedManifest:
    return CollectedManifest("/verity/manifests/m.yaml", system, tuple(names))


def test_a_tag_links_to_the_system_it_names():
    f = make_function("f")
    found = links(SIGNALS, [f], {arn(f): {"ai:system-id": "sys:a"}}, [], KNOWN)
    assert found == {"f": Link(("sys:a",), ())}


def test_a_manifest_links_to_the_functions_it_lists():
    f, g = make_function("f"), make_function("g")
    found = links(SIGNALS, [f, g], {}, [manifest("sys:b", "f", "absent")], KNOWN)
    assert found == {"f": Link(("sys:b",), ()), "g": Link()}
    assert in_manifest([manifest("sys:b", "f", "absent")]) == {"f", "absent"}


def test_a_tag_and_a_manifest_naming_the_same_system_link_once():
    f = make_function("f")
    found = links(
        SIGNALS, [f], {arn(f): {"ai:system-id": "sys:a"}}, [manifest("sys:a", "f")], KNOWN
    )
    assert found["f"].systems == ("sys:a",)


def test_two_different_systems_both_link():
    f = make_function("f")
    found = links(
        SIGNALS, [f], {arn(f): {"ai:system-id": "sys:a"}}, [manifest("sys:b", "f")], KNOWN
    )
    assert found["f"].systems == ("sys:a", "sys:b")


def test_a_system_that_does_not_exist_is_unknown_not_linked():
    f = make_function("f")
    found = links(SIGNALS, [f], {arn(f): {"ai:system-id": "sys:ghost"}}, [], KNOWN)
    assert found["f"] == Link((), ("sys:ghost",))


def test_a_value_that_is_not_an_id_is_unknown_too():
    f = make_function("f")
    found = links(SIGNALS, [f], {arn(f): {"ai:system-id": "support"}}, [], KNOWN)
    assert found["f"].unknown == ("support",)


def scores(**by_name):
    return {name: Score(level, tuple(sigs)) for name, (level, sigs) in by_name.items()}


def test_an_unlinked_probable_or_possible_function_is_a_candidate():
    found = candidates(
        scores(a=(L.PROBABLE, ["env_ai_name"]), b=(L.POSSIBLE, ["name_ai_token"]), c=(L.NONE, ())),
        {"a": Link(), "b": Link(), "c": Link()},
    )
    assert found == [
        CandidateSpec("a", L.PROBABLE, ("env_ai_name",)),
        CandidateSpec("b", L.POSSIBLE, ("name_ai_token",)),
    ]


def test_an_unlinked_function_with_proven_usage_is_a_candidate():
    found = candidates(scores(a=(L.CONFIRMED_USAGE, ["trail_ai_event"])), {"a": Link()})
    assert [c.likelihood for c in found] == [L.CONFIRMED_USAGE]


def test_a_linked_function_is_not_a_candidate():
    found = candidates(scores(a=(L.PROBABLE, ["x"])), {"a": Link(("sys:a",), ())})
    assert found == []


def test_naming_an_unknown_system_makes_a_declared_candidate_with_its_signal():
    found = candidates(scores(a=(L.DECLARED, ["tag_system_id"])), {"a": Link((), ("sys:ghost",))})
    assert found == [CandidateSpec("a", L.DECLARED, ("names_unknown_system", "tag_system_id"))]


def test_a_function_linked_to_one_system_and_naming_a_ghost_is_still_a_candidate():
    found = candidates(
        scores(a=(L.DECLARED, ["tag_system_id"])), {"a": Link(("sys:a",), ("sys:g",))}
    )
    assert [c.function for c in found] == ["a"]


def test_a_platform_component_is_never_a_candidate():
    found = candidates(scores(a=(L.NONE, ["platform_component"])), {"a": Link()})
    assert found == []
