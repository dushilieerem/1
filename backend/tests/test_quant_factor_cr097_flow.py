"""CR097 failures/resources/public endpoints with isolated HTTP and DB substitutes."""
import copy,json,unittest
from unittest.mock import MagicMock,patch
from services.quant_factor import review,resources,policy,f0_agent,service,sealed
from tests.test_quant_factor_assets import fixture

class FeedbackTests(unittest.TestCase):
 def row(self):
  row,_=fixture();row['archive']=None;row['status']='development_failed';row['evidence']['development']['gate']={'passed':False};row['evidence']['development'].pop('novelty',None)
  return row
 def conn(self,row):
  c=MagicMock();c.execute.return_value.fetchone.return_value=row;w=MagicMock();w.__enter__.return_value=c;return c,w
 def test_real_numeric_failure_can_request_review_without_novelty_or_archive(self):
  row=self.row();c,w=self.conn(row)
  with patch.object(review,'get_conn',return_value=w),patch.object(review,'current',return_value={'id':row['id']}),patch.object(review,'_require_novelty',side_effect=AssertionError('feedback never upgrades admission')):
   review.request_review(5,2,row['id'],'复盘冻结失败实验','research_feedback_only')
  update=[x for x in c.execute.call_args_list if x.args[0].startswith('UPDATE')][0];card=json.loads(update.args[1][0]);self.assertEqual(card['review']['purpose'],'research_feedback_only');self.assertFalse(card['review']['materials']['grants_admission'])
 def test_feedback_never_supports_or_registers(self):
  row=self.row();row['archive']={'review':{'status':'requested','purpose':'research_feedback_only','assigned_to':9}}
  c,w=self.conn(row)
  with patch.object(review,'get_conn',return_value=w),self.assertRaises(policy.WorkflowError):review.record(9,2,row['id'],'research_supported','不能升级')
  with patch('services.quant_factor.assets.approve',side_effect=policy.WorkflowError('不是研究资产审批')),self.assertRaises(policy.WorkflowError):review.record(9,2,row['id'],'approve_research_and_register','不能升级')
 def test_unknown_submission_and_never_run_are_not_completed_research(self):
  for block in ({},{'submission_started':True,'interrupted':True}):
   row=self.row();row['evidence']['development']=block
   with self.subTest(block=block),self.assertRaisesRegex(policy.WorkflowError,'尚无已完成'):review.feedback_materials(row)
 def test_known_execution_failure_can_be_reviewed_but_lists_missing_material(self):
  row=self.row();row['evidence']['development']={'run_id':'known','external_status':'failed','interrupted':False}
  materials=review.feedback_materials(row);self.assertFalse(materials['has_numerical_result']);self.assertTrue(materials['known_execution_failure']);self.assertTrue(materials['missing'])
 def test_resource_pending_does_not_relabel_numeric_success_as_failure(self):
  row=self.row();row['status']='development_error';row['evidence']['development']['gate']={'passed':False,'numerical_passed':True};row['evidence']['development']['novelty']={'status':'resource_pending','gate':{'complete':False,'passed':False}}
  self.assertIn('正式查重',review.feedback_materials(row)['missing'][-1])
 def test_formal_admission_still_uses_full_eligibility(self):
  row=self.row();c,w=self.conn(row)
  with patch.object(review,'get_conn',return_value=w),patch('services.quant_factor.assets.eligibility',side_effect=policy.WorkflowError('正式查重缺失')) as eligibility,self.assertRaisesRegex(policy.WorkflowError,'正式查重'):
   review.request_review(5,2,row['id'],'正式申请','research_admission')
  eligibility.assert_called_once();self.assertFalse(any(x.args[0].startswith('UPDATE') for x in c.execute.call_args_list))

