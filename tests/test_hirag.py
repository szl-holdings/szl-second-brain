#!/usr/bin/env python3
"""HIRAG adversarial tests: 9/9 must pass; the gate fails closed everywhere."""
import sys, time, unittest
sys.path.insert(0, ".")
from second_brain.hirag import (EvidenceNode, ProvenanceDAG, HIRAG, HiragError, metadata_presence_trust_anchor,
                                lambda_v1, gate_v1, ZERO_VETO, NUMERIC_TIE)

class TestHIRAG(unittest.TestCase):
    def test_duplicate_node_rejected(self):
        dag = ProvenanceDAG()
        dag.add(EvidenceNode("a", "t", "h"*16, "r1", "apache-2.0", time.time()))
        with self.assertRaises(HiragError):
            dag.add(EvidenceNode("a", "t2", "h"*16, "r1", "apache-2.0", time.time()))

    def test_unknown_parent_rejected(self):
        dag = ProvenanceDAG()
        with self.assertRaises(HiragError):
            dag.add(EvidenceNode("b", "t", "h"*16, "r1", "apache-2.0", time.time(), derived_from=["ghost"]))

    def test_weight_sum_fail_closed(self):
        with self.assertRaises(HiragError):
            lambda_v1([1.0, 1.0], [0.7, 0.7])

    def test_axis_range_fail_closed(self):
        with self.assertRaises(HiragError):
            lambda_v1([1.5, 1.0], [0.5, 0.5])

    def test_tau_invalid_blocks(self):
        v, c = gate_v1([1.0], [1.0], 1.5)
        self.assertEqual((v, c), ("BLOCK", "LAMBDA_TAU_INVALID"))

    def test_numeric_tie_abstains(self):
        v, c = gate_v1([0.5], [1.0], 0.5)
        self.assertEqual((v, c), ("ABSTAIN", NUMERIC_TIE))

    def test_evidence_chain(self):
        dag = ProvenanceDAG()
        dag.add(EvidenceNode("s1", "src", "h"*16, "r", "mit", time.time()))
        dag.add(EvidenceNode("s2", "sum", "h"*16, "r", "mit", time.time(), derived_from=["s1"]))
        self.assertEqual(set(dag.evidence_chain("s2")), {"s1", "s2"})

    def test_stale_node_zero_veto(self):
        dag = ProvenanceDAG()
        dag.add(EvidenceNode("s3", "old", "h"*16, "r", "mit", time.time() - 400*24*3600))
        r = HIRAG(dag, tau=0.05).admit("s3", 0.9)
        self.assertEqual((r["verdict"], r["code"]), ("NO_GO", ZERO_VETO))

    def test_selfcheck(self):
        from second_brain.hirag import selfcheck
        self.assertTrue(selfcheck())

if __name__ == "__main__":
    unittest.main()

class TestAdmissionContract(unittest.TestCase):
    """Regression tests for the four admission defects (averaging, weight
    omission, chain-head binding, unknown license). Fail closed everywhere."""

    def _dag(self):
        dag = ProvenanceDAG()
        dag.add(EvidenceNode("good", "g", "h" * 16, "r1", "mit", time.time()))
        dag.add(EvidenceNode("bad", "b", "", "r1", "mit", time.time()))
        dag.add(EvidenceNode("derived", "d", "h" * 16, "r2", "mit", time.time(),
                             derived_from=["good", "bad"]))
        return dag

    def test_one_broken_parent_vetoes(self):
        # D1: averaging let one broken parent of two score 0.5; now it must be 0.0
        self.assertEqual(self._dag().derivation_integrity("derived"), 0.0)

    def test_weight_omission_fails_closed(self):
        # D2: custom weights cannot drop mandatory axes
        with self.assertRaises(HiragError):
            HIRAG(self._dag(), tau=0.5, weights={"relevance": 1.0})

    def test_extra_axis_fails_closed(self):
        with self.assertRaises(HiragError):
            HIRAG(self._dag(), tau=0.5, weights={
                "source_receipt_valid": 0.2, "license_admissible": 0.2,
                "freshness": 0.2, "relevance": 0.2,
                "derivation_integrity": 0.1, "extra": 0.1})

    def test_chain_head_binding(self):
        # D3: a supplied chain head must match the node's declared claim
        n = EvidenceNode("x", "t", "h" * 16, "r", "mit", time.time())
        self.assertFalse(n.receipt_valid("forged-head"))          # no claim -> False
        n2 = EvidenceNode("x", "t", "h" * 16, "r", "mit", time.time(),
                          chain_head_claim="head-abc")
        self.assertTrue(n2.receipt_valid("head-abc"))
        self.assertFalse(n2.receipt_valid("other-head"))
        self.assertTrue(n2.receipt_valid(None))                   # metadata presence only

    def test_unknown_license_vetoes(self):
        # D4: unknown rights fail closed, not admissible by string match
        dag = ProvenanceDAG()
        dag.add(EvidenceNode("u", "t", "h" * 16, "r", "unknown", time.time()))
        r = HIRAG(dag, tau=0.5).admit("u", 0.99)
        self.assertFalse(r["admitted"])
        self.assertEqual(r["code"], ZERO_VETO)

    def test_broken_parent_node_refused_full_weights(self):
        # even with full canonical weights, a derived node with one broken
        # parent must refuse (derivation_integrity = 0.0 vetoes)
        r = HIRAG(self._dag(), tau=0.5).admit("derived", 1.0)
        self.assertFalse(r["admitted"])
        self.assertEqual(r["code"], ZERO_VETO)


