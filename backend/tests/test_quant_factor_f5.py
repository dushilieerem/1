import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from services.quant_factor import f5
from services.quant_factor.policy import WorkflowError

ROW = {'id': 'c', 'user_id': 5, 'org_id': 2, 'project_id': 'p', 'status': 'validation_passed',
       'snapshot_hash': 'h', 'archive': {'review': {'status': 'requested','assigned_to':9}}, 'events': [{'x': 1}],
       'snapshot': {'plan': {'researchPurpose': 'replication'}},
       'evidence': {'development': {'gate': {'passed': True}, 'report_id': 'r'}}}


class F5Test(unittest.TestCase):
    def test_self_review_rejected(self):
        row = {**ROW, 'user_id': 9}
        c = MagicMock(); c.execute.return_value.fetchone.return_value = row
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(f5, 'get_conn', return_value=conn):
            with self.assertRaisesRegex(WorkflowError, '自己'):
                f5.opinion(9, 2, 'c')

    def test_context_has_no_research_events(self):
        with patch.object(f5.review,'_ledger_context',return_value=None),patch.object(f5,'_sealed',return_value=None):
            ctx = f5._frozen_context(1, 2, ROW)
        self.assertNotIn('events', ctx)
        self.assertEqual(ctx['novelty_evidence'],'尚无完整对照证据')

    def test_invalid_verdict_rejected(self):
        c = MagicMock(); c.execute.return_value.fetchone.return_value = {**ROW, 'user_id': 5}
        conn = MagicMock(); conn.__enter__.return_value = c
        out = {'content': json.dumps({'verdict': 'approve', 'rationale': 'E1 NW t 达标，同意入库'})}
        with patch.object(f5, 'get_conn', return_value=conn), \
             patch.object(f5, '_frozen_context', return_value={}), \
             patch.object(f5, 'ensure_reviewer' if False else 'review') as rev:
            rev.ensure_reviewer.return_value = None
            with patch.object(f5, 'get_task'), patch.object(f5, 'assert_quota_available'), \
                 patch.object(f5, 'record_usage'), patch('services.quant_factor.model_budget.run', return_value=out):
                with self.assertRaisesRegex(WorkflowError, '结论不在允许范围'):
                    f5.opinion(9, 2, 'c')


class F5DateSerializationTest(unittest.TestCase):
    def test_date_in_frozen_snapshot_serializes(self):
        row = {**ROW, 'user_id': 5, 'snapshot': {'plan': {'researchPurpose': 'replication'},
                                                 'as_of': date(2026, 1, 1)}}
        c = MagicMock(); c.execute.return_value.fetchone.return_value = row
        conn = MagicMock(); conn.__enter__.return_value = c
        seen = {}
        out = {'content': json.dumps({'verdict': 'reject', 'rationale': '封存失败，不能入库',
                                      'limitations': ['R4 未接入']})}
        def run_task(*args,messages,**kwargs):
            seen['messages'] = messages
            return out
        with patch.object(f5, 'get_conn', return_value=conn), \
             patch.object(f5.review,'_ledger_context',return_value=None),patch.object(f5,'_sealed',return_value=None), \
             patch.object(f5, 'get_task'), patch.object(f5, 'assert_quota_available'), \
             patch.object(f5, 'record_usage'), patch('services.quant_factor.model_budget.run', side_effect=run_task):
            result = f5.opinion(9, 2, 'c')
        self.assertEqual(result['verdict'], 'reject')
        self.assertIn('2026-01-01', seen['messages'][1]['content'])
