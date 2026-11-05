"""V5 P0 ledger counting rules: K, rerun, sealed budget and holding period."""
import unittest

from services.quant_factor.ledger import (
    can_request_sealed,
    counts_toward_k,
    current_k,
    k_summary,
    next_k,
    next_trial_no,
    sealed_request_error,
)
from services.quant_factor.metrics import threshold


def trial(no, outcome="passed", **kwargs):
    return {"trial_no": no, "outcome": outcome, **kwargs}


class CountsTowardKTest(unittest.TestCase):
    def test_passed_and_failed_development_tests_count(self):
        self.assertTrue(counts_toward_k(trial(1, "passed")))
        self.assertTrue(counts_toward_k(trial(2, "failed")))
        self.assertTrue(counts_toward_k(trial(3, "passed", executor="human")))
        self.assertTrue(counts_toward_k(trial(4, "passed", executor="agent")))

    def test_deterministic_rerun_does_not_count(self):
        self.assertFalse(counts_toward_k(trial(1, "passed", rerun_of="t0")))
        self.assertFalse(counts_toward_k(trial(2, "rerun")))
        self.assertFalse(counts_toward_k(trial(3, "passed", kind="rerun")))

    def test_error_or_cancelled_counts_only_if_metrics_were_seen(self):
        self.assertFalse(counts_toward_k(trial(1, "error")))
        self.assertFalse(counts_toward_k(trial(2, "cancelled")))
        self.assertFalse(counts_toward_k(trial(3, "error", metrics={})))
        self.assertTrue(counts_toward_k(trial(4, "error", metrics={"rank_ic": 0.01})))
        self.assertTrue(counts_toward_k(trial(5, "cancelled", returned_metrics=True)))
        self.assertTrue(counts_toward_k(
            trial(6, "error", result={"metrics": {"rank_ic": 0.01}})))

    def test_timeout_counts_only_with_partial_metrics(self):
        self.assertFalse(counts_toward_k(trial(1, "timeout")))
        self.assertTrue(counts_toward_k(trial(2, "timeout", returned_metrics=True)))

    def test_static_checks_and_smoke_runs_do_not_count(self):
        for no, kind in enumerate(("static_check", "compile", "smoke", "smoke_test"), 1):
            self.assertFalse(counts_toward_k(trial(no, "passed", kind=kind)))

    def test_sealed_validation_is_recorded_but_never_counts(self):
        for no, kind in enumerate(("sealed", "sealed_validation", "holdout_validation"), 1):
            self.assertFalse(counts_toward_k(trial(no, "passed", kind=kind)))

    def test_only_primary_holding_period_counts(self):
        self.assertTrue(counts_toward_k(trial(1, "passed", holding_period=1), 1))
        self.assertFalse(counts_toward_k(trial(2, "passed", holding_period=5), 1))
        self.assertTrue(counts_toward_k(trial(3, "passed"), 1))  # unknown horizon: do not silently drop

    def test_manual_edit_is_not_a_trial_but_the_next_test_counts(self):
        edits = [trial(1, "passed", kind="research", manual_edit=True),
                 trial(2, "failed", kind="research", manual_edit=True)]
        self.assertEqual(current_k(edits), 2)

    def test_unknown_outcome_is_a_defect(self):
        with self.assertRaisesRegex(ValueError, "outcome"):
            counts_toward_k(trial(1, "maybe"))


class CurrentKTest(unittest.TestCase):
    def test_k_ignores_non_counting_rows(self):
        rows = [trial(1, "passed"), trial(2, "failed"), trial(3, "rerun"),
                trial(4, "passed", kind="sealed_validation"), trial(5, "error")]
        self.assertEqual(current_k(rows), 2)

    def test_duplicate_trial_numbers_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            current_k([trial(1, "passed"), trial(1, "failed")])

    def test_malformed_trial_number_rejected(self):
        for bad in (0, True, 1.5, None):
            with self.assertRaises(ValueError):
                current_k([{"trial_no": bad, "outcome": "passed"}])

    def test_next_trial_no_uses_all_rows_but_next_k_uses_counted(self):
        rows = [trial(1, "passed"), trial(2, "rerun"), trial(3, "failed")]
        self.assertEqual(next_trial_no(rows), 4)
        self.assertEqual(next_k(rows), 3)


class SummaryTest(unittest.TestCase):
    def test_submitted_and_current_k_change_threshold(self):
        rows = [trial(i, "passed") for i in range(1, 13)]
        summary = k_summary(rows, submitted_k=5)
        self.assertEqual(summary["current_k"], 12)
        self.assertTrue(summary["changed"])
        self.assertAlmostEqual(summary["threshold_submitted"], threshold(5), places=12)
        self.assertAlmostEqual(summary["threshold_current"], threshold(12), places=12)
        self.assertLess(summary["threshold_submitted"], summary["threshold_current"])

    def test_unchanged_k(self):
        summary = k_summary([trial(1, "passed")], submitted_k=1)
        self.assertFalse(summary["changed"])
        self.assertEqual(summary["threshold_submitted"], summary["threshold_current"])


class SealedBudgetTest(unittest.TestCase):
    def test_same_candidate_can_only_be_sealed_once(self):
        rows = [trial(1, "passed", kind="sealed_validation", candidate_id="c1")]
        self.assertIn("同一候选", sealed_request_error(rows, "c1"))
        self.assertFalse(can_request_sealed(rows, "c1"))
        self.assertIsNone(sealed_request_error(rows, "c2"))

    def test_topic_limited_to_three_sealed_checks(self):
        rows = [trial(i, "passed", kind="sealed_validation", candidate_id=f"c{i}")
                for i in range(1, 4)]
        self.assertIn("上限 3", sealed_request_error(rows, "c4"))
        self.assertTrue(can_request_sealed(rows[:2], "c4"))

    def test_sealed_rows_do_not_advance_k(self):
        rows = [trial(1, "passed"), trial(2, "passed", kind="sealed_validation", candidate_id="c1")]
        self.assertEqual(current_k(rows), 1)


if __name__ == "__main__":
    unittest.main()
