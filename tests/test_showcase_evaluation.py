from __future__ import annotations

import copy
import json

import pytest

from examples.showcase.engine import Showcase, fixture_revision, read_fixture
from examples.showcase.evaluate import evaluate, load_queries
from examples.showcase.engine import HERE
from examples.showcase.record import snapshot, write_artifacts


@pytest.fixture
def evaluated():
    demo = Showcase.bundled()
    cases, _ = load_queries()
    predictions = {r["id"]: demo.query(r["query"]) for r in cases}
    return demo, predictions, evaluate(demo, predictions=predictions)


def test_wrong_selected_citation_fails_even_when_correct_evidence_is_retrieved(evaluated):
    demo, predictions, before = evaluated
    output = predictions["eval-status"]
    assert "syn-beacon" in output["retrieved_ids"]
    other = demo.by_id["syn-beacon-color"]
    output["citations"] = [demo.citation(other, other.claims[0])]
    after = evaluate(demo, predictions=predictions)
    a, b = (x["splits"]["evaluation"] for x in (before, after))
    assert a["retrieval_micro_recall_at_k"] == b["retrieval_micro_recall_at_k"]
    assert b["selected_citation_correctness"]["success"] == a["selected_citation_correctness"]["success"] - 1
    assert b["selected_citation_correctness"]["total"] == a["selected_citation_correctness"]["total"]


def test_wrong_statement_from_the_correct_multiclaim_record_fails():
    values, _ = read_fixture("records.json")
    row = next(r for r in values if r["id"] == "syn-beacon")
    row["claims"].append({"kind": "fact", "subject": "aster beacon",
                          "predicate": "temperature", "object": "cold"})
    row["text"] += " aster beacon | temperature | cold."
    demo = Showcase(values, fixture_revision(values))
    cases, _ = load_queries()
    predictions = {r["id"]: demo.query(r["query"]) for r in cases}
    record = demo.by_id["syn-beacon"]
    predictions["eval-status"]["citations"] = [demo.citation(record, record.claims[1])]
    report = evaluate(demo, predictions=predictions)
    measured = next(r for r in report["details"] if r["id"] == "eval-status")
    assert measured["evidence_valid"] and measured["answer_correct"]
    assert not measured["selection_correct"] and not measured["exact"]


@pytest.mark.parametrize("bad", [None, "{broken", "[]", '{"x":1,"x":2}', {}, {"state": "ABSTAIN"}])
def test_parse_and_schema_failures_keep_full_denominators(evaluated, bad):
    demo, predictions, before = evaluated
    predictions["eval-status"] = bad
    after = evaluate(demo, predictions=predictions)
    a, b = (x["splits"]["evaluation"] for x in (before, after))
    assert b["schema_validity"]["total"] == 24
    assert b["schema_validity"]["success"] == a["schema_validity"]["success"] - 1
    assert b["supported_answer_coverage"]["total"] == a["supported_answer_coverage"]["total"]
    assert b["supported_answer_coverage"]["success"] == a["supported_answer_coverage"]["success"] - 1


def test_missing_outputs_and_raised_exceptions_are_failures(evaluated, monkeypatch):
    demo, predictions, _ = evaluated
    del predictions["eval-status"]
    report = evaluate(demo, predictions=predictions)
    failed = next(r for r in report["details"] if r["id"] == "eval-status")
    assert failed["error"] == "KeyError" and not failed["exact"]

    def fail(*args, **kwargs):
        raise RuntimeError("simulated runtime failure")

    monkeypatch.setattr(demo, "query", fail)
    report = evaluate(demo)
    assert report["splits"]["evaluation"]["schema_validity"] == {"success": 0, "total": 24, "rate": 0}
    assert report["splits"]["evaluation"]["unsafe_or_invalid_negative_output"]["rate"] == 1


@pytest.mark.parametrize("field,value", [("source_id", "synthetic:forged"), ("date", "2026-10-03"),
                                        ("text_sha256", "0" * 64), ("quote", "invented statement")])
def test_citation_integrity_is_independent_of_a_plausible_answer(evaluated, field, value):
    demo, predictions, before = evaluated
    predictions["eval-status"]["citations"][0][field] = value
    report = evaluate(demo, predictions=predictions)
    row = next(r for r in report["details"] if r["id"] == "eval-status")
    assert row["answer_correct"] and row["schema_valid"]
    assert not row["evidence_valid"] and not row["exact"]
    assert report["splits"]["evaluation"]["citation_integrity"]["success"] == 23


def test_abstention_with_steps_and_fabricated_edges_fail(evaluated):
    demo, predictions, _ = evaluated
    predictions["eval-reversed"]["steps"] = copy.deepcopy(predictions["eval-path-2"]["steps"])
    predictions["eval-path-2"]["steps"][0]["predicate"] = "proves"
    report = evaluate(demo, predictions=predictions)
    rows = {r["id"]: r for r in report["details"]}
    assert not rows["eval-reversed"]["schema_valid"]
    assert not rows["eval-path-2"]["evidence_valid"]
    assert report["splits"]["evaluation"]["supported_navigation"]["success"] == 2


def test_always_abstain_control_cannot_pass_supported_coverage(evaluated):
    demo, predictions, _ = evaluated
    for output in predictions.values():
        output.update(state="ABSTAIN", reason="UNKNOWN_FACT", answer=None, citations=[], steps=[])
    report = evaluate(demo, predictions=predictions)
    metrics = report["splits"]["evaluation"]
    assert metrics["schema_validity"]["rate"] == 1
    assert metrics["supported_answer_coverage"]["success"] == 0
    assert metrics["selected_citation_correctness"]["success"] == 0
    assert metrics["supported_navigation"]["success"] == 0


def test_wrong_answer_and_reordered_path_cannot_pass(evaluated):
    demo, predictions, _ = evaluated
    predictions["eval-status"]["answer"] = "inactive"
    predictions["eval-path-2"]["steps"].reverse()
    predictions["eval-path-2"]["citations"].reverse()
    report = evaluate(demo, predictions=predictions)
    rows = {r["id"]: r for r in report["details"]}
    assert rows["eval-status"]["selection_correct"] and not rows["eval-status"]["answer_correct"]
    assert not rows["eval-path-2"]["navigation_correct"]
    assert not rows["eval-status"]["exact"] and not rows["eval-path-2"]["exact"]


def test_committed_measurement_and_static_page_are_reproducible(tmp_path):
    baseline = json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))
    assert baseline == snapshot()
    write_artifacts(tmp_path)
    for name in ("baseline.json", "index.html"):
        assert (tmp_path / name).read_bytes() == (HERE / name).read_bytes()
