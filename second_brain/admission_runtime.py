#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Explicit opt-in HIRAG admission for the served hybrid routes.

Off unless SECOND_BRAIN_HIRAG_ADMISSION is exactly "1". Off, the served routes
use the unchanged library coordinator and their payloads are identical to it;
the reason the gate did not run is reported on /api/v1/retrieval-capabilities
and /readyz. On, the gate is built only from the committed metadata sidecar
bound to the active corpus generation. A missing, malformed, stale or
mismatched sidecar BLOCKS gated retrieval instead of serving an ungated fallback.

Nothing is synthesized here: absent licences stay unknown (refused), and the
clock is read once per query and recorded beside the decisions. Decisions are
computed over declared inputs; they are not measurements.

The library contract (second_brain.admission) asks for a controller-measured
ingestion time. No such observation exists for the shipped corpus, so this
opt-in substitutes the committer time of the commit that landed the corpus
bytes (REPOSITORY_ADMISSION_COMMIT_TIME). That substitute is NOT ratified: it
needs an owner decision and every configuration block says so. It is an upper
bound on when the projection was built, so it can only overstate freshness.
"""
from __future__ import annotations

import contextvars
import copy
import hashlib
import os
import re
import threading
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from second_brain._data import data_file
from second_brain.admission import (
    RANK_DERIVED_RELEVANCE,
    UNKNOWN_LICENSE,
    CorpusAdmission,
    CorpusAdmissionError,
)
from second_brain.corpus import CorpusIntegrityError, load_corpus, strict_json
from second_brain.hirag import ADMISSIBLE_LICENSES, DEFAULT_WEIGHTS, TIE_EPS
from second_brain.hybrid import HybridSecondBrain, RetrievalBoundaryError, hybrid_index
from second_brain.retrieve import SecondBrainIndex, index

OPT_IN_ENV = "SECOND_BRAIN_HIRAG_ADMISSION"
METADATA_FILE = "corpus-admission-metadata.v1.json"
METADATA_SCHEMA = "szl.second-brain.corpus-admission-metadata/v1"
SCHEMA = "szl.second-brain.admission-runtime/v1"
INGESTED_AT_KINDS = frozenset({"REPOSITORY_ADMISSION_COMMIT_TIME"})
SIGNATURE_STATES = frozenset({"NOT_VERIFIED"})
LICENSE_POLICIES = frozenset({"ABSENT_IS_UNKNOWN"})
MIN_UNIX_S = 1_000_000_000  # rejects small/garbage values; millisecond stamps are caught as future
TAU = 0.5
FRESHNESS_WINDOW_S = 30 * 24 * 3600
DECISION_LABEL = "COMPUTED_OVER_DECLARED_INPUTS"
OWNER_RATIFICATION = "REQUIRES_OWNER_DECISION"
GATED_ROUTES = ("/", "/api/v1/query", "/api/v1/hybrid", "/api/v1/evidence-graph", "/evidence")
UNGATED_ROUTES = ("/retrieve", "/api/v1/retrieve", "/plan", "/api/v1/plan", "/api/v1/navigator",
                  "/api/v1/frontier-handles", "/api/v1/anatomy-feed")
NOT_GATED_WITHIN_GATED_ROUTES = ("FRONTIER_REVIEW_CANDIDATE_HANDLES", "LUTAR_REFERENCE_HANDLES")
_METADATA_KEYS = frozenset({"schema", "corpus_file", "corpus_sha256", "row_count", "ingested_at",
                            "licenses", "license_policy", "license_basis"})
_STAMP_KEYS = frozenset({"unix_s", "utc", "kind", "granularity", "source_commit",
                         "signature_verification", "basis"})
_LICENSE_KEYS = frozenset({"license", "basis", "declared_by"})
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The admission run of the current query, visible to served_hybrid_context in the
# same thread/context only; requests never share it.
_RUN: contextvars.ContextVar[tuple[float, dict[str, Any]] | None] = contextvars.ContextVar(
    "second_brain_hirag_admission_run", default=None)


class AdmissionBlocked(Exception):
    """The operator asked for the gate but it cannot be built from committed data."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ServedCorpusAdmission(CorpusAdmission):
    """Reads the clock once per selection and keeps the full run for the receipt."""

    def admit_selection(self, selected: Sequence[str], now: float | None = None) -> dict[str, Any]:
        evaluated_at = time.time() if now is None else now
        run = super().admit_selection(selected, now=evaluated_at)
        _RUN.set((evaluated_at, run))
        return run


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _one_of(value: Any, allowed: frozenset[str]) -> bool:
    # Type first: a JSON list or object is unhashable and must read as invalid, not raise.
    return isinstance(value, str) and value in allowed


