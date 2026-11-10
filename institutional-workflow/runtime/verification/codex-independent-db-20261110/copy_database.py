"""Approved scoped DB-to-DB copy. No row dumps, source writes, bootstrap or replay.
Every write is to the newly initialized target. Existing business rows stop the copy.
"""
from db_operator_common import *
from psycopg.types.json import Jsonb
from datetime import date,datetime,timezone
from decimal import Decimal
import uuid,secrets

USER_COLS=['id','username','password_hash','role','status','ai_quota_daily','token_version','created_at','updated_at']
MEMBER_COLS=['id','org_id','user_id','role','status','created_at','updated_at']
AUDIT_COLS=['id','created_at','user_id','role','action','module','resource','method','path','status_code','duration_ms','request_id']
COPIED=['users','inst_orgs','inst_members','detect_projects','quant_factor_topics','quant_factor_branches','detect_runs','quant_factor_candidates','quant_factor_agent_jobs','quant_factor_f0_runs','quant_factor_iterations','quant_factor_trials','quant_factor_sealed_validations','quant_factor_imported_factors','quant_factor_controls','quant_factor_org_controls','quant_ai_budget_accounts','quant_ai_budget_supplements','quant_research_token_policies','quant_research_queue_jobs','quant_research_queue_slots','quant_ai_budget_calls','quant_data_requests','ai_usage','user_factor_libraries','user_library_factors','user_custom_factors','factor_dashboard_metrics','app_audit_logs']

def normalize(v):
 if isinstance(v,datetime):return v.astimezone(timezone.utc).isoformat()
 if isinstance(v,date):return v.isoformat()
 if isinstance(v,(Decimal,uuid.UUID)):return str(v)
 if isinstance(v,dict):return {str(k):normalize(x) for k,x in sorted(v.items())}
 if isinstance(v,(list,tuple)):return [normalize(x) for x in v]
 return v

def digest(rows,*,exclude=()):
 strings=[json.dumps(normalize({k:v for k,v in r.items() if k not in exclude}),sort_keys=True,ensure_ascii=False,separators=(',',':')) for r in rows]
 return hashlib.sha256(('\n'.join(sorted(strings))).encode()).hexdigest()

def topo(rows,parent):
 remaining=list(rows);done=set();out=[]
 while remaining:
  ready=[r for r in remaining if not r.get(parent) or r[parent] in done]
  if not ready:raise RuntimeError('missing or cyclic whitelist parent: '+parent)
  for r in ready:out.append(r);done.add(r['id']);remaining.remove(r)
 return out

def columns(c,t):
 return c.execute("SELECT column_name,data_type,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",(t,)).fetchall()

def rows(c,t,where='',args=(),cols=None):
 selected=sql.SQL(',').join(map(sql.Identifier,cols)) if cols else sql.SQL('*')
 return [dict(r) for r in c.execute(sql.SQL('SELECT {} FROM {} {}').format(selected,sql.Identifier(t),sql.SQL('WHERE '+where if where else '')),args).fetchall()]

