"""Adversarial offline tests for the unsigned temporal-evidence prototype."""
import copy
import json
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, ".")

from second_brain.temporal_evidence import (
    ABSTAIN,
    CURRENT_CANDIDATE,
    EXPLAIN_CONFLICT,
    MAX_EVIDENCE,
    MAX_LINKS_PER_RECORD,
    SCHEMA,
    TRUTH_LABEL,
    WARN_STALE,
    TemporalEvidenceError,
    TemporalEvidenceLedger,
    compute_metadata_sha256,
)


def evidence(identity="evidence:e1", claim="claim:c", **changes):
    record = {
        "evidence_id": identity,
        "claim_id": claim,
        "source_handle": "handle:public-source",
        "content_sha256": "a" * 64,
        "recorded_at": 0,
        "valid_from": 0,
        "valid_until": 110,
        "rights": "apache-2.0",
        "supersedes": [],
        "contradicts": [],
    }
    record.update(changes)
    if "metadata_sha256" not in changes:
        record["metadata_sha256"] = compute_metadata_sha256(record)
    return record


def tampered(record, **changes):
    result = copy.deepcopy(record)
    result.update(changes)
    return result


def decision(receipt, identity):
    return next(item for item in receipt["decisions"] if item["evidence_id"] == identity)


class TemporalLifecycleTests(unittest.TestCase):
    def test_current_candidate_is_explicitly_unsigned_and_not_grounded(self):
        receipt = TemporalEvidenceLedger([evidence()]).evaluate("claim:c", 100)
        self.assertEqual(receipt["state"], CURRENT_CANDIDATE)
        self.assertIsNone(receipt["code"])
        self.assertEqual(receipt["candidate_evidence_id"], "evidence:e1")
        self.assertEqual(receipt["candidate_metadata_sha256"],
                         decision(receipt, "evidence:e1")["metadata_sha256"])
        self.assertEqual(receipt["truth_label"], TRUTH_LABEL)
        self.assertEqual(receipt["signed_provenance"], "NOT_ESTABLISHED")
        self.assertEqual(receipt["grounded_navigation"], "NOT_ESTABLISHED")
        self.assertEqual(receipt["semantic_support"], "NOT_EVALUATED")
        self.assertEqual(receipt["runtime_integration"], "NOT_APPLIED")
        self.assertEqual(receipt["execution_authority"], "NONE")
        json.dumps(receipt, allow_nan=False)

    def test_validity_start_is_inclusive(self):
        receipt = TemporalEvidenceLedger([evidence()]).evaluate("claim:c", 0)
        self.assertEqual(receipt["state"], CURRENT_CANDIDATE)

    def test_validity_end_is_exclusive(self):
        receipt = TemporalEvidenceLedger([evidence()]).evaluate("claim:c", 110)
        self.assertEqual((receipt["state"], receipt["code"]),
                         (WARN_STALE, "TEMPORAL_STALE_ONLY"))
        self.assertIsNone(receipt["candidate_evidence_id"])
        self.assertEqual(decision(receipt, "evidence:e1")["code"],
                         "TEMPORAL_STALE_AT_AS_OF")

    def test_open_ended_interval_remains_current(self):
        record = evidence(valid_until=None)
        receipt = TemporalEvidenceLedger([record]).evaluate("claim:c", 10**12)
        self.assertEqual(receipt["state"], CURRENT_CANDIDATE)

    def test_future_validity_abstains(self):
        record = evidence(recorded_at=-10, valid_from=0)
        receipt = TemporalEvidenceLedger([record]).evaluate("claim:c", -1)
        self.assertEqual((receipt["state"], receipt["code"]),
                         (ABSTAIN, "TEMPORAL_FUTURE_EVIDENCE"))
        self.assertEqual(decision(receipt, "evidence:e1")["code"],
                         "TEMPORAL_FUTURE_VALIDITY")

    def test_future_observation_abstains_even_when_interval_is_current(self):
        record = evidence(recorded_at=20)
        receipt = TemporalEvidenceLedger([record]).evaluate("claim:c", 10)
        self.assertEqual(receipt["state"], ABSTAIN)
        self.assertEqual(decision(receipt, "evidence:e1")["code"],
                         "TEMPORAL_FUTURE_OBSERVATION")
        self.assertEqual(decision(receipt, "evidence:e1")["axes"]["recorded_by_as_of"], 0)

    def test_stale_evidence_is_reported_but_does_not_veto_a_current_record(self):
        old = evidence("evidence:old", valid_until=50)
        current = evidence("evidence:new", valid_until=200)
        receipt = TemporalEvidenceLedger([old, current]).evaluate("claim:c", 100)
        self.assertEqual(receipt["state"], CURRENT_CANDIDATE)
        self.assertEqual(receipt["candidate_evidence_id"], "evidence:new")
        self.assertEqual(decision(receipt, "evidence:old")["state"], WARN_STALE)

    def test_unknown_rights_zero_vetoes_otherwise_current_evidence(self):
        record = evidence(rights="unknown")
        receipt = TemporalEvidenceLedger([record]).evaluate("claim:c", 100)
        self.assertEqual((receipt["state"], receipt["code"]),
                         (ABSTAIN, "TEMPORAL_RIGHTS_NOT_ADMISSIBLE"))
        item = decision(receipt, "evidence:e1")
        self.assertEqual(item["zero_veto_pass"], 0)
        self.assertIn("rights_admissible", item["vetoed_by"])

    def test_rights_ineligible_record_cannot_create_ambiguity_or_conflict(self):
        allowed = evidence("evidence:allowed")
        unknown = evidence("evidence:unknown", rights="unknown",
                           contradicts=["evidence:allowed"])
        receipt = TemporalEvidenceLedger([allowed, unknown]).evaluate("claim:c", 100)
        self.assertEqual(receipt["state"], CURRENT_CANDIDATE)
        self.assertEqual(receipt["candidate_evidence_id"], "evidence:allowed")
        self.assertEqual(receipt["conflicting_evidence_pairs"], [])

    def test_multiple_current_records_without_links_are_ambiguous(self):
        records = [evidence("evidence:e1"), evidence("evidence:e2")]
        receipt = TemporalEvidenceLedger(records).evaluate("claim:c", 100)
        self.assertEqual((receipt["state"], receipt["code"]),
                         (ABSTAIN, "TEMPORAL_AMBIGUOUS_CURRENT_EVIDENCE"))
        self.assertIsNone(receipt["candidate_evidence_id"])
        self.assertEqual(len(receipt["eligible_evidence_ids"]), 2)

    def test_current_contradiction_explains_conflict_without_selecting(self):
        first = evidence("evidence:e1", contradicts=["evidence:e2"])
        second = evidence("evidence:e2")
        receipt = TemporalEvidenceLedger([first, second]).evaluate("claim:c", 100)
        self.assertEqual((receipt["state"], receipt["code"]),
                         (EXPLAIN_CONFLICT, "TEMPORAL_CONTRADICTORY_CURRENT_EVIDENCE"))
        self.assertEqual(receipt["conflicting_evidence_pairs"],
                         [["evidence:e1", "evidence:e2"]])
        self.assertIsNone(receipt["candidate_evidence_id"])

    def test_reciprocal_contradiction_declarations_are_one_edge(self):
        first = evidence("evidence:e1", contradicts=["evidence:e2"])
        second = evidence("evidence:e2", contradicts=["evidence:e1"])
        receipt = TemporalEvidenceLedger([first, second]).evaluate("claim:c", 100)
        self.assertEqual(receipt["conflicting_evidence_pairs"],
                         [["evidence:e1", "evidence:e2"]])

    def test_uninvolved_current_record_abstains_when_other_pair_conflicts(self):
        records = [
            evidence("evidence:e1", contradicts=["evidence:e2"]),
            evidence("evidence:e2"),
            evidence("evidence:e3"),
        ]
        receipt = TemporalEvidenceLedger(records).evaluate("claim:c", 100)
        self.assertEqual(receipt["state"], EXPLAIN_CONFLICT)
        self.assertEqual(decision(receipt, "evidence:e3")["code"],
                         "TEMPORAL_CONFLICT_BLOCKS_CLAIM")

    def test_stale_contradiction_does_not_block_current_evidence(self):
        stale = evidence("evidence:old", valid_until=50,
                         contradicts=["evidence:new"])
        current = evidence("evidence:new", valid_until=200)
        receipt = TemporalEvidenceLedger([stale, current]).evaluate("claim:c", 100)
        self.assertEqual(receipt["state"], CURRENT_CANDIDATE)
        self.assertEqual(receipt["conflicting_evidence_pairs"], [])

    def test_active_supersession_excludes_old_evidence(self):
        old = evidence("evidence:old", valid_until=200)
        new = evidence("evidence:new", valid_from=100, valid_until=200,
                       supersedes=["evidence:old"])
        receipt = TemporalEvidenceLedger([old, new]).evaluate("claim:c", 150)
        self.assertEqual(receipt["candidate_evidence_id"], "evidence:new")
        self.assertEqual(decision(receipt, "evidence:old")["code"],
                         "TEMPORAL_SUPERSEDED_AT_AS_OF")

    def test_future_successor_does_not_supersede_before_its_start(self):
        old = evidence("evidence:old", valid_until=200)
        new = evidence("evidence:new", valid_from=100, valid_until=200,
                       supersedes=["evidence:old"])
        receipt = TemporalEvidenceLedger([old, new]).evaluate("claim:c", 50)
        self.assertEqual(receipt["candidate_evidence_id"], "evidence:old")
        self.assertEqual(decision(receipt, "evidence:new")["code"],
                         "TEMPORAL_FUTURE_VALIDITY")

    def test_transitive_supersession_excludes_all_older_records(self):
        first = evidence("evidence:e1", valid_until=200)
        second = evidence("evidence:e2", valid_until=200,
                          supersedes=["evidence:e1"])
        third = evidence("evidence:e3", valid_from=100, valid_until=200,
                         supersedes=["evidence:e2"])
        receipt = TemporalEvidenceLedger([first, second, third]).evaluate("claim:c", 150)
        self.assertEqual(receipt["candidate_evidence_id"], "evidence:e3")
        self.assertEqual(decision(receipt, "evidence:e1")["axes"]["not_superseded"], 0)
        self.assertEqual(decision(receipt, "evidence:e2")["axes"]["not_superseded"], 0)


