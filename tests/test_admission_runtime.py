#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Served HIRAG admission is explicit opt-in, reported when off, and fails closed when on."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app_refinement import app
from second_brain import admission_runtime as runtime
from second_brain.admission import CorpusAdmission, CorpusAdmissionError
from second_brain.console import render_console
from second_brain.hirag import ADMISSIBLE_LICENSES, gate_v1, lambda_v1
from second_brain.hybrid import HybridSecondBrain, RetrievalBoundaryError, hybrid_index
from second_brain.neomme import PUBLIC_CORPUS_SHA256
from second_brain.retrieve import SecondBrainIndex, canonical_sha256, index
from second_brain.workbench import query_bundle, readiness

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "data" / runtime.METADATA_FILE
CORPUS = ROOT / "data" / "brain-corpus.public.jsonl"
# Pinned so that any edit to the committed stamp is a deliberate, reviewed test change.
ADMISSION_COMMIT = "ba400df03d1252d300328a3fdbc4f6b86df05b4c"
ADMISSION_COMMIT_UNIX_S = 1788009755
FIXTURE_BASIS = "TEST_FIXTURE_NOT_A_RIGHTS_OR_TIME_DECLARATION"
METRIC_CARD = re.compile(r'<article class="metric"><span>(.*?)</span><strong>(.*?)</strong>')
client = TestClient(app)

_spec = importlib.util.spec_from_file_location("check_admission_metadata", ROOT / "tools" / "check_admission_metadata.py")
history_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(history_check)


def _enable(monkeypatch, value="1"):
    monkeypatch.setenv(runtime.OPT_IN_ENV, value)
    runtime.reset_runtime_admission()


def _utc(unix_s):
    try:
        return datetime.fromtimestamp(unix_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError, TypeError):
        return "UNREPRESENTABLE"


def _declared(license_value="apache-2.0"):
    return {"license": license_value, "basis": FIXTURE_BASIS, "declared_by": "TEST_FIXTURE"}


def _committed_sidecar_is_current() -> bool:
    """A corpus change leaves the committed sidecar STALE until a follow-up regenerates it on main."""
    return json.loads(SIDECAR.read_text(encoding="utf-8"))["corpus_sha256"] == hashlib.sha256(CORPUS.read_bytes()).hexdigest()


TEXTS = {
    "n1": "locked eight formula authority evidence",
    "n2": "second brain evidence retrieval formula",
    "n3": "formula receipt evidence admission",
    "n4": "evidence retrieval hydration formula",
    "n5": "formula evidence lineage retrieval",
    "n6": "retrieval evidence formula review",
}


def _corpus(tmp_path: Path) -> tuple[SecondBrainIndex, Path]:
    path = tmp_path / "brain.jsonl"
    path.write_text("".join(json.dumps({"id": k, "source": "s-" + k, "title": v.title(), "text": v,
                                        "sha256": hashlib.sha256(v.encode()).hexdigest()}, sort_keys=True) + "\n"
                            for k, v in TEXTS.items()), encoding="utf-8")
    return SecondBrainIndex(path), path


def _sidecar_value(corpus_path: Path, *, licenses=None, unix_s=None) -> dict:
    unix_s = int(time.time()) - 3600 if unix_s is None else unix_s
    return {"schema": runtime.METADATA_SCHEMA, "corpus_file": corpus_path.name,
            "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(), "row_count": len(TEXTS),
            "ingested_at": {"unix_s": unix_s, "utc": _utc(unix_s), "kind": "REPOSITORY_ADMISSION_COMMIT_TIME",
                            "granularity": "WHOLE_CORPUS", "source_commit": "a" * 40,
                            "signature_verification": "NOT_VERIFIED", "basis": FIXTURE_BASIS},
            "licenses": licenses if licenses is not None else {}, "license_policy": "ABSENT_IS_UNKNOWN",
            "license_basis": FIXTURE_BASIS}


def _write(tmp_path: Path, value, name="meta.json") -> Path:
    path = tmp_path / name
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode("utf-8"))
    return path


def _fixture_runtime(tmp_path, monkeypatch, licenses, unix_s=None):
    brain, corpus_path = _corpus(tmp_path)
    sidecar = _sidecar_value(corpus_path, licenses=licenses, unix_s=unix_s)
    coordinator, block = runtime.build_runtime(brain, _write(tmp_path, sidecar))
    monkeypatch.setattr(runtime, "_STATE", (coordinator, block))
    return brain, coordinator, block


def _cards(html: str) -> list[tuple[str, str]]:
    return METRIC_CARD.findall(html)


# --- default: off, reported, and invisible on the served payloads and console -------------

