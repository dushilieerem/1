"""Bounded real authorization transactions ONLY in a new temporary schema of svquant_zxd_dev.
No public migration, shared database access, model, service reload or research dispatch.
"""
import argparse,contextlib,json,os,re,socket,sys,uuid,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--allow-owned-temporary-schema',action='store_true');args=parser.parse_args()
if not args.allow_owned_temporary_schema:raise SystemExit('Explicit owned-schema test flag required')
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_AUTONOMOUS_RESEARCH_ENABLED']='1';sys.path.insert(0,str(ROOT/'backend'))
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg import sql
configuration=ROOT/'institutional-workflow/runtime/.private/quant-zxd-db.env'
values=dict(line.split('=',1) for line in configuration.read_text().splitlines() if line and not line.startswith('#') and '=' in line)
opts=conninfo_to_dict(values['DATABASE_URL'])
if opts.get('dbname')!='svquant_zxd_dev':raise SystemExit('Shared/unknown DB forbidden')
SCHEMA='quant_cr102_'+uuid.uuid4().hex[:16]
if not re.fullmatch(r'quant_cr102_[0-9a-f]{16}',SCHEMA):raise SystemExit('Invalid fixture schema')
opts['options']=f'-c search_path={SCHEMA},pg_catalog -c statement_timeout=5000 -c lock_timeout=2500'
NATIVE_CONNECT=psycopg.connect

def assert_target(c,*,allow_schema_absent=False):
 state=c.execute("SELECT current_database() AS db,current_user AS actor,current_schema() AS first_schema,current_schemas(FALSE) AS schemas").fetchone()
 if state['db']!='svquant_zxd_dev' or state['actor']!=opts.get('user'):raise RuntimeError('fixture database/actor mismatch')
 if not allow_schema_absent and (state['first_schema']!=SCHEMA or state['schemas']!=[SCHEMA,'pg_catalog']):raise RuntimeError('fixture search_path can fall outside isolated schema')

def connection(*,autocommit=False,allow_schema_absent=False,readonly=False):
 selected=dict(opts)
 if readonly:selected['options']+=' -c default_transaction_read_only=on'
 c=NATIVE_CONNECT(make_conninfo(**selected),row_factory=dict_row,autocommit=autocommit)
 try:assert_target(c,allow_schema_absent=allow_schema_absent)
 except Exception:c.close();raise
 return c

def forbidden(*a,**k):raise AssertionError('No unreviewed DB/model/HTTP access in owned PG test')

def guarded_connect(conninfo='',**kw):
 requested=conninfo_to_dict(conninfo,**kw)
 if requested.get('dbname')!='svquant_zxd_dev' or requested.get('options')!=opts['options']:return forbidden()
 return NATIVE_CONNECT(conninfo,**kw)

def public_fingerprint():
 # Explicit schema-qualified reads only; no application/bootstrap imports or public writes.
 import hashlib
 with connection(allow_schema_absent=True,readonly=True) as c:
  allowed=json.loads((ROOT/'institutional-workflow/runtime/verification/codex-independent-db-20261110/schema-capture.json').read_text())['schema_table_allowlist']
  result={}
  for entry in allowed:
   namespace,name=entry.split('.',1) if '.' in entry else ('public',entry)
   records=c.execute(sql.SQL("SELECT to_jsonb(t)-'password_hash' AS value FROM {}.{} t").format(sql.Identifier(namespace),sql.Identifier(name))).fetchall()
   lines=sorted(json.dumps(row['value'],sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str) for row in records)
   result[entry]={'count':len(lines),'sha':hashlib.sha256(('\n'.join(lines)).encode()).hexdigest()}
  constraints=c.execute("SELECT n.nspname,c.relname,pg_get_constraintdef(k.oid) AS definition FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','svquant') ORDER BY n.nspname,c.relname,k.conname").fetchall()
  result['constraint_definitions']=hashlib.sha256(json.dumps(constraints,sort_keys=True,default=str).encode()).hexdigest()
  return result

guards=contextlib.ExitStack()
guards.enter_context(patch.object(psycopg,'connect',side_effect=forbidden))
guards.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden))
guards.enter_context(patch.object(socket.socket,'connect_ex',side_effect=forbidden))
from services.quant_factor import autonomy
from services.quant_factor.research_experience import digest