class TemporalValidationTests(unittest.TestCase):
    def assert_code(self, code, records):
        with self.assertRaises(TemporalEvidenceError) as caught:
            TemporalEvidenceLedger(records)
        self.assertEqual(caught.exception.code, code)

    def test_top_level_and_record_types_are_strict(self):
        for records in (None, {}, (), "records"):
            with self.subTest(records=type(records).__name__):
                self.assert_code("TEMPORAL_RECORD_LIST_INVALID", records)
        self.assert_code("TEMPORAL_RECORD_TYPE_INVALID", [object()])

    def test_missing_extra_and_raw_content_fields_are_rejected(self):
        valid = evidence()
        missing = copy.deepcopy(valid)
        missing.pop("rights")
        self.assert_code("TEMPORAL_RECORD_FIELDS_INVALID", [missing])
        extra = tampered(valid, content="PRIVATE_SENTINEL_9f27")
        with self.assertRaises(TemporalEvidenceError) as caught:
            TemporalEvidenceLedger([extra])
        self.assertEqual(caught.exception.code, "TEMPORAL_RECORD_FIELDS_INVALID")
        self.assertNotIn("PRIVATE_SENTINEL_9f27", str(caught.exception))

    def test_strict_evidence_ids(self):
        bad_values = (None, 1, True, "", "e1", "evidence:", "evidence:A",
                      "evidence:a b", "evidence:a/", "evidence:a.", "claim:e1")
        for bad in bad_values:
            with self.subTest(bad=bad):
                self.assert_code("TEMPORAL_EVIDENCE_ID_INVALID",
                                 [tampered(evidence(), evidence_id=bad)])

    def test_claim_source_and_link_identifiers_are_namespaced(self):
        self.assert_code("TEMPORAL_CLAIM_ID_INVALID",
                         [tampered(evidence(), claim_id="c")])
        self.assert_code("TEMPORAL_SOURCE_HANDLE_INVALID",
                         [tampered(evidence(), source_handle="https://example.invalid")])
        self.assert_code("TEMPORAL_LINK_ID_INVALID",
                         [tampered(evidence(), contradicts=["e2"])])

    def test_content_and_metadata_sha256_are_lowercase_hex(self):
        self.assert_code("TEMPORAL_CONTENT_SHA256_INVALID",
                         [tampered(evidence(), content_sha256="A" * 64)])
        self.assert_code("TEMPORAL_METADATA_SHA256_INVALID",
                         [evidence(metadata_sha256="0" * 63)])
        self.assert_code("TEMPORAL_METADATA_SHA256_MISMATCH",
                         [evidence(metadata_sha256="0" * 64)])

    def test_metadata_tampering_is_detected(self):
        record = tampered(evidence(), rights="mit")
        self.assert_code("TEMPORAL_METADATA_SHA256_MISMATCH", [record])

    def test_metadata_digest_normalizes_link_order(self):
        forward = evidence(contradicts=["evidence:e2", "evidence:e3"])
        reverse = evidence(contradicts=["evidence:e3", "evidence:e2"])
        self.assertEqual(forward["metadata_sha256"], reverse["metadata_sha256"])

    def test_nonfinite_and_non_real_timestamps_fail_closed(self):
        bad_values = (None, "100", True, False, float("nan"), float("inf"),
                      float("-inf"), 10**1000)
        for field in ("recorded_at", "valid_from", "valid_until"):
            values = bad_values[1:] if field == "valid_until" else bad_values
            for bad in values:
                with self.subTest(field=field, bad=repr(bad)):
                    self.assert_code("TEMPORAL_TIMESTAMP_INVALID",
                                     [tampered(evidence(), **{field: bad})])

    def test_empty_or_reversed_validity_intervals_are_rejected(self):
        for start, end in ((10, 10), (11, 10), (0, -1)):
            with self.subTest(start=start, end=end):
                self.assert_code("TEMPORAL_VALIDITY_INTERVAL_INVALID",
                                 [tampered(evidence(), valid_from=start, valid_until=end)])

    def test_rights_field_is_bounded_and_machine_readable(self):
        for bad in (None, True, "", "unknown rights", "a" * 65, "proprietary all rights"):
            with self.subTest(bad=bad):
                self.assert_code("TEMPORAL_RIGHTS_FIELD_INVALID",
                                 [tampered(evidence(), rights=bad)])

    def test_duplicate_evidence_ids_are_rejected(self):
        self.assert_code("TEMPORAL_DUPLICATE_EVIDENCE_ID",
                         [evidence(), evidence()])

    def test_duplicate_links_are_rejected(self):
        for field in ("supersedes", "contradicts"):
            with self.subTest(field=field):
                self.assert_code("TEMPORAL_DUPLICATE_LINK",
                                 [tampered(evidence(), **{field: ["evidence:e2", "evidence:e2"]})])

    def test_missing_references_are_rejected(self):
        for field in ("supersedes", "contradicts"):
            with self.subTest(field=field):
                self.assert_code("TEMPORAL_MISSING_REFERENCE",
                                 [evidence(**{field: ["evidence:ghost"]})])

    def test_self_links_are_rejected(self):
        for field in ("supersedes", "contradicts"):
            with self.subTest(field=field):
                self.assert_code("TEMPORAL_SELF_LINK",
                                 [evidence(**{field: ["evidence:e1"]})])

    def test_cross_claim_links_are_rejected(self):
        for field in ("supersedes", "contradicts"):
            with self.subTest(field=field):
                first = evidence("evidence:e1", **{field: ["evidence:e2"]})
                second = evidence("evidence:e2", claim="claim:other")
                self.assert_code("TEMPORAL_CROSS_CLAIM_LINK", [first, second])

    def test_two_node_and_three_node_supersession_cycles_are_rejected(self):
        first = evidence("evidence:e1", supersedes=["evidence:e2"])
        second = evidence("evidence:e2", supersedes=["evidence:e1"])
        self.assert_code("TEMPORAL_SUPERSESSION_CYCLE", [first, second])
        first = evidence("evidence:e1", supersedes=["evidence:e3"])
        second = evidence("evidence:e2", supersedes=["evidence:e1"])
        third = evidence("evidence:e3", supersedes=["evidence:e2"])
        self.assert_code("TEMPORAL_SUPERSESSION_CYCLE", [first, second, third])

    def test_contradiction_triangle_is_a_conflict_not_a_false_cycle(self):
        records = [
            evidence("evidence:e1", contradicts=["evidence:e2"]),
            evidence("evidence:e2", contradicts=["evidence:e3"]),
            evidence("evidence:e3", contradicts=["evidence:e1"]),
        ]
        receipt = TemporalEvidenceLedger(records).evaluate("claim:c", 100)
        self.assertEqual(receipt["state"], EXPLAIN_CONFLICT)
        self.assertEqual(len(receipt["conflicting_evidence_pairs"]), 3)


