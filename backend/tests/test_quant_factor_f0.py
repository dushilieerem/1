import json
import unittest
from unittest.mock import MagicMock, patch

from services.quant_factor import f0, f0_agent, locked_data
from services.quant_factor.policy import WorkflowError

TOPIC = {'id': 't', 'project_id': 'p', 'view_id': 'v', 'max_trials': 4,
         'primary_holding_period': 1, 'status': 'active'}


def conn(fetchone=None):
    c = MagicMock(); c.execute.return_value = c; c.fetchone.return_value = fetchone
    w = MagicMock(); w.__enter__.return_value = c
    return w, c


class F0StartTest(unittest.TestCase):
    def setUp(self):
        control=patch.object(f0.service, 'control_status', return_value={'paused':False})
        control.start();self.addCleanup(control.stop)

    def test_view_drift_stops(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None, None]
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w), \
             patch('services.factor.detect_store.get_project', return_value={'project': {'id': 'p', 'config': {}}}), \
             patch.object(locked_data, 'for_topic', side_effect=WorkflowError('旧台账接到新视图')), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            out = f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(out['status'], 'stopped')
        self.assertEqual(rec.call_args.args[6]['technical_wait']['kind'], 'fixed_data_or_resources')
        self.assertIn('旧台账接到新视图', rec.call_args.args[7])

    def test_budget_uses_k_not_candidates(self):
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None, None, None, {'n':0}]
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(f0.ledger, '_trials', return_value=[]), \
             patch.object(f0.ledger, 'current_k', return_value=4), \
             patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(rec.call_args.args[6]['reason'], 'budget_exhausted')

    def test_exhausted_development_budget_still_allows_earned_seal(self):
        candidate={'status':'development_passed','snapshot':{'plan':{'researchPurpose':'discovery'}},'evidence':{'development':{'novelty':{'gate':{'complete':True,'passed':True}}}}}
        w,c=conn();c.fetchone.side_effect=[{'id':'b'},None,None,candidate,{'n':0}]
        with patch.object(f0,'_topic',return_value={**TOPIC,'max_sealed':1}),patch.object(f0,'get_conn',return_value=w),patch.object(locked_data,'for_topic',return_value={'view_id':'v'}),patch.object(f0.ledger,'_trials',return_value=[]),patch.object(f0.ledger,'current_k',return_value=4),patch.object(f0,'_record',return_value={'id':'run','status':'queued'}) as record,patch('services.quant_factor.resources.require_config',return_value={'allowed':True}) as development_preflight,patch.object(f0.POOL,'submit') as schedule,patch('services.factor.detect_store.get_project',return_value={'project':{'id':'p','config':{}}}):
            out=f0.start(1,2,'t','b','earned-seal')
        self.assertEqual(out['status'],'queued');development_preflight.assert_called_once();schedule.assert_called_once()

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
        w, c = conn(); c.fetchone.side_effect = [{'id': 'b', 'source': 'manual'}, None, None]
        with patch.object(f0, '_topic', return_value={**TOPIC, 'status': 'paused'}), \
             patch.object(f0, 'get_conn', return_value=w), patch.object(f0, '_record', return_value={'status': 'stopped'}) as rec:
            f0.start(1, 2, 't', 'b', 'k1')
        self.assertEqual(rec.call_args.args[6]['reason'], 'topic_paused')


class F0SingleFlightTest(unittest.TestCase):
    def test_different_key_reuses_inflight_run_without_scheduling(self):
        w, c = conn()
        c.fetchone.side_effect = [{'id': 'b'}, None, {'id': 'running-1', 'status': 'running'}]
        with patch.object(f0, '_topic', return_value=TOPIC), patch.object(f0, 'get_conn', return_value=w), \
             patch.object(f0, '_record') as record, patch.object(f0.POOL, 'submit') as submit:
            result = f0.start(1, 2, 't', 'b', 'another-key')
        self.assertEqual(result['id'], 'running-1')
        self.assertIn('pg_advisory_xact_lock', c.execute.call_args_list[0].args[0])
        record.assert_not_called()
        submit.assert_not_called()


