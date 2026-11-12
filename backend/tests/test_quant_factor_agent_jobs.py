import unittest
from unittest.mock import patch,MagicMock
import uuid
from services.quant_factor import agent_jobs as jobs
from services.quant_factor.policy import WorkflowError

FIELDS={'horizon_days':1,'title':'日内区间位置研究','direction':'量价','question':'检验20日区间位置对未来一天收益的解释是否存在。','background':'研究假设尚未验证。','summary':'使用真实行情检验，不给投资建议。'}
class AgentJobTests(unittest.TestCase):
 def test_real_tool_boundaries_return_valid_fields_and_usage(self):
  import json
  with patch.object(jobs,'update',return_value=True) as update,patch.object(jobs,'list_projects',return_value={'projects':[{'name':'existing'}]}),patch('services.workflow_workspace.platform_data.published_view',return_value={'view_id':'release-x','datasets':{'daily_bars':{'rows':10}}}),patch('services.quant_factor.asset_context.catalogue',return_value={'scope':'test','count':1,'hash':'h','builtins':[{'library_name':'lib','factor_name':'f','description':'known'}],'owned':[]}),patch.object(jobs,'get_task'),patch('services.quant_factor.model_budget.run',return_value={'content':'```json\n'+json.dumps(FIELDS)+'\n```','model':'test-double','tokens_in':10,'tokens_out':20}) as model,patch('services.quant_data_resources.dataset',return_value={'published':True,'catalog_version':'release-x','publication_version':'release-x','fields':[{'name':'close'},{'name':'volume'},{'name':'unsupported_field'}]}),patch.object(jobs,'record_usage') as usage:
   result=jobs._plan_task(1,2,'j',{})
   self.assertEqual(result['fields'],{k:v for k,v in FIELDS.items() if k!='horizon_days'});self.assertEqual(result['existing_research_count'],1)
   self.assertEqual([c.args[4]['action'] for c in update.call_args_list],['read_data','read_research','read_factor_library','factor_library_read','model_started'])
   self.assertEqual(result['tokens_out'],20);model.assert_called_once();self.assertEqual(model.call_args.args[3],'job:j:planner:1')
   self.assertEqual(json.loads(model.call_args.kwargs['messages'][1]['content'])['allowed_compute_fields'],['close','volume'])
 def test_cancelled_job_never_calls_model_or_fills_fields(self):
  with patch.object(jobs,'read',return_value={'status':'cancelled'}),patch('services.quant_factor.model_budget.run') as model,patch.object(jobs,'update') as update:
   jobs.run(1,2,'j');model.assert_not_called();update.assert_not_called()
 def test_takeover_between_tools_stops_remaining_calls(self):
  with patch.object(jobs,'update',return_value=False),patch('services.workflow_workspace.platform_data.published_view') as data,patch('services.quant_factor.model_budget.run') as model:
   self.assertIsNone(jobs._plan_task(1,2,'j',{}));data.assert_not_called();model.assert_not_called()
 def test_invalid_model_output_is_failure_not_fabricated_task(self):
  with patch.object(jobs,'read',return_value={'status':'queued','stage':'F1','input':{'registered_rules':{'direction':'negative','icMetric':'rank_ic'},'draft':{}}}),patch.object(jobs,'_plan_task',side_effect=ValueError('private upstream text')),patch.object(jobs,'update') as update:
   jobs.run(1,2,'j');self.assertEqual(update.call_args.args[3],'failed');self.assertNotIn('private upstream text',str(update.call_args));self.assertEqual(len(update.call_args.args),5)
 def test_plan_job_only_returns_advisory_fields_not_dates_or_gates(self):
  out={'suggestion':{'hypothesis':'h','target':'t','acceptance':'a','minSignedIc':0,'developmentStart':'changed'}}
  with patch.object(jobs,'read',return_value={'status':'queued','stage':'F2','project_id':'p','input':{'registered_rules':{'direction':'negative','icMetric':'rank_ic'},'draft':{}}}),patch('services.quant_factor.assistant.suggest',return_value=out),patch.object(jobs,'update',return_value=True) as update:
   jobs.run(1,2,'j');self.assertEqual(update.call_args.args[3],'ready');self.assertEqual(update.call_args.args[5]['fields'],{'hypothesis':'h','target':'t','acceptance':'a'})
 def test_code_job_reuses_platform_generation_and_rejects_invalid_code(self):
  with patch.object(jobs,'read',return_value={'status':'queued','stage':'F3','project_id':'p','input':{'registered_rules':{'direction':'negative','icMetric':'rank_ic'},'draft':{'hypothesis':'some research question'}}}),patch.object(jobs,'assert_quota_available'),patch.object(jobs,'record_usage'),patch('services.quant_factor.generation.generate',return_value={'status':'rejected','validation':{'status':'failed','errors':['unsafe']}}) as gen,patch.object(jobs,'update',return_value=True) as update:
   jobs.run(1,2,'j');gen.assert_called_once();self.assertEqual(update.call_args.args[3],'failed');self.assertIn('unsafe',update.call_args.args[4]['message'])
 def test_idempotent_existing_input_never_schedules_model_twice(self):
  draft={'title':'x'};inputs={'draft':draft,'project_id':None,'stage':'F1'}
  c=MagicMock();c.execute.return_value.fetchone.return_value={'id':'old','input':inputs}
  conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(jobs,'get_conn',return_value=conn),patch.object(jobs,'read',return_value={'id':'old'}) as read,patch.object(jobs.POOL,'submit') as submit:
   self.assertEqual(jobs.create(1,2,'F1',None,draft,'key'),{'id':'old'});submit.assert_not_called();read.assert_called_once_with(1,2,'old')
 def test_key_reuse_for_changed_input_rejected(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'id':'old','input':{}}
  conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(jobs,'get_conn',return_value=conn),patch.object(jobs.POOL,'submit') as submit:
   with self.assertRaises(WorkflowError):jobs.create(1,2,'F1',None,{'title':'changed'},'key')
   submit.assert_not_called()
 def test_unknown_or_missing_project_stage_cannot_run(self):
  for stage,pid in [('F6',None),('F3',None)]:
   with self.assertRaises(WorkflowError):jobs.create(1,2,stage,pid,{},None)