def test_default_off_is_reported_and_served_receipts_are_unchanged():
    query = "formula authority"
    assert runtime.served_hybrid_context(query, k=4) == hybrid_index().context(query, k=4)
    hybrid = client.get("/api/v1/hybrid", params={"q": query, "k": 4}).json()
    receipt = hybrid["ranking_receipt"]
    assert receipt["mode"] == "BM25_ONLY" and receipt["admission"] == "NOT_APPLIED"
    assert receipt["admission_detail"] is None and "admission_runtime" not in receipt
    assert hybrid["handles"]
    capabilities = client.get("/api/v1/retrieval-capabilities").json()
    assert capabilities["public_runtime_mode"] == "BM25_ONLY"
    assert "BM25_ONLY+HIRAG_ADMISSION" in capabilities["available_modes"]
    admission = capabilities["hirag_admission"]
    assert (admission["state"], admission["reason"], admission["opt_in"]) == ("NOT_APPLIED", "OPT_IN_NOT_ENABLED", "NOT_ENABLED")
    assert admission["gated_routes"] == [] and admission["blocked_routes"] == []
    assert admission["ungated_routes"] == list(runtime.GATED_ROUTES + runtime.UNGATED_ROUTES)
    assert admission["lambda"] == "CONJECTURE_1" and admission["owner_ratification"] == "REQUIRES_OWNER_DECISION"
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["runtime_mode"] == "BM25_ONLY"
    # Admission is reported beside the components, never as a component (the console draws one card each).
    assert set(ready.json()["components"]) == {"corpus", "frontier", "refinement"}
    assert ready.json()["hirag_admission"] == admission


@pytest.mark.parametrize("query", ["", "formula authority"])
def test_default_console_is_the_page_without_any_admission_block(query):
    response = client.get("/", params={"q": query} if query else None)
    assert response.status_code == 200
    assert [name for name, _ in _cards(response.text)] == ["Corpus", "Frontier", "Refinement"]
    assert "HIRAG" not in response.text and "Hirag" not in response.text
    status = readiness()
    status.pop("hirag_admission")
    bundle = query_bundle(query, 6) if query else None
    assert response.text == render_console(query, 6, status, bundle, None)


@pytest.mark.parametrize("value,state,reason", [
    ("0", "NOT_APPLIED", "OPT_IN_NOT_ENABLED"), ("", "NOT_APPLIED", "OPT_IN_NOT_ENABLED"),
    ("true", "BLOCKED", "OPT_IN_VALUE_INVALID"), ("yes", "BLOCKED", "OPT_IN_VALUE_INVALID"),
    ("2", "BLOCKED", "OPT_IN_VALUE_INVALID"), (" 1", "BLOCKED", "OPT_IN_VALUE_INVALID"),
    ("1 ", "BLOCKED", "OPT_IN_VALUE_INVALID"), (" ", "BLOCKED", "OPT_IN_VALUE_INVALID"),
])
def test_only_the_exact_opt_in_value_enables_and_ambiguity_blocks(monkeypatch, value, state, reason):
    _enable(monkeypatch, value)
    observation = runtime.admission_observation()
    assert (observation["state"], observation["reason"]) == (state, reason)


# --- the committed sidecar, served end to end --------------------------------------------

