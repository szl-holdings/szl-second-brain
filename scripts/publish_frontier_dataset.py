#!/usr/bin/env python3
"""Publish the reviewed frontier *handles* from canonical GitHub to one HF dataset.

This is a manual, one-target publisher. It never creates compute, publishes raw
candidate content, trains, or changes the separate Alloy in-repo dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from second_brain.frontier import FrontierCandidate, FrontierIndex
from second_brain.public_research import canonical_bytes, strict_json, validate_snapshot
GITHUB_REPO = "szl-holdings/szl-second-brain"
HF_REPO = "SZLHOLDINGS/szl-second-brain-frontier-candidates"
SOURCE_PATHS = (
    "data/frontier-candidates.public.jsonl",
    "data/frontier-state.v1.json",
    "data/public-research-metadata.v1.json",
)
CARD_TEMPLATE = "hub/frontier-dataset/README.template.md"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")

# Exact input triples for structural review-handle projection only.
# These pins do not approve candidate claims, training, promotion, or execution.
# Retain historical inputs: guarded Hub updates rebuild the prior publication.
REVIEWED_INPUTS: dict[tuple[str, str, str], tuple[int, int, int]] = {
    (
        'c6dd7ce0d1379da74eb2456f4ab4b750ec9dd481bf57941240f4a98d771e6163',
        '9eeb6e883463669770ebe0a2cf663ec6ee6bd22da0276b9fee70696015214d74',
        'd63cb1e11373807362632cae45b51263eb97ecbc8168a2ea6af85958a3f74c86',
    ): (137, 10, 6),
    (
        '440473ee67851ad8897d2e2e20e0025b95b202844cdabe0b1acdd5e5619d177f',
        '9443f9bb522e27650b93d42ac9cb225d11fa2b21e52f81dd161269c9511a756c',
        'd63cb1e11373807362632cae45b51263eb97ecbc8168a2ea6af85958a3f74c86',
    ): (141, 10, 6),
    # Structural handle projection reviewed at b50307d; mixed-source rights
    # and review-required status are retained. Pin the raw state-file bytes,
    # not the separate canonical state-core digest.
    (
        'efa7bddf8526aaabada77e27257dc0f0128f151a7e97ebe51d5eafede8f04f7c',
        '54cb1a5b7bb2275ce96611afa00910f4026825e42641bec02f70663fb585258b',
        'd63cb1e11373807362632cae45b51263eb97ecbc8168a2ea6af85958a3f74c86',
    ): (141, 10, 6),
}


class PublicationError(RuntimeError):
    """A source, ownership, or provider boundary prevented publication."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=45, check=False,
    )
    if result.returncode:
        raise PublicationError(f"git {args[0]} failed ({result.returncode})")
    return result.stdout


def gh_verified(revision: str, *, require_current_main: bool = True) -> None:
    query = (
        "query($owner:String!,$name:String!,$oid:GitObjectID!){"
        "repository(owner:$owner,name:$name){"
        "defaultBranchRef{target{... on Commit{oid}}}"
        "object(oid:$oid){... on Commit{oid signature{isValid state}}}"
        "}}"
    )
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}", "-f", "owner=szl-holdings",
         "-f", "name=szl-second-brain", "-f", f"oid={revision}"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=45, check=False,
    )
    if result.returncode:
        raise PublicationError("GitHub signature readback unavailable")
    proof = strict_json(result.stdout)
    repository = proof.get("data", {}).get("repository", {})
    commit = repository.get("object") or {}
    main_oid = repository.get("defaultBranchRef", {}).get("target", {}).get("oid")
    if ((require_current_main and main_oid != revision) or commit.get("oid") != revision
            or commit.get("signature") != {"isValid": True, "state": "VALID"}):
        raise PublicationError("GitHub source signature is not valid")


def canonical_source() -> str:
    remote = git("remote", "get-url", "origin").decode().strip()
    if remote != f"https://github.com/{GITHUB_REPO}.git":
        raise PublicationError("origin is not the canonical GitHub repository")
    if git("status", "--porcelain"):
        raise PublicationError("source checkout is dirty")
    revision = git("rev-parse", "HEAD").decode().strip()
    if not SHA40.fullmatch(revision):
        raise PublicationError("source revision is malformed")
    if git("rev-parse", "refs/remotes/origin/main").decode().strip() != revision:
        raise PublicationError("checkout is not the fetched main revision")
    remote_main = git("ls-remote", "origin", "refs/heads/main").decode().split()[0]
    if remote_main != revision:
        raise PublicationError("GitHub main moved; refresh the checkout")
    gh_verified(revision)
    return revision


