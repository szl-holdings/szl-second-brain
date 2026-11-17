# SPDX-License-Identifier: Apache-2.0
"""Read-only Lutar evidence lineage; no inferred proof, runtime or training authority.

Objects and relations come only from the existing byte-bound public reference.
The optional evidence-loss rehearsal only removes support from a copy. It does
not change files, cache results, call providers, or run an agent/controller.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from second_brain.lutar_reference import (
    LOCKED_IDS, SOURCE_PATH, SOURCE_REPOSITORY, SOURCE_REVISION, SOURCE_SHA256,
    lutar_reference,
)

SCHEMA = "szl.second-brain.lutar-lineage/v1"
Scenario = Literal["observed", "withhold-source"]
SCENARIOS = ("observed", "withhold-source")


def _digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _valid_reference(reference: dict[str, Any]) -> bool:
    """Consistency check on the local producer, not an untrusted-receipt verifier."""
    if not isinstance(reference, dict) or reference.get("ready") is not True:
        return False
    if any(type(reference.get(k)) is not type(v) or reference.get(k) != v for k, v in {
        "schema": "szl.second-brain.lutar-reference/v1",
        "state": "SOURCE_BOUND_REFERENCE", "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION, "source_path": SOURCE_PATH,
        "source_sha256": SOURCE_SHA256, "content_access": "HANDLES_ONLY",
        "declared_locked_count": 8, "declared_carrier_count": 24,
        "proof_replayed_here": False, "runtime_refinement": "UNVERIFIED",
        "independent_checker": "NOT_RUN", "training_authority": "NONE",
        "promotion_authority": "NONE", "execution_authority": "NONE",
        "merge_authority": "NONE", "private_graph_present": False,
    }.items()):
        return False
    handles = reference.get("handles")
    if not isinstance(handles, list) or len(handles) != len(LOCKED_IDS):
        return False
    names = []
    for claim_id, handle in zip(LOCKED_IDS, handles, strict=True):
        if not isinstance(handle, dict) or any(handle.get(k) != v for k, v in {
            "claimId": claim_id, "nodeId": f"lutar:{claim_id}:{SOURCE_REVISION}",
            "repository": SOURCE_REPOSITORY, "revision": SOURCE_REVISION,
            "path": SOURCE_PATH, "sourceSha256": SOURCE_SHA256,
            "evidenceState": "SOURCE_DECLARED_LOCKED_NOT_REPLAYED_HERE",
            "refinementState": "UNVERIFIED", "contentAccess": "HANDLES_ONLY",
        }.items()):
            return False
        declarations = handle.get("declarationNames")
        if (not isinstance(declarations, list) or not declarations
                or any(not isinstance(n, str) or not n.startswith("Puriq.Formula.Proved.")
                       or len(n) > 256 for n in declarations)):
            return False
        if not isinstance(handle.get("title"), str) or len(handle["title"]) > 256:
            return False
        if (not isinstance(handle.get("sha256"), str)
                or re.fullmatch(r"[a-f0-9]{64}", handle["sha256"]) is None
                or not isinstance(handle.get("proofModule"), str)
                or not handle["proofModule"] or len(handle["proofModule"]) > 256):
            return False
        names.extend(declarations)
    try:
        return (len(names) == len(set(names)) == 24
                and reference.get("handles_sha256") == _digest(handles))
    except (TypeError, ValueError):
        return False


def _project_reference(reference: dict[str, Any], *, scenario: Scenario = "observed") -> dict[str, Any]:
    """Project one already-read local reference; never accept external HTTP evidence."""
    if scenario not in SCENARIOS:
        raise ValueError("unsupported read-only scenario")
    observed = _valid_reference(reference)
    withheld = scenario == "withhold-source"
    effective = observed and not withheld
    source_id = "source:" + SOURCE_SHA256
    nodes = [{"id": source_id, "kind": "CLAIM_DOCUMENT", "label": "Pinned Lutar claim document",
              "state": "BYTES_VERIFIED" if effective else "WITHHELD_IN_REHEARSAL" if observed else "UNAVAILABLE"}]
    edges = []
    claims = []
    if effective:
        for handle in reference["handles"]:
            claim = {key: handle[key] for key in (
                "nodeId", "claimId", "title", "repository", "revision", "path",
                "sha256", "sourceSha256", "declarationNames", "proofModule",
                "evidenceState", "refinementState", "contentAccess")}
            claim["declarationNames"] = list(claim["declarationNames"])
            claims.append(claim)
            nodes.append({"id": claim["nodeId"], "kind": "CLAIM_HANDLE", "label": claim["claimId"],
                          "state": "SOURCE_DECLARED_NOT_REPLAYED_HERE"})
            edges.append({"source": source_id, "target": claim["nodeId"], "relation": "DECLARES"})
            for declaration in claim["declarationNames"]:
                carrier_id = "carrier:" + declaration
                nodes.append({"id": carrier_id, "kind": "CARRIER_NAME", "label": declaration,
                              "state": "NAMED_NOT_REPLAYED_HERE"})
                edges.append({"source": claim["nodeId"], "target": carrier_id, "relation": "NAMES_CARRIER"})
    gates = [
        {"id": "source", "label": "Pinned source identity", "state": "VERIFIED" if effective else "UNAVAILABLE",
         "requirement": "Read the exact approved public reference bytes."},
        {"id": "proof", "label": "Proof replay in this consumer", "state": "NOT_RUN_HERE",
         "requirement": "Bind independently checked proof terms and their trusted assumptions."},
        {"id": "meaning", "label": "Mathematical meaning review", "state": "NOT_ESTABLISHED_HERE",
         "requirement": "Review whether the statement expresses the intended claim and domain."},
        {"id": "runtime", "label": "Theorem-to-runtime refinement", "state": "UNVERIFIED",
         "requirement": "Show that the specific deployed implementation satisfies the scoped contract."},
        {"id": "quality", "label": "Weight-bound model evaluation", "state": "NOT_RUN_HERE",
         "requirement": "Evaluate exact weights on licensed, pinned, appropriate held-out data."},
    ]
    value = {
        "schema": SCHEMA, "scenario": scenario,
        "scenario_kind": "COUNTERFACTUAL_READ_ONLY" if withheld else "OBSERVED_LOCAL_REFERENCE",
        "observed_reference_ready": observed, "effective_reference_ready": effective,
        "source_head_freshness": "NOT_CHECKED_PINNED_SNAPSHOT",
        "source": {"repository": SOURCE_REPOSITORY, "revision": SOURCE_REVISION,
                   "path": SOURCE_PATH, "sha256": SOURCE_SHA256},
        "nodes": nodes, "edges": edges, "claims": claims, "gates": gates,
        "coverage": {"scope": "ONE_PINNED_LUTAR_DOCUMENT_NOT_ESTATE_CENSUS",
                     "claim_handles": {"observed": len(claims), "expected": 8},
                     "carrier_names": {"observed": sum(len(x["declarationNames"]) for x in claims), "expected": 24},
                     "proof_replay": {"observed": None, "expected": 24, "available": False}},
        "impact": {"withdrawn_claim_handles": 8 if observed and withheld else 0,
                   "withdrawn_carrier_names": 24 if observed and withheld else 0,
                   "files_changed": 0, "provider_calls": 0, "actions_performed": 0},
        "open_gates": [x["id"] for x in gates if x["state"] != "VERIFIED"],
        "content_access": "HANDLES_ONLY", "signature": "UNSIGNED_CONTENT_DIGEST",
        "proof_replayed_here": False, "independent_checker": "NOT_RUN",
        "semantic_review": "NOT_ESTABLISHED_BY_THIS_CONSUMER", "runtime_refinement": "UNVERIFIED",
        "model_evaluation": "NOT_RUN_HERE", "production_qualification": "NOT_ASSESSED",
        "training_authority": "NONE", "promotion_authority": "NONE",
        "execution_authority": "NONE", "merge_authority": "NONE",
        "private_graph_present": False, "raw_graph_nodes_admitted_to_gradients": 0,
        "lambda": "CONJECTURE_1_OPEN_FALSE_AS_STATED",
        "limitations": ["A DECLARES edge is not a proof or causal guarantee.",
                        "A source digest is not a signature, fresh upstream observation or runtime qualification.",
                        "Rehearsals remove reference support only; they cannot create evidence or authorize actions."]}
    value["snapshot_sha256"] = _digest(value)
    return value


def lutar_lineage(*, scenario: Scenario = "observed") -> dict[str, Any]:
    """Read once per request and derive the public projection from that snapshot."""
    if scenario not in SCENARIOS:
        raise ValueError("unsupported read-only scenario")
    return _project_reference(lutar_reference(), scenario=scenario)
