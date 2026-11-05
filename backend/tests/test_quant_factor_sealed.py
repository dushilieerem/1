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
