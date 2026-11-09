import copy
import unittest
from unittest.mock import patch,MagicMock
from services.quant_factor import presentation,f0_agent
from services.quant_factor.policy import digest,WorkflowError
from tests.test_quant_factor_assets import fixture

class IdentityTests(unittest.TestCase):
 def test_initial_creation_is_not_execution_provenance(self):
  out=presentation.branch_sources({'source':'manual'},{'executor':'agent'})
  self.assertEqual(out['creation_label'],'人工建立课题');self.assertEqual(out['execution_label'],'研究系统执行')
 def test_candidate_uses_report_mapping_not_latest_branch(self):
  facts={'topic_id':'topic','branches':{'h1':{'source':'manual'}},'labels':{'h1':'H1'},'trials':[{'branch_id':'h1','trial_no':1,'executor':'agent','report_id':'qf_c_development'},{'branch_id':'h2','trial_no':2,'report_id':'qf_other_development'}]}
  out=presentation.candidate_identity({'id':'c','evidence':{}},facts)
  self.assertEqual((out['trial_no'],out['branch_label']),(1,'H1'))
  self.assertEqual(out['execution_label'],'研究系统执行')
 def test_conflicting_branch_is_explicit_not_guessed(self):
  out=presentation.candidate_identity({'id':'c','evidence':{'branch_id':'wrong'}},{'trials':[{'report_id':'qf_c_development','branch_id':'h1','trial_no':1}],'branches':{},'labels':{}})
  self.assertEqual(out['relation_status'],'conflict');self.assertIsNone(out['branch_id'])
 def test_checkout_copies_selected_definition_and_static_scope_without_pass_status(self):
  row,_=fixture();row['snapshot']['request'].pop('universe');row['snapshot']['request']['universe_snapshot']={'symbols':['000001.SZ','600000.SH']};row['snapshot_hash']=digest(row['snapshot']);before=copy.deepcopy(row)
  out=presentation.checkout_config({'draftFactor':{'name':'wrong'},'researchUniverseSymbols':['wrong']},row,'new')
  self.assertEqual(out['researchUniverseSymbols'],['000001.SZ','600000.SH']);self.assertEqual(out['v5ActiveBranch'],'new');self.assertFalse(out['sourceResearchCandidate']['inherits_approval']);self.assertNotIn('archive',out);self.assertEqual(row,before)
 def test_checkout_rejects_changed_frozen_evidence(self):
  row,_=fixture();row['snapshot']['name']='changed'
  with self.assertRaisesRegex(ValueError,'指纹'):presentation.checkout_config({},row,'new')
 def test_late_model_is_not_applied_after_pause_or_epoch_change(self):
  for topic,run in [({'status':'paused'},{'status':'running','decision':{'runner_epoch':'old'}}),({'status':'active'},{'status':'running','decision':{'runner_epoch':'new'}})]:
   c=MagicMock();c.execute.return_value=c;c.fetchone.side_effect=[{'id':'p'},topic,run]
   with patch.object(f0_agent,'get_conn') as connect:
    connect.return_value.__enter__.return_value=c
    with self.assertRaisesRegex(WorkflowError,'暂停|接手'):
     with f0_agent._writable_project(1,2,{'id':'p'},'t','r','old'):self.fail('late writer entered')

class QuantSaveAdapterTests(unittest.TestCase):
 def test_actual_quant_put_uses_atomic_workbench_then_keeps_legacy_fallback(self):
  from app.routers.inst_quant import quant_detect_project_put
  with patch('services.quant_factor.presentation.save_workbench',return_value={'project':{'id':'v5'}}) as save,patch('app.routers.detect.detect_put_project') as legacy:
   self.assertEqual(quant_detect_project_put('p',{'config':{}},9,{'org':{'id':2}}),{'project':{'id':'v5'}})
  save.assert_called_once_with(9,2,'p',{'config':{}});legacy.assert_not_called()
  with patch('services.quant_factor.presentation.save_workbench',return_value=None),patch('app.routers.detect.detect_put_project',return_value={'project':{'id':'legacy'}}) as legacy:
   self.assertEqual(quant_detect_project_put('p',{},9,{'org':{'id':2}})['project']['id'],'legacy')
  legacy.assert_called_once()
 def test_actual_quant_put_cas_conflict_cannot_fall_through_to_unguarded_save(self):
  from app.routers.inst_quant import quant_detect_project_put
  from fastapi import HTTPException
  with patch('services.quant_factor.presentation.save_workbench',side_effect=ValueError('控制版本已变化')),patch('app.routers.detect.detect_put_project') as legacy,self.assertRaises(HTTPException) as error:quant_detect_project_put('p',{},9,{'org':{'id':2}})
  self.assertEqual(error.exception.status_code,409);legacy.assert_not_called()
