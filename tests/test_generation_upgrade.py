# SPDX-License-Identifier: Apache-2.0
"""Tests exercise actual index/coordinator classes, not just helper contracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from second_brain.corpus import CorpusIntegrityError, load_corpus
from second_brain.hybrid import AuthorizedHydrator, HybridSecondBrain, ProviderUnavailable, RetrievalBoundaryError
from second_brain.retrieve import SecondBrainIndex


def rows(count=40):
    return [{"id": f"n{i:03}", "source": f"source-{i}", "title": "shared evidence",
             "text": f"common retrieval evidence document {i}",
             "sha256": hashlib.sha256(f"common retrieval evidence document {i}".encode()).hexdigest()}
            for i in range(count)]


def write(path, values):
    path.write_text("".join(json.dumps(row) + "\n" for row in values), encoding="utf-8")


class GenerationUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.jsonl"
        write(self.path, rows())

    def test_valid_rows_and_file_digest(self):
        corpus = load_corpus(self.path)
        self.assertEqual(len(corpus.rows), 40)
        self.assertEqual(corpus.file_sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_rejects_partial_invalid_json(self):
        self.path.write_text(self.path.read_text() + '{"bad":')
        index = SecondBrainIndex(self.path)
        self.assertFalse(index.built)
        self.assertEqual(index.rows, [])

    def test_rejects_duplicate_json_keys(self):
        self.path.write_text(self.path.read_text().replace('"id":', '"id":"shadow","id":', 1))
        self.assertFalse(SecondBrainIndex(self.path).built)

    def test_rejects_digest_synthesis_and_wrong_digest(self):
        for value in (None, "0" * 64, "z" * 64, True):
            candidate = rows()
            candidate[20]["sha256"] = value
            write(self.path, candidate)
            with self.subTest(value=value):
                self.assertFalse(SecondBrainIndex(self.path).built)

    def test_rejects_duplicate_node(self):
        write(self.path, rows() + rows(1))
        self.assertFalse(SecondBrainIndex(self.path).built)

    def test_expected_file_hash_pins_metadata(self):
        checksum = load_corpus(self.path).file_sha256
        candidate = rows(); candidate[0]["source"] = "substituted"
        write(self.path, candidate)
        self.assertFalse(SecondBrainIndex(self.path, expected_sha256=checksum).built)

    def test_failed_reload_retains_old_generation(self):
        index = SecondBrainIndex(self.path)
        before = index.search("retrieval", 6)
        self.path.write_text("malformed")
        self.assertFalse(index.reload())
        self.assertTrue(index.built)
        self.assertEqual(index.search("retrieval", 6), before)
        self.assertEqual(index.stats()["admission_state"], "ACTIVE_PREVIOUS_RELOAD_REJECTED")

    def test_snapshot_and_external_row_mutation_do_not_change_index(self):
        index = SecondBrainIndex(self.path)
        view = index.snapshot()
        before = view.search("retrieval", 6)
        external = index.rows; external[0]["id"] = "poison"; external[0]["_tf"]["retrieval"] = 999
        write(self.path, rows(3)); self.assertTrue(index.reload())
        self.assertEqual(index.n, 3)
        self.assertEqual(view.n, 40)
        self.assertEqual(view.search("retrieval", 6), before)
        with self.assertRaises(CorpusIntegrityError):
            view.reload()

    def test_internal_candidates_are_not_clamped_to_twelve(self):
        index = SecondBrainIndex(self.path)
        self.assertEqual(len(index.search_candidates("retrieval", limit=32)["handles"]), 32)
        self.assertEqual(len(index.search("retrieval", k=12)["handles"]), 12)
        result = HybridSecondBrain(index).context("retrieval", k=8)
        self.assertEqual(result["ranking_receipt"]["sparse_candidate_count"], 32)
        self.assertEqual(len(result["handles"]), 8)

    def test_candidate_pool_can_reach_128(self):
        write(self.path, rows(140))
        result = HybridSecondBrain(SecondBrainIndex(self.path), candidate_multiplier=20).context("retrieval", k=12)
        self.assertEqual(result["ranking_receipt"]["candidate_k"], 128)
        self.assertEqual(result["ranking_receipt"]["sparse_candidate_count"], 128)

    def test_bad_numeric_requests_rejected(self):
        brain = HybridSecondBrain(SecondBrainIndex(self.path))
        for k in (True, False, 1.9, "3", 0, 13):
            with self.subTest(k=k), self.assertRaises(RetrievalBoundaryError):
                brain.context("retrieval", k=k)
        for weight in (float("nan"), float("inf"), True, -1, 0):
            with self.subTest(weight=weight), self.assertRaises(RetrievalBoundaryError):
                HybridSecondBrain(SecondBrainIndex(self.path), dense_weight=weight)

    def test_invalid_dense_outputs_never_fall_back(self):
        for output in ([{"node_id":"unknown","score":1.0}], [{"node_id":"n000","score":True}],
                       [{"node_id":"n000","score":float("nan")}], [{"node_id":"n000","score":1.0}]*2):
            with self.subTest(output=output), self.assertRaises(RetrievalBoundaryError):
                HybridSecondBrain(SecondBrainIndex(self.path), dense_provider=lambda *_:output).context("retrieval")

    def test_only_typed_outage_may_fall_back(self):
        def unavailable(*_):
            raise ProviderUnavailable("offline")
        def invalid(*_):
            raise RuntimeError("unclassified bug")
        result = HybridSecondBrain(SecondBrainIndex(self.path), dense_provider=unavailable).context("retrieval")
        self.assertEqual(result["ranking_receipt"]["mode"], "BM25_FALLBACK_DENSE_UNAVAILABLE")
        with self.assertRaises(RuntimeError):
            HybridSecondBrain(SecondBrainIndex(self.path), dense_provider=invalid).context("retrieval")

    def test_empty_or_unknown_rerank_cannot_claim_success(self):
        for output in ([], ["unknown"], ["n000", "n000"], "n000"):
            with self.subTest(output=output), self.assertRaises(RetrievalBoundaryError):
                HybridSecondBrain(SecondBrainIndex(self.path), reranker=lambda *_:output).context("retrieval")

    def test_access_failure_does_not_become_fallback(self):
        def denied(*_):
            raise PermissionError("revoked")
        with self.assertRaises(PermissionError):
            HybridSecondBrain(SecondBrainIndex(self.path), dense_provider=denied).context("retrieval")

    def test_bound_dense_generation_must_match(self):
        class Dense:
            generation_sha256 = "0" * 64
            def __call__(self, *_):
                raise AssertionError("must not call mismatched dense generation")
        with self.assertRaises(RetrievalBoundaryError):
            HybridSecondBrain(SecondBrainIndex(self.path), dense_provider=Dense()).context("retrieval")

    def test_reload_inside_dense_does_not_mix_public_generation(self):
        index = SecondBrainIndex(self.path)
        previous = index.generation_sha256
        def dense(*_):
            write(self.path, rows(1)); self.assertTrue(index.reload())
            return [{"node_id":"n039", "score":1.0}]
        result = HybridSecondBrain(index, dense_provider=dense).context("retrieval")
        self.assertEqual(result["corpus_n"], 40)
        self.assertEqual(result["generation_sha256"], previous)
        self.assertEqual(index.n, 1)

    def test_authorizer_truthiness_cannot_grant_access(self):
        for value in ("allow", 1, {}, None):
            with self.subTest(value=value), self.assertRaises(RetrievalBoundaryError):
                AuthorizedHydrator(lambda *_:value, path=self.path).hydrate(
                    [{"nodeId":"n000"}], principal_id="p", tenant_id="t", policy_revision="a"*40)

    def test_hydration_rechecks_whole_corpus_admission(self):
        self.path.write_text(self.path.read_text() + "not json")
        with self.assertRaises(RetrievalBoundaryError):
            AuthorizedHydrator(lambda *_:True, path=self.path)

    def test_reranker_outage_is_explicit_and_configurable(self):
        def unavailable(*_):
            raise ProviderUnavailable("offline")
        result = HybridSecondBrain(SecondBrainIndex(self.path), reranker=unavailable).context("retrieval")
        self.assertEqual(result["ranking_receipt"]["mode"], "BM25_ONLY+RERANKER_UNAVAILABLE")
        with self.assertRaises(RetrievalBoundaryError):
            HybridSecondBrain(SecondBrainIndex(self.path), reranker=unavailable,
                              allow_reranker_fallback=False).context("retrieval")

    def test_public_neural_factory_rejects_an_unadmitted_corpus(self):
        from second_brain.neomme import PublicNeuralBrain
        with patch("second_brain.neomme.CORPUS", self.path), self.assertRaises(CorpusIntegrityError):
            PublicNeuralBrain(None)

    def test_index_persistence_is_bound_and_tamper_detecting(self):
        from second_brain.neomme import PublicNeuralBrain
        write(self.path, rows(3))
        checksum = load_corpus(self.path).file_sha256
        class Encoder:
            identity = {"kind":"FAKE_TEST_ENCODER_NOT_MODEL_INFERENCE"}
            def encode(self, *_):
                return [1.0] + [0.0]*1023, None
        with patch("second_brain.neomme.CORPUS", self.path), patch("second_brain.neomme.PUBLIC_CORPUS_SHA256", checksum):
            brain = PublicNeuralBrain(Encoder())
            path = Path(self.temp.name) / "index.json"
            seal = brain.build(path)
            restored = PublicNeuralBrain(Encoder()); restored.load(path, expected_sha256=seal)
            result = restored.coordinator(rerank=False).context("retrieval", k=2)
            self.assertEqual(result["ranking_receipt"]["mode"], "HYBRID_SPARSE_DENSE")
            self.assertEqual(result["ranking_receipt"]["dense_binding"]["index_sha256"], seal)
            self.assertEqual(len(result["handles"]), 2)
            old = restored.index_sha256
            path.write_text("{}")
            with self.assertRaises(CorpusIntegrityError):
                restored.load(path, expected_sha256=seal)
            self.assertEqual(restored.index_sha256, old)


if __name__ == "__main__":
    unittest.main()
