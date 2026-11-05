import unittest
from unittest.mock import MagicMock, patch

from services.quant_factor import review


class ReviewQueueTest(unittest.TestCase):
    def test_queue_is_org_scoped_and_only_requested(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchall.return_value = []
        connection = MagicMock()
        connection.__enter__.return_value = cursor
        with patch.object(review, 'get_conn', return_value=connection):
            self.assertEqual(review.queue(11, 22), [])
        sql, params = cursor.execute.call_args.args
        self.assertIn("org_id=%s", sql)
        self.assertIn("user_id<>%s", sql)
        self.assertIn("'requested'", sql)
        self.assertEqual(params, (22, 11))

    def test_claim_rejects_another_reviewer(self):
        from services.quant_factor.policy import WorkflowError
        row = {'user_id': 99, 'archive': {'review': {'status': 'requested', 'assigned_to': 77}}}
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = row
        connection = MagicMock()
        connection.__enter__.return_value = cursor
        with patch.object(review, 'get_conn', return_value=connection):
            with self.assertRaisesRegex(WorkflowError, '其他复核人'):
                review.claim(11, 22, 'c')


if __name__ == '__main__':
    unittest.main()
