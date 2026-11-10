"""Only explicit isolated development schema; actual advice transactions, no model/RE."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from psycopg.types.json import Jsonb
from tests.test_quant_research_method_pg import IsolatedResearchMethodPostgresTests
from services.quant_factor import research_advice as advice

class AdviceReceiptPostgresTests(IsolatedResearchMethodPostgresTests):
 def setUp(self):
  super().setUp();self.add_contract()
  guard=patch.object(advice,'get_conn',self.connection);guard.start();self.addCleanup(guard.stop)
  with self.connection() as c:
   c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision,created_at) VALUES('original-run',%s,%s,'project','topic','branch','run-key','running','{}',now()-interval '1 minute')",(self.uid,self.org))
  self.body={'request_key':'same-request','run_id':'original-run','branch_id':'branch','control_epoch':'original','candidate_id':'candidate','message':'保留方向，只比较既定窗口'}
 def test_commit_then_lost_response_replays_after_stop_and_new_run_without_rewrite(self):
  first=advice.submit(self.uid,self.org,'topic',self.body)
  with self.connection() as c:
   decision=c.execute("SELECT decision FROM quant_factor_f0_runs WHERE id='original-run'").fetchone()['decision'];decision['human_advice'][0].update(status='not_adopted',reason='未采用：研究已结束')
   c.execute("UPDATE quant_factor_f0_runs SET status='stopped',decision=%s WHERE id='original-run'",(Jsonb(decision),))
   c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision) VALUES('new-run',%s,%s,'project','topic','branch','new-key','running','{}')",(self.uid,self.org))
  replay=advice.submit(self.uid,self.org,'topic',self.body)
  self.assertEqual(first['id'],replay['id']);self.assertEqual(replay['run_id'],'original-run');self.assertEqual(replay['status'],'not_adopted')
  with self.connection() as c:self.assertEqual(c.execute("SELECT decision FROM quant_factor_f0_runs WHERE id='new-run'").fetchone()['decision'],{})
 def test_same_key_different_message_branch_epoch_or_run_is_conflict(self):
  first=advice.submit(self.uid,self.org,'topic',self.body)
  for delta in ({'message':'换成另一条建议'},{'branch_id':'other'},{'control_epoch':'new-epoch'},{'run_id':'other-run'}):
   with self.subTest(delta=delta),self.assertRaises(advice.AdviceRejected) as error:advice.submit(self.uid,self.org,'topic',{**self.body,**delta})
   self.assertEqual(error.exception.code,'advice_key_conflict')
  self.assertEqual(advice.submit(self.uid,self.org,'topic',self.body)['id'],first['id'])
 def test_permission_scope_and_new_run_same_branch_cannot_accept_old_target(self):
  advice.submit(self.uid,self.org,'topic',self.body)
  for identity in ((self.uid+9,self.org,'topic'),(self.uid,self.org+9,'topic'),(self.uid,self.org,'other-topic')):
   with self.subTest(identity=identity),self.assertRaises(KeyError):advice.submit(*identity,self.body)
  with self.connection() as c:
   c.execute("UPDATE quant_factor_f0_runs SET status='stopped' WHERE id='original-run'")
   c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision) VALUES('new-run',%s,%s,'project','topic','branch','new-key','running','{}')",(self.uid,self.org))
  with self.assertRaises(advice.AdviceRejected) as error:advice.submit(self.uid,self.org,'topic',{**self.body,'request_key':'new-input'})
  self.assertEqual(error.exception.code,'advice_target_changed')
 def test_branch_changed_is_definite_no_write_and_explicit_new_target_can_save_once(self):
  with self.connection() as c:
   cfg=self.project()['config'];cfg.update(v5ActiveBranch='revised-branch',v5ControlEpoch='revised-epoch')
   c.execute('UPDATE detect_projects SET config=%s',(Jsonb(cfg),))
  with self.assertRaises(advice.AdviceRejected) as error:advice.submit(self.uid,self.org,'topic',{**self.body,'candidate_id':None})
  self.assertEqual(error.exception.code,'advice_target_changed')
  with self.connection() as c:self.assertEqual(c.execute("SELECT decision FROM quant_factor_f0_runs WHERE id='original-run'").fetchone()['decision'],{})
  new={**self.body,'request_key':'confirmed-new-target','branch_id':'revised-branch','control_epoch':'revised-epoch','candidate_id':None}
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:advice.submit(self.uid,self.org,'topic',new),range(2)))
  self.assertEqual(results[0]['id'],results[1]['id'])
  self.assertEqual(results[0]['status'],'pending')
