import copy,io,json,unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from services.quant_factor import research_method as method,research_contract as contract,model_budget as budget,provenance
from services.quant_factor.policy import WorkflowError
from tests.test_quant_research_method import contract as fixture_contract,snap,RULES

class RunSnapshotTests(unittest.TestCase):
 def test_project_scope_ignores_unrelated_bff_provenance_but_preserves_original(self):
  frozen=fixture_contract();frozen['method_identity']['bff_code_revision']='old-quant-collection';frozen['contract_hash']=contract.fingerprint({k:v for k,v in frozen.items() if k!='contract_hash'})
  project={'id':'p','config':{'researchPlan':{**snap()['plan'],'rules':RULES,'researchContract':frozen}}};before=copy.deepcopy(project)
  with patch.object(provenance,'_CODE_REVISION','unrelated-quant-change'):self.assertEqual(contract.check_project(project),frozen)
  self.assertEqual(project,before)
 def test_loaded_snapshot_never_reads_live_wip_or_git_head(self):
  saved=method.snapshot()
  with patch.object(Path,'read_bytes',side_effect=AssertionError('live disk should not be read')):self.assertEqual(method.snapshot(),saved)
 def test_only_explicit_method_files_affect_implementation_identity(self):
  values={name:name.encode() for name in method.METHOD_FILES};values['presentation.py']=b'ui helper';values['HEAD']=b'before'
  with patch.object(Path,'read_bytes',side_effect=lambda:None):pass
  def read(path):return values[path.name]
  with patch.object(Path,'read_bytes',read):
   original=method.implementation_fingerprint('/fixture');values['presentation.py']=b'new ui';values['HEAD']=b'new docs commit';self.assertEqual(method.implementation_fingerprint('/fixture'),original)
   values['f0_agent.py']=b'changed actual method';self.assertNotEqual(method.implementation_fingerprint('/fixture'),original)
 def test_actual_method_change_refuses_old_run_snapshot(self):
  saved=method.snapshot()
  with patch.object(method,'_LOADED_IMPLEMENTATION','new-loaded-method'),self.assertRaisesRegex(WorkflowError,'新运行'):method.validate_snapshot(saved)
 def test_all_roles_wire_exact_frozen_16000_and_150_without_gateway_retry(self):
  from ai.gateway import providers
  from ai.router import get_task
  method.register_tasks();frozen=method.snapshot();target=SimpleNamespace(model='existing-slot-model',provider='fixture',base_url='http://fixture.invalid',timeout=150)
  raw={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}
  for role in (method.PLANNER,method.IMPLEMENTER,method.DIAGNOSER):
   spec=replace(get_task(role),validator=None)
   with self.subTest(role=role),patch('ai.router.get_task',return_value=spec),patch.object(providers,'resolve_target',return_value=target),patch.object(budget,'reserve',return_value={'id':'call','status':'reserved'}) as reserve,patch.object(budget,'claim',return_value=True),patch.object(budget,'settle'),patch.object(budget,'unresolved'),patch.object(providers,'_post',return_value=io.BytesIO(json.dumps(raw).encode())) as post,patch.object(providers,'complete',side_effect=AssertionError('hidden retry forbidden')),patch.dict(budget.OUTPUT_LIMITS,{role:1}):
    budget.run(999999,999998,'p','explicit-call',role,messages=[{'role':'user','content':'fixture'}],method_snapshot=frozen)
   self.assertEqual(post.call_count,1);self.assertEqual(post.call_args.args[1]['max_tokens'],16000);self.assertEqual(post.call_args.kwargs['timeout'],150);self.assertEqual(reserve.call_args.args[7],16000)
 def test_complete_proposal_and_diagnosis_json_schemas_and_strict_null(self):
  proposal={'action':'run_test','hypothesis':'exact hypothesis','mechanism':'reason','required_fields':['close'],'change_scope':'initial','expected_effect':'effect','falsification':'no IC','evidence_refs':[],'rationale':'based on fixed research contract','title':'test','stop_reason':''}
  ctx={'research_contract':fixture_contract(),'evidence_refs':[],'run_id':'run','active_branch':'h1','k':0,'next_new_trial_threshold':1.96,'decision_step':1,'method_snapshot':method.snapshot()}
  with patch.object(budget,'run',return_value={'content':json.dumps(proposal)}) as model:method.plan(1,2,'p','run',ctx)
  prompt=model.call_args.kwargs['messages'][0]['content'];self.assertIn('"required"',prompt);self.assertIn('"enum"',prompt);self.assertIn('"type": "string"',prompt);self.assertEqual(model.call_args.kwargs['method_snapshot'],ctx['method_snapshot'])
  with self.assertRaises(ValueError):method.parse_proposal(json.dumps({**proposal,'stop_reason':None}),fixture_contract(),[])
  interpretation={'findings':[],'explanation':'descriptive only','next_action':'stop','uncertainty':[],'evidence_refs':['r']}
  with patch.object(budget,'run',return_value={'content':json.dumps(interpretation)}) as model:method.interpret(1,2,'p','run',1,{'facts':{'report_id':'r'},'facts_hash':'f'},method_snapshot=method.snapshot())
  self.assertIn('"required"',model.call_args.kwargs['messages'][0]['content']);self.assertIn('"enum"',model.call_args.kwargs['messages'][0]['content'])
 def test_provenance_uses_frozen_caps_and_keeps_pure_manual_distinct(self):
  frozen=method.snapshot();agent=provenance.method_manifest('sha','agent','run',research_contract=fixture_contract(),method_snapshot=frozen)
  self.assertEqual(set(agent['execution_config']['role_output_limits'].values()),{16000});self.assertEqual(agent['execution_config']['method_snapshot'],frozen)
  manual=provenance.method_manifest('sha','human',research_contract=fixture_contract());self.assertEqual(manual['method_version'],'factor-manual-v1');self.assertNotIn('role_output_limits',manual['execution_config'])

 def test_generation_carries_supplied_task_snapshot_to_actual_budget_boundary(self):
  from services.quant_factor import generation
  frozen=method.snapshot();body={'prompt':'按固定过去价格定义生成截面因子','context':{'custom_source_contract':'quant-panel-causal-v1'},'idempotency_key':'00000000-0000-4000-8000-000000000008'}
  raw={'factor':{'factor_name':'f','factor_code':'def f(self): return self.close.rank(axis=1,pct=True)'},'errors':[]}
  with patch.object(budget,'run',return_value={'data':raw,'model':'same-slot'}) as model:
   output=generation.generate(999999,999998,'p','job',body,research_contract=fixture_contract(),method_snapshot=frozen,proposal={'required_fields':['close']})
  self.assertEqual(model.call_args.kwargs['method_snapshot'],frozen);self.assertEqual(model.call_args.args[4],method.IMPLEMENTER);self.assertEqual(output['research_method']['method_snapshot'],frozen);self.assertEqual(output['meta']['prompt_version'],frozen['roles'][method.IMPLEMENTER]['prompt_version'])