PUBLIC_BEFORE=public_fingerprint()
SCHEMA_OID=None
migration=(ROOT/'institutional-workflow/migrations/0048_quant_autonomous_research.sql').read_text()
# This one fixture bundle may contain table/index/constraint DDL only; no DML/roles/hooks.
reviewed='\n'.join(line.split('--',1)[0] for line in migration.splitlines())
if re.search(r'\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|GRANT|REVOKE|EXECUTE|FUNCTION|EXTENSION|DATABASE|ROLE)\b',reviewed,re.I):raise RuntimeError('non-schema side effects in fixture bundle')
if re.search(r'\b(public|svquant)\s*\.',reviewed,re.I):raise RuntimeError('schema-qualified business reference forbidden in fixture bundle')
with connection(allow_schema_absent=True) as c:
 c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(SCHEMA)))
 SCHEMA_OID=c.execute('SELECT oid FROM pg_namespace WHERE nspname=%s',(SCHEMA,)).fetchone()['oid']
 assert_target(c)
 c.execute("CREATE TABLE users(id BIGINT PRIMARY KEY,status TEXT NOT NULL);CREATE TABLE inst_orgs(id BIGINT PRIMARY KEY,code TEXT,name_cn TEXT,name_en TEXT,status TEXT);CREATE TABLE inst_members(id BIGINT PRIMARY KEY,user_id BIGINT,org_id BIGINT,role TEXT,status TEXT);CREATE TABLE detect_projects(user_id BIGINT,id TEXT,PRIMARY KEY(user_id,id));CREATE TABLE quant_factor_topics(id TEXT PRIMARY KEY,user_id BIGINT,org_id BIGINT,UNIQUE(user_id,org_id,id));CREATE TABLE quant_factor_f0_runs(id TEXT PRIMARY KEY);CREATE TABLE quant_research_queue_jobs(id TEXT PRIMARY KEY);")
 c.execute(migration)
 refs=c.execute("SELECT k.conname,source_ns.nspname AS source_schema,target_ns.nspname AS target_schema FROM pg_constraint k JOIN pg_class source ON source.oid=k.conrelid JOIN pg_namespace source_ns ON source_ns.oid=source.relnamespace JOIN pg_class target ON target.oid=k.confrelid JOIN pg_namespace target_ns ON target_ns.oid=target.relnamespace WHERE k.contype='f' AND source_ns.nspname=%s",(SCHEMA,)).fetchall()
 if any(row['target_schema']!=SCHEMA for row in refs):raise RuntimeError('fixture FK resolved outside owned schema')
 for name in ('users','inst_orgs','inst_members','detect_projects','quant_factor_topics','quant_factor_f0_runs','quant_research_queue_jobs'):
  resolved=c.execute('SELECT to_regclass(%s)::text AS name',(name,)).fetchone()['name']
  oid=c.execute('SELECT relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%s) AS owned FROM pg_class WHERE oid=to_regclass(%s)',(SCHEMA,name)).fetchone()
  if not oid or not oid['owned']:raise RuntimeError('base table lookup fell outside fixture schema')

BASE=1000000000+int(uuid.uuid4().hex[:6],16)
CASE=0