def _utc(unix_s: int) -> str:
    return datetime.fromtimestamp(unix_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _block(opt_in: str, state: str, reason: str | None, **extra: Any) -> dict[str, Any]:
    # Route disclosure in every state: where the gate filters, where a requested but
    # unbuildable gate refuses, and where it is never consulted.
    return {"schema": SCHEMA, "opt_in_env": OPT_IN_ENV, "opt_in": opt_in, "state": state,
            "reason": reason, "scope": "CONFIGURATION_ONLY",
            "participation_evidence": "QUERY_RANKING_RECEIPT_ADMISSION_FIELD",
            "gated_routes": list(GATED_ROUTES) if state == "CONFIGURED" else [],
            "blocked_routes": list(GATED_ROUTES) if state == "BLOCKED" else [],
            "ungated_routes": list(UNGATED_ROUTES) if state != "NOT_APPLIED" else list(GATED_ROUTES + UNGATED_ROUTES),
            "gate_scope": "BRAIN_CORPUS_HANDLES_ONLY",
            "not_gated_within_gated_routes": list(NOT_GATED_WITHIN_GATED_ROUTES),
            "owner_ratification": OWNER_RATIFICATION,
            "lambda": "CONJECTURE_1", "lambda_status": "ADVISORY", **extra}


def _metadata(raw: bytes, generation_sha256: str, corpus_ids: set[str]) -> dict[str, Any]:
    try:
        value = strict_json(raw)
    except CorpusIntegrityError as exc:
        raise AdmissionBlocked("METADATA_INVALID") from exc
    if not isinstance(value, dict) or set(value) != _METADATA_KEYS or value["schema"] != METADATA_SCHEMA:
        raise AdmissionBlocked("METADATA_INVALID")
    if value["corpus_sha256"] != generation_sha256:
        raise AdmissionBlocked("METADATA_GENERATION_MISMATCH")
    stamp, licenses = value["ingested_at"], value["licenses"]
    if (not _nonblank(value["corpus_file"]) or type(value["row_count"]) is not int
            or value["row_count"] != len(corpus_ids) or not _one_of(value["license_policy"], LICENSE_POLICIES)
            or not _nonblank(value["license_basis"])
            or not isinstance(stamp, dict) or set(stamp) != _STAMP_KEYS or not isinstance(licenses, dict)):
        raise AdmissionBlocked("METADATA_INVALID")
    unix_s = stamp["unix_s"]
    if (type(unix_s) is not int or unix_s < MIN_UNIX_S or not _one_of(stamp["kind"], INGESTED_AT_KINDS)
            or stamp["granularity"] != "WHOLE_CORPUS"
            or not _one_of(stamp["signature_verification"], SIGNATURE_STATES) or not _nonblank(stamp["basis"])
            or not isinstance(stamp["source_commit"], str) or not _COMMIT.fullmatch(stamp["source_commit"])):
        raise AdmissionBlocked("METADATA_INVALID")
    if unix_s > time.time():  # a future or millisecond stamp would clamp freshness to 1.0
        raise AdmissionBlocked("METADATA_INGESTED_AT_IN_FUTURE")
    if stamp["utc"] != _utc(unix_s):
        raise AdmissionBlocked("METADATA_INVALID")
    for node_id, declaration in licenses.items():
        if (node_id not in corpus_ids or not isinstance(declaration, dict) or set(declaration) != _LICENSE_KEYS
                or not all(_nonblank(declaration[key]) for key in _LICENSE_KEYS)
                # "unknown" is the absence of a declaration; it is expressed by omission, never declared.
                or declaration["license"].strip().casefold() == UNKNOWN_LICENSE):
            raise AdmissionBlocked("METADATA_INVALID")
    return value


def build_runtime(brain: SecondBrainIndex, metadata_path: Path) -> tuple[HybridSecondBrain, dict[str, Any]]:
    """Build the gated coordinator from committed data only, or raise AdmissionBlocked."""
    view = brain.snapshot()
    if not view.built or not isinstance(view.generation_sha256, str) or not _HEX64.fullmatch(view.generation_sha256):
        raise AdmissionBlocked("CORPUS_UNAVAILABLE")
    try:
        corpus = load_corpus(view.path, view.generation_sha256)
    except (OSError, CorpusIntegrityError) as exc:
        raise AdmissionBlocked("CORPUS_UNAVAILABLE") from exc
    ids = {row.node_id for row in corpus.rows}
    try:
        raw = Path(metadata_path).read_bytes()
    except OSError as exc:
        raise AdmissionBlocked("METADATA_UNAVAILABLE") from exc
    value = _metadata(raw, view.generation_sha256, ids)
    stamp, licenses = value["ingested_at"], value["licenses"]
    node_metadata = {node_id: ({"ingested_at": stamp["unix_s"], "license": licenses[node_id]["license"]}
                               if node_id in licenses else {"ingested_at": stamp["unix_s"]})
                     for node_id in ids}
    weights = dict(DEFAULT_WEIGHTS)
    try:
        gate = _ServedCorpusAdmission(corpus, generation_sha256=view.generation_sha256,
                                      node_metadata=node_metadata, tau=TAU, weights=weights,
                                      freshness_window_s=FRESHNESS_WINDOW_S)
    except CorpusAdmissionError as exc:
        raise AdmissionBlocked("ADMISSION_CONFIG_REJECTED") from exc
    admissible = sum(1 for d in licenses.values() if d["license"].lower() in ADMISSIBLE_LICENSES)
    window_ends = stamp["unix_s"] + FRESHNESS_WINDOW_S
    block = _block("ENABLED", "CONFIGURED", None,
                   corpus_generation_sha256=view.generation_sha256, corpus_row_count=len(ids),
                   metadata_file=Path(metadata_path).name, metadata_sha256=hashlib.sha256(raw).hexdigest(),
                   ingested_at={**{key: stamp[key] for key in
                                   ("unix_s", "utc", "kind", "granularity", "source_commit", "signature_verification")},
                                "substitutes_for": "CONTROLLER_RECORDED_INGESTION_TIME",
                                "ratification": OWNER_RATIFICATION,
                                "bound": "UPPER_BOUND_ON_PROJECTION_BUILD_TIME",
                                "freshness_bias": "CAN_ONLY_OVERSTATE_FRESHNESS",
                                "freshness_window_ends_unix_s": window_ends,
                                "freshness_window_ends_utc": _utc(window_ends)},
                   declared_license_count=len(licenses), admissible_license_count=admissible,
                   unknown_license_count=len(ids) - len(licenses),
                   policy={"tau": TAU, "weights": weights, "freshness_window_s": FRESHNESS_WINDOW_S,
                           "freshness": "LINEAR_DECAY_FROM_INGESTED_AT", "admissible_licenses": sorted(ADMISSIBLE_LICENSES),
                           "go_rule": "LAMBDA_STRICTLY_ABOVE_TAU", "tie_band": "ABS_LN_LAMBDA_MINUS_LN_TAU_AT_MOST",
                           "tie_band_eps": TIE_EPS, "relevance_measure": RANK_DERIVED_RELEVANCE,
                           "relevance_order": "ADMISSION_DETAIL_OFFERED_RANK_ORDER",
                           "clock": "READ_ONCE_PER_QUERY_RECORDED_AS_EVALUATED_AT_UNIX_S"},
                   decision_label=DECISION_LABEL)
    return HybridSecondBrain(brain, admission=gate), block


_LOCK = threading.Lock()
_STATE: tuple[HybridSecondBrain | None, dict[str, Any]] | None = None


def _runtime() -> tuple[HybridSecondBrain | None, dict[str, Any]]:
    global _STATE
    with _LOCK:
        if _STATE is None:
            # Exact match only: " 1", "true" or "yes" are ambiguous operator intent and BLOCK.
            requested = os.environ.get(OPT_IN_ENV, "")
            if requested in ("", "0"):
                _STATE = (None, _block("NOT_ENABLED", "NOT_APPLIED", "OPT_IN_NOT_ENABLED"))
            elif requested != "1":
                _STATE = (None, _block("INVALID", "BLOCKED", "OPT_IN_VALUE_INVALID"))
            else:
                try:
                    _STATE = build_runtime(index(), data_file(METADATA_FILE))
                except AdmissionBlocked as exc:
                    _STATE = (None, _block("ENABLED", "BLOCKED", exc.reason))
                except Exception as exc:  # noqa: BLE001 - any unforeseen build failure must BLOCK, never 500 or fall back
                    _STATE = (None, _block("ENABLED", "BLOCKED", "ADMISSION_BUILD_ERROR",
                                           error_type=type(exc).__name__))
        return _STATE


def admission_observation() -> dict[str, Any]:
    """Configuration only; per-query participation is ranking_receipt.admission."""
    return copy.deepcopy(_runtime()[1])


def _refusal(receipt: dict[str, Any]) -> dict[str, Any]:
    return {"verdict": receipt["verdict"], "code": receipt["code"], "lambda": receipt["lambda"],
            "zero_axes": sorted(axis for axis, value in receipt["axes"].items() if value == 0.0)}


def served_hybrid_context(query: str, k: int = 6) -> dict[str, Any]:
    coordinator, block = _runtime()
    if block["state"] == "BLOCKED":
        raise RetrievalBoundaryError("HIRAG admission requested but unavailable: " + block["reason"])
    if coordinator is None:
        return hybrid_index().context(query, k=k)
    token = _RUN.set(None)
    try:
        payload = coordinator.context(query, k=k)
        run = _RUN.get()
    except CorpusAdmissionError as exc:
        raise RetrievalBoundaryError("HIRAG admission run rejected") from exc
    finally:
        _RUN.reset(token)
    receipt = payload["ranking_receipt"]
    receipt.setdefault("admission", "NOT_RUN")  # empty query or unbuilt index: the gate had nothing to judge
    detail = receipt.get("admission_detail")
    if run is not None and isinstance(detail, dict):
        evaluated_at, result = run
        # offered_rank_order is a list, so the digest binds the order that relevance (1/rank) was computed over;
        # the decisions/refusals objects are keyed maps whose member order canonical hashing ignores.
        detail.update(evaluated_at_unix_s=evaluated_at, decision_label=DECISION_LABEL, lambda_status="ADVISORY",
                      offered_rank_order=[r["node_id"] for r in result["receipts"]],
                      refusals={r["node_id"]: _refusal(r) for r in result["receipts"] if not r["admitted"]})
    receipt["admission_runtime"] = copy.deepcopy(block)
    return payload


def reset_runtime_admission() -> None:
    global _STATE
    with _LOCK:
        _STATE = None


__all__ = ["AdmissionBlocked", "DECISION_LABEL", "METADATA_FILE", "METADATA_SCHEMA", "OPT_IN_ENV",
           "admission_observation", "build_runtime", "reset_runtime_admission", "served_hybrid_context"]
