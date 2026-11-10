import copy,json,unittest
from unittest.mock import patch
from services.quant_factor import research_contract as rc,source_identity as si,development_diagnosis as dd,research_method as rm,policy
from services.quant_factor.metrics import threshold

RULES={'direction':'positive','icMetric':'rank_ic','minSignedIc':.005,'maxDrawdown':.5,'minObservations':60}
SOURCE='def f(self):\n    x=self.close.shift(1)\n    return x.rank(axis=1,pct=True)'

def contract():return rc.freeze(data_fields=rc.OHLCV|{'turnover'},engine_fields=rc.OHLCV|{'turnover'},requested_fields=None,rules=RULES,data_identity={'view_id':'v','org_id':999999,'project_id':'p','universe':None,'development':['2025-07-01','2025-09-30'],'validation':['2026-06-22','2026-09-21']},method_identity={'version':rc.METHOD_VERSION},explicit_ohlcv=True)
def snap():return {'request':{'factor_name':'f','factor_code':SOURCE,'universe_snapshot':{'symbols':['000001.SZ'],'version':'1'},'groups':5,'rebalance_days':5},'plan':{'researchContract':contract(),'developmentStart':'2025-07-01','developmentEnd':'2025-09-30','validationStart':'2026-06-22','validationEnd':'2026-09-21'},'rules':RULES}
def candidate():return {'id':'c1','snapshot_hash':'sha','snapshot':snap(),'evidence':{'development':{'report_id':'r1','gate':{'passed':False,'checks':[{'name':'方向 NW t','actual':1.63461,'threshold':threshold(2),'passed':False}]},'result':{'factor_analysis':{'rank_ic_series':[{'date':'2025-07-01','value':.1},{'date':'2025-07-02','value':-.2}],'ic_series':[{'date':'2025-07-01','value':.9}]}},'novelty':{'status':'resource_pending'}},'validation':{'secret':123456}}}

class ContractTests(unittest.TestCase):
 def test_exact_ohlcv_enforced_by_actual_source(self):
  c=contract();rc.check_fields(['close','volume'],c)
  with self.assertRaisesRegex(ValueError,'turnover'):rc.check_fields(['turnover'],c)
  self.assertEqual(c['allowed_fields'],sorted(rc.OHLCV))
 def test_missing_capability_and_tamper_fail_closed(self):
  with self.assertRaises(ValueError):rc.freeze(data_fields=['close'],engine_fields=['volume'],requested_fields=None,rules=RULES,data_identity={'v':1},method_identity={'v':2})
  c=contract();c['allowed_fields'].append('turnover')
  with self.assertRaisesRegex(ValueError,'变化'):rc.check_fields([],c)
 def test_server_reads_matching_publication_not_client_contract(self):
  project={'id':'p','config':{'researchPlan':{'rules':RULES,'fieldRestriction':'ohlcv','researchContract':{'forged':True}}}}
  meta={'published':True,'catalog_version':'v','publication_version':'v','fields':[{'name':n} for n in rc.OHLCV]}
  with patch('services.quant_data_resources.dataset',return_value=meta):c=rc.from_project(999999,999998,project,{'view_id':'v','manifest_sha256':'m','datasets':{'daily_bars':{'sha256':'daily'},'unrelated':{'sha256':'other'}}})
  self.assertEqual(c['data_identity']['org_id'],999998);self.assertNotIn('unrelated',c['data_identity']['datasets']);self.assertNotIn('forged',c)
  with patch('services.quant_data_resources.dataset',return_value={**meta,'publication_version':'other'}),self.assertRaises(ValueError):rc.from_project(1,2,project,{'view_id':'v'})
 def test_legacy_is_not_rewritten(self):self.assertIsNone(rc.check_project({'id':'old','config':{}}))

