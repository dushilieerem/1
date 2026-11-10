"""Actual FastAPI lifespan, external bootstrap/prewarm replaced; no real SQL/network."""
import asyncio,os,unittest
from unittest.mock import patch
from app import main
from services.quant_factor import research_queue,service

class QuantStartupScopeTests(unittest.TestCase):
 def run_lifespan(self):
  async def run():
   async with main.lifespan(main.app):pass
  asyncio.run(run())
 def test_default_shared_startup_never_claims_or_resets_any_research_rows(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'0'}),patch.object(main,'_configure_threadpool'),patch.object(main,'bootstrap_schemas'),patch.object(main.threading,'Thread'),patch.object(research_queue,'get_conn',side_effect=AssertionError('default startup must not access queue DB')),patch.object(service,'mark_interrupted_candidates',side_effect=AssertionError('legacy full-table entry must not be called')),patch.object(research_queue,'recover_owned') as recover:
   self.run_lifespan()
  recover.assert_not_called()
 def test_explicit_owned_startup_reuses_existing_owned_recovery_and_dispatcher(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'1'}),patch.object(main,'_configure_threadpool'),patch.object(main,'bootstrap_schemas'),patch.object(main.threading,'Thread') as thread,patch.object(research_queue,'_STARTED',False),patch.object(research_queue,'recover_owned',return_value={'requeued':0,'waiting_confirmation':0,'waiting_checkpoint':0}) as recover,patch.object(service,'mark_interrupted_candidates',side_effect=AssertionError('never use candidate-wide cleanup')):
   self.run_lifespan()
   self.assertTrue(research_queue._STARTED)
   # Second startup cannot duplicate a dispatcher/recovery pass in one process.
   self.run_lifespan()
  recover.assert_called_once()
  self.assertEqual(sum(1 for call in thread.call_args_list if call.kwargs.get('name')=='quant-owned-research-dispatch'),1)
 def test_owned_recovery_failure_does_not_advertise_successful_startup(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'1'}),patch.object(main,'_configure_threadpool'),patch.object(main,'bootstrap_schemas'),patch.object(main.threading,'Thread'),patch.object(research_queue,'_STARTED',False),patch.object(research_queue,'recover_owned',side_effect=RuntimeError('owned lease could not be checked')):
   with self.assertRaisesRegex(RuntimeError,'owned lease'):self.run_lifespan()
   self.assertFalse(research_queue._STARTED)
 def test_deprecated_unscoped_candidate_entry_is_noop_even_if_called_directly(self):
  for enabled in ('0','1'):
   with self.subTest(queue_flag=enabled),patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':enabled}),patch.object(service,'get_conn',side_effect=AssertionError('legacy candidate-wide DB access forbidden')):
    self.assertEqual(service.mark_interrupted_candidates(),0)

if __name__=='__main__':unittest.main()
