"""LLM adapter with OpenAI primary and Google Gemini fallback."""

from pathlib import Path
from typing import Literal

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.llm.evidence_context import (
    format_evidence_for_llm,
    prepare_evidence_for_llm,
)
from ai_incident_commander.llm.usage import ainvoke_with_usage_logging
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.grounding import GroundingVerdict
from ai_incident_commander.models.rca import RcaHypothesis
from ai_incident_commander.ops.metrics import is_rate_limit_error, record_llm_rate_limit_error

logger = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
LlmPurpose = Literal["synthesis", "grounding"]


def load_prompt(name: str) -> str:
    """
    Load a version-controlled prompt file from ``prompts/``.

    Args:
        name: Prompt filename including extension (e.g. ``rca_synthesis.md``).

    Returns:
        Prompt file contents as a string.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _resolve_model_names(settings: Settings, purpose: LlmPurpose) -> tuple[str, str]:
    """
    Resolve OpenAI and Google model names for a given LLM purpose.

    Args:
        settings: Application settings loaded from the environment.
        purpose: Whether the call is for synthesis or grounding validation.

    Returns:
        Tuple of OpenAI model name and Google model name.
    """
    if purpose == "grounding":
        openai_model = settings.openai_grounding_model or settings.openai_model
        google_model = settings.google_grounding_model or settings.google_model
        return openai_model, google_model

    return settings.openai_model, settings.google_model


def build_llm(
    settings: Settings | None = None,
    *,
    purpose: LlmPurpose = "synthesis",
) -> BaseChatModel:
    """
    Build the primary LLM with Google Gemini fallback.

    Args:
        settings: Optional settings override; defaults to cached ``get_settings()``.
        purpose: ``grounding`` may use cheaper provider models when configured.

    Returns:
        LangChain chat model with fallback configured.

    Raises:
        ValueError: If neither OpenAI nor Google API keys are configured.
    """
    resolved = settings or get_settings()
    if not resolved.openai_api_key and not resolved.google_api_key:
        raise ValueError("OPENAI_API_KEY or GOOGLE_API_KEY is required for RCA synthesis")

    openai_model, google_model = _resolve_model_names(resolved, purpose)
    models: list[BaseChatModel] = []
    if resolved.openai_api_key:
        models.append(
            ChatOpenAI(
                model=openai_model,
                api_key=resolved.openai_api_key,
                temperature=0,
            )
        )
    if resolved.google_api_key:
        models.append(
            ChatGoogleGenerativeAI(
                model=google_model,
                google_api_key=resolved.google_api_key,
                temperature=0,
            )
        )

    primary = models[0]
    if len(models) == 1:
        return primary
    return primary.with_fallbacks(models[1:])


def _prepare_evidence(settings: Settings, evidence: EvidenceBundle) -> EvidenceBundle:
    """
    Compact evidence using environment-backed token budget settings.

    Args:
        settings: Application settings with evidence budget fields.
        evidence: Raw collected investigation evidence.

    Returns:
        Evidence bundle trimmed for LLM prompts.
    """
    return prepare_evidence_for_llm(
        evidence,
        field_max_chars=settings.evidence_field_max_chars,
        token_budget=settings.evidence_prompt_token_budget,
        chars_per_token=settings.chars_per_token_estimate,
    )


async def synthesize_rca_hypothesis(
    evidence: EvidenceBundle,
    service: str,
    description: str,
    settings: Settings | None = None,
) -> RcaHypothesis:
    """
    Synthesize a structured RCA hypothesis from collected evidence.

    Args:
        evidence: Evidence bundle gathered for the investigation.
        service: Affected service name.
        description: Incident description from the trigger.
        settings: Optional settings override for LLM configuration.

    Returns:
        Structured ``RcaHypothesis`` from the LLM.

    Raises:
        ValueError: If no LLM provider is configured.
        Exception: Propagates LLM provider errors after logging context.
    """
    resolved = settings or get_settings()
    llm = build_llm(resolved, purpose="synthesis")
    structured_llm = llm.with_structured_output(RcaHypothesis)
    system_prompt = load_prompt("rca_synthesis.md")
    prepared = _prepare_evidence(resolved, evidence)
    user_content = (
        f"Service: {service}\n"
        f"Description: {description}\n\n"
        f"Evidence JSON:\n{format_evidence_for_llm(prepared, mode='full')}"
    )

    log = logger.bind(service=service)
    log.info("rca_synthesis_started")

    try:
        result, _usage = await ainvoke_with_usage_logging(
            structured_llm,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ],
            operation="rca_synthesis",
            service=service,
        )
    except Exception as error:
        if is_rate_limit_error(error):
            from ai_incident_commander.ops.metrics import record_llm_rate_limit_error

            record_llm_rate_limit_error()
        log.error("rca_synthesis_failed", error=str(error))
        raise

    if not isinstance(result, RcaHypothesis):
        hypothesis = RcaHypothesis.model_validate(result)
    else:
        hypothesis = result

    log.info("rca_synthesis_completed", root_cause=hypothesis.root_cause_candidate)
    return hypothesis


async def validate_rca_grounding(
    evidence: EvidenceBundle,
    rca: RcaHypothesis,
    settings: Settings | None = None,
) -> GroundingVerdict:
    """
    Validate whether an RCA hypothesis is grounded in raw evidence.

    Args:
        evidence: Evidence bundle shown to the validator (RCA excluded).
        rca: RCA hypothesis to validate.
        settings: Optional settings override for LLM configuration.

    Returns:
        Grounding verdict with binary grounding score.

    Raises:
        ValueError: If no LLM provider is configured.
        Exception: Propagates LLM provider errors after logging context.
    """
    resolved = settings or get_settings()
    llm = build_llm(resolved, purpose="grounding")
    structured_llm = llm.with_structured_output(GroundingVerdict)
    system_prompt = load_prompt("grounding_validator.md")
    prepared = _prepare_evidence(resolved, evidence)
    user_content = (
        f"Proposed RCA:\n{rca.model_dump_json(indent=2)}\n\n"
        f"Evidence summary:\n{format_evidence_for_llm(prepared, mode='summary')}"
    )

    log = logger.bind(service=rca.affected_service)
    log.info("grounding_validation_started")

    try:
        result, _usage = await ainvoke_with_usage_logging(
            structured_llm,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ],
            operation="grounding_validation",
            service=rca.affected_service,
        )
    except Exception as error:
        if is_rate_limit_error(error):
            record_llm_rate_limit_error()
        log.error("grounding_validation_failed", error=str(error))
        raise

    if not isinstance(result, GroundingVerdict):
        verdict = GroundingVerdict.model_validate(result)
    else:
        verdict = result

    normalized_score = 1.0 if verdict.grounded else 0.0
    if verdict.grounding_score != normalized_score:
        verdict = verdict.model_copy(update={"grounding_score": normalized_score})

    log.info(
        "grounding_validation_completed",
        grounded=verdict.grounded,
        score=verdict.grounding_score,
    )
    return verdict
