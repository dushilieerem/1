"""CR102 durable authorization entry points. Scope installation is an operator policy,
never a researcher payload. No DDL, model call or compute is performed here.
The execution feature is off until its reviewed planner/family adapters are loaded.
"""
from copy import deepcopy
import json,uuid
from services.core.db import get_conn
from services.core.env_config import env
from services.institution.inst_store import _quant_context,QUANT_LOGIN_ROLES
from .research_experience import digest
from .autonomy_contract import family_scope
from . import autonomy_authorization as rules

class AutonomyError(Exception):
 def __init__(self,code,message,status=409):super().__init__(message);self.code=code;self.status=status

def enabled():return env('QUANT_AUTONOMOUS_RESEARCH_ENABLED','0')=='1'
def _request_key(value):
 try:return str(uuid.UUID(value))
 except (ValueError,TypeError,AttributeError):raise AutonomyError('invalid_submission','请重新确认这笔操作。',400) from None
def installed(c):
 names=('quant_research_scope_grants','quant_research_authorizations','quant_research_planning_triggers','quant_research_planning_runs','quant_research_evaluation_families','quant_research_family_topics','quant_research_authorization_events')
 row=c.execute("SELECT bool_and(to_regclass(checks.name) IS NOT NULL) AS available FROM unnest(%s::text[]) AS checks(name)",(list(names),)).fetchone()
 return bool(row and row['available'])

def _member(c,uid,org,write=False):
 row=c.execute("SELECT m.id,m.org_id,m.role,m.status AS member_status,o.code,o.name_cn,o.name_en,o.status AS org_status,u.status AS user_status FROM inst_members m JOIN inst_orgs o ON o.id=m.org_id JOIN users u ON u.id=m.user_id WHERE m.user_id=%s AND m.org_id=%s",(uid,org)).fetchone()
 if not row or row['member_status']!='active' or row['org_status']!='active' or row['user_status']!='active' or row['role'] not in QUANT_LOGIN_ROLES:raise AutonomyError('membership_inactive','机构研究权限已变化，请重新登录核对。',403)
 ctx=_quant_context({'id':uid,'status':row['user_status']},dict(row))
 if write and not ctx['can_write']:raise AutonomyError('research_read_only','当前身份只能查看自主研究。',403)
 return {'user_id':uid,'org_id':org,'role':row['role'],'status':'active','quant_permission':ctx['permissions']['quant']}

def _scope_summary(row):
 s=row['snapshot'];return {'id':row['id'],'name':row['name'],'version':row['version'],'data_view_id':s['data_identity']['view_id'],'allowed_fields':s['allowed_fields'],'sample_count':len(s['universe_snapshot']),'universe_snapshot':s['universe_snapshot'],'development':s['development'],'validation':s['validation'],'forecast_horizon_sessions':s['forecast_horizon_sessions'],'ic_metric':s['ic_metric'],'task_max_trials':s['task_max_trials'],'overall_max_trials':s['overall_max_trials']}

def _public(row,scope=None):
 if scope is None:scope={'id':row['scope_id'],'name':'已保存的研究范围','version':row['scope_version'],'snapshot':row['scope']}
 return {'id':row['id'],'version':row['version'],'enabled':row['enabled'],'scope_id':row['scope_id'],'scope_version':row['scope_version'],'direction':row['direction'],'scope':_scope_summary(scope) if scope else None,'family_id':row['family_id'],'updated_at':row.get('updated_at'),'state':'waiting_planning' if row['enabled'] else 'paused'}

