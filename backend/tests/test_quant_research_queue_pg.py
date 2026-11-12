"""Own-schema real transactions: root contention, children, restart and unknown occupancy."""
import os,threading,json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from services.quant_factor import research_queue as q,model_budget as b,f0,repo
from services.quant_factor.policy import WorkflowError
from tests.test_quant_model_budget_pg import IsolatedBudgetPostgresTests

class IsolatedQueueTests(IsolatedBudgetPostgresTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  try:
   with cls.connection() as c:
    c.execute((Path(__file__).parents[1]/'migrations/0040_quant_research_queue.sql').read_text())
    c.execute('CREATE TABLE quant_factor_org_controls(org_id bigint,paused boolean)')
  except BaseException:cls.tearDownClass();raise
 def setUp(self):
  super().setUp()
  for target,name,value in [(q,'get_conn',self.connection),(q,'DEPLOYMENT_ID','owned-fixture:'+self.schema),(f0,'get_conn',self.connection),(repo,'get_conn',self.connection)]:
   guard=patch.object(target,name,value);guard.start();self.addCleanup(guard.stop)
  guard=patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'1'});guard.start();self.addCleanup(guard.stop)
  with self.connection() as c:c.execute('TRUNCATE quant_research_queue_slots,quant_research_queue_jobs CASCADE')
 def add(self,obj,kind='f0'):
  with self.connection() as c:return q.enqueue(c,kind,obj,self.uid,self.org)
 def queue_row(self,job):
  with self.connection() as c:return dict(c.execute('SELECT * FROM quant_research_queue_jobs WHERE id=%s',(job['id'],)).fetchone())
 def test_two_database_claimants_get_one_root_and_children_can_run_while_parent_waits(self):
  first=self.add('first');second=self.add('second');barrier=threading.Barrier(2)
  def contender(_):barrier.wait(timeout=2);return q.claim()
  with ThreadPoolExecutor(max_workers=2) as pool:claimed=list(pool.map(contender,[0,1]))
  parent=next(j for j in claimed if j);self.assertEqual(sum(j is not None for j in claimed),1);self.assertEqual(parent['id'],first['id'])
  created=threading.Event();finished=threading.Event();result=[]
  def handler(job):
   with self.connection() as c:result.append(q.enqueue(c,'agent','child',self.uid,self.org))
   created.set();self.assertTrue(finished.wait(3))
  with ThreadPoolExecutor(max_workers=1) as pool:
   future=pool.submit(q.run_job,parent,handler);self.assertTrue(created.wait(2));child=q.claim()
   self.assertEqual(child['root_id'],parent['id']);self.assertEqual(child['parent_id'],parent['id']);self.assertIsNone(q.claim())
   q.run_job(child,lambda j:None);finished.set();future.result(timeout=3)
  self.assertEqual(q.claim()['id'],second['id'])
 def test_unknown_physical_call_blocks_other_children_and_roots_until_receipt_arrives(self):
  first=self.add('first',kind='agent');other=self.add('other');parent=q.claim();saved=[]
  def handler(job):
   with self.connection() as c:q.enqueue(c,'agent','unstarted-child',self.uid,self.org)
   row=b.reserve(self.uid,self.org,'project','unknown-call','quant.factor.research_assistant','fixed',100,3000);saved.append(row)
   b.claim(self.uid,self.org,row['id']);b.unresolved(self.uid,self.org,row['id'],'lost ack')
  q.run_job(parent,handler)
  self.assertEqual(self.queue_row(parent)['status'],'waiting');self.assertIsNone(q.claim())
  # A late usable response with missing usage proves no active model operation;
  # unresolved accounting remains held, but must not be treated as active work.
  b.settle(self.uid,self.org,saved[0]['id'],{'content':'finished, usage unavailable'})
  q.reconcile_waiting();child=q.claim();self.assertEqual(child['object_id'],'unstarted-child');q.run_job(child,lambda j:None)
  self.assertEqual(q.claim()['id'],other['id'])
  with self.connection() as c:self.assertEqual(c.execute('SELECT status FROM quant_ai_budget_calls WHERE id=%s',(saved[0]['id'],)).fetchone()['status'],'unresolved')
 def test_restart_preserves_queued_and_reclaims_only_proved_dead_owned_owner(self):
  first=self.add('first');second=self.add('second');running=q.claim()
  with self.connection() as c:c.execute("UPDATE quant_research_queue_jobs SET owner_instance='old',owner_pid=2147483000,owner_start='gone' WHERE id=%s",(running['id'],))
  with patch.object(q,'DEPLOYMENT_ID','foreign-deployment'):
   foreign=self.add('foreign');foreign_run=q.claim()
   with self.connection() as c:c.execute("UPDATE quant_research_queue_jobs SET owner_instance='old',owner_pid=2147483000,owner_start='gone' WHERE id=%s",(foreign_run['id'],))
  result=q.recover_owned();self.assertEqual(result,{'requeued':0,'waiting_confirmation':0,'waiting_checkpoint':1});self.assertEqual(self.queue_row(second)['status'],'queued');self.assertEqual(self.queue_row(foreign)['status'],'running')
  self.assertEqual(self.queue_row(first)['status'],'waiting');q.reconcile_waiting();self.assertEqual(q.claim()['id'],second['id'])
 def test_checkpoint_only_waiting_root_does_not_starve_the_next_root(self):
  first=self.add('first');second=self.add('second');running=q.claim()
  with self.connection() as c:c.execute("UPDATE quant_research_queue_jobs SET owner_instance='old',owner_pid=2147483000,owner_start='gone' WHERE id=%s",(running['id'],))
  q.recover_owned()
  self.assertEqual(self.queue_row(first)['status'],'waiting')
  # No physical call was made, so the old checkpoint releases the one slot.
  self.assertEqual(q.claim()['id'],second['id'])
 def test_operator_abandoned_unconfirmed_call_releases_root_after_restart(self):
  first=self.add('first',kind='agent');second=self.add('second');parent=q.claim();saved=[]
  def handler(job):
   row=b.reserve(self.uid,self.org,'project','lost-receipt','quant.factor.research_assistant','fixed',100,3000);b.claim(self.uid,self.org,row['id']);saved.append(row)
  q.run_job(parent,handler)
  self.assertEqual(self.queue_row(parent)['status'],'waiting');self.assertIsNone(q.claim())
  b.abandon_unconfirmed(self.uid,self.org,saved[0]['id'],'BFF process restarted before receipt','test-operator')
  q.recover_owned()
  self.assertEqual(q.claim()['id'],second['id'])
 def test_foreign_host_owner_is_not_left_pinned_forever(self):
  first=self.add('first');second=self.add('second');running=q.claim()
  with self.connection() as c:c.execute("UPDATE quant_research_queue_jobs SET owner_host='other-host',owner_instance='old',owner_pid=2147483000,owner_start='gone' WHERE id=%s",(running['id'],))
  q.recover_owned()
  self.assertEqual(self.queue_row(first)['status'],'waiting')
  self.assertEqual(q.claim()['id'],second['id'])
 def test_child_finish_resumes_a_yielded_f0_root(self):
  first=self.add('yielded-run');second=self.add('second');parent=q.claim()
  with self.connection() as c:
   c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision,rounds,stop_reason,view_id) VALUES('yielded-run',%s,%s,'project','topic','branch','yielded','queued','{\"scheduler_yield\":true}',3,'','view')",(self.uid,self.org))
  with self.connection() as c:q.enqueue(c,'agent','child',self.uid,self.org,parent=parent['id'])
  q.run_job(parent,lambda j:None)
  self.assertEqual(self.queue_row(parent)['status'],'completed')
  child=q.claim();self.assertEqual(child['object_id'],'child');q.run_job(child,lambda j:None)
  self.assertEqual(q.claim()['id'],first['id'])
 def test_old_usage_gaps_without_queue_identity_do_not_occupy_slot(self):
  with patch.dict(os.environ,{'QUANT_RESEARCH_DURABLE_QUEUE':'0'}):
   historic=b.reserve(self.uid,self.org,'project','old-gap','quant.factor.research_assistant','old',100,3000);b.claim(self.uid,self.org,historic['id']);b.unresolved(self.uid,self.org,historic['id'],'historic receipt gap')
  self.add('new');self.assertIsNotNone(q.claim())
 def test_cancel_queued_keeps_history_and_stale_owner_cannot_finish_current_job(self):
  first=self.add('first');second=self.add('second')
  with self.connection() as c:self.assertTrue(q.cancel(c,'f0','first',self.uid,self.org))
  self.assertEqual(self.queue_row(first)['status'],'cancelled');running=q.claim();self.assertEqual(running['id'],second['id'])
  stale={**running,'owner_epoch':'stale'};self.assertFalse(q.finish(stale));self.assertEqual(self.queue_row(second)['status'],'running')
 def test_resume_waiting_refusal_rolls_back_f0_status_in_same_transaction(self):
  with self.connection() as c:
   c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision,rounds,stop_reason,view_id) VALUES('resume-run',%s,%s,'project','topic','branch','same','stopped','{}',0,'technical waiting','view')",(self.uid,self.org))
   job=q.enqueue(c,'f0','resume-run',self.uid,self.org)
   c.execute("UPDATE quant_research_queue_jobs SET status='waiting' WHERE id=%s",(job['id'],))
  with patch.object(f0,'published_view',return_value={'view_id':'view'}),patch.object(f0.service,'control_status',return_value={'paused':False}),patch('services.factor.detect_store.get_project',return_value={'project':{'config':{'v5ActiveBranch':'branch'}}}),patch('services.quant_factor.resources.require_config'),patch('services.quant_factor.research_contract.project_contract',return_value=None):
   with self.assertRaisesRegex(WorkflowError,'原物理调用仍待确认'):f0.resume(self.uid,self.org,'resume-run')
  with self.connection() as c:self.assertEqual(c.execute("SELECT status FROM quant_factor_f0_runs WHERE id='resume-run'").fetchone()['status'],'stopped')
  self.assertEqual(self.queue_row(job)['status'],'waiting')
 def test_scheduler_checkpoint_yields_to_older_root_without_ending_research(self):
  first=self.add('first');other=self.add('second');running=q.claim()
  with self.connection() as c:c.execute("INSERT INTO quant_factor_f0_runs(id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,decision,rounds,stop_reason,view_id) VALUES('first',%s,%s,'project','topic','branch','slice','queued','{\"scheduler_yield\":true}',3,'','view')",(self.uid,self.org))
  self.assertTrue(q.finish(running));self.assertEqual(self.queue_row(first)['status'],'queued');self.assertGreater(self.queue_row(first)['queued_at'],self.queue_row(other)['queued_at']);self.assertEqual(q.claim()['id'],other['id'])

 def test_actual_novelty_submit_intent_blocks_slot_even_with_saved_development_result(self):
  from services.quant_factor import novelty,re_client
  root=self.add('candidate',kind='novelty');other=self.add('other');job=q.claim()
  refs={'hash':'frozen-ref','scope':'fixture','count':1,'builtins':[{'library_name':'fixture','factor_name':'fixture'}],'owned':[]}
  snap={'request':{'factor_name':'fixture','library_name':'fixture'},'plan':{'researchPurpose':'replication','developmentStart':'2025-07-01','developmentEnd':'2025-09-30'}}
  dev={'meta':{'data_release_id':'release','factor_source_hash':'source','spec_hash':'spec'}}
  def request(url,**kwargs):
   if kwargs['method']=='POST':
    self.assertEqual(self.queue_row(job)['external_calls'][0]['status'],'submitting')
    return 202,{}, {'run_id':'a'*32,'status':'queued'}
   if kwargs['method']=='DELETE':return 200,{}, {'cancel_requested':True}
   raise TimeoutError('fixture read timeout')
  out=[]
  with patch.object(novelty,'request_json',side_effect=request),patch('services.quant_factor.resources.preflight',return_value={'allowed':True}),patch.object(re_client,'base',return_value='http://fixture.invalid'):
   q.run_job(job,lambda j:out.append(novelty.assess(self.uid,snap,dev,reference=refs,org=self.org)))
  self.assertEqual(out[0]['status'],'unavailable');self.assertEqual(self.queue_row(job)['status'],'waiting');self.assertIsNone(q.claim())
  with patch.object(re_client,'request_json',return_value=(200,{}, {'status':'cancelled'})) as get:q.reconcile_waiting()
  get.assert_called_once();self.assertEqual(get.call_args.kwargs['method'],'GET');self.assertEqual(q.claim()['id'],other['id'])
 def test_actual_f0_parent_creates_agent_child_and_waits_without_changing_controller(self):
  from contextlib import ExitStack
  from services.quant_factor import agent_jobs,ledger,service
  from psycopg.types.json import Jsonb
  from services.factor import detect_store
  cfg={'v5ActiveBranch':'branch','v5ControlEpoch':'epoch','researchPlan':{'rules':{'direction':'positive','icMetric':'rank_ic'}}}
  project={'id':'project','name':'fixture','config':cfg}
  with self.connection() as c:
   c.execute('UPDATE detect_projects SET config=%s',(Jsonb(cfg),))
   c.execute("CREATE TABLE quant_factor_agent_jobs(id text PRIMARY KEY,user_id bigint,org_id bigint,project_id text,stage text,request_key text,input jsonb,status text,events jsonb,output jsonb,created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now())")
  created=threading.Event();child_done=threading.Event();captured=[]
  def tool(uid,org,run_id,topic,decision,step,worker_epoch=None):
   child=agent_jobs.create(uid,org,'F3','project',{'hypothesis':'fixture'},'stable-job',controller={'run_id':run_id,'worker_epoch':worker_epoch,'control_epoch':'epoch'})
   captured.append(child);created.set();self.assertTrue(child_done.wait(3));return {'status':'stopped','reason':'fixture completed'}
  def generate(*args,**kwargs):
   self.assertIsNotNone(q.current_id());q.require_context()
   with self.connection() as c:c.execute('INSERT INTO quant_factor_org_controls VALUES(%s,TRUE)',(self.org,))
   with self.assertRaisesRegex(WorkflowError,'自动研究已暂停'):q.require_context()
   with self.connection() as c:c.execute('DELETE FROM quant_factor_org_controls WHERE org_id=%s',(self.org,))
   return {'status':'ready','validation':{'status':'passed'},'factor':{'factor_code':'def factor(self): return self.close','factor_name':'factor'}}
  with ExitStack() as stack:
   for module,name,value in [(agent_jobs,'get_conn',self.connection),(ledger,'get_conn',self.connection),(agent_jobs,'get_project',lambda *a:{'project':project}),(agent_jobs,'assert_quota_available',lambda *a:None),(f0,'published_view',lambda:{'view_id':'view'}),(service,'control_status',lambda *a:{'paused':False}),(service,'recover_pending',lambda *a,**k:None),(service,'backfill_terminal_trials',lambda *a,**k:None),(f0.f0_agent,'_context',lambda *a:{}),(f0.f0_agent,'execute',tool),(f0.f0_agent,'decide',lambda *a:(f0.f0_agent.Decision(action='run_test',branch_id='branch',rationale='fixture'),{}))]:stack.enter_context(patch.object(module,name,value))
   stack.enter_context(patch.object(detect_store,'get_project',return_value={'project':project}));stack.enter_context(patch('services.quant_factor.resources.require_config'));stack.enter_context(patch('services.quant_factor.locked_data.for_topic',return_value={}));stack.enter_context(patch('services.quant_factor.research_contract.project_contract',return_value=None));stack.enter_context(patch('services.quant_factor.research_contract.check_project',return_value=None));stack.enter_context(patch('services.quant_factor.generation.generate',side_effect=generate));stack.enter_context(patch('services.quant_factor.causality.diagnose_source',return_value={'contract':{'fields':['close']}}))
   run=f0.start(self.uid,self.org,'topic','branch','real-entry');parent=q.claim();self.assertEqual(parent['object_id'],run['id'])
   with ThreadPoolExecutor(max_workers=1) as pool:
    future=pool.submit(q.run_job,parent,q._handler);self.assertTrue(created.wait(2));child=q.claim();self.assertEqual(child['kind'],'agent');self.assertEqual(child['root_id'],parent['id'])
    q.run_job(child,q._handler);child_done.set();future.result(timeout=3)
   self.assertEqual(agent_jobs.read(self.uid,self.org,captured[0]['id'])['status'],'ready')
  with self.connection() as c:
   state=c.execute('SELECT status,decision FROM quant_factor_f0_runs WHERE id=%s',(run['id'],)).fetchone();self.assertEqual(state['status'],'stopped')
   saved=c.execute('SELECT input FROM quant_factor_agent_jobs WHERE id=%s',(captured[0]['id'],)).fetchone()['input'];self.assertEqual(saved['controller']['worker_epoch'],state['decision']['runner_epoch'])

 def test_actual_development_retry_requeues_original_get_and_unknown_submit_keeps_error(self):
  from contextlib import ExitStack
  from psycopg.types.json import Jsonb
  from services.quant_factor import service,store,ledger,re_client,repo
  meta={'data_release_id':'data','factor_source_hash':'source','spec_hash':'spec'}
  block={'interrupted':True,'submission_started':True,'run_id':'b'*32,'compute_backend':{'base':'http://fixture.invalid'},'expected_identity':meta}
  job=self.add('candidate',kind='development')
  with self.connection() as c:
   c.execute("UPDATE quant_research_queue_jobs SET status='completed' WHERE id=%s",(job['id'],))
   c.execute("UPDATE quant_factor_candidates SET status='development_error',archive='{}',evidence=jsonb_set(evidence,'{development}',%s::jsonb) WHERE id='candidate'",(Jsonb(block),))
  with ExitStack() as stack:
   for module in (service,store,ledger,repo):stack.enter_context(patch.object(module,'get_conn',self.connection))
   stack.enter_context(patch.object(service,'current',side_effect=lambda uid,org,cid:store.read(uid,org,cid)))
   stack.enter_context(patch.object(service,'save_run'));stack.enter_context(patch.object(service,'sign_result',return_value='fixture-signature'));stack.enter_context(patch.object(service,'_append_development_trial'));stack.enter_context(patch.object(service,'evaluate',return_value={'passed':False,'checks':[]}))
   http=stack.enter_context(patch.object(re_client,'request_json',return_value=(200,{}, {'status':'succeeded','result':{'meta':meta}})))
   result=service.retry_development(self.uid,self.org,'candidate');self.assertEqual(result['status'],'development_running')
   restored=self.queue_row(job);self.assertEqual(restored['status'],'queued');self.assertTrue(restored['payload']['query_existing_only'])
   worker=q.claim();q.run_job(worker,q._handler)
   http.assert_called_once();self.assertEqual(http.call_args.kwargs['method'],'GET');self.assertTrue(http.call_args.args[0].endswith('/'+'b'*32))
   self.assertEqual(self.queue_row(job)['status'],'completed')
   with self.connection() as c:
    self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_factor_trials').fetchone()['n'],1)
    c.execute("UPDATE quant_factor_candidates SET status='development_error',evidence=jsonb_set(evidence,'{development}',%s::jsonb) WHERE id='candidate'",(Jsonb({'interrupted':True,'submission_started':True}),))
   with self.assertRaisesRegex(WorkflowError,'不能重复提交'):service.retry_development(self.uid,self.org,'candidate')
   self.assertEqual(store.read(self.uid,self.org,'candidate')['status'],'development_error');http.assert_called_once()

 def test_explicit_lightweight_advice_is_metered_while_heavy_queue_remains_occupied(self):
  import io
  from types import SimpleNamespace
  from ai.gateway import providers
  from ai.router.specs import TaskSpec
  self.add('background');background=q.claim()
  raw={'choices':[{'message':{'content':'fixture advice'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}
  target=SimpleNamespace(model='fixture',provider='fixture',base_url='http://fixture.invalid',timeout=10)
  with patch('ai.router.get_task',return_value=TaskSpec(task_id='quant.factor.research_assistant')),patch.object(providers,'resolve_target',return_value=target),patch.object(providers,'_post',side_effect=lambda *a,**k:io.BytesIO(json.dumps(raw).encode())) as post:
   with self.assertRaisesRegex(WorkflowError,'排队执行'):b.run(self.uid,self.org,'project','blocked-implicit','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}])
   with q.lightweight_advice():out=b.run(self.uid,self.org,'project','explicit-light','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}])
  self.assertEqual(out['tokens_in'],10);post.assert_called_once();self.assertIsNone(q.claim());self.assertEqual(self.queue_row(background)['status'],'running')
  with self.connection() as c:
   call=c.execute("SELECT queue_job_id,actual_tokens FROM quant_ai_budget_calls WHERE call_key='explicit-light'").fetchone();self.assertIsNone(call['queue_job_id']);self.assertEqual(call['actual_tokens'],30)

 def test_confirmed_provider_rejection_is_not_an_unknown_running_request(self):
  from types import SimpleNamespace
  from ai.gateway import providers
  from ai.router.specs import TaskSpec
  first=self.add('first',kind='agent');other=self.add('other');job=q.claim();errors=[]
  target=SimpleNamespace(model='fixture',provider='fixture',base_url='http://fixture.invalid',timeout=10)
  def handler(j):
   try:b.run(self.uid,self.org,'project','rejected','quant.factor.research_assistant',messages=[{'role':'user','content':'fixture'}])
   except WorkflowError as exc:errors.append(exc)
  with patch('ai.router.get_task',return_value=TaskSpec(task_id='quant.factor.research_assistant')),patch.object(providers,'resolve_target',return_value=target),patch.object(providers,'_post',side_effect=providers._HttpFailure(429,'fixture quota','rejected')) as post:q.run_job(job,handler)
  self.assertEqual(len(errors),1);post.assert_called_once();self.assertEqual(self.queue_row(job)['status'],'completed');self.assertEqual(q.claim()['id'],other['id'])
  with self.connection() as c:
   row=c.execute("SELECT status,actual_tokens,response FROM quant_ai_budget_calls WHERE call_key='rejected'").fetchone();self.assertEqual(row['status'],'unresolved');self.assertIsNone(row['actual_tokens']);self.assertTrue(row['response']['provider_request_terminal'])