class SourceIdentityTests(unittest.TestCase):
 def test_whitespace_comments_and_consistent_names_equal(self):
  other=SOURCE.replace('x=','result = ').replace('return x.','return result.')+' # comment'
  self.assertEqual(si.identity(SOURCE),si.identity(other))
 def test_original_local_name_cannot_alias_free_or_parameter(self):
  a='def f(self):\n    _local_0=self.close\n    x=self.volume\n    return _local_0.add(x)'
  b='def f(self):\n    y=self.close\n    _local_0=self.volume\n    return y.add(_local_0)'
  self.assertEqual(si.identity(a),si.identity(b))
  self.assertNotEqual(si.identity(a),si.identity(b.replace('y.add(_local_0)','_local_0.add(y)')))
 def test_invalid_future_source_never_gets_identity(self):
  with self.assertRaises(ValueError):si.identity('def f(self): return self.close.shift(-1)')
 def test_no_algebraic_reordering(self):
  self.assertNotEqual(si.identity('def f(self): return self.close+self.volume'),si.identity('def f(self): return self.volume+self.close'))
 def test_all_execution_conditions_participate_in_reuse(self):
  original=snap();key=si.execution_key(original)
  changes=[('request','groups',10),('request','universe_snapshot',{'symbols':['600000.SH']}),('plan','developmentEnd','2025-09-29'),('rules','direction','negative'),('plan','researchContract',{**contract(),'method_identity':{'version':'different'}})]
  for part,field,value in changes:
   with self.subTest(field=field):
    changed=copy.deepcopy(original);changed[part][field]=value;self.assertNotEqual(key,si.execution_key(changed))
  changed=copy.deepcopy(original);changed['request']['factor_code']=SOURCE.replace('x=','y=').replace('return x.','return y.');self.assertEqual(key,si.execution_key(changed))

class DiagnosisTests(unittest.TestCase):
 def test_rank_series_and_selected_report_only(self):
  out=dd.describe(candidate(),{'report_id':'r1','trial_no':2,'branch_id':'h2','k_at_report':2},2,threshold)
  facts=out['facts'];self.assertEqual(facts['metric_type'],'rank_ic');self.assertEqual(facts['evaluation_stage'],'development');self.assertAlmostEqual(facts['series']['summary']['signed_mean'],-.05)
  self.assertEqual(facts['historical_threshold'],threshold(2));self.assertEqual(facts['next_new_trial_threshold'],threshold(3));self.assertNotIn('123456',json.dumps(out))
  with self.assertRaises(ValueError):dd.describe(candidate(),{'report_id':'another'},2,threshold)
 def test_missing_series_not_zero_or_temporal_segments(self):
  c=candidate();del c['evidence']['development']['result']['factor_analysis']['rank_ic_series']
  facts=dd.describe(c,{'report_id':'r1'},0,threshold)['facts'];self.assertIsNone(facts['series']['summary']);self.assertEqual(facts['series']['state'],'missing')
  c=candidate();c['evidence']['development']['result']['factor_analysis']['rank_ic_series']=[{'value':.1},{'value':.2}]
  series=dd.describe(c,{'report_id':'r1'},1,threshold)['facts']['series'];self.assertFalse(series['temporal_order_confirmed']);self.assertIsNone(series['first_half'])
  with self.assertRaises(ValueError):dd.describe(candidate(),{'report_id':'r1'},True,threshold)
 def test_proposal_cannot_override_authority_or_invent_refs(self):
  p={'action':'revise','hypothesis':'test change','mechanism':'mechanism','required_fields':['close'],'change_scope':'one change','expected_effect':'test','falsification':'no IC','evidence_refs':['r1'],'rationale':'E2 evidence insufficient','title':'短周期修订','stop_reason':''}
  self.assertEqual(rm.parse_proposal(json.dumps(p),contract(),['r1']).hypothesis,'test change')
  for bad in ({**p,'k':0},{**p,'required_fields':['turnover']},{**p,'evidence_refs':['sealed:r2']}):
   with self.assertRaises(ValueError):rm.parse_proposal(json.dumps(bad),contract(),['r1'])
 def test_three_role_specs_explicit_caps(self):
  rm.register_tasks();from ai.router import get_task
  self.assertEqual(get_task(rm.IMPLEMENTER).max_tokens,16000);self.assertNotEqual(rm.PLANNER,rm.DIAGNOSER)
 def test_gate_observations_follow_frozen_metric(self):
  result={'metrics':{'ic':.1,'rank_ic':.2,'max_drawdown':.01},'meta':{'data_release_id':'d','spec_hash':'s','factor_source_hash':'f'},'factor_analysis':{'ic_series':[{'value':.1}]*61,'rank_ic_series':[{'value':.2}]*59}}
  for metric,n in [('ic',61),('rank_ic',59)]:
   gate=policy.evaluate(result,{**RULES,'icMetric':metric},k=2);obs=next(x for x in gate['checks'] if x['name']=='有效IC观测数');self.assertEqual(obs['actual'],n)