def status(uid,org):
 with get_conn() as c:
  if not installed(c):return {'available':False,'enabled':False,'state':'not_enabled','reason':'自主研究尚未配置，可继续使用已有研究任务。','scopes':[],'authorization':None}
  member=_member(c,uid,org)
  scopes=c.execute('SELECT * FROM quant_research_scope_grants WHERE org_id=%s AND (user_id=%s OR user_id IS NULL) AND enabled ORDER BY created_at,id',(org,uid)).fetchall()
  row=c.execute('SELECT * FROM quant_research_authorizations WHERE user_id=%s AND org_id=%s ORDER BY enabled DESC,updated_at DESC,id LIMIT 1',(uid,org)).fetchone()
  scope=next((x for x in scopes if row and x['id']==row['scope_id'] and x['version']==row['scope_version']),None)
  available=enabled() and bool(scopes);effective=bool(row and row['enabled'] and scope and member['quant_permission']=='write' and available)
  latest=c.execute('SELECT id,status,decision_reason,project_id,topic_id,f0_run_id,updated_at FROM quant_research_planning_runs WHERE user_id=%s AND org_id=%s ORDER BY created_at DESC,id DESC LIMIT 1',(uid,org)).fetchone()
 return {'available':available,'enabled':effective,'state':latest['status'] if effective and latest else 'waiting_planning' if effective else 'paused' if row and not row['enabled'] else 'not_enabled','reason':'' if effective else '自主研究尚未启用。' if scopes and not enabled() else '请先确认可用研究范围。' if not scopes else '尚未开启自主研究。','scopes':[_scope_summary(x) for x in scopes],'authorization':_public(row,scope) if row else None,'planning':dict(latest) if latest else None,'can_control':member['quant_permission']=='write'}

def _write_guard(c,uid,org):
 if not installed(c) or not enabled():raise AutonomyError('autonomy_unavailable','自主研究尚未启用，已有任务不受影响。')
 c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
 return _member(c,uid,org,True)

def _grant(c,uid,org,scope_id,version):
 row=c.execute('SELECT * FROM quant_research_scope_grants WHERE id=%s AND org_id=%s AND (user_id=%s OR user_id IS NULL) FOR SHARE',(scope_id,org,uid)).fetchone()
 if not row or not row['enabled'] or row['version']!=version:raise AutonomyError('scope_changed','研究范围已变化或暂不可用，请重新确认。')
 if row['snapshot_hash']!=digest(row['snapshot']) or row['snapshot'].get('org_id')!=org or row['snapshot'].get('version')!=version:raise AutonomyError('scope_unconfirmed','研究范围的授权记录需要核对，尚未启动。')
 return dict(row)

def _trigger(c,row,reason,key):
 # Persist one pending event, never a model call or an unbounded task list.
 old=c.execute("SELECT * FROM quant_research_planning_triggers WHERE authorization_id=%s AND state='pending' FOR UPDATE",(row['id'],)).fetchone()
 if old:return dict(old)
 identifier=str(uuid.uuid4())
 return dict(c.execute("INSERT INTO quant_research_planning_triggers(id,user_id,org_id,authorization_id,authorization_version,reason,request_key,state) VALUES(%s,%s,%s,%s,%s,%s,%s,'pending') ON CONFLICT(authorization_id,request_key) DO UPDATE SET request_key=EXCLUDED.request_key RETURNING *",(identifier,row['user_id'],row['org_id'],row['id'],row['version'],reason,key)).fetchone())