class F0RunTest(unittest.TestCase):
    def test_stop_decision_is_persisted(self):
        w, c = conn(fetchone={'id': 'run1', 'status': 'queued', 'user_id': 1, 'org_id': 2,
                              'topic_id': 't', 'project_id': 'p', 'decision': {}})
        decision = f0_agent.Decision(action='stop', rationale='E1 NW t -0.76 未达标，停止', stop_reason='no_improvement')
        with patch.object(f0, 'get_conn', return_value=w), patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0.service,'recover_pending'),patch.object(f0.service,'backfill_terminal_trials'), \
             patch.object(f0.ledger,'_trials',return_value=[]), \
             patch.object(f0_agent, '_context',return_value={'novelty':{}}), \
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
             patch('services.quant_factor.model_budget.run', return_value={'content': json.dumps(payload)}):
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
        with patch.object(f0_agent, 'get_conn') as gc, patch.object(f0_agent, '_context', return_value={'remaining': 2}):
            gc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            result = f0_agent.execute(1, 2, 'run', TOPIC, decision, 1)
        self.assertEqual(result['status'], 'stopped')
        self.assertIn('没有研发达标', result['reason'])


class SealActionTest(unittest.TestCase):
    def test_f0_requests_seal_and_submits_review_after_pass(self):
        cand = {'id': 'c', 'status': 'development_passed', 'snapshot': {'plan': {'researchPurpose': 'replication'}}}
        with patch.object(f0_agent, 'get_conn') as gc, patch.object(f0_agent, '_context', return_value={'remaining': 2}), \
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
             patch('services.quant_factor.model_budget.run', return_value={'content': json.dumps(payload)}):
            return f0_agent.decide(1, 2, TOPIC, 'run')

    def test_echoed_readonly_context_is_stripped(self):
        decision, _ = self._decide({'action': 'run_test', 'rationale': 'K=0 首次检验，t*=1.96',
                                    't_critical': 2.2414, 'threshold': 2.2414, 'k': 0})
        self.assertEqual(decision.action, 'run_test')

    def test_unknown_field_still_rejected(self):
        with self.assertRaisesRegex(WorkflowError, '无法解析'):
            self._decide({'action': 'run_test', 'rationale': 'K=0 首次检验，t*=1.96', 'surprise': 1})


class F0ConcurrentStartTest(unittest.TestCase):
    def test_two_parallel_http_starts_schedule_only_one_run(self):
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor
        mutex = threading.RLock()
        barrier = threading.Barrier(2)
        runs = []
        class FakeConnection:
            def __init__(self):
                self.locked = 0
                self.row = None
            def __enter__(self): return self
            def __exit__(self, *args):
                for _ in range(self.locked): mutex.release()
            def execute(self, sql, params=()):
                if 'pg_advisory_xact_lock' in sql:
                    mutex.acquire(); self.locked += 1
                elif 'quant_factor_branches' in sql: self.row = {'id': 'b'}
                elif 'idempotency_key=%s' in sql:
                    self.row = next((r for r in runs if r['key'] == params[-1]), None)
                elif "status IN ('queued','running')" in sql: self.row = runs[0] if runs else None
                else: raise AssertionError(sql)
                return self
            def fetchone(self): return self.row
        def record(uid, org, topic, bid, key, status, *args, **kwargs):
            time.sleep(.02)
            row = {'id': 'one-run', 'key': key, 'status': status}
            runs.append(row)
            return row
        def invoke(key):
            barrier.wait(timeout=2)
            return f0.start(1, 2, 't', 'b', key)
        with patch.object(f0, 'get_conn', side_effect=FakeConnection), \
             patch.object(f0, '_topic', return_value=TOPIC), \
             patch.object(f0.service, 'control_status', return_value={'paused': False}), \
             patch.object(f0, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(f0.ledger, '_trials', return_value=[]), \
             patch.object(f0.ledger, 'current_k', return_value=0), \
             patch.object(f0, '_record', side_effect=record), \
             patch.object(locked_data, 'for_topic', return_value={'view_id': 'v'}), \
             patch('services.factor.detect_store.get_project',return_value={'project':{'config':{}}}), \
             patch('services.quant_factor.resources.require_config',return_value={'allowed':True}), \
             patch.object(f0.POOL, 'submit') as submit:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(invoke, ['key-a', 'key-b']))
        self.assertEqual(len(runs), 1)
        self.assertEqual([r['id'] for r in results], ['one-run', 'one-run'])
        submit.assert_called_once()