def committed_bytes(revision: str, path: str) -> bytes:
    data = git("show", f"{revision}:{path}")
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise PublicationError(f"source file unavailable or too large: {path}")
    return data


def reviewed_source_counts(source: dict[str, bytes]) -> tuple[int, int, int]:
    """Accept exact source sets, never a matching row count alone."""
    if set(source) != set(SOURCE_PATHS):
        raise PublicationError("publication source file set changed")
    if any(type(data) is not bytes or not 0 < len(data) <= MAX_SOURCE_BYTES
           for data in source.values()):
        raise PublicationError("publication source bytes are invalid or oversized")
    identity = tuple(sha256(source[path]) for path in SOURCE_PATHS)
    counts = REVIEWED_INPUTS.get(identity)
    if counts is None:
        raise PublicationError("source set has not been reviewed for handle projection")
    return counts


def projection(revision: str, source: dict[str, bytes]) -> dict[str, bytes]:
    expected_counts = reviewed_source_counts(source)
    rows_bytes = source[SOURCE_PATHS[0]]
    lines = rows_bytes.splitlines(keepends=True)
    if not lines or any(not line.endswith(b"\n") for line in lines):
        raise PublicationError("candidate JSONL is incomplete")
    rows = [strict_json(line) for line in lines]
    if rows_bytes != b"".join(canonical_bytes(row) + b"\n" for row in rows):
        raise PublicationError("candidate JSONL is not canonical")
    state = strict_json(source[SOURCE_PATHS[1]])
    snapshot = strict_json(source[SOURCE_PATHS[2]])
    FrontierIndex._validate(state, rows)
    records = validate_snapshot(snapshot)
    if (len(rows), state.get("source_count"), len(records)) != expected_counts:
        raise PublicationError("reviewed snapshot count changed")
    research_rows = [row["provenance"] for row in rows if row.get("source_kind") == "research-metadata"]
    snapshot_rows = [
        {key: value for key, value in record.items()
         if key not in {"capture_base64", "candidate_state"}}
        for record in records
    ]
    if sorted(map(canonical_bytes, research_rows)) != sorted(map(canonical_bytes, snapshot_rows)):
        raise PublicationError("research rows do not match the reviewed metadata snapshot")
    stated_digest = state.get("state_sha256")
    state_without_digest = {key: value for key, value in state.items() if key != "state_sha256"}
    if stated_digest != sha256(canonical_bytes(state_without_digest)):
        raise PublicationError("frontier state digest mismatch")

    handles = []
    for row in rows:
        candidate = FrontierCandidate(
            candidate_id=row["id"], title=row["title"], content=row["content"],
            content_sha256=row["content_sha256"],
            source_repository=row["source_repository"],
            source_revision=row["source_revision"],
            source_path=row["source_path"], source_kind=row["source_kind"],
            quant_domain=row.get("quant_domain"), admission=row["admission"],
            revision_kind=row.get("source_revision_kind", "git-sha1"),
            provenance=row.get("provenance"),
        )
        handle = candidate.handle()
        if "content" in handle or "provenance" in handle:
            raise PublicationError("raw candidate content entered public projection")
        handles.append(handle)
    handles_bytes = b"".join(canonical_bytes(row) + b"\n" for row in handles)
    published: dict[str, bytes] = {
        "frontier-handles.public.jsonl": handles_bytes,
        "frontier-state.v1.json": source[SOURCE_PATHS[1]],
    }

    template = committed_bytes(revision, CARD_TEMPLATE).decode("utf-8")
    count_markers = {
        "__CANDIDATE_COUNT__": str(len(rows)),
        "__DETAIL_CANDIDATE_COUNT__": str(len(rows)),
        "__GIT_CANDIDATE_COUNT__": str(len(rows) - len(records)),
    }
    if any(marker in template for marker in count_markers):
        for marker, value in count_markers.items():
            if template.count(marker) != 1:
                raise PublicationError(f"card count marker absent or duplicated: {marker}")
            template = template.replace(marker, value)
    elif expected_counts != (137, 10, 6):
        # Historical signed 137-row cards predate these markers. Preserve their
        # exact bytes when rebuilding the previous source-owned publication.
        raise PublicationError("current card count markers are absent")
    replacements = {
        "__SOURCE_SHA__": revision,
        "__CANDIDATE_SHA256__": sha256(rows_bytes),
        "__HANDLE_SHA256__": sha256(handles_bytes),
        "__STATE_SHA256__": sha256(source[SOURCE_PATHS[1]]),
        "__RESEARCH_SHA256__": sha256(source[SOURCE_PATHS[2]]),
        "__CANDIDATE_SET_SHA256__": state["candidate_set_sha256"],
    }
    for marker, value in replacements.items():
        if template.count(marker) != 1:
            raise PublicationError(f"card marker absent or duplicated: {marker}")
        template = template.replace(marker, value)
    published["README.md"] = template.encode("utf-8")
    manifest = {
        "schema": "szl.second-brain.hf-frontier-publication/v1",
        "source_repository": GITHUB_REPO,
        "source_revision": revision,
        "target_dataset": HF_REPO,
        "candidate_count": len(rows),
        "source_count": state["source_count"],
        "research_metadata_count": len(records),
        "candidate_set_sha256": state["candidate_set_sha256"],
        "state": "DISCOVERED_REVIEW_REQUIRED",
        "content_projection": "HANDLES_ONLY",
        "training_authority": "NONE",
        "promotion_authority": "NONE",
        "execution_authority": "NONE",
        "source_files": {
            path: {"sha256": sha256(data), "bytes": len(data)}
            for path, data in source.items()
        },
        "published_files": {
            path: {"sha256": sha256(data), "bytes": len(data)}
            for path, data in published.items()
        },
    }
    published["publication.json"] = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    return published


