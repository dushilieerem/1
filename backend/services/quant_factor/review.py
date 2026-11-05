"""Independent research feedback. Never grants publication or investment authority."""
from datetime import datetime,timezone
from services.core.db import get_conn
from . import store
from .service import event,current,public
from .policy import WorkflowError
from . import ledger
from .metrics import threshold

def request_review(uid,org,cid,note):
    if not note.strip():raise WorkflowError('请说明需要复核的研究问题')
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row:raise KeyError(cid)
        card=dict(row['archive'] or {})
        if not card or row['status'].endswith('_running') or not row['evidence'].get('development',{}).get('gate'):
            raise WorkflowError('请先完成研发检验并保存研究因子卡')
        if card.get('review'):return public(dict(row))
        card['review']={'status':'requested','question':note.strip(),'at':datetime.now(timezone.utc).isoformat(),'snapshot_hash':row['snapshot_hash'],'purpose':'research_feedback_only'}
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('review_requested')]),cid))
    return current(uid,org,cid)

def queue(uid,org):
    with get_conn() as c:
        rows=c.execute("SELECT id,snapshot_hash,status,snapshot->>'name' AS name,archive,updated_at FROM quant_factor_candidates WHERE org_id=%s AND user_id<>%s AND archive->'review'->>'status'='requested' ORDER BY updated_at DESC LIMIT 100",(org,uid)).fetchall()
    return [dict(r) for r in rows]

def ensure_reviewer(row,uid):
    if not row:raise KeyError('candidate')
    if int(row['user_id'])==uid:raise WorkflowError('不能复核自己的研究候选')
    if not (row['archive'] or {}).get('review'):raise KeyError('candidate')

def claim(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s FOR UPDATE',(cid,org)).fetchone()
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
    k=ledger.current_k(trials,topic['primary_holding_period'])
    return {'topic':ledger._public(topic),'trials':[ledger._public(row) for row in trials],
            'k':k,'threshold':threshold(k) if k>=1 else None}


def detail(uid,org,cid):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s',(cid,org)).fetchone()
    ensure_reviewer(row,uid)
    out=public(dict(row))
    # Independent review sees frozen evidence only, not the research dialogue/operator events.
    out.pop('events',None)
    ctx=_ledger_context(org,row['project_id'])
    if ctx:out.update(ctx)
    return out

def record(uid,org,cid,decision,note):
    if decision not in ('research_supported','needs_revision','rejected') or not note.strip():raise WorkflowError('请给出研究复核结论及依据')
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s FOR UPDATE',(cid,org)).fetchone()
        ensure_reviewer(row,uid)
        from .novelty_policy import handoff_allowed
        if decision=='research_supported':
            ctx=_ledger_context(org,row['project_id'])
            if ctx:
                checks=(row['evidence'].get('development') or {}).get('gate',{}).get('checks') or []
                nw=[x for x in checks if x.get('name')=='方向 NW t']
                if not nw:raise WorkflowError('候选缺少日度 Rank IC 的 NW t 证据，不能确认入库')
                if ctx['threshold'] is not None and float(nw[0]['actual'])<float(ctx['threshold']):
                    raise WorkflowError('按课题当前 K 校正后 NW t 未达标，只能退回补证或归档')
            if row['snapshot']['plan'].get('researchPurpose')=='discovery' and not handoff_allowed(row):raise WorkflowError('新因子候选尚未通过完整去重检验，可反馈补充研究，不能确认新成果依据充分。')
        card=dict(row['archive']);review=dict(card['review'])
        if review['status']!='requested':raise WorkflowError('此版本已复核，不能覆盖原结论；新研究版本须单独提交')
        ensure_assigned(review,uid)
        review.update(status='reviewed',decision=decision,note=note.strip(),reviewer_id=uid,reviewed_at=datetime.now(timezone.utc).isoformat())
        card['review']=review
        # Neither research feedback nor a passing gate can modify approved/sealed.
        assert card['approved'] is False and card['sealed'] is False
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(card),store.encode([event('review_recorded',reviewer_id=uid,decision=decision)]),cid))
    return detail(uid,org,cid)
