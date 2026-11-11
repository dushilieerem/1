"""Actual bounded PG transactions, own unique schema/high actors; never production records."""
import copy
from contextlib import contextmanager
from unittest.mock import patch
from psycopg.types.json import Jsonb
from services.quant_factor import ledger,presentation,f0,f0_agent,repo,agent_jobs
from services.quant_factor.policy import digest,snapshot,WorkflowError
from services.factor.detect_store import _row_project
from tests.test_quant_factor_assets_pg import IsolatedAssetPostgresTests

class IsolatedHandoffPostgresTests(IsolatedAssetPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  with cls.connection() as c:
   c.execute("ALTER TABLE detect_projects ADD COLUMN description text DEFAULT '',ADD COLUMN updated_at timestamptz DEFAULT now()")
   c.execute("ALTER TABLE quant_factor_topics ADD COLUMN updated_at timestamptz DEFAULT now(),ADD COLUMN max_sealed int DEFAULT 1")
   c.execute("ALTER TABLE quant_factor_branches ADD COLUMN parent_id text,ADD COLUMN source text DEFAULT 'manual',ADD COLUMN owner_id bigint,ADD COLUMN hypothesis_version int DEFAULT 1,ADD COLUMN implementation_version int DEFAULT 1,ADD COLUMN title text,ADD COLUMN created_at timestamptz DEFAULT now()")
   c.execute('ALTER TABLE quant_factor_trials ADD COLUMN branch_id text')
   for name in ['quant_factor_agent_jobs','quant_factor_iterations']:c.execute('CREATE TABLE '+name+'(id text,user_id bigint,org_id bigint,project_id text,status text)')
   c.execute('ALTER TABLE quant_factor_sealed_validations ADD COLUMN id text,ADD COLUMN project_id text')
   c.execute("ALTER TABLE quant_factor_agent_jobs ADD COLUMN input jsonb DEFAULT '{}',ADD COLUMN output jsonb,ADD COLUMN events jsonb DEFAULT '[]',ADD COLUMN updated_at timestamptz DEFAULT now()")
 def setUp(self):
  super().setUp()
  for target in [repo,ledger,f0,f0_agent,agent_jobs]:
   guard=patch.object(target,'get_conn',self.connection);guard.start();self.addCleanup(guard.stop)
  guard=patch('services.core.db.get_conn',self.connection);guard.start();self.addCleanup(guard.stop)
  guard=patch('services.factor.detect_store.get_project',side_effect=lambda uid,pid:{'project':self.project()});guard.start();self.addCleanup(guard.stop)
  with self.connection() as c:
   c.execute('TRUNCATE quant_factor_agent_jobs,quant_factor_iterations')
   c.execute("UPDATE quant_factor_candidates SET archive='{}',evidence=jsonb_set(evidence,'{branch_id}','\"branch\"')")
   c.execute("UPDATE quant_factor_trials SET branch_id='branch'")
   cfg=copy.deepcopy(self.facts['project']['config']);cfg.update(v5ActiveBranch='branch',v5ControlEpoch='original')
   c.execute('UPDATE detect_projects SET config=%s',(Jsonb(cfg),))
 def project(self):
  with self.connection() as c:return _row_project(c.execute('SELECT * FROM detect_projects').fetchone())
 def _restore_asset_archive(self):
  with self.connection() as c:c.execute("UPDATE quant_factor_candidates SET archive=%s::jsonb WHERE id='candidate'",(Jsonb(self.row['archive']),))
 def test_parallel_approval_is_idempotent_in_real_transactions(self):
  self._restore_asset_archive();return super().test_parallel_approval_is_idempotent_in_real_transactions()
 def test_write_failure_rolls_back_approval_and_asset_and_event(self):
  self._restore_asset_archive();return super().test_write_failure_rolls_back_approval_and_asset_and_event()
 def test_other_computed_candidate_without_ledger_blocks_real_approval(self):
  self._restore_asset_archive();return super().test_other_computed_candidate_without_ledger_blocks_real_approval()
 def test_start_and_approval_use_compatible_lock_order(self):
  self._restore_asset_archive();return super().test_start_and_approval_use_compatible_lock_order()
 def test_takeover_forks_exact_frozen_source_and_preserves_old_evidence_and_k(self):
  before=copy.deepcopy(self.row)
  with patch.object(ledger,'get_conn',self.connection):out=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True)
  project=self.project();self.assertEqual(project['config']['v5ActiveBranch'],out['id']);self.assertEqual(project['config']['sourceResearchCandidate']['snapshot_hash'],before['snapshot_hash'])
  with self.connection() as c:
   self.assertEqual(c.execute('SELECT snapshot_hash FROM quant_factor_candidates').fetchone()['snapshot_hash'],before['snapshot_hash']);self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_trials').fetchone()['n'],1)
 def test_manual_save_rejects_stale_epoch_and_rolls_back(self):
  with patch.object(ledger,'get_conn',self.connection):out=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True)
  payload=self.project();stale=copy.deepcopy(payload)
  with patch.object(ledger,'get_conn',self.connection):
   saved=presentation.save_workbench(self.uid,self.org,'project',payload)
   self.assertNotEqual(saved['project']['config']['v5ControlEpoch'],stale['config']['v5ControlEpoch'])
   with self.assertRaisesRegex(ValueError,'控制版本'):presentation.save_workbench(self.uid,self.org,'project',stale)
 def test_late_old_model_cannot_overwrite_after_real_pause_and_takeover(self):
  old=self.project()
  with self.connection() as c:c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision) VALUES('old',%s,%s,'project','topic','branch','old','running','{\"runner_epoch\":\"old\"}')",(self.uid,self.org))
  with patch.object(ledger,'get_conn',self.connection):ledger.set_topic_status(self.uid,self.org,'topic','paused');ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True)
  with patch.object(f0_agent,'get_conn',self.connection),self.assertRaises(WorkflowError):
   with f0_agent._writable_project(self.uid,self.org,old,'topic','old','old'):self.fail('old writer obtained ownership')
  with self.connection() as c:self.assertEqual(c.execute("SELECT status FROM quant_factor_f0_runs WHERE id='old'").fetchone()['status'],'stopped')
 def test_handoff_commit_then_lost_response_replays_same_queue_and_budget(self):
  with patch.object(ledger,'get_conn',self.connection):branch=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True)
  project=self.project();handoff={'acknowledged':True,'control_epoch':project['config']['v5ControlEpoch'],'snapshot_hash':digest(snapshot(project))}
  with patch.object(f0,'get_conn',self.connection),patch.object(f0.ledger,'_trials',return_value=[{'trial_no':1,'holding_period':1,'kind':'research','outcome':'passed','returned_metrics':True}]),patch.object(f0.service,'control_status',return_value={'paused':False}),patch.object(f0,'published_view',return_value={'view_id':'view'}),patch('services.quant_factor.locked_data.for_topic',return_value={'view_id':'view','view_manifest_sha256':'manifest','daily_release':'release','daily_dataset_sha256':'dataset'}),patch('services.quant_factor.resources.require_config'),patch.object(f0.POOL,'submit') as schedule:
   first=f0.start(self.uid,self.org,'topic',branch['id'],'lost-response',handoff);again=f0.start(self.uid,self.org,'topic',branch['id'],'lost-response',handoff)
  self.assertEqual(first['id'],again['id']);self.assertEqual(schedule.call_count,1)
  with self.connection() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_trials').fetchone()['n'],1)
   self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_f0_runs').fetchone()['n'],1)
 def test_handoff_insert_failure_rolls_back_control_epoch_and_queue(self):
  with patch.object(ledger,'get_conn',self.connection):branch=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True)
  project=self.project();epoch=project['config']['v5ControlEpoch'];handoff={'acknowledged':True,'control_epoch':epoch,'snapshot_hash':digest(snapshot(project))}
  with patch.object(f0,'get_conn',self.connection),patch.object(f0.ledger,'_trials',return_value=[]),patch.object(f0.service,'control_status',return_value={'paused':False}),patch.object(f0,'published_view',return_value={'view_id':'view'}),patch('services.quant_factor.resources.require_config'),patch.object(f0,'_record',side_effect=RuntimeError('after control update')),patch.object(f0.POOL,'submit') as schedule,self.assertRaises(RuntimeError):f0.start(self.uid,self.org,'topic',branch['id'],'rollback',handoff)
  schedule.assert_not_called();self.assertEqual(self.project()['config']['v5ControlEpoch'],epoch)
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_f0_runs').fetchone()['n'],0)

 def test_parallel_manual_saves_same_epoch_allow_exactly_one(self):
  import threading
  from concurrent.futures import ThreadPoolExecutor
  branch=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True);payload=self.project();barrier=threading.Barrier(2)
  def save(_):
   barrier.wait(timeout=2)
   try:return presentation.save_workbench(self.uid,self.org,'project',payload)['ok']
   except ValueError as exc:self.assertIn('控制版本',str(exc));return False
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,[1,2]))
  self.assertEqual(sorted(results),[False,True])

 def test_old_f3_pending_takeover_save_and_late_ready_does_not_block_or_overwrite(self):
  with self.connection() as c:c.execute("INSERT INTO quant_factor_agent_jobs(id,user_id,org_id,project_id,status) VALUES('old-f3',%s,%s,'project','running')",(self.uid,self.org))
  ledger.set_topic_status(self.uid,self.org,'topic','paused');branch=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True)
  payload=self.project();payload['description']='人工已明确修改';saved=presentation.save_workbench(self.uid,self.org,'project',payload)
  self.assertFalse(agent_jobs.update(self.uid,self.org,'old-f3','ready',{'action':'ready'},{'fields':{'name':'late_old_model','code':'old'}}))
  self.assertEqual(self.project()['description'],'人工已明确修改')
  with self.connection() as c:
   old=c.execute("SELECT status,output FROM quant_factor_agent_jobs WHERE id='old-f3'").fetchone();self.assertEqual(old['status'],'cancelled');self.assertEqual(old['output']['fields']['name'],'late_old_model')
   c.execute("INSERT INTO quant_factor_agent_jobs(id,user_id,org_id,project_id,status) VALUES('new-f3',%s,%s,'project','running')",(self.uid,self.org))
  with self.assertRaisesRegex(ValueError,'仍有研究'):presentation.save_workbench(self.uid,self.org,'project',saved['project'])

 def test_stale_takeover_cas_does_not_replace_new_manual_branch(self):
  epoch=self.project()['config']['v5ControlEpoch'];first=ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True,epoch)
  with self.assertRaisesRegex(ValueError,'控制版本'):ledger.takeover_branch(self.uid,self.org,'topic','branch','candidate',True,epoch)
  self.assertEqual(self.project()['config']['v5ActiveBranch'],first['id'])
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_branches').fetchone()['n'],2)