def snapshot(c,cutoff):
 topics=rows(c,'quant_factor_topics','user_id=%s AND org_id=%s',(2527,ORG))
 projects=sorted({t['project_id'] for t in topics});expected=json.loads((HERE/'readonly-closure.json').read_text())['topic_project_ids']
 if projects!=expected or len(topics)!=19:raise RuntimeError('source research scope changed; re-review required')
 topic_ids=[r['id'] for r in topics]
 deployment='quant-bff-18799-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
 out={'users':rows(c,'users','id=ANY(%s)',(list(QA),),USER_COLS),'inst_orgs':rows(c,'inst_orgs','id=%s',(ORG,)),'inst_members':rows(c,'inst_members','org_id=%s AND user_id=ANY(%s)',(ORG,list(QA)),MEMBER_COLS),'quant_factor_topics':topics}
 out['detect_projects']=rows(c,'detect_projects','user_id=%s AND id=ANY(%s)',(2527,projects))
 out['detect_runs']=rows(c,'detect_runs','user_id=%s AND project_id=ANY(%s)',(2527,projects))
 for t in ['quant_factor_branches','quant_factor_trials']:
  out[t]=rows(c,t,'user_id=%s AND org_id=%s AND topic_id=ANY(%s)',(2527,ORG,topic_ids))
 for t in ['quant_factor_candidates','quant_factor_f0_runs','quant_factor_iterations','quant_factor_sealed_validations']:
  out[t]=rows(c,t,'user_id=%s AND org_id=%s AND project_id=ANY(%s)',(2527,ORG,projects))
 out['quant_factor_agent_jobs']=rows(c,'quant_factor_agent_jobs','user_id=%s AND org_id=%s AND (project_id=ANY(%s) OR project_id IS NULL)',(2527,ORG,projects))
 for t in ['quant_factor_imported_factors','quant_factor_org_controls','quant_ai_budget_accounts','quant_ai_budget_supplements','quant_research_token_policies']:
  out[t]=rows(c,t,'org_id=%s',(ORG,))
 out['quant_factor_controls']=rows(c,'quant_factor_controls','org_id=%s AND user_id=ANY(%s)',(ORG,list(QA)))
 out['quant_ai_budget_calls']=rows(c,'quant_ai_budget_calls','org_id=%s AND user_id=ANY(%s)',(ORG,list(QA)))
 out['quant_research_queue_jobs']=rows(c,'quant_research_queue_jobs','deployment_id=%s AND org_id=%s AND user_id=ANY(%s)',(deployment,ORG,list(QA)))
 out['quant_research_queue_slots']=rows(c,'quant_research_queue_slots','deployment_id=%s',(deployment,))
 out['quant_data_requests']=rows(c,'quant_data_requests','org_id=%s AND user_id=%s',(ORG,2527))
 out['ai_usage']=rows(c,'ai_usage','user_id=ANY(%s)',(list(QA),))
 for t in ['user_factor_libraries','user_library_factors','user_custom_factors']:out[t]=rows(c,t,'user_id=%s',(2527,))
 out['app_audit_logs']=rows(c,'app_audit_logs',"user_id=ANY(%s) AND path LIKE '/api/inst/quant/%%' AND created_at<=%s",(list(QA),cutoff),AUDIT_COLS)
 out['factor_dashboard_metrics']=[dict(r) for r in c.execute("""SELECT DISTINCT d.* FROM quant_factor_imported_factors i JOIN LATERAL (SELECT x.* FROM factor_dashboard_metrics x WHERE x.library=i.source_library AND x.factor_name=i.factor_name AND x.rules_version='yg_v1' ORDER BY (x.universe='CSI300') DESC,(x.period='3y') DESC,(x.filter_limit_up=1) DESC,(x.filter_suspended=1) DESC,x.computed_at DESC LIMIT 1) d ON TRUE WHERE i.org_id=%s""",(ORG,)).fetchall()]
 if set(out)!=set(COPIED):raise RuntimeError('copy selector outside exact allowlist')
 return out

def validate(data):
 expected={'users':3,'inst_orgs':1,'inst_members':3,'detect_projects':19,'detect_runs':28,'quant_factor_topics':19,'quant_factor_branches':36,'quant_factor_candidates':29,'quant_factor_trials':28,'quant_factor_f0_runs':32,'quant_factor_agent_jobs':27,'quant_factor_iterations':0,'quant_factor_sealed_validations':3,'quant_factor_imported_factors':331,'quant_factor_controls':1,'quant_factor_org_controls':1,'quant_ai_budget_accounts':2,'quant_ai_budget_supplements':1,'quant_research_token_policies':1,'quant_ai_budget_calls':17,'quant_research_queue_jobs':7,'quant_research_queue_slots':1,'quant_data_requests':2,'ai_usage':93,'user_factor_libraries':0,'user_library_factors':0,'user_custom_factors':0,'factor_dashboard_metrics':331}
 for t,n in expected.items():
  if len(data[t])!=n:raise RuntimeError('source approved count changed: '+t)
 actors=set(QA)|{1046}
 for t,rs in data.items():
  for r in rs:
   for key in ['user_id','created_by','authorized_by','paused_by','handled_by','owner_id']:
    if r.get(key) is not None and r[key] not in actors:raise RuntimeError('actor dependency outside whitelist: '+t+'.'+key)
 for t in ['quant_factor_f0_runs','quant_factor_agent_jobs','quant_factor_iterations']:
  if any(r['status'] in ('queued','running') for r in data[t]):raise RuntimeError('active research found; stop copy')
 if any(r['status'].endswith('_running') for r in data['quant_factor_candidates']):raise RuntimeError('active candidate found')
 if any(r['status']!='settled' for r in data['quant_ai_budget_calls']):raise RuntimeError('unresolved physical usage found')
 if any(r['status']!='completed' for r in data['quant_research_queue_jobs']) or any(r['root_id'] for r in data['quant_research_queue_slots']):raise RuntimeError('owned queue occupied')
 for r in data['quant_ai_budget_calls']:
  if r.get('project_id') and r['project_id'] not in {x['id'] for x in data['detect_projects']}:raise RuntimeError('call project outside whitelist')
 if sum(r['actual_tokens'] or 0 for r in data['quant_ai_budget_calls'])!=121103:raise RuntimeError('metered actual changed')
 if {r['mode'] for r in data['quant_research_token_policies']}!={'unlimited'}:raise RuntimeError('authorization changed')

def insert(c,t,rs):
 if t not in COPIED:raise RuntimeError('write table not approved')
 assert_target(c)
 if not rs:return
 cols=list(rs[0]);types={r['column_name']:r['data_type'] for r in columns(c,t)}
 if not set(cols)<=set(types):raise RuntimeError('target columns differ: '+t)
 stmt=sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(t),sql.SQL(',').join(map(sql.Identifier,cols)),sql.SQL(',').join(sql.Placeholder() for _ in cols))
 vals=[tuple(Jsonb(r[k]) if types[k] in ('json','jsonb') and r[k] is not None else r[k] for k in cols) for r in rs]
 with c.cursor() as cur:cur.executemany(stmt,vals)

