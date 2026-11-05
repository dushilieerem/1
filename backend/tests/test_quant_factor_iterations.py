import copy
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock,patch
from services.quant_factor import iterations as it
from services.quant_factor.policy import WorkflowError,digest

PLAN={'revision':'fixed','hypothesis':'past prices only','candidateExpression':'CLV 5','target':'next day','developmentStart':'2025-01-01','developmentEnd':'2025-06-30','validationStart':'2025-07-01','validationEnd':'2025-12-31','maxTrials':4}
BASE={'plan':PLAN,'rules':{'minSignedIc':.02,'maxDrawdown':.3,'minObservations':60},'request':{'factor_name':'clv','factor_code':'old'}}
JOB={'id':'i','status':'running','project_id':'p','max_rounds':2,'baseline':BASE}
def candidate(status='development_failed',release='release1'):
 return {'id':'c','status':status,'snapshot_hash':'hash','snapshot':copy.deepcopy(BASE),'evidence':{'development':{'run_id':'real1','report_id':'r1','gate':{'passed':status=='development_passed','checks':[{'name':'Rank IC','actual':.01,'operator':'>=','threshold':.02,'passed':False}]},'result':{'metrics':{'rank_ic':.01},'meta':{'data_release_id':release}}}}}
class IterationTests(unittest.TestCase):
 def run_mock(self,results,max_rounds=2,fields=None):
  stack=ExitStack();self.addCleanup(stack.close);handles={}
  for name in ['checkpoint','log','finish','save_round','remember_child','cleanup_children','wait_candidate','wait_agent','apply_code','submit_research','get_project','get_conn']:
   handles[name]=stack.enter_context(patch.object(it,name))
  handles['checkpoint'].return_value={**JOB,'max_rounds':max_rounds}
  handles['wait_candidate'].side_effect=results
  handles['wait_agent'].return_value={'id':'a','output':{'fields':fields or {'name':'clv2','code':'new'}}}
  handles['apply_code'].return_value='next_hash'
  handles['get_project'].return_value={'project':{'config':{'researchPlan':copy.deepcopy(PLAN),'draftFactor':{'name':'clv','body':'old'},'factorCodes':['clv']}}}
  handles['create']=stack.enter_context(patch.object(it.service,'create',return_value=candidate()))
  handles['validate']=stack.enter_context(patch.object(it.service,'validate'))
  handles['agent']=stack.enter_context(patch.object(it.agent_jobs,'create',return_value={'id':'a'}))
  it.run(1,2,'i');return handles
 def test_failed_research_improves_once_and_stops_at_budget_with_fixed_gates(self):
  h=self.run_mock([candidate(),candidate()]);self.assertEqual(h['create'].call_count,2);self.assertEqual(h['agent'].call_count,1)
  self.assertEqual(h['create'].call_args_list[0].args[-1],digest(BASE));self.assertEqual(h['create'].call_args_list[1].args[-1],'next_hash')
  self.assertEqual(h['finish'].call_args.args[3],'limit_reached');h['validate'].assert_not_called();h['submit_research'].assert_not_called()
  sent=h['agent'].call_args.args[4];self.assertIn('0.02',sent['hypothesis']);self.assertNotIn('validation',sent['hypothesis']);self.assertEqual(sent['candidateExpression'],'CLV 5')
  self.assertEqual(PLAN['revision'],'fixed');self.assertEqual(BASE['rules']['minSignedIc'],.02)
 def test_oos_failure_stops_and_is_never_used_for_more_training(self):
  h=self.run_mock([candidate('development_passed'),candidate('validation_failed')],max_rounds=20)
  h['validate'].assert_called_once();h['agent'].assert_not_called();h['submit_research'].assert_not_called();self.assertEqual(h['finish'].call_args.args[3],'validation_failed')
 def test_passing_both_gates_only_requests_independent_research_review(self):
  h=self.run_mock([candidate('development_passed'),candidate('validation_passed')]);h['submit_research'].assert_called_once();h['agent'].assert_not_called()
 def test_changed_data_release_stops_cross_release_search(self):
  h=self.run_mock([candidate(),candidate(release='release2')]);self.assertEqual(h['finish'].call_args.args[3],'failed');self.assertIn('数据版本',h['finish'].call_args.args[4]);h['submit_research'].assert_not_called()
 def test_tool_error_is_not_treated_as_a_bad_factor(self):
  h=self.run_mock([candidate('development_error')]);h['agent'].assert_not_called();self.assertEqual(h['finish'].call_args.args[3],'failed')
 def test_identical_generated_code_is_not_recomputed(self):
  h=self.run_mock([candidate()],fields={'name':'clv','code':'old'});h['create'].assert_called_once();h['apply_code'].assert_not_called();self.assertIn('未产生新的实现',h['finish'].call_args.args[4])
 def test_used_holdout_overlap_rejected_even_after_plan_revision_changes(self):
  c=candidate();c['evidence']['validation']={'run_id':'v'}
  self.assertTrue(it.validation_seen([c],{**PLAN,'revision':'new'}))
  self.assertFalse(it.validation_seen([c],{**PLAN,'validationStart':'2026-01-01','validationEnd':'2026-06-30'}))
 def test_paused_loop_never_writes_code(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'status':'paused'};conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(it,'get_conn',return_value=conn),patch('services.factor.code_validation.validated_factor_code'):
   with self.assertRaises(it.Stopped):it.apply_code(1,2,'i','expected',{'name':'f','code':'def f(self): return self.close'})
  self.assertFalse(any('UPDATE detect_projects' in str(x) for x in c.execute.call_args_list))
 def test_paused_handoff_does_not_archive_or_send_review(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'status':'paused'};conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(it,'checkpoint'),patch.object(it,'get_conn',return_value=conn),patch.object(it.service,'archive') as archive,patch('services.quant_factor.review.request_review') as review:
   with self.assertRaises(it.Stopped):it.submit_research(1,2,'i',candidate(),1,'expected')
   archive.assert_not_called();review.assert_not_called()
 def test_manual_input_change_stops_before_next_tool(self):
  with patch.object(it,'read',return_value=JOB),patch.object(it,'get_project',return_value={'project':{}}),patch.object(it,'snapshot',return_value={'changed':True}):
   with self.assertRaisesRegex(WorkflowError,'人工修改'):it.checkpoint(1,2,'i','original')
 def test_invalid_round_limits_rejected_before_database_or_model(self):
  with patch.object(it,'get_conn') as db:
   for n in [0,21,True,1.5]:
    with self.assertRaises(WorkflowError):it.start(1,2,'p',n)
   db.assert_not_called()

