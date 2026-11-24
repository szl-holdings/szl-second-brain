"""Offline regression contracts for the read-only public HF source-parity witness."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

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
    @staticmethod
    def page(rows, next_url=None):
        response = BytesIO(json.dumps(rows).encode("utf-8"))
        response.status = 200
        response.headers = Message()
        if next_url is not None:
            response.headers["Link"] = f'<{next_url}>; rel="next"'
        return response

    def test_extra_file_on_later_pinned_page_requires_review(self):
        expected, rows = fixture()
        tree_url = gate.SPACE_API + "/tree/" + "a" * 40
        first = tree_url + "?recursive=true"
        second = tree_url + "?expand=false&recursive=true&limit=1000&cursor=cGFnZTI%3D"
        extra = {"type": "file", "oid": "e" * 40, "path": "extra.py"}
        opener = Mock()
        opener.open.side_effect = [self.page(rows, second), self.page([extra])]
        report = gate.compare_file_oids(expected, gate.provider_json(first, opener=opener))
        self.assertEqual(report["state"], "SOURCE_PARITY_MATCH_EXTRA_REVIEW_REQUIRED")
        self.assertEqual(report["extra_space_paths_sample"], ["extra.py"])
        self.assertEqual(
            [call.args[0].full_url for call in opener.open.call_args_list],
            [first, second],
        )

    def test_continuation_cannot_leave_the_pinned_recursive_tree(self):
        first = gate.SPACE_API + "/tree/" + "a" * 40 + "?recursive=true"
        for second in (
            first.replace("a" * 40, "b" * 40) + "&cursor=next",
            first.replace("huggingface.co", "example.org") + "&cursor=next",
            first.replace("recursive=true", "recursive=false") + "&cursor=next",
        ):
            with self.subTest(second=second):
                opener = Mock()
                opener.open.return_value = self.page([], second)
                with self.assertRaises(gate.ParityHold):
                    gate.provider_json(first, opener=opener)
                opener.open.assert_called_once()

    def test_repeated_or_over_budget_continuation_holds(self):
        _, rows = fixture()
        first = gate.SPACE_API + "/tree/" + "a" * 40 + "?recursive=true"
        second = first + "&cursor=next"
        opener = Mock()
        opener.open.side_effect = [self.page(rows[:1], second), self.page(rows[1:], second)]
        with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_TREE_PAGINATION"):
            gate.provider_json(first, opener=opener)
        opener = Mock()
        opener.open.return_value = self.page(rows, second)
        with patch.object(gate, "MAX_FILES", len(rows)):
            with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_TREE_LIMIT"):
                gate.provider_json(first, opener=opener)
        opener.open.assert_called_once()

    def test_unavailable_second_page_cannot_produce_a_match(self):
        _, rows = fixture()
        first = gate.SPACE_API + "/tree/" + "a" * 40 + "?recursive=true"
        second = first + "&cursor=next"
        opener = Mock()
        opener.open.side_effect = [self.page(rows, second), TimeoutError()]
        with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_TRANSPORT_TimeoutError"):
            gate.provider_json(first, opener=opener)

    def test_byte_budget_spans_pages(self):
        _, rows = fixture()
        first = gate.SPACE_API + "/tree/" + "a" * 40 + "?recursive=true"
        first_page = self.page(rows[:1], first + "&cursor=next")
        opener = Mock()
        opener.open.side_effect = [first_page, self.page(rows[1:])]
        with patch.object(gate, "MAX_HTTP_BYTES", len(first_page.getvalue()) + 1):
            with self.assertRaisesRegex(gate.ParityHold, "PROVIDER_RESPONSE_OVERSIZE"):
                gate.provider_json(first, opener=opener)

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
