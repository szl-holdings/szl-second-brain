"""Read-only exact-source comparison for the public SZL Second Brain Space.

Never signs, publishes, deploys, downloads models or hydrates private graph data.
A matching source tree is not evidence of runtime health, API readiness, or
production admission. Missing provider access and moving commits fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "szl.second-brain.public-space-parity/v1"
GITHUB_REPO = "szl-holdings/szl-second-brain"
SPACE_REPO = "SZLHOLDINGS/szl-second-brain"
SPACE_API = "https://huggingface.co/api/spaces/" + SPACE_REPO
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
MAX_HTTP_BYTES = 1_000_000
MAX_FILES = 1000
MAX_TREE_PAGES = 10
MAX_EXTRAS_DISPLAY = 30


class ParityHold(ValueError):
    """Insufficient or conflicting source/deployment observation."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ParityHold(code)


def pairs_strict(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def strict_json(raw: bytes):
    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs_strict,
            parse_constant=lambda _: require(False, "NONFINITE_JSON"),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ParityHold("INVALID_PROVIDER_JSON") from exc


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_page(url, opener, byte_budget):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "szl-second-brain-parity/1.0",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=10) as response:
            require(
                type(response.status) is int and response.status == 200,
                "PROVIDER_HTTP_NON_200",
            )
            raw = response.read(byte_budget + 1)
            require(len(raw) <= byte_budget, "PROVIDER_RESPONSE_OVERSIZE")
            links = response.headers.get_all("Link", [])
    except urllib.error.HTTPError as exc:
        raise ParityHold("PROVIDER_HTTP_" + str(exc.code)) from None
    except (OSError, TimeoutError) as exc:
        raise ParityHold("PROVIDER_TRANSPORT_" + type(exc).__name__) from None
    return strict_json(raw), links, len(raw)


def next_tree_url(links, tree_url):
    """Accept the Hub's single next link on exactly the original tree."""
    require(len(links) == 1, "PROVIDER_TREE_PAGINATION")
    match = re.fullmatch(r'\s*<([^<>\s]+)>\s*;\s*rel="next"\s*', links[0])
    require(match is not None, "PROVIDER_TREE_PAGINATION")
    url = match.group(1)
    path, _, query = url.partition("?")
    require(path == tree_url and "#" not in url, "PROVIDER_TREE_PAGINATION")
    try:
        params = urllib.parse.parse_qs(
            query, keep_blank_values=True, strict_parsing=True, max_num_fields=4
        )
    except ValueError:
        raise ParityHold("PROVIDER_TREE_PAGINATION") from None
    limits = params.get("limit", ["1000"])
    require(
        set(params) <= {"recursive", "expand", "limit", "cursor"}
        and params.get("recursive") == ["true"]
        and params.get("expand", ["false"]) == ["false"]
        and len(params.get("cursor", [])) == 1
        and bool(params["cursor"][0])
        and len(limits) == 1
        and re.fullmatch(r"[1-9][0-9]{0,3}", limits[0]) is not None
        and int(limits[0]) <= 1000,
        "PROVIDER_TREE_PAGINATION",
    )
    return url


def provider_json(url: str, *, opener=None):
    """Only fixed Hugging Face public API paths. No credentials or redirects."""
    opener = opener or urllib.request.build_opener(NoRedirect())
    if url == SPACE_API:
        return read_page(url, opener, MAX_HTTP_BYTES)[0]
    tree_url, _, query = url.partition("?")
    prefix = SPACE_API + "/tree/"
    require(
        tree_url.startswith(prefix)
        and SHA40.fullmatch(tree_url[len(prefix):]) is not None
        and query == "recursive=true",
        "PROVIDER_URL_NOT_ALLOWLISTED",
    )
    rows = []
    seen = set()
    byte_budget = MAX_HTTP_BYTES
    while True:
        require(
            url not in seen and len(seen) < MAX_TREE_PAGES, "PROVIDER_TREE_PAGINATION"
        )
        seen.add(url)
        page, links, size = read_page(url, opener, byte_budget)
        require(type(page) is list, "PROVIDER_TREE_INVALID")
        require(len(rows) + len(page) <= MAX_FILES, "PROVIDER_TREE_LIMIT")
        rows.extend(page)
        if not links:
            return rows
        require(len(rows) < MAX_FILES, "PROVIDER_TREE_LIMIT")
        byte_budget -= size
        url = next_tree_url(links, tree_url)


