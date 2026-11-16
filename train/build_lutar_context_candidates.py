#!/usr/bin/env python3
"""Export public Lutar context candidates; never train or modify existing corpora."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from second_brain.lutar_reference import curriculum_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = curriculum_candidates()
    # Exclusive creation preserves prior receipts. The owner selects the local output.
    with args.output.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(document, target, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({"state": document["state"], "count": document["count"],
                      "content_sha256": document["content_sha256"],
                      "training_authority": "NONE", "proof_completions": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
