import pytest
from discovery_support import SIGNALS, make_function
from verity_core.discovery.signals import Score, score, tokens
from verity_core.model.enums import AiLikelihood as L

NONE_FIRED = {"in_manifest": False, "iam_ai_action": False, "usage": False, "trail_event": False}


def scored(function, tags=None, **facts) -> Score:
    return score(SIGNALS, function, tags or {}, **{**NONE_FIRED, **facts})


def test_invoice_renderer_scores_none_with_no_signals():
    function = make_function(
        "invoice-renderer", env=["TEMPLATE_BUCKET"], description="Renders invoices as PDF"
    )
    assert scored(function) == Score(L.NONE, ())


def test_an_openai_env_name_scores_probable():
    function = make_function(
        "shadow-summariser", env=["OPENAI_BASE_URL"], description="Summarises documents"
    )
    assert scored(function) == Score(L.PROBABLE, ("env_ai_name", "name_ai_token"))


@pytest.mark.parametrize(
    "name",
    [
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "BEDROCK_REGION",
        "AZURE_OPENAI_ENDPOINT",
        "MODEL_ADAPTER",
        "LLM_URL",
        "MY_GPT_MODEL",
    ],
)
def test_ai_env_names_score_probable(name):
    assert scored(make_function("x", env=[name])).likelihood is L.PROBABLE


@pytest.mark.parametrize(
    "name", ["TEMPLATE_BUCKET", "LOG_LEVEL", "MODELS_DIR", "OPENAIRE_ID", "HELP_TABLE"]
)
def test_ordinary_env_names_score_nothing(name):
    assert scored(make_function("x", env=[name])).likelihood is L.NONE


@pytest.mark.parametrize(
    "name", ["mail-sender", "maintenance-job", "email_digest", "paid-invoices", "main"]
)
def test_a_substring_of_ai_in_a_name_is_not_a_token(name):
    assert scored(make_function(name)) == Score(L.NONE, ())


@pytest.mark.parametrize("name", ["ai-router", "doc_ml_trainer", "chatbot", "my-llm-proxy"])
def test_an_ai_token_in_the_name_scores_possible(name):
    assert scored(make_function(name)) == Score(L.POSSIBLE, ("name_ai_token",))


def test_the_description_is_scored_too():
    function = make_function("worker", description="An assistant for the sales team")
    assert scored(function) == Score(L.POSSIBLE, ("name_ai_token",))


def test_the_tag_declares_and_wins_over_weaker_signals():
    function = make_function("x", env=["OPENAI_BASE_URL"])
    result = scored(function, {"ai:system-id": "sys:a"})
    assert result == Score(L.DECLARED, ("env_ai_name", "tag_system_id"))


def test_an_empty_tag_does_not_declare():
    assert scored(make_function("x"), {"ai:system-id": ""}).likelihood is L.NONE


def test_a_manifest_declares():
    assert scored(make_function("x"), in_manifest=True) == Score(L.DECLARED, ("manifest",))


def test_usage_and_trail_events_confirm_usage_above_probable():
    function = make_function("x", env=["OPENAI_BASE_URL"])
    assert scored(function, usage=True).likelihood is L.CONFIRMED_USAGE
    assert scored(function, trail_event=True).signals == ("env_ai_name", "trail_ai_event")


def test_an_iam_ai_grant_scores_probable():
    assert scored(make_function("x"), iam_ai_action=True) == Score(L.PROBABLE, ("iam_ai_action",))


def test_the_ladder_order_is_declared_usage_probable_possible():
    function = make_function("ai-thing", env=["OPENAI_BASE_URL"])
    every = scored(
        function,
        {"ai:system-id": "sys:a"},
        in_manifest=True,
        iam_ai_action=True,
        usage=True,
        trail_event=True,
    )
    assert every.likelihood is L.DECLARED
    assert every.signals == tuple(sorted(every.signals))
    assert set(every.signals) == {s.id for s in SIGNALS.signals}
    no_declaration = scored(function, iam_ai_action=True, usage=True)
    assert no_declaration.likelihood is L.CONFIRMED_USAGE


def test_a_platform_component_scores_none_whatever_else_fires():
    function = make_function("mock-openai", env=["OPENAI_BASE_URL"])
    result = scored(function, {"verity:component": "mock"}, iam_ai_action=True, usage=True)
    assert result == Score(L.NONE, ("platform_component",))


def test_tokens_split_on_anything_that_is_not_a_letter_or_digit():
    assert tokens("Mail-sender_v2, an AI/ML tool") == [
        "mail",
        "sender",
        "v2",
        "an",
        "ai",
        "ml",
        "tool",
    ]


@pytest.mark.parametrize(
    "name",
    [
        "LEGAL_OPENAI_API_KEY",
        "AWS_BEDROCK_REGION",
        "APP_ANTHROPIC_TOKEN",
        "CHATGPT_KEY",
        "SUMMARY_MODEL_ID",
    ],
)
def test_a_vendor_word_anywhere_in_an_env_name_scores_probable(name):
    assert scored(make_function("x", env=[name])).likelihood is L.PROBABLE


@pytest.mark.parametrize("name", ["COHERENT_MODE", "MISTRALLY", "HELP_ARTICLES_TABLE", "MODEL_DIR"])
def test_a_vendor_word_inside_another_word_does_not_count(name):
    assert scored(make_function("x", env=[name])).likelihood is L.NONE


@pytest.mark.parametrize(
    "name", ["ContractSummariserFn", "MyStack-OpenAiProxy-AB12", "gpt4-worker", "OpenAIProxy"]
)
def test_camel_case_and_numbered_names_score_possible(name):
    assert scored(make_function(name)) == Score(L.POSSIBLE, ("name_ai_token",))


@pytest.mark.parametrize("name", ["EmailSender", "RetainLogs", "MyStack-Mailer-AB12"])
def test_camel_case_words_that_contain_ai_score_none(name):
    assert scored(make_function(name)) == Score(L.NONE, ())


def test_camel_case_tokens():
    assert tokens("OpenAiProxy") == tokens("OpenAIProxy") == ["open", "ai", "proxy"]
    assert tokens("ContractSummariserFn") == ["contract", "summariser", "fn"]
    assert tokens("gpt4-worker") == ["gpt4", "worker"]
