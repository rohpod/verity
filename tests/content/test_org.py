from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from content_samples import good_files, good_org, write_tree
from verity_core.content.lint import lint
from verity_core.content.loader import ContentError, load_content
from verity_core.content.seed import seed
from verity_core.graph.integrity import check_integrity
from verity_core.graph.memory import InMemoryRepository
from verity_core.graph.traversals import provider_impact
from verity_core.model.edges import ProcessesEdge
from verity_core.model.enums import (
    EdgeType,
    ModelOrigin,
    NodeType,
    Purpose,
    Role,
    Source,
)
from verity_core.model.nodes import AISystem, Model, Provider
from verity_core.model.validation import GraphValidationError

REAL = Path(__file__).parents[2] / "content"


def with_org(org=None, files=None):
    files = dict(files if files is not None else good_files())
    files["org/kestrel.yaml"] = org if org is not None else good_org()
    return files


def load(tmp_path, org=None, files=None):
    return load_content(write_tree(tmp_path, with_org(org, files)))


def change(mutate):
    org = good_org()
    mutate(org)
    return org


# --- the loader ----------------------------------------------------------------------------


def test_a_small_estate_loads_with_its_edges(tmp_path):
    content = load(tmp_path)
    kinds = {n.type for n in content.estate}
    assert kinds == {
        NodeType.ORGANISATION,
        NodeType.DEPARTMENT,
        NodeType.PERSON,
        NodeType.PROVIDER,
        NodeType.MODEL,
        NodeType.DATASET,
        NodeType.RISK,
        NodeType.AI_SYSTEM,
    }
    edges = {(e.type, e.src, e.dst) for e in content.edges}
    assert (EdgeType.PART_OF, "dept:legal", "org:kestrel") in edges
    assert (EdgeType.MEMBER_OF, "person:l-ivanova", "dept:legal") in edges
    assert (EdgeType.OWNS, "person:l-ivanova", "sys:faq-bot") in edges
    assert (EdgeType.APPROVES_RISK_FOR, "person:l-ivanova", "sys:faq-bot") in edges
    assert (EdgeType.USES_MODEL, "sys:faq-bot", "model:bedrock-fm") in edges
    assert (EdgeType.PROVIDED_BY, "model:bedrock-fm", "prov:mock-bedrock") in edges
    assert (EdgeType.TRAINED_ON, "model:churn-gbm", "ds:billing") in edges
    assert (EdgeType.HAS_RISK, "sys:faq-bot", "risk:drift") in edges
    assert (EdgeType.OWNS, "person:l-ivanova", "risk:drift") in edges


def test_the_dataset_purpose_is_the_edge_qualifier(tmp_path):
    (edge,) = (e for e in load(tmp_path).edges if isinstance(e, ProcessesEdge))
    assert edge.purpose is Purpose.RETRIEVAL


def test_system_facts_are_kept_and_the_rest_are_unknown(tmp_path):
    systems = {n.id: n for n in load(tmp_path).estate if isinstance(n, AISystem)}
    faq = systems["sys:faq-bot"]
    assert faq.roles == [Role.PROVIDER, Role.DEPLOYER]
    assert faq.first_placed_on_market == date(2026, 3, 2)
    assert faq.interacts_with_people is True
    assert faq.generates_synthetic_content is None


def test_provenance_comes_from_the_item_or_the_file(tmp_path):
    estate = {n.id: n for n in load(tmp_path).estate}
    assert estate["sys:faq-bot"].source is Source.DECLARED
    assert estate["prov:mock-bedrock"].source is Source.SIMULATED
    assert estate["prov:corvid-labs"].source is Source.SYNTHETIC
    assert estate["person:l-ivanova"].source is Source.SYNTHETIC


def test_an_edge_takes_the_provenance_of_the_record_that_declares_it(tmp_path):
    by_key = {(e.type, e.src, e.dst): e for e in load(tmp_path).edges}
    assert by_key[(EdgeType.PROVIDED_BY, "model:bedrock-fm", "prov:mock-bedrock")].source is (
        Source.SIMULATED
    )
    assert by_key[(EdgeType.OWNS, "person:l-ivanova", "sys:faq-bot")].source is Source.DECLARED
    assert by_key[(EdgeType.MEMBER_OF, "person:l-ivanova", "dept:legal")].source is Source.SYNTHETIC


