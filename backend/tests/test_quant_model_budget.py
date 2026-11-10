import unittest
from unittest.mock import patch,MagicMock
from services.quant_factor import model_budget as b
from services.quant_factor.policy import WorkflowError

class BudgetLogicTests(unittest.TestCase):
 def test_utf8_upper_bound_includes_messages_schema_and_framing(self):
  messages=[{'role':'user','content':'量价研究'}]
  self.assertGreater(b.input_upper_bound(messages,{'type':'object'}),len(str(messages).encode())+1024)
 def test_oversized_prompt_rejected_before_reservation(self):
  with self.assertRaisesRegex(WorkflowError,'输入范围'):b.input_upper_bound([{'role':'user','content':'x'*50_000}])
 def test_provider_usage_missing_or_zero_defaults_do_not_become_free(self):
  for value in [{},{'tokens_in':0,'tokens_out':0},{'usage':{}},{'usage':{'prompt_tokens':1}},{'content':'answer','usage':{'prompt_tokens':0,'completion_tokens':0}}]:self.assertIsNone(b.measured_usage(value))
 def test_actual_usage_counts_provider_total_including_extra_accounting(self):
  measured=b.measured_usage({'usage':{'prompt_tokens':30,'completion_tokens':20,'total_tokens':60}})
  self.assertEqual(measured['total_tokens'],60)
 def test_invalid_usage_boolean_negative_float_are_not_trusted(self):
  for value in [True,-1,1.2]:self.assertIsNone(b.measured_usage({'usage':{'prompt_tokens':value,'completion_tokens':1}}))
 def test_pending_history_rejects_before_model_call_and_does_not_infer_zero(self):
  c=MagicMock();c.execute.return_value=c;c.fetchone.side_effect=[None,{'ai_quota_daily':200},{'n':0},None,None];c.fetchall.return_value=[]
  with patch.object(b,'get_conn') as conn:
   conn.return_value.__enter__.return_value=c
   with self.assertRaisesRegex(WorkflowError,'历史模型用量尚待核对'):b.reserve(1,2,'p','call','research.generate_factor','hash',100,8000)
  self.assertFalse(any('INSERT INTO quant_ai_budget_calls' in x.args[0] for x in c.execute.call_args_list))
 def test_reused_call_identity_rejects_other_actor_and_changed_request(self):
  row={'user_id':1,'project_id':'p','request_hash':'original','supplement_id':None}
  c=MagicMock();c.execute.return_value=c;c.fetchone.return_value=row
  with patch.object(b,'get_conn') as conn:
   conn.return_value.__enter__.return_value=c
   with self.assertRaisesRegex(WorkflowError,'另一输入'):b.reserve(1,2,'p','same','research.generate_factor','changed',100,8000)
   with self.assertRaisesRegex(WorkflowError,'另一输入'):b.reserve(9,2,'p','same','research.generate_factor','original',100,8000)
 def test_explicit_f3_cap_is_8000_without_changing_shared_task(self):
  from ai.router.tasks.factor_generation import FACTOR_TASK
  self.assertIsNone(FACTOR_TASK.max_tokens);self.assertEqual(b.OUTPUT_LIMITS['research.generate_factor'],8000)

