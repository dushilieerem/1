"""F0 constrained next-step runner.

One run executes at most one authorised development test on the selected branch.
Budget, locked view, branch ownership and idempotency are enforced server-side.
F0 never approves, seals or changes gates; those stay human/F5 actions.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from functools import partial

from services.core.db import get_conn
from services.workflow_workspace.platform_data import published_view

from . import decision_engine, f0_agent, ledger, service
from .policy import WorkflowError,digest,snapshot

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quant-factor-f0")
ACTIVE = ("queued", "running")


def _public(row) -> dict:
    out={key:value for key,value in dict(row).items() if key not in ('user_id','org_id')}
    if (out.get('decision') or {}).get('method_version')=='bounded-factor-rd-v2' or (out.get('decision') or {}).get('reason')=='locked_view_drift':
        from .research_method import compatibility
        out['method_compatibility']=compatibility(out['decision'].get('method_snapshot'))
        out['method_compatibility']['configuration_changed']=out['method_compatibility']['requires_new_run']
        if out.get('status')=='failed' or (out.get('decision') or {}).get('recovery_requires_new_run'):out['method_compatibility']['requires_new_run']=True
    return out


def _topic(uid, org, topic_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s",
            (topic_id, uid, org)).fetchone()
    if not row:
        raise KeyError(topic_id)
    return dict(row)


def _record(uid, org, topic, branch_id, key, status, decision=None, reason="", rounds=0,connection=None):
    run_id = str(uuid.uuid4())
    with nullcontext(connection) if connection is not None else get_conn() as c:
        c.execute(
            """INSERT INTO quant_factor_f0_runs
               (id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,
                decision,rounds,stop_reason,view_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (run_id, uid, org, topic["project_id"], topic["id"], branch_id, key, status,
             service.store.encode(decision or {}), rounds, reason, topic["view_id"]))
        row = c.execute("SELECT * FROM quant_factor_f0_runs WHERE id=%s", (run_id,)).fetchone()
    return dict(row)


def start(uid,org,topic_id,branch_id,idempotency_key,handoff=None,method_change=None):
    with get_conn() as lock:
        lock.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
        lock.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-factor-start:{uid}:{org}:{topic_id}',))
        row=_start_locked(uid,org,topic_id,branch_id,idempotency_key,handoff,lock,method_change)
        schedule=row.pop('_schedule',False)
    # The worker cannot observe an uncommitted queued row.
    if schedule:
        from . import research_queue
        if research_queue.enabled():research_queue.wake()
        else:POOL.submit(run,uid,org,row['id'])
    return row


