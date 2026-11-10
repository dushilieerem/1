import copy
from contextlib import ExitStack
from unittest.mock import patch
from psycopg.types.json import Jsonb
from tests.test_quant_research_method_pg import IsolatedNewResearchPostgresTests
from services.quant_factor import f0,ledger,research_method as method,provenance

class IsolatedRunSnapshotTests(IsolatedNewResearchPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  with cls.connection() as c:
   c.execute('ALTER TABLE quant_factor_trials ADD COLUMN branch_id text')
   c.execute('ALTER TABLE quant_factor_sealed_validations ADD COLUMN project_id text,ADD COLUMN id text')
   c.execute('CREATE TABLE quant_factor_iterations(id text,user_id bigint,org_id bigint,project_id text,status text)')
 def setUp(self):
  with self.connection() as c:c.execute('TRUNCATE quant_factor_f0_runs,quant_factor_trials,quant_factor_branches,quant_factor_candidates,quant_factor_topics,detect_projects CASCADE')
  super().setUp()
 def create_topic(self):
  self.view={'view_id':'view','manifest_sha256':'manifest','datasets':{'daily_bars':{'release':'frozen','sha256':'sha'}}}
  from services.quant_factor.research_contract import OHLCV
  meta={'published':True,'catalog_version':'view','publication_version':'view','fields':[{'name':name} for name in OHLCV]}
  body={'view_id':'view','view_manifest_sha256':'manifest','primary_holding_period':1,'max_trials':2,'max_sealed':1,'policy_version':'v5-p0','development_start':'2025-07-01','development_end':'2025-09-30','validation_start':'2026-06-22','validation_end':'2026-09-21'}
  with patch('services.workflow_workspace.platform_data.published_view',return_value=self.view),patch('services.quant_data_resources.dataset',return_value=meta):self.topic=ledger.create_topic(self.uid,self.org,'new-project',body)['topic']
  self.cfg=self.project()['config'];self.branch=self.cfg['v5ActiveBranch']
 def guards(self):
  stack=ExitStack();stack.enter_context(patch('services.factor.detect_store.get_project',side_effect=lambda uid,pid:{'project':self.project()}));stack.enter_context(patch.object(f0,'published_view',return_value=self.view));stack.enter_context(patch.object(f0.service,'control_status',return_value={'paused':False}));stack.enter_context(patch.object(f0.service,'locked_view_available',return_value=True));stack.enter_context(patch('services.quant_factor.resources.require_config'));stack.enter_context(patch('services.quant_factor.locked_data.for_topic',return_value={}));self.queue=stack.enter_context(patch.object(f0.POOL,'submit'));return stack
 def test_explicit_new_run_preserves_same_topic_h1_k_and_old_failed_record(self):
  self.create_topic()
  # Existing exposed research in this fixture proves K is not reset by a new run.
  with self.connection() as c:c.execute("INSERT INTO quant_factor_trials(id,topic_id,user_id,org_id,project_id,trial_no,report_id,outcome,kind,holding_period,returned_metrics,branch_id) VALUES('e1',%s,%s,%s,'new-project',1,'qf_fixture_development','failed','research',1,true,%s)",(self.topic['id'],self.uid,self.org,self.branch))
  with self.guards():
   first=f0.start(self.uid,self.org,self.topic['id'],self.branch,'first')
   old=copy.deepcopy(first['decision']);old.pop('method_snapshot') # Real first version never had a run snapshot.
   with self.connection() as c:c.execute("UPDATE quant_factor_f0_runs SET status='failed',stop_reason='fixture planner length',decision=%s WHERE id=%s",(Jsonb(old),first['id']))
   with self.assertRaisesRegex(ValueError,'新(?:建)?运行'):f0.resume(self.uid,self.org,first['id'])
   body={'previous_run_id':first['id'],'expected_method_hash':method.snapshot()['snapshot_hash'],'expected_control_epoch':self.cfg['v5ControlEpoch'],'acknowledged':True,'reason':'explicit updated output configuration'}
   new=f0.start(self.uid,self.org,self.topic['id'],self.branch,'second',method_change=body);again=f0.start(self.uid,self.org,self.topic['id'],self.branch,'second',method_change=body)
   self.assertEqual(new['id'],again['id']);self.assertNotEqual(first['id'],new['id']);self.assertEqual(self.queue.call_count,2)
  self.assertEqual(new['topic_id'],first['topic_id']);self.assertEqual(new['branch_id'],first['branch_id']);self.assertEqual(new['decision']['method_transition']['previous_run_id'],first['id']);self.assertEqual(new['decision']['method_snapshot'],method.snapshot())
  with self.connection() as c:
   prior=c.execute('SELECT status,decision FROM quant_factor_f0_runs WHERE id=%s',(first['id'],)).fetchone();self.assertEqual(prior['status'],'failed');self.assertEqual(prior['decision'],old)
   self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_branches').fetchone()['n'],1)
  self.assertEqual(ledger.current_k(ledger._trials(self.uid,self.org,self.topic['id']),1),1);self.assertEqual(self.project()['config'],self.cfg)
 def test_nonmethod_change_can_resume_but_actual_loaded_method_change_cannot(self):
  self.create_topic()
  with self.guards():
   first=f0.start(self.uid,self.org,self.topic['id'],self.branch,'first')
   with self.connection() as c:c.execute("UPDATE quant_factor_f0_runs SET status='stopped' WHERE id=%s",(first['id'],))
   with patch.object(provenance,'_CODE_REVISION','nonmethod-quant-change'):
    same=f0.resume(self.uid,self.org,first['id']);self.assertEqual(same['id'],first['id'])
   with self.connection() as c:c.execute("UPDATE quant_factor_f0_runs SET status='stopped' WHERE id=%s",(first['id'],))
   with patch.object(method,'_LOADED_IMPLEMENTATION','changed-related-loaded-method'),self.assertRaisesRegex(ValueError,'新(?:建)?运行'):f0.resume(self.uid,self.org,first['id'])
   self.assertEqual(self.queue.call_count,2)

 def test_data_dependency_wait_preserves_method_snapshot_and_resumes_same_run(self):
  from services.quant_factor.policy import WorkflowError
  self.create_topic()
  with self.guards():
   with patch('services.quant_factor.locked_data.for_topic',side_effect=WorkflowError('fixed view not yet enabled')):
    waiting=f0.start(self.uid,self.org,self.topic['id'],self.branch,'data-wait')
   self.assertEqual(waiting['status'],'stopped');self.assertEqual(waiting['decision']['method_snapshot'],method.snapshot());self.assertEqual(waiting['decision']['control_epoch'],self.cfg['v5ControlEpoch']);self.assertEqual(waiting['decision']['technical_wait']['kind'],'fixed_data_or_resources');self.queue.assert_not_called()
   resumed=f0.resume(self.uid,self.org,waiting['id']);self.assertEqual(resumed['id'],waiting['id']);self.assertEqual(resumed['topic_id'],self.topic['id']);self.assertEqual(resumed['branch_id'],self.branch);self.queue.assert_called_once()
  self.assertEqual(ledger.current_k(ledger._trials(self.uid,self.org,self.topic['id']),1),0)

 def test_updated_method_and_manual_handoff_bind_original_epoch_in_one_new_run(self):
  from services.quant_factor.policy import digest,snapshot,WorkflowError
  self.create_topic()
  with self.guards():
   old=f0.start(self.uid,self.org,self.topic['id'],self.branch,'first-auto')
   with self.connection() as c:c.execute("UPDATE quant_factor_f0_runs SET status='failed' WHERE id=%s",(old['id'],))
   cfg=self.project()['config'];epoch=cfg['v5ControlEpoch'];cfg.update(factorCodes=['manual_signal'],draftFactor={'name':'manual_signal','body':'def manual_signal(self): return self.close'},v5ManualVersion={'branch_id':self.branch,'control_epoch':epoch,'source':'human_workbench_save'})
   with self.connection() as c:c.execute('UPDATE detect_projects SET config=%s WHERE user_id=%s AND id=%s',(Jsonb(cfg),self.uid,'new-project'))
   saved_hash=digest(snapshot(self.project()));change={'previous_run_id':old['id'],'expected_method_hash':method.snapshot()['snapshot_hash'],'expected_control_epoch':epoch,'acknowledged':True,'reason':'explicit method and manual version'}
   with self.assertRaisesRegex(WorkflowError,'人工版本'):f0.start(self.uid,self.org,self.topic['id'],self.branch,'missing-handoff',method_change=change)
   run=f0.start(self.uid,self.org,self.topic['id'],self.branch,'manual-and-method',handoff={'snapshot_hash':saved_hash,'control_epoch':epoch,'acknowledged':True},method_change=change)
  self.assertEqual(run['decision']['manual_handoff']['snapshot_hash'],saved_hash);self.assertEqual(run['decision']['manual_handoff']['branch_id'],self.branch);self.assertEqual(run['decision']['method_transition']['expected_control_epoch'],epoch)
  self.assertNotEqual(run['decision']['control_epoch'],epoch);self.assertEqual(run['decision']['manual_handoff']['control_epoch'],run['decision']['control_epoch']);self.assertEqual(run['decision']['method_transition']['previous_run_id'],old['id'])
  self.assertEqual(self.project()['config']['draftFactor']['body'],'def manual_signal(self): return self.close');self.assertEqual(ledger.current_k(ledger._trials(self.uid,self.org,self.topic['id']),1),0)
