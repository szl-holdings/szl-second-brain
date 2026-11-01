# SPDX-License-Identifier: Apache-2.0
"""SZL Second Brain holographic FastAPI Space.

GET /hologram 0-CDN chamber. GET /retrieve and /plan (POST aliases under /api/v1).
SOFTWARE navigator over the public 575-chunk projection.
Λ = Conjecture 1. Never overwrites SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from second_brain.plan import plan_from_handles
from second_brain.retrieve import index, navigator_context, rag_status, retrieve
from second_brain.web_contracts import PlanRequest, QueryRequest

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
if not STATIC.is_dir():
    STATIC = ROOT / "static"
CHAMBER = STATIC / "index.html"
RECEIPT = ROOT / "train" / "training_receipt.json"
EVAL = ROOT / "train" / "eval_report.json"

router = APIRouter()


def _retrieve_payload(q: str, k: int) -> dict[str, Any]:
    hit = retrieve(q, k=k)
    for handle in hit.get("handles") or []:
        if isinstance(handle, dict):
            handle.pop("text", None)
            handle.pop("_toks", None)
            handle.pop("_tf", None)
    return hit


def _plan_payload(
    q: str, k: int, handles: list[dict[str, Any]] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    hit = _retrieve_payload(q, k)
    offered = hit.get("handles") or []
    if handles is not None:
        # Client handles may select only exact records from this retrieval.
        # Never turn an arbitrary client node/note into a grounded citation.
        by_id = {h["nodeId"]: h for h in offered}
        seen: set[str] = set()
        for handle in handles:
            node_id = handle.get("nodeId")
            if (not isinstance(node_id, str) or node_id in seen
                    or node_id not in by_id or handle != by_id[node_id]):
                raise HTTPException(422, "handles must match the current retrieval")
            seen.add(node_id)
        offered = [by_id[h["nodeId"]] for h in handles]
    planned = plan_from_handles(q, offered if hit.get("ready") else [])
    planned["schema"] = "szl.second-brain.plan/v1"
    planned["retrieve_ready"] = bool(hit.get("ready"))
    planned["corpus_n"] = hit.get("corpus_n")
    if not hit.get("ready"):
        planned["honesty"] = hit.get("honesty") or "UNAVAILABLE"
        planned["last"] = "UNAVAILABLE"
    else:
        planned["honesty"] = (
            "SOFTWARE lexical planner over offered handles. Never LIVE weights. "
            "Score is overlap, never correctness. Controller resolves content."
        )
    return planned, hit


def _graph(q: str, hit: dict[str, Any], planned: dict[str, Any]) -> dict[str, Any]:
    cited = set(planned.get("citedNodeIds") or [])
    handles = hit.get("handles") or []
    scores = hit.get("scores") or []
    return {
        "nodes": [{"id": "query", "kind": "QUERY", "label": (q or "")[:80]}]
        + [
            {
                "id": h["nodeId"],
                "kind": "HANDLE",
                "label": h.get("note") or h["nodeId"],
                "cited": h["nodeId"] in cited,
            }
            for h in handles
            if isinstance(h, dict) and h.get("nodeId")
        ],
        "edges": [
            {
                "from": "query",
                "to": h["nodeId"],
                "score": scores[i] if i < len(scores) else 0,
            }
            for i, h in enumerate(handles)
            if isinstance(h, dict) and h.get("nodeId")
        ],
    }


@router.get("/hologram", response_class=HTMLResponse)
def home() -> HTMLResponse:
    page = CHAMBER if CHAMBER.is_file() else STATIC / "chamber.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))


@router.get("/health")
def health() -> dict[str, Any]:
    st = rag_status()
    return {
        "ok": bool(st.get("built")),
        "product": "SZL Second Brain",
        "kind": "SOFTWARE",
        "lambda": "CONJECTURE_1",
        "chunk_count": st.get("chunk_count", 0),
        "corpus_n": st.get("chunk_count", 0),
        "index_is_model_weights": False,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "sku": "SZLHOLDINGS/brain-navigator-r2",
        "does_not_overwrite": "SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator",
        "publication_eligible": False,
        "honesty": st.get("honesty"),
    }


@router.get("/api/v1/index")
def index_stats() -> dict[str, Any]:
    return index().stats()


@router.get("/api/v1/status")
def status_route() -> dict[str, Any]:
    return rag_status()


@router.get("/api/v1/manifest")
def manifest() -> dict[str, Any]:
    return {
        "schema": "szl.second-brain.manifest/v1",
        "product": "SZL Second Brain",
        "space": "https://huggingface.co/spaces/SZLHOLDINGS/second-brain",
        "github": "https://github.com/szl-holdings/szl-second-brain",
        "sku": "SZLHOLDINGS/brain-navigator-r2",
        "kind": "SOFTWARE",
        "canvas": "0-CDN",
        "lambda": "Conjecture 1",
        "contentAccess": "HANDLES_ONLY",
        "brainBinding": "NOT_RESOLVED",
        "publication_eligible": False,
        "routes": ["/", "/hologram", "/api/v1/query", "/retrieve", "/plan",
                   "/api/v1/retrieve", "/api/v1/plan", "/api/v1/hybrid",
                   "/api/v1/frontier-handles", "/api/v1/refinement-memory"],
    }


@router.get("/api/v1/retrieve")
@router.get("/retrieve")
def retrieve_get(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    return JSONResponse(_retrieve_payload(q, k))


@router.post("/api/v1/retrieve")
def retrieve_post(body: QueryRequest) -> JSONResponse:
    q, k = body.query, body.k
    if not q:
        return JSONResponse({"error": "query is required", "label": "UNAVAILABLE"}, status_code=400)
    return JSONResponse(_retrieve_payload(q, k))


@router.get("/api/v1/plan")
@router.get("/plan")
def plan_get(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    planned, _hit = _plan_payload(q, k)
    return JSONResponse(planned)


@router.post("/api/v1/plan")
def plan_post(body: PlanRequest) -> JSONResponse:
    q, k = body.query, body.k
    if not q:
        return JSONResponse({"error": "query is required", "label": "UNAVAILABLE"}, status_code=400)
    planned, hit = _plan_payload(q, k, body.handles)
    return JSONResponse(
        {
            "schema": "szl.second-brain.plan/v1",
            "retrieve": hit,
            "plan": planned,
            "graph": _graph(q, hit, planned),
        }
    )


@router.get("/api/v1/navigator")
def navigator_route(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    return JSONResponse(navigator_context(q, k=k))


@router.get("/api/v1/receipt")
def receipt() -> JSONResponse:
    if not RECEIPT.is_file():
        return JSONResponse(
            {"label": "UNAVAILABLE", "reason": "training_receipt.json not present"},
            status_code=200,
        )
    return JSONResponse(json.loads(RECEIPT.read_text(encoding="utf-8")))


@router.get("/api/v1/eval")
def eval_report() -> JSONResponse:
    if not EVAL.is_file():
        return JSONResponse(
            {"label": "UNAVAILABLE", "reason": "eval_report.json not present"},
            status_code=200,
        )
    return JSONResponse(json.loads(EVAL.read_text(encoding="utf-8")))
