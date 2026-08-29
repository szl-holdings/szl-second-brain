# SPDX-License-Identifier: Apache-2.0
"""SZL Second Brain holographic FastAPI Space.

GET / 0-CDN chamber. GET /retrieve and /plan (POST aliases under /api/v1).
SOFTWARE navigator over the public 575-chunk projection.
Λ = Conjecture 1. Never overwrites SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from second_brain.plan import plan_from_handles
from second_brain.retrieve import index, navigator_context, rag_status, retrieve

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CHAMBER = STATIC / "index.html"
RECEIPT = ROOT / "train" / "training_receipt.json"
EVAL = ROOT / "train" / "eval_report.json"

app = FastAPI(
    title="SZL Second Brain",
    version="1.0.0",
    description="SOFTWARE retrieval hologram. Handles only. Λ = Conjecture 1.",
    docs_url=None,
    redoc_url=None,
)


def _clip(text: Any, n: int = 2000) -> str:
    return str(text or "").strip()[:n]


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
    offered = handles if handles is not None else (hit.get("handles") or [])
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


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    page = CHAMBER if CHAMBER.is_file() else STATIC / "chamber.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/health")
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


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    st = rag_status()
    return {
        "ready": bool(st.get("built")),
        "lambda": "CONJECTURE_1",
        "kind": "SOFTWARE",
        "chunk_count": st.get("chunk_count", 0),
    }


@app.get("/api/v1/index")
def index_stats() -> dict[str, Any]:
    return index().stats()


@app.get("/api/v1/status")
def status_route() -> dict[str, Any]:
    return rag_status()


@app.get("/api/v1/manifest")
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
        "routes": ["/retrieve", "/plan", "/api/v1/retrieve", "/api/v1/plan"],
    }


@app.get("/api/v1/retrieve")
@app.get("/retrieve")
def retrieve_get(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    return JSONResponse(_retrieve_payload(q, k))


@app.post("/api/v1/retrieve")
async def retrieve_post(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    q = _clip(body.get("query") or body.get("q") or "")
    k = int(body.get("k") or 6)
    if not q:
        return JSONResponse({"error": "query is required", "label": "UNAVAILABLE"}, status_code=400)
    return JSONResponse(_retrieve_payload(q, max(1, min(k, 12))))


@app.get("/api/v1/plan")
@app.get("/plan")
def plan_get(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    planned, _hit = _plan_payload(q, k)
    return JSONResponse(planned)


@app.post("/api/v1/plan")
async def plan_post(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    q = _clip(body.get("query") or body.get("q") or "")
    k = int(body.get("k") or 6)
    if not q:
        return JSONResponse({"error": "query is required", "label": "UNAVAILABLE"}, status_code=400)
    handles = body.get("handles")
    if handles is not None and not isinstance(handles, list):
        handles = None
    planned, hit = _plan_payload(q, max(1, min(k, 12)), handles)
    return JSONResponse(
        {
            "schema": "szl.second-brain.plan/v1",
            "retrieve": hit,
            "plan": planned,
            "graph": _graph(q, hit, planned),
        }
    )


@app.get("/api/v1/navigator")
def navigator_route(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    return JSONResponse(navigator_context(q, k=k))


@app.get("/api/v1/receipt")
def receipt() -> JSONResponse:
    if not RECEIPT.is_file():
        return JSONResponse(
            {"label": "UNAVAILABLE", "reason": "training_receipt.json not present"},
            status_code=200,
        )
    return JSONResponse(json.loads(RECEIPT.read_text(encoding="utf-8")))


@app.get("/api/v1/eval")
def eval_report() -> JSONResponse:
    if not EVAL.is_file():
        return JSONResponse(
            {"label": "UNAVAILABLE", "reason": "eval_report.json not present"},
            status_code=200,
        )
    return JSONResponse(json.loads(EVAL.read_text(encoding="utf-8")))


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", os.environ.get("SECOND_BRAIN_PORT", "8101")))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
