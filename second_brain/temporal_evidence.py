"""Offline claim/evidence/as-of lifecycle receipts with fail-closed vetoes.

This additive prototype is not wired to retrieval, generation, or deployment.
SHA-256 binds the declared metadata bytes; it does not authenticate an issuer,
verify the referenced content, establish rights, or prove semantic support.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

SCHEMA = "szl.second-brain.temporal-evidence/v1"
TRUTH_LABEL = "UNSIGNED_ADVISORY_ONLY"
CURRENT_CANDIDATE = "CURRENT_CANDIDATE"
WARN_STALE = "WARN_STALE"
EXPLAIN_CONFLICT = "EXPLAIN_CONFLICT"
ABSTAIN = "ABSTAIN"

MAX_EVIDENCE = 256
MAX_LINKS_PER_RECORD = 32
MAX_TOTAL_LINKS = 1024
ADMISSIBLE_RIGHTS = frozenset({"apache-2.0", "mit", "cc-by-4.0", "bsd-3-clause"})

_FIELDS = {
    "evidence_id", "claim_id", "source_handle", "content_sha256",
    "recorded_at", "valid_from", "valid_until", "rights", "supersedes",
    "contradicts", "metadata_sha256",
}
_ID = re.compile(r"(?:claim|evidence|handle):[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
_RIGHTS = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class TemporalEvidenceError(ValueError):
    """The complete candidate ledger is invalid; no partial ledger is built."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _finite_real(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _identifier(value: Any, kind: str) -> bool:
    return (isinstance(value, str) and value.startswith(kind + ":")
            and _ID.fullmatch(value) is not None)


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _declared_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": record["evidence_id"],
        "claim_id": record["claim_id"],
        "source_handle": record["source_handle"],
        "content_sha256": record["content_sha256"],
        "recorded_at": record["recorded_at"],
        "valid_from": record["valid_from"],
        "valid_until": record["valid_until"],
        "rights": record["rights"],
        "supersedes": sorted(record["supersedes"]),
        "contradicts": sorted(record["contradicts"]),
    }


@dataclass(frozen=True)
class _Evidence:
    evidence_id: str
    claim_id: str
    source_handle: str
    content_sha256: str
    recorded_at: int | float
    valid_from: int | float
    valid_until: int | float | None
    rights: str
    supersedes: tuple[str, ...]
    contradicts: tuple[str, ...]
    metadata_sha256: str


def _validate_record(record: Any, verify_metadata_sha256: bool = True) -> _Evidence:
    if not isinstance(record, dict):
        raise TemporalEvidenceError("TEMPORAL_RECORD_TYPE_INVALID")
    if set(record) != _FIELDS:
        raise TemporalEvidenceError("TEMPORAL_RECORD_FIELDS_INVALID")
    if not _identifier(record["evidence_id"], "evidence"):
        raise TemporalEvidenceError("TEMPORAL_EVIDENCE_ID_INVALID")
    if not _identifier(record["claim_id"], "claim"):
        raise TemporalEvidenceError("TEMPORAL_CLAIM_ID_INVALID")
    if not _identifier(record["source_handle"], "handle"):
        raise TemporalEvidenceError("TEMPORAL_SOURCE_HANDLE_INVALID")
    if (not isinstance(record["content_sha256"], str)
            or _SHA256.fullmatch(record["content_sha256"]) is None):
        raise TemporalEvidenceError("TEMPORAL_CONTENT_SHA256_INVALID")
    for field in ("recorded_at", "valid_from"):
        if not _finite_real(record[field]):
            raise TemporalEvidenceError("TEMPORAL_TIMESTAMP_INVALID")
    valid_until = record["valid_until"]
    if valid_until is not None and not _finite_real(valid_until):
        raise TemporalEvidenceError("TEMPORAL_TIMESTAMP_INVALID")
    if valid_until is not None and not record["valid_from"] < valid_until:
        raise TemporalEvidenceError("TEMPORAL_VALIDITY_INTERVAL_INVALID")
    rights = record["rights"]
    if not isinstance(rights, str) or _RIGHTS.fullmatch(rights) is None:
        raise TemporalEvidenceError("TEMPORAL_RIGHTS_FIELD_INVALID")
    for field in ("supersedes", "contradicts"):
        links = record[field]
        if not isinstance(links, list):
            raise TemporalEvidenceError("TEMPORAL_LINK_LIST_INVALID")
        if len(links) > MAX_LINKS_PER_RECORD:
            raise TemporalEvidenceError("TEMPORAL_LINK_LIMIT_EXCEEDED")
        if any(not _identifier(link, "evidence") for link in links):
            raise TemporalEvidenceError("TEMPORAL_LINK_ID_INVALID")
        if len(set(links)) != len(links):
            raise TemporalEvidenceError("TEMPORAL_DUPLICATE_LINK")
    declared_sha = record["metadata_sha256"]
    if verify_metadata_sha256 and (
            not isinstance(declared_sha, str) or _SHA256.fullmatch(declared_sha) is None):
        raise TemporalEvidenceError("TEMPORAL_METADATA_SHA256_INVALID")
    try:
        computed_sha = _digest(_declared_metadata(record))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise TemporalEvidenceError("TEMPORAL_METADATA_CANONICALIZATION_FAILED") from exc
    if verify_metadata_sha256 and declared_sha != computed_sha:
        raise TemporalEvidenceError("TEMPORAL_METADATA_SHA256_MISMATCH")
    return _Evidence(
        evidence_id=record["evidence_id"], claim_id=record["claim_id"],
        source_handle=record["source_handle"], content_sha256=record["content_sha256"],
        recorded_at=record["recorded_at"], valid_from=record["valid_from"],
        valid_until=valid_until, rights=rights,
        supersedes=tuple(sorted(record["supersedes"])),
        contradicts=tuple(sorted(record["contradicts"])),
        metadata_sha256=declared_sha if verify_metadata_sha256 else computed_sha,
    )


