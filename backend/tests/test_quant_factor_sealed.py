"""Sealed orchestration isolation: substitutes persistence and HTTP, no real RE jobs."""
import copy
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock,patch
from services.quant_factor import sealed
from services.quant_factor.policy import WorkflowError,digest

REQUEST={'factor_name':'f','factor_code':'def f(self): return self.close','start':'2025-01-01','end':'2025-03-31'}
EXPECTED={'data_release_id':'frozen-data','factor_source_hash':'frozen-source','spec_hash':'heldout-spec'}
TARGET={'base':'http://127.0.0.1:18804','service':'ResearchEngine','service_version':'fixture','method_version':'fixture','method_code_hash':'a'*64,'policy_hash':'b'*64}
RECEIPT={'allowed':True,'service_version':'fixture','version':'fixture','method_code_hash':'a'*64,'policy_hash':'b'*64}
SNAP={'rules':{},'request':REQUEST,'plan':{}}
INTENT={'compute_backend':TARGET,'schema':sealed.INTENT_SCHEMA,'request':REQUEST,'request_hash':digest(REQUEST),'expected_identity':EXPECTED,'snapshot_hash':digest(SNAP),'topic_id':'t1'}
ROW={'id':'s1','candidate_id':'c1','user_id':1,'org_id':2,'topic_id':'t1','status':'queued','snapshot_hash':INTENT['snapshot_hash'],'result':{'intent':INTENT},'trial_ids':['t1']}

class SealedTest(unittest.TestCase):
 def test_detail_masks_full_result_from_researcher(self):
  row={**ROW,'result':{'gate':{'passed':True},'confirmation':'pending','message':'继续核对原任务'}}
  c=MagicMock();c.execute.return_value.fetchone.return_value=row;conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(sealed,'get_conn',return_value=conn):
   masked=sealed.detail(1,2,'c1',False);full=sealed.detail(99,2,'c1',True)
  self.assertNotIn('result',masked);self.assertEqual(full['result'],row['result']);self.assertEqual(masked['confirmation'],'pending')
  self.assertEqual(c.execute.call_args.args[1],('c1',2))
 def test_request_replays_existing_before_quota_or_development_check(self):
  @contextmanager
  def locked(*args):yield MagicMock(),{'status':'development_failed'},{'max_sealed':0},None,copy.deepcopy(ROW)
  with patch.object(sealed,'_locked',locked),patch.object(sealed,'_check_new') as new,patch.object(sealed.POOL,'submit') as submit:
   self.assertEqual(sealed.request(1,2,'c1')['id'],'s1')
  new.assert_not_called();submit.assert_called_once()
 def test_unknown_submission_replay_does_not_schedule_another_post(self):
  row=copy.deepcopy(ROW);row.update(status='error',result={**row['result'],'submission_started':True,'confirmation':'pending'})
  @contextmanager
  def locked(*args):yield MagicMock(),{}, {},None,row
  with patch.object(sealed,'_locked',locked),patch.object(sealed.POOL,'submit') as submit:
   self.assertEqual(sealed.request(1,2,'c1')['id'],'s1')
  submit.assert_not_called()
 def test_old_research_visible_validation_blocks_independent_plan(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'id':'legacy-candidate'}
  with self.assertRaisesRegex(WorkflowError,'已有研究侧样本外'):sealed._assert_unexposed(c,1,2,{'project_id':'p'})
 def test_result_requires_pre_submission_data_source_and_spec(self):
  sealed._confirm_result({'meta':EXPECTED},INTENT)
  for key in EXPECTED:
   with self.subTest(key=key),self.assertRaisesRegex(WorkflowError,'身份'):
    sealed._confirm_result({'meta':{**EXPECTED,key:'changed'}},INTENT)
  with self.assertRaisesRegex(WorkflowError,'旧封存'):sealed._confirm_result({'meta':EXPECTED},{})

