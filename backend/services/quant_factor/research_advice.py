"""Explicit human research input, bound to a control epoch; never edits source."""
import uuid
from services.core.db import get_conn
from . import ledger,store
from .policy import WorkflowError


def submit(uid,org,topic_id,payload):
 topic=ledger._topic(uid,org,topic_id)
 message=str(payload.get('message') or '').strip();key=str(payload.get('request_key') or '')
 if not 2<=len(message)<=1000 or not 1<=len(key)<=100:raise WorkflowError('请填写2至1000字的研究建议并保留提交身份')
 with get_conn() as c:
  c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
  c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-factor-start:{uid}:{org}:{topic_id}',))
  project=c.execute('SELECT config FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,topic['project_id'])).fetchone()
  cfg=(project or {}).get('config') or {}
  if not cfg.get('researchPlan',{}).get('researchContract'):raise WorkflowError('此历史任务未启用版本化研究建议；可明确接手修订，不回写旧运行')
  run=c.execute('SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE',(uid,org,topic_id)).fetchone()
  if not run:raise WorkflowError('请先明确委托研究，再为该运行提交建议')
  if run['status'] not in ('queued','running'):raise WorkflowError('该运行已结束，不能再提交待处理建议；可明确接手新版本修订')
  decision=dict(run.get('decision') or {});advice=list(decision.get('human_advice') or [])
  existing=next((a for a in advice if a['request_key']==key),None)
  body={k:payload.get(k) for k in ('branch_id','control_epoch','candidate_id')};body['message']=message
  if existing:
   if existing['input']!=body:raise WorkflowError('此建议提交身份已用于另一正文，未覆盖旧建议')
   return existing
  if body['branch_id']!=cfg.get('v5ActiveBranch') or not body['control_epoch'] or body['control_epoch']!=cfg.get('v5ControlEpoch'):raise WorkflowError('当前控制版本已变化，请重新读取后为明确版本提交建议')
  if body['candidate_id']:
   candidate=c.execute('SELECT id,evidence FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s AND project_id=%s',(body['candidate_id'],uid,org,topic['project_id'])).fetchone()
   if not candidate or (candidate.get('evidence') or {}).get('branch_id')!=body['branch_id']:raise WorkflowError('建议目标不是此分支的冻结候选')
  current_topic=c.execute('SELECT status FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s',(topic_id,uid,org)).fetchone()
  if not current_topic or current_topic['status']!='active':raise WorkflowError('研究已暂停或结束，请明确接手后修订，不为旧运行增加待处理建议')
  if len(advice)>=20:raise WorkflowError('此运行的研究建议已达到20条，请等待处理或明确接手；未丢弃旧记录')
  item={'id':str(uuid.uuid4()),'request_key':key,'actor_user_id':uid,'input':body,'status':'pending','reason':''}
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
