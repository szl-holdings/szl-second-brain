#!/usr/bin/env python3
"""HIRAG admission wiring tests: the hybrid gate is optional, content-bound and fails closed.

9/9 must pass. The default pipeline contract is byte-identical (NOT_APPLIED);
a configured gate filters the ranked selection with receipts and never backfills.
"""
import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, ".")

from second_brain.admission import CorpusAdmission, CorpusAdmissionError
from second_brain.corpus import load_corpus
from second_brain.hybrid import HybridSecondBrain, RetrievalBoundaryError
from second_brain.retrieve import SecondBrainIndex

LICENSED = "apache-2.0"
REFUSED_LICENSE = "proprietary-all-rights-reserved"
UNKNOWN = "unknown"


def _write_corpus(directory: Path, texts: dict, licenses: dict) -> tuple[Path, str]:
    """Write a strict corpus JSONL; return its path and the generation sha256."""
    path = directory / "brain.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        for node_id, text in texts.items():
            row = {"id": node_id, "source": "src-" + node_id, "title": text.title(),
                   "text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "license": licenses.get(node_id, UNKNOWN)}
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    generation = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, generation


def _metadata(licenses: dict, *, now=None, ingested_at=None, omit=()) -> dict:
    now = now if now is not None else time.time()
    meta = {}
    for node_id, license_value in licenses.items():
        if node_id in omit:
            continue
        meta[node_id] = {"license": license_value,
                         "ingested_at": ingested_at if ingested_at is not None else now}
    return meta


class AdmissionWiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.texts = {
            "n1": "locked eight formula authority and Lean proof",
            "n2": "second brain evidence retrieval and hydration",
            "n3": "A11oy action admission and signed receipt",
        }
        self.licenses = {"n1": LICENSED, "n2": LICENSED, "n3": LICENSED}

    def _corpus_pair(self, licenses=None, **kwargs):
        licenses = licenses if licenses is not None else self.licenses
        path, generation = _write_corpus(self.directory, self.texts, licenses)
        brain = SecondBrainIndex(path)
        corpus = load_corpus(path)
        admission = CorpusAdmission(corpus, generation_sha256=generation,
                                    node_metadata=_metadata(licenses, **kwargs))
        return brain, admission

    def test_default_is_not_applied_and_contract_unchanged(self):
        brain, _ = self._corpus_pair()
        result = HybridSecondBrain(brain).context("formula authority", k=2)
        receipt = result["ranking_receipt"]
        self.assertEqual(receipt["admission"], "NOT_APPLIED")
        self.assertIsNone(receipt["admission_detail"])
        self.assertNotIn("+HIRAG_ADMISSION", receipt["mode"])

    def test_applied_gate_filters_refused_nodes_and_reports_receipt(self):
        licenses = {"n1": LICENSED, "n2": LICENSED, "n3": REFUSED_LICENSE}
        brain, admission = self._corpus_pair(licenses)
        result = HybridSecondBrain(brain, admission=admission).context(
            "formula authority retrieval admission", k=3)
        receipt = result["ranking_receipt"]
        self.assertEqual(receipt["admission"], "APPLIED")
        self.assertTrue(receipt["mode"].endswith("+HIRAG_ADMISSION"))
        detail = receipt["admission_detail"]
        self.assertEqual(detail["gate"], "szl.hirag/v1")
        self.assertEqual(detail["relevance_measure"], "RANK_DERIVED_1_OVER_RANK")
        self.assertEqual(detail["refused_count"], 1)
        self.assertEqual(detail["admitted_count"], 2)
        self.assertEqual(detail["admission_rate"], round(2 / 3, 4))
        admitted_ids = [handle["nodeId"] for handle in result["handles"]]
        self.assertNotIn("n3", admitted_ids)
        self.assertEqual(detail["decisions"]["n3"], False)
        # no backfill: the refused node is dropped, never replaced
        self.assertEqual(len(result["evidence"]), detail["admitted_count"])

    def test_unknown_license_refuses_all_fail_closed(self):
        licenses = {node_id: UNKNOWN for node_id in self.texts}
        brain, admission = self._corpus_pair(licenses)
        result = HybridSecondBrain(brain, admission=admission).context(
            "formula authority retrieval", k=3)
        receipt = result["ranking_receipt"]
        self.assertEqual(receipt["admission"], "APPLIED")
        self.assertEqual(receipt["admission_detail"]["admitted_count"], 0)
        self.assertEqual(result["ready"], False)
        self.assertEqual(result["handles"], [])
        self.assertTrue(receipt["mode"].endswith("+HIRAG_ADMISSION"))

    def test_stale_freshness_refuses_regardless_of_rank(self):
        stale = time.time() - 400 * 24 * 3600  # far outside the default 30-day window
        brain, admission = self._corpus_pair(ingested_at=stale)
        result = HybridSecondBrain(brain, admission=admission).context(
            "formula authority", k=1)
        detail = result["ranking_receipt"]["admission_detail"]
        self.assertEqual(detail["admitted_count"], 0)
        self.assertEqual(result["ready"], False)

    def test_license_is_passed_through_exactly(self):
        declared = "Apache-2.0"  # owner spelling is preserved, never normalized
        licenses = {"n1": declared, "n2": declared, "n3": declared}
        brain, admission = self._corpus_pair(licenses)
        for node_id in self.texts:
            self.assertEqual(admission.licenses[node_id], declared)
        result = HybridSecondBrain(brain, admission=admission).context(
            "formula authority retrieval admission", k=3)
        self.assertEqual(result["ranking_receipt"]["admission_detail"]["admitted_count"], 3)

    def test_generation_mismatch_fails_closed_at_query_time(self):
        brain, admission = self._corpus_pair()
        # rewrite the corpus: a new generation invalidates the bound gate
        texts = dict(self.texts)
        texts["n1"] = "rewritten generation drifts away from the admitted corpus"
        path, _ = _write_corpus(self.directory, texts, self.licenses)
        drifted = SecondBrainIndex(path)
        with self.assertRaises(RetrievalBoundaryError):
            HybridSecondBrain(drifted, admission=admission).context("formula authority", k=2)

    def test_hybrid_rejects_non_corpus_admission_fail_closed(self):
        brain, _ = self._corpus_pair()
        with self.assertRaises(RetrievalBoundaryError):
            HybridSecondBrain(brain, admission=object())

    def test_corpus_admission_requires_full_node_metadata(self):
        path, generation = _write_corpus(self.directory, self.texts, self.licenses)
        corpus = load_corpus(path)
        with self.assertRaises(CorpusAdmissionError):
            CorpusAdmission(corpus, generation_sha256=generation,
                            node_metadata=_metadata(self.licenses, omit=("n2",)))

    def test_corpus_admission_requires_measured_ingested_at_and_bound_generation(self):
        path, generation = _write_corpus(self.directory, self.texts, self.licenses)
        corpus = load_corpus(path)
        # ingested_at must be a measured real: missing, non-numeric, oversized
        # (a value that cannot convert to float must not escape as OverflowError)
        for bad in (None, "yesterday", True, 10 ** 1000):
            meta = {node_id: {"license": self.licenses[node_id], "ingested_at": bad}
                    for node_id in self.texts}
            with self.assertRaises(CorpusAdmissionError):
                CorpusAdmission(corpus, generation_sha256=generation, node_metadata=meta)
        # the corpus file digest must equal the declared generation sha256
        with self.assertRaises(CorpusAdmissionError):
            CorpusAdmission(corpus, generation_sha256="f" * 64,
                            node_metadata=_metadata(self.licenses))


if __name__ == "__main__":
    unittest.main()
