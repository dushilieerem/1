# -*- coding: utf-8 -*-
"""量化长任务 queue 模式：入队、消费、inline 兼容。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.quant_factor import jobs, service


def test_enqueue_run_and_retry_payloads():
    with patch.object(jobs, "enqueue", return_value=7) as enqueue:
        assert jobs.enqueue_run(1, 2, "cid", "development") == 7
        enqueue.assert_called_once_with(
            jobs.RUN_KIND, {"uid": 1, "org": 2, "cid": "cid", "phase": "development"}
        )
        jobs.enqueue_retry(1, 2, "cid")
        enqueue.assert_called_with(jobs.RETRY_KIND, {"uid": 1, "org": 2, "cid": "cid"})


def test_handlers_call_service():
    with patch.object(service, "run") as run:
        jobs._handle_run({"uid": 1, "org": 2, "cid": "c", "phase": "validation"})
        run.assert_called_once_with(1, 2, "c", "validation")
    with patch.object(service, "_retry_novelty") as retry:
        jobs._handle_retry({"uid": 1, "org": 2, "cid": "c"})
        retry.assert_called_once_with(1, 2, "c")


def test_dispatch_queue_mode(monkeypatch):
    monkeypatch.setenv("QUANT_FACTOR_JOB_MODE", "queue")
    with patch.object(jobs, "enqueue_run") as enqueue_run:
        service._dispatch(1, 2, "c", "development")
    enqueue_run.assert_called_once_with(1, 2, "c", "development")


def test_dispatch_inline_mode(monkeypatch):
    monkeypatch.delenv("QUANT_FACTOR_JOB_MODE", raising=False)
    with patch.object(service.POOL, "submit") as submit:
        service._dispatch(1, 2, "c", "development")
    submit.assert_called_once_with(service.run, 1, 2, "c", "development")

def test_dispatch_queue_failure_marks_candidate(monkeypatch):
    monkeypatch.setenv("QUANT_FACTOR_JOB_MODE", "queue")
    with patch.object(jobs, "enqueue_run", side_effect=RuntimeError("db down")), \
         patch.object(service.store, "update") as update:
        try:
            service._dispatch(1, 2, "c", "development")
        except Exception:
            pass
        else:
            raise AssertionError("expected dispatch failure")
    update.assert_called_once()
    assert update.call_args.args[0:4] == (1, 2, "c", "development_error")


class InterruptedCandidateTest(unittest.TestCase):
    def test_restart_without_proven_owner_keeps_legacy_candidate_unchanged(self):
        from unittest.mock import patch
        from services.quant_factor import service
        with patch.object(service, 'get_conn') as connection, patch.object(service.store, 'update') as update:
            marked = service.mark_interrupted_candidates()
        self.assertEqual(marked, 0)
        connection.assert_not_called()
        update.assert_not_called()


class RetryBudgetTest(unittest.TestCase):
    def test_retry_rejects_when_budget_exhausted(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import ledger, service
        from services.quant_factor.policy import WorkflowError
        row = {'id': 'c1', 'user_id': 9, 'org_id': 2, 'project_id': 'p',
               'status': 'development_error', 'evidence': {'development': {'interrupted': True}}}
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.side_effect = [
            row,
            {'id': 't1', 'max_trials': 3, 'primary_holding_period': 1},
            {'n': 0},
        ]
        conn = MagicMock(); conn.__enter__.return_value = cursor
        with patch.object(service.store, 'read', return_value=row), \
             patch.object(service, 'get_conn', return_value=conn), \
             patch.object(ledger, '_trials', return_value=[]), \
             patch.object(ledger, 'current_k', return_value=3), \
             patch.object(service, '_dispatch', return_value=None):
            with self.assertRaisesRegex(WorkflowError, '试验预算'):
                service.retry_development(9, 2, 'c1')
