import unittest
from unittest.mock import MagicMock, patch

from services.quant_factor import f0

TOPIC = {'id': 't', 'project_id': 'p', 'view_id': 'v', 'max_trials': 4, 'primary_holding_period': 1, 'status': 'active'}


def conn(fetchone=None):
    c = MagicMock(); c.execute.return_value = c; c.fetchone.return_value = fetchone
    w = MagicMock(); w.__enter__.return_value = c
    return w, c


class F0StartTest(unittest.TestCase):
    def test_view_drift_stops_before_writing_compute(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None]
        with patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'new'}), \
             patch.object(f0, '_record', return_value={'status': 'stopped', 'stop_reason': 'view'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(out['status'], 'stopped')
        self.assertEqual(rec.call_args.args[5], 'stopped')

    def test_budget_exhausted_stops(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None, {'n': 4}]
        with patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(out['status'], 'stopped')
        self.assertIn('预算', rec.call_args.args[7])

    def test_duplicate_key_returns_existing_without_new_record(self):
        w, c = conn(fetchone={'id': 'run1', 'status': 'queued', 'user_id': 1, 'org_id': 2, 'decision': {'action': 'run_development_test'}})
        with patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, '_record') as rec:
            out = f0.start(1, 2, 't', 'b', 'same')
        self.assertEqual(out['id'], 'run1')
        rec.assert_not_called()

    def test_foreign_branch_is_rejected(self):
        w, c = conn(fetchone=None)
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w):
            with self.assertRaises(KeyError):
                f0.start(1, 2, 't', 'foreign', 'k1')


class F0RunTest(unittest.TestCase):
    def test_one_authorised_test_executes_and_completes(self):
        w, c = conn(fetchone={'id': 'run1', 'project_id': 'p', 'status': 'queued',
                              'user_id': 1, 'org_id': 2, 'decision': {'action': 'run_development_test'}})
        candidate = {'id': 'c1', 'status': 'development_passed'}
        with patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'service') as svc:
            svc.create.return_value = candidate
            svc.current.return_value = candidate
            f0.run(1, 2, 'run1')
        svc.create.assert_called_once_with(1, 2, 'p')
        updates = [x for x in c.execute.call_args_list if "status='completed'" in x.args[0]]
        self.assertTrue(updates)


class F0DecisionTest(unittest.TestCase):
    def test_failed_trial_derives_branch_without_rerun(self):
        w, c = conn(); c.fetchone.side_effect = [
            {'id': 'b', 'source': 'manual'}, None, {'n': 0}, None]
        latest = {'trial_no': 1, 'outcome': 'failed'}
        with patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(f0.ledger, '_trials', return_value=[latest]), \
             patch.object(f0.POOL, 'submit'), \
             patch.object(f0, '_record', return_value={'id': 'run', 'status': 'queued'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k')
        decision = rec.call_args.args[6]
        self.assertEqual(decision['action'], 'derive_branch')
        self.assertEqual(decision['from_trial'], 1)

    def test_passed_trial_stops_for_human(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None, {'n': 0}]
        with patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(f0.ledger, '_trials', return_value=[{'trial_no': 1, 'outcome': 'passed'}]), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k')
        self.assertEqual(out['status'], 'stopped')
        self.assertEqual(rec.call_args.args[6]['reason'], 'development_passed')


class F0PauseTest(unittest.TestCase):
    def test_paused_topic_stops_without_scheduling(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None]
        topic = {**TOPIC, 'status': 'paused'}
        with patch.object(f0, '_topic', return_value=topic), \
             patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k')
        self.assertEqual(out['status'], 'stopped')
        self.assertEqual(rec.call_args.args[6]['reason'], 'topic_paused')
