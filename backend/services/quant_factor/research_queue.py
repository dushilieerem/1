"""One durable research slot per explicitly owned deployment, shared by its child tools.

No age-based lease expiry: an unconfirmed physical request retains the slot. Historic
usage gaps are accounting facts and are never interpreted as active requests.
"""
from __future__ import annotations
import contextvars,hashlib,os,socket,threading,uuid
from pathlib import Path
from services.core.db import get_conn
from .policy import WorkflowError
DEPLOYMENT_ID='quant-bff-18799-'+hashlib.sha256(str(Path(__file__).resolve().parents[3]).encode()).hexdigest()[:16]
INSTANCE=uuid.uuid4().hex
HOST=socket.gethostname()
_CURRENT=contextvars.ContextVar('quant_research_queue_job',default=None)
_LIGHT=contextvars.ContextVar('quant_research_lightweight',default=False)
_WAKE=threading.Event()

def _start_ticks(pid):
 try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except (OSError,IndexError):return None

PROCESS_START=_start_ticks(os.getpid())

def _lock(c):
 c.execute('INSERT INTO quant_research_queue_slots(deployment_id) VALUES(%s) ON CONFLICT DO NOTHING',(DEPLOYMENT_ID,))
 return c.execute('SELECT * FROM quant_research_queue_slots WHERE deployment_id=%s FOR UPDATE',(DEPLOYMENT_ID,)).fetchone()

def enabled():return os.environ.get('QUANT_RESEARCH_DURABLE_QUEUE')=='1'

def enqueue(c,kind,object_id,uid,org,*,parent=None,payload=None):
 if kind not in ('f0','iteration','agent','development','validation','novelty','sealed'):raise ValueError('unsupported research queue kind')
 if parent is None:parent=_CURRENT.get()
 inherited=None
 if parent:
  slot=_lock(c)
  inherited=c.execute('SELECT * FROM quant_research_queue_jobs WHERE id=%s AND deployment_id=%s AND user_id=%s AND org_id=%s',(parent,DEPLOYMENT_ID,uid,org)).fetchone()
  if not inherited or inherited['status']!='running' or slot['root_id']!=inherited['root_id']:raise WorkflowError('原研究执行槽已变化，未派生新的计算动作')
 identifier=str(uuid.uuid4());root=inherited['root_id'] if inherited else identifier
 c.execute("INSERT INTO quant_research_queue_jobs(id,deployment_id,kind,object_id,user_id,org_id,root_id,parent_id,payload,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'queued') ON CONFLICT(deployment_id,kind,object_id) DO NOTHING",(identifier,DEPLOYMENT_ID,kind,object_id,uid,org,root,parent,__import__('json').dumps(payload or {})))
 return dict(c.execute('SELECT * FROM quant_research_queue_jobs WHERE deployment_id=%s AND kind=%s AND object_id=%s',(DEPLOYMENT_ID,kind,object_id)).fetchone())

def by_object(c,kind,object_id):
 row=c.execute('SELECT * FROM quant_research_queue_jobs WHERE deployment_id=%s AND kind=%s AND object_id=%s',(DEPLOYMENT_ID,kind,object_id)).fetchone()
 return dict(row) if row else None

def current_id():return _CURRENT.get()

def unknown_calls(c,root_id):
 # Missing usage on a received response is not an in-flight request. Old history
 # has no queue identity and cannot monopolize this deployment's execution slot.
 return bool(c.execute("SELECT b.id FROM quant_ai_budget_calls b JOIN quant_research_queue_jobs j ON j.id=b.queue_job_id WHERE j.deployment_id=%s AND j.root_id=%s AND b.status IN ('dispatched','unresolved') AND b.response IS NULL LIMIT 1",(DEPLOYMENT_ID,root_id)).fetchone())