class SelectedParentIntegrationTests(unittest.TestCase):
 def context(self):
  from services.quant_factor import f0_agent as agent
  from unittest.mock import MagicMock
  topic={'id':'topic','project_id':'p','primary_holding_period':1,'max_trials':4,'status':'active'}
  trials=[{'trial_no':1,'branch_id':'h1','report_id':'qf_c1_development','outcome':'failed','holding_period':1}, {'trial_no':2,'branch_id':'h2','report_id':'qf_c2_development','outcome':'failed','holding_period':1}]
  cand=candidate();cand['evidence']['development']['novelty']['status']='deferred';cand['evidence']['development']['report_id']='qf_c1_development';cand['id']='c1'
  cfg={'v5ActiveBranch':'h1','researchPlan':{**snap()['plan'],'hypothesis':'原研究假设','rules':RULES,'researchContract':contract()}}
  c=MagicMock();w=MagicMock();w.__enter__.return_value=c
  def execute(sql,args=()):
   cursor=MagicMock()
   if 'FROM quant_factor_branches' in sql:cursor.fetchall.return_value=[{'id':'h1'},{'id':'h2'}]
   elif 'stop_reason' in sql:cursor.fetchall.return_value=[]
   elif 'SELECT config' in sql:cursor.fetchone.return_value={'config':cfg}
   elif 'SELECT decision' in sql:cursor.fetchone.return_value={'branch_id':'h1','decision':{'method_version':rc.METHOD_VERSION}}
   elif 'COUNT(*)' in sql:cursor.fetchone.return_value={'n':0}
   elif 'quant_factor_candidates' in sql:
    self.assertEqual(args[0],'c1');cursor.fetchone.return_value=cand
   return cursor
  c.execute.side_effect=execute
  with patch.object(agent,'get_conn',return_value=w),patch.object(agent.ledger,'_trials',return_value=trials),patch('services.quant_factor.asset_context.catalogue',return_value={'hash':'assets','count':0,'owned':[],'builtins':[]}):
   return agent._context(999999,999998,topic,'run'),topic
 def test_planner_reads_selected_old_branch_not_global_latest(self):
  from services.quant_factor import f0_agent as agent
  ctx,topic=self.context();self.assertEqual(ctx['selected_parent']['candidate_id'],'c1');self.assertEqual(ctx['selected_parent']['branch_id'],'h1');self.assertEqual(ctx['development_diagnosis']['facts']['historical_k'],1);self.assertEqual(ctx['k'],2)
  proposal={'action':'revise','hypothesis':'原样选定的新假设','mechanism':'解释','required_fields':['close'],'change_scope':'只改过去窗口','expected_effect':'事前预期','falsification':'不成立则停止','evidence_refs':['qf_c1_development'],'rationale':'E1显著性不支持原假设','title':'短期价量修订','stop_reason':''}
  with patch.object(agent,'_context',return_value=ctx),patch.object(agent,'_phase'),patch('services.quant_factor.model_budget.run',return_value={'content':json.dumps(proposal),'tokens_in':1,'tokens_out':2}) as model:
   decision,_=agent.decide(999999,999998,topic,'run')
  self.assertEqual(decision.branch_id,'h1');self.assertEqual(decision.binding['parent_candidate_id'],'c1');self.assertEqual(decision.next_hypothesis,proposal['hypothesis']);self.assertEqual(model.call_args.args[4],rm.PLANNER)
 def test_changed_parent_blocks_execution_before_any_tool(self):
  from services.quant_factor import f0_agent as agent
  ctx,topic=self.context();bound=rm.binding(ctx);bound['parent_candidate_id']='other'
  decision=agent.Decision(action='revise',rationale='针对固定父证据的修订',binding=bound)
  with patch.object(agent,'_context',return_value=ctx),patch.object(agent,'_revise') as tool,self.assertRaisesRegex(ValueError,'父E/H'):
   agent.execute(999999,999998,'run',topic,decision,1)
  tool.assert_not_called()
 def test_same_conditions_reuse_stops_before_market_or_seal(self):
  from services.quant_factor import f0_agent as agent
  ctx,topic=self.context();decision=agent.Decision(action='run_test',rationale='检验已固定当前实现')
  reused={**candidate(),'status':'development_passed','reused_evidence':True}
  with patch.object(agent,'_context',return_value={**ctx,'remaining':1,'manual_handoff':{'snapshot_hash':'sha','control_epoch':'epoch'}}),patch.object(agent,'get_project',return_value={'project':{'config':{'factorCodes':['f'],'draftFactor':{'body':SOURCE}}}}),patch.object(agent,'_run_test',return_value=reused),patch.object(agent.sealed,'request') as seal:
   out=agent.execute(999999,999998,'run',topic,decision,1)
  self.assertEqual(out['status'],'stopped');seal.assert_not_called()


