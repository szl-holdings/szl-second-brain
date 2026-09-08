from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "neomme-cache-1.4.1-hf-cpu-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def test_neomme_cache_evidence_is_complete_and_non_promotional() -> None:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert value["schema"] == "szl.brain.cache-restart-observation/v1"
    assert value["provider"]["status"] == "COMPLETED"
    assert value["provider"]["job_id"] == "6a9ff8ff8e5f7b7fd14cbbe3"
    assert SHA40.fullmatch(value["source"]["candidate_revision"])
    assert SHA40.fullmatch(value["source"]["protected_main_merge"])
    assert value["corpus"]["indexed_rows"] == 575
    assert value["corpus"]["diagnostic_queries_each_process"] == 8
    assert len(value["warm_process"]["query_seconds"]) == 8
    assert len(value["fresh_process_after_index_restore"]["query_seconds"]) == 8
    assert value["persisted_index"]["fresh_process_rankings_identical"] is True
    assert value["persisted_index"]["all_hydration_digests_match"] is True
    assert value["warm_process"]["median_seconds"] < 1.0
    assert value["fresh_process_after_index_restore"]["cache"]["misses"] > 0

    for digest in (
        value["model"]["model_lock_sha256"],
        value["corpus"]["corpus_sha256"],
        value["persisted_index"]["sha256"],
        value["receipts"]["build_sha256"],
        value["receipts"]["restore_sha256"],
    ):
        assert SHA256.fullmatch(digest)

    boundary = value["truth_boundary"]
    assert boundary == {
        "status": "PASS",
        "training_performed": False,
        "production_promoted": False,
        "private_graph_loaded": False,
        "independent_relevance_evaluation": False,
        "runtime_qualification_implied": False,
        "sla_claimed": False,
        "private_memory_durability_claimed": False,
    }
