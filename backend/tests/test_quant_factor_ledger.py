"""V5 P0 ledger counting rules: K, rerun, sealed budget and holding period."""
import unittest

from services.quant_factor.ledger import (
    can_request_sealed,
    counts_toward_k,
    current_k,
    is_deterministic_rerun,
    k_after_append,
    k_summary,
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

    def test_missing_holding_period_fails_closed_when_topic_has_primary(self):
        with self.assertRaisesRegex(ValueError, "缺少持有期"):
            counts_toward_k(trial(1, "passed"), 1)
        # Without a registered primary horizon the call is not making that claim.
        self.assertTrue(counts_toward_k(trial(2, "passed")))

    def test_manual_edit_event_is_not_a_trial_but_the_next_test_counts(self):
        rows = [trial(1, "passed", kind="manual_edit"),
                trial(2, "failed", kind="manual_edit"),
                trial(3, "passed", kind="research")]
        self.assertEqual(current_k(rows), 1)

    def test_unknown_outcome_is_a_defect(self):
        with self.assertRaisesRegex(ValueError, "outcome"):
            counts_toward_k(trial(1, "maybe"))


class DeterministicRerunTest(unittest.TestCase):
    def identity(self, **kwargs):
        base = {"implementation_hash": "h1", "data_release_id": "r1",
                "view_id": "v1", "parameters": {"window": 5, "direction": "positive"}}
        return {**base, **kwargs}

    def test_same_identity_is_server_derived_rerun(self):
        self.assertTrue(is_deterministic_rerun(self.identity(), self.identity()))

    def test_any_changed_identity_is_not_a_rerun(self):
        self.assertFalse(is_deterministic_rerun(self.identity(), self.identity(implementation_hash="h2")))
        self.assertFalse(is_deterministic_rerun(self.identity(), self.identity(data_release_id="r2")))
        self.assertFalse(is_deterministic_rerun(self.identity(), self.identity(view_id="v2")))
        self.assertFalse(is_deterministic_rerun(self.identity(), self.identity(parameters={"window": 10})))

    def test_missing_identity_fails_closed(self):
        for key in ("implementation_hash", "data_release_id", "parameters"):
            self.assertFalse(is_deterministic_rerun(self.identity(), self.identity(**{key: None})))
            self.assertFalse(is_deterministic_rerun(self.identity(**{key: None}), self.identity()))


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

    def test_next_trial_no_uses_all_rows_and_k_after_append_respects_kind(self):
        rows = [trial(1, "passed"), trial(2, "rerun"), trial(3, "failed")]
        self.assertEqual(next_trial_no(rows), 4)
        self.assertEqual(k_after_append(rows, trial(4, "passed")), 3)
        self.assertEqual(k_after_append(rows, trial(4, "rerun")), 2)
        self.assertEqual(k_after_append(rows, trial(4, "passed", kind="sealed_validation")), 2)


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

    def test_pre_submission_zero_is_not_a_valid_submitted_k(self):
        for value in (0, None, True):
            with self.assertRaises(ValueError):
                k_summary([trial(1, "passed")], submitted_k=value)


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


class ServerDerivedTrialFieldsTest(unittest.TestCase):
    def call(self, payload):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import ledger
        topic = {'id': 't', 'project_id': 'p', 'view_id': 'v', 'release_id': '',
                 'release_ids': {}, 'view_manifest_sha256': '', 'contract_revision': '',
                 'as_of': None, 'primary_holding_period': 1}
        cursor = MagicMock(); cursor.execute.return_value.fetchone.return_value = {'id': 'b'}
        connection = MagicMock(); connection.__enter__.return_value = cursor
        base = {'branch_id': 'b', 'implementation_hash': 'h', 'executor': 'human', 'outcome': 'passed'}
        with patch.object(ledger, '_topic', return_value=topic), patch.object(ledger, 'get_conn', return_value=connection):
            ledger.append_trial(1, 2, 't', {**base, **payload})

    def test_rerun_kind_and_outcome_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'kind'):
            self.call({'kind': 'rerun'})
        with self.assertRaisesRegex(ValueError, 'outcome'):
            self.call({'outcome': 'rerun'})

    def test_diagnostic_and_sealed_kinds_are_rejected(self):
        for kind in ('static_check', 'compile', 'smoke', 'smoke_test', 'sealed_validation'):
            with self.assertRaisesRegex(ValueError, 'kind'):
                self.call({'kind': kind})
