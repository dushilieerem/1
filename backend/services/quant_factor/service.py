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
from .re_client import proxy_submit_factor_backtest,proxy_get_factor_run,proxy_cancel_factor_run,legacy_get_factor_run,legacy_cancel_factor_run
from . import re_client
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
    out={k:v for k,v in row.items() if k not in ('user_id','org_id')}
    if (row.get('archive') or {}).get('research_asset'):
        from .assets import serialize
        out['archive']={**row['archive'],'research_asset':serialize(row['archive']['research_asset'],row['org_id'],full=False)}
    return out

def current(uid,org,cid):
    row=store.read(uid,org,cid)
    if row['status'].endswith('_running') and (datetime.now(timezone.utc)-row['updated_at']).total_seconds()>2400:
        store.update(uid,org,cid,row['status'].replace('_running','_error'),event('execution_interrupted',message='计算超过恢复窗口，可能服务中断；已保留证据，未自动重试'))
        row=store.read(uid,org,cid)
    try: row['stale']=digest(snapshot(get_project(uid,row['project_id'])['project']))!=row['snapshot_hash']
    except (KeyError,WorkflowError): row['stale']=True
    with get_conn() as c:
        topic=c.execute('SELECT id FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,row['project_id'])).fetchone()
    from .presentation import context,candidate_identity
    row['presentation']=candidate_identity(row,context(uid,org,row['project_id']))
    row['validation_mode']='sealed' if topic else 'legacy'
    from .review import feedback_materials
    try:row['feedback_eligibility']={'allowed':True,**feedback_materials(row)}
    except WorkflowError as exc:row['feedback_eligibility']={'allowed':False,'reason':str(exc)}
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


def _reserved_development(c,uid,org,project_id,exclude_id=''):
    row=c.execute("""SELECT COUNT(*) AS n FROM quant_factor_candidates q
        WHERE q.user_id=%s AND q.org_id=%s AND q.project_id=%s AND q.id<>%s
          AND (q.status='development_running' OR
            (q.evidence->'development'->'result' IS NOT NULL AND q.evidence->'development'->'result' NOT IN ('null'::jsonb,'{}'::jsonb)) OR
            (q.status='development_error' AND q.evidence->'development'->>'interrupted'='true'
             AND COALESCE(q.evidence->'development'->>'external_status','') NOT IN ('failed','cancelled')))
          AND NOT EXISTS(SELECT 1 FROM quant_factor_trials t
              WHERE t.user_id=q.user_id AND t.org_id=q.org_id AND t.project_id=q.project_id
                AND t.report_id='qf_'||q.id||'_development')""",(uid,org,project_id,exclude_id)).fetchone()
    return int(row['n'])


def create(uid,org,project_id,expected_snapshot_hash=None,reference=None,executor='human',f0_run_id=None,expected_control_epoch=None,expected_run_epoch=None):
    locked=_locked_view_error(uid,org,project_id)
    if locked:raise WorkflowError(locked)
    with get_conn() as c:
        # Serialize creation per actor: budget and duplicate checks must be atomic.
        c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
        p=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,project_id)).fetchone()
        if not p: raise KeyError(project_id)
        if executor=='agent' and f0_run_id:
            owner=c.execute('SELECT status,decision FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s AND project_id=%s',(f0_run_id,uid,org,project_id)).fetchone()
            topic_state=c.execute('SELECT status FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,project_id)).fetchone()
            if not owner or owner['status']!='running' or (expected_run_epoch is not None and (owner.get('decision') or {}).get('runner_epoch')!=expected_run_epoch) or not topic_state or topic_state['status']!='active' or (p.get('config') or {}).get('v5ControlEpoch')!=expected_control_epoch:raise WorkflowError('研究控制版本已改变，未从旧的研究系统动作启动计算')
        snap=snapshot(_row_project(dict(p))); sha=digest(snap)
        if snap.get('sourceResearchAsset'):
            from .assets import detail as asset_detail
            ref=snap['sourceResearchAsset'];source=asset_detail(uid,org,ref.get('id',''))
            if ref.get('snapshotHash')!=source['snapshot_hash'] or ref.get('version')!=source['version']:raise WorkflowError('引用资产版本与固定登记不一致')
        if expected_snapshot_hash and sha!=expected_snapshot_hash:raise WorkflowError('研究输入已变更，停止自动提交，未覆盖人工修改。')
        existing=c.execute('SELECT id,status,evidence FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND snapshot_hash=%s',(uid,org,project_id,sha)).fetchone()
        if existing:
            if reference and existing['evidence'].get('library_reference',{}).get('hash')!=reference['hash']:
                raise WorkflowError('已有候选的对照库版本不同，请复盘后开启新的研究任务。')
            cid=existing['id']
        else:
            from .resources import require_config
            require_config(_row_project(dict(p))['config'])
            from . import ledger
            topic=c.execute("SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",(uid,org,project_id)).fetchone()
            if topic:
                used=ledger.current_k(ledger._trials(uid,org,topic['id']),topic['primary_holding_period'])
                reserved=_reserved_development(c,uid,org,project_id)
                if used+int(reserved)>=int(topic['max_trials']):
                    raise WorkflowError('课题 K 已达到试验预算（已计入在途检验）；请先复盘并明确修订计划')
            else:
                count=c.execute('SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,project_id)).fetchone()['n']
                if count>=snap['plan']['maxTrials']: raise WorkflowError('本研究已达到登记的候选尝试预算；请先复盘并明确修订计划')
            pending=c.execute("SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND status LIKE '%%_running'",(uid,org)).fetchone()['n']
            if pending>=4: raise WorkflowError('验证计算队列繁忙，请稍后提交')
            cid=str(uuid.uuid4())
            from .provenance import method_manifest
            evidence={'method':{**method_manifest(sha,executor,f0_run_id,research_contract=snap['plan'].get('researchContract')),'control_epoch':(p.get('config') or {}).get('v5ControlEpoch')}}
            if snap['request'].get('factor_code'):
                from .source_contract import inspect_source
                evidence['method']['source_contract']=inspect_source(snap['request']['factor_code'],snap['request']['factor_name'])
            active_branch=((p.get('config') or {}).get('v5ActiveBranch') if hasattr(p,'get') else None)
            if active_branch:
                evidence['branch_id']=str(active_branch)
            if snap['plan'].get('researchPurpose') in ('discovery','replication'):
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
        rows=c.execute("SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('development_passed','development_failed','development_error','cancelled') ORDER BY created_at",(uid,org,project_id)).fetchall()
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
    if row['status'] not in ('development_passed','development_failed','development_error','cancelled'):return None
    data=(row.get('evidence') or {}).get('development') or {}
    result=data.get('result') or {};gate=data.get('gate') or {}
    if not result or not gate:return None
    report_id=data.get('report_id') or 'qf_'+cid+'_development'
    with _BACKFILL_LOCK:
        with get_conn() as c:
            exists=c.execute("SELECT id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND project_id=%s AND report_id=%s",(uid,org,row['project_id'],report_id)).fetchone()
        if exists:return None
        outcome='cancelled' if row['status']=='cancelled' else 'error' if row['status']=='development_error' else 'passed' if row['status']=='development_passed' else 'failed'
        req=data.get('request') or row['snapshot']['request']
        return _append_development_trial(uid,org,row,req,result,gate,outcome,report_id,executor,f0_run_id)

def validate(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row: raise KeyError(cid)
        if (row.get('archive') or {}).get('research_asset'):raise WorkflowError('已登记版本不可重新验证，改进请建立新候选')
        topic=c.execute('SELECT id FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,row['project_id'])).fetchone()
        if topic:raise WorkflowError('V5任务请在独立验证环节申请封存验证；研究侧不开放样本外明细')
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


def run(uid,org,cid,phase,executor='human',f0_run_id=None,recovery_only=False):
    # Non-blocking execution lease shared by recovery/manual/queued workers.
    # API handlers never wait for this worker-only lock.
    with get_conn() as lease:
        acquired=lease.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS acquired",(f"quant-factor-compute:{uid}:{org}:{cid}:{phase}",)).fetchone()
        if not acquired or acquired['acquired'] is not True:return
        return _run_once(uid,org,cid,phase,executor,f0_run_id,recovery_only)


def _run_once(uid,org,cid,phase,executor='human',f0_run_id=None,recovery_only=False):
    running=phase+'_running'
    try:
        row=store.read(uid,org,cid)
        if row['status']=='cancelled' or (row.get('archive') or {}).get('research_asset'):return
        snap=row['snapshot']; req=copy.deepcopy(snap['request']);plan=snap['plan']
        req.update(start=plan[phase+'Start'],end=plan[phase+'End'])
        prior=dict((row.get('evidence') or {}).get(phase) or {})
        rid=prior.get('run_id')
        result=prior.get('result')
        if not result:
            if not rid:
                if recovery_only:raise WorkflowError('此恢复仅可查询原任务；缺少原运行标识，不会发起新计算')
                if prior.get('submission_started'):
                    raise WorkflowError('上次计算提交的结果尚未确认；请先核对外部任务，不能重复提交')
                if req.get('factor_code'):
                    from .causality import diagnose_source
                    try:source_check=diagnose_source(req['factor_code'],req['factor_name'])
                    except ValueError as exc:
                        implementation_check_failed=True
                        store.update(uid,org,cid,running,event('implementation_check_failed',message=str(exc)),{'source_contract':{'passed':False,'error':str(exc)}})
                        raise WorkflowError(str(exc)) from exc
                    if store.update(uid,org,cid,running,event('implementation_checked',message='实现一致性与有界因果性检查通过；不代表研究达标'),{'source_contract':source_check}) is False:return
                from .resources import require
                try:resource_receipt=require('factor',req)
                except WorkflowError:
                    resource_check_failed=True
                    raise
                prior['resource_preflight']=resource_receipt
                prior['compute_backend']=re_client.target(resource_receipt)
                prior.update(submission_started=True,request=req)
                if store.update(uid,org,cid,running,event(phase+'_submitting',message='已记录计算提交身份'),{phase:prior}) is False:return
                status,_,task=proxy_submit_factor_backtest(req,target=prior['compute_backend'])
                if status not in (200,202) or not isinstance(task,dict) or not task.get('run_id'):
                    raise WorkflowError('计算提交结果未确认；保留记录，不能盲目重复提交')
                rid=task['run_id'];prior.update(run_id=rid)
                if store.update(uid,org,cid,running,event(phase+'_submitted',tool='ResearchEngine.factor',run_id=rid),{phase:prior}) is False:
                    proxy_cancel_factor_run(rid,target=prior['compute_backend']) if prior.get('compute_backend') else legacy_cancel_factor_run(rid);return
            deadline=time.monotonic()+900
            while time.monotonic()<deadline:
                state=store.read(uid,org,cid)
                if state['status']=='cancelled':
                    proxy_cancel_factor_run(rid,target=prior['compute_backend']) if prior.get('compute_backend') else legacy_cancel_factor_run(rid);return
                status,_,task=proxy_get_factor_run(rid,target=prior['compute_backend']) if prior.get('compute_backend') else legacy_get_factor_run(rid)
                if status!=200: raise WorkflowError('计算状态暂无法确认；外部任务身份保留，HTTP '+str(status))
                if task.get('status')=='succeeded': break
                if task.get('status') in ('failed','cancelled'):
                    prior.update(external_status=task['status'],interrupted=False,message=('外部计算已失败' if task['status']=='failed' else '外部计算已停止')+': '+str(task.get('error') or '未返回结果')[:500])
                    store.update(uid,org,cid,phase+'_error',event(phase+'_external_terminal',status=task['status'],message=prior['message']),{phase:prior})
                    return
                time.sleep(2)
            else:
                raise WorkflowError('计算结果确认超时，原任务身份保留；稍后继续查询，不重复提交')
            result=task.get('result') or {}
        meta=result.get('meta') or {}
        expected=prior.get('expected_identity') or ((prior.get('result') or {}).get('meta') if recovery_only else None)
        if recovery_only and not expected:raise WorkflowError('原结果已取回，但缺少可核对的数据与源码身份，需人工确认，未纳入正式证据')
        if expected and any(not expected.get(k) or meta.get(k)!=expected[k] for k in ('data_release_id','factor_source_hash','spec_hash')):raise WorkflowError('原计算结果的数据、源码或规格身份不一致，不能合并到固定证据')
        gate=evaluate(result,snap['rules'],_gate_k(uid,org,row['project_id'],phase))
        if phase=='validation': compare_identity(row['evidence']['development']['result'],result)
        # Trusted server-to-server result, signed through the existing report persistence contract.
        signed={**result,'_svquant_verified_token':sign_result(uid,result)}
        report_id='qf_'+cid+'_'+phase
        save_run(uid,{'id':report_id,'projectId':row['project_id'],'factorName':req['factor_name'],
                     'description':snap['name']+' / '+phase,'request':{**req,'_re_run_id':rid},'result':signed})
        data={'run_id':rid,'report_id':report_id,'request':req,'result':result,'gate':gate,'expected_identity':{k:meta.get(k) for k in ('data_release_id','factor_source_hash','spec_hash')},**({'compute_backend':prior['compute_backend']} if prior.get('compute_backend') else {})}
        if recovery_only:
            data.update(interrupted=True,needs_fixed_version=True)
            store.update(uid,org,cid,phase+'_error',event('original_result_recovered',message='原结果已核对，等待固定数据版本计算能力，未发起新的计算'),{phase:data})
            if phase=='development':_append_development_trial(uid,org,row,req,result,gate,'error',report_id,executor,f0_run_id)
            return
        novelty_status=None
        if phase=='development' and snap['plan'].get('researchPurpose') in ('discovery','replication'):
            if store.update(uid,org,cid,running,event('novelty_assessment_started',message='核对查重条件，未执行的对照不会视为完成')) is False:return
            # Persist numerical evidence before a dependent service is called.
            if store.update(uid,org,cid,running,event('numerical_checks_completed',passed=gate['passed']),{phase:data}) is False:return
            novelty=_compare_library(uid,org,cid,row,data)
            data['novelty']=novelty;novelty_status=novelty['status']
            numerical_passed=gate['passed']
            gate={**gate,'numerical_passed':numerical_passed,'passed':numerical_passed and (snap['plan'].get('researchPurpose')=='replication' or novelty.get('gate',{}).get('passed') is True)}
            data['gate']=gate
            store.update(uid,org,cid,running,event('novelty_status_updated',status=novelty_status,message=novelty['message']))
            if snap['plan'].get('researchPurpose')=='replication':novelty_status=None
        final_status=phase+('_error' if novelty_status in ('unavailable','incomplete','resource_pending') else '_passed' if gate['passed'] else '_failed')
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
        # Preserve the last confirmed run identity; a polling timeout is not permission
        # to submit another computation or release the unresolved reservation.
        latest=store.read(uid,org,cid)
        if latest['status']=='cancelled':
            if locals().get('rid'):
                original=(latest.get('evidence') or {}).get(phase) or {}
                proxy_cancel_factor_run(rid,target=original['compute_backend']) if original.get('compute_backend') else legacy_cancel_factor_run(rid)
            return
        block=dict((latest.get('evidence') or {}).get(phase) or {})
        block.update(interrupted=not bool(locals().get('implementation_check_failed') or locals().get('resource_check_failed')),message=str(exc)[:1200])
        if locals().get('implementation_check_failed'):block['preflight_failure']='implementation'
        if locals().get('resource_check_failed'):block['preflight_failure']='resource'
        store.update(uid,org,cid,phase+'_error',event(phase+'_error',message=str(exc)[:1200]),{phase:block})

def recover_pending(uid, org, project_id,recovery_only=False):
    with get_conn() as c:
        rows=c.execute("SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status='development_error' AND evidence->'development'->>'interrupted'='true' ORDER BY created_at",(uid,org,project_id)).fetchall()
    for item in rows:
        run(uid,org,item['id'],'development','agent',None,recovery_only)
        recovered=store.read(uid,org,item['id'])
        block=(recovered.get('evidence') or {}).get('development',{})
        if block.get('external_status') in ('failed','cancelled') and not block.get('interrupted'):continue
        if recovery_only and block.get('needs_fixed_version'):continue
        if recovered['status']=='development_error' or recovered['status'].endswith('_running'):
            raise WorkflowError('已有检验仍需恢复确认；原任务和证据保留，尚未开始新的研究动作')


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
        if (row.get('archive') or {}).get('research_asset'):raise WorkflowError('已登记版本不可重新检验，改进请建立新候选')
        if row['status']=='development_running':return public(dict(row))
        data=row['evidence'].get('development') or {}
        if row['status'] not in ('development_error','development_passed') or data.get('novelty',{}).get('status') not in ('unavailable','incomplete') or data.get('gate',{}).get('numerical_passed') is not True:
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
    row=store.read(uid,org,cid)
    if (row.get('archive') or {}).get('research_asset'):return
    data=copy.deepcopy(row['evidence']['development'])
    novelty=_compare_library(uid,org,cid,row,data)
    data['novelty']=novelty
    replication=(row.get('snapshot') or {}).get('plan',{}).get('researchPurpose')=='replication'
    data['gate']={**data['gate'],'passed':data['gate'].get('numerical_passed') is True and (replication or novelty.get('gate',{}).get('passed') is True)}
    status='development_error' if not replication and novelty['status'] in ('unavailable','incomplete') else 'development_passed' if data['gate']['passed'] else 'development_failed'
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
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-factor-org-control:{org}',))
        c.execute(
            """INSERT INTO quant_factor_org_controls(org_id,paused,paused_by,paused_at,updated_at)
               VALUES (%s,%s,%s,CASE WHEN %s THEN NOW() ELSE NULL END,NOW())
               ON CONFLICT (org_id) DO UPDATE
                 SET paused=EXCLUDED.paused,paused_by=EXCLUDED.paused_by,
                     paused_at=CASE WHEN EXCLUDED.paused THEN NOW() ELSE NULL END,updated_at=NOW()""",
            (org, bool(paused), uid, bool(paused)))
    return control_status(uid, org)


def retry_development(uid, org, cid):
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9106, uid))
        row=c.execute("SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE",(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        if (row.get('archive') or {}).get('research_asset'):raise WorkflowError('已登记版本不可重新检验，改进请建立新候选')
        if row['status']=='development_running':return current(uid,org,cid)
        if row['status']!='development_error':raise WorkflowError('只有研发计算异常的固定候选可以恢复')
        block=dict((row.get('evidence') or {}).get('development') or {})
        if block.get('external_status') in ('failed','cancelled'):raise WorkflowError('原计算已明确结束；请保留失败或停止原因，修订研究后建立新候选')
        if not block.get('interrupted'):raise WorkflowError('该异常没有可恢复的中断记录，请先核对原计算')
        if not block.get('run_id') and block.get('submission_started'):
            raise WorkflowError('上次提交结果尚未确认，请先核对外部任务；不能重复提交')
        if not block.get('run_id') and not block.get('result'):
            from . import ledger
            topic=c.execute("SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",(uid,org,row['project_id'])).fetchone()
            if topic:
                used=ledger.current_k(ledger._trials(uid,org,topic['id']),topic['primary_holding_period'])
                if used+_reserved_development(c,uid,org,row['project_id'],cid)>=topic['max_trials']:raise WorkflowError('任务已达到试验预算（含待确认检验），不能新增检验')
        block.update(interrupted=False,message='')
        c.execute("UPDATE quant_factor_candidates SET status='development_running',evidence=evidence||%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode({'development':block}),store.encode([event('development_resume',message='继续确认原检验结果')]),cid))
    _dispatch(uid,org,cid,'development','human')
    return current(uid,org,cid)


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
            "message": "服务重启，原计算身份已保留；恢复时先确认原任务结果。",
        })
        evidence[phase] = block
        try:
            store.update(row["user_id"], row["org_id"], row["id"], phase + "_error",
                         event("run_interrupted", message=block["message"]), evidence)
            marked += 1
        except Exception:
            continue
    return marked




def locked_view_available(topic):
    """Read existing published metadata; availability alone never authorizes new RE work."""
    import json
    from services.quant_data_resources import _published_view_paths
    path=_published_view_paths().get(topic['view_id'])
    if not path or not topic.get('view_manifest_sha256'):return False
    raw=(path/'manifest.json').read_bytes();manifest=json.loads(raw)
    if manifest.get('view_id')!=topic['view_id'] or hashlib.sha256(raw).hexdigest()!=topic['view_manifest_sha256']:return False
    releases={k:v.get('release') for k,v in (manifest.get('datasets') or {}).items()}
    return all(releases.get(k)==v for k,v in (topic.get('release_ids') or {}).items())


def has_recoverable_run(uid,org,project_id):
    with get_conn() as c:
        return bool(c.execute("SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status='development_error' AND evidence->'development'->>'run_id' IS NOT NULL AND evidence->'development'->>'interrupted'='true' AND COALESCE(evidence->'development'->>'external_status','') NOT IN ('failed','cancelled') LIMIT 1",(uid,org,project_id)).fetchone())
