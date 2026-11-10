import copy,hashlib,json,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from services.quant_factor.causality import diagnose_source,diagnostic_scope,FIXTURE_VERSION
from services.quant_factor import f0_agent,research_method
ROOT=Path(__file__).resolve().parents[2]
SOURCE=(Path(__file__).parent/'fixtures/cr101_cross_section_20.py.txt').read_text()

class ScopeTests(unittest.TestCase):
 def test_real_generated_code_8_column_probe_reports_diagnostic_coverage_not_market_failure(self):
  with self.assertRaisesRegex(ValueError,'合成诊断覆盖不足.*640行/8证券') as error:
   diagnose_source(SOURCE,'f0_factor',scope=diagnostic_scope())
  self.assertIn('不是实际行情不足或研究不成立',str(error.exception))
 def test_exact_generated_code_passes_frozen_40_scope_and_real_re_prefix_checks(self):
  contract={'data_identity':{'universe':['synthetic_'+str(i) for i in range(40)]}}
  checked=diagnose_source(SOURCE,'f0_factor',scope=diagnostic_scope(contract))
  self.assertTrue(checked['diagnostic']['passed']);self.assertEqual(checked['diagnostic']['columns'],40)
  self.assertEqual(checked['diagnostic']['cutoff_rows'],[560,600]);self.assertEqual(checked['fixture_version'],FIXTURE_VERSION)
  self.assertEqual(checked['diagnostic']['fixture'],FIXTURE_VERSION)
  self.assertEqual(checked['contract']['source_sha256'],hashlib.sha256(SOURCE.encode()).hexdigest())
  self.assertEqual(checked['diagnostic']['actual_re_source_hash'],checked['contract']['wrapped_source_sha256'])
 def test_checker_and_fixture_are_versioned_and_scope_is_cache_identity(self):
  self.assertTrue({'causality.py','causality_worker.py'}<=set(research_method.METHOD_FILES))
  self.assertIn('scoped-diagnostic-r4',research_method.snapshot()['revision'])
  source='def f(self): return self.close'
  with patch('services.quant_factor.causality._diagnose_cached',return_value={}) as cached:
   diagnose_source(source,'f',scope=diagnostic_scope())
   diagnose_source(source,'f',scope=diagnostic_scope({'data_identity':{'universe':['a','b']}}))
  self.assertNotEqual(cached.call_args_list[0].args,cached.call_args_list[1].args)
 def test_completed_planner_progress_is_bound_to_captured_worker_epoch(self):
  proposal=research_method.Proposal(action='run_test',hypothesis='causal research',mechanism='mechanism',required_fields=['close'],change_scope='',expected_effect='positive',falsification='test',evidence_refs=[],rationale='selected frozen context',title='test',stop_reason='')
  ctx={'method_version':'bounded-factor-rd-v2','runner_epoch':'captured-old-worker'}
  with patch.object(f0_agent,'_context',return_value=ctx),patch.object(f0_agent,'_phase'),patch('services.quant_factor.research_method.plan',return_value=(proposal,{'parent_branch_id':'h'},{})),patch.object(f0_agent,'record_progress') as progress:
   f0_agent.decide(7,9,{'project_id':'p'},'run')
  self.assertEqual(progress.call_args.kwargs['worker_epoch'],'captured-old-worker')
 def test_progress_survives_empty_steps_and_rejects_late_worker(self):
  row={'status':'running','decision':{'runner_epoch':'epoch','steps':[]}}
  class Result:
   def fetchone(self):return copy.deepcopy(row)
  class Connection:
   def execute(self,sql,params):
    if sql.startswith('SELECT'):return Result()
    row['decision']['progress_events']=json.loads(params[0]);return Result()
  @contextmanager
  def connection():yield Connection()
  with patch.object(f0_agent,'get_conn',connection):
   for action in ('planning_completed','implementation_generated','implementation_check_failed'):
    self.assertTrue(f0_agent.record_progress(7,9,'run',action,worker_epoch='epoch',references={'job_id':'job','raw_reasoning':'DO NOT STORE'}))
   self.assertFalse(f0_agent.record_progress(7,9,'run','implementation_checked',worker_epoch='old'))
  self.assertEqual(row['decision']['steps'],[])
  self.assertEqual(len(row['decision']['progress_events']),3)
  self.assertNotIn('DO NOT STORE',json.dumps(row))
  row['status']='stopped'
  self.assertEqual([e['action'] for e in row['decision']['progress_events']],['planning_completed','implementation_generated','implementation_check_failed'])

if __name__=='__main__':unittest.main()
