"""The fields ADR 0017 adds: system facts for the rules, and `verified_against`."""

from datetime import date

import pytest
from factories import one_of_each
from pydantic import ValidationError
from verity_core.model.enums import NodeType, Role, VerifiedAgainst
from verity_core.model.nodes import AISystem, Requirement, parse_node


def test_system_facts_default_to_unknown():
    system = one_of_each()[NodeType.AI_SYSTEM]
    assert system.roles == []
    assert system.use_domains == []
    assert system.interacts_with_people is None
    assert system.generates_synthetic_content is None
    assert system.first_placed_on_market is None


def test_system_facts_round_trip():
    system = one_of_each()[NodeType.AI_SYSTEM].model_copy(
        update={
            "roles": [Role.PROVIDER, Role.DEPLOYER],
            "use_domains": ["employment"],
            "interacts_with_people": False,
            "first_placed_on_market": date(2026, 1, 15),
        }
    )
    assert parse_node(system.model_dump(mode="json")) == system


def test_a_system_cannot_have_the_any_role():
    data = one_of_each()[NodeType.AI_SYSTEM].model_dump() | {"roles": [Role.ANY]}
    with pytest.raises(ValidationError, match="specific role"):
        AISystem(**data)


@pytest.mark.parametrize("domain", ["Employment", "has space", "", "1st"])
def test_use_domains_are_lower_case_slugs(domain):
    data = one_of_each()[NodeType.AI_SYSTEM].model_dump() | {"use_domains": [domain]}
    with pytest.raises(ValidationError):
        AISystem(**data)


def test_a_requirement_must_say_what_it_was_verified_against():
    data = one_of_each()[NodeType.REQUIREMENT].model_dump()
    del data["verified_against"]
    with pytest.raises(ValidationError, match="verified_against"):
        Requirement(**data)


def test_verified_against_only_takes_the_two_values():
    data = one_of_each()[NodeType.REQUIREMENT].model_dump() | {"verified_against": "licensed"}
    with pytest.raises(ValidationError):
        Requirement(**data)
    assert {v.value for v in VerifiedAgainst} == {"primary_text", "public_listing"}
