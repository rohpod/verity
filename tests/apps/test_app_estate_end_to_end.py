"""Support, contract, shadow and invoice apps, end to end through the real mock handlers.

No network and no AWS: a local invoker and URL transport stand in for Lambda (D8, ADR 0023)."""

import json
import logging

import boto3
import pytest
from estate_support import ROOT, imported_modules, load_app, local_invoker, url_transport
from factories import TENANT
from moto import mock_aws
from verity_ai.bedrock import BedrockCompatible
from verity_ai.openai import OpenAICompatible
from verity_ai.telemetry import UsageRecorder
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import table_definition
from verity_core.graph.dynamodb.usage import DynamoDBUsageSink
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import Source

support = load_app("apps/support_assistant")
contract = load_app("apps/contract_insights")
shadow = load_app("apps/shadow_summariser")
invoice = load_app("apps/invoice_renderer")
mock_bedrock = load_app("mocks/mock_bedrock")
mock_openai = load_app("mocks/mock_openai")

ARTICLES = json.loads((ROOT / "apps/support_assistant/articles.json").read_text())
URL = "http://localhost/v1"
CANARY = "VERITY-CANARY-7f3a"


def no_sign(method, url, body, headers):
    return headers


def recorder(repo, clock, *, system, provider, model):
    return UsageRecorder(
        repo, tenant=TENANT, system_id=system, provider_id=provider, model_id=model, clock=clock
    )


def bedrock_model(repo, clock):
    usage = recorder(
        repo,
        clock,
        system=support.SYSTEM_ID,
        provider="prov:mock-bedrock",
        model="model:bedrock-fm",
    )
    return BedrockCompatible(local_invoker(mock_bedrock.handler), usage=usage)


def openai_model(usage):
    return OpenAICompatible(
        URL, sign=no_sign, usage=usage, transport=url_transport(mock_openai.handler)
    )


def test_support_answers_from_an_article_discloses_the_ai_and_records_usage(clock):
    repo = InMemoryRepository(TENANT, clock)
    result = support.run(
        {"message": "How do I reset my password?"}, ARTICLES, bedrock_model(repo, clock)
    )
    assert result["article_id"] == "reset-password"
    assert result["handoff"] is False
    assert result["reply"].startswith("[SIMULATED]")
    assert result["simulated"] is True
    assert "AI assistant" in result["disclosure"]
    [record] = repo.usage_records(support.SYSTEM_ID)
    assert record.source is Source.SIMULATED
    assert record.provider_id == "prov:mock-bedrock"
    assert record.token_estimate > 0


def test_support_hands_off_when_no_article_matches(clock):
    repo = InMemoryRepository(TENANT, clock)
    result = support.run({"message": "Tell me a joke"}, ARTICLES, bedrock_model(repo, clock))
    assert result["handoff"] is True
    assert result["article_id"] is None


def test_support_ties_go_to_the_first_article_by_id():
    assert support.match(ARTICLES, "invoice api")["id"] == "api-keys"


def test_support_refuses_an_empty_message(clock):
    with pytest.raises(ValueError):
        support.run(
            {"message": " "}, ARTICLES, bedrock_model(InMemoryRepository(TENANT, clock), clock)
        )


def test_contract_summarises_through_mock_openai_and_records_usage_in_dynamodb(clock):
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        usage = recorder(
            DynamoDBUsageSink(TENANT, client=client),
            clock,
            system=contract.SYSTEM_ID,
            provider="prov:mock-openai",
            model="model:gpt-class",
        )
        result = contract.run({"contract_text": "Fictional master agreement."}, openai_model(usage))
        assert result["summary"].startswith("[SIMULATED]")
        assert result["simulated"] is True
        repo = DynamoDBRepository(TENANT, clock, client=client)
        [record] = repo.usage_records(contract.SYSTEM_ID)
        assert (record.provider_id, record.model_id) == ("prov:mock-openai", "model:gpt-class")
        assert record.source is Source.SIMULATED


def test_shadow_summariser_calls_the_mock_and_writes_no_usage(clock):
    repo = InMemoryRepository(TENANT, clock)
    result = shadow.run({"text": "Some notes."}, openai_model(None))
    assert result["summary"].startswith("[SIMULATED]")
    assert repo.usage_records("sys:shadow-summariser") == []


def test_prompts_are_never_logged(clock, caplog):
    repo = InMemoryRepository(TENANT, clock)
    with caplog.at_level(logging.DEBUG):
        support.run({"message": f"password {CANARY}"}, ARTICLES, bedrock_model(repo, clock))
        shadow.run({"text": CANARY}, openai_model(None))
    assert CANARY not in caplog.text


def test_invoice_renderer_fills_the_template(monkeypatch):
    monkeypatch.setenv("INVOICE_TEMPLATE", "template.txt")
    invoice._template.cache_clear()
    result = invoice.handler(
        {
            "invoice_number": "INV-1",
            "customer": "Fictional Customer $1",
            "lines": [{"description": "Seats", "quantity": 3, "unit_price": "9.50"}],
        },
        None,
    )["invoice"]
    assert "INVOICE INV-1" in result
    assert "Customer: Fictional Customer $1" in result
    assert "Seats: 3 x 9.50 = 28.50" in result
    assert result.endswith("Total: 28.50\n")


def test_the_invoice_renderer_uses_no_ai_and_only_the_standard_library():
    assert not imported_modules("apps/invoice_renderer") & {"verity_ai", "verity_core", "boto3"}


def test_the_shadow_summariser_does_not_import_verity_core():
    assert "verity_core" not in imported_modules("apps/shadow_summariser")