def claim():
 with get_conn() as c:
  slot=_lock(c);root=slot['root_id']
  if root and unknown_calls(c,root):return None
  if root:
   pending=compute_pending(c,root)
   row=c.execute("SELECT * FROM quant_research_queue_jobs WHERE deployment_id=%s AND root_id=%s AND status='queued' AND (%s=FALSE OR payload->>'query_existing_only'='true') ORDER BY (parent_id IS NOT NULL),queued_at,id LIMIT 1 FOR UPDATE",(DEPLOYMENT_ID,root,pending)).fetchone()
  else:
   row=c.execute("SELECT * FROM quant_research_queue_jobs WHERE deployment_id=%s AND parent_id IS NULL AND status='queued' ORDER BY queued_at,id LIMIT 1 FOR UPDATE",(DEPLOYMENT_ID,)).fetchone()
  if not row:return None
  epoch=str(uuid.uuid4())
  if not root:c.execute('UPDATE quant_research_queue_slots SET root_id=%s,updated_at=NOW() WHERE deployment_id=%s',(row['root_id'],DEPLOYMENT_ID))
  return dict(c.execute("UPDATE quant_research_queue_jobs SET status='running',owner_instance=%s,owner_host=%s,owner_pid=%s,owner_start=%s,owner_epoch=%s,updated_at=NOW() WHERE id=%s RETURNING *",(INSTANCE,HOST,os.getpid(),PROCESS_START,epoch,row['id'])).fetchone())

def _release_if_finished(c,root):
 active=c.execute("SELECT id FROM quant_research_queue_jobs WHERE deployment_id=%s AND root_id=%s AND status IN ('queued','running') LIMIT 1",(DEPLOYMENT_ID,root)).fetchone()
 if not active and not unknown_calls(c,root) and not compute_pending(c,root):c.execute('UPDATE quant_research_queue_slots SET root_id=NULL,updated_at=NOW() WHERE deployment_id=%s AND root_id=%s',(DEPLOYMENT_ID,root))

def finish(job,reason='',*,waiting=False):
 with get_conn() as c:
  _lock(c)
  if unknown_calls(c,job['root_id']):waiting=True;reason='模型提交结果尚未确认，保留执行槽；未重复提交'
  elif compute_pending(c,job['root_id']):waiting=True;reason='原计算结果尚未确认，保留执行槽；仅核对原任务'
  if job['kind']=='f0' and not waiting:
   state=c.execute('SELECT status,decision FROM quant_factor_f0_runs WHERE id=%s',(job['object_id'],)).fetchone()
   if state and state['status']=='queued' and (state.get('decision') or {}).get('scheduler_yield'):
    children=c.execute("SELECT id FROM quant_research_queue_jobs WHERE deployment_id=%s AND root_id=%s AND id<>%s AND status IN ('queued','running','waiting') LIMIT 1",(DEPLOYMENT_ID,job['root_id'],job['id'])).fetchone()
    if not children:
     changed=c.execute("UPDATE quant_research_queue_jobs SET status='queued',queued_at=NOW(),reason='调度检查点已保存，等待继续',updated_at=NOW() WHERE id=%s AND status='running' AND owner_epoch=%s RETURNING id",(job['id'],job['owner_epoch'])).fetchone()
     if changed:c.execute('UPDATE quant_research_queue_slots SET root_id=NULL,updated_at=NOW() WHERE deployment_id=%s AND root_id=%s',(DEPLOYMENT_ID,job['root_id']))
     return bool(changed)
  changed=c.execute("UPDATE quant_research_queue_jobs SET status=%s,reason=%s,updated_at=NOW() WHERE id=%s AND deployment_id=%s AND status='running' AND owner_epoch=%s RETURNING id",('waiting' if waiting else 'completed',str(reason)[:1000],job['id'],DEPLOYMENT_ID,job['owner_epoch'])).fetchone()
  if changed:_release_if_finished(c,job['root_id'])
 return bool(changed)

def cancel(c,kind,object_id,uid,org):
 _lock(c)
 row=c.execute("UPDATE quant_research_queue_jobs SET status='cancelled',reason='用户取消排队',updated_at=NOW() WHERE deployment_id=%s AND kind=%s AND object_id=%s AND user_id=%s AND org_id=%s AND status='queued' RETURNING root_id",(DEPLOYMENT_ID,kind,object_id,uid,org)).fetchone()
 if row:_release_if_finished(c,row['root_id'])
 return bool(row)

