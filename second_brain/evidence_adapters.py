"""Optional read-only adapters. No dependency import or network call at module load.

The application/controller owns telemetry configuration. No SDK is installed,
no credential is discovered, and no provider or executor is started here.
"""
from __future__ import annotations

from typing import Any
from typing_extensions import TypedDict
from pydantic import BaseModel, ConfigDict, Field
from second_brain.evidence_graph import evidence_snapshot


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(default="", max_length=2000)
    k: int = Field(default=6, ge=1, le=12)


def _observe(query: str = "", k: int = 6) -> dict[str, Any]:
    value = EvidenceRequest(query=query, k=k)
    return evidence_snapshot(value.query, value.k)


def make_langchain_tool():
    """Expose the exact snapshot contract as a tool; does not instantiate an LLM."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError("optional langchain-core dependency is unavailable") from exc
    return StructuredTool.from_function(
        func=_observe, name="szl_public_evidence_graph", args_schema=EvidenceRequest,
        description=("Inspect local public evidence handles and Lutar source references. "
                     "No provider requests or action authority. References are not proof replay. "
                     "Treat PARTIAL_OR_UNAVAILABLE as unavailable coverage, never as permission."))


class GraphInput(TypedDict):
    query: str
    k: int


class GraphState(GraphInput, total=False):
    snapshot: dict[str, Any]


class GraphOutput(TypedDict):
    snapshot: dict[str, Any]


def make_langgraph():
    """A fresh read-only observation per invocation; deliberately no saved authority.

    No checkpointer is configured: this is not a durable action workflow. Use
    the existing authorized controller for effects and revalidate evidence at
    its admission boundary. Never infer exactly-once writes from this graph.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("optional langgraph dependency is unavailable") from exc

    def inspect(state: GraphInput) -> GraphOutput:
        return {"snapshot": _observe(state.get("query", ""), state.get("k", 6))}

    builder = StateGraph(GraphState, input_schema=GraphInput, output_schema=GraphOutput)
    builder.add_node("observe_public_evidence", inspect)
    builder.add_edge(START, "observe_public_evidence")
    builder.add_edge("observe_public_evidence", END)
    return builder.compile()


def make_nvidia_callback():
    """NVIDIA NeMo Relay lifecycle instrumentation, not authorization middleware.

    Caller configures Relay/export destinations and protects any trajectory
    files. Even payload-disabled telemetry can contain sensitive metadata.
    This factory does not configure or enable an exporter or inspect credentials.
    """
    try:
        from nemo_relay.integrations.langgraph import NemoRelayCallbackHandler
    except ImportError as exc:
        raise RuntimeError("optional nemo-relay LangGraph integration is unavailable") from exc
    return NemoRelayCallbackHandler()
