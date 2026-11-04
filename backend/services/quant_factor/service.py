from __future__ import annotations
import copy
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from services.core.db import get_conn
from services.factor.detect_store import get_project, _row_project, save_run
from services.factor.re_factor_async_proxy import proxy_submit_factor_backtest,proxy_get_factor_run,proxy_cancel_factor_run
from services.strategy.result_signature import sign_result
from .policy import WorkflowError,snapshot,digest,evaluate,compare_identity
from . import store

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='quant-factor-verify')

def event(action,**details): return {'at':datetime.now(timezone.utc).isoformat(),'action':action,**details}

def public(row):
    return {k:v for k,v in row.items() if k not in ('user_id','org_id')}

def current(uid,org,cid):
    row=store.read(uid,org,cid)
    if row['status'].endswith('_running') and (datetime.now(timezone.utc)-row['updated_at']).total_seconds()>1800:
        store.update(uid,org,cid,row['status'].replace('_running','_error'),event('execution_interrupted',message='计算超过恢复窗口，可能服务中断；已保留证据，未自动重试'))
        row=store.read(uid,org,cid)
    try: row['stale']=digest(snapshot(get_project(uid,row['project_id'])['project']))!=row['snapshot_hash']
    except (KeyError,WorkflowError): row['stale']=True
    return public(row)

def create(uid,org,project_id):
    with get_conn() as c:
        # Serialize creation per actor: budget and duplicate checks must be atomic.
        c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
        p=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,project_id)).fetchone()
        if not p: raise KeyError(project_id)
        snap=snapshot(_row_project(dict(p))); sha=digest(snap)
        existing=c.execute('SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND snapshot_hash=%s',(uid,org,project_id,sha)).fetchone()
        if existing: return current(uid,org,existing['id'])
        count=c.execute('SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,project_id)).fetchone()['n']
        if count>=snap['plan']['maxTrials']: raise WorkflowError('本研究已达到登记的候选尝试预算；请先复盘并明确修订计划')
        pending=c.execute("SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE status LIKE '%%_running'").fetchone()['n']
        if pending>=4: raise WorkflowError('验证计算队列繁忙，请稍后提交')
        cid=str(uuid.uuid4())
        c.execute('INSERT INTO quant_factor_candidates(id,user_id,org_id,project_id,snapshot,snapshot_hash,status,events) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)',(cid,uid,org,project_id,store.encode(snap),sha,'development_running',store.encode([event('candidate_frozen',snapshot_hash=sha),event('development_queued')])) )
    POOL.submit(run,uid,org,cid,'development')
    return current(uid,org,cid)

def validate(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row: raise KeyError(cid)
        if row['status']!='development_passed': raise WorkflowError('只有研发检验通过的冻结候选可以提交一次样本外复验')
        p=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,row['project_id'])).fetchone()
        if not p or digest(snapshot(_row_project(dict(p))))!=row['snapshot_hash']: raise WorkflowError('研究输入已变化，请重新冻结并检验当前版本')
        c.execute("UPDATE quant_factor_candidates SET status='validation_running',events=events||%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode([event('validation_queued',sealed=False)]),cid))
    POOL.submit(run,uid,org,cid,'validation')
    return current(uid,org,cid)

def run(uid,org,cid,phase):
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
        result=task.get('result') or {}; gate=evaluate(result,snap['rules'])
        if phase=='validation': compare_identity(row['evidence']['development']['result'],result)
        # Trusted server-to-server result, signed through the existing report persistence contract.
        signed={**result,'_svquant_verified_token':sign_result(uid,result)}
        report_id='qf_'+cid+'_'+phase
        save_run(uid,{'id':report_id,'projectId':row['project_id'],'factorName':req['factor_name'],
                     'description':snap['name']+' / '+phase,'request':{**req,'_re_run_id':rid},'result':signed})
        data={'run_id':rid,'report_id':report_id,'request':req,'result':result,'gate':gate}
        with get_conn() as c:
            locked=c.execute('SELECT status FROM quant_factor_candidates WHERE id=%s FOR UPDATE',(cid,)).fetchone()
            if locked['status']=='cancelled': return
            c.execute('UPDATE quant_factor_candidates SET status=%s,evidence=evidence||%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',
                      (phase+('_passed' if gate['passed'] else '_failed'),store.encode({phase:data}),store.encode([event(phase+'_completed',passed=gate['passed'],checks=gate['checks'],report_id=report_id)]),cid))
    except Exception as exc:
        with get_conn() as c:
            c.execute("UPDATE quant_factor_candidates SET status=%s,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status<>'cancelled'",(phase+'_error',store.encode([event(phase+'_error',message=str(exc)[:1200])]),cid,uid,org))

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
