import os,unittest
from unittest.mock import patch
from services.quant_factor import research_queue as q,service,decision_engine
from services.quant_factor.policy import WorkflowError
from pydantic import BaseModel

class QueueBoundaryTests(unittest.TestCase):
 def test_explicit_lightweight_scope_does_not_authorize_background_roles(self):
  self.assertFalse(q.permits_lightweight('quant.factor.research_assistant'))
  with q.lightweight_advice():
   self.assertTrue(q.permits_lightweight('quant.factor.research_assistant'))
   self.assertTrue(q.permits_lightweight('quant.factor.independent_reviewer'))
   self.assertFalse(q.permits_lightweight('quant.factor.research_planner_v2'))
  self.assertFalse(q.permits_lightweight('quant.factor.research_assistant'))
 def test_heavy_direct_call_cannot_bypass_owned_slot(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'1'}),self.assertRaisesRegex(WorkflowError,'排队执行'):q.require_context()
 def test_own_startup_never_scans_or_resets_all_candidates(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'1'}),patch.object(service,'get_conn',side_effect=AssertionError('global candidate reset forbidden')):
   self.assertEqual(service.mark_interrupted_candidates(),0)
 def test_generic_strategy_exhaustion_unchanged_but_factor_checkpoint_is_not_market_failure(self):
  class Decision(BaseModel):action:str='revise'
  for explicit in (None,'调度检查点，研究结论未定'):
   _,reason=decision_engine.run_steps(decide=lambda n:(Decision(),{}),execute=lambda *a:{},max_steps=1,exhausted_reason=explicit)
   self.assertEqual(reason,explicit or '连续 1 步未达标，停止等待人工复盘')

 def test_control_rejection_before_dispatch_creates_no_unknown_external_intent(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'1'}),patch.object(q,'require_context',side_effect=WorkflowError('paused')),patch.object(q,'get_conn',side_effect=AssertionError('no dispatch intent on rejected control')):
   with self.assertRaises(q.SubmissionNotDispatched):q.external_begin('factor',{'base':'http://fixture.invalid'},'hash')
