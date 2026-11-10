"""Authorized only: own18804 -> own18799, original argv/cwd/env. No DDL/cutover/compute."""
from pathlib import Path
import argparse,ast,datetime,json,os,signal,subprocess,time,urllib.request,urllib.error,hashlib,sqlite3,re
root=Path(__file__).resolve().parents[4];proof=Path(__file__).parent
parser=argparse.ArgumentParser();parser.add_argument('--bff-pid',type=int,required=True);parser.add_argument('--re-pid',type=int,required=True);parser.add_argument('--authorized-own-source-reload',action='store_true');args=parser.parse_args()
if not args.authorized_own_source_reload:raise SystemExit('Explicit authorized reload flag required')
out={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'success':False,'no_migrations_or_database_switch':True,'no_research_model_market_or_approval_submit':True,'frontend_and_shared_services_not_restarted':True}
def save():
 (proof/'source-load-evidence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
def process(pid,cwd,tail):
 p=Path('/proc')/str(pid);argv=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x];assert (p/'cwd').resolve()==cwd and argv[1:]==tail,'service identity changed'
 env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\0') if '=' in x);log=(p/'fd/1').resolve();assert root in log.parents and log.suffix=='.log','unexpected log destination'
 return {'pid':pid,'cwd':cwd,'argv':argv,'env':env,'log':log,'ticks':(p/'stat').read_text().rsplit(')',1)[1].split()[19]}
bff=process(args.bff_pid,root,['institutional-workflow/runtime/start_quant_bff.py']);engine=process(args.re_pid,root/'.workspaces/research-engine-r4',['-m','app.main'])
assert bff['env'].get('QUANT_FACTOR_RE_BASE')=='http://127.0.0.1:18804' and bff['env'].get('QUANT_RESEARCH_DURABLE_QUEUE')=='1'
assert engine['env'].get('RE_CONTROLLED_EXECUTION_REQUIRED')=='1' and engine['env'].get('RE_FROZEN_VIEW_HOME')
main_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();re_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=engine['cwd'],text=True).strip()
assert main_commit.startswith('5575aea') and re_commit.startswith('0808218'),'source review baseline changed'
for cwd,paths in ((root,['backend','frontend/src','frontend/tests']),(engine['cwd'],['app','tests'])):
 assert not subprocess.check_output(['git','diff','--name-only','--',*paths],cwd=cwd,text=True).strip(),'uncommitted business changes'