def fixture():
 global CASE
 CASE+=1;uid=BASE+CASE*10;org=BASE+CASE*10+3;scope_id='scope-'+uuid.uuid4().hex
 scope={'org_id':org,'authority_lineage_id':'fixture-origin-'+str(org),'version':1,'data_identity':{'view_id':'fixture-view','view_manifest_sha256':'a'*64,'daily_release':'fixture-release','daily_dataset_sha256':'b'*64},'universe_snapshot':['000001.SZ','600000.SH'],'development':['2025-07-01','2025-09-30'],'validation':['2026-06-22','2026-09-21'],'forecast_horizon_sessions':1,'ic_metric':'rank_ic','allowed_fields':['close','volume'],'rules':{'icMetric':'rank_ic','minObservations':60},'resource_limits':{'research_concurrency':1,'max_scoring_days':93},'task_max_trials':2,'overall_max_trials':None}
 with connection() as c:
  for user,role,o in [(uid,'quant_researcher',org),(uid+1,'quant_reviewer',org),(uid+2,'quant_researcher',org+1)]:
   c.execute("INSERT INTO users VALUES(%s,'active')",(user,));c.execute("INSERT INTO inst_orgs VALUES(%s,'fixture','fixture',NULL,'active') ON CONFLICT(id) DO NOTHING",(o,));c.execute("INSERT INTO inst_members VALUES(%s,%s,%s,%s,'active')",(user,user,o,role))
  c.execute("INSERT INTO quant_research_scope_grants(id,org_id,authorized_by,name,version,snapshot,snapshot_hash,authorization_reference) VALUES(%s,%s,%s,'fixture scope',1,%s,%s,'isolated test only')",(scope_id,org,uid,Jsonb(scope),digest(scope)))
 return uid,org,{'scope_id':scope_id,'scope_version':1,'direction':'固定范围研究','request_key':str(uuid.uuid4())}

def count(table,org):
 with connection() as c:return c.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE org_id=%s').format(sql.Identifier(table)),(org,)).fetchone()['n']

class OwnedPG(unittest.TestCase):
 def test_same_submission_concurrent_and_uuid_case_returns_one_authorization(self):
  uid,org,body=fixture()
  with ThreadPoolExecutor(max_workers=2) as pool:
   out=list(pool.map(lambda b:autonomy.enable(uid,org,b),[body,{**body,'request_key':body['request_key'].upper()}]))
  self.assertEqual(out[0]['id'],out[1]['id']);self.assertEqual(count('quant_research_authorizations',org),1);self.assertEqual(count('quant_research_authorization_events',org),1);self.assertEqual(count('quant_research_planning_triggers',org),1)
 def test_same_key_changed_body_cannot_overwrite_scope_or_direction(self):
  uid,org,body=fixture();saved=autonomy.enable(uid,org,body)
  with self.assertRaises(autonomy.AutonomyError) as exc:autonomy.enable(uid,org,{**body,'direction':'changed'})
  self.assertEqual(exc.exception.code,'submission_conflict');self.assertEqual(autonomy.enable(uid,org,body)['direction'],body['direction']);self.assertEqual(count('quant_research_authorizations',org),1)
 def test_reviewer_and_cross_institution_scope_cannot_enable(self):
  uid,org,body=fixture()
  with self.assertRaises(autonomy.AutonomyError) as reviewer:autonomy.enable(uid+1,org,body)
  self.assertEqual(reviewer.exception.status,403)
  with self.assertRaises(autonomy.AutonomyError) as foreign:autonomy.enable(uid+2,org+1,body)
  self.assertEqual(foreign.exception.code,'scope_changed');self.assertEqual(count('quant_research_authorizations',org),0);self.assertEqual(count('quant_research_authorizations',org+1),0)
 def test_pause_resume_cas_and_replayed_control_are_durable(self):
  uid,org,body=fixture();saved=autonomy.enable(uid,org,body);change={'enabled':False,'expected_version':1,'request_key':str(uuid.uuid4())}
  first=autonomy.control(uid,org,saved['id'],change);again=autonomy.control(uid,org,saved['id'],change);self.assertEqual(first['version'],2);self.assertEqual(again['version'],2);self.assertFalse(first['enabled'])
  with self.assertRaises(autonomy.AutonomyError):autonomy.control(uid,org,saved['id'],{**change,'request_key':str(uuid.uuid4())})
  resumed=autonomy.control(uid,org,saved['id'],{'enabled':True,'expected_version':2,'request_key':str(uuid.uuid4())});self.assertEqual(resumed['version'],3)
  with connection() as c:
   rows=c.execute('SELECT state,count(*) AS n FROM quant_research_planning_triggers WHERE org_id=%s GROUP BY state',(org,)).fetchall()
  self.assertEqual({r['state']:r['n'] for r in rows},{'cancelled':1,'pending':1});self.assertEqual(count('quant_research_authorization_events',org),3)
 def test_revoked_scope_and_membership_do_not_resume_or_reactivate(self):
  uid,org,body=fixture();saved=autonomy.enable(uid,org,body);paused=autonomy.control(uid,org,saved['id'],{'enabled':False,'expected_version':1,'request_key':str(uuid.uuid4())})
  with connection() as c:c.execute('UPDATE quant_research_scope_grants SET enabled=FALSE WHERE id=%s',(body['scope_id'],))
  with self.assertRaises(autonomy.AutonomyError):autonomy.control(uid,org,saved['id'],{'enabled':True,'expected_version':2,'request_key':str(uuid.uuid4())})
  state=autonomy.status(uid,org);self.assertFalse(state['enabled']);self.assertEqual(state['authorization']['version'],2)
  with connection() as c:c.execute("UPDATE inst_members SET role='quant_reviewer' WHERE user_id=%s",(uid,))
  with self.assertRaises(autonomy.AutonomyError) as denied:autonomy.control(uid,org,saved['id'],{'enabled':True,'expected_version':2,'request_key':str(uuid.uuid4())})
  self.assertEqual(denied.exception.status,403)
 def test_failed_trigger_rolls_back_entire_authorization_family_and_audit_transaction(self):
  uid,org,body=fixture()
  with patch.object(autonomy,'_trigger',side_effect=RuntimeError('injected fixture failure')):
   with self.assertRaises(RuntimeError):autonomy.enable(uid,org,body)
  for table in ['quant_research_authorizations','quant_research_evaluation_families','quant_research_authorization_events','quant_research_planning_triggers']:self.assertEqual(count(table,org),0)

