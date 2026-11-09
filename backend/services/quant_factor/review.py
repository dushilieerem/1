"""Independent research feedback. Never grants publication or investment authority."""
from datetime import datetime,timezone
from services.core.db import get_conn
from services.core.tenant import Tenant
from . import repo
from . import store
from .service import event,current,public
from .policy import WorkflowError,digest
from . import ledger
from .metrics import threshold

def _require_novelty(row):
    novelty = (row.get('evidence') or {}).get('development', {}).get('novelty') or {}
    gate = novelty.get('gate') or {}
    replication=(row.get('snapshot') or {}).get('plan',{}).get('researchPurpose')=='replication'
    if gate.get('complete') is not True or (not replication and gate.get('passed') is not True):
        raise WorkflowError('候选缺少完整查重证据（R4/novelty），不能提交审查或批准入库')


def feedback_materials(row):
    """A real frozen finished/failed attempt may be reviewed, never supported/admitted."""
    snap=row.get('snapshot')
    if not isinstance(snap,dict) or not row.get('snapshot_hash') or digest(snap)!=row['snapshot_hash']:
        raise WorkflowError('冻结候选内容与版本指纹不一致，不能提交复盘')
    evidence=row.get('evidence') or {};dev=evidence.get('development') or {}
    if row['status'].endswith('_running'):raise WorkflowError('检验仍在执行，请先等待明确结果或停止状态')
    numerical=isinstance(dev.get('result'),dict) and bool(dev['result'])
    known_failure=dev.get('external_status') in ('failed','cancelled') and bool(dev.get('run_id'))
    implementation_failure=dev.get('preflight_failure')=='implementation' and evidence.get('source_contract',{}).get('passed') is False
    if not (numerical or known_failure or implementation_failure):
        raise WorkflowError('尚无已完成研发或明确失败的固定记录；结果待确认不能冒充已完成复盘')
    missing=[]
    if not numerical:missing.append('尚无研发数值报告；本次仅复盘已确认的执行失败')
    elif (dev.get('gate') or {}).get('numerical_passed') is not True and not (dev.get('gate') or {}).get('passed'):missing.append('研发数值门槛未全部通过')
    novelty=dev.get('novelty') or {}
    if (novelty.get('gate') or {}).get('complete') is not True:missing.append('正式查重尚未完整完成，不代表新颖性合格')
    return {'candidate_status':row['status'],'development_report_id':dev.get('report_id'),'has_numerical_result':numerical,'known_execution_failure':bool(known_failure or implementation_failure),'missing':missing,'allowed_decisions':['needs_revision','rejected'],'grants_admission':False}


from contextlib import contextmanager

@contextmanager
def _review_scope(uid,org,cid,controller):
    if controller:
        from . import sealed
        with sealed._locked(uid,org,cid) as (c,cand,topic,project,seal):
            sealed._require_controller(c,uid,org,topic,controller)
            yield c
    else:
        with get_conn() as c:yield c

def request_review(uid,org,cid,note,purpose="research_admission",controller=None):
    if not note.strip():raise WorkflowError('请说明需要复核的研究问题')
    with _review_scope(uid,org,cid,controller) as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        card=dict(row['archive'] or {'approved': False, 'sealed': False})
        if card.get('research_asset'):raise WorkflowError('此固定版本已登记，不能重开审批；改进请建立新候选')
        if row['status'].endswith('_running'):raise WorkflowError('请先等待当前检验结束')
        if purpose not in ('research_admission','research_feedback_only'):raise WorkflowError('复核事项类型无效')
        existing=card.get('review') or {}
        if existing.get('status')=='requested':
            if existing.get('purpose')==purpose:return public(dict(row))
            raise WorkflowError('既有复核事项尚未结束，不能将反馈直接升级为资产审批')
        if purpose=='research_admission':
            from .assets import eligibility
            eligibility(dict(row),c,for_submission=True)
        else:materials=feedback_materials(dict(row))
        if existing:card['review_history']=[*(card.get('review_history') or []),existing]
        card['review']={'status':'requested','question':note.strip(),'at':datetime.now(timezone.utc).isoformat(),'snapshot_hash':row['snapshot_hash'],'purpose':purpose,**({'materials':materials} if purpose=='research_feedback_only' else {})}
        if not card.get('note'):card['note']='已提交独立研究复盘，结论待复核人记录'
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('review_requested')]),cid))
    return current(uid,org,cid)