def recover_owned():
 """Keep queued work; do not replay an interrupted action or reset another deployment."""
 waiting=checkpoints=0;changes=[]
 with get_conn() as c:
  _lock(c)
  rows=c.execute("SELECT * FROM quant_research_queue_jobs WHERE deployment_id=%s AND status='running' FOR UPDATE",(DEPLOYMENT_ID,)).fetchall()
  for row in rows:
   if row['owner_host']!=HOST or row['owner_instance']==INSTANCE:continue
   if _start_ticks(row['owner_pid'])==row['owner_start']:continue
   uncertain=unknown_calls(c,row['root_id']) or compute_pending(c,row['root_id'])
   reason='原物理调用结果待确认；不会重新发送' if uncertain else '原执行进程已退出；动作中途检查点需确认，未自动重放'
   c.execute("UPDATE quant_research_queue_jobs SET status='waiting',reason=%s,updated_at=NOW() WHERE id=%s",(reason,row['id']))
   changes.append((dict(row),reason));waiting+=bool(uncertain);checkpoints+=not uncertain
 # Business entry points acquire actor/business rows before queue rows. Never
 # hold the queue/slot lock while updating a candidate, F0 or sealed record.
 for row,reason in changes:_mark_checkpoint(row,reason)
 return {'requeued':0,'waiting_confirmation':waiting,'waiting_checkpoint':checkpoints}

def _mark_checkpoint(row,reason):
 from . import store
 with get_conn() as c:
  c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,row['user_id']))
  if row['kind']=='f0':
   c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason=%s,decision=decision||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND decision->>'queue_deployment'=%s AND status IN ('queued','running')",(reason,store.encode({'technical_wait':{'kind':'interrupted_checkpoint','message':reason},'recovery_requires_new_run':True}),row['object_id'],row['user_id'],row['org_id'],DEPLOYMENT_ID))
  elif row['kind']=='agent':
   c.execute("UPDATE quant_factor_agent_jobs SET status='failed',events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running')",(store.encode([{'action':'technical_checkpoint_wait','message':reason}]),row['object_id'],row['user_id'],row['org_id']))
  elif row['kind'] in ('development','validation','novelty'):
   phase='validation' if row['kind']=='validation' else 'development'
   c.execute("UPDATE quant_factor_candidates SET status=%s,evidence=jsonb_set(evidence,%s::text[],COALESCE(evidence->%s,'{}'::jsonb)||%s::jsonb),updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status=%s",(phase+'_error',[phase],phase,store.encode({'interrupted':row['kind']!='novelty','message':reason}),row['object_id'],row['user_id'],row['org_id'],phase+'_running'))
  elif row['kind']=='sealed':
   c.execute("UPDATE quant_factor_sealed_validations SET status='error',result=result||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running')",(store.encode({'message':reason}),row['object_id'],row['user_id'],row['org_id']))
  elif row['kind']=='iteration':
   c.execute("UPDATE quant_factor_iterations SET status='stopped',stop_reason=%s,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running')",(reason,row['object_id'],row['user_id'],row['org_id']))


def run_job(job,handler):
 token=_CURRENT.set(job['id'])
 try:
  handler(job)
 except Exception as exc:
  if job['kind']=='f0':
   from . import store
   with get_conn() as c:c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason=%s,decision=decision||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND decision->>'queue_deployment'=%s AND status IN ('queued','running')",(str(exc)[:1000],store.encode({'technical_wait':{'kind':'scheduler_error','message':str(exc)[:1000]}}),job['object_id'],job['user_id'],job['org_id'],DEPLOYMENT_ID))
  finish(job,str(exc));raise
 else:finish(job)
 finally:_CURRENT.reset(token);_WAKE.set()

def wake():_WAKE.set()


def require_context():
 if not enabled():return
 if not _CURRENT.get():raise WorkflowError('请通过研究任务或环节委托排队执行；当前入口不会绕过研究执行队列')
 with get_conn() as c:
  owned=c.execute("SELECT j.id,j.root_id,j.user_id,j.org_id,r.kind AS root_kind,r.object_id AS root_object_id FROM quant_research_queue_jobs j JOIN quant_research_queue_jobs r ON r.id=j.root_id JOIN quant_research_queue_slots s ON s.deployment_id=j.deployment_id AND s.root_id=j.root_id WHERE j.id=%s AND j.deployment_id=%s AND j.status='running' AND j.owner_instance=%s",(current_id(),DEPLOYMENT_ID,INSTANCE)).fetchone()
 if not owned:raise WorkflowError('原研究执行槽已变化，未发新的模型或计算请求')
 if owned['root_kind']=='f0':
  with get_conn() as c:
   active=c.execute("SELECT f.id FROM quant_factor_f0_runs f JOIN quant_factor_topics t ON t.id=f.topic_id AND t.user_id=f.user_id AND t.org_id=f.org_id JOIN detect_projects p ON p.id=f.project_id AND p.user_id=f.user_id WHERE f.id=%s AND f.user_id=%s AND f.org_id=%s AND f.status='running' AND t.status='active' AND p.config->>'v5ControlEpoch'=f.decision->>'control_epoch' AND NOT EXISTS(SELECT 1 FROM quant_factor_org_controls controls WHERE controls.org_id=f.org_id AND controls.paused=TRUE)",(owned['root_object_id'],owned['user_id'],owned['org_id'])).fetchone()
  if not active:raise WorkflowError('自动研究已暂停或控制版本已变化，未发新的模型或计算请求')

