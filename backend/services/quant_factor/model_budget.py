"""Quant-only persistent call reservation. Unknown history/usage never becomes zero."""
from __future__ import annotations
import json,uuid,math
from dataclasses import replace
from services.core.db import get_conn
from .policy import WorkflowError,digest
from . import store

LIMITS={'space':1_000_000,'factor':200_000}
OUTPUT_LIMITS={'quant.factor.research_planner_v2':16000,'quant.factor.research_implementation_v2':16000,'quant.factor.evidence_diagnosis_v2':16000,'quant.factor.f0_decider':2000,'quant.factor.task_planner':3000,'quant.factor.research_assistant':3000,'research.generate_factor':8000,'quant.factor.independent_reviewer':2000}
VERSION='quant-model-budget-v1'
MAX_PROMPT_BYTES=48_000
AUTHORIZED_ORG=261

def input_upper_bound(messages,response_format=None):
 if not isinstance(messages,list) or not messages or any(not isinstance(m,dict) for m in messages):raise WorkflowError('模型输入不完整，未发起调用')
 encoded=json.dumps({'messages':messages,'response_format':response_format},ensure_ascii=False,separators=(',',':')).encode('utf-8')
 if len(encoded)>MAX_PROMPT_BYTES:raise WorkflowError('研究材料超出本次模型输入范围，请精简资料，未发起调用')
 # One token per UTF-8 byte plus explicit message/schema framing margin.
 return len(encoded)+1024+64*len(messages)

