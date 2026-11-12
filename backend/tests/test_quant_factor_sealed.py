import unittest
from unittest.mock import MagicMock, patch

from services.quant_factor import sealed
from services.quant_factor.policy import WorkflowError

ROW = {'id': 's1', 'candidate_id': 'c1', 'user_id': 1, 'org_id': 2, 'status': 'passed',
       'result': {'gate': {'passed': True}}, 'trial_ids': ['t1']}


class SealedTest(unittest.TestCase):
    def test_request_requires_development_passed(self):
        with patch.object(sealed, '_candidate', return_value={'status': 'development_failed'}):
            with self.assertRaisesRegex(WorkflowError, '研发检验通过'):
                sealed.request(1, 2, 'c')

    def test_detail_masks_full_result_from_researcher(self):
        cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.fetchone.return_value = ROW
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(sealed, 'get_conn', return_value=connection):
            masked = sealed.detail(1, 2, 'c1', False)
            full = sealed.detail(1, 2, 'c1', True)
        self.assertNotIn('result', masked)
        self.assertEqual(full['result'], {'gate': {'passed': True}})

    def test_detail_is_org_scoped_not_caller_scoped(self):
        cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.fetchone.return_value = ROW
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(sealed, 'get_conn', return_value=connection):
            sealed.detail(99, 2, 'c1', True)
        self.assertEqual(cursor.execute.call_args.args[1], ('c1', 2))


class SealedRunTest(unittest.TestCase):
    def test_success_path_stores_passed_with_f5_executor(self):
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchone.return_value = {'id': 's1', 'candidate_id': 'c1', 'topic_id': 't1',
                                        'status': 'queued', 'user_id': 1, 'org_id': 2}
        connection = MagicMock(); connection.__enter__.return_value = cursor
        cand = {'snapshot': {'plan': {'validationStart': '2025-01-01', 'validationEnd': '2025-12-31'},
                             'request': {'factor_name': 'f'}, 'rules': {}}}
        topic = {'id': 't1', 'primary_holding_period': 1}
        with patch.object(sealed, 'get_conn', return_value=connection), \
             patch.object(sealed, '_candidate', return_value=cand), \
             patch.object(sealed, '_topic', return_value=topic), \
             patch.object(sealed, 'proxy_submit_factor_backtest', return_value=(202, {}, {'run_id': 'r1'})), \
             patch.object(sealed, 'proxy_get_factor_run', return_value=(200, {}, {'status': 'succeeded', 'result': {'meta': {}}})), \
             patch.object(sealed.ledger, '_trials', return_value=[]), \
             patch.object(sealed.ledger, 'current_k', return_value=1), \
             patch.object(sealed, 'evaluate', return_value={'passed': True, 'checks': []}):
            sealed.run(1, 2, 's1')
        updates = [call for call in cursor.execute.call_args_list if "SET status=%s,result" in call.args[0]]
        self.assertEqual(updates[-1].args[1][0], 'passed')
        self.assertEqual(updates[-1].args[1][-1], 's1')