def _handler(job):
 uid,org,obj=job['user_id'],job['org_id'],job['object_id']
 if job['kind']=='f0':
  from . import f0,store
  f0.run(uid,org,obj)
 elif job['kind']=='iteration':
  from . import iterations
  iterations.run(uid,org,obj)
 elif job['kind']=='agent':
  from . import agent_jobs
  agent_jobs.run(uid,org,obj)
 elif job['kind'] in ('development','validation','novelty'):
  from . import service
  args=job['payload']
  if args.get('retry_novelty'):service._retry_novelty(uid,org,obj)
  else:service.run(uid,org,obj,args.get('phase','development'),args.get('executor','human'),args.get('f0_run_id'),recovery_only=bool(args.get('query_existing_only')))
 elif job['kind']=='sealed':
  from . import sealed
  sealed.run(uid,org,obj)

_STARTED=False
_START_LOCK=threading.Lock()

def start_dispatcher():
 global _STARTED
 if not enabled():return
 with _START_LOCK:
  if _STARTED:return
  recover_owned();_STARTED=True
  from concurrent.futures import ThreadPoolExecutor
  pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='quant-owned-research')
  def loop():
   import logging
   while True:
    try:
     reconcile_waiting()
     job=claim()
     if job:pool.submit(run_job,job,_handler);continue
    except Exception:logging.getLogger(__name__).exception('Owned research dispatch failed; queue retained')
    _WAKE.wait(1);_WAKE.clear()
  threading.Thread(target=loop,name='quant-owned-research-dispatch',daemon=True).start()


def compute_pending(c,root):
 rows=c.execute("SELECT kind,object_id,external_calls FROM quant_research_queue_jobs WHERE deployment_id=%s AND root_id=%s AND kind IN ('development','validation','novelty','sealed')",(DEPLOYMENT_ID,root)).fetchall()
 for job in rows:
  physical=job.get('external_calls') or []
  if any(call.get('status') not in ('succeeded','failed','cancelled') for call in physical):return True
  if physical:continue
  if job['kind']=='novelty':continue # New novelty submissions must persist external_calls before POST.
  if job['kind']=='sealed':
   row=c.execute('SELECT result FROM quant_factor_sealed_validations WHERE id=%s',(job['object_id'],)).fetchone();block=(row or {}).get('result') or {}
   if block.get('confirmation') in ('failed','cancelled','confirmed'):continue
  else:
   row=c.execute('SELECT evidence FROM quant_factor_candidates WHERE id=%s',(job['object_id'],)).fetchone()
   block=((row or {}).get('evidence') or {}).get('validation' if job['kind']=='validation' else 'development') or {}
  if block.get('external_status') in ('succeeded','failed','cancelled') or block.get('result'):continue
  if block.get('submission_started') or block.get('run_id'):return True
 return False