out.update(main_commit=main_commit,re_commit=re_commit,old_bff_pid=args.bff_pid,old_re_pid=args.re_pid,processes={k:{'cwd':str(v['cwd']),'argv':v['argv']} for k,v in [('bff',bff),('private_re',engine)]})
COUNT=next(ast.literal_eval(n.value) for n in ast.parse((root/'institutional-workflow/runtime/verification/codex-factor-cr101-20261110/load-cr101.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COUNT_CODE' for t in n.targets))
def counts():
 env=bff['env'].copy();env.update(PYTHONPATH=str(root/'backend'),SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP='1')
 r=subprocess.run([bff['argv'][0],'-c',COUNT],cwd=root,env=env,capture_output=True,text=True,timeout=20)
 assert r.returncode==0,'read-only activity check failed'
 x=json.loads(r.stdout);assert x['database']=='svquant_dev' and not any(x['counts'].values()) and x['unknown_current_model_calls']==0
 assert all(x[k]==0 for k in ('owned_queue_active','owned_external_unknown','owned_slot_held'))
 assert x['private_re']['activity']=={'queued':0,'running':0} and x['private_re']['required'] and x['private_re']['enabled']
 x['available_memory_bytes']=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert x['available_memory_bytes']>=16*1024**3
 return x
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(url,headers=None,body=None):
 req=urllib.request.Request(url,headers=headers or {},method='POST' if body is not None else 'GET',data=json.dumps(body).encode() if body is not None else None)
 if body is not None:req.add_header('Content-Type','application/json')
 try:
  with opener.open(req,timeout=12) as r:
   raw=r.read();return r.status,json.loads(raw) if raw and ('json' in r.headers.get('Content-Type','')) else None
 except urllib.error.HTTPError as e:
  try:data=json.loads(e.read())
  except Exception:data=None
  return e.code,data

def gentle_reload(original):
 assert process(original['pid'],original['cwd'],original['argv'][1:])['ticks']==original['ticks'],'PID reused'
 os.kill(original['pid'],signal.SIGTERM)
 for _ in range(250):
  try:
   if Path('/proc/'+str(original['pid'])+'/stat').read_text().rsplit(')',1)[1].split()[0]=='Z':break
  except FileNotFoundError:break
  time.sleep(.1)
 else:raise RuntimeError('service did not exit gently; no force kill performed')
 with original['log'].open('ab') as log:new=subprocess.Popen(original['argv'],cwd=original['cwd'],env=original['env'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 return new.pid

def wait_health(port):
 for _ in range(100):
  try:
   status,body=call(f'http://127.0.0.1:{port}/api/health')
   if status==200 and ((port==18804 and body.get('status')=='ok') or (port==18799 and body.get('ok') is True and body.get('db')=='ok')):
    if port==18799:assert body.get('schema',{}).get('ok') is True
    return {'http':status,'ok':body.get('ok'),'status':body.get('status'),'db':body.get('db'),'schema_ok':body.get('schema',{}).get('ok')}
  except (OSError,urllib.error.URLError,TimeoutError,AttributeError):pass
  time.sleep(.25)
 raise RuntimeError('loaded service health was not confirmed')

try:
 out['preload']=counts();save();print('zero in-flight confirmed; gently loading own RE',flush=True)
 out['new_re_pid']=gentle_reload(engine);save();out['re_health']=wait_health(18804);out['after_re_before_bff']=counts();save();print('own RE health confirmed; gently loading own BFF',flush=True)
 out['new_bff_pid']=gentle_reload(bff);save();out['bff_health']=wait_health(18799);out['postload']=counts()
 assert out['postload']['private_re']['frozen_data_view']['enabled'] is True
 out['frontend_http']=call('http://127.0.0.1:19536/quant/factor/library')[0];out['prototype_http']=call('http://127.0.0.1:19536/quant-delivery/v5/factor-factory.html?v=105#library')[0]
 assert out['frontend_http']==200 and out['prototype_http']==200
 # Existing registered development researcher. Login is the only POST and records only login/audit.
 lines=(root/'institutional-workflow/runtime/coordination/dev-test-accounts.md').read_text().splitlines();account=next(cells for line in lines if line.startswith('|') and (cells:=[x.strip().strip('`') for x in line.strip().strip('|').split('|')])[0]=='test')
 code,identity=call('http://127.0.0.1:18799/api/inst/quant/auth/login',body={'username':account[0],'password':account[1]});assert code==200,'registered researcher login failed';headers={'Authorization':'Bearer '+identity['token']};out['http_checks']=[{'check':'registered_login','status':code,'org_id':identity['org']['id'],'permission':identity['permissions']['quant']}]
 code,reference=call('http://127.0.0.1:18799/api/inst/quant/factor-workflow/imports/svquant-existing/reference',headers);assert code==200
 db=root/'.workspaces/research-engine-r4/app/assets/factors/factor_library.db'
 with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
  for fid in ('SV01_0001','SV02_0001','SV11_0001'):
   item=next(x for x in reference['items'] if x['source_factor_id']==fid and x['source_library']=='主因子库')
   actual=c.execute('SELECT factor_code FROM factors WHERE sv_id=?',(fid,)).fetchone()[0]
   status,data=call('http://127.0.0.1:18799/api/inst/quant/factor-workflow/imports/'+item['id']+'/source',headers)
   assert status==200 and data['source_code']==actual and data['source_sha256']==hashlib.sha256(actual.encode()).hexdigest() and data['factor_id']==fid
   out['http_checks'].append({'check':'real_source_equals_deployment_sqlite','factor_id':fid,'status':status,'function_name':data['function_name'],'source_sha256':data['source_sha256'],'source_hash':data['source_hash'],'execution_validated':data['execution_validated']})
   assert call('http://127.0.0.1:18799/api/inst/quant/factor-workflow/imports/'+item['id']+'/source')[0]==401
 out['http_checks'].append({'check':'source_without_login_denied','status':401})
 status,_=call('http://127.0.0.1:18799/api/inst/quant/factor-workflow/imports/does-not-exist/source',headers);assert status==404;out['http_checks'].append({'check':'missing_import_denied','status':status})
 # Read only the minimal foreign import ID, never its owner, source or body.
 env=bff['env'].copy();env.update(PYTHONPATH=str(root/'backend'),SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP='1')
 foreign_code="""import json,psycopg
from psycopg.rows import dict_row
from services.core.db import database_url
with psycopg.connect(database_url(),row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
 row=c.execute('SELECT id FROM quant_factor_imported_factors WHERE org_id<>%s LIMIT 1',(261,)).fetchone()
 print(json.dumps(dict(row) if row else None))
"""
 result=subprocess.run([bff['argv'][0],'-c',foreign_code],cwd=root,env=env,capture_output=True,text=True,timeout=12);assert result.returncode==0;foreign=json.loads(result.stdout)
 if foreign:
  status,_=call('http://127.0.0.1:18799/api/inst/quant/factor-workflow/imports/'+foreign['id']+'/source',headers);assert status==404;out['http_checks'].append({'check':'existing_foreign_org_import_denied','status':status,'foreign_body_read':False})
 else:out['http_checks'].append({'check':'foreign_org_import','result':'no existing foreign fixture; no record created; actual cross-org HTTP not completed'})
 rid='qf_216e30df-21dd-4562-8383-02c414a126da_development';status,data=call('http://127.0.0.1:18799/api/inst/quant/detect/runs/'+rid,headers);assert status==200 and data.get('run',{}).get('id')==rid;out['http_checks'].append({'check':'existing_r4_report_read_only','status':status,'report_id':rid})
 out['final_activity']=counts();out['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();out['success']=True;save();print(json.dumps({'success':True,'main_commit':main_commit,'re_commit':re_commit,'bff_pid':out['new_bff_pid'],'re_pid':out['new_re_pid'],'health':out['bff_health'],'evidence':str(proof/'source-load-evidence.json')},ensure_ascii=False),flush=True)
except BaseException as exc:
 out.update(success=False,error_type=type(exc).__name__,error=str(exc)[:400]);save();print('load stopped; sanitized evidence saved',flush=True);raise
