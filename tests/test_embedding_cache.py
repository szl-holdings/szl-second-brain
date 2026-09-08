# SPDX-License-Identifier: Apache-2.0
"""Fake payload cache tests; no native model inference is asserted here."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from second_brain.corpus import CorpusIntegrityError, load_corpus
from second_brain.embedding_cache import EmbeddingCache
from second_brain.neomme import PublicNeuralBrain
from test_generation_upgrade import rows, write


class EmbeddingCacheTests(unittest.TestCase):
    def test_lru_eviction_and_accounting(self):
        cache = EmbeddingCache(6)
        cache.put(("a",), "a", byte_size=3)
        cache.put(("b",), "b", byte_size=3)
        self.assertEqual(cache.get(("a",)), "a")
        cache.put(("c",), "c", byte_size=3)
        self.assertIsNone(cache.get(("b",)))
        self.assertEqual(cache.get(("a",)), "a")
        self.assertEqual(cache.stats()["payload_bytes"], 6)
        self.assertEqual(cache.stats()["evictions"], 1)

    def test_oversize_and_disabled_do_not_retain(self):
        for budget in (0, 1):
            cache = EmbeddingCache(budget)
            self.assertFalse(cache.put(("x",), "x", byte_size=2))
            self.assertEqual(cache.stats()["payload_bytes"], 0)
            self.assertIsNone(cache.get(("x",)))

    def test_replacement_does_not_double_count(self):
        cache = EmbeddingCache(8)
        cache.put(("x",), "a", byte_size=8)
        cache.put(("x",), "b", byte_size=2)
        self.assertEqual(cache.stats()["payload_bytes"], 2)
        self.assertEqual(cache.get(("x",)), "b")

    def test_bad_budgets_and_sizes_are_rejected(self):
        for budget in (True, -1, 1.5, "5", 512*1024*1024+1):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                EmbeddingCache(budget)
        for size in (True, 0, -1, float("inf"), "1"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                EmbeddingCache(8).put(("x",), "x", byte_size=size)

    def test_model_and_corpus_scopes_are_distinct_keys(self):
        cache = EmbeddingCache(16)
        cache.put(("corpus-a", "model-a", "node"), "a", byte_size=8)
        self.assertIsNone(cache.get(("corpus-b", "model-a", "node")))
        self.assertIsNone(cache.get(("corpus-a", "model-b", "node")))

    def test_existing_neural_provider_reuses_body_outputs(self):
        class FakeTokens:
            def numel(self): return 256
            def element_size(self): return 4
        class FakeEncoder:
            identity = {"kind": "FAKE_UNIT_TEST_NOT_MODEL"}
            calls = 0
            def encode(self, *_):
                self.calls += 1
                return [1.0] + [0.0]*1023, FakeTokens()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.jsonl"; write(path, rows(3))
            checksum = load_corpus(path).file_sha256
            with patch("second_brain.neomme.CORPUS", path), patch("second_brain.neomme.PUBLIC_CORPUS_SHA256", checksum):
                encoder = FakeEncoder(); brain = PublicNeuralBrain(encoder, token_cache_bytes=8192)
                progress = []
                brain.build(Path(directory) / "index.json", progress=lambda done, total:progress.append((done,total)))
                self.assertEqual(encoder.calls, 3)
                self.assertEqual(progress, [(1,3),(2,3),(3,3)])
                for row in brain.corpus.rows:
                    self.assertIsInstance(brain._document_tokens(row), FakeTokens)
                self.assertEqual(encoder.calls, 3)
                self.assertEqual(brain.cache_stats()["hits"], 3)
                self.assertEqual(brain.cache_stats()["payload_bytes"], 3072)
                # A new model identity cannot hit the old model's cached output.
                encoder.identity = {"kind": "DIFFERENT_FAKE_UNIT_TEST_MODEL"}
                with self.assertRaises(CorpusIntegrityError):
                    brain._document_tokens(brain.corpus.rows[0])
                self.assertEqual(encoder.calls, 3)


if __name__ == "__main__":
    unittest.main()
