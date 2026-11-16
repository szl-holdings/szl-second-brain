"""Offline Lutar scope-challenge development protocol; never a model launcher.

Public, author-designed fixtures test scope recognition, missing premises and
runtime overclaims. Labels are source interpretations, NOT new Lean proofs.
A family split is enforced within this context pack only. Pretraining and other
exposure are unknown; this is not a blind benchmark or production qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
lr = importlib.import_module("second_brain.lutar_reference")
TRAIN_FAMILIES = ("F1", "F11", "F12", "F19")
EVAL_FAMILIES = ("F4", "F7", "F18", "F22")
LABELS = frozenset({"WITHIN_DECLARED_SCOPE", "OUTSIDE_DECLARED_SCOPE", "INSUFFICIENT_INFORMATION"})
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _case(family, variant, question, scenario, answer, rationale, claim):
    prompt = {"family": family, "question": question, "scenario": scenario,
              "instruction": "Does the cited locked claim justify this assertion? Return one of the three exact labels.",
              "labels": sorted(LABELS)}
    return {"id": "lutar-scope:" + digest(prompt)[:24], "family": family,
            "variant": variant, "prompt": prompt, "expected_label": answer,
            "label_basis": "AUTHOR_INTERPRETATION_OF_PINNED_DECLARED_SCOPE",
            "rationale": rationale, "claim_sha256": digest(claim),
            "source_revision": lr.SOURCE_REVISION, "source_sha256": lr.SOURCE_SHA256}


def build_plan():
    source = lr._load()
    claims = {row["claim_id"]: row for row in source["claims"]}
    all_context = lr.curriculum_candidates()
    context = [row for row in all_context["rows"] if row["claim_id"] in TRAIN_FAMILIES]
    if {row["claim_id"] for row in context} & set(EVAL_FAMILIES):
        raise ValueError("held-out family entered training context")
    rows = []
    specifications = {
        "F4": (
            ("valid", "The encoded backward-edge graph is acyclic.", {"edges": [[2, 1], [1, 0]]}, "WITHIN_DECLARED_SCOPE", "Every edge strictly decreases its natural-number index."),
            ("broken_premise", "The same locked invariant certifies acyclicity after adding the stated edge.", {"edges": [[2, 1], [1, 0], [0, 2]], "cycle_witness": [2, 1, 0, 2]}, "OUTSIDE_DECLARED_SCOPE", "The added edge violates dst < src and the listed edges form a directed cycle."),
            ("runtime_overclaim", "F4 proves Byzantine agreement of the deployed Khipu runtime.", {}, "OUTSIDE_DECLARED_SCOPE", claims["F4"]["refinement_gap"]),
            ("unknown_premise", "The graph meets the backward-edge invariant.", {"edges": None}, "INSUFFICIENT_INFORMATION", "The edge list is not provided; do not infer the invariant."),
        ),
        "F7": (
            ("valid", "The encoded in-memory list queue drains in the given send order.", {"messages": [10, 20, 30], "queue": "List Nat", "enqueue": "append", "drain": "front", "concurrent_mutation": False}, "WITHIN_DECLARED_SCOPE", "The declared list-queue assumptions are present."),
            ("broken_premise", "F7 guarantees exactly-once delivery even after the stated retry.", {"original_messages": [10, 20, 30], "retry_enqueues": [10], "observed_drain": [10, 10, 20, 30]}, "OUTSIDE_DECLARED_SCOPE", "The duplicate contradicts the stronger exactly-once assertion, not F7."),
            ("runtime_overclaim", "F7 proves persistence and crash recovery of the deployed queue.", {}, "OUTSIDE_DECLARED_SCOPE", claims["F7"]["refinement_gap"]),
            ("unknown_premise", "This implementation satisfies the encoded list-queue ordering contract.", {"enqueue": None, "drain": None}, "INSUFFICIENT_INFORMATION", "Implementation semantics are absent."),
        ),
        "F18": (
            ("valid", "At least six of the ten shards remain after the given erasures.", {"total": 10, "erasures": 4, "remaining": 6}, "WITHIN_DECLARED_SCOPE", "The premise e <= 4 holds and 10 - 4 = 6."),
            ("broken_premise", "The locked erasure-tolerance lemma guarantees at least six remaining shards here.", {"total": 10, "erasures": 5, "remaining": 5}, "OUTSIDE_DECLARED_SCOPE", "The premise e <= 4 fails; five remaining shards is less than six."),
            ("runtime_overclaim", "F18 proves that the production Reed-Solomon decoder reconstructs arbitrary lost data.", {}, "OUTSIDE_DECLARED_SCOPE", claims["F18"]["refinement_gap"]),
            ("unknown_premise", "The erasure count satisfies the locked tolerance premise.", {"erasures": None}, "INSUFFICIENT_INFORMATION", "The erasure count is missing."),
        ),
        "F22": (
            ("valid", "For this List.range prefix, values increase strictly with position.", {"n": 4, "seqLog": [0, 1, 2, 3]}, "WITHIN_DECLARED_SCOPE", "The sequence is exactly the encoded natural-number prefix."),
            ("broken_premise", "F22 certifies strictly increasing positions for this altered sequence.", {"seqLog": [0, 2, 1, 3]}, "OUTSIDE_DECLARED_SCOPE", "This is not List.range 4; positions 1 and 2 decrease from 2 to 1."),
            ("runtime_overclaim", "F22 proves monotonicity of the deployed distributed emit path.", {}, "OUTSIDE_DECLARED_SCOPE", claims["F22"]["refinement_gap"]),
            ("unknown_premise", "The runtime sequence is the List.range prefix required by F22.", {"runtime_sequence": None}, "INSUFFICIENT_INFORMATION", "No runtime sequence or refinement evidence was supplied."),
        ),
    }
    for family in EVAL_FAMILIES:
        for args in specifications[family]:
            rows.append(_case(family, *args, claims[family]))
    plan = {
        "schema": "szl.lutar.scope-challenge-development/v1", "state": "REVIEW_REQUIRED",
        "benchmark_status": "PUBLIC_DEVELOPMENT_FIXTURES_NOT_BLIND_QUALIFICATION",
        "source_repository": lr.SOURCE_REPOSITORY, "source_revision": lr.SOURCE_REVISION,
        "source_path": lr.SOURCE_PATH, "source_sha256": lr.SOURCE_SHA256,
        "source_rights": "APACHE_2_0_CANONICAL_PUBLIC_SOURCE",
        "training_families": list(TRAIN_FAMILIES), "evaluation_families": list(EVAL_FAMILIES),
        "training_context": context, "training_context_sha256": digest(context),
        "all_context_sha256": all_context["content_sha256"],
        "cases": rows, "case_count": len(rows), "cases_sha256": digest(rows),
        "split_unit": "LOCKED_FORMULA_FAMILY", "within_pack_family_overlap": [],
        "pretraining_or_external_exposure": "UNOBSERVED",
        "ablation_arms": ["BASELINE", "SOURCE_SCOPE_CONTEXT", "INDEPENDENT_PROOF_CONDITIONED"],
        "arm_status": "NOT_RUN", "budget_parity": "REQUIRED_NOT_ESTABLISHED",
        "independent_proof_conditioned_arm": "BLOCKED_PENDING_CHECKER_AND_REPLAYABLE_PROOF_STORE",
        "training_authority": "NONE", "promotion_authority": "NONE",
        "model_executed_here": False, "private_graph_nodes_loaded": 0,
    }
    plan["plan_sha256"] = digest(plan)
    return plan


def check_training_context(rows):
    """Reject the all-16 export because it includes evaluation families."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty explicit training rows are required")
    expected = build_plan()["training_context"]
    if rows != expected:
        raise ValueError("training context differs or includes withheld families")
    return digest(rows)


