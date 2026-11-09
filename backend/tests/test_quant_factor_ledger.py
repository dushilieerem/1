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


class OrgTopicsTest(unittest.TestCase):
    def test_list_org_topics_scopes_by_session_and_returns_k(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import ledger
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchall.return_value = [
            {'id': 't1', 'user_id': 1, 'org_id': 2, 'project_id': 'p', 'primary_holding_period': 1,
             'view_id': 'v', 'branch_count': 1, 'trial_count': 1, 'created_at': None},
        ]
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(ledger, 'get_conn', return_value=connection), patch.object(ledger, '_trials', return_value=[trial(1, 'passed', holding_period=1)]) as trials:
            out = ledger.list_org_topics(1, 2)
        self.assertEqual(out[0]['k'], 1)
        self.assertEqual(out[0]['branch_count'], 1)
        self.assertEqual(cursor.execute.call_args.args[1], (1, 2))
        trials.assert_called_once_with(1, 2, 't1')


class TakeoverTest(unittest.TestCase):
    def test_takeover_requires_explicit_candidate_and_confirmation(self):
        from services.quant_factor import ledger
        with self.assertRaisesRegex(ValueError,'明确确认'):ledger.takeover_branch(1,2,'t','parent')
    def test_takeover_rejects_foreign_parent(self):
        from unittest.mock import MagicMock,patch
        from services.quant_factor import ledger
        cursor=MagicMock();cursor.execute.return_value=cursor;cursor.fetchone.return_value=None
        connection=MagicMock();connection.__enter__.return_value=cursor
        with patch.object(ledger,'_topic',return_value={'id':'t','project_id':'p'}),patch.object(ledger,'get_conn',return_value=connection),patch.object(ledger,'_lock_workbench',return_value={}):
            with self.assertRaises(KeyError):ledger.takeover_branch(1,2,'t','foreign','candidate',True)


class LockedViewTest(unittest.TestCase):
    def test_topic_view_drift_blocks_new_compute(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import service
        cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.fetchone.return_value = {'view_id': 'old'}
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(service, 'get_conn', return_value=connection), \
             patch('services.workflow_workspace.platform_data.published_view', return_value={'view_id': 'new'}):
            msg = service._locked_view_error(1, 2, 'p')
        self.assertIn('旧台账接到新视图', msg)

    def test_same_view_is_allowed(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import service
        cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.fetchone.return_value = {'view_id': 'v'}
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(service, 'get_conn', return_value=connection), \
             patch('services.workflow_workspace.platform_data.published_view', return_value={'view_id': 'v'}):
            self.assertIsNone(service._locked_view_error(1, 2, 'p'))


class TopicPauseTest(unittest.TestCase):
    def test_archived_topic_cannot_resume(self):
        from unittest.mock import patch
        from services.quant_factor import ledger
        with patch.object(ledger, '_topic', return_value={'id': 't', 'status': 'archived'}):
            with self.assertRaisesRegex(ValueError, '归档'):
                ledger.set_topic_status(1, 2, 't', 'active')


class TrialInsertShapeTest(unittest.TestCase):
    """Regression: the f0_run_id column once had a value but no placeholder.

    A mismatch only surfaces on a real INSERT, so guard the SQL shape statically.
    """

    def test_every_trial_column_has_a_placeholder(self):
        import inspect
        import re
        from services.quant_factor import ledger
        source = inspect.getsource(ledger.append_trial)
        match = re.search(
            r"INSERT INTO quant_factor_trials\s*\((.*?)\)\s*VALUES\s*\((.*?)\)", source, re.S)
        self.assertIsNotNone(match)
        columns = [c.strip() for c in match.group(1).split(',') if c.strip()]
        placeholders = re.findall(r"%s", match.group(2))
        self.assertEqual(len(columns), len(placeholders),
                         f"{len(columns)} columns but {len(placeholders)} placeholders")


class TerminalCandidateBackfillTest(unittest.TestCase):
    """A reused terminal candidate must not hide a completed test from K."""

    def _row(self):
        return {
            'id': 'c1', 'status': 'development_failed', 'project_id': 'p1',
            'snapshot': {'request': {'factor_name': 'f'}},
            'evidence': {'development': {
                'request': {'universe': 'CSI500'},
                'result': {'metrics': {'rank_ic_mean': 0.01}},
                'gate': {'passed': False, 'checks': []},
                'report_id': 'qf_c1_development'}},
        }

    def test_existing_trial_skips_backfill(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import service
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchone.return_value = {'id': 't1'}
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(service.store, 'read', return_value=self._row()), \
             patch.object(service, 'get_conn', return_value=connection), \
             patch.object(service, '_append_development_trial') as append:
            self.assertIsNone(service._ensure_development_trial(1, 2, 'c1'))
        append.assert_not_called()

    def test_missing_trial_backfills_failed_outcome(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import service
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchone.return_value = None
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(service.store, 'read', return_value=self._row()), \
             patch.object(service, 'get_conn', return_value=connection), \
             patch.object(service, '_append_development_trial', return_value={'id': 't'}) as append:
            self.assertEqual(service._ensure_development_trial(1, 2, 'c1', 'agent', 'r1'), {'id': 't'})
        args = append.call_args.args
        self.assertEqual(args[6], 'failed')
        self.assertEqual(args[7], 'qf_c1_development')
        self.assertEqual(args[9], 'r1')


class TerminalBackfillScanTest(unittest.TestCase):
    def test_scans_only_terminal_candidates_and_reports_added(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import service
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchall.return_value = [{'id': 'c1'}, {'id': 'c2'}]
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(service, 'get_conn', return_value=connection), \
             patch.object(service, '_ensure_development_trial', side_effect=[{'id': 't1'}, None]) as ensure:
            added = service.backfill_terminal_trials(1, 2, 'p1', 'agent', 'r1')
        self.assertEqual([x['id'] for x in added], ['t1'])
        self.assertEqual(ensure.call_count, 2)
        sql = cursor.execute.call_args.args[0]
        self.assertIn('development_failed', sql)
        self.assertIn('development_passed', sql)


class BranchLabelTest(unittest.TestCase):
    def branches(self):
        return [
            {"id": "r", "parent_id": None, "source": "manual", "hypothesis_version": 1, "created_at": "2026-01-01"},
            {"id": "a1", "parent_id": "r", "source": "agent", "hypothesis_version": 2, "created_at": "2026-01-02"},
            {"id": "a2", "parent_id": "a1", "source": "agent", "hypothesis_version": 3, "created_at": "2026-01-03"},
            {"id": "m1", "parent_id": "a1", "source": "manual", "hypothesis_version": 3, "created_at": "2026-01-04"},
            {"id": "a2b", "parent_id": "a1", "source": "agent", "hypothesis_version": 3, "created_at": "2026-01-05"},
        ]

    def test_revision_and_parallel_labels(self):
        from services.quant_factor import ledger
        labels = ledger._branch_labels(1, 2, "t", self.branches())
        self.assertEqual(labels["r"], "H1")
        self.assertEqual(labels["a1"], "H2")
        self.assertEqual(labels["a2"], "H3")
        self.assertEqual(labels["m1"], "H2a")
        self.assertEqual(labels["a2b"], "H4")

    def test_existing_labels_stable_when_sibling_added(self):
        from services.quant_factor import ledger
        before = ledger._branch_labels(1, 2, "t", self.branches())
        extra = {"id": "m2", "parent_id": "a1", "source": "manual", "hypothesis_version": 3, "created_at": "2026-01-06"}
        after = ledger._branch_labels(1, 2, "t", self.branches() + [extra])
        for key in ("r", "a1", "a2", "m1", "a2b"):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after["m2"], "H2b")


def test_short_title_strips_reasoning_and_limits_length():
    from services.quant_factor import ledger

    assert ledger._short_title("单日信号噪声偏高；改为 5 日反转") == "单日信号噪声偏高"
    assert ledger._short_title("  ") == ""
    long = ledger._short_title("反转" * 20)
    assert len(long) <= 23 and long.endswith("…")
