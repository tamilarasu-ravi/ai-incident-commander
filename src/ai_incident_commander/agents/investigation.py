"""LangGraph node implementations for the investigation pipeline."""

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.constants import EVIDENCE_COVERAGE_THRESHOLD
from ai_incident_commander.fixtures.mock_evidence import get_stub_eval_result
from ai_incident_commander.integrations.collector import collect_live_evidence
from ai_incident_commander.llm.adapter import synthesize_rca_hypothesis
from ai_incident_commander.models.investigation import InvestigationState


async def collect_evidence(
    state: InvestigationState,
    settings: Settings | None = None,
) -> InvestigationState:
    """
    Collect evidence from GitHub, Datadog, Jira, and Slack RTS in parallel.

    Deployments remain fixture-backed until a deployment source is added.

    Args:
        state: Current investigation state with ``service`` and ``description`` set.
        settings: Optional settings override for integration credentials.

    Returns:
        Updated state with ``evidence`` populated or ``error`` status on failure.
    """
    service = state["service"]
    description = state["description"]
    resolved = settings or get_settings()

    try:
        evidence = await collect_live_evidence(
            service=service,
            description=description,
            settings=resolved,
        )
    except ValueError as error:
        return {
            **state,
            "status": "error",
            "error_message": str(error),
        }

    return {
        **state,
        "evidence": evidence,
        "status": "collecting",
    }


async def synthesize_rca(state: InvestigationState, settings: Settings | None = None) -> InvestigationState:
    """
    Synthesize an RCA hypothesis from collected evidence via the LLM.

    Args:
        state: Current investigation state with ``evidence`` populated.
        settings: Optional settings override for LLM configuration.

    Returns:
        Updated state with ``rca`` populated.

    Raises:
        ValueError: If evidence is missing from state.
    """
    evidence = state.get("evidence")
    if evidence is None:
        raise ValueError("collect_evidence must run before synthesize_rca")

    resolved = settings or get_settings()
    rca = await synthesize_rca_hypothesis(
        evidence=evidence,
        service=state["service"],
        description=state["description"],
        settings=resolved,
    )

    return {
        **state,
        "rca": rca,
        "status": "synthesizing",
    }


async def run_evals(state: InvestigationState) -> InvestigationState:
    """
    Apply stub evaluation scores for Day 2 (full eval engine on Day 5).

    Args:
        state: Current investigation state with ``rca`` populated.

    Returns:
        Updated state with ``eval_result`` and routing metadata.

    Raises:
        ValueError: If RCA is missing from state.
    """
    if state.get("rca") is None:
        raise ValueError("synthesize_rca must run before run_evals")

    stub_eval = get_stub_eval_result(state["service"])
    if stub_eval is None:
        return {
            **state,
            "status": "error",
            "error_message": f"No stub eval fixture for service '{state['service']}'.",
        }

    blocked = stub_eval.evidence_coverage < EVIDENCE_COVERAGE_THRESHOLD
    block_reason = ""
    if blocked:
        block_reason = (
            f"Evidence coverage {stub_eval.evidence_coverage:.0%} is below "
            f"{EVIDENCE_COVERAGE_THRESHOLD:.0%} threshold."
        )

    eval_result = stub_eval.model_copy(
        update={"blocked": blocked, "block_reason": block_reason},
    )

    return {
        **state,
        "eval_result": eval_result,
        "status": "evaluating",
        "block_reason": block_reason if blocked else None,
    }


def route_after_evals(state: InvestigationState) -> str:
    """
    Route to block or surface based on stub eval outcome.

    Args:
        state: Investigation state after ``run_evals``.

    Returns:
        Graph edge name ``block`` or ``surface_rca``.
    """
    eval_result = state.get("eval_result")
    if eval_result is None or eval_result.blocked:
        return "block"
    return "surface_rca"


async def surface_rca(state: InvestigationState) -> InvestigationState:
    """
    Mark investigation as ready for Slack surfacing.

    Args:
        state: Investigation state that passed evaluation.

    Returns:
        Updated state with ``status`` set to ``surfaced``.
    """
    return {
        **state,
        "status": "surfaced",
    }


async def block_investigation(state: InvestigationState) -> InvestigationState:
    """
    Mark investigation as blocked from human approval.

    Args:
        state: Investigation state that failed evaluation.

    Returns:
        Updated state with ``status`` set to ``blocked``.
    """
    eval_result = state.get("eval_result")
    reason = state.get("block_reason") or (
        eval_result.block_reason if eval_result else "Investigation blocked."
    )
    return {
        **state,
        "status": "blocked",
        "block_reason": reason,
    }