class TemporalBoundsAndDeterminismTests(unittest.TestCase):
    def test_record_count_is_bounded(self):
        records = [evidence("evidence:e%d" % index) for index in range(MAX_EVIDENCE + 1)]
        with self.assertRaises(TemporalEvidenceError) as caught:
            TemporalEvidenceLedger(records)
        self.assertEqual(caught.exception.code, "TEMPORAL_RECORD_LIMIT_EXCEEDED")

    def test_each_link_list_is_bounded(self):
        links = ["evidence:e%d" % index for index in range(MAX_LINKS_PER_RECORD + 1)]
        with self.assertRaises(TemporalEvidenceError) as caught:
            TemporalEvidenceLedger([tampered(evidence(), contradicts=links)])
        self.assertEqual(caught.exception.code, "TEMPORAL_LINK_LIMIT_EXCEEDED")

    def test_total_link_count_is_bounded(self):
        identities = ["evidence:e%d" % index for index in range(33)]
        records = [evidence(identity, contradicts=[other for other in identities if other != identity])
                   for identity in identities]
        with self.assertRaises(TemporalEvidenceError) as caught:
            TemporalEvidenceLedger(records)
        self.assertEqual(caught.exception.code, "TEMPORAL_TOTAL_LINK_LIMIT_EXCEEDED")

    def test_evaluation_is_order_independent_and_input_mutation_safe(self):
        records = [evidence("evidence:e2"), evidence("evidence:e1")]
        original = copy.deepcopy(records)
        ledger = TemporalEvidenceLedger(records)
        before = ledger.evaluate("claim:c", 100)
        records[0]["rights"] = "unknown"
        records.reverse()
        after = ledger.evaluate("claim:c", 100)
        self.assertNotEqual(records, original)
        self.assertEqual(original[0]["rights"], "apache-2.0")
        self.assertEqual(before, after)
        reversed_ledger = TemporalEvidenceLedger(copy.deepcopy(original[::-1]))
        self.assertEqual(ledger.ledger_sha256, reversed_ledger.ledger_sha256)
        self.assertEqual(before, reversed_ledger.evaluate("claim:c", 100))

    def test_query_failures_abstain_without_nonfinite_json_or_raw_input_echo(self):
        ledger = TemporalEvidenceLedger([evidence()])
        for bad in (True, None, "100", float("nan"), float("inf"), 10**1000):
            with self.subTest(bad=repr(bad)):
                receipt = ledger.evaluate("claim:c", bad)
                self.assertEqual(receipt["code"], "TEMPORAL_AS_OF_INVALID")
                self.assertEqual(receipt["state"], ABSTAIN)
                self.assertIsNone(receipt["as_of"])
                json.dumps(receipt, allow_nan=False)
        bad_claim = "PRIVATE_CLAIM_SENTINEL"
        receipt = ledger.evaluate(bad_claim, 100)
        self.assertEqual(receipt["code"], "TEMPORAL_QUERY_CLAIM_ID_INVALID")
        self.assertNotIn(bad_claim, json.dumps(receipt))

    def test_unknown_claim_and_empty_ledger_abstain(self):
        for ledger in (TemporalEvidenceLedger([]), TemporalEvidenceLedger([evidence()])):
            receipt = ledger.evaluate("claim:missing", 100)
            self.assertEqual((receipt["state"], receipt["code"]),
                             (ABSTAIN, "TEMPORAL_UNKNOWN_CLAIM"))
            self.assertEqual(receipt["decisions"], [])

    def test_receipt_exposes_handles_only_as_digests_not_source_or_content(self):
        record = evidence()
        source_handle = record["source_handle"]
        content_sha = record["content_sha256"]
        receipt = TemporalEvidenceLedger([record]).evaluate("claim:c", 100)
        encoded = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(source_handle, encoded)
        self.assertNotIn(content_sha, encoded)
        self.assertNotIn("source_handle", encoded)
        self.assertNotIn("content_sha256", encoded)
        self.assertEqual(receipt["schema"], SCHEMA)

    def test_evaluation_does_not_open_network_or_use_wall_clock(self):
        ledger = TemporalEvidenceLedger([evidence()])
        with mock.patch.object(socket, "create_connection",
                               side_effect=AssertionError("NETWORK_FORBIDDEN")), \
                mock.patch.object(socket.socket, "connect",
                                  side_effect=AssertionError("NETWORK_FORBIDDEN")), \
                mock.patch("time.time", side_effect=AssertionError("WALL_CLOCK_FORBIDDEN")):
            self.assertEqual(ledger.evaluate("claim:c", 100),
                             ledger.evaluate("claim:c", 100))


if __name__ == "__main__":
    unittest.main()