def _start_locked(uid,org,topic_id,branch_id,idempotency_key,handoff=None,connection=None,method_change=None):
    key=str(idempotency_key or '').strip()
    if not 1<=len(key)<=100:raise WorkflowError('请提供1至100字符的提交身份')
    topic=_topic(uid,org,topic_id);record=partial(_record,connection=connection)
    with nullcontext(connection) if connection is not None else get_conn() as c:
        branch=c.execute('SELECT * FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s',(branch_id,uid,org,topic_id)).fetchone()
        if not branch:raise KeyError(branch_id)
        existing=c.execute('SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND idempotency_key=%s',(uid,org,topic_id,key)).fetchone()
        if existing:
            old=(existing.get('decision') or {}).get('manual_handoff') or {}
            if handoff and old.get('snapshot_hash')!=handoff.get('snapshot_hash'):raise WorkflowError('此提交已绑定另一版本，请先核对原运行，未覆盖原记录')
            if method_change:
                transition=(existing.get('decision') or {}).get('method_transition') or {}
                if transition.get('previous_run_id')!=method_change.get('previous_run_id') or transition.get('new_snapshot_hash')!=method_change.get('expected_method_hash') or transition.get('expected_control_epoch')!=method_change.get('expected_control_epoch'):raise WorkflowError('同一提交身份已绑定另一方法或控制版本，请核对原运行')
            return _public(existing)
        active=c.execute("SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",(uid,org,topic_id)).fetchone()
        if active:return _public(active)
        if topic['status']!='active' and not (handoff and topic['status']=='paused'):
            return _public(record(uid,org,topic,branch_id,key,'stopped',{'action':'stop','reason':'topic_'+topic['status']},'课题处于暂停/归档状态，研究系统不再调度'))
        if service.control_status(uid,org)['paused']:
            return _public(record(uid,org,topic,branch_id,key,'stopped',{'action':'stop','reason':'global_pause'},'研究负责人已暂停全部：不启动新的自动研究动作'))
        k_now=ledger.current_k(ledger._trials(uid,org,topic_id),topic['primary_holding_period']);remaining=int(topic['max_trials'])-k_now
        can_seal=False
        if remaining<=0:
            from .novelty_policy import handoff_allowed
            candidate=c.execute("SELECT * FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status='development_passed' AND evidence->>'branch_id'=%s ORDER BY updated_at DESC LIMIT 1",(uid,org,topic['project_id'],branch_id)).fetchone()
            used=c.execute('SELECT COUNT(*) AS n FROM quant_factor_sealed_validations WHERE user_id=%s AND org_id=%s AND topic_id=%s',(uid,org,topic_id)).fetchone()['n']
            can_seal=bool(candidate and handoff_allowed(candidate) and used<int(topic.get('max_sealed') or 1))
        if remaining<=0 and not can_seal:
            return _public(record(uid,org,topic,branch_id,key,'stopped',{'action':'stop','reason':'budget_exhausted'},'课题试验预算已用尽，研究已停止'))
        from services.factor.detect_store import get_project,_row_project
        from .resources import require_config
        from .research_contract import project_contract,METHOD_VERSION
        initial_project=get_project(uid,topic['project_id'])['project']
        contract=project_contract(initial_project);config=initial_project['config'];initial_control_epoch=config.get('v5ControlEpoch')
        manual_marker=config.get('v5ManualVersion') or {}
        if ((manual_marker.get('branch_id')==branch_id and manual_marker.get('source')=='human_workbench_save') or (branch.get('source')=='manual' and branch.get('parent_id'))) and not handoff:raise WorkflowError('当前有已保存人工版本；请明确从该版本交回，不能让新规划覆盖人工实现')
        decision={'action':'decide','method_version':METHOD_VERSION if contract else 'factor-f0-v1','contract_hash':contract['contract_hash'] if contract else None}
        if handoff:
            project_row=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,topic['project_id'])).fetchone()
            if not project_row:raise KeyError(topic['project_id'])
            project=_row_project(dict(project_row));config=project['config'];epoch=config.get('v5ControlEpoch')
            if handoff.get('acknowledged') is not True or branch['source']!='manual' or not epoch or epoch!=handoff.get('control_epoch') or config.get('v5ActiveBranch')!=branch_id:
                raise WorkflowError('请明确确认当前人工分支及控制版本，未从其他分支继续')
            if digest(snapshot(project))!=handoff.get('snapshot_hash'):raise WorkflowError('人工版本已变化，请重新读取并确认交回，未覆盖当前输入')
            for table,clause in [('quant_factor_candidates',"status LIKE '%%_running'"),('quant_factor_iterations',"status IN ('queued','running')"),('quant_factor_sealed_validations',"status IN ('queued','running')")]:
                if c.execute('SELECT id FROM '+table+' WHERE user_id=%s AND org_id=%s AND project_id=%s AND '+clause+' LIMIT 1',(uid,org,topic['project_id'])).fetchone():raise WorkflowError('当前仍有在途检验，请等待结果落账后交回')
            epoch=str(uuid.uuid4());config['v5ControlEpoch']=epoch
            c.execute('UPDATE detect_projects SET config=%s::jsonb,updated_at=NOW() WHERE user_id=%s AND id=%s',(service.store.encode(config),uid,topic['project_id']))
            c.execute("UPDATE quant_factor_topics SET status='active',updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s",(topic_id,uid,org))
            decision['manual_handoff']={'snapshot_hash':handoff['snapshot_hash'],'branch_id':branch_id,'control_epoch':epoch,'note':str(handoff.get('note') or '')[:2000],'at':service.event('handoff')['at']}
        elif remaining>0:
            project=get_project(uid,topic['project_id'])['project'];config=project['config'];active_branch=config.get('v5ActiveBranch')
            if active_branch and active_branch!=branch_id:raise WorkflowError('当前工程稿绑定另一分支，请明确选择当前版本或接手后继续')
        if contract:
            from .research_method import snapshot as method_snapshot,validate_snapshot
            frozen_method=method_snapshot()
            prior=c.execute('SELECT id,status,decision FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC LIMIT 1',(uid,org,topic_id)).fetchone()
            prior_snapshot=(prior.get('decision') or {}).get('method_snapshot') if prior else None
            if prior and (prior_snapshot!=frozen_method or prior['status']=='failed' or (prior.get('decision') or {}).get('recovery_requires_new_run')) and not method_change and not (handoff and prior_snapshot==frozen_method):
                raise WorkflowError('当前研究方法已更新；请明确使用更新方法创建新运行，原任务、分支及K保留')
            if method_change:
                if not prior or prior['id']!=method_change.get('previous_run_id') or prior['status'] not in ('failed','stopped') or method_change.get('acknowledged') is not True or method_change.get('expected_method_hash')!=frozen_method['snapshot_hash'] or not config.get('v5ControlEpoch') or method_change.get('expected_control_epoch')!=initial_control_epoch:
                    raise WorkflowError('请重新确认上一运行、当前方法与控制版本，未创建新的模型尝试')
                decision['method_transition']={'previous_run_id':prior['id'],'previous_snapshot_hash':(prior_snapshot or {}).get('snapshot_hash'),'new_snapshot_hash':frozen_method['snapshot_hash'],'reason':str(method_change.get('reason') or '用户明确采用更新后的研究方法')[:1000],'expected_control_epoch':method_change['expected_control_epoch'],'actor_user_id':uid,'at':service.event('method_changed')['at']}
            decision['method_snapshot']=frozen_method
        from .factor_window import conflict as window_conflict
        window_error=window_conflict(initial_project.get('name'),(config.get('researchPlan') or {}).get('hypothesis'),(config.get('draftFactor') or {}).get('body'))
        if window_error:raise WorkflowError(window_error)
        decision['control_epoch']=config.get('v5ControlEpoch')
        try:
            from .locked_data import for_topic
            for_topic(topic)
            require_config(config)
        except (WorkflowError,ValueError,OSError) as exc:
            decision['technical_wait']={'kind':'fixed_data_or_resources','message':str(exc)[:1000]}
            return _public(record(uid,org,topic,branch_id,key,'stopped',decision,'等待固定数据与计算范围确认：'+str(exc)[:800]))
        from . import research_queue
        if research_queue.enabled():decision['queue_deployment']=research_queue.DEPLOYMENT_ID
        saved=record(uid,org,topic,branch_id,key,'queued',decision)
        if research_queue.enabled():research_queue.enqueue(c,'f0',saved['id'],uid,org)
        row=_public(saved);row['_schedule']=True
        return row


