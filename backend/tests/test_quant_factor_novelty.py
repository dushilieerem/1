import unittest
import copy
from unittest import TestCase
from unittest.mock import patch
from services.quant_factor.asset_context import code_identity,duplicate_matches,planner_context
from services.quant_factor.novelty_policy import DEFAULTS,policy,evaluate_comparison,handoff_allowed
from services.quant_factor.policy import WorkflowError

class NoveltyTests(TestCase):
 def rules(self):return policy({'researchPurpose':'discovery','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS}})
 def result(self):return {'expected_count':1,'meta':{'data_release_id':'r','candidate_source_hash':'c','spec_hash':'s'},'comparisons':[{'reference_id':'lib:f','status':'succeeded','mean_abs_spearman':.2,'valid_days':120,'min_pairs':200,'coverage':.95}]}
 def test_rename_comment_and_local_name_do_not_evade_duplicate(self):
  a='def a(self):\n    x=self.close.shift(1)\n    return self.close / x - 1'
  b='def other(self):\n    """different description"""\n    prior=self.close.shift(1)\n    return self.close / prior - 1'
  self.assertEqual(code_identity(a),code_identity(b))
  self.assertEqual(len(duplicate_matches(b,{'owned':[{'factor_code':a,'factor_name':'a','source_id':'u:1','library_name':'mine'}]})),1)
 def test_different_formula_not_claimed_identical(self):
  self.assertNotEqual(code_identity('def f(self): return self.close.shift(1)'),code_identity('def f(self): return self.close.shift(2)'))
 def test_syntax_error_is_not_executed(self):self.assertIsNone(code_identity('raise SystemExit()'))
 def test_valid_full_comparison_passes(self):
  r=evaluate_comparison(self.result(),self.rules(),'r','c');self.assertTrue(r['passed']);self.assertTrue(r['complete'])
 def test_equivalent_or_opposite_factor_fails(self):
  r=self.result();r['comparisons'][0]['mean_abs_spearman']=1
  out=evaluate_comparison(r,self.rules(),'r','c');self.assertFalse(out['passed']);self.assertEqual(out['status'],'failed')
 def test_missing_comparison_never_passes(self):
  r=self.result();r['expected_count']=2
  self.assertEqual(evaluate_comparison(r,self.rules(),'r','c')['status'],'incomplete')
 def test_duplicate_references_do_not_count_twice(self):
  r=self.result();r['expected_count']=2;r['comparisons']*=2
  self.assertFalse(evaluate_comparison(r,self.rules(),'r','c')['complete'])
 def test_insufficient_days_pairs_coverage_or_nan_blocks(self):
  for k,v in [('valid_days',3),('min_pairs',2),('coverage',.1),('mean_abs_spearman',float('nan'))]:
   with self.subTest(k=k):
    r=self.result();r['comparisons'][0][k]=v;self.assertFalse(evaluate_comparison(r,self.rules(),'r','c')['passed'])
 def test_missing_evidence_or_identity_mismatch_blocks(self):
  for key in ('data_release_id','candidate_source_hash','spec_hash'):
   r=self.result();r['meta'].pop(key)
   with self.subTest(k=key),self.assertRaises(WorkflowError):evaluate_comparison(r,self.rules(),'r','c')
 def test_invalid_policy_rejected(self):
  for k,v in [('maxAbsCorrelation',1),('minDays',2.5),('minPairs',True),('minCoverage',0)]:
   with self.subTest(k=k),self.assertRaises(WorkflowError):policy({'researchPurpose':'discovery','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS,k:v}})
 def test_old_and_replication_not_labeled_new(self):
  for purpose in ('legacy','replication',None):
   self.assertFalse(handoff_allowed({'snapshot':{'plan':{'researchPurpose':purpose}}}))
 def test_full_library_metadata_reaches_planner(self):
  refs={'scope':'visible','count':2,'hash':'h','builtins':[{'library_name':'l','factor_name':'f','description':'existing reversal'}],'owned':[{'source_id':'u:1','factor_name':'x','description':'my definition','factor_code':'def x(self): return self.close'}]}
  ctx=planner_context(refs);self.assertEqual(len(ctx['references']),2);self.assertIn('existing reversal',str(ctx));self.assertIn('my definition',str(ctx))

class NoveltyIntegrationBoundaryTests(TestCase):
 def test_known_duplicate_rejects_even_if_another_reference_is_missing(self):
  base=NoveltyTests();r=base.result();r['expected_count']=2;r['comparisons'][0]['mean_abs_spearman']=1
  gate=evaluate_comparison(r,base.rules(),'r','c')
  self.assertEqual(gate['status'],'failed');self.assertFalse(gate['complete']);self.assertFalse(gate['passed'])
 def test_fractional_day_counts_never_pass(self):
  base=NoveltyTests();r=base.result();r['comparisons'][0]['valid_days']=120.5
  self.assertFalse(evaluate_comparison(r,base.rules(),'r','c')['passed'])
 def test_manifest_identity_rejects_substitution_and_source_hash_change(self):
  from services.quant_factor.novelty import validate_result
  from services.quant_factor.policy import digest
  payload={'references':[{'reference_id':'a'}]};dev={'meta':{'spec_hash':'s'}}
  row={'reference_id':'a','source_hash':'code','status':'succeeded'}
  result={'expected_count':1,'comparisons':[row],'meta':{'request_hash':digest(payload),'candidate_backtest_spec_hash':'s','reference_source_hash':digest([('a','code')])}}
  validate_result(result,payload,dev)
  for mutate in [lambda r:r['comparisons'][0].update(reference_id='b'),lambda r:r['meta'].update(candidate_backtest_spec_hash='other'),lambda r:r['comparisons'][0].update(source_hash=None)]:
   bad=copy.deepcopy(result);mutate(bad)
   with self.assertRaises(WorkflowError):validate_result(bad,payload,dev)
 def test_exact_definition_rejected_without_calling_compute(self):
  from services.quant_factor.novelty import assess
  source='def x(self): return self.close.shift(1)'
  refs={'hash':'frozen','count':1,'scope':'owned','builtins':[],'owned':[{'factor_code':source,'factor_name':'x','source_id':'u:1','library_name':'mine'}]}
  with patch('services.quant_factor.novelty.request_json') as http:
   out=assess(1,{'plan':{'researchPurpose':'discovery','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS}},'request':{'factor_code':source}},{},refs)
  self.assertEqual(out['status'],'failed');http.assert_not_called()
 def test_retry_reuses_original_development_report_and_never_backtests(self):
  from services.quant_factor import service
  from unittest.mock import MagicMock
  data={'report_id':'unchanged','result':{'meta':{'data_release_id':'old'}},'gate':{'passed':False,'numerical_passed':True},'novelty':{'status':'unavailable'}}
  row={'snapshot':{},'evidence':{'development':data,'library_reference':{'hash':'frozen'}}}
  with patch.object(service.store,'read',return_value=row),patch.object(service,'_compare_library',return_value={'status':'passed','message':'ok','gate':{'passed':True}}) as compare,patch.object(service.store,'update') as update,patch.object(service,'proxy_submit_factor_backtest') as bt:
   service._retry_novelty(1,2,'c')
  bt.assert_not_called();self.assertEqual(compare.call_args.args[3],row)
  saved=update.call_args.args[-1]['development'];self.assertEqual(saved['report_id'],'unchanged');self.assertEqual(saved['result'],data['result']);self.assertTrue(saved['gate']['passed'])
 def test_retry_foreign_candidate_is_unavailable(self):
  from services.quant_factor import service
  from unittest.mock import MagicMock
  c=MagicMock();c.execute.return_value.fetchone.return_value=None;conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(service,'get_conn',return_value=conn),patch.object(service.POOL,'submit') as pool:
   with self.assertRaises(KeyError):service.retry_novelty(1,2,'foreign')
  self.assertEqual(c.execute.call_args.args[1],('foreign',1,2));pool.assert_not_called()

class HandoffEvidenceTests(TestCase):
 def test_comparison_payload_does_not_copy_verified_token(self):
  from services.quant_factor.novelty import comparison_request
  snapshot={'plan':{'developmentStart':'2025-01-01','developmentEnd':'2025-06-30','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS}},'request':{'factor_name':'f'}}
  development={'meta':{'data_release_id':'r','factor_source_hash':'c','spec_hash':'s'},'result':{'_svquant_verified_token':'do-not-copy','metrics':{'rank_ic':.03}}}
  refs={'builtins':[{'library_name':'lib','factor_name':'known'}],'owned':[]}
  payload=comparison_request(snapshot,development,refs,{'minPairs':30})
  self.assertNotIn('do-not-copy',repr(payload));self.assertNotIn('_svquant_verified_token',payload)

 def test_residual_rank_ic_is_never_fabricated_or_passed_through(self):
  result={'expected_count':1,'meta':{'data_release_id':'r','candidate_source_hash':'c','spec_hash':'s'},'residual_rank_ic':.5,
          'comparisons':[{'reference_id':'lib:f','status':'succeeded','mean_abs_spearman':.2,'valid_days':120,'min_pairs':200,'coverage':.95}]}
  rules=policy({'researchPurpose':'discovery','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS}})
  out=evaluate_comparison(result,rules,'r','c')
  self.assertEqual(out['residual'],{'status':'not_supported'})
  self.assertNotIn('residual_rank_ic',out)


class ThresholdBoundaryTest(unittest.TestCase):
 def test_default_threshold_is_070(self):
  self.assertEqual(DEFAULTS['maxAbsCorrelation'],.7)
 def test_equal_threshold_is_duplicate(self):
  rules=policy({'researchPurpose':'discovery','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS}})
  result={'meta':{'data_release_id':'r','candidate_source_hash':'c','spec_hash':'s'},'expected_count':1,
          'comparisons':[{'reference_id':'r','status':'succeeded','mean_abs_spearman':.7,'valid_days':100,'min_pairs':200,'coverage':.95}]}
  out=evaluate_comparison(result,rules,'r','c')
  self.assertFalse(out['passed']);self.assertEqual(out['status'],'failed')
