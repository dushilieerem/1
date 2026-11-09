"""RealPG own schema/high actors. Synthetic grants never touch live org261."""
import json,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from services.quant_factor import model_budget as b
from services.quant_factor.policy import WorkflowError
from tests.test_quant_factor_assets_pg import IsolatedAssetPostgresTests

class IsolatedBudgetPostgresTests(IsolatedAssetPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  with cls.connection() as c:
   c.execute('CREATE TABLE users(id bigint PRIMARY KEY,ai_quota_daily int)');c.execute('CREATE TABLE inst_orgs(id bigint PRIMARY KEY)')
   c.execute('CREATE TABLE ai_usage(id bigserial,user_id bigint,run_id text,skill text,tokens_in int,tokens_out int,created_at timestamptz DEFAULT now())')
   c.execute((Path(__file__).parents[1]/'migrations/0038_quant_ai_budget.sql').read_text())
 def setUp(self):
  super().setUp()
  with self.connection() as c:
   c.execute('TRUNCATE quant_ai_budget_calls,quant_ai_budget_supplements,quant_ai_budget_accounts,ai_usage,users,inst_orgs CASCADE')
   c.execute('INSERT INTO users VALUES(%s,200),(%s,200)',(self.uid,self.reviewer));c.execute('INSERT INTO inst_orgs VALUES(%s)',(self.org,))
   c.execute("INSERT INTO quant_ai_budget_supplements(id,org_id,authorized_by,module,research_scope,limit_tokens,purpose,authorization_reference,authorization_hash,status) VALUES('fixture-grant',%s,%s,'factor','isolated-test',10000,'synthetic only','fixture','fixture','authorized')",(self.org,self.uid))
  guard=patch.object(b,'get_conn',self.connection);guard.start();self.addCleanup(guard.stop)
 def reserve(self,key='same',uid=None,org=None):return b.reserve(uid or self.uid,org or self.org,'project',key,'quant.factor.research_assistant','fixed-'+key,100,3000)
 def test_durable_reservation_replay_after_lost_response_is_one_charge(self):
  first=self.reserve();second=self.reserve();self.assertEqual(first['id'],second['id'])
  with self.connection() as c:self.assertEqual(b._charge_sum(c,self.org,'fixture-grant'),3100)
 def test_parallel_reservations_cannot_overspend_one_org_pool(self):
  with self.connection() as c:c.execute('UPDATE quant_ai_budget_supplements SET limit_tokens=4000')
  barrier=threading.Barrier(2)
  def reserve(key):
   barrier.wait(timeout=2)
   try:return bool(self.reserve(key))
   except WorkflowError as exc:self.assertIn('额度不足',str(exc));return False
  with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(reserve,['a','b']))
  self.assertEqual(sorted(out),[False,True])
 def test_members_share_one_pool_but_other_org_cannot_inherit(self):
  self.reserve('researcher');self.reserve('reviewer',uid=self.reviewer)
  with self.connection() as c:self.assertEqual(b._charge_sum(c,self.org,'fixture-grant'),6200)
  with self.assertRaisesRegex(WorkflowError,'历史模型用量尚待核对'):self.reserve('foreign',org=self.org+1)
 def test_claim_is_atomic_and_account_call_count_preserved(self):
  row=self.reserve();barrier=threading.Barrier(2)
  def claim(_):barrier.wait(timeout=2);return b.claim(self.uid,self.org,row['id'])
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,[1,2]))
  self.assertEqual(sorted(results),[False,True])
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) n FROM ai_usage').fetchone()['n'],1)
 def test_provider_total_settlement_and_replay_are_not_double_charged(self):
  row=self.reserve();self.assertTrue(b.claim(self.uid,self.org,row['id']))
  output={'content':'response','usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':123}}
  b.settle(self.uid,self.org,row['id'],output);b.settle(self.uid,self.org,row['id'],output)
  with self.connection() as c:self.assertEqual(b._charge_sum(c,self.org,'fixture-grant'),123)
  self.assertEqual(self.reserve()['response']['content'],'response')
 def test_timeout_and_missing_usage_keep_full_reservation(self):
  first=self.reserve('timeout');b.claim(self.uid,self.org,first['id']);b.unresolved(self.uid,self.org,first['id'],'timeout')
  second=self.reserve('no-usage');b.claim(self.uid,self.org,second['id']);b.settle(self.uid,self.org,second['id'],{'content':'answer without usage'})
  with self.connection() as c:self.assertEqual(b._charge_sum(c,self.org,'fixture-grant'),6200)
  self.assertEqual(self.reserve('timeout')['status'],'unresolved');self.assertEqual(self.reserve('no-usage')['status'],'unresolved')
 def test_old_baseline_unknown_blocks_without_grant_even_with_known_lower_bound(self):
  with self.connection() as c:
   c.execute('DELETE FROM quant_ai_budget_supplements')
   c.execute("INSERT INTO quant_ai_budget_accounts(org_id,scope,limit_tokens,baseline_state,historical_tokens,unknown_history) VALUES(%s,'space',1000000,'pending',180331,'{\"unknown\":true}'),(%s,'factor',200000,'pending',180331,'{\"unknown\":true}')",(self.org,self.org))
  with self.assertRaisesRegex(WorkflowError,'历史模型用量尚待核对'):self.reserve()
 def test_account_daily_limit_is_not_expanded_by_grant(self):
  row=self.reserve()
  with self.connection() as c:c.execute('UPDATE users SET ai_quota_daily=0 WHERE id=%s',(self.uid,))
  with self.assertRaisesRegex(WorkflowError,'账号模型调用次数'):b.claim(self.uid,self.org,row['id'])
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) n FROM ai_usage').fetchone()['n'],0)

 def test_real_runner_persists_response_then_replays_without_second_physical_request(self):
  import io
  from types import SimpleNamespace
  from ai.router.specs import TaskSpec
  from ai.gateway import providers
  raw={'choices':[{'message':{'content':'fixture answer'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}
  target=SimpleNamespace(model='fixture',provider='fixture',base_url='http://fixture.invalid',timeout=10)
  with patch('ai.router.get_task',return_value=TaskSpec(task_id='quant.factor.research_assistant')),patch.object(providers,'resolve_target',return_value=target),patch.object(providers,'_post',side_effect=lambda *a,**k:io.BytesIO(json.dumps(raw).encode())) as post,patch.object(providers,'complete',side_effect=AssertionError('forbidden')):
   first=b.run(self.uid,self.org,'project','stable-operation','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}]);again=b.run(self.uid,self.org,'project','stable-operation','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}])
  self.assertEqual(first,again);post.assert_called_once()
  with self.connection() as c:self.assertEqual(b._charge_sum(c,self.org,'fixture-grant'),30);self.assertEqual(c.execute('SELECT COUNT(*) n FROM ai_usage').fetchone()['n'],1)
 def test_real_runner_lost_response_cannot_automatically_resubmit(self):
  from types import SimpleNamespace
  from ai.router.specs import TaskSpec
  from ai.gateway import providers
  target=SimpleNamespace(model='fixture',provider='fixture',base_url='http://fixture.invalid',timeout=10)
  with patch('ai.router.get_task',return_value=TaskSpec(task_id='quant.factor.research_assistant')),patch.object(providers,'resolve_target',return_value=target),patch.object(providers,'_post',side_effect=TimeoutError('fixture ack lost')) as post:
   with self.assertRaisesRegex(WorkflowError,'TimeoutError'):b.run(self.uid,self.org,'project','lost-operation','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}])
   with self.assertRaisesRegex(WorkflowError,'原模型提交结果尚待核对'):b.run(self.uid,self.org,'project','lost-operation','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}])
  post.assert_called_once()
  with self.connection() as c:self.assertGreater(b._charge_sum(c,self.org,'fixture-grant'),3000)

 def test_settled_receipt_cannot_be_replaced_with_different_usage(self):
  row=self.reserve();b.claim(self.uid,self.org,row['id']);b.settle(self.uid,self.org,row['id'],{'content':'a','usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}})
  with self.assertRaisesRegex(WorkflowError,'不可替换'):b.settle(self.uid,self.org,row['id'],{'content':'different','usage':{'prompt_tokens':1,'completion_tokens':2,'total_tokens':3}})
  with self.connection() as c:self.assertEqual(b._charge_sum(c,self.org,'fixture-grant'),30)
 def test_authorization_activation_same_org_scope_is_one_pool_without_resetting_spend(self):
  record=Path(__file__).parents[2]/'institutional-workflow/runtime/verification/pm-cr099-20261109/research-budget-authorization.json'
  with patch.object(b,'AUTHORIZED_ORG',self.org):
   first=b.install_authorization(self.org,self.uid,record);self.reserve('after-grant');again=b.install_authorization(self.org,self.reviewer,record)
  self.assertEqual(first['id'],again['id']);self.assertEqual(first['authorized_by'],self.uid)
  with self.connection() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) n FROM quant_ai_budget_supplements WHERE research_scope='institutional_quant.factor_research.20261109'").fetchone()['n'],1)
   self.assertEqual(b._charge_sum(c,self.org,first['id']),3100)
