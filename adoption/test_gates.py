import unittest

from adoption.gates import (ADMITTED, DIGEST_MISMATCH_REJECTED, Gate, GateVerdict, MALFORMED_REJECTED,
                            PinError, SourcePin, STALE_UNKNOWN, TenPassLedger,
                            UNSUPPORTED_CLAIM_REJECTED)

NOW = 10_000.0
DIG = "c" * 64
OTHER = "d" * 64
URL = "https://arxiv.org/abs/2104.08663"


def pin(claim="BEIR leaders evaluate dense retrieval on 18 tasks",
        supported=True, ts=NOW, window=600.0, digest=DIG, kind="leader-attribution"):
    return SourcePin(url=URL, retrieved_ts=ts, window_s=window,
                     content_digest=digest, claim=claim, claim_kind=kind,
                     claim_supported=supported)


class PinTests(unittest.TestCase):
    def test_malformed_pin_raises(self):
        for bad in (lambda: pin(ts=-1.0), lambda: pin(window=0.0),
                    lambda: pin(digest="zz" * 32), lambda: pin(claim=""),
                    lambda: pin(kind="not-a-kind")):
            with self.assertRaises(PinError):
                bad()
        with self.assertRaises(PinError):
            SourcePin(url="http://not-https", retrieved_ts=NOW, window_s=600.0,
                      content_digest=DIG, claim="x", claim_kind="leader-attribution",
                      claim_supported=True)

    def test_malformed_stale_pin_is_malformed(self):
        # malformed dominates: a broken digest cannot be relabeled stale
        with self.assertRaises(PinError):
            SourcePin(url=URL, retrieved_ts=NOW - 100_000.0, window_s=1.0,
                      content_digest="zz" * 32, claim="x",
                      claim_kind="leader-attribution", claim_supported=True)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate = Gate()

    def test_admitted_when_pinned_fresh_digest_matching_supported(self):
        v = self.gate.evaluate(pin(), NOW + 100.0, DIG)
        self.assertEqual(v.outcome, ADMITTED)
        self.assertIn("not a quality result", v.reason)
        self.assertEqual(v.pin_digest, DIG)
        self.assertEqual(v.evaluated_ts, NOW + 100.0)

    def test_staleness_boundary_exact(self):
        # delta == window -> still fresh (boundary inclusive)
        v = self.gate.evaluate(pin(window=600.0), NOW + 600.0, DIG)
        self.assertEqual(v.outcome, ADMITTED)
        # delta beyond window -> STALE_UNKNOWN, never admitted
        v2 = self.gate.evaluate(pin(window=600.0), NOW + 600.001, DIG)
        self.assertEqual(v2.outcome, STALE_UNKNOWN)

    def test_stale_pin_unknown_never_admitted(self):
        v = self.gate.evaluate(pin(), NOW + 10_000.0, DIG)
        self.assertEqual(v.outcome, STALE_UNKNOWN)
        self.assertIn("UNKNOWN", v.reason)

    def test_future_retrieved_timestamp_rejected(self):
        v = self.gate.evaluate(pin(ts=NOW + 50.0), NOW, DIG)
        self.assertEqual(v.outcome, MALFORMED_REJECTED)
        self.assertIn("future pin", v.reason)

    def test_missing_expected_digest_rejected(self):
        v = self.gate.evaluate(pin(), NOW, None)
        self.assertEqual(v.outcome, MALFORMED_REJECTED)
        v2 = self.gate.evaluate(pin(), NOW, "zz" * 32)
        self.assertEqual(v2.outcome, MALFORMED_REJECTED)

    def test_digest_mismatch_rejected(self):
        v = self.gate.evaluate(pin(), NOW + 1.0, OTHER)
        self.assertEqual(v.outcome, DIGEST_MISMATCH_REJECTED)

    def test_unsupported_claim_rejected(self):
        v = self.gate.evaluate(pin(supported=False), NOW + 1.0, DIG)
        self.assertEqual(v.outcome, UNSUPPORTED_CLAIM_REJECTED)

    def test_unsupported_stale_claim_is_unsupported(self):
        # precedence: unsupported beats stale; never relabeled STALE_UNKNOWN
        v = self.gate.evaluate(pin(supported=False), NOW + 10_000.0, DIG)
        self.assertEqual(v.outcome, UNSUPPORTED_CLAIM_REJECTED)

    def test_non_pin_rejected_malformed(self):
        v = self.gate.evaluate({"url": URL}, NOW, DIG)
        self.assertEqual(v.outcome, MALFORMED_REJECTED)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.gate = Gate()
        self.led = TenPassLedger(URL, DIG)

    def _admitted(self, ts=NOW + 1.0):
        return self.gate.evaluate(pin(ts=ts), ts, DIG)

    def test_ten_pass_incomplete_is_honest(self):
        for i in range(1, 10):
            self.led.record_pass(i, self._admitted())
        v = self.led.verdict()
        self.assertEqual(v["outcome"], "IN_PROGRESS_HONEST")
        self.assertEqual(v["passes_recorded"], 9)  # never adopted before pass 10

    def test_ledger_reports_missing_passes(self):
        self.led.record_pass(2, self._admitted())
        self.led.record_pass(7, self._admitted())
        v = self.led.verdict()
        self.assertEqual(v["missing_passes"], [1, 3, 4, 5, 6, 8, 9, 10])

    def test_all_ten_passes(self):
        for i in range(1, 11):
            self.led.record_pass(i, self._admitted())
        self.assertEqual(self.led.verdict()["outcome"], "ALL_TEN_PASSES")

    def test_non_admitted_pass_rejected(self):
        stale = self.gate.evaluate(pin(), NOW + 10_000.0, DIG)  # STALE_UNKNOWN
        with self.assertRaises(PinError):
            self.led.record_pass(1, stale)
        bad = self.gate.evaluate(pin(supported=False), NOW + 1.0, DIG)  # UNSUPPORTED
        with self.assertRaises(PinError):
            self.led.record_pass(1, bad)

    def test_cross_source_pass_rejected(self):
        v = self.gate.evaluate(SourcePin(url="https://other.example/x", retrieved_ts=NOW,
                                         window_s=600.0, content_digest=DIG, claim="c",
                                         claim_kind="leader-attribution", claim_supported=True),
                               NOW + 1.0, DIG)
        self.assertEqual(v.outcome, ADMITTED)
        with self.assertRaises(PinError):
            self.led.record_pass(1, v)  # different source identity
        v2 = self.gate.evaluate(pin(digest=OTHER), NOW + 1.0, OTHER)
        self.assertEqual(v2.outcome, ADMITTED)
        with self.assertRaises(PinError):
            self.led.record_pass(1, v2)  # different content digest

    def test_duplicate_pass_raises(self):
        self.led.record_pass(1, self._admitted())
        with self.assertRaises(PinError):
            self.led.record_pass(1, self._admitted())

    def test_pass_out_of_range_raises(self):
        with self.assertRaises(PinError):
            self.led.record_pass(0, self._admitted())
        with self.assertRaises(PinError):
            self.led.record_pass(11, self._admitted())

    def test_not_a_verdict_rejected(self):
        with self.assertRaises(PinError):
            self.led.record_pass(1, {"outcome": ADMITTED})


if __name__ == "__main__":
    unittest.main()