class PlanFormatRepairTests(unittest.TestCase):
 def test_one_format_repair_is_validated_and_both_attempts_record_usage(self):
  from services.quant_factor import assistant as a
  import json
  valid={'hypothesis':'h','target':'future one day','acceptance':'method','summary':'not tested','limitations':[]}
  with patch.object(a,'get_project',return_value={'project':{'name':'study','config':{}}}),patch.object(a,'get_task'),patch.object(a,'assert_quota_available'),patch('services.quant_factor.model_budget.run',side_effect=[{'content':'{"hypothesis":{}}','tokens_out':10},{'content':json.dumps(valid),'tokens_out':20}]) as run,patch.object(a,'record_usage') as usage:
   progress=MagicMock(return_value=True);out=a.suggest(1,2,'p',progress=progress)
   self.assertEqual(out['suggestion'],valid);self.assertEqual(run.call_count,2);self.assertNotEqual(run.call_args_list[0].args[3],run.call_args_list[1].args[3]);progress.assert_called_once()
 def test_takeover_before_format_repair_prevents_second_model_request(self):
  from services.quant_factor import assistant as a
  with patch.object(a,'get_project',return_value={'project':{'name':'study','config':{}}}),patch.object(a,'get_task'),patch.object(a,'assert_quota_available'),patch('services.quant_factor.model_budget.run',return_value={'content':'{}'}) as run,patch.object(a,'record_usage'):
   with self.assertRaises(RuntimeError):a.suggest(1,2,'p',progress=lambda _:False)
   run.assert_called_once()

