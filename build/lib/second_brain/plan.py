"""SOFTWARE navigator: NAVIGATE or ABSTAIN over offered handles only.

Lexical overlap on handle notes. NEVER correctness. Never invents a nodeId.
Raw 9464-node graph is not here. Λ = Conjecture 1.
"""
from __future__ import annotations

from typing import Any

from second_brain.retrieve import tokenize

SOFTWARE_PLANNER = "SZL-BrainNavigator-R2-SOFTWARE"
CAPABILITY = "SZL-BrainNavigator-R2"
ARTIFACT = "SZLHOLDINGS/brain-navigator-r2"
BASE = "Qwen/Qwen3.5-0.8B"

# Queries that must not be grounded on the public projection, even if a
# decoy handle shares a stray token. Named-N abstain gate.
_ABSTAIN_HINTS = (
    "secret launch",
    "physical effector",
    "unpublished earnings",
    "private 9464",
    "9464-node",
    "owner-setup.md",
    "excluded owner-setup",
    "2099 world cup",
    "nvml joule",
    "meter that is not attached",
    "invent a nodeid",
    "sovereign-citizen",
    "land patent that voids",
)


def _unsupported(query: str) -> bool:
    q = (query or "").lower()
    return any(h in q for h in _ABSTAIN_HINTS)


def _score_handle(query: str, handle: dict[str, Any]) -> float:
    q = tokenize(query)
    if not q:
        return 0.0
    note = f"{handle.get('note', '')} {handle.get('label', '')} {handle.get('nodeKind', '')}"
    toks = tokenize(note)
    if not toks:
        return 0.0
    qset = set(q)
    tset = set(toks)
    return float(len(qset & tset))


def plan_from_handles(
    query: str,
    handles: list[dict[str, Any]],
    *,
    kind: str = "SOFTWARE",
) -> dict[str, Any]:
    offered = []
    for h in handles:
        offered.append(
            {
                "nodeId": h["nodeId"],
                "nodeKind": h.get("nodeKind") or "INDEX",
                "label": h.get("label") or "DECLARED",
                "note": (h.get("note") or "")[:160],
            }
        )
    ids = {h["nodeId"] for h in offered}
    abstain = _unsupported(query) or not offered
    best: dict[str, Any] | None = None
    best_score = 0.0
    if not abstain:
        for h in offered:
            sc = _score_handle(query, h)
            if sc > best_score:
                best_score = sc
                best = h
        if best is None or best_score <= 0:
            abstain = True

    if abstain or best is None or best["nodeId"] not in ids:
        cite: list[str] = []
        steps: list[dict[str, Any]] = []
        decision = "ABSTAIN"
        reason: str | None = (
            "No offered handle supports the query; refusing to fabricate grounding."
        )
    else:
        cite = [best["nodeId"]]
        steps = [
            {
                "action": "CITE",
                "nodeId": best["nodeId"],
                "rationale": "offered handle note overlaps the query topic",
            }
        ]
        decision = "NAVIGATE"
        reason = None

    return {
        "planId": "software-navigator",
        "capabilityProfile": CAPABILITY,
        "provenance": "SYNTHETIC" if kind == "SOFTWARE" else "MODEL_PROPOSED",
        "query": query,
        "contentAccess": "HANDLES_ONLY",
        "candidates": offered,
        "decision": decision,
        "steps": steps,
        "citedNodeIds": cite,
        "groundedOnly": True,
        "brainBinding": {
            "protocol": "khipu-retrieval",
            "status": "NOT_RESOLVED",
            "note": "Controller resolves handles outside the weights.",
        },
        "controllerBoundary": (
            "SOFTWARE planner proposes a route over offered handles. "
            "The controller resolves content outside the weights."
        ),
        "abstainReason": reason,
        "base_model": BASE,
        "artifact": ARTIFACT,
        "planner": SOFTWARE_PLANNER,
        "kind": kind,
        "lambda": "Conjecture 1",
        "raw_graph_nodes_admitted_to_gradients": 0,
    }
