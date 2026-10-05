import json
import tempfile
import unittest
from pathlib import Path

from second_brain.refinement_memory import (
    RefinementMemoryBoundaryError,
    RefinementMemoryIndex,
    canonical_bytes,
    load_public_state,
    sha256_hex,
)


def receipt() -> dict:
    body = {
        "schema": "szl.refinement.receipt/v1",
        "method": "ALLOY_REFINEMENT_FABRIC",
        "model_pair": {
            "explorer": {"model_id": "one", "revision": "r1"},
            "auditor_repairer": {"model_id": "two", "revision": "r2"},
        },
        "authority": {
            "execution": "NONE",
            "training": "NONE",
            "promotion": "NONE",
            "merge": "NONE",
        },
        "privacy": {
            "hidden_chain_of_thought_requested": False,
            "hidden_chain_of_thought_persisted": False,
            "raw_prompts_persisted": False,
            "public_verifiable_steps_only": True,
        },
        "branches": [
            {
                "findings": [
                    {
                        "step_id": "s2",
                        "verdict": "FAIL",
                        "error_code": "ARITHMETIC_ERROR",
                        "confidence": 0.9,
                        "note_sha256": "0" * 64,
                    }
                ],
                "patches": [
                    {
                        "step_id": "s2",
                        "error_code": "ARITHMETIC_ERROR",
                        "verified": True,
                    }
                ],
                "regression_guard": {
                    "changed_unflagged_step_count": 0,
                },
            }
        ],
    }
    body["receipt_sha256"] = sha256_hex(canonical_bytes(body))
    return body


class RefinementMemoryTests(unittest.TestCase):
    def test_ingest_is_idempotent_and_handles_only(self) -> None:
        index = RefinementMemoryIndex()
        self.assertTrue(index.ingest(receipt()))
        self.assertFalse(index.ingest(receipt()))
        status = index.public_status()
        self.assertEqual(status["receipt_count"], 1)
        self.assertEqual(status["pattern_count"], 1)
        self.assertEqual(status["handles"][0]["verified_repair_rate"], 1.0)
        self.assertEqual(status["content_access"], "HANDLES_ONLY")
        self.assertFalse(status["raw_reasoning_present"])

    def test_private_reasoning_is_rejected_recursively(self) -> None:
        bad = receipt()
        bad["branches"][0]["chain_of_thought"] = "private"
        body = dict(bad)
        body.pop("receipt_sha256")
        bad["receipt_sha256"] = sha256_hex(canonical_bytes(body))
        with self.assertRaisesRegex(
            RefinementMemoryBoundaryError, "forbidden private field"
        ):
            RefinementMemoryIndex((bad,))

    def test_public_state_round_trip_is_bound(self) -> None:
        state = RefinementMemoryIndex((receipt(),)).public_status()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            self.assertEqual(load_public_state(path), state)
            state["pattern_count"] = 9
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(
                RefinementMemoryBoundaryError, "digest mismatch"
            ):
                load_public_state(path)


if __name__ == "__main__":
    unittest.main()
