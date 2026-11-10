"""Source-only capture; no DB imports/connections, no bootstrap/seed execution."""
import ast,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];PROOF=Path(__file__).parent;BUNDLE=PROOF/'canonical-migrations'
SOURCES=[('services/auth/auth_store.py','ensure_schema'),('services/institution/inst_store.py','ensure_inst_schema'),('services/factor/detect_store.py','ensure_detect_schema'),('services/strategy/strategy_store.py','ensure_strategy_schema'),('ai/runtime/store.py','ensure_ai_usage_schema'),('services/core/audit_log_store.py','ensure_audit_schema'),('services/factor/user_factor_store.py','ensure_user_factors_schema'),('services/factor/user_library_store.py','ensure_user_libraries_schema'),('services/factor/factor_dashboard_metrics_store.py','ensure_factor_dashboard_metrics_schema'),('services/factor/re_factor_catalog.py','ensure_re_factor_catalog_schema')]
BASELINE='9c7ae105b5cd2602165799e7abbc8fe9d77e220f'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def literal(node,env):
 if isinstance(node,ast.Name):return env[node.id]
 if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return literal(node.left,env)+literal(node.right,env)
 return ast.literal_eval(node)
def extract(node,env=None):
 env=env or {};out=[]
 if isinstance(node,ast.For):
  values=literal(node.iter,env)
  for value in values:
   for child in node.body:out.extend(extract(child,{**env,node.target.id:value}))
  return out
 if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='execute':
  text=literal(node.args[0],env)
  if not isinstance(text,str):raise ValueError('nonliteral DDL')
  return [text.strip()]
 for child in ast.iter_child_nodes(node):out.extend(extract(child,env))
 return out

def capture():
 manifest=json.loads((PROOF/'migration-manifest-proposal.json').read_text());items=[];excluded=[];ddl=[]
 for file,function in SOURCES:
  raw=(ROOT/'backend'/file).read_bytes();tree=ast.parse(raw);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
  for statement in extract(fn):
   item={'source':file+':'+function,'sha256':sha(statement.encode()),'sql':statement}
   if re.match(r'^(CREATE TABLE|CREATE INDEX|ALTER TABLE)\b',statement,re.I):ddl.append(statement);items.append(item)
   else:excluded.append(item)
 tree=ast.parse((ROOT/'backend/services/invest/schema.py').read_text());values=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='DDL'))
 for text in values:
  if re.search(r'CREATE TABLE IF NOT EXISTS invest_(stocks|etf)\b',text):ddl.append(text.strip());items.append({'source':'services/invest/schema.py:DDL only stocks/etf','sha256':sha(text.strip().encode()),'sql':text.strip()})
 assert len(excluded)==1 and excluded[0]['sql'].startswith('UPDATE user_library_factors'),'unexpected non-schema capture'
 BUNDLE.mkdir(exist_ok=True);files=[]
 for f in sorted((ROOT/'backend/migrations').glob('*.sql')):
  number=int(f.name[:4])
  if number<=35:name=f.name
  else:
   mapping=next(x for x in manifest['own_six_rename_map'] if Path(x['source_file']).name==f.name);assert sha(f.read_bytes())==mapping['sha256'];name=mapping['target_name']
  raw=f.read_bytes();(BUNDLE/name).write_bytes(raw);files.append({'name':name,'sha256':sha(raw)})
 for entry in manifest['official_files']:
  raw=subprocess.check_output(['git','show',BASELINE+':backend/migrations/'+entry['file']],cwd=ROOT);assert sha(raw)==entry['sha256'];(BUNDLE/entry['file']).write_bytes(raw);files.append({'name':entry['file'],'sha256':sha(raw)})
 assert len(files)==43 and len(list(BUNDLE.glob('*.sql')))==43
 table_names=set();dml=[]
 for statement in ddl:table_names.update(re.findall(r'CREATE TABLE IF NOT EXISTS\s+([\w.]+)',statement,re.I))
 for entry in files:
  text=(BUNDLE/entry['name']).read_text();plain=re.sub(r'--[^\n]*','',text)
  assert not re.search(r'\b(?:DROP DATABASE|CREATE DATABASE|CREATE ROLE|ALTER ROLE|TRUNCATE|dblink|postgres_fdw)\b',plain,re.I),entry['name']
  table_names.update(re.findall(r'CREATE TABLE (?:IF NOT EXISTS )?\s*([\w.]+)',plain,re.I))
  for line in plain.splitlines():
   if re.match(r'\s*(INSERT INTO|UPDATE |DELETE FROM)',line,re.I):dml.append({'file':entry['name'],'line':line.strip()})
 (PROOF/'captured-scaffold.sql').write_text('-- Target svquant_zxd_dev only; captured schema statements, never executed on source.\n'+';\n'.join(ddl)+';\n')
 result={'status':'captured_not_executed','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'scaffold_statements':items,'excluded_non_schema':excluded,'canonical_files':sorted(files,key=lambda x:x['name']),'canonical_dml_review':dml,'schema_table_allowlist':sorted(table_names|{'schema_migrations'}),'no_full_bootstrap_seed_refresh_or_scheduler':True}
 (PROOF/'schema-capture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'scaffold_statements':len(items),'excluded_non_schema':len(excluded),'canonical_files':len(files),'schema_tables':len(table_names),'canonical_dml_review':dml}))
 return result
if __name__=='__main__':capture()