class ResourceTests(unittest.TestCase):
 def test_sample_identity_is_stable_and_does_not_claim_historical_membership(self):
  sample=resources.static_sample(['000001.sz','600000.SH']);self.assertEqual(sample['membership_mode'],'static');self.assertEqual(sample,resources.static_sample(['000001.SZ','600000.SH']))
  for bad in [[],['000001.SZ','000001.SZ'],['../../escape']]:
   with self.subTest(bad=bad),self.assertRaises(policy.WorkflowError):resources.static_sample(bad)
 def test_frozen_snapshot_uses_only_static_sample_not_universe(self):
  row,_=fixture();snap=row['snapshot'];project={'id':'p','name':'sample','config':{'researchPlan':snap['plan'],'factorCodes':[snap['request']['factor_name']],'draftFactor':{'name':snap['request']['factor_name'],'body':'def '+snap['request']['factor_name']+'(self): return self.close.rank(axis=1,pct=True)'},'researchUniverseSymbols':['000001.SZ','600000.SH']}}
  result=policy.snapshot(project);self.assertNotIn('universe',result['request']);self.assertEqual(len(result['request']['universe_snapshot']['symbols']),2);self.assertNotIn('warmup_sessions',result['request'])
 def test_preflight_unavailable_fails_closed_without_any_model_or_compute(self):
  with patch.object(resources,'request_json',return_value=(404,{},{})):
   self.assertFalse(resources.preflight('factor',{})['allowed'])
   with self.assertRaises(policy.WorkflowError):resources.require('factor',{})
 def test_resource_wait_stops_without_another_model_decision(self):
  ctx={'novelty':{'status':'resource_pending'}}
  with patch.object(f0_agent,'_context',return_value=ctx),patch.object(f0_agent,'run_task',side_effect=AssertionError('must not burn model')):
   decision,usage=f0_agent.decide(5,2,{},'run')
  self.assertEqual(decision.action,'stop');self.assertEqual(usage['tokens_out'],0)
 def test_v5_legacy_validate_endpoint_is_rejected_before_dispatch(self):
  row,_=fixture();c=MagicMock();c.execute.return_value.fetchone.side_effect=[row,{'id':'topic'}];conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(service,'get_conn',return_value=conn),patch.object(service,'_dispatch') as dispatch,self.assertRaisesRegex(policy.WorkflowError,'封存验证'):service.validate(5,2,row['id'])
  dispatch.assert_not_called()


class QuantTargetTests(unittest.TestCase):
 def test_only_quant_proxy_uses_private_target_and_common_wrapper(self):
  from services.quant_factor import re_client
  from services.factor import re_factor_async_proxy as common
  source='def own_factor(self): return self.close.rank(axis=1,pct=True)'
  req={'factor_name':'own_factor','factor_code':source,'_svquant_ui':{'private':True}}
  with patch.object(re_client,'base',return_value='http://127.0.0.1:18804'),patch.object(re_client,'headers',return_value=None),patch.object(re_client,'request_json',return_value=(202,{}, {'run_id':'a'*32})) as http:
   re_client.proxy_submit_factor_backtest(req,target={'base':'http://127.0.0.1:18804'})
  self.assertEqual(http.call_args.args[0],'http://127.0.0.1:18804/api/backtest/factor');body=http.call_args.kwargs['payload'];self.assertNotIn('_svquant_ui',body);self.assertEqual(body['factor_code'],common.validated_factor_code(source,'own_factor'))
 def test_recovery_uses_persisted_target_instead_of_current_configuration(self):
  from services.quant_factor import re_client
  saved={'base':'http://127.0.0.1:18804','service_version':'frozen','method_version':'frozen'}
  with patch.object(re_client,'base',return_value='http://127.0.0.1:19999'),patch.object(re_client,'headers',return_value=None),patch.object(re_client,'request_json',return_value=(404,{},{})) as http:re_client.proxy_get_factor_run('a'*32,target=saved)
  self.assertEqual(http.call_args.args[0],'http://127.0.0.1:18804/api/backtest/factor/'+'a'*32)
 def test_target_identity_missing_fails_before_submission(self):
  from services.quant_factor import re_client
  with self.assertRaisesRegex(policy.WorkflowError,'身份'):re_client.target({'allowed':True})
