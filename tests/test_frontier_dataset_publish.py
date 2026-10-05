"""Publication projection must preserve review status and omit candidate text."""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publish_frontier_dataset", ROOT / "scripts" / "publish_frontier_dataset.py"
)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


def source() -> dict[str, bytes]:
    # Windows checkouts may use CRLF; the publisher reads immutable Git blobs.
    return {path: publisher.committed_bytes("HEAD", path) for path in publisher.SOURCE_PATHS}


def render(data: dict[str, bytes]) -> dict[str, bytes]:
    template = (ROOT / publisher.CARD_TEMPLATE).read_bytes()
    with patch.object(publisher, "committed_bytes", return_value=template):
        return publisher.projection("a" * 40, data)


def test_publication_is_handle_only_and_binds_exact_source_bytes() -> None:
    data = source()
    output = render(data)
    assert set(output) == {
        "frontier-handles.public.jsonl", "frontier-state.v1.json",
        "README.md", "publication.json",
    }
    handles = [json.loads(line) for line in output["frontier-handles.public.jsonl"].splitlines()]
    assert len(handles) == 141
    assert all(row["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED" for row in handles)
    assert all(row["contentAccess"] == "HANDLES_ONLY" for row in handles)
    assert all("content" not in row and "provenance" not in row for row in handles)
    assert output["frontier-state.v1.json"] == data["data/frontier-state.v1.json"]
    manifest = json.loads(output["publication.json"])
    assert manifest["source_revision"] == "a" * 40
    assert manifest["content_projection"] == "HANDLES_ONLY"
    assert manifest["source_files"]["data/frontier-candidates.public.jsonl"]["sha256"] == publisher.sha256(
        data["data/frontier-candidates.public.jsonl"]
    )
    assert all(manifest[key] == "NONE" for key in (
        "training_authority", "promotion_authority", "execution_authority"
    ))


def test_candidate_tamper_fails_before_provider_write() -> None:
    data = source()
    path = "data/frontier-candidates.public.jsonl"
    data[path] = data[path].replace(b"Governed Kernel Suite", b"Ungoverned Kernel Suite", 1)
    with pytest.raises((ValueError, publisher.PublicationError)):
        render(data)


def test_authority_drift_fails_before_provider_write() -> None:
    data = source()
    path = "data/frontier-state.v1.json"
    data[path] = data[path].replace(b'"training_authority": "NONE"', b'"training_authority": "YES"')
    with pytest.raises((ValueError, publisher.PublicationError)):
        render(data)


def test_mismatched_research_snapshot_fails_before_provider_write() -> None:
    data = source()
    path = "data/public-research-metadata.v1.json"
    snapshot = json.loads(data[path])
    snapshot["records"] = list(reversed(snapshot["records"]))
    snapshot["records"][0]["metadata"]["title"] = "Changed research title"
    data[path] = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()
    with pytest.raises((ValueError, publisher.PublicationError)):
        render(data)


def test_guarded_update_requires_current_hub_head(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = types.ModuleType("huggingface_hub")
    hub.CommitOperationAdd = lambda **kwargs: kwargs
    hub.hf_hub_download = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("stale Hub revision must fail before download")
    )
    utils = types.ModuleType("huggingface_hub.utils")
    utils.RepositoryNotFoundError = type("RepositoryNotFoundError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "huggingface_hub.utils", utils)

    class FakeApi:
        def whoami(self):
            return {"orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

        def repo_info(self, *args, **kwargs):
            return SimpleNamespace(sha="b" * 40)

        def create_commit(self, **kwargs):
            raise AssertionError("provider write must not happen")

    monkeypatch.setattr(publisher, "_readback", lambda *_: (_ for _ in ()).throw(ValueError("different")))
    with pytest.raises(publisher.PublicationError, match="exact current Hub revision required"):
        publisher.publish(FakeApi(), {"publication.json": b"{}"}, expected_hub_revision="c" * 40)


def test_guarded_update_verifies_old_source_and_uses_hub_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hub = types.ModuleType("huggingface_hub")
    hub.CommitOperationAdd = lambda **kwargs: kwargs
    utils = types.ModuleType("huggingface_hub.utils")
    utils.RepositoryNotFoundError = type("RepositoryNotFoundError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "huggingface_hub.utils", utils)
    old_source, new_source, old_hub, new_hub = "a" * 40, "b" * 40, "c" * 40, "d" * 40
    old_manifest = {
        "schema": "szl.second-brain.hf-frontier-publication/v1",
        "source_repository": publisher.GITHUB_REPO,
        "target_dataset": publisher.HF_REPO,
        "content_projection": "HANDLES_ONLY",
        "source_revision": old_source,
        "training_authority": "NONE", "promotion_authority": "NONE", "execution_authority": "NONE",
    }
    marker = tmp_path / "prior-publication.json"
    marker.write_text(json.dumps(old_manifest), encoding="utf-8")
    hub.hf_hub_download = lambda *args, **kwargs: str(marker)
    old_expected = {"publication.json": b"old"}
    new_expected = {"publication.json": json.dumps({"source_revision": new_source}).encode()}
    calls = []

    def check_bytes(_api, revision, expected):
        calls.append(("readback", revision, expected))
        if len([item for item in calls if item[0] == "readback"]) == 1:
            raise ValueError("new bytes differ")

    monkeypatch.setattr(publisher, "_readback", check_bytes)
    monkeypatch.setattr(publisher, "build", lambda revision: old_expected if revision == old_source else None)
    monkeypatch.setattr(publisher, "git", lambda *args: calls.append(("git", *args)) or b"")
    monkeypatch.setattr(publisher, "gh_verified", lambda *args, **kwargs: calls.append(("signature", args, kwargs)))

    class FakeApi:
        def whoami(self):
            return {"orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

        def repo_info(self, *args, **kwargs):
            return SimpleNamespace(sha=old_hub)

        def create_commit(self, **kwargs):
            calls.append(("commit", kwargs))
            return SimpleNamespace(oid=new_hub)

    assert publisher.publish(FakeApi(), new_expected, expected_hub_revision=old_hub) == (
        "UPDATED_AND_VERIFIED", new_hub
    )
    assert ("git", "merge-base", "--is-ancestor", old_source, new_source) in calls
    assert ("signature", (old_source,), {"require_current_main": False}) in calls
    assert ("readback", old_hub, old_expected) in calls
    assert next(item[1] for item in calls if item[0] == "commit")["parent_commit"] == old_hub
    assert ("readback", new_hub, new_expected) in calls


@pytest.mark.parametrize("path", publisher.SOURCE_PATHS)
def test_reviewed_source_requires_each_exact_input_blob(path: str) -> None:
    data = source()
    data[path] += b"\n"
    with pytest.raises(publisher.PublicationError, match="source set has not been reviewed"):
        render(data)


def test_extra_source_file_cannot_enter_public_manifest() -> None:
    data = source()
    data["unreviewed/private.json"] = b"{}"
    with pytest.raises(publisher.PublicationError, match="source file set changed"):
        render(data)


def test_self_consistent_same_count_change_remains_unreviewed() -> None:
    data = source()
    rows = [publisher.strict_json(line) for line in data[publisher.SOURCE_PATHS[0]].splitlines()]
    rows[0]["title"] += " (unreviewed)"
    data[publisher.SOURCE_PATHS[0]] = b"".join(publisher.canonical_bytes(row) + b"\n" for row in rows)
    state = publisher.strict_json(data[publisher.SOURCE_PATHS[1]])
    state["candidate_set_sha256"] = publisher.sha256(data[publisher.SOURCE_PATHS[0]])
    state["state_sha256"] = publisher.sha256(publisher.canonical_bytes({
        key: value for key, value in state.items() if key != "state_sha256"
    }))
    data[publisher.SOURCE_PATHS[1]] = publisher.canonical_bytes(state) + b"\n"
    publisher.FrontierIndex._validate(state, rows)
    assert len(rows) == 141
    with pytest.raises(publisher.PublicationError, match="source set has not been reviewed"):
        render(data)


def test_public_card_counts_match_the_projected_handles() -> None:
    output = render(source())
    card = output["README.md"].decode()
    assert "Inspect 141 attributed" in card
    assert "**141 attributed candidates" in card
    assert "| 135 Git-sourced candidates" in card
    assert "__CANDIDATE_COUNT__" not in card
    assert "__DETAIL_CANDIDATE_COUNT__" not in card
    assert "__GIT_CANDIDATE_COUNT__" not in card


@pytest.mark.parametrize("marker", [
    "__CANDIDATE_COUNT__", "__DETAIL_CANDIDATE_COUNT__", "__GIT_CANDIDATE_COUNT__"
])
def test_missing_or_duplicate_card_count_marker_is_rejected(marker: str) -> None:
    data = source()
    template = (ROOT / publisher.CARD_TEMPLATE).read_bytes()
    for replacement in (b"", marker.encode() * 2):
        broken = template.replace(marker.encode(), replacement)
        with patch.object(publisher, "committed_bytes", return_value=broken):
            with pytest.raises(publisher.PublicationError, match="card count marker"):
                publisher.projection("a" * 40, data)


def test_legacy_and_current_source_policies_remain_distinct() -> None:
    receipt = json.loads((ROOT / "tests/fixtures/frontier-projection-efa7bddf.review.json").read_text(encoding="utf-8"))
    assert len(publisher.REVIEWED_INPUTS) == len(receipt["historical_inputs"]) + 1
    for historical in receipt["historical_inputs"]:
        assert publisher.REVIEWED_INPUTS[tuple(historical["source_sha256"])] == tuple(historical["counts"])
    assert set(publisher.REVIEWED_INPUTS.values()) == {(137, 10, 6), (141, 10, 6)}
    assert all(len(identities) == 3 and all(len(digest) == 64 for digest in identities)
               for identities in publisher.REVIEWED_INPUTS)


def test_reviewed_ouroboros_projection_preserves_receipt_and_rights() -> None:
    receipt = json.loads((ROOT / "tests/fixtures/frontier-projection-efa7bddf.review.json").read_text(encoding="utf-8"))
    data = source()
    identity = tuple(publisher.sha256(data[path]) for path in publisher.SOURCE_PATHS)
    assert identity == tuple(receipt["source_sha256"])
    assert publisher.REVIEWED_INPUTS[identity] == (141, 10, 6)

    output = render(data)
    handles_bytes = output["frontier-handles.public.jsonl"]
    assert publisher.sha256(handles_bytes) == receipt["handles_sha256"]
    handles = [json.loads(line) for line in handles_bytes.splitlines()]
    assert len(handles) == 141
    assert all(row["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED" for row in handles)
    assert all(row["contentAccess"] == "HANDLES_ONLY" for row in handles)
    assert all("content" not in row and "provenance" not in row for row in handles)

    research = [row["sourceIdentity"] for row in handles if "sourceIdentity" in row]
    assert len(research) == 6
    assert all(row["fullTextLicence"] == "NOT_INFERRED" for row in research)
    observed_rights = {}
    for row in research:
        key = f"{row['provider']}:{row['metadataLicence']}"
        observed_rights[key] = observed_rights.get(key, 0) + 1
    assert observed_rights == receipt["metadata_rights_counts"]

    state = json.loads(output["frontier-state.v1.json"])
    assert state["state_sha256"] == receipt["canonical_state_core_sha256"]
    assert publisher.sha256(output["frontier-state.v1.json"]) == identity[1]
    card = output["README.md"].decode()
    assert "license: other" in card
    assert "no blanket open-data" in card
