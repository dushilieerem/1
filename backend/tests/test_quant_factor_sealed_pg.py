"""Opt-in actual PG: same unique dev-only schema/high actors as existing integration fixture."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from contextlib import contextmanager
from services.quant_factor import sealed
from tests.test_quant_factor_assets_pg import IsolatedAssetPostgresTests

class IsolatedSealedPostgresTests(IsolatedAssetPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  with cls.connection() as c:
   c.execute('ALTER TABLE quant_factor_topics ADD COLUMN max_sealed int DEFAULT 1')
   c.execute("ALTER TABLE quant_factor_sealed_validations ADD COLUMN id text UNIQUE,ADD COLUMN project_id text,ADD COLUMN executor text,ADD COLUMN release_ids jsonb,ADD COLUMN view_manifest_sha256 text,ADD COLUMN contract_revision text,ADD COLUMN as_of timestamptz,ADD COLUMN trial_ids jsonb,ADD COLUMN evaluated_at timestamptz,ADD COLUMN updated_at timestamptz DEFAULT now()")
   c.execute('ALTER TABLE quant_factor_sealed_validations ADD UNIQUE(candidate_id)')
 def test_sealed_parallel_request_replays_same_row_even_at_full_budget(self):
  with self.connection() as c:c.execute('DELETE FROM quant_factor_sealed_validations')
  barrier=threading.Barrier(2);intent={'schema':sealed.INTENT_SCHEMA,'snapshot_hash':self.row['snapshot_hash']}
  def request(_):barrier.wait(timeout=2);return sealed.request(self.uid,self.org,'candidate')
  with patch.object(sealed,'get_conn',self.connection),patch.object(sealed,'_check_new',return_value=(intent,[{'id':'trial'}])),patch.object(sealed.POOL,'submit'),ThreadPoolExecutor(max_workers=2) as pool:
   rows=list(pool.map(request,[1,2]))
  self.assertEqual(rows[0]['id'],rows[1]['id'])
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM quant_factor_sealed_validations').fetchone()['n'],1)
 def test_sealed_intent_insert_rolls_back_on_response_before_commit_failure(self):
  with self.connection() as c:c.execute('DELETE FROM quant_factor_sealed_validations')
  class Failing:
   def __init__(self,c):self.c=c
   def execute(self,statement,*args):
    result=self.c.execute(statement,*args)
    if str(statement).startswith('INSERT INTO quant_factor_sealed_validations'):raise RuntimeError('injected after real insert before commit')
    return result
  @contextmanager
  def failing():
   with self.connection() as c:yield Failing(c)
  with patch.object(sealed,'get_conn',failing),patch.object(sealed,'_check_new',return_value=({'schema':sealed.INTENT_SCHEMA},[])),patch.object(sealed.POOL,'submit') as submit,self.assertRaises(RuntimeError):sealed.request(self.uid,self.org,'candidate')
  submit.assert_not_called()
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM quant_factor_sealed_validations').fetchone()['n'],0)
 def test_sealed_recovery_workers_claim_only_once(self):
  import time
  barrier=threading.Barrier(2);calls=[]
  def once(*args):calls.append(args);time.sleep(.15)
  def run(_):barrier.wait(timeout=2);sealed.run(self.uid,self.org,'isolated-seal')
  with patch.object(sealed,'get_conn',self.connection),patch.object(sealed,'_run_once',side_effect=once),ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,[1,2]))
  self.assertEqual(len(calls),1)