def _owns_worker(uid,org,run_id,worker_epoch):
    with get_conn() as c:
        return c.execute("SELECT id FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s AND status='running' AND decision->>'runner_epoch'=%s",(run_id,uid,org,worker_epoch)).fetchone() is not None


def run(uid, org, run_id):
    worker_epoch=None
    try:
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE",
                (run_id, uid, org)).fetchone()
            if not row or row["status"] != 'queued':
                return
            worker_epoch=str(uuid.uuid4())
            c.execute("UPDATE quant_factor_f0_runs SET status='running',decision=jsonb_set(decision,'{runner_epoch}',to_jsonb(%s::text)),updated_at=NOW() WHERE id=%s",(worker_epoch,run_id))
        topic = _topic(uid, org, row["topic_id"])
        if (row.get('decision') or {}).get('method_version')=='bounded-factor-rd-v2' and not (row.get('decision') or {}).get('recovery_only'):
            from .research_method import validate_snapshot
            validate_snapshot((row.get('decision') or {}).get('method_snapshot'))
        steps = []
        current_steps = list((row.get("decision") or {}).get("steps") or [])
        base_decision={key:value for key,value in (row.get("decision") or {}).items() if key not in ("steps","current_action")}
        def execute_step(decision, step):
            with get_conn() as c:
                c.execute("UPDATE quant_factor_f0_runs SET decision=decision||%s::jsonb,updated_at=NOW() WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s",
                          (service.store.encode({"steps": current_steps, "current_action": decision.action}), run_id,worker_epoch))
            if not _owns_worker(uid,org,run_id,worker_epoch):raise WorkflowError('当前研究已由新的控制版本接管，旧动作未执行')
            return f0_agent.execute(uid, org, run_id, topic, decision, step,worker_epoch=worker_epoch)

        def on_step(step, entry, current):
            nonlocal current_steps
            current_steps = list(current)
            with get_conn() as c:
                from .research_advice import decisions_after_result
                saved=c.execute('SELECT decision FROM quant_factor_f0_runs WHERE id=%s FOR UPDATE',(run_id,)).fetchone()
                advice=decisions_after_result(((saved or {}).get('decision') or {}).get('human_advice') or [],entry.get('decision',{}).get('proposal') or {},entry.get('result') or {})
                next_branch=(entry.get('result') or {}).get('branch_id')
                if next_branch:advice=[{**a,'status':'not_adopted','reason':'未采用：目标研究分支已变化'} if a['status']=='pending' and a['input']['branch_id']!=next_branch else a for a in advice]
                c.execute("UPDATE quant_factor_f0_runs SET rounds=%s,decision=decision||%s::jsonb,updated_at=NOW() WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s",
                          (step, service.store.encode({"steps": current,"current_action":None,"current_phase":None,"human_advice":advice}), run_id,worker_epoch))

        # A reused frozen candidate can carry a completed test that never reached the ledger;
        # record it before deciding so K and the trial evidence are truthful.
        service.recover_pending(uid, org, topic["project_id"],recovery_only=bool((row.get("decision") or {}).get("recovery_only")))
        service.backfill_terminal_trials(uid, org, topic["project_id"], "agent", run_id)
        if (row.get("decision") or {}).get("recovery_only"):
            with get_conn() as c:
                c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason=%s,updated_at=NOW() WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s",('locked_view_drift：原结果已恢复，等待固定数据版本计算能力；未发新研究',run_id,worker_epoch))
            return
        k0 = ledger.current_k(ledger._trials(uid, org, topic["id"]), topic["primary_holding_period"])
        from . import research_queue
        max_steps = 3 if research_queue.enabled() else min(max(0,12-len(current_steps)),max(1,int(topic['max_trials'])-k0+2))

        def before_step(step):
            if not _owns_worker(uid,org,run_id,worker_epoch):return '研究已由新的控制版本接管'
            current = _topic(uid, org, topic["id"])
            if current["status"] != "active":
                return "课题已暂停/归档，F0 停止"
            ctx=f0_agent._context(uid,org,topic,run_id)
            if (ctx.get('novelty') or {}).get('status')=='resource_pending':return '研发数值检验已完成，正式查重范围待确认；停止自动迭代，可提交研究复盘'
            return ""

        def stop_when(decision, result):
            if result.get('action')=='request_seal':return '独立验证完成，交人工审查'
            # Statistical failures inform the next planner; they are not a fixed
            # rule to abandon the research direction after three attempts.
            return ''

        steps, stop_reason = decision_engine.run_steps(
            decide=lambda step: (f0_agent.Decision(action='run_test',branch_id=base_decision['manual_handoff']['branch_id'],rationale='先按已确认人工版本检验；同一快照已有证据则复用，不重置试验计数'),{'tokens_in':0,'tokens_out':0,'manual_handoff':True}) if base_decision.get('manual_handoff') and step==1 else f0_agent.decide(uid, org, topic, run_id),
            execute=execute_step,
            max_steps=max_steps,
            before_step=before_step,
            stop_when=stop_when,
            on_step=on_step,
            initial_steps=current_steps,
            exhausted_reason="本轮调度步数已用完，研究结论未定；保存检查点等待继续")
        with get_conn() as c:
            from .research_advice import close_pending
            if stop_reason=='本轮调度步数已用完，研究结论未定；保存检查点等待继续' and research_queue.enabled():
                c.execute("UPDATE quant_factor_f0_runs SET status='queued',rounds=%s,decision=decision||%s::jsonb,stop_reason='',updated_at=NOW() WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s",(len(steps),service.store.encode({'scheduler_yield':True,'current_action':None,'current_phase':None}),run_id,worker_epoch))
                return
            close_pending(c,uid,org,run_id=run_id,worker_epoch=worker_epoch,reason='未采用：研究已结束')
            c.execute("""UPDATE quant_factor_f0_runs
                       SET status='stopped',rounds=%s,stop_reason=%s,updated_at=NOW()
                       WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s""",
                      (len(steps), stop_reason, run_id,worker_epoch))
    except Exception as exc:
        if worker_epoch is None:return
        with get_conn() as c:
            from .research_advice import close_pending
            close_pending(c,uid,org,run_id=run_id,worker_epoch=worker_epoch,reason='未采用：研究已结束或中断')
            from . import research_queue
            if research_queue.enabled():
                c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason=%s,decision=decision||%s::jsonb,updated_at=NOW() WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s",(str(exc)[:1000],service.store.encode({'technical_wait':{'kind':'execution_dependency','message':str(exc)[:1000]},'recovery_requires_new_run':True,'current_action':None,'current_phase':None}),run_id,worker_epoch))
            else:
                c.execute("UPDATE quant_factor_f0_runs SET status='failed',stop_reason=%s,updated_at=NOW() WHERE id=%s AND status='running' AND decision->>'runner_epoch'=%s",(str(exc)[:1000],run_id,worker_epoch))