def reconcile_waiting():
 # The only remote operation here is GET of an already persisted run at its
 # original backend. No submit, fallback backend or fabricated result.
 with get_conn() as c:
  rows=[dict(r) for r in c.execute("SELECT * FROM quant_research_queue_jobs WHERE deployment_id=%s AND status='waiting' ORDER BY updated_at,id LIMIT 20",(DEPLOYMENT_ID,)).fetchall()]
 for job in rows:
  for call in job.get('external_calls') or []:
   if call.get('run_id') and call.get('status') not in ('succeeded','failed','cancelled'):
    from .re_client import request_json,headers
    endpoint=call['target']['base']+('/api/factor/novelty/' if call['kind']=='novelty' else '/api/backtest/factor/')+call['run_id']
    code,_,receipt=request_json(endpoint,method='GET',timeout=30,headers=headers())
    if code==200 and isinstance(receipt,dict):external_update(call['id'],run_id=call['run_id'],status=receipt.get('status'),job_id=job['id'])
  if not job.get('external_calls') and job['kind'] in ('development','validation','sealed'):
   phase='validation' if job['kind']=='validation' else 'development'
   with get_conn() as c:
    if job['kind']=='sealed':row=c.execute('SELECT result FROM quant_factor_sealed_validations WHERE id=%s AND user_id=%s AND org_id=%s',(job['object_id'],job['user_id'],job['org_id'])).fetchone();block=(row or {}).get('result') or {};target=(block.get('intent') or {}).get('compute_backend')
    else:row=c.execute('SELECT evidence FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s',(job['object_id'],job['user_id'],job['org_id'])).fetchone();block=((row or {}).get('evidence') or {}).get(phase) or {};target=block.get('compute_backend')
   if block.get('run_id') and target and block.get('external_status') not in ('succeeded','failed','cancelled') and not block.get('result'):
    from .re_client import proxy_get_factor_run
    code,_,receipt=proxy_get_factor_run(block['run_id'],target=target)
    if code==200 and isinstance(receipt,dict) and receipt.get('status') in ('succeeded','failed','cancelled'):
     from . import store
     terminal=receipt['status']
     with get_conn() as c:
      if job['kind']=='sealed':c.execute("UPDATE quant_factor_sealed_validations SET result=jsonb_set(result,'{external_status}',to_jsonb(%s::text)),updated_at=NOW() WHERE id=%s AND result->>'run_id'=%s",(terminal,job['object_id'],block['run_id']))
      else:c.execute("UPDATE quant_factor_candidates SET evidence=jsonb_set(evidence,%s::text[],to_jsonb(%s::text)),updated_at=NOW() WHERE id=%s AND evidence->%s->>'run_id'=%s",([phase,'external_status'],terminal,job['object_id'],phase,block['run_id']))
  with get_conn() as c:
   _lock(c)
   if not unknown_calls(c,job['root_id']) and not compute_pending(c,job['root_id']):
    c.execute("UPDATE quant_research_queue_jobs SET status='completed',reason='原调用已确认结束；保留检查点，可明确继续',updated_at=NOW() WHERE id=%s AND status='waiting'",(job['id'],))
    _release_if_finished(c,job['root_id'])


class SubmissionNotDispatched(WorkflowError):pass

