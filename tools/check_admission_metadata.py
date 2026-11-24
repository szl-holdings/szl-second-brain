#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Fail unless every claim in the HIRAG admission sidecar is true in this checkout's git history.

Recomputes, read-only:
  * that the sidecar's source_commit is a mainline (first-parent) commit of HEAD that
    touched data/brain-corpus.public.jsonl. A pull-request branch commit is refused: a
    squash merge drops it from main, and main would then cite a commit it does not have;
  * that the commit's committer time equals ingested_at.unix_s, and utc renders it;
  * that the corpus bytes at that commit hash to the sidecar's corpus_sha256.

It then reports whether the sidecar is CURRENT (it names the working-tree corpus bytes)
or STALE (the corpus changed after the named commit). STALE is not a failure here: no
commit time can honestly be recorded for corpus bytes before they land on main, and the
served opt-in already fails closed on a stale sidecar (BLOCKED, METADATA_GENERATION_MISMATCH).
A follow-up change regenerates the sidecar from the mainline commit that landed the bytes.

A shallow clone or a missing git binary is a failure here (CI uses fetch-depth 0), never a
skipped check. This does not verify the commit signature; the sidecar says NOT_VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CORPUS = "data/brain-corpus.public.jsonl"
SIDECAR = "data/corpus-admission-metadata.v1.json"


class AdmissionMetadataError(Exception):
    """A sidecar claim does not match what git history records for the corpus."""


class HistoryUnavailable(AdmissionMetadataError):
    """The checkout is not a full-history git repository, so no claim can be recomputed."""


def _git(root: Path, *args: str, text: bool = True):
    # -C root is authoritative: an exported GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE must not redirect the check.
    env = {key: value for key, value in os.environ.items()
           if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=text, check=False, env=env)


def check(root: Path) -> dict:
    stamp_file = json.loads((root / SIDECAR).read_text(encoding="utf-8"))
    stamp = stamp_file["ingested_at"]
    commit, unix_s = stamp["source_commit"], stamp["unix_s"]
    try:
        shallow = _git(root, "rev-parse", "--is-shallow-repository")
    except OSError as exc:
        raise HistoryUnavailable("git is not available") from exc
    if shallow.returncode != 0:
        raise HistoryUnavailable("not a git checkout")
    if shallow.stdout.strip() != "false":
        raise HistoryUnavailable("shallow git history")
    # From here on the history is complete, so an absent or off-mainline commit is a binding error.
    mainline = {}
    for line in _git(root, "log", "--first-parent", "--format=%H %ct", "HEAD", "--", CORPUS).stdout.splitlines():
        sha, _, ct = line.partition(" ")
        mainline[sha] = ct
    if commit not in mainline:
        if _git(root, "cat-file", "-e", commit + "^{commit}").returncode != 0:
            raise AdmissionMetadataError("sidecar source_commit is absent from this full-history checkout: " + commit)
        raise AdmissionMetadataError("sidecar source_commit is not a mainline (first-parent) commit of HEAD that "
                                     "touched the corpus; cite the commit that landed the corpus on main: " + commit)
    if mainline[commit] != str(unix_s):
        raise AdmissionMetadataError(f"sidecar unix_s {unix_s} is not the committer time {mainline[commit]} of {commit}")
    if stamp["utc"] != datetime.fromtimestamp(unix_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"):
        raise AdmissionMetadataError("sidecar utc does not match unix_s")
    at_commit = _git(root, "show", f"{commit}:{CORPUS}", text=False)
    if at_commit.returncode != 0:
        raise AdmissionMetadataError("corpus not readable at the admission commit")
    if hashlib.sha256(at_commit.stdout).hexdigest() != stamp_file["corpus_sha256"]:
        raise AdmissionMetadataError("corpus bytes at the admission commit differ from the sidecar corpus_sha256")
    working = hashlib.sha256((root / CORPUS).read_bytes()).hexdigest()
    return {"commit": commit, "unix_s": unix_s, "corpus_sha256": stamp_file["corpus_sha256"],
            "working_corpus_sha256": working,
            "status": "CURRENT" if working == stamp_file["corpus_sha256"] else "STALE"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        result = check(root)
    except AdmissionMetadataError as exc:
        print("admission metadata check FAILED:", exc, file=sys.stderr)
        return 1
    print("admission metadata claims match git history:", json.dumps(result, sort_keys=True))
    if result["status"] == "STALE":
        print("admission metadata is STALE: the corpus changed after the cited commit, so the "
              "SECOND_BRAIN_HIRAG_ADMISSION opt-in BLOCKS (METADATA_GENERATION_MISMATCH) until the "
              "sidecar is regenerated from the mainline commit that landed the current corpus.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
