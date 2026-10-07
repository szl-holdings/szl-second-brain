import json
import copy
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
    @staticmethod
    def resign(value: dict, field: str) -> dict:
        value.pop(field, None)
        value[field] = sha256_hex(canonical_bytes(value))
        return value

    def load_state(self, state: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            return load_public_state(path)

    def test_rejected_later_branch_preserves_empty_and_existing_index(self) -> None:
        for existing in (False, True):
            with self.subTest(existing=existing):
                index = RefinementMemoryIndex((receipt(),) if existing else ())
                before = index.public_status()
                bad = receipt()
                bad["branches"].append({"findings": [], "patches": ["malformed"]})
                self.resign(bad, "receipt_sha256")
                with self.assertRaises(RefinementMemoryBoundaryError):
                    index.ingest(bad)
                self.assertEqual(index.public_status(), before)
                valid = receipt()
                valid["branches"] *= 2
                self.resign(valid, "receipt_sha256")
                self.assertTrue(index.ingest(valid))

    def test_invalid_later_confidence_preserves_index(self) -> None:
        index = RefinementMemoryIndex((receipt(),))
        before = index.public_status()
        bad = receipt()
        bad["branches"].append(copy.deepcopy(bad["branches"][0]))
        bad["branches"][1]["findings"][0]["confidence"] = "private task"
        self.resign(bad, "receipt_sha256")
        with self.assertRaises(RefinementMemoryBoundaryError):
            index.ingest(bad)
        self.assertEqual(index.public_status(), before)

    def test_verified_rejects_string_number_and_missing_boolean(self) -> None:
        for invalid in ("false", "true", 0, 1, None, []):
            with self.subTest(invalid=invalid):
                bad = receipt()
                bad["branches"][0]["patches"][0]["verified"] = invalid
                self.resign(bad, "receipt_sha256")
                index = RefinementMemoryIndex()
                with self.assertRaises(RefinementMemoryBoundaryError):
                    index.ingest(bad)
                self.assertEqual(index.public_status()["receipt_count"], 0)
                self.assertEqual(index.handles(), [])

    def test_regression_rate_counts_affected_attempts(self) -> None:
        row = receipt()
        row["branches"][0]["regression_guard"]["changed_unflagged_step_count"] = 2
        row["branches"][0]["patches"].append(copy.deepcopy(row["branches"][0]["patches"][0]))
        self.resign(row, "receipt_sha256")
        index = RefinementMemoryIndex((row, receipt()))
        handle = index.handles()[0]
        self.assertEqual(handle["repair_attempts"], 3)
        self.assertEqual(handle["regression_rate"], 2 / 3)

    def test_regression_counts_reject_coercion(self) -> None:
        for invalid in (-1, True, "2", 1.5):
            with self.subTest(invalid=invalid):
                row = receipt()
                row["branches"][0]["regression_guard"]["changed_unflagged_step_count"] = invalid
                self.resign(row, "receipt_sha256")
                with self.assertRaises(RefinementMemoryBoundaryError):
                    RefinementMemoryIndex((row,))

    def test_digest_valid_extra_fields_cannot_publish_private_content(self) -> None:
        for location in ("state", "handle"):
            with self.subTest(location=location):
                state = RefinementMemoryIndex((receipt(),)).public_status()
                target = state if location == "state" else state["handles"][0]
                target["content"] = "private task text"
                self.resign(state, "state_sha256")
                with self.assertRaises(RefinementMemoryBoundaryError):
                    self.load_state(state)

    def test_public_state_requires_every_response_field(self) -> None:
        state = RefinementMemoryIndex((receipt(),)).public_status()
        for field in ("state", "receipt_count", "pattern_count", "ready", "merge_authority"):
            with self.subTest(field=field):
                bad = copy.deepcopy(state)
                del bad[field]
                self.resign(bad, "state_sha256")
                with self.assertRaises(RefinementMemoryBoundaryError):
                    self.load_state(bad)

    def test_public_handle_requires_schema_identity_counts_rates_and_boundaries(self) -> None:
        changes = {"schema": "other", "id": "private task", "sha256": "0" * 64,
                   "model_pair_sha256": "private", "error_code": "private content",
                   "repair_attempts": True, "verified_repairs": 2,
                   "verified_repair_rate": "1", "regression_rate": 2,
                   "mean_audit_confidence": 10 ** 1000, "training_authority": "ALLOW",
                   "promotion_authority": "ALLOW", "execution_authority": "ALLOW",
                   "candidate_state": "READY", "content_access": "CONTENT"}
        for field, value in changes.items():
            with self.subTest(field=field):
                state = RefinementMemoryIndex((receipt(),)).public_status()
                state["handles"][0][field] = value
                self.resign(state, "state_sha256")
                with self.assertRaises(RefinementMemoryBoundaryError):
                    self.load_state(state)

    def test_public_state_rejects_contradictory_counts_and_authority(self) -> None:
        changes = {"receipt_count": 0, "pattern_count": 0, "ready": 1,
                   "state": "READY", "training_authority": "ALLOW",
                   "promotion_authority": "ALLOW", "execution_authority": "ALLOW",
                   "merge_authority": "ALLOW"}
        for field, value in changes.items():
            with self.subTest(field=field):
                state = RefinementMemoryIndex((receipt(),)).public_status()
                state[field] = value
                self.resign(state, "state_sha256")
                with self.assertRaises(RefinementMemoryBoundaryError):
                    self.load_state(state)

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
