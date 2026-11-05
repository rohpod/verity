from datetime import UTC, datetime

import pytest
import yaml
from content_samples import broken, good_files, mapping, requirement, write_tree
from verity_core.content.loader import Content, ContentError, load_content
from verity_core.graph.integrity import check_integrity
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.edges import MapsToEdge
from verity_core.model.enums import EdgeType, NodeType, Source, StrmType


def load(tmp_path, files=None) -> Content:
    return load_content(write_tree(tmp_path, files or good_files()))


def test_an_empty_directory_is_empty_content(tmp_path):
    content = load_content(tmp_path)
    assert content.nodes() == []
    assert content.edges == ()


def test_loads_every_file(tmp_path):
    content = load(tmp_path)
    assert [f.id for f in content.frameworks] == ["fw:euaia", "fw:iso42001"]
    assert len(content.requirements) == 8
    assert len(content.controls) == 4
    assert [d.id for d in content.dates] == ["euaia-example"]
    assert content.copyrighted == {"iso42001"}


def test_everything_is_seeded_in_the_tenant(tmp_path):
    content = load_content(write_tree(tmp_path, good_files()), tenant="acme")
    records = [*content.nodes(), *content.edges]
    assert {r.source for r in records} == {Source.SEEDED}
    assert {r.tenant for r in records} == {"acme"}


def test_requirements_inherit_the_framework_source(tmp_path):
    req = next(r for r in load(tmp_path).requirements if r.id == "req:euaia:art4")
    assert req.source_url == "https://eur-lex.example.org/eu-ai-act"
    assert req.source_version == "2024/1689 as amended by 2026/1744"


def test_a_requirement_can_override_the_framework_source(tmp_path):
    def mutate(files):
        requirement(files, "euaia", "art4")["source_version"] = "something narrower"

    req = next(r for r in load(tmp_path, broken(mutate)).requirements if r.id == "req:euaia:art4")
    assert req.source_version == "something narrower"


def test_top_level_requirements_are_part_of_the_framework_and_children_of_their_parent(tmp_path):
    part_of = {(e.src, e.dst) for e in load(tmp_path).edges if e.type is EdgeType.PART_OF}
    assert ("req:euaia:art9", "fw:euaia") in part_of
    assert ("req:euaia:art9-2a", "req:euaia:art9") in part_of
    assert ("req:euaia:art9-2a", "fw:euaia") not in part_of


def test_mappings_keep_their_stm_fields(tmp_path):
    maps = {(e.src, e.dst): e for e in load(tmp_path).edges if isinstance(e, MapsToEdge)}
    edge = maps[("req:iso42001:A.8.2", "ctl:VC-012")]
    assert edge.strm is StrmType.INTERSECTS_WITH
    assert edge.strength == 5
    negative = maps[("req:euaia:art25", "ctl:VC-014")]
    assert negative.strm is StrmType.NO_RELATIONSHIP
    assert negative.strength is None


def test_the_content_writes_into_a_repository_and_the_graph_is_sound(tmp_path):
    content = load(tmp_path)
    repo = InMemoryRepository("kestrel", lambda: datetime(2026, 11, 5, tzinfo=UTC))
    for node in content.nodes():
        repo.upsert_node(node)
    for edge in content.edges:
        repo.upsert_edge(edge)
    assert len(repo.nodes_by_type(NodeType.REQUIREMENT)) == 8
    assert check_integrity(repo.load_graph()) == []


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    [
        (
            "unknown parent",
            lambda f: requirement(f, "euaia", "art9-2a").update(parent="art99"),
            "unknown parent",
        ),
        (
            "parent cycle",
            lambda f: requirement(f, "euaia", "art9").update(parent="art9-2a"),
            "its own ancestor",
        ),
        (
            "duplicate requirement",
            lambda f: f["frameworks/euaia.yaml"]["requirements"].append(
                dict(requirement(f, "euaia", "art4"))
            ),
            "defined twice",
        ),
        (
            "duplicate control",
            lambda f: f["controls.yaml"]["controls"].append(
                dict(f["controls.yaml"]["controls"][0])
            ),
            "defined twice",
        ),
        (
            "duplicate mapping",
            lambda f: f["mappings/euaia.yaml"]["mappings"].append(
                dict(mapping(f, "euaia", "art4"))
            ),
            "mapped to 'VC-001' twice",
        ),
        (
            "mapping to an unknown control",
            lambda f: mapping(f, "euaia", "art4").update(control="VC-099"),
            "unknown control",
        ),
        (
            "mapping from an unknown requirement",
            lambda f: mapping(f, "euaia", "art4").update(requirement="art99"),
            "unknown requirement",
        ),
        (
            "mapping for an unknown framework",
            lambda f: f["mappings/euaia.yaml"].update(framework="nope"),
            "unknown framework",
        ),
        (
            "no_relationship with a strength",
            lambda f: mapping(f, "euaia", "art25").update(strength=3),
            "no_relationship takes no strength",
        ),
        (
            "an excerpt field on an ISO entry",
            lambda f: requirement(f, "iso42001", "A.6").update(excerpt="copied text"),
            "excerpt",
        ),
        (
            "a bad control code",
            lambda f: f["controls.yaml"]["controls"][0].update(code="C1"),
            "code",
        ),
        (
            "an automatable organisational control",
            lambda f: f["controls.yaml"]["controls"][0].update(automatable=True),
            "cannot be automatable",
        ),
        (
            "a duplicate date",
            lambda f: f["rules/obligation_dates.yaml"]["dates"].append(
                dict(f["rules/obligation_dates.yaml"]["dates"][0])
            ),
            "defined twice",
        ),
    ],
)
def test_bad_content_is_refused_with_the_file_named(tmp_path, name, mutate, message):
    with pytest.raises(ContentError, match=message) as error:
        load(tmp_path, broken(mutate))
    assert str(error.value).startswith(str(tmp_path)), name


def test_a_duplicate_yaml_key_is_an_error(tmp_path):
    write_tree(tmp_path, good_files())
    (tmp_path / "controls.yaml").write_text(
        "controls:\n  - code: VC-001\n    code: VC-002\n    title: x\n"
    )
    with pytest.raises(ContentError, match="duplicate key 'code'"):
        load_content(tmp_path)


def test_invalid_yaml_is_an_error(tmp_path):
    write_tree(tmp_path, good_files())
    (tmp_path / "controls.yaml").write_text("controls: [unclosed")
    with pytest.raises(ContentError):
        load_content(tmp_path)


def test_dates_are_read_as_dates(tmp_path):
    (date,) = load(tmp_path).dates
    assert date.date.isoformat() == "2027-12-02"
    assert yaml.safe_load("a: 2027-12-02")["a"] == date.date
