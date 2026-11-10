"""Explicit human research input, bound to a control epoch; never edits source."""
import uuid
from services.core.db import get_conn
from . import ledger,store
from .policy import WorkflowError


class AdviceRejected(WorkflowError):
 def __init__(self,code,message):
  super().__init__(message);self.code=code


def _original_receipt(c,uid,org,topic_id,key,body,expected_run_id):
 # Same actor/topic lock is held for lookup and insertion. Confirm receipt before
 # checking current run state: a completed run does not erase an accepted input.
 rows=c.execute("""SELECT r.id AS original_run_id,a.item AS item
   FROM quant_factor_f0_runs r CROSS JOIN LATERAL
   jsonb_array_elements(COALESCE(r.decision->'human_advice','[]'::jsonb)) AS a(item)
   WHERE r.user_id=%s AND r.org_id=%s AND r.topic_id=%s AND a.item->>'request_key'=%s
   ORDER BY r.created_at DESC LIMIT 2""",(uid,org,topic_id,key)).fetchall()
 if not rows:return None
 row=rows[0];item=row['item']
 if len(rows)!=1 or item.get('input')!=body or (expected_run_id is not None and expected_run_id!=row['original_run_id']):
  raise AdviceRejected('advice_key_conflict','这笔建议的提交记录与当前内容或目标不一致，未覆盖原记录；请先核对原建议。')
 return {**item,'run_id':row['original_run_id']}


def submit(uid,org,topic_id,payload):
 topic=ledger._topic(uid,org,topic_id)
 message=str(payload.get('message') or '').strip();key=str(payload.get('request_key') or '')
 if not 2<=len(message)<=1000 or not 1<=len(key)<=100:raise AdviceRejected('advice_invalid','请填写2至1000字的研究建议。')
 body={k:payload.get(k) for k in ('branch_id','control_epoch','candidate_id')};body['message']=message
 expected_run_id=payload.get('run_id')
 with get_conn() as c:
  c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
  c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-factor-start:{uid}:{org}:{topic_id}',))
  original=_original_receipt(c,uid,org,topic_id,key,body,expected_run_id)
  if original is not None:return original
  project=c.execute('SELECT config FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,topic['project_id'])).fetchone()
  cfg=(project or {}).get('config') or {}
  if not cfg.get('researchPlan',{}).get('researchContract'):raise AdviceRejected('advice_legacy','此历史任务未启用研究建议；可明确接手修订，原文字已保留。')
  run=c.execute('SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE',(uid,org,topic_id)).fetchone()
  if not run:raise AdviceRejected('advice_not_started','研究尚未开始，这笔建议未保存。原文字已保留。')
  if expected_run_id is not None and expected_run_id!=run['id']:raise AdviceRejected('advice_target_changed','研究已进入新的运行，这笔建议未保存；请确认当前研究版本后再提交。')
  if run['status'] not in ('queued','running'):raise AdviceRejected('advice_ended','本次研究已结束，这笔建议未保存。原文字已保留，可复制或接手修订。')
  if body['branch_id']!=cfg.get('v5ActiveBranch') or not body['control_epoch'] or body['control_epoch']!=cfg.get('v5ControlEpoch'):raise AdviceRejected('advice_target_changed','当前研究版本已变化，这笔建议未保存；请确认新的研究版本后再提交。')
  if body['candidate_id']:
   candidate=c.execute('SELECT id,evidence FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s AND project_id=%s',(body['candidate_id'],uid,org,topic['project_id'])).fetchone()
   if not candidate or (candidate.get('evidence') or {}).get('branch_id')!=body['branch_id']:raise AdviceRejected('advice_target_changed','当前查看的试验与建议目标不一致，这笔建议未保存；请重新确认研究版本。')
  current_topic=c.execute('SELECT status FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s',(topic_id,uid,org)).fetchone()
  if not current_topic or current_topic['status']!='active':raise AdviceRejected('advice_paused','研究已暂停或结束，这笔建议未保存。原文字已保留，可复制或接手修订。')
  decision=dict(run.get('decision') or {});advice=list(decision.get('human_advice') or [])
  if len(advice)>=20:raise AdviceRejected('advice_limit','本次研究的建议已达到20条，请等待处理或明确接手；原文字已保留。')
  item={'id':str(uuid.uuid4()),'request_key':key,'run_id':run['id'],'actor_user_id':uid,'input':body,'status':'pending','reason':''}
  advice.append(item);decision['human_advice']=advice
  c.execute('UPDATE quant_factor_f0_runs SET decision=%s::jsonb,updated_at=NOW() WHERE id=%s',(store.encode(decision),run['id']))
  return item


def decisions_after_result(advice,proposal,result):
 """Adoption is recorded only after the selected action actually completes."""
 choices={item['advice_id']:item for item in proposal.get('advice_decisions') or []}
 out=[]
 for item in advice:
  choice=choices.get(item['id']);saved=dict(item)
  if item['status']=='pending' and choice and (choice['status']=='not_adopted' or result.get('status')=='completed'):
   saved.update(status=choice['status'],reason=choice['reason'])
  out.append(saved)
 return out


def close_pending(connection,uid,org,*,topic_id=None,run_id=None,worker_epoch=None,reason):
 clause='topic_id=%s' if topic_id is not None else 'id=%s';identity=topic_id if topic_id is not None else run_id
 ownership=" AND status='running' AND decision->>'runner_epoch'=%s" if worker_epoch is not None else ''
 params=(uid,org,identity,worker_epoch) if worker_epoch is not None else (uid,org,identity)
 rows=connection.execute('SELECT id,decision FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND '+clause+ownership+' FOR UPDATE',params).fetchall()
 for row in rows:
  items=(row.get('decision') or {}).get('human_advice') or []
  if not any(a['status']=='pending' for a in items):continue
  updated=[{**a,'status':'not_adopted','reason':reason} if a['status']=='pending' else a for a in items]
  connection.execute("UPDATE quant_factor_f0_runs SET decision=jsonb_set(decision,'{human_advice}',%s::jsonb),updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s",(store.encode(updated),row['id'],uid,org))