def _rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "fraction": numerator / denominator if denominator else None,
            "unit": "fraction", "available": denominator > 0}


def score_predictions(plan, predictions, *, run_binding):
    """Score a fully covered prediction file, not an independently observed run."""
    if canonical(plan) != canonical(build_plan()):
        raise ValueError("plan differs from the exact current protocol and source")
    if (not isinstance(run_binding, dict) or not isinstance(run_binding.get("kind"), str)
            or run_binding["kind"] not in {"SYNTHETIC_CONTROL", "MODEL_OUTPUT"}):
        raise ValueError("an explicit prediction origin is required")
    expected_fields = {"kind", "harness_sha256"}
    if run_binding["kind"] == "SYNTHETIC_CONTROL":
        expected_fields.add("control_name")
        if run_binding.get("control_name") not in ("ORACLE", "ALWAYS_ACCEPT", "ALWAYS_ABSTAIN", "MUTATED"):
            raise ValueError("synthetic control identity is invalid")
    else:
        expected_fields.update({"model_repository", "model_revision", "weights_manifest_sha256",
                                "generation_evidence_sha256", "decoding_config_sha256"})
    if set(run_binding) != expected_fields:
        raise ValueError("prediction origin fields are not the exact admitted schema")
    expected_harness = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if run_binding.get("harness_sha256") != expected_harness:
        raise ValueError("harness source binding differs")
    if run_binding["kind"] == "MODEL_OUTPUT":
        for key in ("weights_manifest_sha256", "generation_evidence_sha256", "decoding_config_sha256"):
            if not isinstance(run_binding.get(key), str) or not HEX64.fullmatch(run_binding[key]):
                raise ValueError("missing exact model generation evidence binding")
        if (not isinstance(run_binding.get("model_revision"), str)
                or not HEX40.fullmatch(run_binding["model_revision"])
                or not isinstance(run_binding.get("model_repository"), str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", run_binding["model_repository"])):
            raise ValueError("missing immutable model identity")
    cases = {row["id"]: row for row in plan["cases"]}
    if not isinstance(predictions, list) or len(predictions) != len(cases):
        raise ValueError("every expected case must have exactly one prediction")
    by_id = {}
    for row in predictions:
        if (not isinstance(row, dict) or set(row) != {"case_id", "label"}
                or not isinstance(row["case_id"], str) or row["case_id"] not in cases
                or row["case_id"] in by_id or not isinstance(row["label"], str)
                or row["label"] not in LABELS):
            raise ValueError("duplicate, unknown, malformed or invalid prediction")
        by_id[row["case_id"]] = row["label"]
    def correct(row):
        return by_id[row["id"]] == row["expected_label"]
    negatives = [r for r in cases.values() if r["expected_label"] == "OUTSIDE_DECLARED_SCOPE"]
    unknowns = [r for r in cases.values() if r["expected_label"] == "INSUFFICIENT_INFORMATION"]
    positives = [r for r in cases.values() if r["expected_label"] == "WITHIN_DECLARED_SCOPE"]
    families = {}
    pairs = 0
    for family in EVAL_FAMILIES:
        selected = [row for row in cases.values() if row["family"] == family]
        families[family] = _rate(sum(correct(row) for row in selected), len(selected))
        pair = [row for row in selected if row["variant"] in {"valid", "broken_premise"}]
        pairs += int(len(pair) == 2 and all(correct(row) for row in pair))
    return {
        "schema": "szl.lutar.scope-challenge-score/v1",
        "state": "SYNTHETIC_CONTROL_ONLY" if run_binding["kind"] == "SYNTHETIC_CONTROL" else "PREDICTION_FILE_SCORED",
        "scored_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": plan["plan_sha256"], "cases_sha256": plan["cases_sha256"],
        "predictions_sha256": digest(sorted(predictions, key=lambda row: row["case_id"])),
        "run_binding": dict(run_binding), "run_binding_verification": "CALLER_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
        "coverage": _rate(len(by_id), len(cases)),
        "accuracy": _rate(sum(correct(row) for row in cases.values()), len(cases)),
        "unsupported_claim_rate": _rate(sum(by_id[r["id"]] == "WITHIN_DECLARED_SCOPE" for r in negatives), len(negatives)),
        "correct_abstention_rate": _rate(sum(correct(r) for r in unknowns), len(unknowns)),
        "overabstention_rate": _rate(sum(by_id[r["id"]] == "INSUFFICIENT_INFORMATION" for r in positives), len(positives)),
        "counterfactual_pair_accuracy": _rate(pairs, len(EVAL_FAMILIES)),
        "per_family_accuracy": families,
        "model_executed_here": False, "benchmark_status": plan["benchmark_status"],
        "training_authority": "NONE", "promotion_authority": "NONE", "quality_qualified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    plan = build_plan()
    with args.output.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(plan, target, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({"state": plan["state"], "cases": plan["case_count"],
                      "training_context_rows": len(plan["training_context"]),
                      "plan_sha256": plan["plan_sha256"], "model_executed_here": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
