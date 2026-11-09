"""CR-095 isolated fixtures: no model, backtest or live database calls."""
import copy
import math
import unittest
from unittest.mock import MagicMock,patch
from services.quant_factor import assets
from services.quant_factor.policy import digest,WorkflowError,snapshot
from services.quant_factor.novelty import comparison_request
from services.quant_factor.novelty_policy import DEFAULTS


def fixture(kind='discovery'):
    rules={'minSignedIc':.005,'maxDrawdown':.5,'minObservations':60,'direction':'positive','icMetric':'rank_ic'}
    snap={'name':'隔离固定候选','request':{'factor_name':'known','library_name':'lib','universe':'CSI500'},'rules':rules,
          'plan':{'hypothesis':'用于隔离测试的假设','researchPurpose':kind,'developmentStart':'2023-01-01','developmentEnd':'2023-03-31','validationStart':'2023-04-01','validationEnd':'2023-06-30','noveltyPolicy':{'scope':'all_accessible',**DEFAULTS}}}
    project={'id':'project','name':'隔离固定候选','config':{'factorCodes':['known'],'factorLibraries':{'known':'lib'},'universe':'CSI500','benchmark':'CSI500','researchPlan':{**snap['plan'],'revision':'plan-v1','acceptance':'固定测试门槛','target':'未来1日收益','frequency':'daily','maxTrials':2,'rules':rules}}}
    snap=snapshot(project)
    def result(spec):
        return {'meta':{'data_release_id':'data','factor_source_hash':'source','spec_hash':spec},'metrics':{'rank_ic':.03,'max_drawdown':-.1},'factor_analysis':{'rank_ic_series':[{'value':.03+.01*math.sin(i)} for i in range(70)]}}
    dev=result('development');sealed_result=result('sealed')
    refs={'hash':'catalog','count':1,'scope':'complete isolated fixture catalog','builtins':[{'library_name':'lib','factor_name':'baseline'}],'owned':[]}
    payload=comparison_request(snap,dev,refs,DEFAULTS)
    comparison={'reference_id':'lib:baseline','status':'succeeded','source_hash':'reference','mean_abs_spearman':.2 if kind=='discovery' else 1.,'valid_days':70,'min_pairs':40,'coverage':1.}
    n={'reference_hash':'catalog','reference_count':1,'gate':{'expected_count':1},'comparisons':[comparison],
       'meta':{'request_hash':digest(payload),'candidate_backtest_spec_hash':'development','reference_source_hash':digest([('lib:baseline','reference')]),'data_release_id':'data','candidate_source_hash':'source','spec_hash':'comparison'}}
    sha=digest(snap)
    row={'id':'candidate','user_id':5,'org_id':2,'project_id':'project','status':'development_passed','snapshot_hash':sha,'snapshot':snap,
         'archive':{'review':{'status':'requested','purpose':'research_admission','assigned_to':9}},
         'evidence':{'method':{'method_id':'isolated-method','method_version':'test-v1','contract_version':'test-contract','code_revision':'fixture-code','config_digest':sha},'library_reference':refs,'development':{'report_id':'qf_candidate_development','run_id':'dev-run','result':dev,'novelty':n}}}
    execution={'snapshot_hash':sha,'job_mode':'isolated-test'}
    row['evidence']['method'].update(execution_config=execution,execution_config_digest=digest(execution))
    facts={'topic':{'id':'topic','policy_version':'policy-v1','primary_holding_period':1,'max_trials':2,'view_id':'view'},'current_hash':sha,'inflight':0,
           'trials':[{'trial_no':1,'report_id':'qf_candidate_development','outcome':'passed','kind':'research','holding_period':1,'returned_metrics':True}],
           'sealed':{'topic_id':'topic','snapshot_hash':sha,'status':'passed','report_id':'sealed_report','view_id':'view','result':{'run_id':'seal-run','result':sealed_result}}}
    facts['project']=project
    return row,facts


class AdmissionEvidenceTests(unittest.TestCase):
    def test_complete_discovery_and_replication_have_distinct_kinds(self):
        for kind in ('discovery','replication'):
            row,facts=fixture(kind);out=assets.validate_evidence(row,facts)
            self.assertEqual(out['kind'],kind);self.assertEqual(out['k'],1)
    def test_invalid_or_incomplete_evidence_is_rejected(self):
        changes=[lambda r,f:f.update(unrecorded_metrics=1),lambda r,f:f.update(inflight=1),lambda r,f:f.update(current_hash='changed'),
                 lambda r,f:f['sealed'].update(status='failed'),lambda r,f:f['sealed'].update(snapshot_hash='other'),
                 lambda r,f:r['evidence'].pop('method'),lambda r,f:r['evidence']['development']['novelty'].update(diagnostic=True),
                 lambda r,f:r['evidence']['development']['novelty']['comparisons'][0].update(mean_abs_spearman=.7),
                 lambda r,f:r['evidence']['development']['novelty'].update(reference_count=2),
                 lambda r,f:f['trials'].clear(),lambda r,f:r['evidence']['development']['result']['metrics'].update(max_drawdown=-.9)]
        for change in changes:
            with self.subTest(change=change):
                row,facts=fixture();change(row,facts)
                with self.assertRaises((WorkflowError,ValueError)):assets.validate_evidence(row,facts)
    def test_gate_booleans_cannot_override_failed_real_numbers(self):
        row,facts=fixture();row['evidence']['development']['gate']={'passed':True}
        row['evidence']['development']['result']['metrics']['rank_ic']=0
        with self.assertRaisesRegex(WorkflowError,'硬门槛'):assets.validate_evidence(row,facts)
    def test_comparison_result_hash_must_match_fixed_request(self):
        row,facts=fixture();row['evidence']['development']['novelty']['meta']['request_hash']='wrong'
        with self.assertRaisesRegex(WorkflowError,'固定输入'):assets.validate_evidence(row,facts)