def pending_count(org, uid=None, reviewer=False):
    """Reviewer sees items waiting for them; a researcher sees their own submissions."""
    with get_conn() as c:
        if uid is None:
            return c.execute(
                "SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE org_id=%s AND archive->'review'->>'status'='requested'",
                (org,)).fetchone()["n"]
        if reviewer:
            return c.execute(
                "SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE org_id=%s AND user_id<>%s AND archive->'review'->>'status'='requested'",
                (org, uid)).fetchone()["n"]
        return c.execute(
            "SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE org_id=%s AND user_id=%s AND archive->'review'->>'status'='requested'",
            (org, uid)).fetchone()["n"]


def queue(uid,org):
    return repo.review_queue(Tenant.from_pair(uid,org),uid)

def ensure_reviewer(row,uid):
    if not row:raise KeyError('candidate')
    if int(row['user_id'])==uid:raise WorkflowError('不能复核自己的研究候选')
    if not (row['archive'] or {}).get('review'):raise KeyError('candidate')

def claim(uid,org,cid):
    tenant=Tenant.from_pair(uid,org)
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s FOR UPDATE',(cid,tenant.org_id)).fetchone()
        ensure_reviewer(row,uid)
        card=dict(row['archive']);review=dict(card['review'])
        if review.get('status')!='requested':raise WorkflowError('此版本已复核，不能重复领取')
        assigned=review.get('assigned_to')
        if assigned is not None and int(assigned)!=uid:raise WorkflowError('该事项已指派给其他复核人')
        review.update(assigned_to=uid,assigned_at=datetime.now(timezone.utc).isoformat())
        card['review']=review
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('review_claimed',reviewer_id=uid)]),cid))
    return detail(uid,org,cid)

def ensure_assigned(review,uid):
    if not isinstance(review,dict) or review.get('assigned_to') is None:
        raise WorkflowError('请先领取该复核事项再作决定')
    if int(review['assigned_to'])!=uid:
        raise WorkflowError('该事项已指派给其他复核人')

def _ledger_context(org,project_id):
    with get_conn() as c:
        topic=c.execute("SELECT * FROM quant_factor_topics WHERE org_id=%s AND project_id=%s",(org,project_id)).fetchone()
        if not topic:return None
        trials=[dict(row) for row in c.execute(
            "SELECT * FROM quant_factor_trials WHERE org_id=%s AND topic_id=%s ORDER BY trial_no",
            (org,topic['id'])).fetchall()]
        branches=[dict(row) for row in c.execute(
            "SELECT * FROM quant_factor_branches WHERE org_id=%s AND topic_id=%s ORDER BY created_at",
            (org,topic['id'])).fetchall()]
    labels=ledger._branch_labels(topic['user_id'],org,topic['id'],branches)
    for trial in trials:
        trial['branch_label']=labels.get(trial.get('branch_id'),'H?')
        trial['counts_toward_k']=ledger.counts_toward_k(trial,topic['primary_holding_period'])
    k=ledger.current_k(trials,topic['primary_holding_period'])
    return {'topic':ledger._public(topic),'trials':[ledger._public(row) for row in trials],
            'k':k,'threshold':threshold(max(k,1)),'threshold_k':max(k,1)}


