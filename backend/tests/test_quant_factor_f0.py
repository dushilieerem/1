import json
import unittest
from unittest.mock import MagicMock, patch

from services.quant_factor import f0, f0_agent
from services.quant_factor.policy import WorkflowError

TOPIC = {'id': 't', 'project_id': 'p', 'view_id': 'v', 'max_trials': 4,
         'primary_holding_period': 1, 'status': 'active'}


def conn(fetchone=None):
    c = MagicMock(); c.execute.return_value = c; c.fetchone.return_value = fetchone
    w = MagicMock(); w.__enter__.return_value = c
    return w, c


class F0StartTest(unittest.TestCase):
    def test_view_drift_stops(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None]
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'new'}), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(out['status'], 'stopped')
        self.assertEqual(rec.call_args.args[6]['reason'], 'locked_view_drift')

    def test_budget_uses_k_not_candidates(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None]
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(f0.ledger, '_trials', return_value=[]), \
             patch.object(f0.ledger, 'current_k', return_value=4), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(rec.call_args.args[6]['reason'], 'budget_exhausted')

    def test_duplicate_key_returns_existing(self):
        w, c = conn(fetchone={'id': 'run1', 'status': 'queued', 'user_id': 1, 'org_id': 2})
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, '_record') as rec:
            out = f0.start(1, 2, 't', 'b', 'same')
        self.assertEqual(out['id'], 'run1')
        rec.assert_not_called()

    def test_foreign_branch_rejected(self):
        w, c = conn(fetchone=None)
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w):
            with self.assertRaises(KeyError):
                f0.start(1, 2, 't', 'foreign', 'k1')

    def test_paused_topic_stops(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None]
        with patch.object(f0, '_topic', return_value={**TOPIC, 'status': 'paused'}), \
             patch.object(f0, 'get_conn', return_value=w), patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(rec.call_args.args[6]['reason'], 'topic_paused')


class F0RunTest(unittest.TestCase):
    def test_stop_decision_is_persisted(self):
        w, c = conn(fetchone={'id': 'run1', 'status': 'queued', 'user_id': 1, 'org_id': 2,
                              'topic_id': 't', 'project_id': 'p', 'decision': {}})
        decision = f0_agent.Decision(action='stop', rationale='E1 NW t -0.76 未达标，停止', stop_reason='no_improvement')
        with patch.object(f0, 'get_conn', return_value=w), patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0_agent, 'decide', return_value=(decision, {})), \
             patch.object(f0_agent, 'execute', return_value={'status': 'stopped', 'reason': 'no_improvement'}):
            f0.run(1, 2, 'run1')
        stops = [x for x in c.execute.call_args_list if "stop_reason=%s" in x.args[0]]
        self.assertTrue(stops)
        self.assertEqual(stops[-1].args[1][1], 'no_improvement')


class DecisionValidationTest(unittest.TestCase):
    def decide(self, payload):
        with patch.object(f0_agent, '_context', return_value={'branches': [], 'remaining': 2}), \
             patch.object(f0_agent, 'get_task'), patch.object(f0_agent, 'assert_quota_available'), \
             patch.object(f0_agent, 'record_usage'), \
             patch.object(f0_agent, 'run_task', return_value={'content': json.dumps(payload)}):
            return f0_agent.decide(1, 2, TOPIC, 'run')

    def test_unknown_action_rejected(self):
        with self.assertRaisesRegex(WorkflowError, '白名单'):
            self.decide({'action': 'widen_scope', 'rationale': 'E1 未达标所以要扩数据'})

    def test_short_rationale_rejected(self):
        with self.assertRaisesRegex(WorkflowError, '理由'):
            self.decide({'action': 'run_test', 'rationale': 'x'})

    def test_revise_without_hypothesis_rejected(self):
        with self.assertRaisesRegex(WorkflowError, '新假设'):
            self.decide({'action': 'revise', 'rationale': 'E1 NW t -0.76，需修订实现', 'next_hypothesis': ''})

    def test_request_seal_is_not_executed_by_f0(self):
        decision = f0_agent.Decision(action='request_seal', rationale='E4 研发已通过，应由 F5 封存')
        result = f0_agent.execute(1, 2, 'run', TOPIC, decision, 1)
        self.assertEqual(result['status'], 'stopped')
        self.assertIn('F5', result['reason'])