class OnePhysicalAttemptTests(unittest.TestCase):
 def execute(self,raw=None,error=None):
  import io,json
  from types import SimpleNamespace
  from ai.router.specs import TaskSpec
  from ai.gateway import providers
  from contextlib import ExitStack
  target=SimpleNamespace(model='fixture-primary',provider='fixture',base_url='http://fixture.invalid',timeout=10)
  with ExitStack() as stack:
   stack.enter_context(patch('ai.router.get_task',return_value=TaskSpec(task_id='research.generate_factor',max_tokens=None,response_format={'type':'json_schema'})))
   stack.enter_context(patch.object(providers,'resolve_target',return_value=target))
   stack.enter_context(patch.object(b,'_unlimited_mode',return_value=False));stack.enter_context(patch.object(b,'reserve',return_value={'id':'call','status':'reserved'}));stack.enter_context(patch.object(b,'claim',return_value=True))
   settle=stack.enter_context(patch.object(b,'settle'));unknown=stack.enter_context(patch.object(b,'unresolved'))
   post=stack.enter_context(patch.object(providers,'_post',side_effect=error,return_value=io.BytesIO(json.dumps(raw).encode()) if raw is not None else None))
   complete=stack.enter_context(patch.object(providers,'complete',side_effect=AssertionError('hidden gateway loop forbidden')))
   try:out=b.run(1,2,'p','same','research.generate_factor',messages=[{'role':'user','content':'fixture'}]);failure=None
   except Exception as exc:out=None;failure=exc
  return out,failure,post,complete,settle,unknown
 def test_single_primary_attempt_has_explicit_cap_and_preserves_full_usage(self):
  raw={'choices':[{'message':{'content':'answer'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,'completion_tokens_details':{'reasoning_tokens':8}}}
  out,failure,post,complete,settle,unknown=self.execute(raw)
  self.assertIsNone(failure);self.assertEqual(out['usage'],raw['usage']);self.assertEqual(out['finish_reason'],'stop');post.assert_called_once();complete.assert_not_called();self.assertEqual(post.call_args.args[1]['max_tokens'],8000);self.assertEqual(post.call_args.args[1]['response_format'],{'type':'json_object'});unknown.assert_not_called()
 def test_timeout_is_one_attempt_no_implicit_retry_or_refund(self):
  out,failure,post,complete,settle,unknown=self.execute(error=TimeoutError('fixture timeout'))
  self.assertIsInstance(failure,WorkflowError);post.assert_called_once();complete.assert_not_called();settle.assert_not_called();unknown.assert_called_once()
 def test_length_is_known_usage_failure_without_output_expansion(self):
  raw={'choices':[{'message':{'content':'','reasoning_content':'reasoning fixture'},'finish_reason':'length'}],'usage':{'prompt_tokens':10,'completion_tokens':8000,'total_tokens':8010,'completion_tokens_details':{'reasoning_tokens':8000}}}
  out,failure,post,complete,settle,unknown=self.execute(raw)
  self.assertIsNotNone(failure);post.assert_called_once();self.assertEqual(post.call_args.args[1]['max_tokens'],8000);self.assertEqual(settle.call_args.args[3]['usage'],raw['usage']);self.assertEqual(settle.call_args.args[3]['finish_reason'],'length')

class DirectQuantGenerationTests(unittest.TestCase):
 def test_direct_quant_generation_cannot_bypass_org_budget_or_spoof_actor(self):
  from app.routers.inst_quant import quant_ai_factor_generation
  body={'idempotency_key':'fixture','user_id':999,'org_id':999}
  with patch('app.routers.inst_quant._quant_uid',return_value=7),patch('services.quant_factor.generation.generate',return_value={'status':'ready'}) as generate:
   self.assertEqual(quant_ai_factor_generation(body,{'user':{'id':7},'org':{'id':2}}),{'status':'ready'})
  self.assertEqual(generate.call_args.args[:3],(7,2,None));self.assertIn('manual:7:fixture',generate.call_args.args[3])
 def test_direct_quant_generation_budget_denial_is_409_and_never_uses_personal_generator(self):
  from app.routers.inst_quant import quant_ai_factor_generation
  from fastapi import HTTPException
  with patch('app.routers.inst_quant._quant_uid',return_value=7),patch('services.quant_factor.generation.generate',side_effect=WorkflowError('额度不足')),patch('app.routers.ai_factor_generation.ai_factor_generations') as personal,self.assertRaises(HTTPException) as error:quant_ai_factor_generation({'idempotency_key':'fixture'},{'user':{'id':7},'org':{'id':2}})
  self.assertEqual(error.exception.status_code,409);personal.assert_not_called()
