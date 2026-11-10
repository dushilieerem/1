"""Actual PG checks in an owned schema/high actors; all market/model inputs synthetic."""
import copy,json
from unittest.mock import patch
from psycopg.types.json import Jsonb
from tests.test_quant_factor_handoff_pg import IsolatedHandoffPostgresTests
from services.quant_factor import research_contract as rc,research_advice as advice,presentation
from services.factor import detect_store

class IsolatedResearchMethodPostgresTests(IsolatedHandoffPostgresTests):
 def add_contract(self):
  project=self.project();cfg=project['config'];plan=cfg['researchPlan']
  contract=rc.freeze(data_fields=rc.OHLCV,engine_fields=rc.OHLCV,requested_fields=None,rules=plan['rules'],
   data_identity={'project_id':'project','org_id':self.org,'view_id':'view','universe':cfg.get('researchUniverseSymbols') or cfg.get('universe'),'development':[plan['developmentStart'],plan['developmentEnd']],'validation':[plan['validationStart'],plan['validationEnd']]},method_identity={'version':rc.METHOD_VERSION})
  cfg['researchPlan']['researchContract']=contract
  with self.connection() as c:c.execute('UPDATE detect_projects SET config=%s',(Jsonb(cfg),))
  return contract
 def test_generic_removal_and_recomputed_contract_rollback(self):
  contract=self.add_contract();before=self.project()
  for incoming in ({}, {'researchPlan':{'researchContract':{**contract,'contract_hash':'recomputed'}}}):
   with patch.object(detect_store,'get_conn',self.connection),self.assertRaisesRegex(ValueError,'通用工程入口'):
    detect_store.upsert_project(self.uid,{'id':'project','config':incoming})
   self.assertEqual(self.project()['config'],before['config'])
 def test_quant_save_requires_same_server_contract(self):
  self.add_contract();payload=self.project()
  with self.connection() as c:c.execute("UPDATE quant_factor_trials SET branch_id='old-frozen-branch'")
  for mutation in ('remove','recompute','cross-project'):
   changed=copy.deepcopy(payload);plan=changed['config']['researchPlan']
   if mutation=='remove':plan.pop('researchContract')
   else:
    plan['researchContract']['data_identity']['project_id']='other' if mutation=='cross-project' else 'project'
    plan['researchContract']['allowed_fields'].append('turnover')
    plan['researchContract']['contract_hash']=rc.fingerprint({k:v for k,v in plan['researchContract'].items() if k!='contract_hash'})
   with self.assertRaisesRegex(ValueError,'契约不可覆盖'):presentation.save_workbench(self.uid,self.org,'project',changed)
  self.assertEqual(self.project()['config'],payload['config'])
 def test_advice_response_loss_idempotent_and_stale_target_rejected(self):
  self.add_contract()
  with self.connection() as c:c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision) VALUES('method-run',%s,%s,'project','topic','branch','method','running','{}')",(self.uid,self.org))
  body={'message':'保持既定方向，只比较过去窗口','request_key':'stable-advice','branch_id':'branch','control_epoch':'original','candidate_id':'candidate'}
  with patch.object(advice,'get_conn',self.connection):
   first=advice.submit(self.uid,self.org,'topic',body);again=advice.submit(self.uid,self.org,'topic',body)
   self.assertEqual(first['id'],again['id'])
   with self.assertRaises(advice.AdviceRejected) as conflict:advice.submit(self.uid,self.org,'topic',{**body,'message':'changed message'})
   self.assertEqual(conflict.exception.code,'advice_key_conflict')
   with self.assertRaises(advice.AdviceRejected) as stale:advice.submit(self.uid,self.org,'topic',{**body,'request_key':'new-advice','control_epoch':'stale'})
   self.assertEqual(stale.exception.code,'advice_target_changed')
  with self.connection() as c:
   saved=c.execute("SELECT decision FROM quant_factor_f0_runs WHERE id='method-run'").fetchone()['decision'];self.assertEqual(len(saved['human_advice']),1);self.assertEqual(saved['human_advice'][0]['status'],'pending')


