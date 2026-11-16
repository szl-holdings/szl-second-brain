"""Read-only, exact-source Lutar claim references and context-only review examples.

This consumer verifies the retained public claim document, not Lean proof terms.
It never maps formula IDs to unrelated runtime implementations, trains a model,
loads the private graph, or promotes a source declaration into execution authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from second_brain._data import data_file

SOURCE_REPOSITORY = "szl-holdings/lutar-lean"
SOURCE_REVISION = "59d6b026b8418f59bd6535d532bdeb7551b398f0"
SOURCE_PATH = "claims/locked-formulas.v1.json"
SOURCE_SHA256 = "5e0358ae4e0ff6345a42e8c2711c675fa4ec2366267205912892e9e46ecf5a6f"
SOURCE_FILE = "lutar-locked-claims.source.v1.json"
LOCKED_IDS = ("F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22")
TRUST_BASE = ("propext", "Classical.choice", "Quot.sound")
MAX_SOURCE_BYTES = 128 * 1024
SCHEMA = "szl.second-brain.lutar-reference/v1"


class LutarReferenceError(ValueError):
    """The pinned source is missing, changed, or outside the admitted contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LutarReferenceError("duplicate source member")
        result[key] = value
    return result


def _load(path: Path | None = None) -> dict[str, Any]:
    source = data_file(SOURCE_FILE) if path is None else path
    try:
        with source.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        raise LutarReferenceError("source unavailable") from exc
    if len(raw) > MAX_SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise LutarReferenceError("source identity mismatch")
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, UnicodeError) as exc:
        raise LutarReferenceError("source document invalid") from exc
    if (not isinstance(value, dict)
            or value.get("schema") != "szl.lutar.locked-formula-claims/v1"
            or value.get("repository") != SOURCE_REPOSITORY
            or value.get("locked_ids") != list(LOCKED_IDS)
            or value.get("carrier_theorem_count") != 24
            or value.get("trust_base") != list(TRUST_BASE)
            or value.get("lean_toolchain") != "leanprover/lean4:v4.35.0"):
        raise LutarReferenceError("source claim boundary changed")
    claims = value.get("claims")
    if not isinstance(claims, list) or len(claims) != len(LOCKED_IDS):
        raise LutarReferenceError("claim inventory incomplete")
    ids = [claim.get("claim_id") for claim in claims if isinstance(claim, dict)]
    if len(ids) != 8 or len(set(ids)) != 8 or set(ids) != set(LOCKED_IDS):
        raise LutarReferenceError("claim identities changed")
    declarations = [name for claim in claims for name in claim["theorem_declarations"]]
    if len(declarations) != 24 or len(set(declarations)) != 24:
        raise LutarReferenceError("carrier identities changed")
    if value["lambda"]["locked_proven"] is not False:
        raise LutarReferenceError("Lambda was promoted")
    return value


def _boundary() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "content_access": "HANDLES_ONLY",
        "verification_scope": "PINNED_SOURCE_BYTES_AND_DECLARED_CLAIM_STRUCTURE",
        "proof_replayed_here": False,
        "semantic_review": "NOT_ESTABLISHED_BY_THIS_CONSUMER",
        "runtime_refinement": "UNVERIFIED",
        "independent_checker": "NOT_RUN",
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION,
        "source_path": SOURCE_PATH,
        "source_sha256": SOURCE_SHA256,
        "source_head_freshness": "NOT_CHECKED_PINNED_SNAPSHOT",
        "training_authority": "NONE", "promotion_authority": "NONE",
        "execution_authority": "NONE", "merge_authority": "NONE",
        "private_graph_present": False,
        "private_graph_nodes_loaded": 0,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "lambda": "CONJECTURE_1_OPEN_FALSE_AS_STATED",
    }


def lutar_reference(*, path: Path | None = None) -> dict[str, Any]:
    """Return handles only. Recheck bytes on every call; do not cache a stale pass."""
    boundary = _boundary()
    try:
        source = _load(path)
    except LutarReferenceError:
        return {**boundary, "state": "UNAVAILABLE", "ready": False,
                "handles": [], "reason": "LUTAR_SOURCE_UNAVAILABLE_OR_CHANGED"}
    claims = {claim["claim_id"]: claim for claim in source["claims"]}
    handles = []
    for claim_id in LOCKED_IDS:
        claim = claims[claim_id]
        handles.append({
            "nodeId": "lutar:" + claim_id + ":" + SOURCE_REVISION,
            "claimId": claim_id, "title": claim["name"],
            "repository": SOURCE_REPOSITORY, "revision": SOURCE_REVISION,
            "path": SOURCE_PATH, "sha256": hashlib.sha256(_canonical(claim)).hexdigest(),
            "sourceSha256": SOURCE_SHA256,
            "declarationNames": ["Puriq.Formula.Proved." + name
                                 for name in claim["theorem_declarations"]],
            "proofModule": source["compiled_import_path"],
            "evidenceState": "SOURCE_DECLARED_LOCKED_NOT_REPLAYED_HERE",
            "refinementState": "UNVERIFIED",
            "contentAccess": "HANDLES_ONLY",
        })
    return {**boundary, "state": "SOURCE_BOUND_REFERENCE", "ready": True,
            "declared_locked_count": len(handles), "declared_carrier_count": 24,
            "handles": handles,
            "handles_sha256": hashlib.sha256(_canonical(handles)).hexdigest()}


def curriculum_candidates(*, path: Path | None = None) -> dict[str, Any]:
    """Offline controller helper: 16 source-attributed context/limits examples.

    Not exposed as HTTP, not added to the 575-chunk corpus or navigator weights.
    These examples quote the source's mathematical scope and refinement limits;
    they are not proof completions or an empirical model-quality evaluation.
    """
    source = _load(path)
    claims = {claim["claim_id"]: claim for claim in source["claims"]}
    rows = []
    for claim_id in LOCKED_IDS:
        claim = claims[claim_id]
        for task, fields in (
            ("identify_formal_scope", ("exact_mathematical_statement", "hypotheses", "supported_input_domain")),
            ("distinguish_runtime_guarantees", ("refinement_gap", "public_wording")),
        ):
            rows.append({
                "id": f"lutar-context:{claim_id}:{task}", "claim_id": claim_id,
                "task": task, "source_repository": SOURCE_REPOSITORY,
                "source_revision": SOURCE_REVISION, "source_sha256": SOURCE_SHA256,
                "claim_sha256": hashlib.sha256(_canonical(claim)).hexdigest(),
                "source_declared_answer": {field: claim[field] for field in fields},
                "role": "STATEMENT_AND_LIMIT_CONTEXT_NOT_PROOF_COMPLETION",
                "review_state": "REVIEW_REQUIRED", "training_authority": "NONE",
            })
    return {"schema": "szl.lutar.context-curriculum-candidate/v1",
            "state": "REVIEW_REQUIRED", "rows": rows, "count": len(rows),
            "content_sha256": hashlib.sha256(_canonical(rows)).hexdigest(),
            "training_authority": "NONE", "proof_completions": 0,
            "private_graph_nodes_loaded": 0, "runtime_refinement": "UNVERIFIED"}