def build(revision: str) -> dict[str, bytes]:
    return projection(revision, {path: committed_bytes(revision, path) for path in SOURCE_PATHS})


def _readback(api: Any, revision: str, expected: dict[str, bytes]) -> None:
    from huggingface_hub import hf_hub_download

    info = api.repo_info(HF_REPO, repo_type="dataset", revision=revision)
    if info.sha != revision or info.private:
        raise PublicationError("Hub identity or visibility readback mismatch")
    actual_paths = {item.rfilename for item in info.siblings or []}
    if actual_paths - set(expected) - {".gitattributes"} or set(expected) - actual_paths:
        raise PublicationError("Hub file set differs from the source-owned publication")
    for path, data in expected.items():
        local = Path(hf_hub_download(
            HF_REPO, path, repo_type="dataset", revision=revision,
            force_download=True,
        ))
        if local.read_bytes() != data:
            raise PublicationError(f"Hub byte mismatch: {path}")


def publish(api: Any, expected: dict[str, bytes], *, expected_hub_revision: str | None = None) -> tuple[str, str]:
    from huggingface_hub import CommitOperationAdd
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import RepositoryNotFoundError

    identity = api.whoami()
    if not any(org.get("name") == "SZLHOLDINGS" and org.get("roleInOrg") == "admin"
               for org in identity.get("orgs", [])):
        raise PublicationError("cached Hugging Face identity lacks SZLHOLDINGS admin role")
    try:
        prior = api.repo_info(HF_REPO, repo_type="dataset")
    except RepositoryNotFoundError:
        prior = None
    if prior is not None:
        try:
            _readback(api, prior.sha, expected)
        except Exception as exc:
            if expected_hub_revision is None or prior.sha != expected_hub_revision:
                raise PublicationError("target dataset differs; exact current Hub revision required") from exc
            manifest_path = Path(hf_hub_download(
                HF_REPO, "publication.json", repo_type="dataset", revision=prior.sha,
                force_download=True,
            ))
            prior_manifest = strict_json(manifest_path.read_bytes())
            prior_source = prior_manifest.get("source_revision")
            if (prior_manifest.get("schema") != "szl.second-brain.hf-frontier-publication/v1"
                    or prior_manifest.get("source_repository") != GITHUB_REPO
                    or prior_manifest.get("target_dataset") != HF_REPO
                    or prior_manifest.get("content_projection") != "HANDLES_ONLY"
                    or not isinstance(prior_source, str) or not SHA40.fullmatch(prior_source)
                    or any(prior_manifest.get(key) != "NONE" for key in
                           ("training_authority", "promotion_authority", "execution_authority"))):
                raise PublicationError("prior Hub publication ownership is invalid")
            current_source = strict_json(expected["publication.json"])["source_revision"]
            git("merge-base", "--is-ancestor", prior_source, current_source)
            gh_verified(prior_source, require_current_main=False)
            _readback(api, prior.sha, build(prior_source))
            operations = [
                CommitOperationAdd(path_in_repo=path, path_or_fileobj=io.BytesIO(data))
                for path, data in expected.items()
            ]
            commit = api.create_commit(
                repo_id=HF_REPO, repo_type="dataset", operations=operations,
                commit_message="Correct Second Brain frontier review status",
                parent_commit=prior.sha,
            )
            _readback(api, commit.oid, expected)
            return "UPDATED_AND_VERIFIED", commit.oid
        return "ALREADY_PUBLISHED", prior.sha

    if expected_hub_revision is not None:
        raise PublicationError("expected Hub revision supplied but dataset is absent")

    api.create_repo(HF_REPO, repo_type="dataset", private=False, exist_ok=False)
    empty = api.repo_info(HF_REPO, repo_type="dataset")
    if empty.private or {item.rfilename for item in empty.siblings or []} - {".gitattributes"}:
        raise PublicationError("new dataset has unexpected content or visibility")
    operations = [
        CommitOperationAdd(path_in_repo=path, path_or_fileobj=io.BytesIO(data))
        for path, data in expected.items()
    ]
    commit = api.create_commit(
        repo_id=HF_REPO, repo_type="dataset", operations=operations,
        commit_message="Publish source-bound Second Brain review handles",
        parent_commit=empty.sha,
    )
    _readback(api, commit.oid, expected)
    return "PUBLISHED_AND_VERIFIED", commit.oid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="create and publish the fixed dataset")
    parser.add_argument("--expected-hub-revision", help="exact current Hub SHA for a guarded update")
    parser.add_argument("--receipt", type=Path, required=True, help="new receipt path outside the source checkout")
    args = parser.parse_args()
    if args.expected_hub_revision is not None and not SHA40.fullmatch(args.expected_hub_revision):
        raise PublicationError("expected Hub revision is malformed")
    if args.receipt.resolve().is_relative_to(ROOT.resolve()):
        raise PublicationError("receipt must be outside the source checkout")
    if args.receipt.exists():
        raise PublicationError("receipt path already exists")
    intent_path = args.receipt.with_name(args.receipt.stem + ".intent" + args.receipt.suffix)
    if args.apply and intent_path.exists():
        raise PublicationError("apply intent path already exists")
    revision = canonical_source()
    expected = build(revision)
    state, hub_revision = "PLAN_VERIFIED_SOURCE", None
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    if args.apply:
        from huggingface_hub import HfApi
        intent = {
            "schema": "szl.second-brain.hf-frontier-publication-intent/v1",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "state": "APPLY_REQUESTED_NO_PROVIDER_PROOF",
            "source_revision": revision,
            "target_dataset": HF_REPO,
            "expected_hub_revision": args.expected_hub_revision,
            "published_file_sha256": {path: sha256(data) for path, data in expected.items()},
        }
        with intent_path.open("x", encoding="utf-8") as stream:
            json.dump(intent, stream, sort_keys=True, indent=2)
            stream.write("\n")
        try:
            state, hub_revision = publish(
                HfApi(), expected, expected_hub_revision=args.expected_hub_revision
            )
        except Exception as exc:
            failure = {
                **intent,
                "schema": "szl.second-brain.hf-frontier-publication-receipt/v1",
                "state": "PROVIDER_OUTCOME_UNKNOWN",
                "provider_mutation": "UNKNOWN_AFTER_APPLY_REQUEST",
                "error_type": type(exc).__name__,
            }
            with args.receipt.open("x", encoding="utf-8") as stream:
                json.dump(failure, stream, sort_keys=True, indent=2)
                stream.write("\n")
            raise
    receipt = {
        "schema": "szl.second-brain.hf-frontier-publication-receipt/v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "source_revision": revision,
        "target_dataset": HF_REPO,
        "hub_revision": hub_revision,
        "provider_mutation": bool(args.apply and state in {"PUBLISHED_AND_VERIFIED", "UPDATED_AND_VERIFIED"}),
        "expected_hub_revision": args.expected_hub_revision,
        "published_file_sha256": {path: sha256(data) for path, data in expected.items()},
    }
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
