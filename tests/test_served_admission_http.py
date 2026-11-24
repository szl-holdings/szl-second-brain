#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Fresh served process: the HIRAG opt-in changes what app_refinement serves, and only when set.

The opt-in case is the negative control for this change: on a tree without the served
wiring the variable is ignored, admission stays NOT_APPLIED and handles are returned.
This file deliberately imports nothing from the change so it runs against such a tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPT_IN_ENV = "SECOND_BRAIN_HIRAG_ADMISSION"
SIDECAR = ROOT / "data" / "corpus-admission-metadata.v1.json"
CORPUS = ROOT / "data" / "brain-corpus.public.jsonl"
PROBE = r"""
import json
from fastapi.testclient import TestClient
from app_refinement import app
client = TestClient(app)
response = client.get("/api/v1/hybrid", params={"q": "formula authority", "k": 6})
hybrid = response.json()
capabilities = client.get("/api/v1/retrieval-capabilities").json()
print(json.dumps({"status": response.status_code, "state": hybrid["state"], "handles": hybrid.get("handles"),
                  "receipt": hybrid.get("ranking_receipt"),
                  "public_runtime_mode": capabilities["public_runtime_mode"],
                  "hirag_admission": capabilities.get("hirag_admission")}))
"""


def _serve(value: str | None) -> dict:
    env = {key: item for key, item in os.environ.items() if key != OPT_IN_ENV}
    if value is not None:
        env[OPT_IN_ENV] = value
    env["PYTHONPATH"] = str(ROOT)
    done = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=180, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def _sidecar_names_served_corpus() -> bool:
    if not SIDECAR.exists():
        return False
    return json.loads(SIDECAR.read_text(encoding="utf-8"))["corpus_sha256"] == hashlib.sha256(CORPUS.read_bytes()).hexdigest()


def test_opt_in_applies_hirag_admission_in_a_fresh_served_process():
    served = _serve("1")
    assert served["public_runtime_mode"] == "BM25_ONLY"
    if not _sidecar_names_served_corpus():
        # Missing or stale metadata: the requested gate refuses; it never serves an ungated answer.
        assert served["status"] == 422 and served["state"] == "BLOCKED", served
        assert served["hirag_admission"]["state"] == "BLOCKED"
        return
    receipt = served["receipt"]
    assert receipt["admission"] == "APPLIED", receipt["admission"]
    assert receipt["mode"] == "BM25_ONLY+HIRAG_ADMISSION"
    assert receipt["admission_detail"]["admitted_count"] == 0
    assert served["handles"] == [] and served["state"] == "ABSTAIN_NO_GROUNDED_HANDLES"
    assert served["hirag_admission"]["state"] == "CONFIGURED"


def test_unset_opt_in_serves_bm25_only_and_says_why_in_a_fresh_process():
    served = _serve(None)
    receipt = served["receipt"]
    assert receipt["admission"] == "NOT_APPLIED" and receipt["mode"] == "BM25_ONLY"
    assert "admission_runtime" not in receipt and served["handles"]
    assert served["public_runtime_mode"] == "BM25_ONLY"
    assert served["hirag_admission"]["reason"] == "OPT_IN_NOT_ENABLED"