def enable(uid,org,body):
 body={**body,'request_key':_request_key(body['request_key'])}
 target={'scope_id':body['scope_id'],'scope_version':body['scope_version'],'direction':body['direction'].strip()};request_hash=digest(target)
 with get_conn() as c:
  member=_write_guard(c,uid,org)
  old=c.execute('SELECT * FROM quant_research_authorizations WHERE user_id=%s AND org_id=%s AND request_key=%s FOR UPDATE',(uid,org,body['request_key'])).fetchone()
  if old:
   if old['request_hash']!=request_hash:raise AutonomyError('submission_conflict','这笔开启请求已绑定另一份范围或方向，请先核对原记录。')
   return _public(old)
  grant=_grant(c,uid,org,body['scope_id'],body['scope_version'])
  active=c.execute('SELECT id FROM quant_research_authorizations WHERE user_id=%s AND org_id=%s AND enabled LIMIT 1 FOR UPDATE',(uid,org)).fetchone()
  if active:raise AutonomyError('already_enabled','已有开启的自主研究，请先查看或暂停原授权。')
  try:record=rules.prepare((uid,org),member,grant['snapshot'],body['direction'],body['request_key'])
  except (ValueError,PermissionError) as exc:raise AutonomyError('scope_unconfirmed','研究范围尚未完整核对，尚未启动。') from exc
  # Family facts are never model supplied. Its existing immutable scope must agree.
  identity_scope=family_scope(grant['snapshot'])
  c.execute('INSERT INTO quant_research_evaluation_families(id,org_id,authority_lineage_id,scope,scope_hash) VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT(id) DO NOTHING',(record['family_id'],org,grant['snapshot']['authority_lineage_id'],json.dumps(identity_scope),digest(identity_scope)))
  family=c.execute('SELECT * FROM quant_research_evaluation_families WHERE id=%s AND org_id=%s FOR UPDATE',(record['family_id'],org)).fetchone()
  if not family or family['scope_hash']!=digest(identity_scope):raise AutonomyError('family_changed','原研究谱系需要核对，未创建新任务。')
  row=c.execute('INSERT INTO quant_research_authorizations(id,user_id,org_id,request_key,request_hash,scope_id,scope_version,scope,scope_hash,family_id,direction,version,enabled) VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,1,TRUE) RETURNING *',(record['id'],uid,org,body['request_key'],request_hash,grant['id'],grant['version'],json.dumps(record['scope']),record['scope_hash'],record['family_id'],record['direction'])).fetchone()
  c.execute("INSERT INTO quant_research_authorization_events(id,authorization_id,user_id,org_id,version,request_key,request_hash,action,payload) VALUES(%s,%s,%s,%s,1,%s,%s,'enabled',%s::jsonb)",(str(uuid.uuid4()),record['id'],uid,org,body['request_key'],request_hash,json.dumps({'scope_id':grant['id'],'scope_version':grant['version']})))
  _trigger(c,row,'user_enabled','enable:'+body['request_key'])
 return _public(row,grant)

def control(uid,org,aid,body):
 body={**body,'request_key':_request_key(body['request_key'])}
 with get_conn() as c:
  member=_write_guard(c,uid,org)
  row=c.execute('SELECT * FROM quant_research_authorizations WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(aid,uid,org)).fetchone()
  if not row:raise AutonomyError('authorization_not_found','记录不存在或无权访问。',404)
  events=c.execute("SELECT request_key,request_hash,payload FROM quant_research_authorization_events WHERE authorization_id=%s AND action IN ('enabled','paused')",(aid,)).fetchall()
  if any(e['request_key']==body['request_key'] and 'enabled' not in e['payload'] for e in events):raise AutonomyError('submission_conflict','这笔提交身份已用于另一项操作，请先核对原记录。')
  record=dict(row);record['controls']=[{'request_key':e['request_key'],'request_hash':e['request_hash'],**e['payload']} for e in events if 'enabled' in e['payload']]
  try:next_state=rules.control(record,(uid,org),member,enabled=body['enabled'],expected_version=body['expected_version'],request_key=body['request_key'])
  except rules.AuthorizationConflict as exc:raise AutonomyError('authorization_changed','自主研究状态已变化，请刷新后确认。') from exc
  if next_state['version']==row['version']:return _public(row)
  if next_state['enabled']:_grant(c,uid,org,row['scope_id'],row['scope_version'])
  changed=c.execute('UPDATE quant_research_authorizations SET enabled=%s,version=%s,updated_at=NOW() WHERE id=%s AND version=%s RETURNING *',(next_state['enabled'],next_state['version'],aid,row['version'])).fetchone()
  if not changed:raise AutonomyError('authorization_changed','自主研究状态已变化，请刷新后确认。')
  event=next_state['controls'][-1]
  c.execute('INSERT INTO quant_research_authorization_events(id,authorization_id,user_id,org_id,version,request_key,request_hash,action,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',(str(uuid.uuid4()),aid,uid,org,next_state['version'],event['request_key'],event['request_hash'],'enabled' if next_state['enabled'] else 'paused',json.dumps({'enabled':event['enabled'],'applied_version':event['applied_version']})))
  if not next_state['enabled']:
   c.execute("UPDATE quant_research_planning_triggers SET state='cancelled',updated_at=NOW() WHERE authorization_id=%s AND state='pending'",(aid,))
  else:_trigger(c,changed,'user_resumed','resume:'+body['request_key'])
 return _public(changed)