class PauseTests(unittest.TestCase):
 def test_pause_keeps_inflight_frozen_calculation_but_stops_agent_adoption(self):
  with patch.object(it.agent_jobs,'cancel') as agent_cancel,patch.object(it.service,'cancel') as cancel,patch.object(it.service,'current') as read:
   it.cleanup_children(1,2,{'status':'paused','candidate_id':'c','agent_job_id':'a'})
   agent_cancel.assert_called_once_with(1,2,'a');cancel.assert_not_called();read.assert_not_called()

class NoveltyIterationTests(unittest.TestCase):
 run_mock=IterationTests.run_mock
 def test_novelty_feedback_excludes_daily_panels_and_keeps_failed_gate(self):
  c=candidate();c['evidence']['development']['novelty']={'status':'failed','gate':{'max_abs_correlation':.95,'closest':{'reference_id':'existing','factor_name':'known','mean_abs_spearman':.95,'series':['DO_NOT_SEND']*10000}},'comparisons':['DO_NOT_SEND']*10000}
  h=self.run_mock([c,c]);draft=h['agent'].call_args.args[4]
  self.assertIn('0.95',draft['hypothesis']);self.assertNotIn('DO_NOT_SEND',draft['hypothesis']);self.assertLess(len(draft['hypothesis']),1500)
 def test_reference_source_drift_stops_iteration(self):
  a=candidate();b=candidate()
  for c,sha in [(a,'one'),(b,'two')]:c['evidence']['development']['novelty']={'status':'failed','meta':{'reference_source_hash':sha}}
  h=self.run_mock([a,b]);self.assertEqual(h['finish'].call_args.args[3],'failed');self.assertIn('源码版本',h['finish'].call_args.args[4])