class F0ResumeConsistencyTest(unittest.TestCase):
    def test_queued_resume_reuses_identity_without_new_worker(self):
        row={'id':'r','topic_id':'t','status':'queued'}
        w,c=conn(fetchone=row)
        with patch.object(f0,'read',return_value=row),patch.object(f0,'get_conn',return_value=w),patch.object(f0.POOL,'submit') as submit:
            self.assertEqual(f0.resume(1,2,'r')['id'],'r')
        submit.assert_not_called()
        self.assertEqual(c.execute.call_args_list[0].args[1],(9106,1))
        self.assertEqual(c.execute.call_args_list[1].args[1],('quant-factor-start:1:2:t',))

    def test_other_active_run_is_reused_instead_of_resuming_old_run(self):
        old={'id':'old','topic_id':'t','status':'failed'}
        w,c=conn();c.fetchone.side_effect=[old,{'id':'active','topic_id':'t','status':'running'}]
        with patch.object(f0,'read',return_value=old),patch.object(f0,'get_conn',return_value=w),patch.object(f0.POOL,'submit') as submit:
            self.assertEqual(f0.resume(1,2,'old')['id'],'active')
        submit.assert_not_called()

    def test_running_worker_cannot_be_claimed_twice(self):
        w,c=conn(fetchone={'id':'r','status':'running'})
        with patch.object(f0,'get_conn',return_value=w),patch.object(f0_agent,'decide') as decide:
            f0.run(1,2,'r')
        decide.assert_not_called()
        self.assertIn('FOR UPDATE',c.execute.call_args.args[0])

    def test_engine_resume_preserves_previous_events_and_step_identity(self):
        from services.quant_factor.decision_engine import run_steps
        prior={'step':1,'at':'2026-11-09T00:00:00','decision':{'action':'run_test'},'result':{'status':'completed'}}
        d=f0_agent.Decision(action='stop',rationale='已有试验结果不满足要求，停止研究')
        steps,reason=run_steps(decide=lambda n:(d,{}),execute=lambda d,n:{'status':'stopped','reason':'done'},max_steps=1,initial_steps=[prior])
        self.assertEqual(steps[0],prior);self.assertEqual(steps[1]['step'],2);self.assertEqual(reason,'done')

class LateSealReviewTests(unittest.TestCase):
 def test_waited_seal_evidence_cannot_trigger_review_after_manual_takeover(self):
  cand={'id':'c','status':'development_passed','snapshot':{'plan':{'researchPurpose':'replication'}}}
  with patch.object(f0_agent,'get_conn') as gc,patch.object(f0_agent,'_context',return_value={'remaining':1}),patch.object(f0_agent.sealed,'request',return_value={'id':'s'}),patch.object(f0_agent.sealed,'detail',return_value={'status':'passed'}),patch.object(f0_agent.review,'request_review',side_effect=WorkflowError('人工已暂停并接手')) as review:
   gc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=cand
   out=f0_agent.execute(1,2,'r',TOPIC,f0_agent.Decision(action='request_seal',rationale='研发已通过，申请封存'),1,worker_epoch='original')
  self.assertEqual(out['status'],'stopped');self.assertIn('未继续自动送审',out['reason']);self.assertEqual(review.call_args.kwargs['controller'],{'run_id':'r','worker_epoch':'original'})
