"""LangGraph investigation pipeline definition."""

import uuid
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from ai_incident_commander.agents.investigation import (
    block_investigation,
    collect_evidence,
    route_after_evals,
    run_evals,
    surface_rca,
    synthesize_rca,
)
from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.models.investigation import InvestigationState


def build_investigation_graph(settings: Settings | None = None) -> StateGraph:
    """
    Build the LangGraph investigation pipeline.

    Args:
        settings: Optional settings passed to LLM-backed nodes.

    Returns:
        Compiled LangGraph runnable.
    """
    resolved = settings or get_settings()

    async def synthesize_rca_node(state: InvestigationState) -> InvestigationState:
        """Wrapper binding settings into the synthesize node."""
        return await synthesize_rca(state, settings=resolved)

    graph = StateGraph(InvestigationState)
    graph.add_node("collect_evidence", collect_evidence)
    graph.add_node("synthesize_rca", synthesize_rca_node)
    graph.add_node("run_evals", run_evals)
    graph.add_node("surface_rca", surface_rca)
    graph.add_node("block", block_investigation)

    graph.add_edge(START, "collect_evidence")
    graph.add_conditional_edges(
        "collect_evidence",
        _route_after_collect,
        {
            "continue": "synthesize_rca",
            "error": END,
        },
    )
    graph.add_edge("synthesize_rca", "run_evals")
    graph.add_conditional_edges(
        "run_evals",
        route_after_evals,
        {
            "block": "block",
            "surface_rca": "surface_rca",
        },
    )
    graph.add_edge("surface_rca", END)
    graph.add_edge("block", END)

    return graph.compile()


def _route_after_collect(state: InvestigationState) -> str:
    """
    Stop the graph early when evidence collection failed.

    Args:
        state: State returned from ``collect_evidence``.

    Returns:
        ``continue`` or ``error`` edge name.
    """
    if state.get("status") == "error":
        return "error"
    return "continue"


@lru_cache
def get_investigation_graph():
    """
    Return a cached compiled investigation graph using default settings.

    Returns:
        Compiled LangGraph runnable.
    """
    return build_investigation_graph(get_settings())


async def run_investigation(
    service: str,
    description: str,
    settings: Settings | None = None,
) -> InvestigationState:
    """
    Execute the full investigation pipeline for a service incident.

    Args:
        service: Affected service name.
        description: Free-text incident description.
        settings: Optional settings override for graph construction.

    Returns:
        Final investigation state after graph completion.
    """
    graph = (
        build_investigation_graph(settings)
        if settings is not None
        else get_investigation_graph()
    )

    initial_state: InvestigationState = {
        "investigation_id": str(uuid.uuid4()),
        "service": service,
        "description": description,
        "evidence": None,
        "rca": None,
        "eval_result": None,
        "status": "pending",
        "block_reason": None,
        "error_message": None,
    }

    result = await graph.ainvoke(initial_state)
    return result