def test_opt_in_with_the_committed_sidecar_gates_served_routes_or_blocks_when_stale(monkeypatch):
    _enable(monkeypatch)
    if not _committed_sidecar_is_current():
        # After a corpus change and before the follow-up regeneration: fail closed, never ungated.
        assert runtime.admission_observation()["reason"] == "METADATA_GENERATION_MISMATCH"
        assert client.get("/api/v1/hybrid", params={"q": "formula authority"}).status_code == 422
        assert client.get("/readyz").status_code == 503
        return
    hybrid = client.get("/api/v1/hybrid", params={"q": "formula authority", "k": 6}).json()
    receipt = hybrid["ranking_receipt"]
    assert receipt["admission"] == "APPLIED" and receipt["mode"] == "BM25_ONLY+HIRAG_ADMISSION"
    detail = receipt["admission_detail"]
    assert detail["gate"] == "szl.hirag/v1" and detail["relevance_measure"] == "RANK_DERIVED_1_OVER_RANK"
    assert detail["decision_label"] == "COMPUTED_OVER_DECLARED_INPUTS" and detail["lambda_status"] == "ADVISORY"
    # The committed metadata declares no licence, so every offered node is refused and nothing is backfilled.
    assert detail["refused_count"] == len(detail["decisions"]) > 0 and detail["admitted_count"] == 0
    assert hybrid["state"] == "ABSTAIN_NO_GROUNDED_HANDLES" and hybrid["handles"] == []
    assert set(detail["refusals"]) == set(detail["decisions"]) == set(detail["offered_rank_order"])
    block = receipt["admission_runtime"]
    stale = detail["evaluated_at_unix_s"] >= block["ingested_at"]["freshness_window_ends_unix_s"]
    for refusal in detail["refusals"].values():
        assert (refusal["verdict"], refusal["code"], refusal["lambda"]) == ("NO_GO", "ZERO_VETO", 0.0)
        assert "license_admissible" in refusal["zero_axes"]
        assert ("freshness" in refusal["zero_axes"]) is stale
    assert block["state"] == "CONFIGURED" and block["opt_in"] == "ENABLED" and block["reason"] is None
    assert block["corpus_generation_sha256"] == PUBLIC_CORPUS_SHA256 and block["corpus_row_count"] == len(index().rows)
    assert (block["declared_license_count"], block["admissible_license_count"]) == (0, 0)
    assert block["unknown_license_count"] == block["corpus_row_count"]
    stamp = block["ingested_at"]
    assert (stamp["kind"], stamp["signature_verification"]) == ("REPOSITORY_ADMISSION_COMMIT_TIME", "NOT_VERIFIED")
    # The substitute for a controller-measured ingestion time is labelled unratified, with its bias.
    assert (stamp["substitutes_for"], stamp["ratification"]) == ("CONTROLLER_RECORDED_INGESTION_TIME", "REQUIRES_OWNER_DECISION")
    assert stamp["freshness_bias"] == "CAN_ONLY_OVERSTATE_FRESHNESS"
    assert block["metadata_sha256"] == hashlib.sha256(SIDECAR.read_bytes()).hexdigest()
    assert block["policy"]["tau"] == 0.5 and block["policy"]["freshness_window_s"] == 30 * 24 * 3600
    assert block["gated_routes"] == list(runtime.GATED_ROUTES) and block["blocked_routes"] == []
    assert block["ungated_routes"] == list(runtime.UNGATED_ROUTES)
    assert "MEASURED" not in json.dumps(receipt)
    bundle = client.get("/api/v1/query", params={"q": "formula authority", "k": 6}).json()
    served = bundle["retrieve"]["ranking_receipt"]
    assert served["admission"] == "APPLIED" and served["admission_runtime"]["metadata_sha256"] == block["metadata_sha256"]
    assert bundle["receipt"]["ranking_receipt_sha256"] == canonical_sha256(served)
    assert bundle["receipt"]["signature"] == "UNSIGNED_CONTENT_DIGEST"
    # Disclosed: only brain-corpus handles are gated; review candidates in the same response are not.
    assert bundle["retrieve"]["handles"] == [] and bundle["frontier"]["handles"]
    capabilities = client.get("/api/v1/retrieval-capabilities").json()
    # The base retrieval mode is unchanged; admission participation is reported per route and per query.
    assert capabilities["public_runtime_mode"] == "BM25_ONLY"
    assert capabilities["hirag_admission"]["state"] == "CONFIGURED"
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["runtime_mode"] == "BM25_ONLY"
    assert ready.json()["hirag_admission"]["state"] == "CONFIGURED"
    # Every gated query abstains, so the evidence surfaces report PARTIAL_OR_UNAVAILABLE (503).
    graph = client.get("/api/v1/evidence-graph", params={"q": "formula authority"})
    assert graph.status_code == 503 and graph.json()["state"] == "PARTIAL_OR_UNAVAILABLE"
    assert client.get("/evidence", params={"q": "formula authority"}).status_code == 503
    # Disclosed limit: the legacy lexical route bypasses the gate and still returns handles.
    assert client.get("/api/v1/retrieve", params={"q": "formula authority"}).json()["handles"]


def test_committed_sidecar_declares_no_rights_and_pins_its_stamp():
    value = json.loads(SIDECAR.read_text(encoding="utf-8"))
    assert value["corpus_file"] == CORPUS.name
    assert value["licenses"] == {} and value["license_policy"] == "ABSENT_IS_UNKNOWN"
    stamp = value["ingested_at"]
    assert (stamp["unix_s"], stamp["source_commit"]) == (ADMISSION_COMMIT_UNIX_S, ADMISSION_COMMIT)
    assert stamp["kind"] == "REPOSITORY_ADMISSION_COMMIT_TIME" and stamp["signature_verification"] == "NOT_VERIFIED"
    assert "upper bound" in stamp["basis"] and "overstate" in stamp["basis"]


def test_committed_sidecar_is_current_or_the_opt_in_refuses_to_build():
    value = json.loads(SIDECAR.read_text(encoding="utf-8"))
    if _committed_sidecar_is_current():
        _coordinator, block = runtime.build_runtime(index(), SIDECAR)
        assert block["state"] == "CONFIGURED" and block["corpus_generation_sha256"] == value["corpus_sha256"]
        assert value["row_count"] == block["corpus_row_count"]
    else:
        with pytest.raises(runtime.AdmissionBlocked) as caught:
            runtime.build_runtime(index(), SIDECAR)
        assert caught.value.reason == "METADATA_GENERATION_MISMATCH"


