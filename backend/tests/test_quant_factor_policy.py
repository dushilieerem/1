import copy
import math
import unittest
from services.quant_factor.policy import snapshot,digest,evaluate,compare_identity,WorkflowError

def project():
 return {'id':'p','name':'研究','config':{'factorCodes':['momentum'],'draftFactor':{'name':'momentum','body':'def momentum(self):\n    return self.close.pct_change(20)'},'executionTiming':'next_open','researchPlan':{'revision':'r1','hypothesis':'动量','acceptance':'预先定义门槛','developmentStart':'2024-01-01','developmentEnd':'2024-12-31','validationStart':'2025-01-01','validationEnd':'2025-06-30','maxTrials':10,'rules':{'minSignedIc':0.01,'maxDrawdown':.3,'minObservations':2,'direction':'positive'}}}}
def result():
 return {'metrics':{'ic':.05,'max_drawdown':-.1},'meta':{'data_release_id':'r1','spec_hash':'s1','factor_source_hash':'f1'},'factor_analysis':{'ic_series':[{'date':'a','value':.05},{'date':'b','value':.1}]}}
class PolicyTests(unittest.TestCase):
 def test_scientific_v2_requires_real_costs(self):
  p=project();p['config']['researchPlan']['evaluationProtocol']='scientific-v2';p['config']['commissionRate']=0;p['config']['stampTax']=0;p['config']['slippageRate']=0
  with self.assertRaisesRegex(WorkflowError,'科学评估 v2 要求'):snapshot(p)
 def test_nonoverlap(self):
  p=project();p['config']['researchPlan']['validationStart']='2024-12-31'
  with self.assertRaises(WorkflowError):snapshot(p)
 def test_explicit_rules_required(self):
  p=project();del p['config']['researchPlan']['rules']
  with self.assertRaises(WorkflowError):snapshot(p)
 def test_snapshot_tracks_input_but_not_mutable_title_timestamp(self):
  p=project();a=digest(snapshot(p));p['updatedAt']='today';self.assertEqual(a,digest(snapshot(p)))
  p['config']['commissionRate']=.002;self.assertNotEqual(a,digest(snapshot(p)))
 def test_code_error_rejected(self):
  p=project();p['config']['draftFactor']['body']='x=';
  with self.assertRaises(WorkflowError):snapshot(p)
 def test_sameclose_rejected(self):
  p=project();p['config']['executionTiming']='same_close'
  with self.assertRaises(WorkflowError):snapshot(p)
 def test_nonfinite_threshold_rejected(self):
  p=project();p['config']['researchPlan']['rules']['minSignedIc']=float('nan')
  with self.assertRaises(WorkflowError):snapshot(p)
 def test_boolean_threshold_rejected(self):
  p=project();p['config']['researchPlan']['rules']['minSignedIc']=True
  with self.assertRaises(WorkflowError):snapshot(p)
 def test_poor_candidate_filtered(self):
  r=result();r['metrics']['ic']=-.02;self.assertFalse(evaluate(r,snapshot(project())['rules'])['passed'])
 def test_pass_does_not_mean_sealed(self):
  g=evaluate(result(),snapshot(project())['rules']);self.assertTrue(g['passed']);self.assertFalse(g['sealed'])
 def test_missing_observations_fail_closed(self):
  r=result();r['factor_analysis']={};self.assertFalse(evaluate(r,snapshot(project())['rules'])['passed'])
 def test_nan_observations_not_counted(self):
  r=result();r['factor_analysis']['ic_series'][0]['value']=float('nan');self.assertFalse(evaluate(r,snapshot(project())['rules'])['passed'])
 def test_missing_provenance_rejected(self):
  r=result();r['meta'].pop('spec_hash')
  with self.assertRaises(WorkflowError):evaluate(r,snapshot(project())['rules'])
 def test_data_drift_rejected(self):
  a=result();b=result();b['meta']['data_release_id']='r2'
  with self.assertRaises(WorkflowError):compare_identity(a,b)
 def test_source_drift_rejected(self):
  a=result();b=result();b['meta']['factor_source_hash']='f2'
  with self.assertRaises(WorkflowError):compare_identity(a,b)
 def test_negative_direction(self):
  r=result();r['metrics']['ic']=-.05;rules=snapshot(project())['rules'];rules['direction']='negative';self.assertTrue(evaluate(r,rules)['passed'])
