"""Explicitly authorized own-deployment migration/activation/reload. No research submit."""
from pathlib import Path
import argparse,os,sys,json,subprocess,datetime,time,signal,urllib.request
root=Path(__file__).resolve().parents[4];proof=Path(__file__).parent;private=root/'.workspaces/research-engine-r4'
p=argparse.ArgumentParser();p.add_argument('--bff-pid',type=int,required=True);p.add_argument('--re-pid',type=int,required=True);p.add_argument('--frozen-view-home',type=Path,required=True);p.add_argument('--actor-user',type=int,required=True);p.add_argument('--authorization',required=True);p.add_argument('--apply-and-load-authorized',action='store_true');args=p.parse_args()
if not args.apply_and_load_authorized:raise SystemExit('Explicit authorized loading flag required')
record={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'no_model_market_or_review_submit':True,'frontend_not_restarted':True,'shared_services_not_modified':True}
def save():
 (proof/'load-evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
def process(pid,cwd,expected_tail):
 path=Path('/proc')/str(pid);argv=[v.decode() for v in (path/'cmdline').read_bytes().split(b'\0') if v];actual=(path/'cwd').resolve()
 assert actual==cwd and argv[1:]==expected_tail,'unexpected process identity'
 values=dict(item.split('=',1) for item in (path/'environ').read_bytes().decode().split('\0') if '=' in item)
 log=(path/'fd/1').resolve();assert root in log.parents and log.suffix=='.log','log outside own checkout'
 return {'pid':pid,'argv':argv,'cwd':cwd,'env':values,'log':log,'start':(path/'stat').read_text().rsplit(')',1)[1].split()[19]}
def brief(item):return {'pid':item['pid'],'argv':item['argv'],'cwd':str(item['cwd']),'log':str(item['log']),'process_start_ticks':item['start']}
bff=process(args.bff_pid,root,['institutional-workflow/runtime/start_quant_bff.py']);engine=process(args.re_pid,private,['-m','app.main'])
assert bff['env'].get('QUANT_FACTOR_RE_BASE')=='http://127.0.0.1:18804'
assert engine['env'].get('RE_CONTROLLED_EXECUTION_REQUIRED')=='1'
home=args.frozen_view_home.resolve();assert home.is_dir()
authorization=(root/args.authorization).resolve();assert root in authorization.parents
record['startup_map']={'bff':brief(bff),'private_re':brief(engine),'new_private_flags':{'RE_CONTROLLED_EXECUTION_REQUIRED':'1','RE_FROZEN_VIEW_HOME':str(home)},'bff_launcher_flags':{'QUANT_RESEARCH_DURABLE_QUEUE':'1','SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP':'1'},'migration_order':['0039_quant_research_token_policy','0040_quant_research_queue','0041_quant_model_capacity']}
record['source']={'svquant_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'research_engine_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=private,text=True).strip()}
(proof/'startup-map.json').write_text(json.dumps(record['startup_map'],ensure_ascii=False,indent=2));save()

