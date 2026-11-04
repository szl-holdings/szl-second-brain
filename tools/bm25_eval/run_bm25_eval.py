#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline BM25 retrieval eval over the admitted 575-chunk public projection.

MEASURED baseline only. No dense embedder, reranker, GraphRAG, or HiRAG path.
Uses SecondBrainIndex lexical scoring (BM25-like TF saturation + IDF).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from second_brain.retrieve import PUBLIC_CHUNK_COUNT, SecondBrainIndex  # noqa: E402

QUERIES_PATH = Path(__file__).resolve().parent / "frozen_queries.v1.json"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
HANDLE_REQUIRED = ("nodeId", "nodeKind", "label")
SCHEMA = "szl.second-brain.bm25-eval.receipt/v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        )
        return out.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def load_queries(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "szl.second-brain.bm25-eval.queries/v1":
        raise SystemExit("unexpected query fixture schema")
    rows = data.get("queries")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise SystemExit("frozen query count must be 1..30")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate query id")
    return data


def rate(success: int, total: int) -> dict[str, Any]:
    return {
        "success": success,
        "total": total,
        "rate": round(success / total, 6) if total else None,
    }


def handle_fields_ok(handles: list[dict[str, Any]]) -> bool:
    for handle in handles:
        if not isinstance(handle, dict):
            return False
        if any(not handle.get(key) for key in HANDLE_REQUIRED):
            return False
        if "text" in handle or "_toks" in handle:
            return False
    return True


def evaluate(index: SecondBrainIndex, fixture: dict[str, Any], *, ks: tuple[int, ...]) -> dict[str, Any]:
    details = []
    retrieve_rows = []
    empty_abstain = []
    no_support = []

    for case in fixture["queries"]:
        intent = case["intent"]
        query = case["query"]
        relevant = set(case.get("relevant") or [])
        expect_cite = list(case.get("expect_cite") or [])
        max_k = max(ks)
        hit = index.search(query, k=max_k)
        ranked = [h["nodeId"] for h in hit["handles"]]
        handles_ok = handle_fields_ok(hit["handles"])
        per_k = {}
        for k in ks:
            top = ranked[:k]
            hits = len(relevant & set(top))
            per_k[f"@{k}"] = {
                "retrieved": top,
                "relevant_hits": hits,
                "relevant_total": len(relevant),
                "recall": round(hits / len(relevant), 6) if relevant else None,
                "all_required": bool(relevant) and hits == len(relevant),
                "cite_hit": bool(expect_cite) and set(expect_cite).issubset(set(top)),
            }
        row = {
            "id": case["id"],
            "intent": intent,
            "family": case.get("family"),
            "abstain_mode": case.get("abstain_mode"),
            "query": query,
            "ready": hit["ready"],
            "returned_k": hit["k"],
            "handles_ok": handles_ok,
            "relevant": sorted(relevant),
            "expect_cite": expect_cite,
            "ranked_ids": ranked,
            "scores": hit.get("scores") or [],
            "per_k": per_k,
        }
        details.append(row)
        if intent == "RETRIEVE":
            retrieve_rows.append(row)
        elif case.get("abstain_mode") == "EMPTY_INDEX":
            empty_abstain.append(row)
        else:
            no_support.append(row)

    def recall_summary(k: int) -> dict[str, Any]:
        micro_hits = sum(r["per_k"][f"@{k}"]["relevant_hits"] for r in retrieve_rows)
        micro_tot = sum(r["per_k"][f"@{k}"]["relevant_total"] for r in retrieve_rows)
        macros = [r["per_k"][f"@{k}"]["recall"] for r in retrieve_rows if r["relevant"]]
        all_req = sum(1 for r in retrieve_rows if r["per_k"][f"@{k}"]["all_required"])
        return {
            "micro_recall": rate(micro_hits, micro_tot),
            "macro_recall_mean": round(sum(macros) / len(macros), 6) if macros else None,
            "all_required": rate(all_req, len(retrieve_rows)),
        }

    def cite_summary(k: int) -> dict[str, Any]:
        cite_cases = [r for r in retrieve_rows if r["expect_cite"]]
        return rate(sum(1 for r in cite_cases if r["per_k"][f"@{k}"]["cite_hit"]), len(cite_cases))

    handle_cases = details
    handle_ok_n = sum(1 for r in handle_cases if r["handles_ok"])
    empty_ok = sum(1 for r in empty_abstain if r["ready"] is False and r["returned_k"] == 0)
    no_support_ready = sum(1 for r in no_support if r["ready"] is True)

    return {
        "retrieve_cases": len(retrieve_rows),
        "abstain_empty_index_cases": len(empty_abstain),
        "abstain_no_support_cases": len(no_support),
        "recall": {f"@{k}": recall_summary(k) for k in ks},
        "citation_gold_hit_rate": {f"@{k}": cite_summary(k) for k in ks},
        "handle_contract_ok": rate(handle_ok_n, len(handle_cases)),
        "abstention": {
            "empty_index_correct": rate(empty_ok, len(empty_abstain)),
            "empty_index_count_correct": empty_ok,
            "no_support_cases": len(no_support),
            "no_support_ready_true_count": no_support_ready,
            "no_support_ready_false_count": len(no_support) - no_support_ready,
            "note": (
                "EMPTY_INDEX expects ready=false (no lexical hit). "
                "NO_SUPPORT has no gold answer chunk; BM25 may still return "
                "weak lexical noise — counted as ready_true, not as correctness."
            ),
        },
        "details": details,
    }


def build_receipt(
    *,
    fixture: dict[str, Any],
    metrics: dict[str, Any],
    index: SecondBrainIndex,
    ks: tuple[int, ...],
    queries_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    corpus_path = index.path
    return {
        "schema": SCHEMA,
        "status": "MEASURED",
        "credit": "Stephen Lutar",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha(),
        "source_repository": "szl-holdings/szl-second-brain",
        "query_fixture_revision": fixture["revision"],
        "query_fixture_sha256": sha256_file(queries_path),
        "query_count": len(fixture["queries"]),
        "ks": list(ks),
        "retriever": {
            "kind": "SOFTWARE",
            "algorithm": "SecondBrainIndex BM25-like (TF/(TF+1.2)*IDF*qf; corpus-order tie-break)",
            "dense": False,
            "graph_rag": False,
            "hirag": False,
            "content_access": "HANDLES_ONLY",
            "index_is_model_weights": False,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "lambda_status": "CONJECTURE_1",
        },
        "corpus": {
            "path": str(corpus_path.relative_to(ROOT)) if corpus_path.is_relative_to(ROOT) else str(corpus_path),
            "chunk_count_loaded": index.n,
            "public_chunk_count_declared": PUBLIC_CHUNK_COUNT,
            "file_sha256": index.generation_sha256,
            "manifest_projection_sha256": manifest.get("projectionSha256"),
            "manifest_public_chunk_count": manifest.get("publicChunkCount"),
            "by_source": index.stats().get("by_source"),
            "secret_scan": manifest.get("secretScan"),
        },
        "limitations": [
            "Lexical overlap rank is never correctness.",
            "No dense embedder, reranker, or generation provider in this receipt.",
            "No GraphRAG/HiRAG parity claim.",
            "NO_SUPPORT abstention cases measure empty-gold policy pressure, not navigator abstain.",
            "Receipt is UNSIGNED content checksum, not an attestation.",
        ],
        "metrics": {
            "recall": metrics["recall"],
            "citation_gold_hit_rate": metrics["citation_gold_hit_rate"],
            "handle_contract_ok": metrics["handle_contract_ok"],
            "abstention": {
                k: v for k, v in metrics["abstention"].items() if k != "note"
            },
            "abstention_note": metrics["abstention"]["note"],
            "retrieve_cases": metrics["retrieve_cases"],
            "abstain_empty_index_cases": metrics["abstain_empty_index_cases"],
            "abstain_no_support_cases": metrics["abstain_no_support_cases"],
        },
        "details": metrics["details"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries",
        type=Path,
        default=QUERIES_PATH,
        help="frozen query fixture JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evidence" / "bm25-retrieval-eval-receipt.json",
        help="receipt JSON output path",
    )
    parser.add_argument("--k", type=int, nargs="+", default=[5, 10])
    args = parser.parse_args(argv)

    fixture = load_queries(args.queries)
    index = SecondBrainIndex()
    if not index.built or index.n != PUBLIC_CHUNK_COUNT:
        raise SystemExit(
            f"index not ready: built={index.built} n={index.n} expected={PUBLIC_CHUNK_COUNT}"
        )

    ks = tuple(sorted(set(args.k)))
    metrics = evaluate(index, fixture, ks=ks)
    receipt = build_receipt(
        fixture=fixture, metrics=metrics, index=index, ks=ks, queries_path=args.queries
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Compact stdout summary for operators.
    summary = {
        "status": receipt["status"],
        "out": str(args.out),
        "git_sha": receipt["git_sha"],
        "corpus_file_sha256": receipt["corpus"]["file_sha256"],
        "chunk_count_loaded": receipt["corpus"]["chunk_count_loaded"],
        "metrics": {
            "recall": receipt["metrics"]["recall"],
            "citation_gold_hit_rate": receipt["metrics"]["citation_gold_hit_rate"],
            "handle_contract_ok": receipt["metrics"]["handle_contract_ok"],
            "abstention": receipt["metrics"]["abstention"],
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
