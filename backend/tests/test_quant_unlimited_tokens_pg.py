"""Opt-in own-schema checks of unlimited authorization without a model/network call."""
import json,uuid
from pathlib import Path
from unittest.mock import patch
from services.quant_factor import token_policy as t,model_budget as b
from services.quant_factor.policy import WorkflowError
from tests.test_quant_model_budget_pg import IsolatedBudgetPostgresTests

class IsolatedUnlimitedTests(IsolatedBudgetPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  try:
   with cls.connection() as c:
    c.execute((Path(__file__).parents[1]/'migrations/0039_quant_research_token_policy.sql').read_text())
    c.execute('CREATE TABLE inst_members(id bigserial,org_id bigint,user_id bigint,status text)')
  except BaseException:
   cls.tearDownClass();raise
 def setUp(self):
  super().setUp()
  with self.connection() as c:
   c.execute('TRUNCATE inst_members')
   c.execute("INSERT INTO inst_members(org_id,user_id,status) VALUES(%s,%s,'active'),(%s,%s,'active')",(self.org,self.uid,self.org,self.reviewer))
  guard=patch.object(t,'get_conn',self.connection);guard.start();self.addCleanup(guard.stop)
  guard=patch.object(t,'AUTHORIZED_ORG',self.org);guard.start();self.addCleanup(guard.stop)
  record=json.loads((Path(__file__).parents[2]/'institutional-workflow/runtime/verification/pm-cr101-20261110/token-policy-authorization.json').read_text())
  record['org_id']=self.org;record['supersedes_token_ceiling'].update(grant_id='fixture-grant',old_limit_tokens=10000)
  self.record=record
  self.file=Path(__file__).parents[2]/'institutional-workflow/runtime/verification/codex-factor-cr101-20261110'/('fixture-'+uuid.uuid4().hex+'.json')
  self.file.parent.mkdir(parents=True,exist_ok=True);self.file.write_text(json.dumps(record));self.addCleanup(self.file.unlink)
 def install(self,actor=None):return t.install(self.org,actor or self.uid,self.file)
 def test_unlimited_replay_preserves_old_grant_spend_and_unknown_history(self):
  old=self.reserve('old');b.claim(self.uid,self.org,old['id']);b.settle(self.uid,self.org,old['id'],{'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}})
  with self.connection() as c:
   c.execute("INSERT INTO quant_ai_budget_accounts(org_id,scope,limit_tokens,baseline_state,historical_tokens,unknown_history) VALUES(%s,'factor',200000,'pending',180331,%s::jsonb)",(self.org,json.dumps({'missing_calls':46})))
  first=self.install();again=self.install(self.reviewer);self.assertEqual(first['id'],again['id']);self.assertEqual(first['authorized_by'],self.uid)
  with self.connection() as c:
   c.execute('UPDATE quant_ai_budget_supplements SET limit_tokens=1') # An old exhausted grant cannot stop an explicit unlimited pool.
  new=self.reserve('new');self.assertEqual(new['token_policy_id'],first['id'])
  out=b.status(self.uid,self.org)
  self.assertEqual(out['token_limit_mode'],'unlimited');self.assertIsNone(out['cumulative_token_limit']);self.assertIsNone(out['new_authorization']['remaining_tokens'])
  self.assertEqual(out['usage']['settled_tokens'],300);self.assertEqual(out['usage']['held_tokens'],3100)
  self.assertEqual(out['legacy_accounts'][0]['historical_tokens'],180331);self.assertEqual(out['legacy_accounts'][0]['unknown_history']['missing_calls'],46)
  with self.connection() as c:self.assertEqual(c.execute('SELECT actual_tokens FROM quant_ai_budget_calls WHERE id=%s',(old['id'],)).fetchone()['actual_tokens'],300)
 def test_one_institution_pool_shared_actors_but_other_institution_is_not_authorized(self):
  self.install()
  with self.connection() as c:c.execute('UPDATE quant_ai_budget_supplements SET limit_tokens=1')
  self.reserve('member-a');self.reserve('member-b',uid=self.reviewer)
  with self.assertRaisesRegex(WorkflowError,'历史模型用量'):self.reserve('foreign',org=self.org+1)
 def test_unknown_current_usage_stays_unresolved_and_replay_cannot_resend(self):
  self.install();row=self.reserve('unknown');self.assertTrue(b.claim(self.uid,self.org,row['id']));b.unresolved(self.uid,self.org,row['id'],'lost receipt')
  again=self.reserve('unknown');self.assertEqual(again['id'],row['id']);self.assertEqual(again['status'],'unresolved');self.assertFalse(b.claim(self.uid,self.org,row['id']))
  out=b.status(self.uid,self.org);self.assertEqual(out['usage']['unresolved_calls'],1);self.assertEqual(out['usage']['held_tokens'],3100)
 def test_unlimited_and_legacy_daily_counter_do_not_block_token_governed_calls(self):
  self.install();row=self.reserve()
  with self.connection() as c:c.execute('UPDATE users SET ai_quota_daily=0 WHERE id=%s',(self.uid,))
  self.assertTrue(b.claim(self.uid,self.org,row['id']))
 def test_changed_authorization_is_rejected_and_original_event_remains(self):
  first=self.install();self.record['recorded_at_utc']='different';self.file.write_text(json.dumps(self.record))
  with self.assertRaisesRegex(WorkflowError,'不同的研究政策授权'):self.install()
  with self.connection() as c:self.assertEqual(t.current(c,self.org)['authorization_hash'],first['authorization_hash'])
 def test_without_new_authorization_old_finite_policy_still_blocks(self):
  with self.connection() as c:c.execute('UPDATE quant_ai_budget_supplements SET limit_tokens=1')
  with self.assertRaisesRegex(WorkflowError,'额度不足'):self.reserve()

 def test_closed_or_replaced_grant_is_waiting_not_a_status_crash_or_false_ready(self):
  self.install();row=self.reserve('old');b.claim(self.uid,self.org,row['id']);b.settle(self.uid,self.org,row['id'],{'usage':{'prompt_tokens':1,'completion_tokens':2,'total_tokens':3}})
  with self.connection() as c:c.execute("UPDATE quant_ai_budget_supplements SET status='closed'")
  out=b.status(self.uid,self.org);self.assertIsNone(out['new_authorization']);self.assertFalse(out['execution_ready']);self.assertEqual(out['policy_state'],'needs_confirmation');self.assertEqual(out['usage']['settled_tokens'],3)
  with self.assertRaisesRegex(WorkflowError,'身份不一致'):self.reserve('closed')
  with self.connection() as c:c.execute("INSERT INTO quant_ai_budget_supplements(id,org_id,authorized_by,module,research_scope,limit_tokens,purpose,authorization_reference,authorization_hash,status) VALUES('other',%s,%s,'factor','another-scope',99999,'fixture','fixture','another-hash','authorized')",(self.org,self.uid))
  out=b.status(self.uid,self.org);self.assertFalse(out['execution_ready']);self.assertEqual(out['policy_state'],'needs_confirmation');self.assertEqual(out['usage']['settled_tokens'],3)
  with self.assertRaisesRegex(WorkflowError,'身份不一致'):self.reserve('replaced')
