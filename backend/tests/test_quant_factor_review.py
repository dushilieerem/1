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


class CurrentKReviewTest(unittest.TestCase):
    def row(self):
        return {'id': 'c', 'user_id': 5, 'org_id': 2, 'project_id': 'p', 'snapshot_hash': 'h',
                'archive': {'review': {'status': 'requested', 'assigned_to': 9}, 'approved': False, 'sealed': False},
                'snapshot': {'plan': {'researchPurpose': 'replication'}},
                'evidence': {'development': {'gate': {'checks': [
                    {'name': '方向 NW t', 'actual': 2.0, 'operator': '>=', 'threshold': 2.1, 'passed': False}]}}}}

    def test_record_blocks_when_current_k_raises_bar(self):
        c = MagicMock(); c.execute.return_value.fetchone.return_value = self.row()
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(review, 'get_conn', return_value=conn), \
             patch.object(review, '_ledger_context', return_value={'k': 4, 'threshold': 2.5, 'trials': [], 'topic': {}}):
            with self.assertRaisesRegex(review.WorkflowError, '当前 K'):
                review.record(9, 2, 'c', 'research_supported', 'ok')

    def test_record_allows_when_current_threshold_met(self):
        c = MagicMock(); c.execute.return_value.fetchone.return_value = self.row()
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(review, 'get_conn', return_value=conn), \
             patch.object(review, '_ledger_context', return_value={'k': 4, 'threshold': 1.9, 'trials': [], 'topic': {}}), \
             patch.object(review, 'detail', return_value={'id': 'c'}):
            self.assertEqual(review.record(9, 2, 'c', 'research_supported', 'ok'), {'id': 'c'})


class ReviewIsolationTest(unittest.TestCase):
    def test_detail_hides_research_events(self):
        row = {'id': 'c', 'user_id': 5, 'org_id': 2, 'project_id': 'p', 'snapshot_hash': 'h',
               'archive': {'review': {'status': 'requested'}}, 'events': [{'message': 'chat'}],
               'snapshot': {}, 'evidence': {}}
        c = MagicMock(); c.execute.return_value.fetchone.return_value = row
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(review, 'get_conn', return_value=conn), \
             patch.object(review, '_ledger_context', return_value=None):
            out = review.detail(9, 2, 'c')
        self.assertNotIn('events', out)


class SealFailedReviewReturnTest(unittest.TestCase):
    def test_returns_researcher_view_not_reviewer_detail(self):
        from unittest.mock import MagicMock, patch
        from services.quant_factor import review
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchone.return_value = {"id": "c", "user_id": 1, "org_id": 2, "archive": {},
                                        "snapshot_hash": "h", "status": "development_failed", "events": []}
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(review, "get_conn", return_value=connection), \
             patch.object(review, "detail", side_effect=AssertionError("must not require reviewer")), \
             patch.object(review, "current", return_value={"id": "c"}):
            self.assertEqual(review.open_seal_failed_review(1, 2, "c", "sealed failed"), {"id": "c"})
