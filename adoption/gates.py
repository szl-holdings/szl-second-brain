"""Source-pinned adoption gates (propose-only).

Doctrine (leader-study, #102 read-only; BEIR leader arXiv:2104.08663
studied, not executed): no claim enters the second brain without a
source pin. A pin carries an https URL, a retrieved timestamp, a
window, a content digest, and a claim from the module-supported
allowlist. Verdict precedence is deterministic:
malformed pin or expected digest -> unsupported claim -> digest
mismatch -> staleness -> ADMITTED. Stale pins are UNKNOWN, never
admitted; the ten-pass ledger requires ten recorded ADMITTED
evaluations bound to the SAME source identity and content digest
before adoption - no pass is ever guessed, and failed or cross-source
evaluations cannot be recorded as passes. Freshness boundary exact:
fresh iff 0 <= evaluation_ts - retrieved_ts <= window_s; evaluation
timestamps EARLIER than retrieved_ts are malformed-rejected. All
timestamps and digests are injected; no wall-clock reads, no network.

Honest limitation, verbatim: this is a local, in-process evaluation
model over injected pins; it does not fetch, rank, or evaluate real
retrieval corpora (BEIR or otherwise) and an ADMITTED verdict is
structural admission only, not a measured retrieval-quality result.

Propose-only, unsigned; merges are owned by the estate signature wall.
No status claims are made about any other pull request.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from typing import Dict

SCHEMA_VERSION = "szl.adoption.gates/v1"
BANNER = "PROPOSAL_ONLY_UNSIGNED"

HEX64 = re.compile(r"^[0-9a-f]{64}$")

ADMITTED = "ADMITTED"
STALE_UNKNOWN = "STALE_UNKNOWN"
DIGEST_MISMATCH_REJECTED = "DIGEST_MISMATCH_REJECTED"
UNSUPPORTED_CLAIM_REJECTED = "UNSUPPORTED_CLAIM_REJECTED"
MALFORMED_REJECTED = "MALFORMED_REJECTED"

SUPPORTED_CLAIM_KINDS = ("leader-attribution", "adoption-recommendation",
                         "metric-reading")


class PinError(ValueError):
    """A source pin or pass record is malformed or forbidden."""


@dataclass
class SourcePin:
    url: str
    retrieved_ts: float
    window_s: float
    content_digest: str
    claim: str
    claim_kind: str
    claim_supported: bool

    def __post_init__(self):
        if not (isinstance(self.url, str) and self.url.startswith("https://") and len(self.url) > 8):
            raise PinError("url must be an https:// source")
        if not isinstance(self.retrieved_ts, (int, float)) or self.retrieved_ts < 0:
            raise PinError("retrieved_ts must be a non-negative number")
        if not self.window_s or self.window_s <= 0:
            raise PinError("window_s must be positive")
        if not (isinstance(self.content_digest, str) and HEX64.match(self.content_digest)):
            raise PinError("content_digest must be 64-char lowercase hex sha256")
        if not self.claim or not isinstance(self.claim, str):
            raise PinError("claim must be a non-empty string")
        if self.claim_kind not in SUPPORTED_CLAIM_KINDS:
            raise PinError("claim_kind must be one of %r" % (SUPPORTED_CLAIM_KINDS,))

    @property
    def source_identity(self) -> str:
        return self.url


@dataclass
class GateVerdict:
    outcome: str
    claim: str
    reason: str
    source_identity: str = ""
    pin_digest: str = ""
    evaluated_ts: float = -1.0

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "claim": self.claim,
                "source_identity": self.source_identity,
                "pin_digest": self.pin_digest,
                "evaluated_ts": self.evaluated_ts}


class Gate:
    """Deterministic fail-closed admission of pinned claims."""

    def evaluate(self, pin, now_ts: float, expected_digest) -> GateVerdict:
        # 1. malformed first (pin shape + expected digest shape)
        if not isinstance(pin, SourcePin) or not isinstance(now_ts, (int, float)):
            return self._v(pin, MALFORMED_REJECTED, "not a SourcePin / malformed evaluation_ts", now_ts)
        if not (isinstance(expected_digest, str) and HEX64.match(expected_digest)):
            return self._v(pin, MALFORMED_REJECTED,
                           "expected_digest must be 64-char lowercase hex sha256", now_ts)
        if now_ts < pin.retrieved_ts:
            return self._v(pin, MALFORMED_REJECTED,
                           "evaluation_ts earlier than retrieved_ts (future pin)", now_ts)
        # 2. unsupported claims (even stale ones are unsupported, not relabeled)
        if not pin.claim_supported:
            return self._v(pin, UNSUPPORTED_CLAIM_REJECTED,
                           "claim not supported by the pinned source", now_ts)
        # 3. digest mismatch (constant-time after strict 64-hex validation)
        if not hmac.compare_digest(pin.content_digest, expected_digest):
            return self._v(pin, DIGEST_MISMATCH_REJECTED,
                           "pin content_digest != expected_digest", now_ts)
        # 4. staleness, exact boundary: fresh iff 0 <= delta <= window_s
        if now_ts - pin.retrieved_ts > pin.window_s:
            return self._v(pin, STALE_UNKNOWN,
                           "pin stale for its window; re-pin required (UNKNOWN, never green)", now_ts)
        # 5. only valid + fresh + digest-matching + supported -> ADMITTED
        return self._v(pin, ADMITTED,
                       "structurally admitted: pinned, in-window, digest-matching, "
                       "supported; not a quality result", now_ts)

    def _v(self, pin, outcome, reason, now_ts) -> GateVerdict:
        if isinstance(pin, SourcePin):
            return GateVerdict(outcome, pin.claim, reason,
                               pin.source_identity, pin.content_digest, float(now_ts))
        return GateVerdict(outcome, "", reason, "", "", float(now_ts))


class TenPassLedger:
    """Ten recorded ADMITTED passes, same source identity + digest, before
    adoption; honest in-progress otherwise; failed evaluations can never
    be recorded as passes."""

    REQUIRED = 10

    def __init__(self, source_identity: str, content_digest: str):
        if not source_identity:
            raise PinError("source_identity must be non-empty")
        if not (isinstance(content_digest, str) and HEX64.match(content_digest)):
            raise PinError("content_digest must be 64-char lowercase hex sha256")
        self._source = source_identity
        self._digest = content_digest
        self._passes: Dict[int, bool] = {}

    def record_pass(self, pass_no, verdict):
        if not isinstance(pass_no, int) or isinstance(pass_no, bool)                 or pass_no < 1 or pass_no > self.REQUIRED:
            raise PinError("pass_no must be an integer in 1..10")
        if pass_no in self._passes:
            raise PinError("pass %d already recorded; no duplicates" % pass_no)
        if not isinstance(verdict, GateVerdict):
            raise PinError("record_pass requires a GateVerdict")
        if verdict.outcome != ADMITTED:
            raise PinError("only ADMITTED evaluations can be recorded as passes; got "
                           + verdict.outcome)
        if verdict.source_identity != self._source or verdict.pin_digest != self._digest:
            raise PinError("cross-source pass rejected: ledger is bound to one source identity and digest")
        self._passes[pass_no] = True

    def verdict(self) -> Dict[str, object]:
        recorded = len(self._passes)
        if recorded == self.REQUIRED:
            return {"schema_version": SCHEMA_VERSION, "banner": BANNER,
                    "outcome": "ALL_TEN_PASSES", "source_identity": self._source,
                    "passes_recorded": recorded}
        missing = sorted([n for n in range(1, self.REQUIRED + 1) if n not in self._passes])
        return {"schema_version": SCHEMA_VERSION, "banner": BANNER,
                "outcome": "IN_PROGRESS_HONEST", "source_identity": self._source,
                "passes_recorded": recorded, "missing_passes": missing,
                "note": "adoption requires all ten recorded ADMITTED passes; never guessed"}