def test_sidecar_claims_are_true_in_git_history():
    try:
        result = history_check.check(ROOT)
    except history_check.HistoryUnavailable as exc:
        # Only a shallow clone or a missing git can skip; an absent or off-mainline commit fails.
        pytest.skip(f"{exc} (CI runs tools/check_admission_metadata.py with fetch-depth 0, where this cannot skip)")
    else:
        assert (result["commit"], result["unix_s"]) == (ADMISSION_COMMIT, ADMISSION_COMMIT_UNIX_S)
        assert result["status"] == ("CURRENT" if _committed_sidecar_is_current() else "STALE")


# --- console with the opt-in set --------------------------------------------------------

def test_console_names_the_admission_state_and_its_refusals_when_configured(tmp_path, monkeypatch):
    _fixture_runtime(tmp_path, monkeypatch, {})
    bare = client.get("/")
    assert bare.status_code == 200
    assert [name for name, _ in _cards(bare.text)] == ["Corpus", "Frontier", "Refinement"]
    assert "HIRAG admission opt-in: <strong>Configured</strong>" in bare.text
    page = client.get("/", params={"q": "formula evidence retrieval"})
    assert page.status_code == 200
    assert "HIRAG admission: 0 admitted · 6 refused" in page.text
    assert "HIRAG admission refused all 6 offered corpus handles. The planner abstains." in page.text
    assert "No corpus handles found" not in page.text


def test_console_names_a_blocked_opt_in_and_refuses_searches(monkeypatch):
    _enable(monkeypatch, "true")
    bare = client.get("/")
    assert bare.status_code == 200 and len(_cards(bare.text)) == 3
    assert "HIRAG admission opt-in: <strong>Blocked</strong> (OPT_IN_VALUE_INVALID)" in bare.text
    assert client.get("/", params={"q": "formula authority"}).status_code == 422


# --- gate mechanics on a synthetic corpus (independent of the committed sidecar) ----------

def test_empty_query_reports_that_the_configured_gate_did_not_run(tmp_path, monkeypatch):
    _fixture_runtime(tmp_path, monkeypatch, {})
    body = client.get("/api/v1/hybrid", params={"q": ""}).json()
    assert body["state"] == "ABSTAIN_NO_QUERY"
    assert body["ranking_receipt"]["admission"] == "NOT_RUN"
    assert body["ranking_receipt"]["admission_runtime"]["state"] == "CONFIGURED"


def test_refusals_come_from_declared_facts_not_from_a_stub(tmp_path):
    brain, corpus_path = _corpus(tmp_path)
    sidecar = _sidecar_value(corpus_path, unix_s=ADMISSION_COMMIT_UNIX_S)
    coordinator, _block = runtime.build_runtime(brain, _write(tmp_path, sidecar))
    ids = ["n1", "n2", "n3"]
    fresh = coordinator.admission.admit_selection(ids, now=ADMISSION_COMMIT_UNIX_S + 60)
    # Right after admission freshness is ~1.0, yet the unknown licence alone vetoes.
    assert all(r["axes"]["freshness"] > 0.99 for r in fresh["receipts"])
    assert all(r["axes"]["license_admissible"] == 0.0 and r["code"] == "ZERO_VETO" for r in fresh["receipts"])
    late = coordinator.admission.admit_selection(ids, now=ADMISSION_COMMIT_UNIX_S + runtime.FRESHNESS_WINDOW_S)
    assert all(r["axes"]["freshness"] == 0.0 for r in late["receipts"])


def test_committed_stamp_window_has_closed_so_declaring_licences_alone_admits_nothing(tmp_path, monkeypatch):
    committed = ADMISSION_COMMIT_UNIX_S  # the shipped ba400df stamp; a fixed historical fact
    licenses = {node_id: _declared() for node_id in TEXTS}
    _brain, coordinator, block = _fixture_runtime(tmp_path, monkeypatch, licenses, unix_s=committed)
    assert block["ingested_at"]["freshness_window_ends_utc"] == "2026-09-28T13:22:35Z"
    assert (block["declared_license_count"], block["admissible_license_count"], block["unknown_license_count"]) == (6, 6, 0)
    # Fresh, the same declarations admit; the decision is not hard-wired to refuse.
    assert coordinator.admission.admit_selection(["n1"], now=committed + 60)["admitted"] == ["n1"]
    result = runtime.served_hybrid_context("formula evidence retrieval", k=6)
    detail = result["ranking_receipt"]["admission_detail"]
    assert detail["evaluated_at_unix_s"] >= block["ingested_at"]["freshness_window_ends_unix_s"]
    assert detail["admitted_count"] == 0 and result["handles"] == []
    assert {axis for refusal in detail["refusals"].values() for axis in refusal["zero_axes"]} == {"freshness"}