class AgentAuditTests(unittest.TestCase):
 def test_consumed_f1_proposal_is_not_restored_as_a_new_task(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'id':'used'};conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(jobs,'get_conn',return_value=conn),patch.object(jobs,'list_projects',return_value={'projects':[{'config':{'researchContext':{'agentJobId':'used'}}}]}),patch.object(jobs,'read') as read:
   self.assertIsNone(jobs.latest(1,2,'F1'));read.assert_not_called()
 def test_f3_generation_receives_expression_and_manual_code(self):
  d={'hypothesis':'h','candidateExpression':'window=5; zero range -> NaN','target':'1 day','name':'factor','code':'manual code'}
  with patch.object(jobs,'read',return_value={'status':'queued','stage':'F3','project_id':'p','input':{'registered_rules':{'direction':'negative','icMetric':'rank_ic'},'draft':d}}),patch.object(jobs,'assert_quota_available'),patch.object(jobs,'record_usage'),patch('services.quant_factor.generation.generate',return_value={'status':'rejected','validation':{'status':'failed','errors':['stop']}}) as gen,patch.object(jobs,'update',return_value=True):
   jobs.run(1,2,'j');prompt=gen.call_args.args[4]['prompt'];self.assertIn('window=5',prompt);self.assertIn('manual code',prompt);self.assertIn('1 day',prompt)


class WindowFeedbackTests(unittest.TestCase):
 def test_f3_window_mismatch_is_fed_back_and_rewritten_once(self):
  draft={'hypothesis':'5 日反转：过去 5 个交易日累计收益最低的股票次日反转','target':'1 day','name':'rev5','code':''}
  first={'status':'ready','validation':{'status':'passed'},'factor':{'factor_name':'rev5','factor_code':'def f0_factor(self):\n    return -self.close.pct_change(1)'},'meta':{}}
  second={'status':'ready','validation':{'status':'passed'},'factor':{'factor_name':'rev5','factor_code':'def f0_factor(self):\n    return -self.close.pct_change(5)'},'meta':{}}
  with patch.object(jobs,'read',return_value={'status':'queued','stage':'F3','project_id':'p','input':{'registered_rules':{'direction':'negative','icMetric':'rank_ic'},'draft':draft}}),patch.object(jobs,'update',return_value=True) as update,patch('services.quant_factor.f0_agent.record_progress'),patch('services.quant_factor.generation.generate',side_effect=[first,second]) as gen:
   jobs.run(1,2,'j')
  self.assertEqual(gen.call_count,2)
  self.assertEqual(gen.call_args_list[0].args[3],'j')
  self.assertTrue(gen.call_args_list[1].args[3].endswith('-window2'))
  self.assertIn('5 日反转',gen.call_args_list[1].args[4]['prompt']);self.assertIsInstance(uuid.UUID(gen.call_args_list[1].args[4]['idempotency_key']),uuid.UUID)
  self.assertEqual([c.args[4]['action'] for c in update.call_args_list].count('implementation_window_feedback'),1)


class CapabilityFeedbackTests(unittest.TestCase):
 def test_f3_unsupported_capability_is_fed_back_and_rewritten_once(self):
  draft={'hypothesis':'用成交量计算量价因子','target':'1 day','name':'f','code':''}
  first={'status':'rejected','validation':{'status':'failed','errors':['需求暂不支持：自然对数 ln']},'meta':{}}
  second={'status':'ready','validation':{'status':'passed'},'factor':{'factor_name':'f','factor_code':'def f0_factor(self):\n    return -self.close.pct_change(5)'},'meta':{}}
  with patch.object(jobs,'read',return_value={'status':'queued','stage':'F3','project_id':'p','input':{'registered_rules':{'direction':'negative','icMetric':'rank_ic'},'draft':draft}}),patch.object(jobs,'update',return_value=True) as update,patch('services.quant_factor.f0_agent.record_progress'),patch('services.quant_factor.generation.generate',side_effect=[first,second]) as gen:
   jobs.run(1,2,'j')
  self.assertEqual(gen.call_count,2);self.assertTrue(gen.call_args_list[1].args[3].endswith('-cap2'));self.assertIn('自然对数',gen.call_args_list[1].args[4]['prompt']);self.assertIn('np.log',gen.call_args_list[1].args[4]['prompt'])
