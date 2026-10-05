# SPDX-License-Identifier: Apache-2.0
"""Operational Second Brain app with handles-only refinement memory.

The existing retrieval/frontier application remains authoritative. This module
adds one read-only route over a content-addressed public aggregate of Alloy
Refinement Fabric receipts. It does not accept receipt writes, hydrate tasks,
return public-step content, invoke models, train, promote, or execute actions.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse

from app_operational import app
from second_brain._data import data_dir
from second_brain.refinement_memory import (
    RefinementMemoryBoundaryError,
    load_public_state,
)

ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def _state_path() -> Path:
    return data_dir() / "refinement-patterns.public.json"


def _unavailable(reason: str) -> JSONResponse:
    return JSONResponse(
        {
            "schema": "szl.second-brain.refinement-memory-response/v1",
            "state": "UNAVAILABLE",
            "ready": False,
            "reason": reason,
            "handles": [],
            "content_access": "HANDLES_ONLY",
            "private_graph_present": False,
            "raw_reasoning_present": False,
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
            "merge_authority": "NONE",
        },
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/refinement-memory")
def refinement_memory_route(
    error_code: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    """Return aggregate repair-pattern handles; never return task or trace text."""

    try:
        state = load_public_state(_state_path())
    except FileNotFoundError:
        return _unavailable("REFINEMENT_MEMORY_NOT_MATERIALIZED")
    except (OSError, ValueError, RefinementMemoryBoundaryError) as exc:
        return _unavailable(type(exc).__name__)

    normalized: str | None = None
    if error_code is not None and error_code.strip():
        normalized = error_code.strip().upper()
        if not ERROR_CODE.fullmatch(normalized):
            return JSONResponse(
                {
                    "schema": "szl.second-brain.refinement-memory-response/v1",
                    "state": "BLOCKED",
                    "ready": False,
                    "reason": "INVALID_ERROR_CODE",
                    "handles": [],
                    "content_access": "HANDLES_ONLY",
                },
                status_code=422,
                headers={"Cache-Control": "no-store"},
            )

    handles = state.get("handles")
    if not isinstance(handles, list):
        return _unavailable("REFINEMENT_MEMORY_HANDLES_INVALID")
    filtered: list[dict[str, Any]] = []
    for handle in handles:
        if not isinstance(handle, dict):
            return _unavailable("REFINEMENT_MEMORY_HANDLE_INVALID")
        if normalized is not None and handle.get("error_code") != normalized:
            continue
        filtered.append(handle)
        if len(filtered) >= limit:
            break

    payload = {
        "schema": "szl.second-brain.refinement-memory-response/v1",
        "state": state["state"],
        "ready": True,
        "state_sha256": state["state_sha256"],
        "receipt_count": state["receipt_count"],
        "pattern_count": state["pattern_count"],
        "returned_count": len(filtered),
        "handles": filtered,
        "content_access": "HANDLES_ONLY",
        "private_graph_present": False,
        "raw_reasoning_present": False,
        "training_authority": "NONE",
        "promotion_authority": "NONE",
        "execution_authority": "NONE",
        "merge_authority": "NONE",
        "honesty": (
            "Observed repair patterns are diagnostics, not proof that a future "
            "answer is correct and not authority to train, promote, or execute."
        ),
    }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})