if __name__=='__main__':unittest.main()

class AssistantSchemaTests(unittest.TestCase):
 def test_assistant_cannot_return_approval_or_hidden_changes(self):
  from pydantic import ValidationError
  from services.quant_factor.assistant import Suggestion
  with self.assertRaises(ValidationError):Suggestion.model_validate({'hypothesis':'h','target':'t','acceptance':'a','summary':'s','limitations':[],'approved':True})

class MetricContractTests(unittest.TestCase):
 def test_rank_metric_uses_rank_not_pearson(self):
  rules=snapshot(project())['rules'];rules['icMetric']='rank_ic'
  r=result();r['metrics']['rank_ic']=-.1
  gate=evaluate(r,rules)
  self.assertFalse(gate['passed']);self.assertEqual(gate['checks'][0]['name'],'方向Rank IC')
 def test_missing_requested_rank_cannot_pass_on_pearson(self):
  rules=snapshot(project())['rules'];rules['icMetric']='rank_ic'
  with self.assertRaises(WorkflowError):evaluate(result(),rules)
 def test_old_pearson_snapshot_remains_identical(self):
  p=project();old=snapshot(p);self.assertNotIn('icMetric',old['rules'])
  p['config']['researchPlan']['rules']['icMetric']='rank_ic'
  self.assertNotEqual(digest(old),digest(snapshot(p)))


class RankICGateTest(unittest.TestCase):
    def result(self, series):
        return {'metrics': {'rank_ic': 0.03, 'max_drawdown': -0.1},
                'factor_analysis': {'rank_ic_mean': 0.03, 'rank_ic_series': series},
                'meta': {'data_release_id': 'r', 'spec_hash': 's', 'factor_source_hash': 'h'}}

    def rules(self):
        return {'icMetric': 'rank_ic', 'direction': 'positive', 'minSignedIc': 0.005,
                'maxDrawdown': 0.5, 'minObservations': 20}

    def series(self, n=120, value=0.03):
        return [{'value': value + 0.01 * ((i * 7) % 5 - 2) / 2} for i in range(n)]

    def test_nw_t_check_uses_k_threshold(self):
        from services.quant_factor.metrics import threshold, newey_west_t
        out = evaluate(self.result(self.series()), self.rules(), k=5)
        check = [c for c in out['checks'] if c['name'] == '方向 NW t'][0]
        self.assertAlmostEqual(check['threshold'], threshold(5), places=12)
        self.assertAlmostEqual(check['actual'], newey_west_t(self.series())['t'], places=12)

    def test_missing_rank_ic_series_blocks_gate(self):
        out = evaluate(self.result([]), self.rules(), k=1)
        self.assertFalse(out['passed'])
        self.assertEqual([c for c in out['checks'] if c['name'] == '日度 Rank IC 序列'][0]['passed'], False)


class NegativeFactorSealTest(unittest.TestCase):
    def test_negative_direction_passes_with_negative_ic(self):
        series = [{'value': -0.03 + 0.005 * ((i * 7) % 5 - 2)} for i in range(220)]
        result = {'metrics': {'rank_ic': -0.03, 'max_drawdown': -0.1},
                  'factor_analysis': {'rank_ic_mean': -0.03, 'rank_ic_series': series},
                  'meta': {'data_release_id': 'r', 'spec_hash': 's', 'factor_source_hash': 'h'}}
        rules = {'icMetric': 'rank_ic', 'direction': 'negative', 'minSignedIc': 0.005,
                 'maxDrawdown': 0.5, 'minObservations': 60}
        out = evaluate(result, rules, k=1, lags=4)
        self.assertTrue(out['passed'])
        self.assertTrue([c for c in out['checks'] if c['name'] == '方向 NW t'][0]['passed'])
