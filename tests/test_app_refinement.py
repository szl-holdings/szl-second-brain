import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

import app_refinement
from second_brain.refinement_memory import RefinementMemoryIndex


class RefinementMemoryRouteTests(TestCase):
    def test_route_returns_handles_only_state(self) -> None:
        state = RefinementMemoryIndex().public_status()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "refinement-patterns.public.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            with patch.object(app_refinement, "_state_path", return_value=path):
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
        with patch.object(app_refinement, "_state_path", return_value=missing):
            response = TestClient(app_refinement.app).get(
                "/api/v1/refinement-memory"
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ready"])


if __name__ == "__main__":
    import unittest

    unittest.main()
