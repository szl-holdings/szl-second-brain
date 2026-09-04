# SPDX-License-Identifier: Apache-2.0
"""Operational Second Brain app: legacy routes plus governed hybrid retrieval.

The public deployment intentionally configures no opaque dense provider. It
therefore reports ``BM25_ONLY`` until a controller injects a revision-pinned,
qualified dense provider. Content hydration remains a library-only controller
operation and is never exposed as an HTTP route.
"""
from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from app import app
from second_brain import __version__
from second_brain.hybrid import RetrievalBoundaryError, hybrid_context

app.version = __version__
app.description = (
    "Governed handles-only retrieval. Public runtime is honest BM25 fallback; "
    "hybrid dense/reranker providers are injectable and must be qualified."
)


@app.get("/api/v1/retrieval-capabilities")
def retrieval_capabilities() -> dict[str, Any]:
    return {
        "schema": "szl.second-brain.retrieval-capabilities/v1",
        "version": __version__,
        "public_content_access": "HANDLES_ONLY",
        "controller_hydration": "AUTHORIZED_LIBRARY_ONLY",
        "available_modes": [
            "BM25_ONLY",
            "HYBRID_SPARSE_DENSE",
            "HYBRID_SPARSE_DENSE+RERANKER",
        ],
        "public_runtime_mode": "BM25_ONLY",
        "dense_provider": "NOT_CONFIGURED",
        "reranker": "NOT_CONFIGURED",
        "private_graph_present": False,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "lambda": "CONJECTURE_1",
        "honesty": (
            "A mode is reported only when its provider actually participates. "
            "Similarity and rank are never represented as correctness."
        ),
    }


@app.get("/api/v1/hybrid")
def hybrid_get(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(6, ge=1, le=12),
) -> JSONResponse:
    try:
        payload = hybrid_context(q, k=k)
    except RetrievalBoundaryError as exc:
        return JSONResponse(
            {
                "schema": "szl.second-brain.hybrid-context/v1",
                "state": "BLOCKED",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "reason": type(exc).__name__,
            },
            status_code=422,
        )
    return JSONResponse(payload)


@app.post("/api/v1/hybrid")
async def hybrid_post(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "JSON object required", "state": "UNAVAILABLE"},
            status_code=400,
        )
    query = str(body.get("query") or body.get("q") or "").strip()[:2000]
    try:
        k = max(1, min(int(body.get("k", 6)), 12))
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "k must be an integer", "state": "UNAVAILABLE"},
            status_code=400,
        )
    try:
        payload = hybrid_context(query, k=k)
    except RetrievalBoundaryError as exc:
        return JSONResponse(
            {
                "schema": "szl.second-brain.hybrid-context/v1",
                "state": "BLOCKED",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "reason": type(exc).__name__,
            },
            status_code=422,
        )
    return JSONResponse(payload)