def test_declared_licence_and_recent_stamp_are_admitted_on_a_synthetic_fixture(tmp_path, monkeypatch):
    _brain, _coordinator, block = _fixture_runtime(tmp_path, monkeypatch, {"n1": _declared()})
    result = runtime.served_hybrid_context("locked eight formula authority", k=2)
    detail = result["ranking_receipt"]["admission_detail"]
    assert detail["decisions"]["n1"] is True and detail["admitted_count"] == 1
    assert [h["nodeId"] for h in result["handles"]] == ["n1"]
    assert "n1" not in detail["refusals"] and all(r["code"] == "ZERO_VETO" for r in detail["refusals"].values())
    assert (block["declared_license_count"], block["admissible_license_count"], block["unknown_license_count"]) == (1, 1, 5)


def test_gate_only_removes_never_adds(tmp_path, monkeypatch):
    licenses = {node_id: _declared() for node_id in ("n1", "n3", "n5")}
    brain, _coordinator, _block = _fixture_runtime(tmp_path, monkeypatch, licenses)
    query = "formula evidence retrieval"
    ungated = [h["nodeId"] for h in HybridSecondBrain(brain).context(query, k=6)["handles"]]
    result = runtime.served_hybrid_context(query, k=6)
    gated = [h["nodeId"] for h in result["handles"]]
    remaining = iter(ungated)
    assert all(node_id in remaining for node_id in gated), "gated handles must be an ordered subsequence"
    assert gated == [node_id for node_id in ungated if node_id in licenses]
    assert result["ranking_receipt"]["admission_detail"]["offered_rank_order"] == ungated
    assert len(result["evidence"]) == result["ranking_receipt"]["admission_detail"]["admitted_count"] == len(gated)


def test_receipt_decisions_are_recomputable_from_digest_bound_inputs(tmp_path, monkeypatch):
    licenses = {"n1": _declared(), "n2": _declared("proprietary"), "n4": _declared("MIT")}
    _brain, _coordinator, block = _fixture_runtime(tmp_path, monkeypatch, licenses)
    receipt = runtime.served_hybrid_context("formula evidence retrieval", k=6)["ranking_receipt"]
    detail, policy = receipt["admission_detail"], receipt["admission_runtime"]["policy"]
    unix_s, evaluated_at = block["ingested_at"]["unix_s"], detail["evaluated_at_unix_s"]
    weights = [policy["weights"][axis] for axis in policy["weights"]]
    outcomes = set()
    # Rank comes from the ordered list, never from the key order of the decisions/refusals objects.
    assert set(detail["offered_rank_order"]) == set(detail["decisions"])
    for rank, node_id in enumerate(detail["offered_rank_order"], 1):
        declared = licenses.get(node_id, {}).get("license", "unknown").lower() in policy["admissible_licenses"]
        axes = {"source_receipt_valid": 1.0, "license_admissible": 1.0 if declared else 0.0,
                "freshness": max(0.0, 1.0 - max(0.0, evaluated_at - unix_s) / policy["freshness_window_s"]),
                "relevance": 1.0 / rank, "derivation_integrity": 1.0}
        scores = [axes[axis] for axis in policy["weights"]]
        verdict, code = gate_v1(scores, weights, policy["tau"])
        assert detail["decisions"][node_id] is (verdict == "GO")
        if verdict != "GO":
            assert (detail["refusals"][node_id]["code"], detail["refusals"][node_id]["lambda"]) == \
                (code, round(lambda_v1(scores, weights), 9))
        outcomes.add(verdict)
    assert outcomes == {"GO", "NO_GO"}
    assert set(policy["admissible_licenses"]) == ADMISSIBLE_LICENSES
    # The digest binds the offered order (a list) and is indifferent to object member order.
    permuted = copy.deepcopy(receipt)
    permuted["admission_detail"]["decisions"] = dict(reversed(list(detail["decisions"].items())))
    assert canonical_sha256(permuted) == canonical_sha256(receipt)
    permuted["admission_detail"]["offered_rank_order"] = list(reversed(detail["offered_rank_order"]))
    assert canonical_sha256(permuted) != canonical_sha256(receipt)


def test_recorded_evaluation_time_is_the_one_the_gate_used(tmp_path, monkeypatch):
    _fixture_runtime(tmp_path, monkeypatch, {"n1": _declared()})
    ticks = itertools.count(1_800_000_000, 997)
    monkeypatch.setattr(runtime.time, "time", lambda: float(next(ticks)))
    used = []
    original = CorpusAdmission.admit_selection

    def spy(self, selected, now=None):
        used.append(now)
        return original(self, selected, now=now)
    monkeypatch.setattr(CorpusAdmission, "admit_selection", spy)
    detail = runtime.served_hybrid_context("formula evidence retrieval", k=6)["ranking_receipt"]["admission_detail"]
    assert len(used) == 1 and detail["evaluated_at_unix_s"] == used[0]