def backend(code):
 env=bff['env'].copy();env['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';env['PYTHONPATH']=str(root/'backend')
 result=subprocess.run([bff['argv'][0],'-c',code],cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
 if result.returncode:raise RuntimeError('Owned backend check failed: '+result.stderr[-1500:])
 return json.loads(result.stdout)

COUNT_CODE="""import json,os
from contextlib import closing
import psycopg
from psycopg.rows import dict_row
from services.core.db import database_url
from services.quant_factor.research_queue import DEPLOYMENT_ID
from services.quant_factor.re_client import headers
import urllib.request
out={'counts':{}}
with psycopg.connect(database_url(),row_factory=dict_row,connect_timeout=5,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
 out['database']=c.execute('SELECT current_database() AS name').fetchone()['name'];assert out['database']=='svquant_dev'
 for key,table,clause in [('f0','quant_factor_f0_runs',"status IN ('queued','running')"),('candidates','quant_factor_candidates',"status LIKE '%_running'"),('sealed','quant_factor_sealed_validations',"status IN ('queued','running')"),('agent_jobs','quant_factor_agent_jobs',"status IN ('queued','running')"),('iterations','quant_factor_iterations',"status IN ('queued','running')")]:out['counts'][key]=c.execute('SELECT COUNT(*) n FROM '+table+' WHERE '+clause).fetchone()['n']
 out['unknown_current_model_calls']=c.execute("SELECT COUNT(*) n FROM quant_ai_budget_calls WHERE org_id=261 AND status IN ('dispatched','unresolved') AND response IS NULL").fetchone()['n']
 table=c.execute("SELECT to_regclass('quant_research_queue_jobs') AS name").fetchone()['name'];out['owned_queue_installed']=bool(table)
 if table:
  out['owned_queue_active']=c.execute("SELECT COUNT(*) n FROM quant_research_queue_jobs WHERE deployment_id=%s AND status IN ('queued','running')",(DEPLOYMENT_ID,)).fetchone()['n']
  out['owned_external_unknown']=c.execute("SELECT COUNT(*) n FROM quant_research_queue_jobs j CROSS JOIN LATERAL jsonb_array_elements(j.external_calls) x WHERE deployment_id=%s AND COALESCE(x->>'status','') NOT IN ('succeeded','failed','cancelled')",(DEPLOYMENT_ID,)).fetchone()['n']
  out['owned_slot_rows']=c.execute('SELECT COUNT(*) n FROM quant_research_queue_slots WHERE deployment_id=%s',(DEPLOYMENT_ID,)).fetchone()['n']
  out['owned_slot_held']=c.execute('SELECT COUNT(*) n FROM quant_research_queue_slots WHERE deployment_id=%s AND root_id IS NOT NULL',(DEPLOYMENT_ID,)).fetchone()['n']
 out['installed_cr101_migrations']=[row['version'] for row in c.execute("SELECT version FROM schema_migrations WHERE version IN ('0039_quant_research_token_policy','0040_quant_research_queue','0041_quant_model_capacity') ORDER BY version").fetchall()]
open_=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with open_.open(urllib.request.Request('http://127.0.0.1:18804/api/factor/compute-capabilities',headers=headers()),timeout=8) as response:
 cap=json.load(response);out['private_re']={'http_status':response.status,'activity':cap['activity'],'required':cap['required'],'enabled':cap['enabled'],'method_code_hash':cap['method_code_hash'],'frozen_data_view':cap.get('frozen_data_view')}
print(json.dumps(out))
"""
def check_zero():
 out=backend(COUNT_CODE);available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024;out['available_memory_bytes']=available
 assert not any(out['counts'].values()) and out['unknown_current_model_calls']==0,'research/model work in flight'
 for key in ('owned_queue_active','owned_external_unknown','owned_slot_held'):assert out.get(key,0)==0,'owned queue is not empty'
 assert out['private_re']['activity']=={'queued':0,'running':0},'private RE in flight'
 assert available>=16*1024**3,'available memory below stop line'
 return out

def read(url):
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(url,timeout=5) as response:return response.status,json.load(response)

def reload_one(item,env):
 check=process(item['pid'],item['cwd'],item['argv'][1:]);assert check['start']==item['start'],'PID reused'
 os.kill(item['pid'],signal.SIGTERM)
 for _ in range(200):
  try:
   if Path('/proc/'+str(item['pid'])+'/stat').read_text().rsplit(')',1)[1].split()[0]=='Z':break
  except FileNotFoundError:break
  time.sleep(.1)
 else:raise RuntimeError('Own service did not exit gently; no force kill/duplicate start')
 with item['log'].open('ab') as stream:new=subprocess.Popen(item['argv'],cwd=item['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
 return new

try:
 record['preload']=check_zero();save()
 migration_code="""import json
from services.core import migrations
from services.quant_factor import token_policy,model_budget
allowed=['0039_quant_research_token_policy','0040_quant_research_queue','0041_quant_model_capacity']
state=migrations.status();pending=state.get('pending') or []
assert all(row['version'] in allowed and not row.get('changed') for row in pending),'unrelated or changed migration'
applied=migrations.apply_migrations();assert applied['ok']
path=AUTHORIZATION
first=token_policy.install(261,ACTOR,path);again=token_policy.install(261,ACTOR,path);assert first['id']==again['id']
status=model_budget.status(ACTOR,261);assert status['token_limit_mode']=='unlimited' and status['execution_ready'] and status['cumulative_token_limit'] is None
print(json.dumps({'applied':[version for version in allowed if version not in state['applied'] and version in applied['applied']],'authorization':{'id':first['id'],'mode':first['mode'],'org_id':first['org_id'],'idempotent':True,'supersedes_grant_id':first['supersedes_grant_id']},'budget_status':status}))
""".replace('AUTHORIZATION',repr(str(authorization))).replace('ACTOR',str(args.actor_user))
 record['migration_activation']=backend(migration_code);save()
 record['before_re_reload']=check_zero();save()
 new_env=engine['env'].copy();new_env['RE_FROZEN_VIEW_HOME']=str(home)
 new_re=reload_one(engine,new_env);record['new_re_pid']=new_re.pid;save()
 for _ in range(120):
  try:
   code,health=read('http://127.0.0.1:18804/api/health')
   if code==200 and health.get('status')=='ok':break
  except Exception:pass
  time.sleep(.25)
 else:raise RuntimeError('new private RE health not confirmed')
 record['private_re_health']={'http_status':code,'body':health};record['after_re_before_bff']=check_zero()
 assert record['after_re_before_bff']['private_re']['frozen_data_view']['enabled'] is True
 save()
 bff_env=bff['env'].copy();bff_env['QUANT_RESEARCH_DURABLE_QUEUE']='1';bff_env['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1'
 new_bff=reload_one(bff,bff_env);record['new_bff_pid']=new_bff.pid;save()
 for _ in range(120):
  try:
   code,health=read('http://127.0.0.1:18799/api/health')
   if code==200 and health.get('ok') is True and health.get('db') in ('ok','healthy'):break
  except Exception:pass
  time.sleep(.25)
 else:raise RuntimeError('new BFF ok/db health not confirmed')
 record['bff_health']={'http_status':code,'ok':health.get('ok'),'db':health.get('db'),'schema_ok':(health.get('schema') or {}).get('ok')}
 runtime_env=dict(item.split('=',1) for item in Path('/proc/'+str(new_bff.pid)+'/environ').read_bytes().decode().split('\0') if '=' in item)
 # /proc/environ may reflect exec-time values only; verify effective queue through
 # actual module startup and service-owned dispatcher DB/readiness separately.
 assert runtime_env.get('QUANT_RESEARCH_DURABLE_QUEUE')=='1'
 record['bff_queue_flag']={'configured_in_launcher':True,'exec_environment_value':runtime_env.get('QUANT_RESEARCH_DURABLE_QUEUE'),'effective_startup_requires_queue':True}
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:19536/quant/factor',timeout=8) as response:record['frontend_http_status']=response.status
 record['final_preflight']=backend("""import json
from services.core.db import get_conn
from services.quant_factor import locked_data,resources
with get_conn() as c:row=c.execute('SELECT t.*,p.config FROM quant_factor_topics t JOIN detect_projects p ON p.id=t.project_id AND p.user_id=t.user_id WHERE t.project_id=%s AND t.org_id=261',('0cf7441a-94e9-4690-94f6-0396f8836346',)).fetchone()
assert row is not None
fixed=locked_data.for_topic(dict(row));request=locked_data.bind(resources.scope_request(row['config']),fixed)
receipt=resources.preflight('factor',request);assert receipt['allowed']
novelty=resources.preflight('novelty',{'candidate':request,'references':[{}]*334});assert not novelty['allowed']
print(json.dumps({'project_id':row['project_id'],'factor_preflight':receipt,'reject_334':{'allowed':novelty['allowed'],'reasons':novelty['reasons']},'actual_market_bytes_verified':False,'no_compute_submitted':True}))
""")
 record['postload_counts']=check_zero();assert record['postload_counts']['owned_slot_rows']==1
 record['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();record['success']=True;save();print(json.dumps({'success':True,'source':record['source'],'new_re_pid':new_re.pid,'new_bff_pid':new_bff.pid,'bff_health':record['bff_health'],'private_re_health':record['private_re_health'],'preflight_allowed':record['final_preflight']['factor_preflight']['allowed'],'evidence':str(proof/'load-evidence.json')},ensure_ascii=False))
except BaseException as exc:
 record.update(success=False,error_type=type(exc).__name__,error=str(exc)[:1500]);save();raise
