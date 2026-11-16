"""Development evaluator and concrete witness controls, never model scores."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
from experiments import lutar_scope_challenge as lc


def binding():
    return {"kind": "SYNTHETIC_CONTROL", "control_name": "ORACLE",
            "harness_sha256": hashlib.sha256(Path(lc.__file__).read_bytes()).hexdigest()}


def predicted(plan, label=None):
    return [{"case_id": row["id"], "label": row["expected_label"] if label is None else label}
            for row in plan["cases"]]


def test_plan_is_deterministic_family_separated_and_source_bound():
    plan = lc.build_plan()
    assert plan == lc.build_plan()
    assert plan["case_count"] == len(plan["cases"]) == 16
    assert len(plan["training_context"]) == 8
    assert set(plan["training_families"]).isdisjoint(plan["evaluation_families"])
    assert {r["family"] for r in plan["cases"]} == set(plan["evaluation_families"])
    assert plan["arm_status"] == "NOT_RUN"
    assert plan["promotion_authority"] == plan["training_authority"] == "NONE"
    assert plan["pretraining_or_external_exposure"] == "UNOBSERVED"
    assert plan["benchmark_status"] == "PUBLIC_DEVELOPMENT_FIXTURES_NOT_BLIND_QUALIFICATION"


def test_full_sixteen_context_export_is_refused_for_this_split():
    plan = lc.build_plan()
    assert lc.check_training_context(plan["training_context"]) == plan["training_context_sha256"]
    for rows in ([], lc.lr.curriculum_candidates()["rows"], plan["training_context"][:-1]):
        with pytest.raises(ValueError):
            lc.check_training_context(rows)


def test_oracle_is_explicitly_a_synthetic_control():
    plan = lc.build_plan()
    result = lc.score_predictions(plan, predicted(plan), run_binding=binding())
    assert result["state"] == "SYNTHETIC_CONTROL_ONLY"
    assert result["accuracy"] == lc._rate(16, 16)
    assert result["unsupported_claim_rate"] == lc._rate(0, 8)
    assert result["correct_abstention_rate"] == lc._rate(4, 4)
    assert result["overabstention_rate"] == lc._rate(0, 4)
    assert result["counterfactual_pair_accuracy"] == lc._rate(4, 4)
    assert result["model_executed_here"] is result["quality_qualified"] is False


def test_always_accept_negative_control_exposes_overclaiming():
    plan = lc.build_plan()
    result = lc.score_predictions(plan, predicted(plan, "WITHIN_DECLARED_SCOPE"), run_binding=binding())
    assert result["accuracy"] == lc._rate(4, 16)
    assert result["unsupported_claim_rate"] == lc._rate(8, 8)
    assert result["correct_abstention_rate"] == lc._rate(0, 4)
    assert result["counterfactual_pair_accuracy"] == lc._rate(0, 4)


def test_always_abstain_does_not_hide_overabstention():
    plan = lc.build_plan()
    result = lc.score_predictions(plan, predicted(plan, "INSUFFICIENT_INFORMATION"), run_binding=binding())
    assert result["accuracy"] == lc._rate(4, 16)
    assert result["correct_abstention_rate"] == lc._rate(4, 4)
    assert result["overabstention_rate"] == lc._rate(4, 4)
    assert result["counterfactual_pair_accuracy"] == lc._rate(0, 4)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "unknown", "bad_label", "extra_field", "wrong_type"])
def test_incomplete_or_ambiguous_predictions_fail(mutation):
    plan = lc.build_plan()
    rows = predicted(plan)
    if mutation == "missing": rows.pop()
    elif mutation == "extra": rows.append(rows[0])
    elif mutation == "duplicate": rows[-1] = rows[0]
    elif mutation == "unknown": rows[-1]["case_id"] = "unknown"
    elif mutation == "bad_label": rows[-1]["label"] = "PASSED"
    elif mutation == "extra_field": rows[-1]["raw_content"] = "not admitted"
    else: rows[-1]["case_id"] = []
    with pytest.raises(ValueError):
        lc.score_predictions(plan, rows, run_binding=binding())


def test_plan_and_harness_drift_fail_closed():
    plan = lc.build_plan()
    changed = deepcopy(plan)
    changed["cases"][0]["expected_label"] = "OUTSIDE_DECLARED_SCOPE"
    with pytest.raises(ValueError):
        lc.score_predictions(changed, predicted(changed), run_binding=binding())
    bad = dict(binding(), harness_sha256="0" * 64)
    with pytest.raises(ValueError):
        lc.score_predictions(plan, predicted(plan), run_binding=bad)


def test_unbound_model_results_are_refused():
    plan = lc.build_plan()
    with pytest.raises(ValueError):
        lc.score_predictions(plan, predicted(plan), run_binding={"kind": "MODEL_OUTPUT", "harness_sha256": binding()["harness_sha256"]})


def test_model_identity_is_declared_not_independently_verified():
    plan = lc.build_plan()
    declared = {"kind": "MODEL_OUTPUT", "harness_sha256": binding()["harness_sha256"],
                "model_repository": "fixture/model", "model_revision": "a" * 40,
                "weights_manifest_sha256": "b" * 64, "generation_evidence_sha256": "c" * 64,
                "decoding_config_sha256": "d" * 64}
    result = lc.score_predictions(plan, predicted(plan), run_binding=declared)
    assert result["state"] == "PREDICTION_FILE_SCORED"
    assert result["run_binding_verification"] == "CALLER_DECLARED_NOT_INDEPENDENTLY_VERIFIED"
    assert result["quality_qualified"] is False
    assert result["model_executed_here"] is False


def test_concrete_counterexamples_are_real_and_not_theorem_refutations():
    rows = {(r["family"], r["variant"]): r for r in lc.build_plan()["cases"]}
    good = rows[("F4", "valid")]["prompt"]["scenario"]
    assert all(dst < src for src, dst in good["edges"])
    bad = rows[("F4", "broken_premise")]["prompt"]["scenario"]
    witness = bad["cycle_witness"]
    assert witness[0] == witness[-1]
    assert all([a, b] in bad["edges"] for a, b in zip(witness, witness[1:]))
    retry = rows[("F7", "broken_premise")]["prompt"]["scenario"]["observed_drain"]
    assert len(retry) > len(set(retry))
    for variant, expected in (("valid", True), ("broken_premise", False)):
        s = rows[("F18", variant)]["prompt"]["scenario"]
        assert s["remaining"] == s["total"] - s["erasures"]
        assert (s["remaining"] >= 6) is expected
    seq = rows[("F22", "broken_premise")]["prompt"]["scenario"]["seqLog"]
    assert seq != list(range(len(seq))) and any(a >= b for a, b in zip(seq, seq[1:]))


def test_empty_denominator_is_unavailable_not_zero_percent():
    assert lc._rate(0, 0)["available"] is False
    assert lc._rate(0, 0)["fraction"] is None


@pytest.mark.parametrize("changed", [{"kind": []}, {"extra_private_field": "not allowed"}, {"control_name": "UNKNOWN"}])
def test_origin_schema_rejects_untyped_or_extra_fields(changed):
    plan = lc.build_plan()
    with pytest.raises(ValueError):
        lc.score_predictions(plan, predicted(plan), run_binding=dict(binding(), **changed))


def test_boolean_plan_mutation_is_not_accepted_as_numeric_equality():
    plan = lc.build_plan()
    changed = deepcopy(plan)
    changed["model_executed_here"] = 0
    with pytest.raises(ValueError):
        lc.score_predictions(changed, predicted(changed), run_binding=binding())