def test_admission_run_error_is_422_blocked_not_500(tmp_path, monkeypatch):
    _fixture_runtime(tmp_path, monkeypatch, {})

    def broken(self, selected, now=None):
        raise CorpusAdmissionError("admission run rejected: injected")
    monkeypatch.setattr(runtime._ServedCorpusAdmission, "admit_selection", broken)
    with pytest.raises(RetrievalBoundaryError):
        runtime.served_hybrid_context("formula authority", k=2)
    response = client.get("/api/v1/hybrid", params={"q": "formula authority"})
    assert response.status_code == 422 and response.json()["state"] == "BLOCKED"
    assert client.get("/api/v1/query", params={"q": "formula authority"}).status_code == 422


# --- malformed or unavailable metadata BLOCKS (never 500, never an ungated fallback) -------

BAD_METADATA = {
    "generation_mismatch": (lambda v: {**v, "corpus_sha256": "0" * 64}, "METADATA_GENERATION_MISMATCH"),
    "future_stamp": (lambda v: _restamp(v, int(time.time()) + 86400), "METADATA_INGESTED_AT_IN_FUTURE"),
    "millisecond_stamp": (lambda v: _restamp(v, int(time.time() * 1000)), "METADATA_INGESTED_AT_IN_FUTURE"),
    "implausibly_small_stamp": (lambda v: _restamp(v, 12345), "METADATA_INVALID"),
    "float_stamp": (lambda v: _restamp(v, 1788009755.5), "METADATA_INVALID"),
    "bool_stamp": (lambda v: _restamp(v, True), "METADATA_INVALID"),
    "utc_disagrees_with_epoch": (lambda v: _set(v, ("ingested_at", "utc"), "2026-01-01T00:00:00Z"), "METADATA_INVALID"),
    "load_time_kind": (lambda v: _set(v, ("ingested_at", "kind"), "PROCESS_LOAD_TIME"), "METADATA_INVALID"),
    "unverifiable_signature_claim": (lambda v: _set(v, ("ingested_at", "signature_verification"), "VERIFIED"), "METADATA_INVALID"),
    "short_commit": (lambda v: _set(v, ("ingested_at", "source_commit"), "abc123"), "METADATA_INVALID"),
    "unknown_stamp_key": (lambda v: _set(v, ("ingested_at", "measured"), True), "METADATA_INVALID"),
    "unknown_top_level_key": (lambda v: {**v, "admit_all": True}, "METADATA_INVALID"),
    "window_override_key": (lambda v: {**v, "freshness_window_s": 10 ** 9}, "METADATA_INVALID"),
    "row_count_mismatch": (lambda v: {**v, "row_count": 575}, "METADATA_INVALID"),
    "other_license_policy": (lambda v: {**v, "license_policy": "ABSENT_IS_APACHE"}, "METADATA_INVALID"),
    "licence_for_unknown_node": (lambda v: _set(v, ("licenses", "not-a-node"), _declared()), "METADATA_INVALID"),
    "bare_string_licence": (lambda v: _set(v, ("licenses", "n1"), "apache-2.0"), "METADATA_INVALID"),
    "blank_licence": (lambda v: _set(v, ("licenses", "n1"), _declared(" ")), "METADATA_INVALID"),
    "declared_unknown_licence": (lambda v: _set(v, ("licenses", "n1"), _declared("UNKNOWN")), "METADATA_INVALID"),
    "declared_padded_unknown_licence": (lambda v: _set(v, ("licenses", "n1"), _declared(" unknown ")), "METADATA_INVALID"),
    "licence_without_basis": (lambda v: _set(v, ("licenses", "n1"), {"license": "mit", "declared_by": "x"}), "METADATA_INVALID"),
    "duplicate_json_key": (lambda v: json.dumps(v).replace('"licenses": {}', '"licenses": {}, "licenses": {}').encode(), "METADATA_INVALID"),
    # JSON arrays/objects where a string is expected are unhashable: they must BLOCK, not raise TypeError.
    "license_policy_list": (lambda v: {**v, "license_policy": ["ABSENT_IS_UNKNOWN"]}, "METADATA_INVALID"),
    "license_policy_object": (lambda v: {**v, "license_policy": {}}, "METADATA_INVALID"),
    "stamp_kind_list": (lambda v: _set(v, ("ingested_at", "kind"), ["REPOSITORY_ADMISSION_COMMIT_TIME"]), "METADATA_INVALID"),
    "signature_object": (lambda v: _set(v, ("ingested_at", "signature_verification"), {}), "METADATA_INVALID"),
    "signature_list": (lambda v: _set(v, ("ingested_at", "signature_verification"), ["NOT_VERIFIED"]), "METADATA_INVALID"),
    "granularity_list": (lambda v: _set(v, ("ingested_at", "granularity"), []), "METADATA_INVALID"),
    "schema_list": (lambda v: {**v, "schema": []}, "METADATA_INVALID"),
    "licenses_list": (lambda v: {**v, "licenses": []}, "METADATA_INVALID"),
    "corpus_sha256_list": (lambda v: {**v, "corpus_sha256": []}, "METADATA_GENERATION_MISMATCH"),
    "top_level_list": (lambda v: [v], "METADATA_INVALID"),
}


