#!/usr/bin/env python3
"""HIRAG adversarial tests: 9/9 must pass; the gate fails closed everywhere."""
import sys, time, unittest
sys.path.insert(0, ".")
from second_brain.hirag import (EvidenceNode, ProvenanceDAG, HIRAG, HiragError,
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
