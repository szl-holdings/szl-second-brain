#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Explicit full-public-corpus neural execution probe, never a relevance claim."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import resource
import time

from second_brain import AuthorizedHydrator, HybridSecondBrain
from second_brain.neomme import LOCK_PATH, NeoMME, PublicNeuralBrain, canonical, file_sha256

QUERIES = (
    "Lambda uniqueness conjecture 1",
    "locked eight formula authority Lean proof",
    "evidence receipt provenance",
    "memory tenant isolation authorization",
    "Ouroboros bounded loops",
    "maritime sanctions screening",
    "governed model inference",
    "Living Anatomy observability",
)


def run(args):
    result = {"schema": "szl.brain.full-corpus-exercise/v1", "status": "NOT_EXECUTED",
              "source_repository": "szl-holdings/szl-second-brain", "source_revision": args.source_revision,
              "observed_at": datetime.now(timezone.utc).isoformat(), "queries": list(QUERIES),
              "independent_relevance_evaluation": False, "private_graph_loaded": False,
              "production_promoted": False, "training_performed": False,
              "receipt_kind": "UNSIGNED_EXECUTION_RECORD_NOT_AUTHORIZATION"}
    started = time.perf_counter()
    stage = "PLAN"
    try:
        if args.execute:
            if not args.model_dir or not args.index_path:
                raise ValueError("model directory and index path required")
            stage = "VERIFIED_NATIVE_MODEL_LOAD"
            print(json.dumps({"stage": stage}), flush=True)
            encoder = NeoMME(args.model_dir)
            brain = PublicNeuralBrain(encoder)
            if len(brain.corpus.rows) != 575:
                raise ValueError("unexpected public corpus count")
            stage = "RESTORE_INDEX" if args.restore_sha else "BUILD_ALL_PUBLIC_EMBEDDINGS"
            mark = time.perf_counter()
            print(json.dumps({"stage": stage}), flush=True)
            def progress(done, total):
                if done % 50 == 0 or done == total:
                    print(json.dumps({"rows_indexed": done, "total": total}), flush=True)
            seal = (brain.load(args.index_path, expected_sha256=args.restore_sha) if args.restore_sha
                    else brain.build(args.index_path, progress=progress))
            result["index_build_or_restore_seconds"] = time.perf_counter() - mark
            result["index_operation"] = "RESTORED" if args.restore_sha else "BUILT"
            result["indexed_rows"] = len(brain.corpus.rows)
            result["dense_dimensions"] = 1024
            result["index_bytes"] = args.index_path.stat().st_size
            result["index_sha256"] = seal
            result["binding"] = brain.binding
            stage = "HYBRID_RETRIEVAL_BODY_RERANK_AND_HYDRATION"
            controller = brain.coordinator(rerank=True)
            baseline = HybridSecondBrain(brain.sparse)
            known = {row.node_id: row.source for row in brain.corpus.rows}
            def authorize(principal, tenant, policy, node, source):
                return (principal == "cpu-public-probe" and tenant == "public-probe"
                        and policy == args.source_revision and known.get(node) == source)
            hydrator = AuthorizedHydrator(authorize, path=brain.sparse.path,
                                          expected_sha256=brain.generation_sha256)
            cases = []
            for query in QUERIES:
                mark = time.perf_counter()
                context = controller.context(query, k=6)
                elapsed = time.perf_counter() - mark
                if context["ranking_receipt"]["mode"] != "HYBRID_SPARSE_DENSE+RERANKER":
                    raise ValueError("neural path did not execute")
                hydration = hydrator.hydrate(context["handles"], principal_id="cpu-public-probe",
                    tenant_id="public-probe", policy_revision=args.source_revision)
                if hydration["evidence_set_sha256"] != context["evidence_set_sha256"]:
                    raise ValueError("context/hydration evidence mismatch")
                if not context["handles"] or context["corpus_n"] != 575:
                    raise ValueError("incomplete corpus query")
                sparse = baseline.context(query, k=6)
                cases.append({"query": query, "seconds": elapsed,
                              "baseline_node_ids": [h["nodeId"] for h in sparse["handles"]],
                              "candidate_node_ids": [h["nodeId"] for h in context["handles"]],
                              "evidence_set_sha256": context["evidence_set_sha256"],
                              "hydration_digest_match": True, "ranking_receipt": context["ranking_receipt"],
                              "cache_after_query": brain.cache_stats()})
                print(json.dumps({"query_executed": len(cases), "total": len(QUERIES), "seconds": elapsed}), flush=True)
            root = Path(__file__).resolve().parents[1]
            result.update({"status": "EXECUTED_PUBLIC_CORPUS", "cases": cases,
                           "model_lock_file_sha256": file_sha256(LOCK_PATH),
                           "source_files": {str(p): file_sha256(root / p) for p in
                               ("second_brain/corpus.py", "second_brain/embedding_cache.py", "second_brain/retrieve.py", "second_brain/hybrid.py",
                                "second_brain/neomme.py", "tools/neomme_corpus_probe.py")},
                           "cache": brain.cache_stats(),
                           "max_rss_bytes_including_dependencies": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                           "python": platform.python_version(), "platform": platform.platform(),
                           "limit": "575 public documents indexed; eight diagnostic queries, no independent qrels, no quality winner or live deployment claim."})
    except Exception as exc:
        result.update({"status": "FAILED", "failure_stage": stage, "error_type": type(exc).__name__})
    result["elapsed_seconds"] = time.perf_counter() - started
    result["receipt_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--index-path", type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--restore-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        parser.error("exact source revision required")
    if args.restore_sha and not re.fullmatch(r"[0-9a-f]{64}", args.restore_sha):
        parser.error("exact persisted index digest required")
    result = run(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return 1 if result["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
