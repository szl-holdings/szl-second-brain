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
from dataclasses import dataclass
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
        confidence = float(finding.get("confidence", 0.0))
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
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
            regressions = (
                int(guard.get("changed_unflagged_step_count", 0))
                if isinstance(guard, Mapping)
                else 0
            )
            findings_by_code: dict[str, list[Mapping[str, Any]]] = {}
            for finding in findings:
                if not isinstance(finding, Mapping):
                    raise RefinementMemoryBoundaryError("finding is invalid")
                code = str(finding.get("error_code") or "").upper()
                if code == "NONE":
                    continue
                if not ERROR_CODE.fullmatch(code):
                    raise RefinementMemoryBoundaryError("finding error code is invalid")
                findings_by_code.setdefault(code, []).append(finding)
            for patch in patches:
                if not isinstance(patch, Mapping):
                    raise RefinementMemoryBoundaryError("patch is invalid")
                code = str(patch.get("error_code") or "").upper()
                if not ERROR_CODE.fullmatch(code):
                    raise RefinementMemoryBoundaryError("patch error code is invalid")
                key = (code, pair_digest)
                accumulator = self._patterns.setdefault(
                    key, _Accumulator(code, pair_digest)
                )
                accumulator.attempts += 1
                accumulator.verified += int(bool(patch.get("verified")))
                accumulator.regressions += regressions
                for finding in findings_by_code.get(code, ()):
                    accumulator.add_finding(finding)
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


def load_public_state(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
        raise RefinementMemoryBoundaryError("public refinement state is invalid")
    _scan_forbidden(payload)
    expected = str(payload.get("state_sha256") or "")
    if not HEX_64.fullmatch(expected):
        raise RefinementMemoryBoundaryError("public state digest is missing")
    body = dict(payload)
    body.pop("state_sha256", None)
    if sha256_hex(canonical_bytes(body)) != expected:
        raise RefinementMemoryBoundaryError("public state digest mismatch")
    if payload.get("content_access") != "HANDLES_ONLY":
        raise RefinementMemoryBoundaryError("public content boundary drifted")
    if payload.get("private_graph_present") is not False:
        raise RefinementMemoryBoundaryError("private graph entered public state")
    if payload.get("raw_reasoning_present") is not False:
        raise RefinementMemoryBoundaryError("raw reasoning entered public state")
    return payload
