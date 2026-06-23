"""LLM adapter with OpenAI primary and Google Gemini fallback."""

from pathlib import Path

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.rca import RcaHypothesis

logger = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


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


def build_llm(settings: Settings | None = None) -> BaseChatModel:
    """
    Build the primary LLM with Google Gemini fallback.

    Args:
        settings: Optional settings override; defaults to cached ``get_settings()``.

    Returns:
        LangChain chat model with fallback configured.

    Raises:
        ValueError: If neither OpenAI nor Google API keys are configured.
    """
    resolved = settings or get_settings()
    if not resolved.openai_api_key and not resolved.google_api_key:
        raise ValueError("OPENAI_API_KEY or GOOGLE_API_KEY is required for RCA synthesis")

    models: list[BaseChatModel] = []
    if resolved.openai_api_key:
        models.append(
            ChatOpenAI(
                model=resolved.openai_model,
                api_key=resolved.openai_api_key,
                temperature=0,
            )
        )
    if resolved.google_api_key:
        models.append(
            ChatGoogleGenerativeAI(
                model=resolved.google_model,
                google_api_key=resolved.google_api_key,
                temperature=0,
            )
        )

    primary = models[0]
    if len(models) == 1:
        return primary
    return primary.with_fallbacks(models[1:])


def _format_evidence_for_prompt(evidence: EvidenceBundle) -> str:
    """
    Serialize evidence into a compact JSON string for the LLM user message.

    Args:
        evidence: Collected investigation evidence.

    Returns:
        JSON string representation of the evidence bundle.
    """
    return evidence.model_dump_json(indent=2)


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
    llm = build_llm(settings)
    structured_llm = llm.with_structured_output(RcaHypothesis)
    system_prompt = load_prompt("rca_synthesis.md")
    user_content = (
        f"Service: {service}\n"
        f"Description: {description}\n\n"
        f"Evidence JSON:\n{_format_evidence_for_prompt(evidence)}"
    )

    log = logger.bind(service=service)
    log.info("rca_synthesis_started")

    try:
        result = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]
        )
    except Exception as error:
        log.error("rca_synthesis_failed", error=str(error))
        raise

    if not isinstance(result, RcaHypothesis):
        hypothesis = RcaHypothesis.model_validate(result)
    else:
        hypothesis = result

    log.info("rca_synthesis_completed", root_cause=hypothesis.root_cause_candidate)
    return hypothesis
