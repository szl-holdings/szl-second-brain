"""second_brain.hirag — Hierarchical Invariant-Retrieval Admission Graph (core).

Implements the HIRAG specification (docs/HIRAG.md): retrieval admission over a
provenance DAG governed by the szl.lambda/v1 zero-veto gate.

Three components:
  * ProvenanceDAG — nodes carry source receipts; edges are derived-from relations;
    retrieval paths are verifiable evidence chains.
  * AdmissionGate — szl.lambda/v1 weighted geometric mean over measured per-node
    axes (source_receipt_valid, license_admissible, freshness, relevance,
    derivation_integrity) with ZERO_VETO: a failed axis refuses admission
    regardless of relevance rank.
  * HIRAG.retrieve_and_admit — composes hierarchical retrieval with the gate.

Honesty contract:
  * Lambda is ADVISORY; Conjecture 1 is machine-checked false as stated; the gate
    does not depend on uniqueness (Theorem U territory is not invoked).
  * Axis scores are caller-measured inputs; the gate certifies the arithmetic,
    not the truth of the measurements.
  * No quality-improvement claim. The gate is a filter; whether it helps is the
    pre-declared evaluation's question (docs/HIRAG.md), not this module's claim.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA = "szl.hirag/v1"
WEIGHT_SUM_TOL = 1e-12
TIE_EPS = 1e-9

GO, NO_GO, ABSTAIN, BLOCK = "GO", "NO_GO", "ABSTAIN", "BLOCK"
ZERO_VETO, BELOW_TAU, NUMERIC_TIE = "ZERO_VETO", "BELOW_TAU", "NUMERIC_TIE"

AXES = ("source_receipt_valid", "license_admissible", "freshness",
        "relevance", "derivation_integrity")
DEFAULT_WEIGHTS = {a: 1.0 / len(AXES) for a in AXES}


class HiragError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def _is_real(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ── Provenance DAG ───────────────────────────────────────────────────────────

@dataclass
class EvidenceNode:
    node_id: str
    content: str
    receipt_hash: str                      # content+source digest
    source_revision: str                    # e.g. git sha / HF revision
    license: str                            # SPDX id or "UNKNOWN"
    ingested_at: float                      # unix time
    derived_from: list[str] = field(default_factory=list)  # parent node_ids
    level: int = 0                          # hierarchy level (0 = source chunk)

    chain_head_claim: Optional[str] = None  # declared membership head, if any

    def receipt_valid(self, chain_head: Optional[str]) -> bool:
        """Receipt validity. With no chain head this is metadata presence only
        (non-empty hash and revision) - it is NOT chain verification. When a
        chain head is supplied, the node must declare a matching membership
        claim; an absent or mismatched claim fails closed (False)."""
        if not self.receipt_hash or not self.source_revision:
            return False
        if chain_head is None:
            return True
        return (self.chain_head_claim is not None
                and self.chain_head_claim == chain_head)


@dataclass
class ProvenanceDAG:
    nodes: dict[str, EvidenceNode] = field(default_factory=dict)

    def add(self, node: EvidenceNode) -> None:
        if node.node_id in self.nodes:
            raise HiragError("HIRAG_DUPLICATE_NODE", node.node_id)
        if not _is_real(node.ingested_at) or \
                (isinstance(node.ingested_at, float) and not math.isfinite(node.ingested_at)):
            raise HiragError("HIRAG_NONFINITE_TIMESTAMP",
                             f"node {node.node_id} ingested_at must be a finite real")
        for parent in node.derived_from:
            if parent not in self.nodes:
                raise HiragError("HIRAG_UNKNOWN_PARENT", f"{node.node_id} -> {parent}")
        # cycle check (derived-from must be acyclic by construction: parents exist first)
        self.nodes[node.node_id] = node

    def derivation_integrity(self, node_id: str, verify_parent=None) -> float:
        """All-edges veto: 1.0 iff EVERY edge verifies, 0.0 if any fails. A node with no parents is
        a source chunk: integrity is its receipt validity."""
        node = self.nodes[node_id]
        if not node.derived_from:
            return 1.0 if node.receipt_hash else 0.0
        for parent_id in node.derived_from:
            parent = self.nodes[parent_id]
            valid = verify_parent(parent) if verify_parent is not None else bool(parent.receipt_hash)
            if not valid:
                return 0.0
        return 1.0

    def evidence_chain(self, node_id: str) -> list[str]:
        """The derived-from path from a node to its source chunks (DAG order)."""
        chain, stack, seen = [], [node_id], set()
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            chain.append(nid)
            stack.extend(self.nodes[nid].derived_from)
        return chain


# ── Admission gate (szl.lambda/v1 semantics, stdlib) ────────────────────────

def lambda_v1(axes: list[float], weights: list[float]) -> float:
    for name, seq in (("axes", axes), ("weights", weights)):
        if not isinstance(seq, list) or len(seq) == 0:
            raise HiragError("LAMBDA_EMPTY" if name == "axes" else "LAMBDA_TYPE_INVALID")
    if len(axes) != len(weights):
        raise HiragError("LAMBDA_LENGTH_MISMATCH")
    for v in axes + weights:
        if not _is_real(v):
            raise HiragError("LAMBDA_TYPE_INVALID")
    for v in axes:
        if isinstance(v, float) and not math.isfinite(v):
            raise HiragError("LAMBDA_NONFINITE_AXIS")
        if not 0.0 <= v <= 1.0:
            raise HiragError("LAMBDA_AXIS_OUT_OF_RANGE")
    for w in weights:
        if isinstance(w, float) and not math.isfinite(w):
            raise HiragError("LAMBDA_NONFINITE_WEIGHT")
        if w <= 0.0:
            raise HiragError("LAMBDA_WEIGHT_NONPOSITIVE")
    if abs(math.fsum(weights) - 1.0) > WEIGHT_SUM_TOL:
        raise HiragError("LAMBDA_WEIGHT_SUM")
    if any(x == 0.0 for x in axes):
        return 0.0
    return math.exp(math.fsum(w * math.log(x) for x, w in zip(axes, weights)))


def gate_v1(axes: list[float], weights: list[float], tau: float) -> tuple[str, Optional[str]]:
    if not _is_real(tau) or not (0 < tau <= 1):
        return BLOCK, "LAMBDA_TAU_INVALID"
    try:
        lam = lambda_v1(axes, weights)
    except HiragError as e:
        return BLOCK, e.code
    if lam == 0.0:
        return NO_GO, ZERO_VETO
    if abs(math.log(lam) - math.log(tau)) <= TIE_EPS:
        return ABSTAIN, NUMERIC_TIE
    return (GO, None) if math.log(lam) > math.log(tau) else (NO_GO, BELOW_TAU)


# ── HIRAG: hierarchical retrieval + admission ───────────────────────────────

# Unknown rights are NOT admissible: fail closed. An "unknown" license
# requires an explicit owner-approved corpus policy before admission.
ADMISSIBLE_LICENSES = {"apache-2.0", "mit", "cc-by-4.0", "bsd-3-clause"}


def metadata_presence_trust_anchor(node: EvidenceNode) -> bool:
    """Explicit WEAK trust anchor: accepts any non-empty receipt/revision pair.
    This is metadata presence only - it does NOT verify content binding, chain
    membership, or issuer scope. Callers that need verified receipts must supply
    a real verifier. Kept as a named, explicit opt-in so the fail-closed default
    is never silently weakened."""
    return bool(node.receipt_hash) and bool(node.source_revision)


class HIRAG:
    def __init__(self, dag: ProvenanceDAG, tau: float = 0.5,
                 weights: Optional[dict[str, float]] = None,
                 freshness_window_s: float = 30 * 24 * 3600,
                 trust_anchor: Optional[Any] = None) -> None:
        """trust_anchor: callable(EvidenceNode) -> bool that verifies a node's
        receipt against a real trust root (chain membership, content binding,
        issuer scope). FAIL-CLOSED DEFAULT: None means no anchor is supplied and
        the receipt axis scores 0.0 - unverifiable receipts veto admission."""
        self.dag = dag
        self.tau = tau
        self.weights = self._validated_weights(weights)
        self.freshness_window_s = freshness_window_s
        self.trust_anchor = trust_anchor
        if not _is_real(freshness_window_s) or \
                (isinstance(freshness_window_s, float) and not math.isfinite(freshness_window_s)) \
                or freshness_window_s <= 0:
            raise HiragError("HIRAG_FRESHNESS_WINDOW_INVALID",
                             "freshness_window_s must be a positive finite real")

    @staticmethod
    def _validated_weights(weights):
        """Admission weights must cover exactly the canonical axis set. Missing,
        extra, or unknown axes fail closed: a ranking weight configuration can
        never silently drop a mandatory provenance/rights/integrity axis."""
        w = dict(weights) if weights is not None else dict(DEFAULT_WEIGHTS)
        if set(w.keys()) != set(AXES):
            raise HiragError("HIRAG_AXIS_SET_INVALID",
                             "weights must cover exactly %s; got %s" % (sorted(AXES), sorted(w.keys())))
        return w

    def _axes_for(self, node: EvidenceNode, relevance: float,
                  now: Optional[float] = None) -> dict[str, float]:
        now = now if now is not None else time.time()
        if self.trust_anchor is None:
            receipt_valid = 0.0   # fail closed: no trust anchor, unverifiable receipt
        else:
            receipt_valid = 1.0 if self.trust_anchor(node) else 0.0
        # Transitive license contract: the node AND every ancestor in its
        # evidence chain must be admissible. An unknown-license ancestor must
        # not pass through an admissible child.
        chain_ids = self.dag.evidence_chain(node.node_id)
        licenses_ok = all(
            (self.dag.nodes[cid].license or "unknown").lower() in ADMISSIBLE_LICENSES
            for cid in chain_ids)
        license_ok = 1.0 if licenses_ok else 0.0
        # derivation integrity uses the SAME trust anchor as the node itself:
        # an anchor-rejected ancestor must veto the descendant (all-edges,
        # transitive). Without an anchor, integrity fails closed (0.0).
        if self.trust_anchor is None:
            integ = 0.0
        else:
            integ = 1.0 if all(self.trust_anchor(self.dag.nodes[cid])
                                for cid in chain_ids) else 0.0
        age = max(0.0, now - node.ingested_at)
        freshness = max(0.0, 1.0 - age / self.freshness_window_s)
        if not _is_real(relevance) or not (0.0 <= relevance <= 1.0):
            raise HiragError("HIRAG_RELEVANCE_OUT_OF_RANGE", str(relevance))
        return {
            "source_receipt_valid": receipt_valid,
            "license_admissible": license_ok,
            "freshness": round(freshness, 6),
            "relevance": relevance,
            "derivation_integrity": integ,
        }

    def admit(self, node_id: str, relevance: float,
              now: Optional[float] = None) -> dict[str, Any]:
        """Admission decision for one retrieved node. Returns the receipt."""
        if node_id not in self.dag.nodes:
            return self._refusal(node_id, "HIRAG_UNKNOWN_NODE", now)
        node = self.dag.nodes[node_id]
        try:
            axes = self._axes_for(node, relevance, now)
            names = list(self.weights.keys())
            scores = [axes[a] for a in names]
            w = [self.weights[a] for a in names]
            verdict, code = gate_v1(scores, w, self.tau)
            lam = lambda_v1(scores, w)
        except HiragError as e:
            # fail closed: an invalid configuration or input must still produce
            # a structured BLOCK receipt, never an unrecorded exception
            return self._refusal(node_id, e.code, now)
        tau_out = self.tau if (_is_real(self.tau) and math.isfinite(self.tau)) else None
        return {
            "schema": SCHEMA,
            "node_id": node_id,
            "axes": axes,
            "lambda": round(lam, 9),
            "tau": tau_out,
            "verdict": verdict,
            "code": code,
            "admitted": verdict == GO,
            "evidence_chain": self.dag.evidence_chain(node_id),
            "lambda_status": "ADVISORY",
            "conjecture_status": "Conjecture 1 (machine-checked false as stated); not a theorem",
            "truth_label": "MEASURED_ADMISSION_DECISION",
        }

    def _refusal(self, node_id: str, code: str, now: Optional[float]) -> dict[str, Any]:
        """Structured BLOCK receipt for invalid inputs/configurations."""
        return {
            "schema": SCHEMA,
            "node_id": node_id,
            "axes": {},
            "lambda": 0.0,
            "tau": self.tau,
            "verdict": BLOCK,
            "code": code,
            "admitted": False,
            "evidence_chain": [],
            "lambda_status": "ADVISORY",
            "conjecture_status": "Conjecture 1 (machine-checked false as stated); not a theorem",
            "truth_label": "MEASURED_ADMISSION_DECISION",
        }

    def retrieve_and_admit(self, ranked: list[tuple[str, float]],
                           now: Optional[float] = None) -> dict[str, Any]:
        """ranked: [(node_id, measured_relevance)] from ANY hierarchical retriever.
        Returns admitted context + per-node receipts, including refusals."""
        receipts, admitted, refused = [], [], []
        for node_id, relevance in ranked:
            r = self.admit(node_id, relevance, now)
            receipts.append(r)
            (admitted if r["admitted"] else refused).append(node_id)
        return {
            "schema": SCHEMA,
            "admitted": admitted,
            "refused": refused,
            "receipts": receipts,
            "admission_rate": round(len(admitted) / max(len(ranked), 1), 4),
            "lambda_status": "ADVISORY",
            "truth_label": "MEASURED_ADMISSION_RUN",
        }


def selfcheck() -> bool:
    dag = ProvenanceDAG()
    dag.add(EvidenceNode("src1", "source text", "h1" * 16, "abc123", "apache-2.0",
                        time.time() - 100, level=0))
    dag.add(EvidenceNode("sum1", "summary", "h2" * 16, "abc123", "apache-2.0",
                        time.time() - 50, derived_from=["src1"], level=1))
    h = HIRAG(dag, tau=0.5, trust_anchor=metadata_presence_trust_anchor)
    ok = h.admit("sum1", 0.9)["admitted"] is True
    # fail-closed default: without a trust anchor, unverifiable receipts veto
    h_noanchor = HIRAG(dag, tau=0.5)
    ok &= h_noanchor.admit("sum1", 0.9)["code"] == ZERO_VETO
    # zero-veto: broken receipt refuses admission regardless of relevance
    dag.add(EvidenceNode("bad1", "unproven", "", "abc123", "apache-2.0",
                         time.time(), level=0))
    r = h.admit("bad1", 0.99)
    ok &= r["admitted"] is False and r["code"] == ZERO_VETO
    # inadmissible license vetoes
    dag.add(EvidenceNode("lic1", "text", "h3" * 16, "abc123", "proprietary-all-rights",
                         time.time(), level=0))
    r2 = h.admit("lic1", 0.99)
    ok &= r2["admitted"] is False and r2["code"] == ZERO_VETO
    # batch run with admission rate
    run = h.retrieve_and_admit([("sum1", 0.9), ("bad1", 0.99), ("lic1", 0.8)])
    ok &= run["admitted"] == ["sum1"] and run["refused"] == ["bad1", "lic1"]
    ok &= abs(run["admission_rate"] - round(1 / 3, 4)) < 1e-9
    return bool(ok)


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA, "selfcheck_pass": selfcheck(),
                      "lambda_status": "ADVISORY"}, indent=1))
