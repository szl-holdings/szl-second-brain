"""Configuration observations never execute or qualify a retrieval provider."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from second_brain.hybrid import HybridSecondBrain
from second_brain.retrieve import SecondBrainIndex


class UncallableProvider:
    def __call__(self, *args, **kwargs):
        raise AssertionError("Observation must never execute providers")

    @property
    def binding(self):
        raise AssertionError("Observation must not read arbitrary provider metadata")


class ConfigurationObservationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "corpus.jsonl"
        text = "retrieval evidence"
        self.path.write_text(json.dumps({"id": "n1", "source": "fixture", "title": "Evidence",
                                        "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}) + "\n")
        self.brain = SecondBrainIndex(self.path)

    def test_default_observation_is_not_a_runtime_mode_or_qualification(self):
        observation = HybridSecondBrain(self.brain).configuration_observation()
        self.assertFalse(observation["dense_provider_configured"])
        self.assertFalse(observation["reranker_configured"])
        self.assertEqual(observation["corpus_row_count"], 1)
        self.assertEqual(observation["corpus_generation_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(observation["scope"], "CONFIGURATION_ONLY")
        self.assertEqual(observation["participation_evidence"], "QUERY_RANKING_RECEIPT_REQUIRED")
        self.assertEqual(set(observation), {"schema", "dense_provider_configured", "reranker_configured",
                                         "corpus_generation_sha256", "corpus_row_count", "scope",
                                         "participation_evidence"})
        json.dumps(observation, allow_nan=False)

    def test_presence_is_reported_without_executing_or_inspecting_provider(self):
        provider = UncallableProvider()
        coordinator = HybridSecondBrain(self.brain, dense_provider=provider, reranker=provider)
        observation = coordinator.configuration_observation()
        self.assertTrue(observation["dense_provider_configured"])
        self.assertTrue(observation["reranker_configured"])

    def test_observation_is_detached_and_reads_current_configuration(self):
        coordinator = HybridSecondBrain(self.brain)
        previous = coordinator.configuration_observation()
        previous["corpus_row_count"] = 999
        coordinator.dense_provider = UncallableProvider()
        current = coordinator.configuration_observation()
        self.assertTrue(current["dense_provider_configured"])
        self.assertFalse(current["reranker_configured"])
        self.assertEqual(current["corpus_row_count"], 1)

    def test_observation_does_not_change_sparse_retrieval(self):
        coordinator = HybridSecondBrain(self.brain)
        before = coordinator.context("evidence")
        coordinator.configuration_observation()
        self.assertEqual(before, coordinator.context("evidence"))


if __name__ == "__main__":
    unittest.main()
