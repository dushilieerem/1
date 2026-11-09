from __future__ import annotations
import copy
import hashlib
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from services.core.db import get_conn
from services.core.env_config import env
from services.factor.detect_store import get_project, _row_project, save_run
from services.factor.re_factor_async_proxy import proxy_submit_factor_backtest,proxy_get_factor_run,proxy_cancel_factor_run
from services.strategy.result_signature import sign_result
from .policy import WorkflowError,snapshot,digest,evaluate,compare_identity
from . import store

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='quant-factor-verify')
_BACKFILL_LOCK=threading.Lock()

def event(action,**details): return {'at':datetime.now(timezone.utc).isoformat(),'action':action,**details}
def _dispatch(uid,org,cid,phase=None,executor="human",f0_run_id=None):
    """inline：进程内线程池；queue：写 background_jobs，由 worker.py 消费。"""
    mode=(env('QUANT_FACTOR_JOB_MODE','inline') or 'inline').strip().lower()
    if mode=='queue':
        from . import jobs
        try:
            if phase:
                if executor == "human" and f0_run_id is None:
                    jobs.enqueue_run(uid,org,cid,phase)
                else:
                    jobs.enqueue_run(uid,org,cid,phase,executor,f0_run_id)
            else:
                jobs.enqueue_retry(uid,org,cid)
        except Exception as exc:
            status=(phase+'_error') if phase else 'development_error'
            store.update(uid,org,cid,status,event('queue_error',message='长任务入队失败，未自动重试'))
            raise WorkflowError('长任务入队失败：'+str(exc)[:300]) from exc
        return
    if phase:
        if executor == "human" and f0_run_id is None:
            POOL.submit(run,uid,org,cid,phase)
        else:
            POOL.submit(run,uid,org,cid,phase,executor,f0_run_id)
    else:
        POOL.submit(_retry_novelty,uid,org,cid)


def public(row):
    return {k:v for k,v in row.items() if k not in ('user_id','org_id')}

def current(uid,org,cid):
    row=store.read(uid,org,cid)
    if row['status'].endswith('_running') and (datetime.now(timezone.utc)-row['updated_at']).total_seconds()>2400:
        store.update(uid,org,cid,row['status'].replace('_running','_error'),event('execution_interrupted',message='计算超过恢复窗口，可能服务中断；已保留证据，未自动重试'))
        row=store.read(uid,org,cid)
    try: row['stale']=digest(snapshot(get_project(uid,row['project_id'])['project']))!=row['snapshot_hash']
    except (KeyError,WorkflowError): row['stale']=True
    return public(row)

def _locked_view_error(uid,org,project_id):
    """A topic locks its view; never silently compute a locked topic on a newer view."""
    with get_conn() as c:
        topic=c.execute("SELECT view_id FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",(uid,org,project_id)).fetchone()
    if not topic:return None
    from services.workflow_workspace.platform_data import published_view
    current=published_view()['view_id']
    if topic['view_id']!=current:
        return f"课题锁定数据视图 {topic['view_id']}，当前发布视图为 {current}；请新建计划版本/课题，不能把旧台账接到新视图"
    return None


