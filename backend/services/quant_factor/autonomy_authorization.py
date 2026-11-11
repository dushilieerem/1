"""CR102: server-frozen scope and owner controls. No DB/model side effects.
The adapter must resolve server_scope from effective policies; client scope/hash is never accepted.
Persistence requires the caller to hold the authorization row lock for the transition.
"""
from copy import deepcopy
import uuid
from .research_experience import digest
from .autonomy_contract import family_key

class AuthorizationConflict(ValueError):pass

def _writer(actor,member):
 uid,org=actor
 if not isinstance(uid,int) or isinstance(uid,bool) or not isinstance(org,int) or isinstance(org,bool) or min(uid,org)<1:raise PermissionError('Invalid actor')
 if member.get('user_id')!=uid or member.get('org_id')!=org or member.get('status')!='active' or member.get('role') not in ('quant_researcher','manager') or member.get('quant_permission')!='write':raise PermissionError('Research authorization requires an active research member')

def prepare(actor,member,server_scope,direction,request_key):
 _writer(actor,member)
 if not isinstance(direction,str) or len(direction)>1000:raise ValueError('Invalid direction preference')
 try:key=str(uuid.UUID(request_key))
 except (ValueError,TypeError,AttributeError):raise ValueError('A stable request UUID is required')
 required={'org_id','authority_lineage_id','version','data_identity','universe_snapshot','development','validation','forecast_horizon_sessions','ic_metric','allowed_fields','rules','resource_limits','task_max_trials','overall_max_trials'}
 if not isinstance(server_scope,dict) or set(server_scope)!=required:raise ValueError('The server research scope is incomplete')
 if server_scope['org_id']!=actor[1]:raise PermissionError('Scope belongs to another institution')
 if not isinstance(server_scope['version'],int) or isinstance(server_scope['version'],bool) or server_scope['version']<1:raise ValueError('Invalid scope version')
 if not isinstance(server_scope['task_max_trials'],int) or isinstance(server_scope['task_max_trials'],bool) or server_scope['task_max_trials']<1:raise ValueError('Task trial policy is missing')
 overall=server_scope['overall_max_trials']
 if overall is not None and (not isinstance(overall,int) or isinstance(overall,bool) or overall<1):raise ValueError('Invalid overall trial policy')
 fields=server_scope['allowed_fields']
 if not isinstance(fields,list) or not fields or len(fields)!=len(set(fields)) or any(not isinstance(v,str) or not v for v in fields):raise ValueError('Effective fields must be explicit')
 if not isinstance(server_scope['rules'],dict) or not server_scope['rules'] or not isinstance(server_scope['resource_limits'],dict) or not server_scope['resource_limits']:raise ValueError('Effective rules and resource policy are required')
 # Validate the canonical statistical family independently from per-task trial ceilings.
 family=family_key(server_scope)
 from datetime import date
 validation=server_scope['validation']
 if not isinstance(validation,list) or len(validation)!=2 or any(not isinstance(v,str) for v in validation):raise ValueError('Validation interval is required')
 if not date.fromisoformat(server_scope['development'][1])<date.fromisoformat(validation[0])<=date.fromisoformat(validation[1]):raise ValueError('Development and independent validation must remain separate')
 snapshot=deepcopy(server_scope)
 authority_hash=digest(snapshot)
 request_hash=digest({'actor':list(actor),'scope_hash':authority_hash,'direction':direction.strip()})
 return {'id':str(uuid.uuid5(uuid.NAMESPACE_URL,f'quant-autonomy:{actor[1]}:{actor[0]}:{key}')),'user_id':actor[0],'org_id':actor[1],'request_key':key,'request_hash':request_hash,'version':1,'enabled':True,'scope':snapshot,'scope_hash':authority_hash,'family_id':family,'direction':direction.strip(),'controls':[]}

def original_receipt(existing,prepared,actor):
 if existing['user_id']!=actor[0] or existing['org_id']!=actor[1]:raise PermissionError('Authorization receipt is private')
 if existing['id']!=prepared['id'] or existing['request_hash']!=prepared['request_hash']:raise AuthorizationConflict('This submission belongs to a different research scope or direction')
 return deepcopy(existing)

def control(record,actor,member,*,enabled,expected_version,request_key):
 _writer(actor,member)
 if (record['user_id'],record['org_id'])!=actor:raise PermissionError('Only the original owner may change this authorization')
 if not isinstance(enabled,bool):raise ValueError('Explicit control is required')
 if not isinstance(expected_version,int) or isinstance(expected_version,bool):raise ValueError('Expected version is required')
 try:key=str(uuid.UUID(request_key))
 except (ValueError,TypeError,AttributeError):raise ValueError('A stable request UUID is required')
 signature=digest({'enabled':enabled,'expected_version':expected_version})
 old=next((x for x in record['controls'] if x['request_key']==key),None)
 if old:
  if old['request_hash']!=signature:raise AuthorizationConflict('Control identity was reused with different content')
  return deepcopy(record)
 if record['version']!=expected_version:raise AuthorizationConflict('Research authorization changed; refresh before applying a new control')
 out=deepcopy(record);out['enabled']=enabled;out['version']+=1;out['controls'].append({'request_key':key,'request_hash':signature,'enabled':enabled,'applied_version':out['version']})
 return out

def may_plan(record,actor,member,expected_version):
 try:_writer(actor,member)
 except PermissionError:return False
 return (record['user_id'],record['org_id'])==actor and record['enabled'] is True and record['version']==expected_version and digest(record['scope'])==record['scope_hash']
