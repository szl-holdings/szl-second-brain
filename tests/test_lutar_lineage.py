"""Semantic/UI controls for source lineage; no proof or model-quality claims."""
import copy
import html
import importlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from second_brain.frontier import anatomy_feed, frontier_status
from second_brain.lineage_console import render_lineage
from second_brain.lutar_lineage import _digest, _project_reference, lutar_lineage
from second_brain.web import app

lr = importlib.import_module("second_brain.lutar_reference")
ll = importlib.import_module("second_brain.lutar_lineage")
client = TestClient(app)


def test_graph_is_exact_source_declaration_not_proof_graph():
    value = lutar_lineage()
    assert value["observed_reference_ready"] is value["effective_reference_ready"] is True
    assert len(value["claims"]) == 8 and len(value["nodes"]) == 33 and len(value["edges"]) == 32
    ids = {n["id"] for n in value["nodes"]}
    assert len(ids) == 33
    assert all(e["source"] in ids and e["target"] in ids for e in value["edges"])
    assert {e["relation"] for e in value["edges"]} == {"DECLARES", "NAMES_CARRIER"}
    assert value["open_gates"] == ["proof", "meaning", "runtime", "quality"]
    assert value["coverage"]["proof_replay"]["observed"] is None
    assert value["coverage"]["proof_replay"]["available"] is False


def test_digest_binds_the_complete_projection():
    first, second = lutar_lineage(), lutar_lineage()
    assert first == second
    expected = first.pop("snapshot_sha256")
    assert expected == _digest(first)
    first["runtime_refinement"] = "CHANGED"
    assert _digest(first) != expected


@pytest.mark.parametrize("scenario", ["observed", "withhold-source"])
def test_all_surfaces_preserve_no_authority_and_no_content(scenario):
    value = lutar_lineage(scenario=scenario)
    for key in ("training_authority", "promotion_authority", "execution_authority", "merge_authority"):
        assert value[key] == "NONE"
    assert value["production_qualification"] == "NOT_ASSESSED"
    assert value["proof_replayed_here"] is False
    assert value["raw_graph_nodes_admitted_to_gradients"] == 0
    assert value["private_graph_present"] is False
    for forbidden in ('"content":', '"text":', '"hypotheses":', '"source_declared_answer":'):
        assert forbidden not in json.dumps(value)
    assert value["lambda"] == "CONJECTURE_1_OPEN_FALSE_AS_STATED"


def test_rehearsal_only_removes_support_without_mutating_reference():
    reference = lr.lutar_reference()
    before = copy.deepcopy(reference)
    observed = _project_reference(reference)
    withheld = _project_reference(reference, scenario="withhold-source")
    assert reference == before
    assert withheld["observed_reference_ready"] is True
    assert withheld["effective_reference_ready"] is False
    assert withheld["claims"] == [] and withheld["edges"] == []
    assert withheld["impact"] == {"withdrawn_claim_handles": 8, "withdrawn_carrier_names": 24,
                                  "files_changed": 0, "provider_calls": 0, "actions_performed": 0}
    assert set(observed["open_gates"]) <= set(withheld["open_gates"])
    assert {n["id"] for n in withheld["nodes"]} <= {n["id"] for n in observed["nodes"]}
    assert lutar_lineage() == observed


@pytest.mark.parametrize("scenario", ["observed", "withhold-source"])
def test_one_source_read_per_request(scenario):
    with patch.object(ll, "lutar_reference", wraps=lr.lutar_reference) as read:
        assert client.get("/lutar", params={"scenario": scenario}).status_code == 200
    read.assert_called_once_with()
    with patch.object(ll, "lutar_reference", wraps=lr.lutar_reference) as read:
        assert client.get("/api/v1/lutar-lineage", params={"scenario": scenario}).status_code == 200
    read.assert_called_once_with()


def test_anatomy_reuses_one_reference_without_touching_frontier():
    before = frontier_status()
    with patch.object(lr, "lutar_reference", wraps=lr.lutar_reference) as read:
        feed = anatomy_feed()
    read.assert_called_once_with()
    assert feed["lutar_lineage"] == _project_reference(feed["lutar_invariants"])
    assert feed["lutar_lineage"]["snapshot_sha256"] == lutar_lineage()["snapshot_sha256"]
    assert frontier_status() == before