def test_references_may_cross_files(tmp_path):
    org = good_org()
    systems = org.pop("systems")
    files = with_org(org)
    files["org/systems.yaml"] = {"source": "synthetic", "systems": systems}
    content = load_content(write_tree(tmp_path, files))
    assert len([n for n in content.estate if isinstance(n, AISystem)]) == 3


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda o: o["people"][0].update(department="nope"), "unknown department 'nope'"),
        (lambda o: o["systems"][0].update(owner="nobody"), "unknown person 'nobody'"),
        (lambda o: o["systems"][0].update(models=["nope"]), "unknown model 'nope'"),
        (lambda o: o["systems"][0].update(risks=["nope"]), "unknown risk 'nope'"),
        (lambda o: o["models"][0].update(provider="nope"), "unknown provider 'nope'"),
        (lambda o: o["models"][2].update(trained_on=["nope"]), "unknown dataset 'nope'"),
        (lambda o: o["systems"].append(dict(o["systems"][0])), "system 'faq-bot' is defined twice"),
        (lambda o: o["people"].append(dict(o["people"][0])), "person 'l-ivanova' is defined twice"),
        (lambda o: o["systems"][0].update(roles=["any"]), "specific role"),
        (lambda o: o["systems"][0].update(source="discovered"), "source"),
        (lambda o: o["systems"][0].update(source="seeded"), "source"),
        (lambda o: o["systems"][0].update(email="a@b.c"), "Extra inputs"),
        (lambda o: o["systems"][0].update(use_domains=["Employment"]), "use_domains"),
    ],
)
def test_bad_estate_files_are_refused_with_the_file_named(tmp_path, mutate, message):
    with pytest.raises(ContentError, match=message) as error:
        load(tmp_path, change(mutate))
    assert "kestrel.yaml" in str(error.value)


def test_a_provider_on_an_in_house_model_loads_but_the_graph_refuses_it(tmp_path):
    # Whether a model may have a provider depends on its origin, which is a graph rule (ADR 0012),
    # so it is refused when written and not when read.
    content = load(tmp_path, change(lambda o: o["models"][2].update(provider="corvid-labs")))
    repo = InMemoryRepository("kestrel", lambda: datetime(2026, 11, 5, tzinfo=UTC))
    for node in content.nodes():
        repo.upsert_node(node)
    provided_by = next(
        e for e in content.edges if e.type is EdgeType.PROVIDED_BY and e.src == "model:churn-gbm"
    )
    with pytest.raises(GraphValidationError, match="provided_by_third_party_only"):
        repo.upsert_edge(provided_by)


def test_two_organisations_are_refused(tmp_path):
    files = with_org()
    files["org/other.yaml"] = {"organisation": {"slug": "other", "name": "Other Ltd"}}
    with pytest.raises(ContentError, match="exactly one organisation"):
        load_content(write_tree(tmp_path, files))


def test_departments_without_an_organisation_are_refused(tmp_path):
    org = good_org()
    del org["organisation"]
    with pytest.raises(ContentError, match="departments need an organisation"):
        load(tmp_path, org)


# --- the lint rules for the estate -----------------------------------------------------------


def codes(tmp_path, org):
    return {i.code for i in lint(load(tmp_path, org), _small()) if i.code != "unmapped_control"}


def _small():
    from verity_core.content.lint import LintLimits

    return LintLimits(min_controls=1, max_controls=10)


def test_the_good_estate_passes(tmp_path):
    assert codes(tmp_path, good_org()) == set()


@pytest.mark.parametrize(
    ("code", "mutate"),
    [
        ("real_vendor_name", lambda o: o["providers"][1].update(name="OpenAI Ltd")),
        ("real_vendor_name", lambda o: o["models"][1].update(name="Claude Chat")),
        ("real_vendor_name", lambda o: o["models"][1].update(name="Amazon Titan Text")),
        ("simulated_not_labelled", lambda o: o["providers"][0].update(name="Bedrock")),
        ("simulated_source_mismatch", lambda o: o["providers"][0].pop("source")),
        ("simulated_source_mismatch", lambda o: o["providers"][1].update(simulated=True)),
        ("model_source_mismatch", lambda o: o["models"][0].pop("source")),
        ("email_like", lambda o: o["people"][0].update(job_title="Head of Legal, ask l@x.org")),
        ("account_id_like", lambda o: o["risks"][0].update(description="Account 123456789012.")),
    ],
)
def test_each_estate_rule_fires(tmp_path, code, mutate):
    assert code in codes(tmp_path, change(mutate))


def test_a_simulated_provider_may_carry_a_real_name(tmp_path):
    # "Bedrock (simulated)" and "GPT-class" are allowed because the data says they are mocks.
    org = change(lambda o: o["models"][0].update(name="GPT-class"))
    assert "real_vendor_name" not in codes(tmp_path, org)