def mark_interrupted():
    """No global UPDATE: only owned durable leases may be reconciled on restart."""
    from . import research_queue
    return research_queue.recover_owned() if research_queue.enabled() else {'legacy_not_modified':True}


def resume(uid, org, run_id):
    original = read(uid, org, run_id)
    topic_id = original["topic_id"]
    with get_conn() as lock:
        lock.execute("SELECT pg_advisory_xact_lock(%s,%s)",(9106,uid))
        lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                     (f"quant-factor-start:{uid}:{org}:{topic_id}",))
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE",
                (run_id, uid, org)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["status"] in ACTIVE:
                return _public(row)
            if row["status"] not in ("stopped", "failed"):
                raise WorkflowError("只有已中断或停止的运行可以继续")
            active = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
                (uid, org, topic_id)).fetchone()
            if active:
                return _public(active)
            topic = _topic(uid, org, topic_id)
            if topic["status"] != 'active' or service.control_status(uid, org)["paused"]:
                raise WorkflowError("研究已暂停，请先恢复任务与自动研究")
            recovery_only=not service.locked_view_available(topic)
            if recovery_only and (not service.locked_view_available(topic) or not service.has_recoverable_run(uid,org,topic['project_id'])):
                raise WorkflowError("固定数据版本目前无法确认或无原任务可恢复；不会用当前数据替换原计划")
            if not recovery_only:
                from services.factor.detect_store import get_project
                from .resources import require_config
                project=get_project(uid,topic['project_id'])['project'];config=project['config']
                expected_branch=next((item.get('result',{}).get('branch_id') for item in reversed((row.get('decision') or {}).get('steps') or []) if item.get('result',{}).get('branch_id')),row['branch_id'])
                if config.get('v5ActiveBranch') and config['v5ActiveBranch']!=expected_branch:raise WorkflowError('当前工程已由另一分支接手，请从已确认人工版本交回，不能恢复旧分支')
                require_config(config)
                from .research_contract import project_contract
                saved_method=(row.get('decision') or {}).get('method_version','legacy')
                contract=project_contract(project)
                if contract and saved_method!='bounded-factor-rd-v2':raise WorkflowError('原运行没有冻结的研究方法身份；请明确新建运行继续，原任务和K保留')
                if saved_method=='bounded-factor-rd-v2':
                    from .research_method import validate_snapshot
                    validate_snapshot((row.get('decision') or {}).get('method_snapshot'))
                if saved_method=='bounded-factor-rd-v2' and (not contract or contract['contract_hash']!=(row.get('decision') or {}).get('contract_hash')):raise WorkflowError('原运行的固定研究契约已不一致，未替换方法继续')
            from . import research_queue
            if not research_queue.enabled() and int(row.get('rounds') or 0) >= 12:
                raise WorkflowError("此运行已达到决策次数上限，原记录保留，请人工复盘")
            decision=dict(row.get('decision') or {})
            if decision.get('recovery_requires_new_run'):raise WorkflowError('原动作中途检查点需要确认；请明确新建运行继续，未自动重放旧动作')
            if decision.get('technical_wait'):
                decision['technical_wait_history']=[*(decision.get('technical_wait_history') or []),{**decision.pop('technical_wait'),'resumed_at':service.event('dependency_resumed')['at']}][-20:]
            decision['recovery_only']=recovery_only
            if not recovery_only:decision['control_epoch']=config.get('v5ControlEpoch')
            if research_queue.enabled():
                old=research_queue.by_object(c,'f0',run_id)
                if old and old['status']=='waiting':raise WorkflowError('原物理调用仍待确认，不能重复提交；保留原执行槽')
                if old and old['status'] in ('completed','cancelled'):
                    c.execute("UPDATE quant_research_queue_jobs SET status='queued',queued_at=NOW(),reason='',updated_at=NOW() WHERE id=%s",(old['id'],))
                elif not old:
                    decision['queue_deployment']=research_queue.DEPLOYMENT_ID
                    research_queue.enqueue(c,'f0',run_id,uid,org)
            c.execute("UPDATE quant_factor_f0_runs SET status='queued',stop_reason='',decision=%s::jsonb,updated_at=NOW() WHERE id=%s", (service.store.encode(decision),run_id))
        if research_queue.enabled():research_queue.wake()
        else:POOL.submit(run,uid,org,run_id)
        return read(uid, org, run_id)


def latest(uid, org, topic_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC LIMIT 1",
            (uid, org, topic_id)).fetchone()
    return _public(row) if row else None


def read(uid, org, run_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s",
            (run_id, uid, org)).fetchone()
    if not row:
        raise KeyError(run_id)
    return _public(row)


__all__ = ["latest", "mark_interrupted", "read", "resume", "run", "start"]
