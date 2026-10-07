import json
import tempfile
from pathlib import Path
import unittest.mock

from fastapi.testclient import TestClient

import app_refinement
from second_brain.refinement_memory import RefinementMemoryIndex, canonical_bytes, sha256_hex


class RefinementMemoryRouteTests(unittest.TestCase):
    def test_digest_valid_malformed_projection_returns_503_without_content(self) -> None:
        for mutation in ("missing_state", "missing_count", "extra_content"):
            with self.subTest(mutation=mutation):
                state = RefinementMemoryIndex().public_status()
                if mutation == "missing_state":
                    del state["state"]
                elif mutation == "missing_count":
                    del state["receipt_count"]
                else:
                    state["handles"] = [{"content": "private task text"}]
                    state["pattern_count"] = 1
                    state["receipt_count"] = 1
                    state["state"] = "REVIEW_REQUIRED"
                state.pop("state_sha256")
                state["state_sha256"] = sha256_hex(canonical_bytes(state))
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "state.json"
                    path.write_text(json.dumps(state), encoding="utf-8")
                    with unittest.mock.patch.object(app_refinement, "_state_path", return_value=path):
                        response = TestClient(app_refinement.app).get("/api/v1/refinement-memory")
                self.assertEqual(response.status_code, 503)
                self.assertFalse(response.json()["ready"])
                self.assertEqual(response.json()["handles"], [])
                self.assertNotIn("private task text", response.text)

    def test_route_returns_handles_only_state(self) -> None:
        state = RefinementMemoryIndex().public_status()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "refinement-patterns.public.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            with unittest.mock.patch.object(app_refinement, "_state_path", return_value=path):
                response = TestClient(app_refinement.app).get(
                    "/api/v1/refinement-memory"
                )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["content_access"], "HANDLES_ONLY")
        self.assertEqual(payload["handles"], [])
        encoded = json.dumps(payload).lower()
        self.assertNotIn("chain_of_thought", encoded)
        self.assertNotIn('"content"', encoded)

    def test_missing_state_fails_closed(self) -> None:
        missing = Path("/definitely/missing/refinement-state.json")
        with unittest.mock.patch.object(app_refinement, "_state_path", return_value=missing):
            response = TestClient(app_refinement.app).get(
                "/api/v1/refinement-memory"
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ready"])


if __name__ == "__main__":
    unittest.main()
