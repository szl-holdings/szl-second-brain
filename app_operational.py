# SPDX-License-Identifier: Apache-2.0
"""Operational Second Brain app: governed retrieval plus review-gated learning.

The public deployment intentionally configures no opaque dense provider. It
therefore reports ``BM25_ONLY`` until a controller injects a revision-pinned,
qualified dense provider. Content hydration remains a library-only controller
operation and is never exposed as an HTTP route. Continuous frontier learning
means content-addressed public-source candidates proposed for review; it never
means silent weight updates, automatic truth promotion, or autonomous execution.
"""
from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from app import app
from second_brain import __version__
from second_brain.frontier import (
    FrontierBoundaryError,
    anatomy_feed as build_anatomy_feed,
    frontier_search,
    frontier_status,
)
from second_brain.hybrid import RetrievalBoundaryError, hybrid_context

app.version = __version__
app.description = (
    "Governed handles-only retrieval with review-gated continuous frontier memory. "
    "Public runtime is honest BM25 fallback; hybrid dense/reranker providers are "
    "injectable and must be qualified."
)


@app.get("/api/v1/retrieval-capabilities")
def retrieval_capabilities() -> dict[str, Any]:
    frontier = frontier_status()
    return {
        "schema": "szl.second-brain.retrieval-capabilities/v2",
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
        "frontier_memory": {
            "ready": frontier.get("ready", False),
            "state": frontier.get("state", "UNAVAILABLE"),
            "candidate_count": frontier.get("candidate_count", 0),
            "content_access": "HANDLES_ONLY",
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
        },
        "private_graph_present": False,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "lambda": "CONJECTURE_1",
        "honesty": (
            "A mode is reported only when its provider actually participates. "
            "Similarity and rank are never represented as correctness. Frontier "
            "candidates remain review-required until a separate human-governed process acts."
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


@app.get("/api/v1/frontier-status")
def frontier_status_route() -> JSONResponse:
    """Expose exact source/digest state without exposing candidate content."""

    return JSONResponse(frontier_status())


@app.get("/api/v1/frontier-handles")
def frontier_handles_route(
    q: str = Query("", alias="q", max_length=2000),
    k: int = Query(12, ge=1, le=24),
) -> JSONResponse:
    """Search review candidates while preserving the public handles-only boundary."""

    try:
        payload = frontier_search(q, k=k)
    except FrontierBoundaryError as exc:
        return JSONResponse(
            {
                "schema": "szl.second-brain.frontier-search/v1",
                "state": "BLOCKED",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "handles": [],
                "scores": [],
                "reason": type(exc).__name__,
                "training_authority": "NONE",
                "promotion_authority": "NONE",
                "execution_authority": "NONE",
            },
            status_code=422,
        )
    return JSONResponse(payload)


@app.get("/api/v1/anatomy-feed")
def anatomy_feed_route(
    k: int = Query(24, ge=1, le=24),
) -> JSONResponse:
    """Return a read-only Brain/formula/quant/Ouroboros feed for Living Anatomy."""

    try:
        payload = build_anatomy_feed(k=k)
    except FrontierBoundaryError as exc:
        return JSONResponse(
            {
                "schema": "szl.second-brain.anatomy-feed/v1",
                "state": "BLOCKED",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "handles": [],
                "scores": [],
                "reason": type(exc).__name__,
                "purpose": "READ_ONLY_LIVING_ANATOMY_OBSERVATION",
                "execution_authority": "NONE",
            },
            status_code=422,
        )
    return JSONResponse(payload)