def create(uid,org,project_id,expected_snapshot_hash=None,reference=None,executor='human',f0_run_id=None):
    locked=_locked_view_error(uid,org,project_id)
    if locked:raise WorkflowError(locked)
    with get_conn() as c:
        # Serialize creation per actor: budget and duplicate checks must be atomic.
        c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
        p=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,project_id)).fetchone()
        if not p: raise KeyError(project_id)
        snap=snapshot(_row_project(dict(p))); sha=digest(snap)
        if expected_snapshot_hash and sha!=expected_snapshot_hash:raise WorkflowError('研究输入已变更，停止自动提交，未覆盖人工修改。')
        existing=c.execute('SELECT id,status,evidence FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND snapshot_hash=%s',(uid,org,project_id,sha)).fetchone()
        if existing:
            if reference and existing['evidence'].get('library_reference',{}).get('hash')!=reference['hash']:
                raise WorkflowError('已有候选的对照库版本不同，请复盘后开启新的研究任务。')
            cid=existing['id']
        else:
            from . import ledger
            topic=c.execute("SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",(uid,org,project_id)).fetchone()
            if topic:
                used=ledger.current_k(ledger._trials(uid,org,topic['id']),topic['primary_holding_period'])
                reserved=c.execute("SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('development_running','development_queued')",(uid,org,project_id)).fetchone()['n']
                if used+int(reserved)>=int(topic['max_trials']):
                    raise WorkflowError('课题 K 已达到试验预算（已计入在途检验）；请先复盘并明确修订计划')
            else:
                count=c.execute('SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,project_id)).fetchone()['n']
                if count>=snap['plan']['maxTrials']: raise WorkflowError('本研究已达到登记的候选尝试预算；请先复盘并明确修订计划')
            pending=c.execute("SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND status LIKE '%%_running'",(uid,org)).fetchone()['n']
            if pending>=4: raise WorkflowError('验证计算队列繁忙，请稍后提交')
            cid=str(uuid.uuid4())
            evidence={}
            active_branch=((p.get('config') or {}).get('v5ActiveBranch') if hasattr(p,'get') else None)
            if active_branch:
                evidence['branch_id']=str(active_branch)
            if snap['plan'].get('researchPurpose')=='discovery':
                from .asset_context import catalogue
                evidence['library_reference']=reference or catalogue(uid, org)
            c.execute('INSERT INTO quant_factor_candidates(id,user_id,org_id,project_id,snapshot,snapshot_hash,status,events,evidence) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb)',(cid,uid,org,project_id,store.encode(snap),sha,'development_running',store.encode([event('candidate_frozen',snapshot_hash=sha,reference_hash=evidence.get('library_reference',{}).get('hash')),event('development_queued')]),store.encode(evidence)))
    if existing and existing['status'] in ('development_passed','development_failed','development_error'):
        try:_ensure_development_trial(uid,org,cid,executor,f0_run_id)
        except Exception:pass
    if not existing:_dispatch(uid,org,cid,'development',executor,f0_run_id)
    return current(uid,org,cid)


def backfill_terminal_trials(uid,org,project_id,executor='agent',f0_run_id=None):
    """Record completed tests for terminal candidates whose ledger write previously failed."""
    with get_conn() as c:
        rows=c.execute("SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('development_passed','development_failed','development_error') ORDER BY created_at",(uid,org,project_id)).fetchall()
    added=[]
    for r in rows:
        item=_ensure_development_trial(uid,org,r['id'],executor,f0_run_id)
        if item:added.append(item)
    return added


def _ensure_development_trial(uid,org,cid,executor='human',f0_run_id=None):
    """Append the trial for a terminal candidate that was computed before its ledger write succeeded.

    Reusing a frozen candidate must never hide a completed test from K. Dedupe by report_id;
    only fills the gap, never rewrites an existing row.
    """
    row=store.read(uid,org,cid)
    if row['status'] not in ('development_passed','development_failed','development_error'):return None
    data=(row.get('evidence') or {}).get('development') or {}
    result=data.get('result') or {};gate=data.get('gate') or {}
    if not result or not gate:return None
    report_id=data.get('report_id') or 'qf_'+cid+'_development'
    with _BACKFILL_LOCK:
        with get_conn() as c:
            exists=c.execute("SELECT id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND project_id=%s AND report_id=%s",(uid,org,row['project_id'],report_id)).fetchone()
        if exists:return None
        outcome='error' if row['status']=='development_error' else 'passed' if row['status']=='development_passed' else 'failed'
        req=data.get('request') or row['snapshot']['request']
        return _append_development_trial(uid,org,row,req,result,gate,outcome,report_id,executor,f0_run_id)

def validate(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row: raise KeyError(cid)
        if row['status']!='development_passed': raise WorkflowError('只有研发检验通过的冻结候选可以提交一次样本外复验')
        p=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,row['project_id'])).fetchone()
        if not p or digest(snapshot(_row_project(dict(p))))!=row['snapshot_hash']: raise WorkflowError('研究输入已变化，请重新冻结并检验当前版本')
        c.execute("UPDATE quant_factor_candidates SET status='validation_running',events=events||%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode([event('validation_queued',sealed=False)]),cid))
    _dispatch(uid,org,cid,'validation','human',None)
    return current(uid,org,cid)

def _gate_k(uid,org,project_id,phase):
    """K used for the threshold: this test counts on development, not on sealed validation."""
    from . import ledger
    with get_conn() as c:
        topic=c.execute("SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",(uid,org,project_id)).fetchone()
    if not topic:return 1
    current=ledger.current_k(ledger._trials(uid,org,topic['id']),topic['primary_holding_period'])
    return current+1 if phase=='development' else current


def run(uid,org,cid,phase,executor='human',f0_run_id=None):
    running=phase+'_running'
    try:
        row=store.read(uid,org,cid);snap=row['snapshot']; req=copy.deepcopy(snap['request']);plan=snap['plan']
        req.update(start=plan[phase+'Start'],end=plan[phase+'End'])
        status,_,task=proxy_submit_factor_backtest(req)
        if status not in (200,202) or not isinstance(task,dict) or not task.get('run_id'):
            raise WorkflowError('计算提交失败：'+str(task)[:500])
        rid=task['run_id'];store.update(uid,org,cid,running,event(phase+'_submitted',tool='ResearchEngine.factor',run_id=rid),{phase:{'run_id':rid,'request':req}})
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            state=store.read(uid,org,cid)
            if state['status']=='cancelled':
                proxy_cancel_factor_run(rid);return
            status,_,task=proxy_get_factor_run(rid)
            if status!=200: raise WorkflowError('计算状态读取失败，HTTP '+str(status))
            if task.get('status')=='succeeded': break
            if task.get('status') in ('failed','cancelled'): raise WorkflowError('计算'+task['status']+': '+str(task.get('error',''))[:500])
            time.sleep(2)
        else:
            proxy_cancel_factor_run(rid)
            raise WorkflowError('计算超过15分钟，已请求取消')
        result=task.get('result') or {}; gate=evaluate(result,snap['rules'],_gate_k(uid,org,row['project_id'],phase))
        if phase=='validation': compare_identity(row['evidence']['development']['result'],result)
        # Trusted server-to-server result, signed through the existing report persistence contract.
        signed={**result,'_svquant_verified_token':sign_result(uid,result)}
        report_id='qf_'+cid+'_'+phase
        save_run(uid,{'id':report_id,'projectId':row['project_id'],'factorName':req['factor_name'],
                     'description':snap['name']+' / '+phase,'request':{**req,'_re_run_id':rid},'result':signed})
        data={'run_id':rid,'report_id':report_id,'request':req,'result':result,'gate':gate}
        novelty_status=None
        if phase=='development' and snap['plan'].get('researchPurpose')=='discovery':
            store.update(uid,org,cid,running,event('novelty_started',message='比对当前可访问因子库，代码不同不等于新因子。'))
            # Persist numerical evidence before a dependent service is called.
            store.update(uid,org,cid,running,event('numerical_checks_completed',passed=gate['passed']),{phase:data})
            novelty=_compare_library(uid,org,cid,row,data)
            data['novelty']=novelty;novelty_status=novelty['status']
            gate={**gate,'numerical_passed':gate['passed'],'passed':gate['passed'] and novelty.get('gate',{}).get('passed') is True}
            data['gate']=gate
            store.update(uid,org,cid,running,event('novelty_completed',status=novelty_status,message=novelty['message']))
        final_status=phase+('_error' if novelty_status in ('unavailable','incomplete') else '_passed' if gate['passed'] else '_failed')
        with get_conn() as c:
            locked=c.execute('SELECT status FROM quant_factor_candidates WHERE id=%s FOR UPDATE',(cid,)).fetchone()
            if locked['status']=='cancelled': return
            c.execute('UPDATE quant_factor_candidates SET status=%s,evidence=evidence||%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',
                      (final_status,store.encode({phase:data}),store.encode([event(phase+'_completed',passed=gate['passed'],checks=gate['checks'],report_id=report_id)]),cid))
        if phase=='development':
            outcome='error' if final_status=='development_error' else 'passed' if final_status=='development_passed' else 'failed'
            try:_append_development_trial(uid,org,row,req,result,gate,outcome,report_id,executor,f0_run_id)
            except Exception as exc:store.update(uid,org,cid,final_status,event('ledger_append_failed',message=str(exc)[:300]))
    except Exception as exc:
        with get_conn() as c:
            c.execute("UPDATE quant_factor_candidates SET status=%s,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status<>'cancelled'",(phase+'_error',store.encode([event(phase+'_error',message=str(exc)[:1200])]),cid,uid,org))

def _append_development_trial(uid,org,row,req,result,gate,outcome,report_id,executor='human',f0_run_id=None):
    """Best-effort ledger row for a completed development test. Never blocks research."""
    from . import ledger
    with get_conn() as c:
        topic=c.execute("SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",(uid,org,row['project_id'])).fetchone()
        if not topic:return None
        project=c.execute("SELECT config FROM detect_projects WHERE user_id=%s AND id=%s",(uid,row['project_id'])).fetchone()
        pinned=(row.get('evidence') or {}).get('branch_id')
        active=pinned or ((project or {}).get('config') or {}).get('v5ActiveBranch')
        branch=None
        if active:
            branch=c.execute("SELECT id FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s",(active,uid,org,topic['id'])).fetchone()
        if not branch:
            branch=c.execute("SELECT id FROM quant_factor_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at LIMIT 1",(uid,org,topic['id'])).fetchone()
    if not branch:return None
    fa=result.get('factor_analysis') or {}
    metrics=result.get('metrics') or {}
    if not metrics and fa.get('rank_ic_mean') is not None:metrics={'rank_ic_mean':fa.get('rank_ic_mean')}
    code=(row.get('snapshot',{}).get('request') or {}).get('factor_code') or ''
    source_hash=(result.get('meta') or {}).get('factor_source_hash')
    implementation_hash=hashlib.sha256(code.encode()).hexdigest() if code else (source_hash or 'unknown')
    parameters={k:req.get(k) for k in ('universe','benchmark','groups','rebalance_days','execution_timing','portfolio_type')}
    parameters['holding_period']=topic['primary_holding_period']
    return ledger.append_trial(uid,org,topic['id'],{
        'branch_id':branch['id'],'implementation_hash':implementation_hash,'kind':'research',
        'parameters':parameters,'result_summary':{'metrics':metrics,'gate':{'passed':gate.get('passed'),'checks':gate.get('checks')}},
        'report_id':report_id,'executor':executor,'outcome':outcome,'f0_run_id':f0_run_id,
        'holding_period':topic['primary_holding_period']})


def _compare_library(uid,org,cid,row,data):
    from .novelty import assess
    def progress(action,message,**details):
        if store.read(uid,org,cid)['status']=='cancelled':return False
        if action:store.update(uid,org,cid,'development_running',event(action,message=message,**details))
        return True
    try:
        return assess(uid,row['snapshot'],data['result'],reference=row['evidence'].get('library_reference'),compute=data['gate'].get('numerical_passed',data['gate']['passed']),progress=progress,org=org)
    except Exception:
        # No exception/HTTP body can expose credentials; the saved report remains intact.
        return {'status':'unavailable','message':'因子库对照服务未完成，原研发报告已保留。恢复服务后可仅重试对照，不重跑回测。','gate':{'passed':False,'complete':False,'expected_count':row['evidence'].get('library_reference',{}).get('count',0),'compared_count':0,'max_abs_correlation':None,'threshold':row['snapshot']['plan'].get('noveltyPolicy',{}).get('maxAbsCorrelation'),'limitation':'数值对照未完成。'}}

def retry_novelty(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        if row['status']=='development_running':return public(dict(row))
        data=row['evidence'].get('development') or {}
        if row['status']!='development_error' or data.get('novelty',{}).get('status') not in ('unavailable','incomplete') or data.get('gate',{}).get('numerical_passed') is not True:
            raise WorkflowError('仅允许重试数值检验已通过、对照服务未完成的固定候选。质量不通过须先改进研究。')
        if not row['evidence'].get('library_reference') or row['evidence'].get('validation'):
            raise WorkflowError('缺少冻结对照库或已进行样本外复验，不能重试本候选的研发对照。')
        p=get_project(uid,row['project_id'])['project']
        if digest(snapshot(p))!=row['snapshot_hash']:raise WorkflowError('研究输入已修改，不能用旧候选重试对照。')
        if c.execute("SELECT id FROM quant_factor_iterations WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('queued','running')",(uid,org,row['project_id'])).fetchone():
            raise WorkflowError('请等待当前自动循环停止后重试对照，避免并发执行。')
        c.execute("UPDATE quant_factor_candidates SET status='development_running',events=events||%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode([event('novelty_retry_queued',message='仅重试冻结库对照，复用原研发报告，不新增候选或重跑回测。')]),cid))
    _dispatch(uid,org,cid,None)
    return current(uid,org,cid)

def _retry_novelty(uid,org,cid):
    row=store.read(uid,org,cid);data=copy.deepcopy(row['evidence']['development'])
    novelty=_compare_library(uid,org,cid,row,data)
    data['novelty']=novelty
    data['gate']={**data['gate'],'passed':novelty.get('gate',{}).get('passed') is True}
    status='development_error' if novelty['status'] in ('unavailable','incomplete') else 'development_passed' if data['gate']['passed'] else 'development_failed'
    store.update(uid,org,cid,status,event('novelty_retry_completed',message=novelty['message'],status=novelty['status']),{'development':data})

def cancel(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        if not row['status'].endswith('_running'):raise WorkflowError('当前没有可取消的计算')
        c.execute("UPDATE quant_factor_candidates SET status='cancelled',events=events||%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode([event('cancel_requested')]),cid))
    return current(uid,org,cid)

def archive(uid,org,cid,note):
    if not isinstance(note,str) or not note.strip() or len(note)>3000: raise WorkflowError('请填写不超过3000字的研究留档说明')
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        if row['status'].endswith('_running'):raise WorkflowError('请等待计算结束或先取消')
        if row['archive']:return public(dict(row))
        card={'purpose':'research_only','note':note.strip(),'snapshot_hash':row['snapshot_hash'],'at':datetime.now(timezone.utc).isoformat(),'approved':False,'sealed':False}
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('research_archived',purpose='research_only')]),cid))
    return current(uid,org,cid)

def register_asset(uid,org,cid,library_id):
    from services.factor.user_library_store import list_library_factors,add_library_factor
    # Existing platform service enforces library ownership. Never publish to community.
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        if not row['archive']:raise WorkflowError('请先保存研究因子卡与证据')
        if row['archive'].get('factor'):return public(dict(row))
        req=row['snapshot']['request'];code=req.get('factor_code')
        if not code:raise WorkflowError('内置因子无需复制入库，可直接在已有库中复用；冻结研究证据已留档')
        factors=list_library_factors(uid,library_id)
        existing=next((f for f in factors if f['name']==req['factor_name']),None)
        if existing and existing['body'].strip()!=code.strip():raise WorkflowError('目标库已有同名不同实现，不能覆盖。请在工程计算中明确新的版本名称')
        asset=existing or add_library_factor(uid,library_id,name=req['factor_name'],body=code,
              description=row['snapshot']['plan']['hypothesis']+'\n研究留档，未通过正式准入。证据版本：'+row['snapshot_hash'],category_label='研究留档_未准入')
        card={**row['archive'],'factor':{'id':asset['id'],'libraryId':asset['libraryId'],'name':asset['name']}}
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('factor_library_registered',factor_id=asset['id'],library_id=asset['libraryId'],purpose='research_only')]),cid))
    return current(uid,org,cid)


