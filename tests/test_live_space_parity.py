"""Offline regression contracts for the read-only public HF source-parity witness."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_live_space_parity", ROOT / "tools" / "check_live_space_parity.py"
)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(gate)


def git_sha():
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()


def fixture():
    expected = {
        "Dockerfile": "a" * 40,
        "app.py": "b" * 40,
        "second_brain/web.py": "c" * 40,
    }
    rows = [
        {"path": path, "oid": sha, "type": "file"} for path, sha in expected.items()
    ]
    return expected, rows


class LiveSpaceParityTests(unittest.TestCase):
    def test_exact_matches_are_only_source_matches(self):
        expected, rows = fixture()
        report = gate.compare_file_oids(expected, rows)
        self.assertEqual(report["state"], "SOURCE_PARITY_MATCH_ONLY")
        self.assertEqual(report["matching_git_blobs"], 3)

    def test_different_dockerfile_detected(self):
        expected, rows = fixture()
        rows[0]["oid"] = "d" * 40
        report = gate.compare_file_oids(expected, rows)
        self.assertEqual(report["state"], "SOURCE_DEPLOYMENT_DRIFT")
        self.assertEqual(report["different_blobs"][0]["path"], "Dockerfile")

    def test_missing_app_detected(self):
        expected, rows = fixture()
        report = gate.compare_file_oids(expected, rows[:1] + rows[2:])
        self.assertEqual(report["state"], "SOURCE_DEPLOYMENT_DRIFT")
        self.assertEqual(report["missing_paths"], ["app.py"])

    def test_unreviewed_extra_file_remains_nonadmitted(self):
        expected, rows = fixture()
        rows.append({"path": "extra.py", "oid": "e" * 40, "type": "file"})
        report = gate.compare_file_oids(expected, rows)
        self.assertEqual(report["state"], "SOURCE_PARITY_MATCH_EXTRA_REVIEW_REQUIRED")
        self.assertEqual(report["extra_space_paths_count"], 1)

    def test_duplicate_provider_blob_refused(self):
        expected, rows = fixture()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_TREE_DUPLICATE"):
            gate.compare_file_oids(expected, rows)

    def test_malformed_provider_oid_refused(self):
        expected, rows = fixture()
        rows[0]["oid"] = "main"
        with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_BLOB_INVALID"):
            gate.compare_file_oids(expected, rows)

    def test_provider_url_allowlist(self):
        with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_URL_NOT_ALLOWLISTED"):
            gate.provider_json("https://example.org/redirect")
        with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_URL_NOT_ALLOWLISTED"):
            gate.provider_json(gate.SPACE_API + "/tree/main?recursive=true")

    def test_source_pin_wrong_is_rejected(self):
        with self.assertRaisesRegex(gate.ParityHold, "SOURCE_HEAD_DRIFT"):
            gate.commit_and_index(ROOT, "0" * 40)

    def test_source_payload_requires_false_publish_flag(self):
        index = gate.commit_and_index(ROOT, git_sha())
        expected = gate.included_source_oids(ROOT, index)
        self.assertIn("Dockerfile", expected)
        self.assertIn("app.py", expected)
        self.assertIn("second_brain/web.py", expected)

    def test_faked_three_reads_source_match_not_deploy_proof(self):
        index = gate.commit_and_index(ROOT, git_sha())
        expected = gate.included_source_oids(ROOT, index)
        tree = [{"path": k, "oid": v, "type": "file"} for k, v in expected.items()]
        sha = "f" * 40
        calls = []

        def fetch(url):
            calls.append(url)
            if "/tree/" in url:
                return tree
            return {"sha": sha, "runtime": {"stage": "RUNNING"}}

        result = gate.verify(ROOT, git_sha(), fetch=fetch)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["parity"]["state"], "SOURCE_PARITY_MATCH_ONLY")
        self.assertFalse(result["public_api_readiness_verified"])
        self.assertFalse(result["provider_deployment_authorized"])
        self.assertFalse(result["credential_or_provider_write_used"])

    def test_moving_space_head_refused(self):
        index = gate.commit_and_index(ROOT, git_sha())
        expected = gate.included_source_oids(ROOT, index)
        tree = [{"path": k, "oid": v, "type": "file"} for k, v in expected.items()]
        calls = []

        def fetch(url):
            calls.append(url)
            if "/tree/" in url:
                return tree
            return {
                "sha": ("a" if len(calls) == 1 else "b") * 40,
                "runtime": {"stage": "RUNNING"},
            }

        with self.assertRaisesRegex(gate.ParityHold, "SPACE_SHA_MOVED"):
            gate.verify(ROOT, git_sha(), fetch=fetch)

    def test_duplicate_json_keys_fail(self):
        with self.assertRaises(gate.ParityHold):
            gate.strict_json(b'{"a":1,"a":2}')


if __name__ == "__main__":
    unittest.main()