def open_seal_failed_review(uid,org,cid,reason,controller=None):
    with _review_scope(uid,org,cid,controller) as c:
        row=c.execute("SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE",(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        card=dict(row['archive'] or {'approved': False, 'sealed': False})
        if card.get('research_asset'):raise WorkflowError('此固定版本已登记，不能重开复盘')
        if card.get('review'):card['review_history']=[*(card.get('review_history') or []),card['review']]
        card['review']={'status':'requested','purpose':'seal_failed_review','question':'封存未通过复盘：'+str(reason)[:1000],'at':datetime.now(timezone.utc).isoformat(),'snapshot_hash':row['snapshot_hash']}
        c.execute("UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s",(store.encode(card),store.encode([event('seal_failed_review_requested')]),cid))
    # The researcher opens this item; returning reviewer-only detail here would fail
    # with a misleading self-review error and hide the sealed failure.
    return current(uid,org,cid)


def detail(uid,org,cid):
    row=repo.candidate_for_org(Tenant.from_pair(uid,org),cid)
    ensure_reviewer(row,uid)
    out=public(dict(row))
    # Independent review sees frozen evidence only, not the research dialogue/operator events.
    out.pop('events',None)
    rev=(row.get('archive') or {}).get('review') or {}
    assigned=rev.get('assigned_to')
    out['review_actions']={'can_claim':rev.get('status')=='requested' and assigned is None,
                           'can_decide':rev.get('status')=='requested' and assigned is not None and int(assigned)==uid}
    ctx=_ledger_context(org,row['project_id'])
    if ctx:out.update(ctx)
    with get_conn() as c:
        sealed=c.execute(
            "SELECT status,result,report_id,created_at FROM quant_factor_sealed_validations WHERE candidate_id=%s AND org_id=%s ORDER BY created_at DESC LIMIT 1",
            (cid,org)).fetchone()
    out['sealed']=dict(sealed) if sealed else None
    if rev.get('purpose')=='research_admission' and rev.get('status')=='requested':
        from .assets import eligibility
        try:eligibility(dict(row));out['admission']={'allowed':True,'reason':''}
        except (WorkflowError,ValueError,KeyError) as exc:out['admission']={'allowed':False,'reason':str(exc)}
    else:out['admission']={'allowed':False,'reason':'此事项仅作研究反馈或复盘，不能直接批准入库'}
    if rev.get('purpose')=='research_feedback_only':
        try:out['feedback_materials']=feedback_materials(dict(row))
        except WorkflowError as exc:out['feedback_materials']={'missing':[str(exc)],'allowed_decisions':['needs_revision','rejected'],'grants_admission':False}
    return out

def record(uid,org,cid,decision,note):
    if decision not in ('research_supported','needs_revision','rejected') or not note.strip():raise WorkflowError('请给出研究复核结论及依据')
    tenant=Tenant.from_pair(uid,org)
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s FOR UPDATE',(cid,tenant.org_id)).fetchone()
        ensure_reviewer(row,uid)
        from .novelty_policy import handoff_allowed
        purpose=((row.get('archive') or {}).get('review') or {}).get('purpose')
        if decision=='research_supported' and purpose in ('research_feedback_only','seal_failed_review','research_admission'):
            raise WorkflowError('此事项只能退回补充或驳回；研究资产必须通过独立批准并登记，不能改作支持结论')
        if purpose=='research_feedback_only':feedback_materials(dict(row))
        if decision=='research_supported':
            _require_novelty(row)
            ctx=_ledger_context(org,row['project_id'])
            if ctx:
                checks=(row['evidence'].get('development') or {}).get('gate',{}).get('checks') or []
                nw=[x for x in checks if x.get('name')=='方向 NW t']
                if not nw:raise WorkflowError('候选缺少日度 Rank IC 的 NW t 证据，不能确认入库')
                if ctx['threshold'] is not None and float(nw[0]['actual'])<float(ctx['threshold']):
                    raise WorkflowError('按课题当前 K 校正后 NW t 未达标，只能退回补证或归档')
            if row['snapshot']['plan'].get('researchPurpose')=='discovery' and not handoff_allowed(row):raise WorkflowError('新因子候选尚未通过完整去重检验，可反馈补充研究，不能确认新成果依据充分。')
        card=dict(row['archive']);review=dict(card['review'])
        if review.get('purpose')=='seal_failed_review' and decision=='research_supported':
            raise WorkflowError('封存未通过的复盘不能入库；只能驳回或退回课题新建计划')
        if review['status']!='requested':raise WorkflowError('此版本已复核，不能覆盖原结论；新研究版本须单独提交')
        ensure_assigned(review,uid)
        review.update(status='reviewed',decision=decision,note=note.strip(),reviewer_id=uid,reviewed_at=datetime.now(timezone.utc).isoformat())
        card['review']=review
        # Neither research feedback nor a passing gate can modify approved/sealed.
        if card.get('approved') or card.get('sealed'):
            raise WorkflowError('已批准或已封存的版本不能改写复核结论')
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('review_recorded',reviewer_id=uid,decision=decision)]),cid))
    return detail(uid,org,cid)


def visible_queue(uid,org,can_review):
    if can_review:return queue(uid,org)
    with get_conn() as c:
        rows=c.execute("SELECT id,user_id,org_id,snapshot_hash,status,snapshot->>'name' AS name,archive,updated_at FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND archive->'review' IS NOT NULL ORDER BY updated_at DESC LIMIT 100",(uid,org)).fetchall()
    return [public(dict(row)) for row in rows]


def visible_detail(uid,org,cid,can_review):
    row=repo.candidate_for_org(Tenant.from_pair(uid,org),cid)
    if not row:raise KeyError(cid)
    if int(row['user_id'])!=uid:
        if not can_review:raise KeyError(cid)
        return detail(uid,org,cid)
    if not (row.get('archive') or {}).get('review'):raise KeyError(cid)
    out=public(dict(row));out.pop('events',None)
    ctx=_ledger_context(org,row['project_id'])
    if ctx:out.update(ctx)
    with get_conn() as c:
        sealed=c.execute('SELECT status,report_id,created_at FROM quant_factor_sealed_validations WHERE org_id=%s AND candidate_id=%s',(org,cid)).fetchone()
    out['sealed']=dict(sealed) if sealed else None
    out['review_actions']={'can_claim':False,'can_decide':False}
    out['admission']={'allowed':False,'reason':'作者只能查看材料，不能批准自己的研究成果'}
    out['is_author']=True
    return out
