"""Create exactly the approved empty database and execute captured DDL only.
Usage: python initialize_database.py --create-approved-isolated-database
Existing target always stops; never drop/recreate. No bootstrap/seed/network service.
"""
from db_operator_common import *
import subprocess

def main():
 if sys.argv[1:]!=['--create-approved-isolated-database']:raise RuntimeError('explicit target creation flag required')
 cap=capture()
 # Verify latest already-fetched master still reserves none of the proposed own prefixes.
 names=subprocess.check_output(['git','ls-tree','-r','--name-only','origin/master','backend/migrations'],cwd=ROOT,text=True).splitlines()
 if any(Path(x).name[:4] in ('0042','0043','0044','0045','0046','0047') for x in names):raise RuntimeError('canonical prefix conflict; stop for coordination')
 with connect(SOURCE,readonly=True) as src:
  info=src.execute('SELECT pg_encoding_to_char(encoding) AS encoding,datcollate,datctype FROM pg_database WHERE datname=current_database()').fetchone()
  exists=src.execute('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s) AS yes',(TARGET,)).fetchone()['yes']
  if exists:raise RuntimeError('target already exists; inspect before any write')
  if dict(info)!={'encoding':'UTF8','datcollate':'en_US.utf8','datctype':'en_US.utf8'}:raise RuntimeError('source locale changed')
 with connect('postgres',autocommit=True) as admin:
  admin.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {} LC_COLLATE {} LC_CTYPE {}').format(sql.Identifier(TARGET),sql.Identifier('svquant'),sql.Literal(info['encoding']),sql.Literal(info['datcollate']),sql.Literal(info['datctype'])))
 save('initialization-marker.json',{'status':'created_empty','database':TARGET,'at_utc':now(),'source_read_only':True})
 with connect(TARGET) as dst:
  assert_target(dst)
  if dst.execute("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')").fetchone()['n']:raise RuntimeError('new target unexpectedly nonempty')
  for row in cap['scaffold_statements']:
   if not row['sql'].lstrip().upper().startswith(('CREATE TABLE','CREATE INDEX','CREATE UNIQUE INDEX','ALTER TABLE')):raise RuntimeError('unexpected non-schema scaffold')
   dst.execute(row['sql'])
 from services.core import migrations
 migrations.MIGRATIONS_DIR=HERE/'canonical-migrations'
 migrations.get_conn=lambda:connect(TARGET)
 result=migrations.apply_migrations()
 if not result['ok'] or len(result['applied'])!=43:raise RuntimeError('canonical migration state not complete')
 with connect(TARGET,readonly=True) as dst:
  tables=dst.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema')").fetchall()
  actual={r['table_name'] if r['table_schema']=='public' else r['table_schema']+'.'+r['table_name'] for r in tables}
  if actual!=set(cap['schema_table_allowlist']):raise RuntimeError('unexpected target schema tables')
  for table in sorted(actual-{'schema_migrations'}):assert_empty(dst,table)
  applied=dst.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall()
 save('initialization-evidence.json',{'status':'initialized_empty_not_copied_not_loaded','at_utc':now(),'database':TARGET,'source_read_only':True,'scaffold_statements':len(cap['scaffold_statements']),'tables':sorted(actual),'canonical_applied':applied,'no_bootstrap_seed_or_source_writes':True,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})
 save('initialization-marker.json',{'status':'initialized_empty','database':TARGET,'at_utc':now()})
 print('initialized empty target; canonical=43; source read-only; no service switch')

if __name__=='__main__':
 try:main()
 except Exception as exc:
  safe_failure('initialization-error.json',exc);print('initialization stopped; sanitized evidence written');sys.exit(1)
