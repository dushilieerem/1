"""Provider-default request contract and actual ledger transactions; transport is a fixture."""
import io,json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from ai.router.specs import TaskSpec
from ai.gateway import providers
from services.quant_factor import model_budget as b,research_method as method
from services.quant_factor.policy import WorkflowError
from tests.test_quant_unlimited_tokens_pg import IsolatedUnlimitedTests

class IsolatedCapacityTests(IsolatedUnlimitedTests):
 def transport(self,raw=None,error=None):
  stack=ExitStack();target=SimpleNamespace(model='fixture-primary',provider='fixture',base_url='http://fixture.invalid',timeout=150)
  stack.enter_context(patch.object(providers,'resolve_target',return_value=target))
  stack.enter_context(patch('ai.router.get_task',side_effect=lambda task:TaskSpec(task_id=task,prompt_version=method.snapshot()['roles'][task]['prompt_version'],max_tokens=None,timeout_sec=900)))
  post=stack.enter_context(patch.object(providers,'_post',side_effect=error if error else lambda *a,**k:io.BytesIO(json.dumps(raw).encode())));stack.enter_context(patch.object(providers,'complete',side_effect=AssertionError('hidden gateway loops forbidden')))
  return stack,post
 def execute(self,key,role=method.PLANNER):return b.run(self.uid,self.org,'project',key,role,messages=[{'role':'user','content':'fixture'}],method_snapshot=method.snapshot())
 def test_all_three_roles_omit_product_cap_and_freeze_actual_parameters_and_provider_total(self):
  self.install();raw={'choices':[{'message':{'content':'fixture'},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':20000,'total_tokens':20100,'completion_tokens_details':{'reasoning_tokens':18000}}}
  stack,post=self.transport(raw)
  with stack:
   for role in (method.PLANNER,method.IMPLEMENTER,method.DIAGNOSER):
    out=self.execute(role,role);self.assertEqual(out['usage'],raw['usage']);self.assertNotIn('max_tokens',post.call_args.args[1]);self.assertEqual(post.call_args.kwargs['timeout'],900)
  self.assertEqual(post.call_count,3)
  with self.connection() as c:
   rows=c.execute('SELECT max_output_tokens,reservation_complete,actual_tokens,request_parameters FROM quant_ai_budget_calls').fetchall();self.assertEqual(len(rows),3)
   for row in rows:
    self.assertIsNone(row['max_output_tokens']);self.assertFalse(row['reservation_complete']);self.assertEqual(row['actual_tokens'],20100);self.assertNotIn('max_tokens',row['request_parameters']);self.assertEqual(row['request_parameters']['output_policy'],'provider_default');self.assertEqual(row['request_parameters']['method_snapshot_hash'],method.snapshot()['snapshot_hash'])
 def test_timeout_preserves_unknown_output_capacity_and_never_reissues_same_call(self):
  self.install();stack,post=self.transport(error=TimeoutError('fixture receipt unknown'))
  with stack:
   with self.assertRaisesRegex(WorkflowError,'TimeoutError'):self.execute('timeout')
   with self.assertRaisesRegex(WorkflowError,'尚待核对'):self.execute('timeout')
  post.assert_called_once();status=b.status(self.uid,self.org);self.assertIsNone(status['usage']['held_tokens']);self.assertEqual(status['usage']['held_output_capacity_unknown_calls'],1);self.assertGreater(status['usage']['held_known_input_bound_tokens'],0)
 def test_known_length_receipt_is_metered_once_not_a_market_trial(self):
  self.install();raw={'choices':[{'message':{'content':'','reasoning_content':'fixture reasoning'},'finish_reason':'length'}],'usage':{'prompt_tokens':100,'completion_tokens':32768,'total_tokens':32868,'completion_tokens_details':{'reasoning_tokens':32768}}}
  stack,post=self.transport(raw)
  with stack:
   with self.assertRaisesRegex(WorkflowError,'AiOutputTruncated'):self.execute('known-length')
   with self.assertRaisesRegex(WorkflowError,'原模型调用未返回'):self.execute('known-length')
  post.assert_called_once()
  with self.connection() as c:
   row=c.execute('SELECT status,actual_tokens,response FROM quant_ai_budget_calls').fetchone();self.assertEqual(row['status'],'settled');self.assertEqual(row['actual_tokens'],32868);self.assertEqual(row['response']['finish_reason'],'length');self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_trials').fetchone()['n'],1)
 def test_received_response_without_usage_remains_unknown_charge_not_zero(self):
  self.install();raw={'choices':[{'message':{'content':'fixture'},'finish_reason':'stop'}],'usage':{}}
  stack,post=self.transport(raw)
  with stack:self.execute('missing-usage')
  with self.connection() as c:
   row=c.execute('SELECT status,actual_tokens,response FROM quant_ai_budget_calls').fetchone();self.assertEqual(row['status'],'unresolved');self.assertIsNone(row['actual_tokens']);self.assertIsNotNone(row['response'])
  status=b.status(self.uid,self.org);self.assertIsNone(status['usage']['held_tokens'])
 def test_no_unlimited_authorization_cannot_send_uncapped_role_request(self):
  raw={'choices':[{'message':{'content':'fixture'},'finish_reason':'stop'}],'usage':{}};stack,post=self.transport(raw)
  with stack,self.assertRaisesRegex(WorkflowError,'持续研究授权'):self.execute('not-authorized')
  post.assert_not_called()
 def test_large_received_artifact_retains_real_usage_and_known_technical_failure(self):
  self.install();raw={'choices':[{'message':{'content':'x'*110000},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':49900,'total_tokens':50000}}
  stack,post=self.transport(raw)
  with stack,self.assertRaisesRegex(WorkflowError,'超过本次可保存范围'):self.execute('large-content')
  with self.connection() as c:
   row=c.execute('SELECT status,actual_tokens,response FROM quant_ai_budget_calls').fetchone();self.assertEqual(row['status'],'settled');self.assertEqual(row['actual_tokens'],50000);self.assertEqual(row['response']['error_type'],'AiOutputStorageLimit');self.assertNotIn('content',row['response']);self.assertEqual(row['response']['content_chars'],110000)