class TenantScopeTests(unittest.TestCase):
 def test_pending_iteration_count_is_tenant_scoped(self):
  c=MagicMock();conn=MagicMock();conn.__enter__.return_value=c
  def execute(sql,params=None):
   c.last_call=(sql,params)
   if 'COUNT(*) AS n' in sql:c.next_row={'n':0}
   elif 'FROM quant_factor_iterations' in sql and 'status IN' in sql:c.next_row=None
   elif 'FROM detect_projects' in sql:c.next_row={'id':'p'}
   elif 'quant_factor_agent_jobs' in sql:c.next_row=None
   else:c.next_row=None
   return c
  c.execute.side_effect=execute;c.fetchone.side_effect=lambda:c.next_row;c.fetchall.return_value=[]
  with patch.object(it,'get_conn',return_value=conn),patch.object(it,'_row_project',return_value={}),patch.object(it,'snapshot',return_value={'plan':{'researchPurpose':'replication','maxTrials':4}}),patch.object(it.POOL,'submit'),patch.object(it,'read',return_value={'id':'i'}):
   it.start(1,2,'p',2)
  self.assertEqual(c.execute.call_args_list[0].args[1],(9109,1))
  pending=[x for x in c.execute.call_args_list if 'COUNT(*) AS n' in x.args[0] and 'quant_factor_iterations' in x.args[0]]
  self.assertTrue(pending);self.assertEqual(pending[-1].args[1],(1,2))

 def test_budget_rejects_existing_plus_rounds_before_writing(self):
  c=MagicMock();conn=MagicMock();conn.__enter__.return_value=c
  def execute(sql,params=None):
   if 'COUNT(*) AS n' in sql:c.next_row={'n':0}
   elif 'FROM quant_factor_iterations' in sql and 'status IN' in sql:c.next_row=None
   elif 'FROM detect_projects' in sql:c.next_row={'id':'p'}
   elif 'quant_factor_agent_jobs' in sql:c.next_row=None
   else:c.next_row=None
   return c
  c.execute.side_effect=execute;c.fetchone.side_effect=lambda:c.next_row
  c.fetchall.return_value=[{'status':'development_failed','evidence':{}}]*3
  with patch.object(it,'get_conn',return_value=conn),patch.object(it,'_row_project',return_value={}),patch.object(it,'snapshot',return_value={'plan':{'researchPurpose':'replication','maxTrials':4}}),patch.object(it.POOL,'submit') as pool:
   with self.assertRaisesRegex(WorkflowError,'剩余研究尝试预算 1 次'):
    it.start(1,2,'p',2)
  pool.assert_not_called()
  self.assertFalse(any('INSERT INTO quant_factor_iterations' in x.args[0] for x in c.execute.call_args_list))

 def test_checkpoint_heartbeat_is_tenant_scoped(self):
  c=MagicMock();conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(it,'read',return_value=JOB),patch.object(it,'get_conn',return_value=conn):
   it.checkpoint(1,2,'i')
  heartbeat=[x for x in c.execute.call_args_list if 'SET updated_at=NOW()' in x.args[0]]
  self.assertTrue(heartbeat);self.assertEqual(heartbeat[-1].args[1],('i',1,2))

 def test_review_handoff_update_is_tenant_scoped(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'status':'running'};conn=MagicMock();conn.__enter__.return_value=c
  cand=candidate();cand['snapshot']['plan']['researchPurpose']='replication'
  with patch.object(it,'checkpoint'),patch.object(it,'get_conn',return_value=conn),patch.object(it.service,'archive'),patch('services.quant_factor.review.request_review'):
   it.submit_research(1,2,'i',cand,1,None)
  handoff=[x for x in c.execute.call_args_list if "status='review_pending'" in x.args[0]]
  self.assertTrue(handoff);self.assertEqual(handoff[-1].args[1][-2:],(1,2))