def external_begin(kind,target,request_hash):
 if not enabled():return None
 try:require_context()
 except WorkflowError as exc:raise SubmissionNotDispatched(str(exc)) from exc
 from . import store
 with get_conn() as c:
  job=c.execute('SELECT * FROM quant_research_queue_jobs WHERE id=%s AND deployment_id=%s FOR UPDATE',(current_id(),DEPLOYMENT_ID)).fetchone()
  calls=list(job.get('external_calls') or [])
  if any(call.get('status') not in ('succeeded','failed','cancelled') for call in calls):raise WorkflowError('原计算提交尚未确认，未再次提交')
  identifier=str(uuid.uuid4());calls.append({'id':identifier,'kind':kind,'target':target,'request_hash':request_hash,'status':'submitting'})
  c.execute('UPDATE quant_research_queue_jobs SET external_calls=%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(calls),job['id']))
 return identifier

def external_update(identifier=None,*,run_id=None,status=None,job_id=None,kind=None):
 if not enabled() or not (job_id or current_id()):return
 from . import store
 with get_conn() as c:
  job=c.execute('SELECT * FROM quant_research_queue_jobs WHERE id=%s AND deployment_id=%s FOR UPDATE',(job_id or current_id(),DEPLOYMENT_ID)).fetchone()
  if not job:return
  calls=list(job.get('external_calls') or [])
  for call in calls:
   if identifier and call['id']!=identifier:continue
   if not identifier and (call.get('run_id')!=run_id or (kind and call['kind']!=kind)):continue
   if call.get('status') in ('succeeded','failed','cancelled'):continue
   if run_id:
    if call.get('run_id') and call['run_id']!=run_id:raise WorkflowError('原计算任务身份不可替换')
    call['run_id']=run_id
   if status in ('queued','running','succeeded','failed','cancelled'):call['status']=status
  c.execute('UPDATE quant_research_queue_jobs SET external_calls=%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(calls),job['id']))


from contextlib import contextmanager
@contextmanager
def lightweight_advice():
 token=_LIGHT.set(True)
 try:yield
 finally:_LIGHT.reset(token)

def permits_lightweight(task_id):
 return _LIGHT.get() and task_id in ('quant.factor.research_assistant','quant.factor.independent_reviewer')


def requeue_existing(c,kind,object_id,uid,org,*,run_id=None,target=None,never_submitted=False,payload=None):
 """Explicit recovery, separate from idempotent create. Never infer new submission."""
 from . import store
 _lock(c)
 job=by_object(c,kind,object_id)
 if job and job['status']=='running':raise WorkflowError('原执行动作仍在处理，请等待当前确认结束，未创建另一执行')
 if job and unknown_calls(c,job['root_id']):raise WorkflowError('原模型提交尚未确认，未重排执行')
 calls=list((job or {}).get('external_calls') or [])
 if any(call.get('status') not in ('succeeded','failed','cancelled') and not call.get('run_id') for call in calls):raise WorkflowError('原计算提交尚未确认，缺少原任务编号；不会重新提交')
 if not run_id and (not never_submitted or calls):raise WorkflowError('没有可确认的原任务，未重复提交计算')
 if run_id and not target:raise WorkflowError('原计算服务身份缺失，未改用其他服务')
 body={**(payload or {}),'query_existing_only':bool(run_id)}
 if not job:
  job=enqueue(c,kind,object_id,uid,org,parent=None,payload=body)
 if job['user_id']!=uid or job['org_id']!=org:raise WorkflowError('原排队任务归属不一致')
 old_root=job['root_id']
 if job['parent_id']:
  root=c.execute('SELECT status FROM quant_research_queue_jobs WHERE id=%s',(old_root,)).fetchone()
  if root and root['status']=='running':raise WorkflowError('原自动研究仍在处理，请先暂停并确认原动作结束')
  body['recovery_from']={'root_id':old_root,'parent_id':job['parent_id']}
 if run_id and not any(call.get('run_id')==run_id for call in calls):calls.append({'id':str(uuid.uuid4()),'kind':'novelty' if kind=='novelty' else 'factor','target':target,'run_id':run_id,'status':'queued','origin':'explicit_original_run_query'})
 c.execute("UPDATE quant_research_queue_jobs SET status='queued',queued_at=NOW(),reason='明确恢复原任务',payload=%s::jsonb,external_calls=%s::jsonb,parent_id=NULL,root_id=id,updated_at=NOW() WHERE id=%s",(store.encode(body),store.encode(calls),job['id']))
 if old_root!=job['id']:_release_if_finished(c,old_root)
 return by_object(c,kind,object_id)


def retry_confirmed_novelty(c,object_id,uid,org,known_run_id=None):
 """Explicit new comparison attempt only after a confirmed failed/cancelled attempt.

A succeeded but unavailable report requires retrieval, never automatic recompute.
"""
 from . import store
 _lock(c)
 job=by_object(c,'novelty',object_id)
 initial=job or by_object(c,'development',object_id)
 if initial and (initial['user_id']!=uid or initial['org_id']!=org):raise WorkflowError('原对照任务归属不一致')
 calls=[call for call in ((initial or {}).get('external_calls') or []) if call['kind']=='novelty']
 if known_run_id and not any(call.get('run_id')==known_run_id for call in calls):raise WorkflowError('原对照任务尚未核对，未重新计算')
 if initial and unknown_calls(c,initial['root_id']):raise WorkflowError('原模型请求仍待确认，未重新提交对照')
 if any(call.get('status') not in ('failed','cancelled') for call in calls):raise WorkflowError('请先核对原对照任务及报告；不会重复提交尚未确认或已完成的计算')
 if job and job['status'] in ('running','queued'):return job
 if not job:return enqueue(c,'novelty',object_id,uid,org,payload={'retry_novelty':True})
 old_root=job['root_id']
 c.execute("UPDATE quant_research_queue_jobs SET status='queued',queued_at=NOW(),parent_id=NULL,root_id=id,payload=%s::jsonb,reason='明确重试已结束的对照',updated_at=NOW() WHERE id=%s",(store.encode({'retry_novelty':True,'recovery_from':{'root_id':old_root,'parent_id':job['parent_id']}}),job['id']))
 if old_root!=job['id']:_release_if_finished(c,old_root)
 return by_object(c,'novelty',object_id)