def main():
 if sys.argv[1:]!=['--copy-approved-qa-history']:raise RuntimeError('explicit scoped copy flag required')
 marker=json.loads((HERE/'initialization-marker.json').read_text())
 if marker.get('status')!='initialized_empty' or marker.get('database')!=TARGET:raise RuntimeError('target not approved initialized empty state')
 cap=capture()
 with connect(SOURCE,readonly=True) as src:
  src.rollback();src.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
  cutoff=src.execute('SELECT clock_timestamp() AS t').fetchone()['t']
  before=src.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall()
  data=snapshot(src,cutoff);validate(data)
  stub={'id':1046,'username':'historical_reference_1046','password_hash':'disabled-reference-'+secrets.token_hex(48),'role':'user','status':'disabled','ai_quota_daily':0,'token_version':0,'created_at':cutoff,'updated_at':cutoff}
  with connect(TARGET) as dst:
   assert_target(dst)
   for t in cap['schema_table_allowlist']:
    if t!='schema_migrations':assert_empty(dst,t)
   for t in COPIED:
    rs=data[t]
    if t=='users':rs=rs+[stub]
    if t=='quant_factor_branches':rs=topo(rs,'parent_id')
    if t=='quant_factor_trials':rs=topo(rs,'rerun_of')
    if t=='quant_research_queue_jobs':rs=topo(rs,'parent_id')
    insert(dst,t,rs)
   verified={}
   for t in COPIED:
    if t=='users':actual=rows(dst,t,'id=ANY(%s)',(list(QA),),USER_COLS)
    else:actual=rows(dst,t,cols=list(data[t][0]) if data[t] else None)
    if digest(actual)!=digest(data[t]):raise RuntimeError('source target row equality failed: '+t)
    verified[t]={'rows':len(actual),'equal':True,'sha256':digest(actual,exclude=('password_hash',))}
   # Compare latest source before the target commit. Read-only HTTP audit appends after cutoff are reported separately.
   with connect(SOURCE,readonly=True) as current:
    latest=snapshot(current,cutoff);validate(latest)
    changed=[t for t in COPIED if digest(latest[t])!=digest(data[t])]
    schema_now=current.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall()
    if changed or schema_now!=before:raise RuntimeError('source changed during snapshot; target transaction will rollback: '+','.join(changed))
    audit_after=current.execute("SELECT count(*) AS n FROM app_audit_logs WHERE user_id=ANY(%s) AND path LIKE '/api/inst/quant/%%' AND created_at>%s",(list(QA),cutoff)).fetchone()['n']
   # Only target-owned serial sequences; no shared sequence writes.
   seqs=[]
   for t in COPIED:
    for col in columns(dst,t):
     if (col['column_default'] or '').startswith('nextval('):
      seq=dst.execute('SELECT pg_get_serial_sequence(%s,%s) AS s',(t,col['column_name'])).fetchone()['s']
      if seq:
       high=dst.execute(sql.SQL('SELECT max({}) AS m FROM {}').format(sql.Identifier(col['column_name']),sql.Identifier(t))).fetchone()['m']
       dst.execute('SELECT setval(%s::regclass,%s,%s)',(seq,high if high is not None else 1,high is not None));seqs.append(seq)
   dst.execute('SET CONSTRAINTS ALL IMMEDIATE')
  # Target has committed. Source still read-only and its schema history is untouched.
 report={'status':'prepared_verified_not_loaded','at_utc':now(),'target_database':TARGET,'source_read_only':True,'snapshot_cutoff':cutoff,'source_core_changed_during_copy':False,'source_audit_appends_after_cutoff':audit_after,'row_checks':verified,'historical_reference':{'user_id':1046,'disabled':True,'original_credentials_or_membership_copied':False},'target_serial_sequences_reset':seqs,'source_schema_migrations_unchanged':True,'canonical_target_migrations':43,'product_known_actual_tokens':121103,'historical_lower_bound':180331,'historical_missing_calls':46,'overlapping_scopes_not_added':True,'authorization_mode':'unlimited','no_budget_reset_or_new_grant':True,'services_switched':False,'source_business_count_changes_since_approved_plan':False}
 save('copy-verification.json',report)
 save('initialization-marker.json',{'status':'prepared_verified_not_loaded','database':TARGET,'at_utc':now(),'snapshot_cutoff':cutoff})
 print('approved QA history committed and verified; source read-only; no service switch')

if __name__=='__main__':
 try:main()
 except Exception as exc:
  safe_failure('copy-error.json',exc);print('copy stopped; sanitized evidence written');sys.exit(1)
