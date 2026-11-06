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

    def test_request_seal_without_passed_candidate_stops(self):
        decision = f0_agent.Decision(action='request_seal', rationale='E4 研发已通过，应由 F5 封存')
        with patch.object(f0_agent, 'get_conn') as gc:
            gc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            result = f0_agent.execute(1, 2, 'run', TOPIC, decision, 1)
        self.assertEqual(result['status'], 'stopped')
        self.assertIn('没有研发达标', result['reason'])


class SealActionTest(unittest.TestCase):
    def test_f0_requests_seal_and_submits_review_after_pass(self):
        cand = {'id': 'c', 'status': 'development_passed', 'snapshot': {'plan': {'researchPurpose': 'replication'}}}
        with patch.object(f0_agent, 'get_conn') as gc, \
             patch.object(f0_agent.sealed, 'request', return_value={'id': 's'}) as req, \
             patch.object(f0_agent.sealed, 'detail', return_value={'status': 'passed'}), \
             patch.object(f0_agent.review, 'request_review') as rev:
            gc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = cand
            result = f0_agent.execute(1, 2, 'run', TOPIC, f0_agent.Decision(action='request_seal', rationale='E4 研发通过，申请封存'), 1)
        req.assert_called_once_with(1, 2, 'c')
        rev.assert_called_once()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['sealed_status'], 'passed')


class EngineTest(unittest.TestCase):
    def test_before_step_pause_and_max_steps(self):
        from services.quant_factor import decision_engine
        calls = []
        def decide(step):
            calls.append(step)
            return f0_agent.Decision(action='run_test', rationale='E1 未达标，继续检验实现'), {}
        def execute(decision, step):
            return {'status': 'completed'}
        steps, reason = decision_engine.run_steps(decide=decide, execute=execute, max_steps=5,
                                                  before_step=lambda step: '课题已暂停' if step == 2 else '')
        self.assertEqual(len(steps), 1)
        self.assertIn('暂停', reason)


class CapabilityFallbackTest(unittest.TestCase):
    def test_detects_capability_message(self):
        from services.quant_factor import f0_agent
        msg = ("F3 未生成通过校验的实现：代码未通过平台校验：需求暂不支持："
               "improvementScope 要求对因子值做 1%/99% 分位 winsorize、按行业分组、剔除成交额最低 5% 及停牌样本")
        self.assertTrue(f0_agent._capability_failure(msg))
        self.assertEqual(set(f0_agent._capability_gaps(msg)),
                         {"winsorize", "行业分组", "成交额分位过滤", "停牌剔除"})

    def test_generic_validation_failure_is_not_capability(self):
        from services.quant_factor import f0_agent
        self.assertFalse(f0_agent._capability_failure("F3 未生成通过校验的实现：语法错误"))

    def test_revise_falls_back_instead_of_stopping(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from services.quant_factor import f0_agent
        decision = SimpleNamespace(action="revise", branch_id="b1", change_scope="winsorize",
                                   stop_reason="", next_hypothesis="h")
        msg = "F3 未生成通过校验的实现：需求暂不支持：分位 winsorize"
        calls = []
        def fake_revise(*args, **kwargs):
            calls.append(kwargs.get("scope_override"))
            if kwargs.get("scope_override") is None:
                raise f0_agent.service.WorkflowError(msg)
            return {"branch_id": "b2", "candidate_status": "development_passed"}
        with patch.object(f0_agent, "_context", return_value={"remaining": 5}), \
             patch.object(f0_agent, "_revise", side_effect=fake_revise):
            out = f0_agent.execute(1, 2, "r1", {"project_id": "p1", "id": "t1"}, decision, 1)
        self.assertEqual(out["status"], "completed")
        self.assertTrue(out["fallback"])
        self.assertIn("winsorize", out["needed_capabilities"])
        self.assertEqual(len(calls), 2)


class EchoedContextTest(unittest.TestCase):
    def _decide(self, payload):
        with patch.object(f0_agent, '_context', return_value={'branches': [], 'remaining': 2}), \
             patch.object(f0_agent, 'get_task'), patch.object(f0_agent, 'assert_quota_available'), \
             patch.object(f0_agent, 'record_usage'), \
             patch.object(f0_agent, 'run_task', return_value={'content': json.dumps(payload)}):
            return f0_agent.decide(1, 2, TOPIC, 'run')

    def test_echoed_readonly_context_is_stripped(self):
        decision, _ = self._decide({'action': 'run_test', 'rationale': 'K=0 首次检验，t*=1.96',
                                    't_critical': 2.2414, 'threshold': 2.2414, 'k': 0})
        self.assertEqual(decision.action, 'run_test')

    def test_unknown_field_still_rejected(self):
        with self.assertRaisesRegex(WorkflowError, '无法解析'):
            self._decide({'action': 'run_test', 'rationale': 'K=0 首次检验，t*=1.96', 'surprise': 1})
