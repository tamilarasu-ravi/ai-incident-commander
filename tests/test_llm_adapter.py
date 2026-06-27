"""Tests for LLM adapter model routing and evidence budgeting."""

from unittest.mock import patch

from ai_incident_commander.config import Settings
from ai_incident_commander.llm.adapter import _resolve_model_names, build_llm


def test_resolve_model_names_uses_grounding_models_when_configured(make_settings) -> None:
    """Grounding purpose prefers dedicated cheaper model env vars."""
    settings: Settings = make_settings(
        openai_model="gpt-4.1",
        openai_grounding_model="gpt-4.1-mini",
        google_model="gemini-2.0-flash",
        google_grounding_model="gemini-2.0-flash-lite",
    )

    openai_model, google_model = _resolve_model_names(settings, "grounding")

    assert openai_model == "gpt-4.1-mini"
    assert google_model == "gemini-2.0-flash-lite"


def test_resolve_model_names_falls_back_to_primary_models(make_settings) -> None:
    """Grounding purpose uses synthesis models when grounding overrides are unset."""
    settings: Settings = make_settings(
        openai_model="gpt-4.1",
        google_model="gemini-2.0-flash",
    )

    openai_model, google_model = _resolve_model_names(settings, "grounding")

    assert openai_model == "gpt-4.1"
    assert google_model == "gemini-2.0-flash"


def test_build_llm_grounding_uses_openai_grounding_model(make_settings) -> None:
    """Grounding LLM builder passes the configured grounding model to OpenAI."""
    settings: Settings = make_settings(
        openai_api_key="sk-test",
        openai_model="gpt-4.1",
        openai_grounding_model="gpt-4.1-mini",
    )

    with patch("ai_incident_commander.llm.adapter.ChatOpenAI") as chat_openai:
        chat_openai.return_value = object()
        build_llm(settings, purpose="grounding")

    chat_openai.assert_called_once_with(
        model="gpt-4.1-mini",
        api_key="sk-test",
        temperature=0,
    )