def _set(value, path, item):
    value = copy.deepcopy(value)
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = item
    return value


def _restamp(value, unix_s):
    value = _set(value, ("ingested_at", "unix_s"), unix_s)
    return _set(value, ("ingested_at", "utc"), _utc(unix_s))


@pytest.mark.parametrize("case", sorted(BAD_METADATA))
def test_bad_metadata_blocks_instead_of_falling_back(tmp_path, case):
    mutate, reason = BAD_METADATA[case]
    brain, corpus_path = _corpus(tmp_path)
    good = _sidecar_value(corpus_path, unix_s=ADMISSION_COMMIT_UNIX_S)
    runtime.build_runtime(brain, _write(tmp_path, good))  # the unmutated fixture is accepted
    with pytest.raises(runtime.AdmissionBlocked) as caught:
        runtime.build_runtime(brain, _write(tmp_path, mutate(good)))
    assert caught.value.reason == reason


def _assert_served_blocked(reason, error_type=None):
    loose = TestClient(app, raise_server_exceptions=False)
    ready = loose.get("/readyz")
    assert ready.status_code == 503 and ready.json()["ready"] is False
    block = ready.json()["hirag_admission"]
    assert (block["state"], block["reason"]) == ("BLOCKED", reason)
    assert block.get("error_type") == error_type
    assert block["gated_routes"] == [] and block["blocked_routes"] == list(runtime.GATED_ROUTES)
    assert block["ungated_routes"] == list(runtime.UNGATED_ROUTES)
    capabilities = loose.get("/api/v1/retrieval-capabilities")
    assert capabilities.status_code == 200 and capabilities.json()["public_runtime_mode"] == "BM25_ONLY"
    assert capabilities.json()["hirag_admission"] == block
    assert loose.get("/api/v1/hybrid", params={"q": "formula authority"}).status_code == 422
    assert loose.post("/api/v1/hybrid", json={"query": "formula authority"}).status_code == 422
    assert loose.get("/api/v1/query", params={"q": "formula authority"}).status_code == 422
    assert loose.get("/api/v1/query", params={"q": ""}).status_code == 422
    # The console renders its form (200) with no query, and refuses (422) a search.
    assert loose.get("/").status_code == 200
    assert loose.get("/", params={"q": "formula authority"}).status_code == 422
    assert loose.get("/api/v1/evidence-graph", params={"q": "formula authority"}).status_code == 422
    assert loose.get("/evidence", params={"q": "formula authority"}).status_code == 503
    # The ungated legacy route is unaffected; it is disclosed in ungated_routes, not silently covered.
    assert loose.get("/api/v1/retrieve", params={"q": "formula authority"}).json()["handles"]


@pytest.mark.parametrize("value,reason", [("true", "OPT_IN_VALUE_INVALID"), ("1", "METADATA_UNAVAILABLE")])
def test_requested_but_unavailable_gate_blocks_served_retrieval(monkeypatch, tmp_path, value, reason):
    monkeypatch.setattr(runtime, "data_file", lambda name: tmp_path / name)
    _enable(monkeypatch, value)
    with pytest.raises(RetrievalBoundaryError):
        runtime.served_hybrid_context("formula authority", k=2)
    _assert_served_blocked(reason)


@pytest.mark.parametrize("field,item", [(("license_policy",), []), (("ingested_at", "kind"), ["X"]),
                                        (("ingested_at", "signature_verification"), {})])
def test_unhashable_sidecar_values_block_every_served_route_instead_of_500(monkeypatch, tmp_path, field, item):
    real = index()
    value = json.loads(SIDECAR.read_text(encoding="utf-8"))
    # Bound to the served corpus so the build reaches the type checks even when the committed sidecar is stale.
    value.update(corpus_sha256=real.generation_sha256, row_count=len(real.rows))
    _write(tmp_path, _set(value, field, item), runtime.METADATA_FILE)
    monkeypatch.setattr(runtime, "data_file", lambda name: tmp_path / name)
    _enable(monkeypatch)
    _assert_served_blocked("METADATA_INVALID")