def compute_metadata_sha256(record: dict[str, Any]) -> str:
    """Validate the fixed metadata and compute its digest, with links sorted."""
    if not isinstance(record, dict) or set(record) not in (_FIELDS, _FIELDS - {"metadata_sha256"}):
        raise TemporalEvidenceError("TEMPORAL_RECORD_FIELDS_INVALID")
    candidate = dict(record)
    candidate["metadata_sha256"] = "0" * 64
    return _validate_record(candidate, verify_metadata_sha256=False).metadata_sha256


class TemporalEvidenceLedger:
    """An immutable-by-convention, bounded view over validated metadata records.

    Construction rejects every malformed record or graph. Evaluation never uses
    wall-clock time and returns a new deterministic receipt for explicit inputs.
    """

    def __init__(self, records: list[dict[str, Any]]) -> None:
        if not isinstance(records, list):
            raise TemporalEvidenceError("TEMPORAL_RECORD_LIST_INVALID")
        if len(records) > MAX_EVIDENCE:
            raise TemporalEvidenceError("TEMPORAL_RECORD_LIMIT_EXCEEDED")
        evidence: list[_Evidence] = []
        by_id: dict[str, _Evidence] = {}
        for record in records:
            item = _validate_record(record)
            if item.evidence_id in by_id:
                raise TemporalEvidenceError("TEMPORAL_DUPLICATE_EVIDENCE_ID")
            by_id[item.evidence_id] = item
            evidence.append(item)
        if sum(len(item.supersedes) + len(item.contradicts) for item in evidence) > MAX_TOTAL_LINKS:
            raise TemporalEvidenceError("TEMPORAL_TOTAL_LINK_LIMIT_EXCEEDED")
        for item in evidence:
            for field, links in (("supersedes", item.supersedes),
                                 ("contradicts", item.contradicts)):
                for target in links:
                    if target not in by_id:
                        raise TemporalEvidenceError("TEMPORAL_MISSING_REFERENCE")
                    if target == item.evidence_id:
                        raise TemporalEvidenceError("TEMPORAL_SELF_LINK")
                    if by_id[target].claim_id != item.claim_id:
                        raise TemporalEvidenceError("TEMPORAL_CROSS_CLAIM_LINK")
        self._by_id = by_id
        self._claims: dict[str, tuple[str, ...]] = {}
        for item in evidence:
            self._claims[item.claim_id] = self._claims.get(item.claim_id, ()) + (item.evidence_id,)
        self._claims = {claim: tuple(sorted(ids)) for claim, ids in self._claims.items()}
        self._superseded_by = {item.evidence_id: [] for item in evidence}
        contradictions = {item.evidence_id: set() for item in evidence}
        for item in evidence:
            for old_id in item.supersedes:
                self._superseded_by[old_id].append(item.evidence_id)
            for other_id in item.contradicts:
                contradictions[item.evidence_id].add(other_id)
                contradictions[other_id].add(item.evidence_id)
        self._superseded_by = {
            identity: tuple(sorted(targets))
            for identity, targets in self._superseded_by.items()
        }
        self._contradictions = {
            identity: tuple(sorted(targets)) for identity, targets in contradictions.items()
        }
        self._check_supersession_cycles()
        self.ledger_sha256 = _digest({
            "schema": SCHEMA,
            "evidence_metadata_sha256": [item.metadata_sha256
                                          for item in sorted(evidence, key=lambda value: value.evidence_id)],
        })

    def _check_supersession_cycles(self) -> None:
        colours: dict[str, int] = {}

        def visit(identity: str) -> None:
            if colours.get(identity) == 1:
                raise TemporalEvidenceError("TEMPORAL_SUPERSESSION_CYCLE")
            if colours.get(identity) == 2:
                return
            colours[identity] = 1
            for target in self._by_id[identity].supersedes:
                visit(target)
            colours[identity] = 2

        for identity in sorted(self._by_id):
            visit(identity)

    @staticmethod
    def _recorded_by(item: _Evidence, as_of: int | float) -> bool:
        return item.recorded_at <= as_of

    @staticmethod
    def _interval_current(item: _Evidence, as_of: int | float) -> bool:
        return item.valid_from <= as_of and (item.valid_until is None or as_of < item.valid_until)

    def _superseded_at(self, identity: str, as_of: int | float) -> bool:
        pending = list(self._superseded_by[identity])
        visited: set[str] = set()
        while pending:
            successor_id = pending.pop()
            if successor_id in visited:
                continue
            visited.add(successor_id)
            successor = self._by_id[successor_id]
            if self._recorded_by(successor, as_of) and self._interval_current(successor, as_of):
                return True
            pending.extend(self._superseded_by[successor_id])
        return False

    def _base_receipt(self, claim_id: str | None, as_of: int | float | None) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "claim_id": claim_id,
            "as_of": as_of,
            "state": ABSTAIN,
            "code": None,
            "candidate_evidence_id": None,
            "candidate_metadata_sha256": None,
            "eligible_evidence_ids": [],
            "conflicting_evidence_pairs": [],
            "decisions": [],
            "ledger_sha256": self.ledger_sha256,
            "zero_veto": "ALL_RIGHTS_AND_TEMPORAL_AXES_REQUIRED_PER_EVIDENCE",
            "truth_label": TRUTH_LABEL,
            "signed_provenance": "NOT_ESTABLISHED",
            "grounded_navigation": "NOT_ESTABLISHED",
            "semantic_support": "NOT_EVALUATED",
            "runtime_integration": "NOT_APPLIED",
            "execution_authority": "NONE",
        }

    def _query_refusal(self, claim_id: Any, as_of: Any, code: str) -> dict[str, Any]:
        receipt = self._base_receipt(
            claim_id if _identifier(claim_id, "claim") else None,
            as_of if _finite_real(as_of) else None,
        )
        receipt["code"] = code
        return receipt

    def evaluate(self, claim_id: str, as_of: int | float) -> dict[str, Any]:
        """Evaluate one claim at an explicit time; no result grants authority."""
        if not _finite_real(as_of):
            return self._query_refusal(claim_id, as_of, "TEMPORAL_AS_OF_INVALID")
        if not _identifier(claim_id, "claim"):
            return self._query_refusal(claim_id, as_of, "TEMPORAL_QUERY_CLAIM_ID_INVALID")
        if claim_id not in self._claims:
            return self._query_refusal(claim_id, as_of, "TEMPORAL_UNKNOWN_CLAIM")

        ids = self._claims[claim_id]
        rights = {identity: self._by_id[identity].rights in ADMISSIBLE_RIGHTS for identity in ids}
        recorded = {identity: self._recorded_by(self._by_id[identity], as_of) for identity in ids}
        interval = {identity: self._interval_current(self._by_id[identity], as_of) for identity in ids}
        superseded = {identity: self._superseded_at(identity, as_of) for identity in ids}
        eligible = [identity for identity in ids
                    if rights[identity] and recorded[identity] and interval[identity]
                    and not superseded[identity]]
        eligible_set = set(eligible)
        conflict_pairs = [(left, right) for index, left in enumerate(eligible)
                          for right in eligible[index + 1:]
                          if right in self._contradictions[left]]
        conflict_ids = {identity for pair in conflict_pairs for identity in pair}

        if conflict_pairs:
            state, code, candidate = EXPLAIN_CONFLICT, "TEMPORAL_CONTRADICTORY_CURRENT_EVIDENCE", None
        elif len(eligible) > 1:
            state, code, candidate = ABSTAIN, "TEMPORAL_AMBIGUOUS_CURRENT_EVIDENCE", None
        elif len(eligible) == 1:
            state, code, candidate = CURRENT_CANDIDATE, None, eligible[0]
        else:
            rights_blocked = any(recorded[identity] and interval[identity]
                                 and not superseded[identity] and not rights[identity]
                                 for identity in ids)
            future = any(not recorded[identity]
                         or self._by_id[identity].valid_from > as_of for identity in ids)
            stale = any(recorded[identity] and self._by_id[identity].valid_from <= as_of
                        and not interval[identity] for identity in ids)
            currently_superseded = any(recorded[identity] and interval[identity]
                                       and superseded[identity] for identity in ids)
            if rights_blocked:
                state, code = ABSTAIN, "TEMPORAL_RIGHTS_NOT_ADMISSIBLE"
            elif future:
                state, code = ABSTAIN, "TEMPORAL_FUTURE_EVIDENCE"
            elif stale:
                state, code = WARN_STALE, "TEMPORAL_STALE_ONLY"
            elif currently_superseded:
                state, code = ABSTAIN, "TEMPORAL_SUPERSEDED_NO_CURRENT_SUCCESSOR"
            else:
                state, code = ABSTAIN, "TEMPORAL_NO_CURRENT_EVIDENCE"
            candidate = None

        receipt = self._base_receipt(claim_id, as_of)
        receipt.update({
            "state": state,
            "code": code,
            "candidate_evidence_id": candidate,
            "candidate_metadata_sha256": self._by_id[candidate].metadata_sha256 if candidate else None,
            "eligible_evidence_ids": eligible,
            "conflicting_evidence_pairs": [list(pair) for pair in conflict_pairs],
        })
        decisions = []
        for identity in ids:
            item = self._by_id[identity]
            axes = {
                "metadata_sha256_valid": 1,
                "rights_admissible": int(rights[identity]),
                "recorded_by_as_of": int(recorded[identity]),
                "valid_at_as_of": int(interval[identity]),
                "not_superseded": int(not superseded[identity]),
            }
            if identity in eligible_set:
                if conflict_pairs:
                    item_state = EXPLAIN_CONFLICT if identity in conflict_ids else ABSTAIN
                    item_code = ("TEMPORAL_CONTRADICTORY_CURRENT_EVIDENCE"
                                 if identity in conflict_ids else "TEMPORAL_CONFLICT_BLOCKS_CLAIM")
                elif len(eligible) > 1:
                    item_state, item_code = ABSTAIN, "TEMPORAL_AMBIGUOUS_CURRENT_EVIDENCE"
                else:
                    item_state, item_code = CURRENT_CANDIDATE, None
            elif not recorded[identity]:
                item_state, item_code = ABSTAIN, "TEMPORAL_FUTURE_OBSERVATION"
            elif item.valid_from > as_of:
                item_state, item_code = ABSTAIN, "TEMPORAL_FUTURE_VALIDITY"
            elif not interval[identity]:
                item_state, item_code = WARN_STALE, "TEMPORAL_STALE_AT_AS_OF"
            elif superseded[identity]:
                item_state, item_code = ABSTAIN, "TEMPORAL_SUPERSEDED_AT_AS_OF"
            else:
                item_state, item_code = ABSTAIN, "TEMPORAL_RIGHTS_NOT_ADMISSIBLE"
            decisions.append({
                "evidence_id": identity,
                "metadata_sha256": item.metadata_sha256,
                "state": item_state,
                "code": item_code,
                "axes": axes,
                "zero_veto_pass": int(all(axes.values())),
                "vetoed_by": [name for name, passed in axes.items() if not passed],
                "current_conflicts": [other for other in self._contradictions[identity]
                                      if other in eligible_set],
            })
        receipt["decisions"] = decisions
        return receipt


__all__ = [
    "ABSTAIN", "ADMISSIBLE_RIGHTS", "CURRENT_CANDIDATE", "EXPLAIN_CONFLICT",
    "MAX_EVIDENCE", "MAX_LINKS_PER_RECORD", "MAX_TOTAL_LINKS", "SCHEMA",
    "TRUTH_LABEL", "WARN_STALE", "TemporalEvidenceError", "TemporalEvidenceLedger",
    "compute_metadata_sha256",
]