result=None
try:
 with patch.object(psycopg,'connect',side_effect=guarded_connect),patch.object(autonomy,'get_conn',side_effect=connection),patch.object(socket.socket,'connect',side_effect=forbidden),patch.object(socket.socket,'connect_ex',side_effect=forbidden):
  result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OwnedPG))
finally:
 before_cleanup=public_fingerprint()
 with connection() as c:
  identity=c.execute('SELECT oid,nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS owned FROM pg_namespace WHERE nspname=%s',(SCHEMA,)).fetchone()
  if not identity or identity['oid']!=SCHEMA_OID or not identity['owned']:raise RuntimeError('fixture schema ownership/OID changed; cleanup refused')
  external=c.execute("SELECT 1 FROM pg_constraint k JOIN pg_class source ON source.oid=k.conrelid JOIN pg_namespace source_ns ON source_ns.oid=source.relnamespace JOIN pg_class target ON target.oid=k.confrelid JOIN pg_namespace target_ns ON target_ns.oid=target.relnamespace WHERE target_ns.nspname=%s AND source_ns.nspname<>%s LIMIT 1",(SCHEMA,SCHEMA)).fetchone()
  views=c.execute("SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON d.classid='pg_rewrite'::regclass AND d.objid=r.oid JOIN pg_class view_rel ON view_rel.oid=r.ev_class JOIN pg_namespace view_ns ON view_ns.oid=view_rel.relnamespace JOIN pg_class target ON d.refclassid='pg_class'::regclass AND d.refobjid=target.oid JOIN pg_namespace target_ns ON target_ns.oid=target.relnamespace WHERE target_ns.nspname=%s AND view_ns.nspname<>%s LIMIT 1",(SCHEMA,SCHEMA)).fetchone()
  if external or views:raise RuntimeError('outside-schema dependency found; CASCADE cleanup refused')
  c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(SCHEMA)))
  assert not c.execute('SELECT oid FROM pg_namespace WHERE nspname=%s',(SCHEMA,)).fetchone()
 after_cleanup=public_fingerprint()
 public_unchanged=PUBLIC_BEFORE==before_cleanup==after_cleanup
 print(json.dumps({'database':'svquant_zxd_dev','fixture_schema':SCHEMA,'fixture_only_sql_applied':True,'public_migration_applied':False,'public_rows_and_constraints_unchanged':public_unchanged,'schema_cleaned':True,'models_or_market_calls':0}))
 if not public_unchanged:raise RuntimeError('public data/constraints changed; stop and review')

raise SystemExit(0 if result and result.wasSuccessful() else 1)