class TestTrustAnchorAndTransitiveContract(unittest.TestCase):
    """Post-#70 regression tests: trust anchor, transitive license, error receipts."""

    def _node(self, dag, nid, lic="mit", parents=()):
        dag.add(EvidenceNode(nid, "c", "h" * 16, "r", lic, time.time(),
                             derived_from=list(parents)))

    def test_no_trust_anchor_fails_closed(self):
        # P1: forged receipt strings must NOT admit without a trusted anchor
        dag = ProvenanceDAG()
        self._node(dag, "forged")
        r = HIRAG(dag, tau=0.5).admit("forged", 1.0)
        self.assertFalse(r["admitted"])
        self.assertEqual(r["code"], ZERO_VETO)

    def test_metadata_anchor_is_explicit_opt_in(self):
        dag = ProvenanceDAG()
        self._node(dag, "n")
        r = HIRAG(dag, tau=0.5, trust_anchor=metadata_presence_trust_anchor).admit("n", 1.0)
        self.assertTrue(r["admitted"])   # explicit weak opt-in, honestly labeled
        # and the anchor actually decides:
        r2 = HIRAG(dag, tau=0.5, trust_anchor=lambda n: False).admit("n", 1.0)
        self.assertFalse(r2["admitted"])

    def test_unknown_license_ancestor_vetoes_child(self):
        # P2: an unknown-license ancestor must not pass through an MIT child
        dag = ProvenanceDAG()
        self._node(dag, "src", lic="unknown")
        self._node(dag, "child", lic="mit", parents=["src"])
        r = HIRAG(dag, tau=0.5, trust_anchor=metadata_presence_trust_anchor).admit("child", 1.0)
        self.assertFalse(r["admitted"])
        self.assertEqual(r["code"], ZERO_VETO)

    def test_admit_invalid_relevance_returns_block_receipt(self):
        # P3: invalid input must produce a structured BLOCK receipt, not a raise
        dag = ProvenanceDAG()
        self._node(dag, "n")
        r = HIRAG(dag, tau=0.5, trust_anchor=metadata_presence_trust_anchor).admit("n", 1.5)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertEqual(r["code"], "HIRAG_RELEVANCE_OUT_OF_RANGE")
        self.assertFalse(r["admitted"])

    def test_unknown_node_returns_block_receipt(self):
        dag = ProvenanceDAG()
        self._node(dag, "n")
        r = HIRAG(dag, tau=0.5).admit("ghost", 1.0)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertEqual(r["code"], "HIRAG_UNKNOWN_NODE")


class TestProvenanceHardening(unittest.TestCase):
    """Post-#72 hardening: anchor-transitive integrity, finite timestamps,
    freshness-window validation, strict-JSON-safe receipts."""

    def _dag(self):
        dag = ProvenanceDAG()
        dag.add(EvidenceNode("p", "c", "h" * 16, "r", "mit", time.time()))
        dag.add(EvidenceNode("child", "c", "h2" * 16, "r2", "mit", time.time(),
                             derived_from=["p"]))
        return dag

    def test_anchor_rejected_ancestor_vetoes_child(self):
        # the trust anchor decides parent validity too, not just the node's own
        dag = self._dag()
        r = HIRAG(dag, tau=0.5, trust_anchor=lambda n: n.node_id != "p").admit("child", 1.0)
        self.assertFalse(r["admitted"])
        self.assertEqual(r["axes"]["derivation_integrity"], 0.0)

    def test_no_anchor_derivation_fails_closed(self):
        dag = self._dag()
        r = HIRAG(dag, tau=0.5).admit("child", 1.0)
        self.assertEqual(r["axes"]["derivation_integrity"], 0.0)
        self.assertFalse(r["admitted"])

    def test_nonfinite_timestamp_rejected_at_insertion(self):
        dag = ProvenanceDAG()
        with self.assertRaises(HiragError) as cm:
            dag.add(EvidenceNode("n", "c", "h", "r", "mit", float("nan")))
        self.assertEqual(cm.exception.code, "HIRAG_NONFINITE_TIMESTAMP")

    def test_zero_freshness_window_rejected_at_construction(self):
        dag = self._dag()
        with self.assertRaises(HiragError) as cm:
            HIRAG(dag, tau=0.5, freshness_window_s=0.0,
                  trust_anchor=metadata_presence_trust_anchor)
        self.assertEqual(cm.exception.code, "HIRAG_FRESHNESS_WINDOW_INVALID")

    def test_nan_tau_receipt_is_strict_json(self):
        import json
        dag = self._dag()
        r = HIRAG(dag, tau=float("nan"),
                  trust_anchor=metadata_presence_trust_anchor).admit("child", 1.0)
        self.assertIsNone(r["tau"])   # non-finite tau never enters the receipt
        json.dumps(r, allow_nan=False)  # must not raise