class GenericWriteAuthorityTests(unittest.TestCase):
 def connection(self,has_topic):
  from unittest.mock import MagicMock
  c=MagicMock();w=MagicMock();w.__enter__.return_value=c
  def execute(sql,args=()):
   cursor=MagicMock()
   if 'to_regclass' in sql:cursor.fetchone.return_value={'table_name':'quant_factor_topics'}
   elif 'FROM quant_factor_topics' in sql:cursor.fetchone.return_value={'id':'topic'} if has_topic else None
   elif 'SELECT run_count' in sql:cursor.fetchone.return_value=None
   elif 'INSERT INTO detect_projects' in sql:cursor.fetchone.return_value={'id':'personal'}
   return cursor
  c.execute.side_effect=execute;return w,c
 def test_actual_post_put_refuse_remove_rehash_cross_project_and_fake_legacy(self):
  from services.factor import detect_store
  from app.routers import detect
  from fastapi import HTTPException
  for altered in ({}, {'researchPlan':{}},{'researchPlan':{'researchContract':contract()}},{'researchPlan':{'researchContract':{**contract(),'data_identity':{'project_id':'other'},'contract_hash':'recomputed'}}}):
   for endpoint in ('post','put'):
    with self.subTest(config=altered,endpoint=endpoint):
     w,c=self.connection(True)
     with patch.object(detect_store,'get_conn',return_value=w),self.assertRaises(HTTPException) as error:
      if endpoint=='post':detect.detect_create_or_upsert({'id':'p','config':altered},uid=999999)
      else:detect.detect_put_project('p',{'config':altered},uid=999999)
     self.assertIn(error.exception.status_code,(400,409));self.assertFalse(any('UPDATE detect_projects' in x.args[0] for x in c.execute.call_args_list))
 def test_new_personal_project_discards_client_supplied_contract(self):
  from services.factor import detect_store
  w,c=self.connection(False)
  with patch.object(detect_store,'get_conn',return_value=w),patch.object(detect_store,'_row_project',side_effect=lambda row:row):
   detect_store.upsert_project(999999,{'id':'new','config':{'researchPlan':{'hypothesis':'personal','researchContract':contract()},'universe':'CSI300'}})
  insert=next(x for x in c.execute.call_args_list if 'INSERT INTO detect_projects' in x.args[0]);saved=json.loads(insert.args[1][5]);self.assertNotIn('researchContract',saved['researchPlan']);self.assertEqual(saved['universe'],'CSI300')