@pytest.mark.parametrize("raw", [b"{}", b"invalid", b"x" * (lr.MAX_SOURCE_BYTES + 1)])
def test_missing_changed_or_oversized_source_removes_support_then_recovers(tmp_path, monkeypatch, raw):
    canonical = lr.data_file(lr.SOURCE_FILE).read_bytes()
    source = tmp_path / "reference.json"
    monkeypatch.setattr(lr, "data_file", lambda _: source)
    original_frontier = frontier_status()
    for data in (None, raw):
        if data is not None:
            source.write_bytes(data)
        for route in ("/lutar", "/api/v1/lutar-lineage"):
            assert client.get(route).status_code == 503
        value = client.get("/api/v1/lutar-lineage").json()
        assert value["claims"] == [] and value["coverage"]["claim_handles"]["observed"] == 0
        assert value["impact"]["withdrawn_claim_handles"] == 0
        assert "source" in value["open_gates"]
    source.write_bytes(canonical)
    assert client.get("/lutar").status_code == 200
    assert client.get("/api/v1/lutar-lineage").json()["effective_reference_ready"] is True
    assert frontier_status() == original_frontier


@pytest.mark.parametrize("field,value", [
    ("source_revision", "main"), ("source_sha256", "0" * 64),
    ("runtime_refinement", "VERIFIED"), ("training_authority", "ALLOW"),
    ("handles_sha256", "0" * 64), ("independent_checker", "PASSED"),
    ("declared_locked_count", 9), ("proof_replayed_here", True)])
def test_local_reference_inconsistencies_fail_unavailable(field, value):
    reference = lr.lutar_reference()
    reference[field] = value
    result = _project_reference(reference)
    assert result["observed_reference_ready"] is False
    assert result["claims"] == []
    assert result["execution_authority"] == "NONE"


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "foreign", "carrier-duplicate"])
def test_bad_handle_inventory_is_not_partial_success(mutation):
    reference = lr.lutar_reference()
    if mutation == "duplicate":
        reference["handles"][1] = reference["handles"][0]
    elif mutation == "missing":
        reference["handles"].pop()
    elif mutation == "foreign":
        reference["handles"][0]["claimId"] = "F23"
    else:
        reference["handles"][1]["declarationNames"] = reference["handles"][0]["declarationNames"]
    reference["handles_sha256"] = _digest(reference["handles"])
    assert _project_reference(reference)["claims"] == []


@pytest.mark.parametrize("scenario", ["observed", "withhold-source"])
def test_html_api_parity_and_headers(scenario):
    args = {"scenario": scenario}
    page = client.get("/lutar", params=args)
    api = client.get("/api/v1/lutar-lineage", params=args)
    value = api.json()
    assert page.status_code == api.status_code == 200
    assert value["snapshot_sha256"] in page.text
    assert html.escape(json.dumps(value, indent=2, ensure_ascii=False), quote=True) in page.text
    assert page.headers["cache-control"] == api.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert '<script' not in page.text
    assert 'method="get"' in page.text
    assert 'href="/lutar"' in client.get("/").text
    if scenario != "observed":
        assert 'hypothetical' in page.text and '0 / 8' in page.text


@pytest.mark.parametrize("scenario", ["promote", "allow", "https://example.invalid", "<script>x</script>", ""])
def test_unknown_scenario_never_triggers_a_source_read(scenario):
    with patch.object(ll, "lutar_reference") as read:
        assert client.get("/lutar", params={"scenario": scenario}).status_code == 422
        assert client.get("/api/v1/lutar-lineage", params={"scenario": scenario}).status_code == 422
    read.assert_not_called()


def test_renderer_escapes_source_derived_strings():
    value = lutar_lineage()
    value["claims"][0]["title"] = '<img src=x onerror="bad()">'
    page = render_lineage(value)
    assert '<img ' not in page and '&lt;img' in page


@pytest.mark.parametrize("module", ["app", "app_operational", "app_refinement", "second_brain.web"])
def test_routes_wired_in_all_existing_entrypoints(module):
    code = (f"from {module} import app; from fastapi.testclient import TestClient; "
            "c=TestClient(app); assert c.get('/lutar').status_code==200; "
            "assert c.get('/api/v1/lutar-lineage').json()['coverage']['claim_handles']['observed']==8")
    subprocess.run([sys.executable, "-B", "-c", code], check=True, timeout=25)
