# SPDX-License-Identifier: Apache-2.0
"""Governed memory for Alloy Refinement Fabric receipts.

Only compact, public failure/repair statistics are admitted. Hidden reasoning,
raw prompts, raw completions, private graph material, and provider credentials
are rejected recursively. The public API exposes handles and digests, never the
underlying task or model transcript.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

RECEIPT_SCHEMA = "szl.refinement.receipt/v1"
STATE_SCHEMA = "szl.second-brain.refinement-memory/v1"
HANDLE_SCHEMA = "szl.second-brain.refinement-pattern-handle/v1"
ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "raw_prompt",
        "system_prompt",
        "raw_completion",
        "transcript",
        "credential",
        "credentials",
        "token",
        "secret",
        "private_graph",
    }
)


class RefinementMemoryBoundaryError(ValueError):
    """A receipt or public projection violated the memory covenant."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RefinementMemoryBoundaryError("value is not strict JSON") from exc


def sha256_hex(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def _scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().casefold()
            if normalized in FORBIDDEN_KEYS:
                raise RefinementMemoryBoundaryError(
                    f"forbidden private field at {path}.{key}"
                )
            _scan_forbidden(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_forbidden(item, f"{path}[{index}]")


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(receipt)
    _scan_forbidden(payload)
    if payload.get("schema") != RECEIPT_SCHEMA:
        raise RefinementMemoryBoundaryError("unsupported receipt schema")
    digest = str(payload.get("receipt_sha256") or "")
    if not HEX_64.fullmatch(digest):
        raise RefinementMemoryBoundaryError("receipt digest is missing")
    body = dict(payload)
    body.pop("receipt_sha256", None)
    if sha256_hex(canonical_bytes(body)) != digest:
        raise RefinementMemoryBoundaryError("receipt digest mismatch")
    privacy = payload.get("privacy")
    if not isinstance(privacy, Mapping):
        raise RefinementMemoryBoundaryError("receipt privacy boundary is missing")
    required_privacy = {
        "hidden_chain_of_thought_requested": False,
        "hidden_chain_of_thought_persisted": False,
        "raw_prompts_persisted": False,
        "public_verifiable_steps_only": True,
    }
    for key, expected in required_privacy.items():
        if privacy.get(key) is not expected:
            raise RefinementMemoryBoundaryError(
                f"receipt privacy boundary mismatch: {key}"
            )
    authority = payload.get("authority")
    if not isinstance(authority, Mapping):
        raise RefinementMemoryBoundaryError("receipt authority boundary is missing")
    for key in ("execution", "training", "promotion", "merge"):
        if authority.get(key) != "NONE":
            raise RefinementMemoryBoundaryError(
                f"receipt carries forbidden {key} authority"
            )
    branches = payload.get("branches")
    if not isinstance(branches, list) or not branches:
        raise RefinementMemoryBoundaryError("receipt branches are missing")
    return payload


@dataclass
class _Accumulator:
    error_code: str
    pair_sha256: str
    attempts: int = 0
    verified: int = 0
    regressions: int = 0
    confidence_sum: float = 0.0
    confidence_count: int = 0

    def add_finding(self, finding: Mapping[str, Any]) -> None:
        value = finding.get("confidence", 0.0)
        if type(value) not in (int, float):
            raise RefinementMemoryBoundaryError("finding confidence is invalid")
        if not 0.0 <= value <= 1.0:
            raise RefinementMemoryBoundaryError("finding confidence is invalid")
        confidence = float(value)
        if not math.isfinite(confidence):
            raise RefinementMemoryBoundaryError("finding confidence is invalid")
        self.confidence_sum += confidence
        self.confidence_count += 1

    def handle(self) -> dict[str, Any]:
        attempts = self.attempts
        verified_rate = self.verified / attempts if attempts else 0.0
        regression_rate = self.regressions / attempts if attempts else 0.0
        confidence = (
            self.confidence_sum / self.confidence_count
            if self.confidence_count
            else 0.0
        )
        identity = sha256_hex(
            canonical_bytes(
                {
                    "error_code": self.error_code,
                    "pair_sha256": self.pair_sha256,
                }
            )
        )
        return {
            "schema": HANDLE_SCHEMA,
            "id": f"refinement:{identity[:32]}",
            "sha256": identity,
            "error_code": self.error_code,
            "model_pair_sha256": self.pair_sha256,
            "repair_attempts": attempts,
            "verified_repairs": self.verified,
            "verified_repair_rate": verified_rate,
            "regression_rate": regression_rate,
            "mean_audit_confidence": confidence,
            "content_access": "HANDLES_ONLY",
            "candidate_state": "REVIEW_REQUIRED",
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
        }


class RefinementMemoryIndex:
    """In-memory aggregate of validated refinement receipts."""

    def __init__(self, receipts: Iterable[Mapping[str, Any]] = ()) -> None:
        self._receipts: set[str] = set()
        self._patterns: dict[tuple[str, str], _Accumulator] = {}
        for receipt in receipts:
            self.ingest(receipt)

    @staticmethod
    def _pair_digest(receipt: Mapping[str, Any]) -> str:
        pair = receipt.get("model_pair")
        if not isinstance(pair, Mapping):
            raise RefinementMemoryBoundaryError("model pair is missing")
        return sha256_hex(canonical_bytes(pair))

    def ingest(self, receipt: Mapping[str, Any]) -> bool:
        payload = validate_receipt(receipt)
        receipt_digest = str(payload["receipt_sha256"])
        if receipt_digest in self._receipts:
            return False
        pair_digest = self._pair_digest(payload)
        # Work on independent accumulators: rejecting any later branch must not
        # publish a partial receipt or modify previously admitted statistics.
        pending = {key: replace(value) for key, value in self._patterns.items()}
        for branch in payload["branches"]:
            if not isinstance(branch, Mapping):
                raise RefinementMemoryBoundaryError("branch receipt is invalid")
            findings = branch.get("findings")
            patches = branch.get("patches")
            guard = branch.get("regression_guard")
            if not isinstance(findings, list) or not isinstance(patches, list):
                raise RefinementMemoryBoundaryError(
                    "branch findings or patches are invalid"
                )
            if not isinstance(guard, Mapping):
                raise RefinementMemoryBoundaryError("regression guard is invalid")
            regressions = guard.get("changed_unflagged_step_count", 0)
            if type(regressions) is not int or regressions < 0:
                raise RefinementMemoryBoundaryError("regression count is invalid")
            findings_by_code: dict[str, list[Mapping[str, Any]]] = {}
            for finding in findings:
                if not isinstance(finding, Mapping):
                    raise RefinementMemoryBoundaryError("finding is invalid")
                code = str(finding.get("error_code") or "").upper()
                if code == "NONE":
                    continue
                if not ERROR_CODE.fullmatch(code):
                    raise RefinementMemoryBoundaryError("finding error code is invalid")
                # Validate even findings that have no matching patch.
                _Accumulator(code, pair_digest).add_finding(finding)
                findings_by_code.setdefault(code, []).append(finding)
            for patch in patches:
                if not isinstance(patch, Mapping):
                    raise RefinementMemoryBoundaryError("patch is invalid")
                code = str(patch.get("error_code") or "").upper()
                if not ERROR_CODE.fullmatch(code):
                    raise RefinementMemoryBoundaryError("patch error code is invalid")
                key = (code, pair_digest)
                verified = patch.get("verified")
                if type(verified) is not bool:
                    raise RefinementMemoryBoundaryError("patch verified must be boolean")
                accumulator = pending.setdefault(key, _Accumulator(code, pair_digest))
                accumulator.attempts += 1
                accumulator.verified += int(verified)
                # A rate measures attempts with regressions, rather than the
                # number of changed steps per attempt.
                accumulator.regressions += int(regressions > 0)
                for finding in findings_by_code.get(code, ()):
                    accumulator.add_finding(finding)
        self._patterns = pending
        self._receipts.add(receipt_digest)
        return True

    def public_status(self) -> dict[str, Any]:
        handles = self.handles()
        state = "REVIEW_REQUIRED" if handles else "EMPTY_REVIEW_REQUIRED"
        body = {
            "schema": STATE_SCHEMA,
            "state": state,
            "ready": True,
            "receipt_count": len(self._receipts),
            "pattern_count": len(handles),
            "handles": handles,
            "content_access": "HANDLES_ONLY",
            "private_graph_present": False,
            "raw_reasoning_present": False,
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
            "merge_authority": "NONE",
        }
        body["state_sha256"] = sha256_hex(canonical_bytes(body))
        return body

    def handles(
        self, *, error_code: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if not 1 <= int(limit) <= 200:
            raise RefinementMemoryBoundaryError("limit must be in [1, 200]")
        normalized = None
        if error_code is not None:
            normalized = str(error_code).strip().upper()
            if not ERROR_CODE.fullmatch(normalized):
                raise RefinementMemoryBoundaryError("error_code filter is invalid")
        rows = [
            accumulator.handle()
            for (code, _), accumulator in self._patterns.items()
            if normalized is None or code == normalized
        ]
        rows.sort(
            key=lambda item: (
                -item["repair_attempts"],
                item["error_code"],
                item["model_pair_sha256"],
            )
        )
        return rows[:limit]


STATE_FIELDS = frozenset({
    "schema", "state", "ready", "receipt_count", "pattern_count", "handles",
    "content_access", "private_graph_present", "raw_reasoning_present",
    "training_authority", "promotion_authority", "execution_authority",
    "merge_authority", "state_sha256",
})
HANDLE_FIELDS = frozenset({
    "schema", "id", "sha256", "error_code", "model_pair_sha256", "repair_attempts",
    "verified_repairs", "verified_repair_rate", "regression_rate",
    "mean_audit_confidence", "content_access", "candidate_state",
    "training_authority", "promotion_authority", "execution_authority",
})


def _nonnegative_integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise RefinementMemoryBoundaryError(f"{field} must be a nonnegative integer")
    return value


def _public_handle(handle: Any) -> None:
    if not isinstance(handle, dict) or set(handle) != HANDLE_FIELDS:
        raise RefinementMemoryBoundaryError("public handle fields are invalid")
    if handle["schema"] != HANDLE_SCHEMA:
        raise RefinementMemoryBoundaryError("public handle schema is invalid")
    code = handle["error_code"]
    pair = handle["model_pair_sha256"]
    if not isinstance(code, str) or not ERROR_CODE.fullmatch(code):
        raise RefinementMemoryBoundaryError("public handle error code is invalid")
    if not isinstance(pair, str) or not HEX_64.fullmatch(pair):
        raise RefinementMemoryBoundaryError("public handle model pair is invalid")
    identity = sha256_hex(canonical_bytes({"error_code": code, "pair_sha256": pair}))
    if handle["sha256"] != identity or handle["id"] != f"refinement:{identity[:32]}":
        raise RefinementMemoryBoundaryError("public handle identity is invalid")
    attempts = _nonnegative_integer(handle["repair_attempts"], "repair_attempts")
    verified = _nonnegative_integer(handle["verified_repairs"], "verified_repairs")
    if attempts < 1 or verified > attempts:
        raise RefinementMemoryBoundaryError("public handle repair counts are invalid")
    for field in ("verified_repair_rate", "regression_rate", "mean_audit_confidence"):
        value = handle[field]
        if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
            raise RefinementMemoryBoundaryError(f"public handle {field} is invalid")
    if handle["verified_repair_rate"] != verified / attempts:
        raise RefinementMemoryBoundaryError("public handle verified rate is inconsistent")
    if handle["content_access"] != "HANDLES_ONLY" or handle["candidate_state"] != "REVIEW_REQUIRED":
        raise RefinementMemoryBoundaryError("public handle boundary is invalid")
    for field in ("training_authority", "promotion_authority", "execution_authority"):
        if handle[field] != "NONE":
            raise RefinementMemoryBoundaryError("public handle authority is invalid")


def load_public_state(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
        raise RefinementMemoryBoundaryError("public refinement state is invalid")
    _scan_forbidden(payload)
    expected = payload.get("state_sha256")
    if not isinstance(expected, str) or not HEX_64.fullmatch(expected):
        raise RefinementMemoryBoundaryError("public state digest is missing")
    body = dict(payload)
    body.pop("state_sha256", None)
    if sha256_hex(canonical_bytes(body)) != expected:
        raise RefinementMemoryBoundaryError("public state digest mismatch")
    # A digest proves byte consistency, not permission to expose arbitrary text.
    # Strict allowlists cover both top-level fields and every handle returned.
    if set(payload) != STATE_FIELDS:
        raise RefinementMemoryBoundaryError("public state fields are invalid")
    if payload["ready"] is not True or payload["content_access"] != "HANDLES_ONLY":
        raise RefinementMemoryBoundaryError("public content boundary drifted")
    if payload["private_graph_present"] is not False:
        raise RefinementMemoryBoundaryError("private graph entered public state")
    if payload["raw_reasoning_present"] is not False:
        raise RefinementMemoryBoundaryError("raw reasoning entered public state")
    for field in ("training_authority", "promotion_authority", "execution_authority", "merge_authority"):
        if payload[field] != "NONE":
            raise RefinementMemoryBoundaryError("public state authority is invalid")
    receipts = _nonnegative_integer(payload["receipt_count"], "receipt_count")
    patterns = _nonnegative_integer(payload["pattern_count"], "pattern_count")
    handles = payload["handles"]
    if not isinstance(handles, list) or patterns != len(handles) or len(handles) > 200:
        raise RefinementMemoryBoundaryError("public state handle count is invalid")
    state = "REVIEW_REQUIRED" if handles else "EMPTY_REVIEW_REQUIRED"
    if payload["state"] != state or (handles and receipts < 1):
        raise RefinementMemoryBoundaryError("public state counts or state are inconsistent")
    identities: set[str] = set()
    for handle in handles:
        _public_handle(handle)
        if handle["id"] in identities:
            raise RefinementMemoryBoundaryError("public state contains duplicate handles")
        identities.add(handle["id"])
    return payload