def measured_usage(response):
 usage=response.get('usage')
 if not isinstance(usage,dict):return None
 def count(key):
  value=usage.get(key)
  return value if isinstance(value,int) and not isinstance(value,bool) and value>=0 else None
 incoming,outgoing=count('prompt_tokens'),count('completion_tokens')
 if incoming is None or outgoing is None:return None
 total=count('total_tokens');total=max(incoming+outgoing,total if total is not None else 0)
 if total==0 and response.get('content'):return None
 return {'tokens_in':incoming,'tokens_out':outgoing,'total_tokens':total,'provider_usage':{k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens') and isinstance(v,int) and not isinstance(v,bool) and v>=0}}

def _lock(c,org):c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-ai-budget:{org}',))

def _charge_sum(c,org,supplement=None):
 query="SELECT COALESCE(SUM(CASE WHEN status='settled' THEN actual_tokens ELSE reserved_tokens END),0) AS n FROM quant_ai_budget_calls WHERE org_id=%s AND funding=%s"
 params=(org,'supplement' if supplement else 'base')
 if supplement:query+=' AND supplement_id=%s';params=(*params,supplement)
 return int(c.execute(query,params).fetchone()['n'])

def reserve(uid,org,project_id,call_key,task_id,request_hash,prompt_upper,max_output,supplement=None):
 if task_id not in OUTPUT_LIMITS or max_output!=OUTPUT_LIMITS[task_id]:raise WorkflowError('模型输出额度未明确，未发起调用')
 if not isinstance(call_key,str) or not 1<=len(call_key)<=200:raise WorkflowError('模型调用身份无效')
 if not isinstance(prompt_upper,int) or prompt_upper<=0:raise WorkflowError('模型输入额度无效')
 reserved=prompt_upper+max_output
 with get_conn() as c:
  _lock(c,org)
  prior=c.execute('SELECT * FROM quant_ai_budget_calls WHERE org_id=%s AND call_key=%s FOR UPDATE',(org,call_key)).fetchone()
  if prior:
   if prior['user_id']!=uid or prior['project_id']!=project_id or prior['request_hash']!=request_hash or (supplement is not None and prior['supplement_id']!=supplement):raise WorkflowError('此模型调用身份已用于另一输入或额度，未覆盖原记录')
   return dict(prior)
  quota=c.execute('SELECT ai_quota_daily FROM users WHERE id=%s',(uid,)).fetchone()
  used=c.execute("SELECT COUNT(*) AS n FROM ai_usage WHERE user_id=%s AND created_at>=date_trunc('day',NOW())",(uid,)).fetchone()['n']
  if not quota or used>=int(quota['ai_quota_daily'] or 0):raise WorkflowError('今日账号模型调用次数已达上限，未预留新请求')
  grant=c.execute("SELECT * FROM quant_ai_budget_supplements WHERE org_id=%s AND module='factor' AND status='authorized' "+("AND id=%s " if supplement else '')+"ORDER BY created_at DESC LIMIT 1 FOR UPDATE",(org,supplement) if supplement else (org,)).fetchone()
  if grant:supplement=grant['id']
  from . import token_policy
  authorization=token_policy.current(c,org)
  if authorization and (not grant or authorization['supersedes_grant_id']!=grant['id']):raise WorkflowError('持续研究授权与原额度身份不一致，未覆盖原记录')
  if supplement:
   if not grant:raise WorkflowError('这项研究没有已确认的补充额度，未发模型请求')
   if not authorization and _charge_sum(c,org,supplement)+reserved>grant['limit_tokens']:raise WorkflowError('本产品研究模型授权额度不足，已用与待核预留保留，未发新请求')
  else:
   accounts=[dict(r) for r in c.execute('SELECT * FROM quant_ai_budget_accounts WHERE org_id=%s FOR UPDATE',(org,)).fetchall()]
   by_scope={row['scope']:row for row in accounts}
   if any(scope not in by_scope or by_scope[scope]['baseline_state']!='confirmed' or by_scope[scope]['historical_tokens'] is None for scope in LIMITS):raise WorkflowError('机构研究的历史模型用量尚待核对，累计余额未确认；未发起模型调用')
   charged=_charge_sum(c,org)
   for scope,ceiling in LIMITS.items():
    account=by_scope[scope]
    if account['limit_tokens']!=ceiling:raise WorkflowError('研究模型额度与已确认契约不一致，未发起调用')
    if int(account['historical_tokens'])+charged+reserved>ceiling:raise WorkflowError(('机构空间' if scope=='space' else '因子研究')+'累计模型额度不足；已有用量和待核预留保留，未发起新请求')
  call_id=str(uuid.uuid4())
  c.execute("INSERT INTO quant_ai_budget_calls(id,org_id,user_id,module,project_id,call_key,task_id,request_hash,funding,supplement_id,reserved_tokens,prompt_upper_tokens,max_output_tokens,status) VALUES(%s,%s,%s,'factor',%s,%s,%s,%s,%s,%s,%s,%s,%s,'reserved')",(call_id,org,uid,project_id,call_key,task_id,request_hash,'supplement' if supplement else 'base',supplement,reserved,prompt_upper,max_output))
  if authorization:c.execute('UPDATE quant_ai_budget_calls SET token_policy_id=%s WHERE id=%s',(authorization['id'],call_id))
  from . import research_queue
  if research_queue.enabled() and (not research_queue.permits_lightweight(task_id) or research_queue.current_id()):
   research_queue.require_context()
   c.execute('UPDATE quant_ai_budget_calls SET queue_job_id=%s WHERE id=%s',(research_queue.current_id(),call_id))
  return dict(c.execute('SELECT * FROM quant_ai_budget_calls WHERE id=%s',(call_id,)).fetchone())

def claim(uid,org,call_id):
 with get_conn() as c:
  c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-ai-account-quota:{uid}',))
  _lock(c,org)
  quota=c.execute('SELECT ai_quota_daily FROM users WHERE id=%s',(uid,)).fetchone()
  used=c.execute("SELECT COUNT(*) AS n FROM ai_usage WHERE user_id=%s AND created_at>=date_trunc('day',NOW())",(uid,)).fetchone()['n']
  if not quota or used>=int(quota['ai_quota_daily'] or 0):raise WorkflowError('今日账号模型调用次数已达上限，未发起新请求')
  row=c.execute("UPDATE quant_ai_budget_calls SET status='dispatched',updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status='reserved' RETURNING task_id",(call_id,uid,org)).fetchone()
  if not row:return False
  # Count each claimed provider attempt in the existing account daily-call gate.
  # The ledger retains that these initial zero tokens are unconfirmed, not free.
  c.execute('INSERT INTO ai_usage(user_id,run_id,skill,tokens_in,tokens_out) VALUES(%s,%s,%s,0,0)',(uid,call_id,row['task_id']))
  return True

def unresolved(uid,org,call_id,note):
 with get_conn() as c:
  _lock(c,org)
  c.execute("UPDATE quant_ai_budget_calls SET status='unresolved',note=%s,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status='dispatched'",(str(note)[:300],call_id,uid,org))

def safe_response(response):
 keys=('content','data','model','provider','tokens_in','tokens_out','usage','finish_reason','prompt_version','latency_ms','error_type','budget_call_id','task','reasoning_tokens','reasoning_chars','http_status','provider_request_terminal')
 return {key:response[key] for key in keys if key in response}

def settle(uid,org,call_id,response):
 usage=measured_usage(response)
 safe=safe_response(response)
 if len(store.encode(safe).encode())>100_000:raise WorkflowError('模型回执超过保存范围，预留保留待核对')
 with get_conn() as c:
  _lock(c,org)
  prior=c.execute('SELECT * FROM quant_ai_budget_calls WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(call_id,uid,org)).fetchone()
  if not prior:raise WorkflowError('原模型用量记录不存在或无权核对')
  if prior['status']=='settled':
   if not usage or int(prior['actual_tokens'])!=usage['total_tokens'] or prior.get('response')!=safe:raise WorkflowError('已结算的模型回执不可替换，原用量保留')
   return usage
  if prior['status'] not in ('dispatched','unresolved'):raise WorkflowError('此模型调用尚未发送，不能写入实耗')
  c.execute("UPDATE quant_ai_budget_calls SET status=%s,actual_tokens=%s,provider_usage=%s::jsonb,response=%s::jsonb,note=%s,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('dispatched','unresolved')",('settled' if usage else 'unresolved',usage['total_tokens'] if usage else None,store.encode(usage['provider_usage']) if usage else None,store.encode(safe),'' if usage else 'Provider usage missing/incomplete; full reservation retained',call_id,uid,org))
  if usage:c.execute('UPDATE ai_usage SET tokens_in=%s,tokens_out=%s WHERE user_id=%s AND run_id=%s',(usage['tokens_in'],usage['tokens_out'],uid,call_id))
 return usage

def run(uid,org,project_id,call_key,task_id,*,messages=None,variables=None,supplement=None,method_snapshot=None):
 """Exactly one physical primary-model attempt; no SDK fallback/expansion/cache."""
 from . import research_queue
 if not research_queue.permits_lightweight(task_id) or research_queue.current_id():research_queue.require_context()
 from ai.router import get_task
 from ai.router.specs import TaskRequest
 from ai.gateway import providers
 if task_id not in OUTPUT_LIMITS:raise WorkflowError('此研究模型任务尚未纳入预算契约')
 spec=get_task(task_id)
 if spec.executors!=('local',):raise WorkflowError('此任务的模型执行路径尚未纳入单次预算契约，未发起调用')
 request=TaskRequest(messages=list(messages or []),variables=dict(variables or {}));resolved=request.messages or list(spec.prompt(request) if spec.prompt else [])
 # Reuse model selection, prompt/validator and one-shot HTTP transport; avoid
 # complete()'s automatic retry, output expansion and model fallback loops.
 target=providers.resolve_target(slot=spec.slot)
 from ai.router.executors import _code_response_format
 response_format=_code_response_format(spec)
 if isinstance(response_format,dict) and response_format.get('type')=='json_schema':response_format={'type':'json_object'}
 upper=input_upper_bound(resolved,response_format);maximum=OUTPUT_LIMITS[task_id];timeout=int(spec.timeout_sec or target.timeout);method_hash=None
 if task_id.endswith('_v2'):
  from .research_method import validate_snapshot
  frozen=validate_snapshot(method_snapshot);role=frozen['roles'].get(task_id)
  if not role or spec.prompt_version!=role['prompt_version']:raise WorkflowError('模型任务与本次冻结方法不一致，未发送请求')
  maximum=role['max_output'];timeout=role['timeout_seconds'];method_hash=frozen['snapshot_hash']
 identity={'budget_version':VERSION,'temperature':float(spec.temperature),'task_id':task_id,'messages':resolved,'variables':variables or {},'max_output':maximum,'prompt_version':spec.prompt_version,'response_format':response_format,'model':target.model,'provider':target.provider,'backend_hash':digest({'base':target.base_url})}
 if method_hash:identity.update(method_snapshot_hash=method_hash,timeout_seconds=timeout)
 fingerprint=digest(identity)
 row=reserve(uid,org,project_id,call_key,task_id,fingerprint,upper,maximum,supplement)
 if row.get('response') is not None:
  if row['response'].get('error_type'):raise WorkflowError('原模型调用未返回可用产物（'+row['response']['error_type']+'），用量已保留；不会自动重发')
  return row['response']
 if row['status']!='reserved':raise WorkflowError('原模型提交结果尚待核对，保留调用身份和预留，不会重复提交')
 if not claim(uid,org,row['id']):raise WorkflowError('原模型请求已领取，请继续查看原任务，未重复提交')
 payload={'model':target.model,'messages':resolved,'temperature':spec.temperature,'max_tokens':maximum}
 if response_format is not None:payload['response_format']=response_format
 try:
  try:raw=providers._read_json(providers._post(target,payload,timeout=timeout,stream=False))
  except providers._HttpFailure as failure:
   if failure.status in (400,401,403,404,405,413,422,429):settle(uid,org,row['id'],{'error_type':'ProviderRequestRejected','http_status':failure.status,'provider_request_terminal':True,'model':target.model,'provider':target.provider,'budget_call_id':row['id']})
   raise providers._failure_to_error(failure,target) from failure
  try:
   output=providers._normalize(raw,target,max_tokens=maximum)
   output.update(task=task_id,prompt_version=spec.prompt_version,budget_call_id=row['id'])
   if spec.validator is not None:output['data']=spec.validator(str(output.get('content') or ''),request)
  except Exception as exc:
   settle(uid,org,row['id'],{'usage':raw.get('usage'),'error_type':type(exc).__name__,'finish_reason':((raw.get('choices') or [{}])[0] or {}).get('finish_reason'),'model':raw.get('model') or target.model,'provider':target.provider,'budget_call_id':row['id']})
   raise
  output=safe_response(output)
  settle(uid,org,row['id'],output)
  return output
 except Exception as exc:
  unresolved(uid,org,row['id'],'模型提交或回执未确认，预留保留；不自动退款或重发')
  if isinstance(exc,WorkflowError):raise
  raise WorkflowError('研究模型调用未完成（'+type(exc).__name__+'），原用量与预留保留；不会自动扩大输出、换模型或重发') from exc


def install_authorization(org,actor,record_path):
 """Explicit CLI-only activation; one institution/product pool, not per actor/task."""
 from pathlib import Path
 record=json.loads(Path(record_path).read_text());ceiling=record.get('new_authorized_tokens')
 if org!=AUTHORIZED_ORG or ceiling!=100_000_000 or record.get('previous_history_complete') is not False or not record.get('does_not_reset_history') or not record.get('does_not_change_shared_site_or_account_limits'):raise WorkflowError('授权记录与本项目预算决定不一致，未创建额度')
 fingerprint=digest(record);grant_id='qbg_'+fingerprint[:24];scope='institutional_quant.factor_research.20261109'
 with get_conn() as c:
  _lock(c,org)
  prior=c.execute('SELECT * FROM quant_ai_budget_supplements WHERE org_id=%s AND research_scope=%s FOR UPDATE',(org,scope)).fetchone()
  if prior:
   if prior['authorization_hash']!=fingerprint or prior['limit_tokens']!=ceiling:raise WorkflowError('此研究授权已有不同版本，未覆盖原额度或消费')
   return dict(prior)
  c.execute("INSERT INTO quant_ai_budget_supplements(id,org_id,authorized_by,module,research_scope,limit_tokens,purpose,authorization_reference,authorization_hash,status) VALUES(%s,%s,%s,'factor',%s,%s,%s,%s,%s,'authorized')",(grant_id,org,actor,scope,ceiling,'本机构量化产品后续Agent因子研究；不扩大计算范围或账号额度',str(record_path),fingerprint))
  return dict(c.execute('SELECT * FROM quant_ai_budget_supplements WHERE id=%s',(grant_id,)).fetchone())


def status(uid,org,project_id=None):
 with get_conn() as c:
  accounts=c.execute('SELECT scope,limit_tokens,baseline_state,historical_tokens,unknown_history FROM quant_ai_budget_accounts WHERE org_id=%s',(org,)).fetchall()
  grant=c.execute("SELECT * FROM quant_ai_budget_supplements WHERE org_id=%s AND module='factor' AND status='authorized' ORDER BY created_at DESC LIMIT 1",(org,)).fetchone()
  from . import token_policy
  authorization=token_policy.current(c,org)
  out={'token_limit_mode':'unlimited' if authorization else 'limited','cumulative_token_limit':None if authorization else (grant['limit_tokens'] if grant else None),'active_policy':{'id':authorization['id'],'mode':authorization['mode'],'supersedes_grant_id':authorization['supersedes_grant_id'],'authorization_hash':authorization['authorization_hash']} if authorization else None,'legacy_baseline':'pending' if not accounts or any(r['baseline_state']!='confirmed' for r in accounts) else 'confirmed','legacy_accounts':[dict(r) for r in accounts],'new_authorization':None}
  if grant:
   totals=c.execute("SELECT COALESCE(SUM(actual_tokens) FILTER(WHERE status='settled'),0) AS settled,COALESCE(SUM(reserved_tokens) FILTER(WHERE status<>'settled'),0) AS held FROM quant_ai_budget_calls WHERE org_id=%s AND supplement_id=%s",(org,grant['id'])).fetchone()
   out['new_authorization']={'id':grant['id'],'limit_tokens':grant['limit_tokens'],'settled_tokens':int(totals['settled']),'held_tokens':int(totals['held']),'remaining_tokens':max(0,grant['limit_tokens']-int(totals['settled'])-int(totals['held'])),'scope':'本机构量化产品因子Agent研究；全机构单池累计，不按成员或任务重置'}
  out['execution_ready']=bool(authorization and grant and authorization['supersedes_grant_id']==grant['id']) if authorization else None
  out['policy_state']='active' if out['execution_ready'] else ('needs_confirmation' if authorization else 'legacy')
  out['policy_message']='持续研究授权与原授权记录待核对；实际用量保留，暂不发送新的模型请求' if authorization and not out['execution_ready'] else ''
  if authorization:
   # The old grant remains a historical fact, never an effective balance.
   if out['new_authorization'] is not None:
    out['new_authorization']['superseded_by_policy_id']=authorization['id']
    out['new_authorization']['remaining_tokens']=None
   totals=c.execute("SELECT COALESCE(SUM(actual_tokens) FILTER(WHERE status='settled'),0) AS settled,COALESCE(SUM(reserved_tokens) FILTER(WHERE status<>'settled'),0) AS held,COUNT(*) FILTER(WHERE status='unresolved') AS unresolved FROM quant_ai_budget_calls WHERE org_id=%s AND module='factor'",(org,)).fetchone()
   out['usage']={'settled_tokens':int(totals['settled']),'held_tokens':int(totals['held']),'unresolved_calls':int(totals['unresolved']),'includes_historical_unknown':False}
  return out


def record_legacy_audit(org,actor,audit_path):
 from pathlib import Path
 audit=json.loads(Path(audit_path).read_text())
 if not any(r['org_id']==org for r in audit['quant_agent_usage_by_stage']):raise WorkflowError('此审计不含当前机构，未写入零历史基线')
 exact=sum(int(r['measured_tokens']) for r in audit['quant_agent_usage_by_stage'] if r['org_id']==org and r['stage']=='F1')+sum(int(r['recorded_tokens']) for r in audit['f0_step_usage'] if r['org_id']==org)+sum(int(r['measured_tokens']) for r in audit['assistant_output_references'] if r['org_id']==org)
 unknown={'complete':False,'f3_zero_usage_rows':sum(int(r['zero_token_rows']) for r in audit['quant_agent_usage_by_stage'] if r['org_id']==org and r['stage']=='F3'),'other_gaps':'Unbound historical F0/assistant and failed/repaired calls; see source audit','audit_sha256':digest(audit),'recorded_by':actor}
 with get_conn() as c:
  _lock(c,org)
  for scope,ceiling in LIMITS.items():
   c.execute("INSERT INTO quant_ai_budget_accounts(org_id,scope,limit_tokens,baseline_state,historical_tokens,unknown_history,baseline_reference) VALUES(%s,%s,%s,'pending',%s,%s::jsonb,%s) ON CONFLICT(org_id,scope) DO UPDATE SET historical_tokens=GREATEST(quant_ai_budget_accounts.historical_tokens,EXCLUDED.historical_tokens),unknown_history=EXCLUDED.unknown_history,baseline_reference=EXCLUDED.baseline_reference,updated_at=NOW() WHERE quant_ai_budget_accounts.baseline_state='pending'",(org,scope,ceiling,exact,store.encode(unknown),str(audit_path)))
 return {'known_lower_bound':exact,'complete':False,'state':'pending'}