def test_an_estate_without_an_organisation_is_flagged(tmp_path):
    org = good_org()
    del org["organisation"]
    del org["departments"]
    del org["people"]
    org["risks"][0].pop("owner")
    for system in org["systems"]:
        for key in ("owner", "developers", "risk_approver"):
            system.pop(key, None)
    assert "no_organisation" in codes(tmp_path, org)


# --- the real Kestrel content ----------------------------------------------------------------


@pytest.fixture(scope="module")
def kestrel():
    return load_content(REAL)


def systems(content):
    return {n.id: n for n in content.estate if isinstance(n, AISystem)}


def test_the_real_content_passes_every_rule_that_can_pass_before_the_controls_exist():
    # PR 5 adds the controls and the regulatory content; until then only the control count fails.
    assert {i.code for i in lint(load_content(REAL))} <= {"control_count"}


def test_there_are_three_declared_systems_and_25_synthetic_ones(kestrel):
    by_source = {}
    for system in systems(kestrel).values():
        by_source.setdefault(system.source, []).append(system.id)
    assert sorted(by_source[Source.DECLARED]) == [
        "sys:contract-insights",
        "sys:support-assistant",
        "sys:talent-screening",
    ]
    assert len(by_source[Source.SYNTHETIC]) == 25
    assert set(by_source) == {Source.DECLARED, Source.SYNTHETIC}


def test_the_organisation_is_kestrel_with_fictional_people(kestrel):
    org = [n for n in kestrel.estate if n.type is NodeType.ORGANISATION]
    assert [o.id for o in org] == ["org:kestrel"]
    people = [n for n in kestrel.estate if n.type is NodeType.PERSON]
    assert len(people) == 15
    assert {p.source for p in people} == {Source.SYNTHETIC}


def test_mock_providers_and_their_models_are_simulated_and_labelled(kestrel):
    providers = {n.id: n for n in kestrel.estate if isinstance(n, Provider)}
    mocks = {i: p for i, p in providers.items() if p.simulated}
    assert set(mocks) == {"prov:mock-bedrock", "prov:mock-openai"}
    assert all(p.source is Source.SIMULATED and "simulated" in p.name for p in mocks.values())
    provided = {e.src for e in kestrel.edges if e.type is EdgeType.PROVIDED_BY and e.dst in mocks}
    models = {n.id: n for n in kestrel.estate if isinstance(n, Model)}
    assert {models[m].source for m in provided} == {Source.SIMULATED}


def test_talent_screening_uses_an_in_house_model_in_the_employment_domain(kestrel):
    talent = systems(kestrel)["sys:talent-screening"]
    assert talent.use_domains == ["employment"]
    (uses,) = (e for e in kestrel.edges if e.type is EdgeType.USES_MODEL and e.src == talent.id)
    model = next(n for n in kestrel.estate if n.id == uses.dst)
    assert model.origin is ModelOrigin.IN_HOUSE
    assert not [e for e in kestrel.edges if e.type is EdgeType.PROVIDED_BY and e.src == model.id]


def test_the_demo_gaps_are_there_on_purpose(kestrel):
    owned = {e.dst for e in kestrel.edges if e.type is EdgeType.OWNS}
    modelled = {e.src for e in kestrel.edges if e.type is EdgeType.USES_MODEL}
    unowned = [s for s in systems(kestrel) if s not in owned]
    unmodelled = [s for s in systems(kestrel) if s not in modelled]
    assert unowned == ["sys:legacy-faq-bot"]
    assert unmodelled == ["sys:meeting-minutes-draft"]


def test_the_real_estate_is_sound_when_written_to_a_graph(repo, clock, kestrel):
    seed(repo, kestrel, clock)
    graph = repo.load_graph()
    assert check_integrity(graph) == []
    assert graph.number_of_nodes() == len(kestrel.nodes())


def test_the_provider_impact_view_has_volume_on_each_mock(repo, clock, kestrel):
    seed(repo, kestrel, clock)
    graph = repo.load_graph()
    bedrock = {s.system_id for s in provider_impact(graph, "prov:mock-bedrock").systems}
    openai = {s.system_id for s in provider_impact(graph, "prov:mock-openai").systems}
    assert len(bedrock) == 5 and "sys:support-assistant" in bedrock
    assert len(openai) == 4 and "sys:contract-insights" in openai
    assert "sys:legacy-faq-bot" in bedrock  # the unowned one is exposed too
    assert not bedrock & openai
