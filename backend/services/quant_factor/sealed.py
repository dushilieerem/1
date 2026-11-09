"""One durable, idempotent heldout intent per frozen V5 candidate.

A lost submission acknowledgement is never permission to expose the holdout again.
Only a known external run may be queried after interruption; researchers see status.
"""
from __future__ import annotations
import copy
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from services.core.db import get_conn
from .re_client import proxy_get_factor_run, proxy_submit_factor_backtest
from . import re_client
from services.factor.detect_store import _row_project
from . import ledger, service, store
from .policy import WorkflowError, evaluate, digest, snapshot
from .metrics import default_lags
from .sealed_identity import expected_identity

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix="quant-factor-sealed")
ACTIVE=("queued","running")
INTENT_SCHEMA='quant.sealed-intent.v1'


def _public(row,full):
    out={k:v for k,v in row.items() if k not in ('user_id','org_id')}
    block=row.get('result') or {}
    out['confirmation']=block.get('confirmation')
    out['message']=block.get('message') or ''
    if not full:out.pop('result',None)
    return out


def _candidate(uid,org,cid):return store.read(uid,org,cid)


@contextmanager
def _locked(uid,org,cid):
    # Same global order as starts, trial append and admission: actor -> topic ->
    # project -> candidate -> sealed. A worker-only execution lease is never awaited.
    with get_conn() as c:
        identity=c.execute('SELECT project_id FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s',(cid,uid,org)).fetchone()
        if not identity:raise KeyError(cid)
        c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
        topic=c.execute('SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,identity['project_id'])).fetchone()
        if not topic:raise WorkflowError('候选没有对应的 V5 课题台账，不能封存')
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f"quant-factor-start:{uid}:{org}:{topic['id']}",))
        project=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,identity['project_id'])).fetchone()
        cand=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        seal=c.execute('SELECT * FROM quant_factor_sealed_validations WHERE candidate_id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        yield c,dict(cand),dict(topic),dict(project) if project else None,dict(seal) if seal else None


def _assert_unexposed(c,uid,org,topic):
    exposed=c.execute("""SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s
        AND (status LIKE 'validation_%%' OR
             (evidence->'validation' IS NOT NULL AND evidence->'validation' NOT IN ('{}'::jsonb,'null'::jsonb))) LIMIT 1""",(uid,org,topic['project_id'])).fetchone()
    if exposed:raise WorkflowError('此任务已有研究侧样本外检验记录，不能再视为未曝光的独立验证；请建立新的验证计划，原记录保留')


def _require_controller(c,uid,org,topic,controller):
    if topic.get('status')!='active':raise WorkflowError('任务已暂停或归档，旧自动动作未继续')
    c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-factor-org-control:{org}',))
    control=c.execute('SELECT paused FROM quant_factor_org_controls WHERE org_id=%s',(org,)).fetchone()
    if control and control['paused']:raise WorkflowError('自动研究已全局暂停，旧动作未继续')
    owner=c.execute("SELECT id FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s AND project_id=%s AND status='running' AND decision->>'runner_epoch'=%s",(controller['run_id'],uid,org,topic['project_id'],controller['worker_epoch'])).fetchone()
    if not owner:raise WorkflowError('当前研究控制版本已变化，旧自动动作未继续')


def _check_new(c,uid,org,cand,topic,project):
    if cand['status']!='development_passed':raise WorkflowError('只有研发检验通过的候选可以申请封存验证')
    if (cand.get('archive') or {}).get('research_asset'):raise WorkflowError('已登记版本不能重新验证')
    if not project or digest(snapshot(_row_project(project)))!=cand['snapshot_hash'] or digest(cand['snapshot'])!=cand['snapshot_hash']:
        raise WorkflowError('研究输入已变化，不能验证旧版本')
    _assert_unexposed(c,uid,org,topic)
    from .assets import context
    facts=context(c,cand)
    if facts.get('unrecorded_metrics') or facts['inflight']-facts.get('dispatch_inflight',0):raise WorkflowError('任务仍有未完成检验或未完整落账的结果，请先确认')
    trials=facts['trials'];k=ledger.current_k(trials,topic['primary_holding_period'])
    if not 1<=k<=topic['max_trials']:raise WorkflowError('研发试验记录缺失或已超授权，不能封存')
    dev=(cand.get('evidence') or {}).get('development') or {}
    if not evaluate(dev.get('result') or {},cand['snapshot']['rules'],k)['passed']:raise WorkflowError('按当前试验次数核验，研发数值门槛未达标')
    ng=(dev.get('novelty') or {}).get('gate') or {};kind=cand['snapshot']['plan'].get('researchPurpose')
    if ng.get('complete') is not True or (kind=='discovery' and ng.get('passed') is not True):raise WorkflowError('正式查重尚未完整通过，不能打开独立验证；可以先提交研究复盘')
    req=copy.deepcopy(cand['snapshot']['request']);plan=cand['snapshot']['plan']
    req.update(start=plan['validationStart'],end=plan['validationEnd'])
    if str(req['start'])!=str(topic['validation_start']) or str(req['end'])!=str(topic['validation_end']):raise WorkflowError('验证区间与固定计划不一致')
    receipt=expected_identity(req,dev.get('result') or {})
    from .resources import require
    resource_receipt=require('factor',req)
    return {'schema':INTENT_SCHEMA,'request':req,'request_hash':receipt['request_hash'],'expected_identity':receipt['expected_identity'],
            'snapshot_hash':cand['snapshot_hash'],'topic_id':topic['id'],'identity_method':receipt['identity_method'],'compute_backend':re_client.target(resource_receipt)},trials


def request(uid,org,cid,f0_run_id=None,worker_epoch=None):
    schedule=False
    with _locked(uid,org,cid) as (c,cand,topic,project,existing):
        if existing:
            # Replay precedes budget/status checks. Unknown acknowledgement is not retried.
            block=existing.get('result') or {}
            schedule=existing['status'] in ACTIVE or (existing['status']=='error' and bool(block.get('run_id')) and block.get('confirmation')=='pending')
            row=existing
        else:
            if f0_run_id:_require_controller(c,uid,org,topic,{'run_id':f0_run_id,'worker_epoch':worker_epoch})
            intent,trials=_check_new(c,uid,org,cand,topic,project)
            if f0_run_id:intent['controller']={'run_id':f0_run_id,'worker_epoch':worker_epoch}

            n=c.execute('SELECT COUNT(*) AS n FROM quant_factor_sealed_validations WHERE user_id=%s AND org_id=%s AND topic_id=%s',(uid,org,topic['id'])).fetchone()['n']
            if n>=int(topic['max_sealed']):raise WorkflowError(f"课题封存验证已达上限 {topic['max_sealed']} 次")
            sid=str(uuid.uuid4());block={'intent':intent,'confirmation':'not_submitted'}
            c.execute("""INSERT INTO quant_factor_sealed_validations
                (id,candidate_id,user_id,org_id,project_id,topic_id,snapshot_hash,status,executor,
                 view_id,release_ids,view_manifest_sha256,contract_revision,as_of,trial_ids,result)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'queued','F5',%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb)""",
                (sid,cid,uid,org,cand['project_id'],topic['id'],cand['snapshot_hash'],topic['view_id'],store.encode(topic.get('release_ids') or {}),topic.get('view_manifest_sha256') or '',topic.get('contract_revision') or '',topic.get('as_of'),store.encode([t['id'] for t in trials]),store.encode(block)))
            row=dict(c.execute('SELECT * FROM quant_factor_sealed_validations WHERE id=%s',(sid,)).fetchone());schedule=True
    if schedule:POOL.submit(run,uid,org,row['id'])
    return _public(row,False)


def _persist(uid,org,cid,sid,status,block,report_id=None):
    with _locked(uid,org,cid) as (c,cand,topic,project,seal):
        if not seal or seal['id']!=sid or seal['status'] in ('passed','failed','cancelled'):return False
        c.execute("""UPDATE quant_factor_sealed_validations SET status=%s,result=%s::jsonb,
           report_id=COALESCE(%s,report_id),evaluated_at=CASE WHEN %s IN ('passed','failed') THEN NOW() ELSE evaluated_at END,
           updated_at=NOW() WHERE id=%s""",(status,store.encode(block),report_id,status,sid))
    return True


def _read(uid,org,sid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_sealed_validations WHERE id=%s AND user_id=%s AND org_id=%s',(sid,uid,org)).fetchone()
    return dict(row) if row else None


def _confirm_result(result,intent):
    if not isinstance(intent,dict) or intent.get('schema')!=INTENT_SCHEMA:raise WorkflowError('旧封存记录缺少提交前固定身份，结果待核对，不会重复提交')
    if digest(intent['request'])!=intent['request_hash']:raise WorkflowError('封存请求指纹不一致')
    meta=result.get('meta') or {};expected=intent.get('expected_identity') or {}
    if any(not expected.get(k) or meta.get(k)!=expected[k] for k in ('data_release_id','factor_source_hash','spec_hash')):
        raise WorkflowError('封存结果的数据、源码或规格身份与提交前记录不一致，不能认定通过')


def run(uid,org,sid):
    with get_conn() as lease:
        acquired=lease.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS acquired',(f'quant-factor-sealed-worker:{uid}:{org}:{sid}',)).fetchone()
        if not acquired or acquired['acquired'] is not True:return
        _run_once(uid,org,sid)


def _run_once(uid,org,sid):
    row=_read(uid,org,sid)
    if not row or row['status'] not in (*ACTIVE,'error'):return
    cid=row['candidate_id'];block=copy.deepcopy(row.get('result') or {});intent=block.get('intent') or {};rid=block.get('run_id')
    if block.get('confirmation') in ('failed','cancelled','confirmed'):return
    try:
        if intent.get('schema')!=INTENT_SCHEMA:raise WorkflowError('旧封存记录缺少提交前固定身份，需核对原计算记录，不会自动重发')
        cand=_candidate(uid,org,cid)
        if cand['snapshot_hash']!=row['snapshot_hash'] or digest(cand['snapshot'])!=intent['snapshot_hash']:raise WorkflowError('封存候选已改变，原记录保留，请先核对')
        if not rid:
            if block.get('submission_started'):raise WorkflowError('这次独立验证的提交结果尚未确认；不会重复计算，请联系研究负责人核对原任务')
            with _locked(uid,org,cid) as (c,locked,topic,project,current):
                _assert_unexposed(c,uid,org,topic)
                if not project or digest(snapshot(_row_project(project)))!=intent['snapshot_hash']:raise WorkflowError('研究输入已改变，尚未提交独立验证')
            req=intent['request']
            if digest(req)!=intent['request_hash']:raise WorkflowError('封存请求指纹不一致')
            if req.get('factor_code'):
                from .causality import diagnose_source
                diagnose_source(req['factor_code'],req['factor_name'])
            from .resources import require
            block['resource_preflight']=require('factor',req)
            current_target=re_client.target(block['resource_preflight'])
            if intent.get('compute_backend')!=current_target:raise WorkflowError('计算服务或受控方法版本已改变，原封存计划保留，请先核对')
            block['compute_backend']=current_target
            block.update(submission_started=True,confirmation='pending',message='正在确认独立验证结果')
            if not _persist(uid,org,cid,sid,'running',block):return
            # The durable unknown-submit marker is committed before any external
            # request. Hold the existing actor/topic lock across this short submit
            # so a completed pause/takeover cannot be followed by a new exposure.
            with _locked(uid,org,cid) as (c,locked,topic,project,current):
                if intent.get('controller') and topic.get('status')!='active':
                    block.update(confirmation='cancelled',message='任务已暂停，独立验证尚未提交；原申请保留。')
                    c.execute("UPDATE quant_factor_sealed_validations SET status='cancelled',result=%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode(block),sid));return
                controller=intent.get('controller')
                stale_controller=False
                if controller:
                    try:_require_controller(c,uid,org,topic,controller)
                    except WorkflowError:stale_controller=True
                if stale_controller or not project or digest(snapshot(_row_project(project)))!=intent['snapshot_hash']:
                    block.update(confirmation='cancelled',message='研究控制版本或工程已变化，独立验证尚未提交；原申请保留。')
                    c.execute("UPDATE quant_factor_sealed_validations SET status='cancelled',result=%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode(block),sid));return
                code,_,task=proxy_submit_factor_backtest(req,target=intent['compute_backend'])

            if code not in (200,202) or not isinstance(task,dict) or not task.get('run_id'):raise WorkflowError('提交结果尚未确认，原验证额度保留；请核对原任务，不会重复提交')
            rid=task['run_id'];block['run_id']=rid
            if not _persist(uid,org,cid,sid,'running',block):return
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            code,_,task=proxy_get_factor_run(rid,target=intent.get('compute_backend'))
            if code!=200 or not isinstance(task,dict):raise WorkflowError('原验证任务目前无法查询，运行身份保留；不会重新提交')
            terminal=task.get('status')
            if terminal in ('failed','cancelled'):
                block.update(confirmation=terminal,external_status=terminal,message='独立验证'+('已停止' if terminal=='cancelled' else '执行失败')+'：'+str(task.get('error') or terminal)[:500])
                _persist(uid,org,cid,sid,'cancelled' if terminal=='cancelled' else 'error',block);return
            if terminal=='succeeded':
                result=task.get('result') or {};_confirm_result(result,intent)
                with _locked(uid,org,cid) as (c,cand,topic,project,current):
                    if cand['snapshot_hash']!=intent['snapshot_hash']:raise WorkflowError('候选版本已改变，原结果待核对')
                    trials=[dict(t) for t in c.execute('SELECT * FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no',(uid,org,topic['id'])).fetchall()]
                    k=ledger.current_k(trials,topic['primary_holding_period'])
                    checks=(cand.get('evidence',{}).get('development') or {}).get('gate',{}).get('checks') or []
                    obs=next((x.get('actual') for x in checks if x.get('name')=='有效IC观测数'),None)
                    lags=default_lags(int(obs)) if isinstance(obs,(int,float)) and obs>=2 else None
                    gate=evaluate(result,cand['snapshot']['rules'],k,lags=lags)
                    block.update(result=result,gate=gate,confirmation='confirmed',message='独立验证已完成')
                    c.execute("UPDATE quant_factor_sealed_validations SET status=%s,result=%s::jsonb,report_id=%s,evaluated_at=NOW(),updated_at=NOW() WHERE id=%s AND status NOT IN ('passed','failed','cancelled')",('passed' if gate['passed'] else 'failed',store.encode(block),'sealed_'+sid,sid))
                return
            time.sleep(2)
        raise WorkflowError('原验证仍未确认完成，运行身份保留；可继续查询，不会重新计算')
    except Exception as exc:
        block.update(confirmation='pending',message=str(exc)[:1200])
        _persist(uid,org,cid,sid,'error',block)


def detail(uid,org,cid,full):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_sealed_validations WHERE candidate_id=%s AND org_id=%s',(cid,org)).fetchone()
    if not row or (not full and int(row['user_id'])!=uid):raise KeyError(cid)
    return _public(dict(row),full)


def status(uid,org,cid,full):return detail(uid,org,cid,full)

__all__=['detail','request','run','status']