class AdviceTests(unittest.TestCase):
 def test_pending_adoption_requires_actual_completion(self):
  from services.quant_factor.research_advice import decisions_after_result
  advice=[{'id':'a','status':'pending','input':{'message':'only past close'}}]
  p={'advice_decisions':[{'advice_id':'a','status':'adopted','reason':'included in saved proposal'}]}
  self.assertEqual(decisions_after_result(advice,p,{'status':'stopped'})[0]['status'],'pending')
  self.assertEqual(decisions_after_result(advice,p,{'status':'completed'})[0]['status'],'adopted')
  self.assertEqual(advice[0]['status'],'pending')
 def test_advice_schema_never_can_change_contract_or_counts(self):
  with self.assertRaises(ValueError):rm.AdviceDecision.model_validate({'advice_id':'a','status':'adopted','reason':'test','k':0})

class ImplementationContractTests(unittest.TestCase):
 def test_new_implementation_uses_explicit_role_and_rejects_actual_extra_field(self):
  from services.quant_factor import generation
  body={'prompt':'按固定定义实现过去价格截面排序','context':{'custom_source_contract':'quant-panel-causal-v1'},'idempotency_key':'00000000-0000-4000-8000-000000000001'}
  raw={'factor':{'factor_name':'f','factor_code':'def f(self): return self.turnover.rank(axis=1,pct=True)'},'errors':[]}
  with patch.object(generation.model_budget,'run',return_value={'data':raw,'model':'same-existing-model'}) as model,self.assertRaisesRegex(ValueError,'turnover'):
   generation.generate(999999,999998,'p','job',body,research_contract=contract(),method_snapshot=rm.snapshot())
  self.assertEqual(model.call_args.args[4],rm.IMPLEMENTER);self.assertEqual(model.call_count,1)
 def test_default_public_prompt_limit_unchanged(self):
  from services.core.ai_factor_input import factor_prompt_error
  from app.routers.ai_factor_generation import _validate
  self.assertIsNotNone(factor_prompt_error('x'*2001));self.assertIsNone(factor_prompt_error('x'*2001,max_chars=12000))


class ProposalAndControllerBoundaryTests(unittest.TestCase):
 def test_generation_rejects_field_outside_selected_proposal_even_if_contract_allows(self):
  from services.quant_factor import generation
  body={'prompt':'明确仅用过去收盘价的研究假设','context':{'custom_source_contract':'quant-panel-causal-v1'},'idempotency_key':'00000000-0000-4000-8000-000000000002'}
  raw={'factor':{'factor_name':'f','factor_code':'def f(self): return self.volume.rank(axis=1,pct=True)'},'errors':[]}
  with patch.object(generation.model_budget,'run',return_value={'data':raw,'model':'same-model'}),self.assertRaisesRegex(ValueError,'研究提案'):
   generation.generate(999999,999998,'p','job',body,research_contract=contract(),proposal={'required_fields':['close']},method_snapshot=rm.snapshot())
 def test_nonempty_proposal_mechanism_and_falsification_are_required(self):
  p={'action':'run_test','hypothesis':'new research','mechanism':'mechanism','required_fields':['close'],'change_scope':'initial','expected_effect':'expected','falsification':'fails IC','evidence_refs':[],'rationale':'bounded evidence based test','title':'test','stop_reason':''}
  for field,value in [('mechanism',' '),('required_fields',[]),('expected_effect',''),('falsification','')]:
   with self.subTest(field=field),self.assertRaisesRegex(ValueError,'提案须声明'):rm.parse_proposal(json.dumps({**p,field:value}),contract(),[])
 def test_old_controller_cannot_enqueue_or_execute_new_f3_after_pause(self):
  from services.quant_factor.agent_jobs import _check_controller
  from unittest.mock import MagicMock
  c=MagicMock();c.execute.return_value=c;controller={'run_id':'run','worker_epoch':'old','control_epoch':'e1'}
  valid={'status':'running','topic_status':'active','decision':{'runner_epoch':'old'},'config':{'v5ControlEpoch':'e1'}}
  c.fetchone.return_value=valid;_check_controller(c,999999,999998,'p',controller)
  for override in ({'topic_status':'paused'},{'status':'stopped'},{'decision':{'runner_epoch':'new'}},{'config':{'v5ControlEpoch':'e2'}}):
   c.fetchone.return_value={**valid,**override}
   with self.assertRaisesRegex(ValueError,'未发新的自动实现'):_check_controller(c,999999,999998,'p',controller)