from tests.test_quant_factor_assets_pg import IsolatedAssetPostgresTests
from services.quant_factor import ledger,f0,repo
class IsolatedNewResearchPostgresTests(IsolatedAssetPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  with cls.connection() as c:
   c.execute("ALTER TABLE detect_projects ADD COLUMN description text DEFAULT '',ADD COLUMN updated_at timestamptz DEFAULT now()")
   c.execute("ALTER TABLE quant_factor_topics ADD COLUMN release_id text,ADD COLUMN release_ids jsonb,ADD COLUMN view_manifest_sha256 text,ADD COLUMN contract_revision text,ADD COLUMN as_of date,ADD COLUMN development_start date,ADD COLUMN development_end date,ADD COLUMN validation_start date,ADD COLUMN validation_end date,ADD COLUMN max_sealed int,ADD COLUMN display_no int,ADD COLUMN updated_at timestamptz DEFAULT now()")
   c.execute("ALTER TABLE quant_factor_topics ALTER COLUMN status SET DEFAULT 'active'")
   c.execute("ALTER TABLE quant_factor_branches ADD COLUMN source text,ADD COLUMN owner_id bigint,ADD COLUMN hypothesis_version int,ADD COLUMN implementation_version int,ADD COLUMN title text")
 def setUp(self):
  self.config={'universe':'CSI500','factorCodes':[],'researchUniverseSymbols':['000001.SZ'], 'researchPlan':{'revision':'new','hypothesis':'仅用OHLCV检验过去价格与量能','acceptance':'事前固定门槛','fieldRestriction':'ohlcv','developmentStart':'2025-07-01','developmentEnd':'2025-09-30','validationStart':'2026-06-22','validationEnd':'2026-09-21','maxTrials':2,'rules':{'direction':'positive','icMetric':'rank_ic','minSignedIc':.005,'maxDrawdown':.5,'minObservations':60}}}
  with self.connection() as c:c.execute('INSERT INTO detect_projects(user_id,id,name,factor_name,config) VALUES(%s,%s,%s,%s,%s)',(self.uid,'new-project','new research','custom_combo',Jsonb(self.config)))
  for module in (ledger,f0,repo,advice):
   guard=patch.object(module,'get_conn',self.connection);guard.start();self.addCleanup(guard.stop)
 def project(self):
  with self.connection() as c:return detect_store._row_project(c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s',(self.uid,'new-project')).fetchone())
 def test_new_topic_freezes_h1_epoch_then_start_and_human_advice(self):
  view={'view_id':'view','manifest_sha256':'manifest','datasets':{'daily_bars':{'release':'frozen-release','sha256':'daily-sha'}}}
  meta={'published':True,'publication_version':'view','catalog_version':'view','fields':[{'name':name} for name in rc.OHLCV]}
  body={'view_id':'view','view_manifest_sha256':'manifest','release_id':'frozen-release','primary_holding_period':1,'max_trials':2,'max_sealed':1,'policy_version':'v5-p0','development_start':'2025-07-01','development_end':'2025-09-30','validation_start':'2026-06-22','validation_end':'2026-09-21'}
  with patch('services.workflow_workspace.platform_data.published_view',return_value=view),patch('services.quant_data_resources.dataset',return_value=meta):created=ledger.create_topic(self.uid,self.org,'new-project',body)
  topic=created['topic'];project=self.project();cfg=project['config'];self.assertTrue(cfg['v5ControlEpoch']);self.assertTrue(cfg['v5ActiveBranch']);self.assertEqual(cfg['researchPlan']['researchContract']['allowed_fields'],sorted(rc.OHLCV))
  with patch('services.factor.detect_store.get_project',side_effect=lambda uid,pid:{'project':self.project()}),patch.object(f0,'published_view',return_value=view),patch.object(f0.service,'control_status',return_value={'paused':False}),patch('services.quant_factor.resources.require_config'),patch.object(f0.POOL,'submit') as queue:
   run=f0.start(self.uid,self.org,topic['id'],cfg['v5ActiveBranch'],'new-run')
  self.assertEqual(run['decision']['method_version'],rc.METHOD_VERSION);queue.assert_called_once()
  item=advice.submit(self.uid,self.org,topic['id'],{'request_key':'first-opinion','branch_id':cfg['v5ActiveBranch'],'control_epoch':cfg['v5ControlEpoch'],'candidate_id':None,'message':'先检验短回看方案，不扩大评分窗'})
  self.assertEqual(item['status'],'pending');ledger.set_topic_status(self.uid,self.org,topic['id'],'paused')
  with self.connection() as c:
   stored=c.execute('SELECT decision FROM quant_factor_f0_runs WHERE id=%s',(run['id'],)).fetchone()['decision']
  self.assertEqual(stored['human_advice'][0]['status'],'not_adopted');self.assertIn('控制版本已变化',stored['human_advice'][0]['reason'])
