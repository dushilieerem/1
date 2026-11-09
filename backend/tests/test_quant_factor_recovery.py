"""Isolated recovery/cancellation tests; network and persistence are explicit substitutes."""
import copy
import unittest
from unittest.mock import MagicMock,patch
from services.quant_factor import service,f0,review
from services.quant_factor.policy import WorkflowError
from tests.test_quant_factor_assets import fixture

class RecoveryTests(unittest.TestCase):
    def state(self,block=None):
        row,_=fixture();row['status']='development_error';row['archive']={};row['snapshot']['plan']['researchPurpose']='legacy'
        result=copy.deepcopy(row['evidence']['development']['result'])
        row['evidence']['development']=copy.deepcopy(block or {})
        return row,result
    def execute(self,state,result,recovery_only=False,update_hook=None,get_hook=None):
        writes=[]
        def read(*args):return copy.deepcopy(state)
        def update(uid,org,cid,status,event,evidence=None):
            writes.append((status,event))
            if update_hook is not None:
                special=update_hook(status,event,evidence)
                if special is not None:return special
            if state['status']=='cancelled':return False
            state['status']=status;state['evidence'].update(copy.deepcopy(evidence or {}));return True
        cursor=MagicMock();cursor.execute.return_value.fetchone.side_effect=lambda:{'status':state['status']}
        conn=MagicMock();conn.__enter__.return_value=cursor
        with patch.object(service.store,'read',side_effect=read),patch.object(service.store,'update',side_effect=update),patch.object(service,'get_conn',return_value=conn),patch.object(service,'proxy_submit_factor_backtest',return_value=(202,{}, {'run_id':'new-run'})) as submit,patch.object(service,'proxy_get_factor_run',side_effect=get_hook or (lambda rid:(200,{}, {'run_id':rid,'status':'succeeded','result':result}))) as poll,patch.object(service,'proxy_cancel_factor_run') as cancel,patch.object(service,'save_run'),patch.object(service,'_gate_k',return_value=1),patch.object(service,'_append_development_trial') as append,patch.object(service,'_compare_library') as compare:
            service._run_once(5,2,'candidate','development',recovery_only=recovery_only)
        return submit,poll,cancel,append,compare,writes
    def test_known_remote_run_is_polled_not_resubmitted(self):
        state,result=self.state({'run_id':'original','interrupted':True});submit,poll,_,append,_,_=self.execute(state,result)
        submit.assert_not_called();poll.assert_called_once_with('original');append.assert_called_once()
    def test_saved_numerical_result_is_reused_without_remote_call(self):
        state,result=self.state();state['evidence']['development']={'run_id':'original','result':result}
        submit,poll,_,append,_,_=self.execute(state,result)
        submit.assert_not_called();poll.assert_not_called();append.assert_called_once()
    def test_unknown_submit_response_never_blindly_resubmits(self):
        state,result=self.state({'submission_started':True});submit,poll,_,append,_,_=self.execute(state,result)
        submit.assert_not_called();poll.assert_not_called();append.assert_not_called();self.assertEqual(state['status'],'development_error')
    def test_known_external_failure_is_terminal_not_unknown(self):
        for terminal in ('failed','cancelled'):
            with self.subTest(status=terminal):
                state,result=self.state({'run_id':'original','interrupted':True})
                submit,poll,_,append,_,_=self.execute(state,result,get_hook=lambda rid:(200,{}, {'status':terminal,'error':'明确原因'}))
                submit.assert_not_called();append.assert_not_called();self.assertEqual(poll.call_count,1)
                self.assertFalse(state['evidence']['development']['interrupted'])
                self.assertEqual(state['evidence']['development']['external_status'],terminal)
                self.assertIn('明确原因',state['evidence']['development']['message'])
    def test_recovery_does_not_relabel_confirmed_failure_as_unknown(self):
        state,_=self.state({'run_id':'original','external_status':'failed','interrupted':False,'message':'外部计算已失败'})
        c=MagicMock();c.execute.return_value.fetchall.return_value=[{'id':'candidate'}]
        conn=MagicMock();conn.__enter__.return_value=c
        with patch.object(service,'get_conn',return_value=conn),patch.object(service,'run'),patch.object(service.store,'read',return_value=state):
            service.recover_pending(5,2,'project')
    def test_cancelled_before_start_never_calls_compute(self):
        state,result=self.state();state['status']='cancelled';submit,poll,_,_,_,_=self.execute(state,result)
        submit.assert_not_called();poll.assert_not_called()
    def test_cancel_before_submit_blocks_external_call(self):
        state,result=self.state()
        def hook(status,event,evidence):
            if event['action']=='development_submitting':state['status']='cancelled';return False
        submit,_,_,_,_,_=self.execute(state,result,update_hook=hook);submit.assert_not_called();self.assertEqual(state['status'],'cancelled')
    def test_cancel_after_accept_requests_remote_cancel_and_keeps_terminal(self):
        state,result=self.state()
        def hook(status,event,evidence):
            if event['action']=='development_submitted':state['status']='cancelled';return False
        submit,poll,cancel,_,_,_=self.execute(state,result,update_hook=hook)
        submit.assert_called_once();cancel.assert_called_once_with('new-run');poll.assert_not_called();self.assertEqual(state['status'],'cancelled')
    def test_poll_exception_cannot_revive_cancelled_candidate(self):
        state,result=self.state({'run_id':'original'})
        def poll(rid):state['status']='cancelled';raise RuntimeError('lost response')
        _,_,cancel,_,_,writes=self.execute(state,result,get_hook=poll)
        self.assertEqual(state['status'],'cancelled');cancel.assert_called_once_with('original');self.assertFalse(any(s=='development_error' for s,e in writes))
    def test_historical_recovery_requires_known_identity_and_never_compares(self):
        state,result=self.state({'run_id':'original'});submit,_,_,append,compare,_=self.execute(state,result,recovery_only=True)
        submit.assert_not_called();append.assert_not_called();compare.assert_not_called();self.assertIn('缺少可核对',state['evidence']['development']['message'])
    def test_verified_original_result_is_retained_without_new_research(self):
        state,result=self.state({'run_id':'original'});state['evidence']['development']['expected_identity']=copy.deepcopy(result['meta'])
        submit,_,_,append,compare,_=self.execute(state,result,recovery_only=True)
        submit.assert_not_called();compare.assert_not_called();append.assert_called_once();self.assertTrue(state['evidence']['development']['needs_fixed_version'])
    def test_mismatched_original_result_is_not_merged(self):
        state,result=self.state({'run_id':'original','expected_identity':{'data_release_id':'wrong','factor_source_hash':'source','spec_hash':'development'}})
        submit,_,_,append,_,_=self.execute(state,result)
        submit.assert_not_called();append.assert_not_called();self.assertIn('身份不一致',state['evidence']['development']['message'])

class RegisteredReviewGuardTest(unittest.TestCase):
    def test_registered_candidate_cannot_open_another_review(self):
        row,_=fixture();row['archive']['research_asset']={'id':'qfa_candidate'}
        c=MagicMock();c.execute.return_value.fetchone.return_value=row;conn=MagicMock();conn.__enter__.return_value=c
        with patch.object(review,'get_conn',return_value=conn),self.assertRaisesRegex(WorkflowError,'已登记'):
            review.request_review(5,2,'candidate','再次提交','research_admission')
        self.assertFalse(any(call.args[0].startswith('UPDATE') for call in c.execute.call_args_list))