class ExactRevisionIntegrationTests(unittest.TestCase):
 def test_selected_proposal_reaches_f3_and_saved_branch_without_assistant_rewrite(self):
  import hashlib
  from unittest.mock import MagicMock
  from contextlib import nullcontext
  from services.quant_factor import f0_agent as agent
  parent=candidate();new_source=SOURCE.replace('shift(1)','shift(2)')
  plan={**snap()['plan'],'revision':'fixed','hypothesis':'old','acceptance':'fixed gate','maxTrials':4,'rules':RULES}
  project={'id':'p','name':'test','config':{'researchPlan':plan,'draftFactor':{'name':'f','body':SOURCE},'factorCodes':['f'],'v5ActiveBranch':'h1','v5ControlEpoch':'epoch'}}
  decision=agent.Decision(action='revise',branch_id='h1',rationale='E1 shows insufficient significance',next_hypothesis='只改变过去窗口的已选完整假设',change_scope='one lag change',title='单一改动',proposal={'required_fields':['close']},binding={'parent_candidate_id':'c1','parent_snapshot_hash':'sha','parent_branch_id':'h1','parent_source_hash':hashlib.sha256(SOURCE.encode()).hexdigest()})
  c=MagicMock();c.execute.return_value.fetchone.return_value={'hypothesis_version':1,'implementation_version':1}
  ready={'id':'job','status':'ready','output':{'fields':{'name':'f','code':new_source}}}
  with patch.object(agent,'get_project',return_value={'project':project}),patch.object(agent.service.store,'read',return_value=parent),patch.object(agent.assistant,'suggest',side_effect=AssertionError('semantic rewrite forbidden')) as assistant,patch.object(agent,'_phase'),patch.object(agent.agent_jobs,'create',return_value=ready) as generate,patch.object(agent,'_equivalent_candidate',return_value=None),patch.object(agent,'_writable_project',return_value=nullcontext(c)),patch.object(agent,'_save_generated') as save,patch.object(agent,'_run_test',return_value={'id':'new-candidate','status':'development_failed'}) as market:
   result=agent._revise(999999,999998,'p','h1',decision,'run','topic',worker_epoch='worker',decision_step=2)
  assistant.assert_not_called();self.assertEqual(generate.call_args.args[4]['hypothesis'],decision.next_hypothesis);self.assertEqual(generate.call_args.args[4]['code'],SOURCE);self.assertEqual(save.call_args.args[3]['researchPlan']['hypothesis'],decision.next_hypothesis);self.assertEqual(result['candidate_id'],'new-candidate');market.assert_called_once()


class ParentFactsTests(unittest.TestCase):
 def test_parent_deltas_only_for_matching_frozen_conditions(self):
  parent=candidate();new=copy.deepcopy(parent);new['id']='c2';new['snapshot']['request']['factor_code']=SOURCE.replace('shift(1)','shift(2)');new['evidence']['development']['gate']['checks'][0]['actual']=1.7
  compared=dd.parent_comparison(new,parent);self.assertTrue(compared['same_execution_conditions']);self.assertAlmostEqual(compared['gate_changes'][0]['change'],1.7-1.63461);self.assertTrue(compared['source_changed'])
  new['snapshot']['request']['groups']=10;compared=dd.parent_comparison(new,parent);self.assertFalse(compared['same_execution_conditions']);self.assertEqual(compared['gate_changes'],[])