def test_unforeseen_build_error_blocks_and_is_cached(monkeypatch):
    calls = []

    def explode(_brain, _path):
        calls.append(1)
        raise TypeError("injected")
    monkeypatch.setattr(runtime, "build_runtime", explode)
    _enable(monkeypatch)
    _assert_served_blocked("ADMISSION_BUILD_ERROR", "TypeError")
    assert len(calls) == 1


# --- route disclosure is tied to the app's real route table -------------------------------

def test_every_query_accepting_route_is_disclosed_as_gated_or_ungated():
    retrieval_paths = set()
    for path, operations in app.openapi()["paths"].items():
        for operation in operations.values():
            names = {p["name"] for p in operation.get("parameters", []) if p["in"] == "query"}
            if names & {"q", "k"} or "requestBody" in operation:
                retrieval_paths.add(path)
    assert not set(runtime.GATED_ROUTES) & set(runtime.UNGATED_ROUTES)
    assert set(runtime.GATED_ROUTES) | set(runtime.UNGATED_ROUTES) == retrieval_paths


# --- the history check: every claim true, squash-merge safe -------------------------------

def _git(repo: Path, *args: str, when: int | None = None) -> str:
    env = {**{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{when} +0000"
    done = subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull,
                           "-c", "init.defaultBranch=main", *args], capture_output=True, text=True, env=env, check=True)
    return done.stdout.strip()


def _bind(repo: Path, commit: str, unix_s: int, corpus: bytes) -> None:
    sidecar = {"corpus_sha256": hashlib.sha256(corpus).hexdigest(),
               "ingested_at": {"unix_s": unix_s, "utc": _utc(unix_s), "source_commit": commit}}
    (repo / history_check.SIDECAR).write_text(json.dumps(sidecar), encoding="utf-8")


def _commit_corpus(repo: Path, body: bytes, when: int, message: str) -> str:
    (repo / history_check.CORPUS).write_bytes(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message, when=when)
    return _git(repo, "rev-parse", "HEAD")


@pytest.mark.skipif(shutil.which("git") is None, reason="git binary unavailable")
def test_history_check_on_a_real_repository_survives_squash_merges(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    _git(repo, "init", "-q")
    v1, v2, t1 = b'{"v": 1}\n', b'{"v": 2}\n', 1_790_000_000
    landed = _commit_corpus(repo, v1, t1, "land corpus v1")
    _bind(repo, landed, t1, v1)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bind sidecar", when=t1 + 100)
    sidecar_commit = _git(repo, "rev-parse", "HEAD")
    assert history_check.check(repo)["status"] == "CURRENT"
    # Every claim is recomputed: time, rendering, bytes, and the commit itself.
    for bad, match in (((landed, t1 + 1, v1), "committer time"), ((landed, t1, v2), "corpus bytes"),
                       ((sidecar_commit, t1 + 100, v1), "mainline"), (("f" * 40, t1, v1), "absent")):
        _bind(repo, *bad)
        with pytest.raises(history_check.AdmissionMetadataError, match=match) as caught:
            history_check.check(repo)
        assert not isinstance(caught.value, history_check.HistoryUnavailable)
    _git(repo, "checkout", "-q", "--", history_check.SIDECAR)
    # A PR changes the corpus. Citing its own branch commit fails at the PR's merge ref ...
    _git(repo, "checkout", "-q", "-b", "pr")
    branch_commit = _commit_corpus(repo, v2, t1 + 1000, "corpus v2")
    _bind(repo, branch_commit, t1 + 1000, v2)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "cite branch commit", when=t1 + 1100)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "pr", when=t1 + 1200)
    with pytest.raises(history_check.AdmissionMetadataError, match="mainline"):
        history_check.check(repo)
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    # ... so the PR leaves the sidecar alone: STALE passes, and squash-merged main stays green.
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "reset", "-q", "--hard", branch_commit)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--squash", "pr")
    _git(repo, "commit", "-q", "-m", "squash: corpus v2", when=t1 + 2000)
    squash = _git(repo, "rev-parse", "HEAD")
    result = history_check.check(repo)
    assert (result["status"], result["commit"]) == ("STALE", landed)
    # A follow-up regenerates from the mainline squash commit.
    _bind(repo, squash, t1 + 2000, v2)
    assert history_check.check(repo)["status"] == "CURRENT"
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", "file://" + str(repo), str(shallow))
    with pytest.raises(history_check.HistoryUnavailable, match="shallow"):
        history_check.check(shallow)


def test_history_check_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(history_check, "check", lambda _root: {"status": "STALE"})
    assert history_check.main() == 0
    assert "STALE" in capsys.readouterr().err

    def failing(_root):
        raise history_check.HistoryUnavailable("shallow git history")
    monkeypatch.setattr(history_check, "check", failing)
    assert history_check.main() == 1