def commit_and_index(root: Path, expected_commit: str):
    require(SHA40.fullmatch(expected_commit) is not None, "EXPECTED_COMMIT_INVALID")
    require(root.is_dir() and not root.is_symlink(), "SOURCE_ROOT_UNAVAILABLE")
    try:
        head = (
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            .decode("ascii")
            .strip()
        )
        status = subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
            ],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        raw = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "--stage", "-z"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ParityHold("SOURCE_GIT_UNAVAILABLE") from None
    require(head == expected_commit, "SOURCE_HEAD_DRIFT")
    require(not status, "SOURCE_TRACKED_DIRTY")
    index = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            meta, path = record.split(b"\t", 1)
            mode, sha, stage = meta.split(b" ")
            name = path.decode("utf-8", "strict")
        except (ValueError, UnicodeError):
            raise ParityHold("SOURCE_INDEX_INVALID") from None
        require(
            stage == b"0"
            and mode in (b"100644", b"100755")
            and SHA40.fullmatch(sha.decode("ascii")) is not None,
            "SOURCE_INDEX_UNSUPPORTED_ENTRY",
        )
        require(name not in index, "SOURCE_INDEX_DUPLICATE")
        index[name] = sha.decode("ascii")
    return index


def included_source_oids(root: Path, index: dict):
    """Reuse the existing owner-controlled COPY-closure validator."""
    module_path = root / "tools" / "check_space_payload.py"
    require(module_path.is_file(), "PAYLOAD_CHECKER_MISSING")
    spec = importlib.util.spec_from_file_location(
        "szl_space_payload_checker", module_path
    )
    require(
        spec is not None and spec.loader is not None, "PAYLOAD_CHECKER_NOT_IMPORTABLE"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    include = mod.evaluate(root)
    manifest = strict_json(
        (root / "publishing" / "space-payload.manifest.json").read_bytes()
    )
    require(
        type(manifest) is dict
        and manifest.get("source_repository") == GITHUB_REPO
        and manifest.get("target_space") == SPACE_REPO
        and manifest.get("publish") is False,
        "SOURCE_PUBLISH_CONTROL_CHANGED",
    )
    require(
        type(include) in (set, frozenset) and 1 <= len(include) <= MAX_FILES,
        "SOURCE_PAYLOAD_SIZE",
    )
    require(all(path in index for path in include), "PAYLOAD_NOT_IN_GIT_INDEX")
    return {path: index[path] for path in sorted(include)}


def compare_file_oids(expected: dict, remote_tree):
    """File identities are Git blob SHA-1, not proof of executing those bytes."""
    require(
        type(expected) is dict and 1 <= len(expected) <= MAX_FILES,
        "EXPECTED_SOURCE_INVALID",
    )
    require(
        type(remote_tree) is list and len(remote_tree) <= MAX_FILES,
        "PROVIDER_TREE_INVALID",
    )
    observed = {}
    for item in remote_tree:
        require(type(item) is dict, "PROVIDER_TREE_ROW")
        if item.get("type") != "file":
            continue
        path, oid = item.get("path"), item.get("oid")
        require(
            type(path) is str
            and len(path) <= 512
            and type(oid) is str
            and SHA40.fullmatch(oid) is not None,
            "PROVIDER_BLOB_INVALID",
        )
        require(path not in observed, "PROVIDER_TREE_DUPLICATE")
        observed[path] = oid

    absent = sorted(set(expected) - set(observed))
    changed = [
        {
            "path": path,
            "expected_git_blob": expected[path],
            "observed_space_blob": observed[path],
        }
        for path in sorted(set(expected) & set(observed))
        if expected[path] != observed[path]
    ]
    extras = sorted(set(observed) - set(expected))
    matching = len(expected) - len(absent) - len(changed)
    return {
        "required_source_files": len(expected),
        "matching_git_blobs": matching,
        "missing_paths": absent,
        "different_blobs": changed,
        "extra_space_paths_count": len(extras),
        "extra_space_paths_sample": extras[:MAX_EXTRAS_DISPLAY],
        "state": "SOURCE_PARITY_MATCH_EXTRA_REVIEW_REQUIRED"
        if not absent and not changed and extras
        else (
            "SOURCE_PARITY_MATCH_ONLY"
            if not absent and not changed
            else "SOURCE_DEPLOYMENT_DRIFT"
        ),
    }


def verify(root: Path, expected_commit: str, *, fetch=provider_json):
    local_index = commit_and_index(root, expected_commit)
    expected = included_source_oids(root, local_index)
    before = fetch(SPACE_API)
    require(type(before) is dict, "SPACE_METADATA_INVALID")
    remote_sha = before.get("sha")
    require(
        type(remote_sha) is str and SHA40.fullmatch(remote_sha) is not None,
        "SPACE_SHA_INVALID",
    )
    tree = fetch(SPACE_API + "/tree/" + remote_sha + "?recursive=true")
    differences = compare_file_oids(expected, tree)
    after = fetch(SPACE_API)
    require(
        type(after) is dict and after.get("sha") == remote_sha,
        "SPACE_SHA_MOVED_DURING_READ",
    )
    require(
        commit_and_index(root, expected_commit) == local_index,
        "SOURCE_INDEX_MOVED_DURING_READ",
    )
    response = {
        "schema": SCHEMA,
        "observed_utc": datetime.now(UTC).isoformat(),
        "source_repository": GITHUB_REPO,
        "source_commit": expected_commit,
        "remote_space": SPACE_REPO,
        "space_commit": remote_sha,
        "provider_stage": before.get("runtime", {}).get("stage")
        if type(before.get("runtime")) is dict
        else None,
        "source_publish_manifest": "FALSE_DO_NOT_UPLOAD",
        "parity": differences,
        "model_inference_verified": False,
        "public_api_readiness_verified": False,
        "provider_deployment_authorized": False,
        "private_graph_accessed": False,
        "credential_or_provider_write_used": False,
        "receipt_signed": False,
    }
    return response


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bounded public HF Space source-file parity witness; never publishes."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-commit", type=str, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.source_root, args.expected_commit)
        raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")
        with args.out.open("xb") as f:
            f.write(raw)
        checksum = hashlib.sha256(raw).hexdigest()
        print(
            json.dumps(
                {
                    "state": result["parity"]["state"],
                    "source_commit": result["source_commit"],
                    "remote_space_commit": result["space_commit"],
                    "required_files": result["parity"]["required_source_files"],
                    "matching_files": result["parity"]["matching_git_blobs"],
                    "changed_files": len(result["parity"]["different_blobs"]),
                    "missing_files": len(result["parity"]["missing_paths"]),
                    "extra_files": result["parity"]["extra_space_paths_count"],
                    "receipt_sha256": checksum,
                    "authorized_to_publish": False,
                },
                sort_keys=True,
            )
        )
        # Every result is an observation, not deployment admission. Drift HOLD=2.
        return 0 if result["parity"]["state"] == "SOURCE_PARITY_MATCH_ONLY" else 2
    except (ParityHold, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "state": "UNAVAILABLE",
                    "reason": str(exc)
                    if isinstance(exc, ParityHold)
                    else type(exc).__name__,
                    "authorized_to_publish": False,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