class SealedRunTest(unittest.TestCase):
 def execute(self,block=None,poll=None,submit=None):
  row=copy.deepcopy(ROW);row['result']=copy.deepcopy(block if block is not None else ROW['result']);writes=[]
  snap=copy.deepcopy(SNAP);cand={'snapshot':snap,'snapshot_hash':digest(snap),'evidence':{}}
  c=MagicMock();c.execute.return_value.fetchall.return_value=[]
  @contextmanager
  def locked(*args):yield c,cand,{'id':'t1','primary_holding_period':1,'status':'active'}, {'id':'p'},row
  def persist(uid,org,cid,sid,status,block,report_id=None):writes.append((status,copy.deepcopy(block)));return True
  with patch.object(sealed,'_read',return_value=row),patch.object(sealed,'_candidate',return_value=cand),patch.object(sealed,'_locked',locked),patch.object(sealed,'_persist',side_effect=persist),patch.object(sealed,'_assert_unexposed'),patch.object(sealed,'snapshot',return_value=snap),patch.object(sealed,'_row_project',side_effect=lambda x:x),patch('services.quant_factor.causality.diagnose_source'),patch('services.quant_factor.resources.require',return_value=RECEIPT),patch.object(sealed.re_client,'base',return_value=TARGET['base']),patch.object(sealed,'proxy_submit_factor_backtest',side_effect=lambda req,**kwargs:(submit(req) if submit else (202,{}, {'run_id':'remote-1'}))) as post,patch.object(sealed,'proxy_get_factor_run',side_effect=lambda rid,**kwargs:(poll(rid) if poll else (200,{}, {'status':'succeeded','result':{'meta':EXPECTED}}))) as get,patch.object(sealed.ledger,'current_k',return_value=1),patch.object(sealed,'evaluate',return_value={'passed':True,'checks':[]}):
   sealed._run_once(1,2,'s1')
  return writes,c,post,get
 def test_ack_is_persisted_before_poll_and_result_keeps_intent(self):
  writes,c,post,get=self.execute();post.assert_called_once();get.assert_called_once_with('remote-1',target=TARGET)
  self.assertTrue(writes[0][1]['submission_started']);self.assertNotIn('run_id',writes[0][1]);self.assertEqual(writes[1][1]['run_id'],'remote-1')
  final=[a for a in c.execute.call_args_list if 'evaluated_at=NOW' in a.args[0]][-1]
  self.assertEqual(final.args[1][0],'passed');self.assertIn('quant.sealed-intent.v1',final.args[1][1])
 def test_lost_response_preserves_unknown_never_posts_on_recovery(self):
  writes,_,post,get=self.execute(submit=lambda req:(_ for _ in ()).throw(TimeoutError('response lost')))
  self.assertTrue(writes[-1][1]['submission_started']);self.assertEqual(writes[-1][1]['confirmation'],'pending');get.assert_not_called()
  _,_,post,get=self.execute(block=writes[-1][1]);post.assert_not_called();get.assert_not_called()
 def test_known_run_queries_only_and_404_preserves_identity(self):
  block={**ROW['result'],'submission_started':True,'run_id':'old-run','confirmation':'pending'}
  writes,_,post,get=self.execute(block=block,poll=lambda rid:(404,{},{}))
  post.assert_not_called();get.assert_called_once_with('old-run',target=TARGET);self.assertEqual(writes[-1][1]['run_id'],'old-run');self.assertEqual(writes[-1][1]['confirmation'],'pending')
 def test_known_failure_and_cancel_are_terminal_not_unknown(self):
  for terminal in ('failed','cancelled'):
   with self.subTest(status=terminal):
    block={**ROW['result'],'run_id':'old-run','submission_started':True,'confirmation':'pending'}
    writes,_,post,get=self.execute(block=block,poll=lambda rid:(200,{}, {'status':terminal,'error':'明确原因'}))
    post.assert_not_called();self.assertEqual(writes[-1][1]['confirmation'],terminal)
    _,_,post,get=self.execute(block=writes[-1][1]);post.assert_not_called();get.assert_not_called()
 def test_changed_identity_never_becomes_passed(self):
  writes,c,_,_=self.execute(block={**ROW['result'],'run_id':'old-run'},poll=lambda rid:(200,{}, {'status':'succeeded','result':{'meta':{**EXPECTED,'spec_hash':'wrong'}}}))
  self.assertEqual(writes[-1][0],'error');self.assertFalse(any('evaluated_at=NOW' in x.args[0] for x in c.execute.call_args_list))

class SealedControlTests(unittest.TestCase):
 def test_paused_topic_rejects_new_seal_before_any_evidence_or_submit(self):
  with self.assertRaisesRegex(WorkflowError,'暂停'):sealed._require_controller(MagicMock(),1,2,{'status':'paused'},{'run_id':'old','worker_epoch':'old'})
 def test_superseded_f0_rejects_new_seal_inside_request_lock(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value=None
  @contextmanager
  def locked(*args):yield c,{'project_id':'p'},{'status':'active','project_id':'p'},None,None
  with patch.object(sealed,'_locked',locked),patch.object(sealed,'_check_new') as check,patch.object(sealed.POOL,'submit') as submit,self.assertRaisesRegex(WorkflowError,'控制版本'):sealed.request(1,2,'c','old','old-epoch')
  check.assert_not_called();submit.assert_not_called()

 def test_manual_explicit_request_does_not_require_automatic_worker_or_active_topic(self):
  c=MagicMock();c.execute.return_value.fetchone.side_effect=[{'n':0},{**ROW,'id':'manual'}]
  @contextmanager
  def locked(*args):yield c,{'project_id':'p','snapshot_hash':'fixed'},{'status':'paused','id':'t','max_sealed':1,'view_id':'v'},None,None
  with patch.object(sealed,'_locked',locked),patch.object(sealed,'_check_new',return_value=({},[])),patch.object(sealed,'_require_controller') as guard,patch.object(sealed.POOL,'submit'):
   self.assertEqual(sealed.request(1,2,'c')['id'],'manual')
  guard.assert_not_called()
 def test_global_pause_blocks_automatic_controller_before_worker_or_new_submission(self):
  c=MagicMock();c.execute.return_value.fetchone.return_value={'paused':True}
  with self.assertRaisesRegex(WorkflowError,'全局暂停'):sealed._require_controller(c,1,2,{'status':'active'},{'run_id':'r','worker_epoch':'e'})
 def test_post_seal_review_uses_actual_controlled_review_scope(self):
  from services.quant_factor import review
  c=MagicMock()
  @contextmanager
  def locked(*args):yield c,{}, {'status':'paused'},None,None
  with patch.object(sealed,'_locked',locked),self.assertRaisesRegex(WorkflowError,'暂停'):review.request_review(1,2,'c','问题',controller={'run_id':'old','worker_epoch':'old'})
  c.execute.assert_not_called()