def control_status(uid, org):
    with get_conn() as c:
        row = c.execute(
            "SELECT paused,paused_by,paused_at,updated_at FROM quant_factor_org_controls WHERE org_id=%s",
            (org,)).fetchone()
    return {"paused": bool(row and row["paused"]), "paused_at": row["paused_at"] if row else None,
            "paused_by": row["paused_by"] if row else None,
            "updated_at": row["updated_at"] if row else None}


def set_global_pause(uid, org, paused):
    with get_conn() as c:
        c.execute(
            """INSERT INTO quant_factor_org_controls(org_id,paused,paused_by,paused_at,updated_at)
               VALUES (%s,%s,%s,CASE WHEN %s THEN NOW() ELSE NULL END,NOW())
               ON CONFLICT (org_id) DO UPDATE
                 SET paused=EXCLUDED.paused,paused_by=EXCLUDED.paused_by,
                     paused_at=CASE WHEN EXCLUDED.paused THEN NOW() ELSE NULL END,updated_at=NOW()""",
            (org, bool(paused), uid, bool(paused)))
    return control_status(uid, org)


def retry_development(uid, org, cid):
    """Re-dispatch an interrupted/failed development run on the same frozen candidate."""
    row = store.read(uid, org, cid)
    if row["status"] != "development_error":
        raise WorkflowError("只有研发计算异常的固定候选可以重试；已通过/未通过请新建研究版本")
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9106, uid))
        topic = c.execute(
            "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",
            (uid, org, row["project_id"])).fetchone()
        if topic:
            from . import ledger
            used = ledger.current_k(ledger._trials(uid, org, topic["id"]), topic["primary_holding_period"])
            running = c.execute(
                "SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND id<>%s AND status IN ('development_running','development_queued')",
                (uid, org, row["project_id"], cid)).fetchone()["n"]
            if used + int(running) >= int(topic["max_trials"]):
                raise WorkflowError("课题 K 已达到试验预算（含在途检验），不能重试；请先复盘并明确修订计划")
    evidence = dict(row.get("evidence") or {})
    block = dict(evidence.get("development") or {})
    if not block.get("interrupted"):
        raise WorkflowError("该异常没有可重试的中断标记；请从 F4 重新发起研究")
    block.update({"interrupted": False, "message": ""})
    evidence["development"] = block
    store.update(uid, org, cid, "development_running",
                 event("development_retry", message="用户重试中断的研发检验"), evidence)
    _dispatch(uid, org, cid, "development", "human")
    return current(uid, org, cid)


def mark_interrupted_candidates() -> int:
    """BFF 重启后在途 F4 线程已不存在；标记为可重试的中断，不伪造结果。"""
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id,user_id,org_id,status,evidence FROM quant_factor_candidates "
            "WHERE status LIKE '%_running'").fetchall()]
    marked = 0
    for row in rows:
        phase = str(row["status"]).split("_")[0]
        if phase not in ("development", "validation"):
            continue
        evidence = dict(row.get("evidence") or {})
        block = dict(evidence.get(phase) or {})
        block.update({
            "interrupted": True,
            "message": "开发服务重启，在途计算未能回写；请从 F4 重新发起受控检验。",
        })
        evidence[phase] = block
        try:
            store.update(row["user_id"], row["org_id"], row["id"], phase + "_error",
                         event("run_interrupted", message=block["message"]), evidence)
            marked += 1
        except Exception:
            continue
    return marked


