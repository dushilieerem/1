"""Target-only operator helpers. Never log connection info, passwords or row bodies."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib,json,os,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE='svquant_dev'; TARGET='svquant_zxd_dev'; QA=(2527,2973,3033); ORG=261
sys.path.insert(0,str(ROOT/'backend'))
from services.core.env_config import load_env,env
load_env()
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from psycopg.rows import dict_row
from psycopg import sql

def now():return datetime.now(timezone.utc).isoformat()
def save(name,value):
 (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')
def credentials():
 values=conninfo_to_dict(env('DATABASE_URL',''))
 if values.get('dbname')!=SOURCE:raise RuntimeError('operator source must be shared read-only database')
 return values

def connect(name,*,readonly=False,autocommit=False):
 if name not in (SOURCE,TARGET,'postgres'):raise RuntimeError('database outside exact allowlist')
 if name==SOURCE and not readonly:raise RuntimeError('shared writes forbidden')
 opts=credentials();opts['dbname']=name
 opts['options']='-c statement_timeout=15000 -c lock_timeout=3000'+(' -c default_transaction_read_only=on' if readonly else '')
 c=psycopg.connect(make_conninfo(**opts),row_factory=dict_row,autocommit=autocommit)
 row=c.execute("SELECT current_database() AS db,current_user AS actor,current_setting('transaction_read_only') AS ro").fetchone()
 if row['db']!=name or row['actor']!='svquant' or (readonly and row['ro']!='on'):
  c.close();raise RuntimeError('database identity mismatch')
 return c

def capture():
 x=json.loads((HERE/'schema-capture.json').read_text())
 files=sorted((HERE/'canonical-migrations').glob('*.sql'))
 expected={a['name']:a['sha256'] for a in x['canonical_files']}
 if len(files)!=43 or set(expected)!={f.name for f in files}:raise RuntimeError('canonical chain mismatch')
 for f in files:
  if hashlib.sha256(f.read_bytes()).hexdigest()!=expected[f.name]:raise RuntimeError('migration bytes changed')
 for r in x['scaffold_statements']:
  if hashlib.sha256(r['sql'].encode()).hexdigest()!=r['sha256']:raise RuntimeError('scaffold bytes changed')
 return x

def assert_empty(c,table):
 if table not in capture()['schema_table_allowlist']:raise RuntimeError('table outside allowlist')
 schema,name=('public',table) if '.' not in table else table.split('.',1)
 n=c.execute(sql.SQL('SELECT count(*) AS n FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(name))).fetchone()['n']
 if n:raise RuntimeError('target table not empty: '+table)

def assert_target(c):
 if c.execute('SELECT current_database() AS db').fetchone()['db']!=TARGET:raise RuntimeError('write target mismatch')

def safe_failure(name,exc):
 save(name,{'status':'stopped_without_cleanup','at_utc':now(),'exception':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None),'constraint':getattr(getattr(exc,'diag',None),'constraint_name',None),'message':str(exc) if isinstance(exc,RuntimeError) else 'database details omitted; no credentials or row bodies logged'})
