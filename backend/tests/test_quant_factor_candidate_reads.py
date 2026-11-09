import json,unittest
from unittest.mock import patch
from services.quant_factor import store,assistant

class CandidateReadTests(unittest.TestCase):
 def evidence(self):return {'branch_id':'branch-uuid','method':{'method_id':'f0'},'development':{'run_id':'actual-run','gate':{'passed':False},'result':{'metrics':{'ic':0.01},'meta':{'source':'fixture'}}},'validation':None,'future_metadata':'scalar'}
 def test_actual_candidate_list_with_scalar_branch_metadata_returns_phase_summaries(self):
  row={'id':'candidate','evidence':self.evidence()}
  with patch.object(store.repo,'candidates',return_value=[row]):out=store.list_candidates(5,2,'p')
  self.assertEqual(set(out[0]['evidence']),{'development'});self.assertEqual(out[0]['evidence']['development']['run_id'],'actual-run');self.assertNotIn('result',out[0]['evidence']['development'])
 def test_actual_assistant_candidate_context_uses_same_mixed_evidence_safely(self):
  suggestion={'hypothesis':'假设','target':'目标','acceptance':'方法','summary':'已有研发未通过','limitations':['尚未通过查重']}
  with patch.object(assistant,'get_project',return_value={'project':{'name':'fixture','config':{}}}),patch.object(assistant.store,'read',return_value={'project_id':'p','snapshot':{},'status':'development_failed','evidence':self.evidence()}),patch.object(assistant,'assert_quota_available'),patch.object(assistant,'get_task'),patch.object(assistant,'record_usage'),patch.object(assistant,'run_task',return_value={'content':json.dumps(suggestion)}) as model:
   result=assistant.suggest(5,2,'p',candidate_id='candidate')
  context=json.loads(model.call_args.kwargs['messages'][1]['content']);self.assertEqual(set(context['candidate']['evidence']),{'development'});self.assertEqual(context['candidate']['evidence']['development']['metrics']['ic'],0.01);self.assertEqual(result['suggestion']['summary'],suggestion['summary'])
