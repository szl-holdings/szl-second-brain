#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect up to twelve explicit public metadata IDs into a review snapshot.

Use only when this collector has exclusive arXiv ownership across all controlled
machines. An exclusive local lock prevents accidental concurrent local runs;
there are no retries, background services, paper downloads, or API credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from second_brain.public_research import (  # noqa: E402
    PublicMetadataClient, ResearchBoundaryError, canonical_bytes,
    digest, merge_captures, strict_json,
    identifier_url,
)
from scripts.refresh_frontier_memory import atomic_write  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arxiv", action="append", default=[])
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--exclusive-arxiv", action="store_true", help="Confirm aggregate collector coordination, not API access permission")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data/public-research-metadata.v1.json")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    requests = [("arxiv", value) for value in args.arxiv] + [("crossref", value) for value in args.doi]
    if not 1 <= len(requests) <= 12 or len(set(requests)) != len(requests):
        parser.error("require one to twelve distinct identifiers")
    if args.arxiv and not args.exclusive_arxiv:
        parser.error("coordinate aggregate arXiv ownership before collection")
    for provider, identifier in requests:
        identifier_url(provider, identifier)
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    lock = args.snapshot.parent / ".public-research-collector.lock"
    handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(handle, str(os.getpid()).encode("ascii"))
        previous = strict_json(args.snapshot.read_bytes()) if args.snapshot.exists() else None
        client = PublicMetadataClient()
        captures = []
        for provider, identifier in requests:
            observed = datetime.now(timezone.utc).isoformat()
            captures.append(client.capture(provider, identifier, observed_at=observed))
        snapshot = merge_captures(previous, captures)
        payload = canonical_bytes(snapshot) + b"\n"
        atomic_write(args.snapshot, payload)
        report = {
            "schema": "szl.second-brain.public-research-collection/v1",
            "state": "DISCOVERED_REVIEW_REQUIRED", "snapshot_sha256": digest(payload),
            "record_count": len(snapshot["records"]), "request_count": len(captures),
            "captures": [{key: value for key, value in row.items() if key not in {"capture_base64", "metadata"}} for row in captures],
            "api_keys_used": False, "paper_text_fetched": False,
            "training_authority": "NONE", "promotion_authority": "NONE", "execution_authority": "NONE",
        }
        atomic_write(args.report, (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        print(json.dumps({"state": report["state"], "record_count": report["record_count"], "snapshot_sha256": report["snapshot_sha256"]}, sort_keys=True))
        return 0
    except ResearchBoundaryError as exc:
        atomic_write(args.report, (json.dumps({"schema": "szl.second-brain.public-research-collection/v1", "state": "BLOCKED", "reason": str(exc), "requested": requests, "previous_snapshot_preserved": True, "api_keys_used": False}, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        os.close(handle)
        lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
