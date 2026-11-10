"""Explicit product-only unlimited authorization; historical accounting is immutable."""
from __future__ import annotations
import json
from pathlib import Path
from services.core.db import get_conn
from .policy import WorkflowError,digest
from . import store
SCOPE='institutional_quant.factor_research'
AUTHORIZED_ORG=261

def validate_authorization(record,org):
 policy=record.get('new_policy') or {}
 prior=record.get('supersedes_token_ceiling') or {}
 if (org!=AUTHORIZED_ORG or record.get('schema')!='pm.quant-factor.token-policy.v2'
     or record.get('org_id')!=org or policy.get('token_limit_mode')!='unlimited'
     or 'product_cumulative_token_limit' not in policy or policy['product_cumulative_token_limit'] is not None
     or policy.get('keep_actual_usage_and_unresolved_records') is not True
     or policy.get('max_concurrent_factor_research_tasks')!=1
     or policy.get('overflow')!='persistent_queue'
     or prior.get('historical_records_preserved') is not True
     or not isinstance(prior.get('grant_id'),str) or not prior['grant_id']
     or not isinstance(prior.get('old_limit_tokens'),int) or isinstance(prior['old_limit_tokens'],bool)
     or not record.get('unchanged_boundaries')):
  raise WorkflowError('授权记录与本产品持续研究政策不一致，未应用')
 return {'scope':SCOPE,'mode':'unlimited','supersedes_grant_id':prior['grant_id'],'previous_limit_tokens':prior['old_limit_tokens'],'authorization_hash':digest(record)}

def current(c,org):
 row=c.execute('SELECT * FROM quant_research_token_policies WHERE org_id=%s AND scope=%s',(org,SCOPE)).fetchone()
 return dict(row) if row else None

def install(org,actor,record_path):
 record=json.loads(Path(record_path).read_text());policy=validate_authorization(record,org)
 with get_conn() as c:
  c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'quant-ai-budget:{org}',))
  prior=current(c,org)
  if prior:
   if prior['authorization_hash']!=policy['authorization_hash']:raise WorkflowError('已有不同的研究政策授权，未覆盖原记录')
   return prior
  grant=c.execute('SELECT * FROM quant_ai_budget_supplements WHERE id=%s AND org_id=%s FOR UPDATE',(policy['supersedes_grant_id'],org)).fetchone()
  if not grant or grant['limit_tokens']!=policy['previous_limit_tokens']:raise WorkflowError('原授权身份与记录不一致，未重置历史额度')
  member=c.execute("SELECT id FROM inst_members WHERE org_id=%s AND user_id=%s AND status='active'",(org,actor)).fetchone()
  if not member:raise WorkflowError('授权操作人不是本机构有效成员')
  identifier='qtp_'+policy['authorization_hash'][:24]
  c.execute("INSERT INTO quant_research_token_policies(id,org_id,scope,mode,authorized_by,supersedes_grant_id,authorization_hash,authorization_reference,authorization_record) VALUES(%s,%s,%s,'unlimited',%s,%s,%s,%s,%s::jsonb)",(identifier,org,SCOPE,actor,grant['id'],policy['authorization_hash'],str(record_path),store.encode(record)))
  return current(c,org)