class AtomicRegistrationTests(unittest.TestCase):
    def approve(self,row,facts,uid=9):
        c=MagicMock();c.execute.return_value.fetchone.side_effect=[{'user_id':row['user_id'],'project_id':row['project_id']},{'id':'topic'},row]
        conn=MagicMock();conn.__enter__.return_value=c
        with patch.object(assets,'get_conn',return_value=conn),patch.object(assets,'eligibility',return_value=assets.validate_evidence(row,facts)):
            out=assets.approve(uid,2,'candidate','独立核验全部冻结证据',{'display_name':'测试资产','category':'反转因子','tags':['日频']},True)
        return out,c,conn
    def test_one_update_records_approval_asset_and_event_together(self):
        row,facts=fixture();out,c,conn=self.approve(row,facts)
        updates=[x for x in c.execute.call_args_list if x.args[0].startswith('UPDATE')]
        self.assertEqual(len(updates),1);self.assertEqual(out['id'],'qfa_candidate');self.assertEqual(out['purpose'],'research_only')
        self.assertIn('research_asset_registered',updates[0].args[1][1]);self.assertIn('approve_research_and_register',updates[0].args[1][0])
        self.assertNotIn('user_id',out);self.assertNotIn('events',out)
    def test_replication_is_a_validation_record_not_a_new_factor(self):
        out,_,_=self.approve(*fixture('replication'))
        self.assertEqual(out['id'],'qfr_candidate');self.assertEqual(out['kind'],'replication_validation')
    def test_self_or_unassigned_or_feedback_cannot_approve(self):
        for mutate,uid in [(lambda r:r.update(user_id=9),9),(lambda r:r['archive']['review'].pop('assigned_to'),9),(lambda r:r['archive']['review'].update(purpose='research_feedback_only'),9),(lambda r:r['archive']['review'].update(purpose='seal_failed_review'),9)]:
            row,facts=fixture();mutate(row)
            with self.subTest(row=row),self.assertRaises(WorkflowError):self.approve(row,facts,uid)
    def test_registration_serialization_failure_leaves_no_update(self):
        row,facts=fixture();c=MagicMock();c.execute.return_value.fetchone.side_effect=[{'user_id':row['user_id'],'project_id':row['project_id']},{'id':'topic'},row];conn=MagicMock();conn.__enter__.return_value=c
        with patch.object(assets,'get_conn',return_value=conn),patch.object(assets,'eligibility',return_value=assets.validate_evidence(row,facts)),patch.object(assets.store,'encode',side_effect=ValueError('encoding failed')):
            with self.assertRaises(ValueError):assets.approve(9,2,'candidate','依据',{'display_name':'资产','category':'反转因子','tags':[]},True)
        self.assertFalse(any(x.args[0].startswith('UPDATE') for x in c.execute.call_args_list))
        self.assertIs(conn.__exit__.call_args.args[0],ValueError)
    def test_replay_returns_same_registered_asset_without_new_decision(self):
        row,facts=fixture();asset,_,_=self.approve(row,facts);row['archive'].update(research_asset=asset);row['archive']['review'].update(decision='approve_research_and_register',status='reviewed')
        c=MagicMock();c.execute.return_value.fetchone.return_value=row;conn=MagicMock();conn.__enter__.return_value=c
        with patch.object(assets,'get_conn',return_value=conn),patch.object(assets,'eligibility') as eligibility,patch.object(assets,'detail',return_value=asset):
            out=assets.approve(9,2,'candidate','相同请求重试',{'display_name':'资产','category':'反转因子','tags':[]},True)
        self.assertEqual(out['id'],asset['id']);eligibility.assert_not_called()
        self.assertFalse(any(x.args[0].startswith('UPDATE') for x in c.execute.call_args_list))
    def test_asset_serialize_rejects_cross_org_and_modified_snapshot(self):
        row,facts=fixture();out,_,_=self.approve(row,facts)
        with self.assertRaises(KeyError):assets.serialize(out,99)
        out['hypothesis']='changed'
        with self.assertRaises(WorkflowError):assets.serialize(out,2)
