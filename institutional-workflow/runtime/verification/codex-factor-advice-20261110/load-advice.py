"""Explicitly authorized BFF-only reload. Never submit a research action."""
from pathlib import Path
import argparse,ast,datetime,json,os,signal,subprocess,time,urllib.request
root=Path(__file__).resolve().parents[4];proof=Path(__file__).parent
parser=argparse.ArgumentParser();parser.add_argument('--bff-pid',type=int,required=True);parser.add_argument('--expected-re-pid',type=int,required=True);parser.add_argument('--authorized-bff-only',action='store_true');args=parser.parse_args()
if not args.authorized_bff_only:raise SystemExit('Explicit authorized BFF-only reload flag required')
record={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'no_model_or_market_submit':True,'old_failure_unchanged':True,'no_online_advice_submitted':True,'source_commit':'6c7a0b67bcde5b573c5a7621ed1df8cc1130914d','no_migrations_or_authorization_changes':True,'re_and_frontend_not_restarted':True}
def save():(proof/'advice-load.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
def process(pid,cwd,tail):
 path=Path('/proc')/str(pid);argv=[v.decode() for v in (path/'cmdline').read_bytes().split(b'\0') if v];assert (path/'cwd').resolve()==cwd and argv[1:]==tail,'unexpected service identity'
 env=dict(x.split('=',1) for x in (path/'environ').read_bytes().decode().split('\0') if '=' in x)
 log=(path/'fd/1').resolve();assert root in log.parents and log.suffix=='.log'
 return {'argv':argv,'env':env,'log':log,'ticks':(path/'stat').read_text().rsplit(')',1)[1].split()[19]}
bff=process(args.bff_pid,root,['institutional-workflow/runtime/start_quant_bff.py']);re=process(args.expected_re_pid,root/'.workspaces/research-engine-r4',['-m','app.main'])
assert bff['env'].get('QUANT_FACTOR_RE_BASE')=='http://127.0.0.1:18804' and bff['env'].get('QUANT_RESEARCH_DURABLE_QUEUE')=='1'
assert re['env'].get('RE_CONTROLLED_EXECUTION_REQUIRED')=='1'
record.update(source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),old_bff_pid=args.bff_pid,unchanged_re_pid=args.expected_re_pid,argv=bff['argv'],cwd=str(root))
code=next(ast.literal_eval(n.value) for n in ast.parse((root/'institutional-workflow/runtime/verification/codex-factor-cr101-20261110/load-cr101.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COUNT_CODE' for t in n.targets))
def counts():
 env=bff['env'].copy();env.update(PYTHONPATH=str(root/'backend'),SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP='1')
 result=subprocess.run([bff['argv'][0],'-c',code],cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
 if result.returncode:raise RuntimeError('Read-only count check failed: '+result.stderr[-800:])
 out=json.loads(result.stdout);assert out['database']=='svquant_dev' and not any(out['counts'].values()) and out['unknown_current_model_calls']==0
 for k in ('owned_queue_active','owned_external_unknown','owned_slot_held'):assert out[k]==0,'queue not idle'
 assert out['private_re']['activity']=={'queued':0,'running':0}
 out['available_memory_bytes']=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
 assert out['available_memory_bytes']>=16*1024**3
 return out
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def health(port):
 with opener.open('http://127.0.0.1:'+str(port)+'/api/health',timeout=5) as response:return response.status,json.load(response)
def advice_contract():
 with opener.open('http://127.0.0.1:18799/openapi.json',timeout=5) as response:schema=json.load(response)
 path='/api/inst/quant/factor-workflow/topics/{topic_id}/research-advice'
 ref=schema['paths'][path]['post']['requestBody']['content']['application/json']['schema']['$ref']
 body=schema['components']['schemas'][ref.rsplit('/',1)[-1]]
 return {'read_only_openapi_http':200,'path':path,'schema_name':ref.rsplit('/',1)[-1],'run_id_schema':body.get('properties',{}).get('run_id'),'run_id_optional':'run_id' not in body.get('required',[]),'required':body.get('required',[]),'additional_properties':body.get('additionalProperties')}
try:
 record['preload']=counts();record['before_input_contract']=advice_contract();save()
 assert process(args.bff_pid,root,bff['argv'][1:])['ticks']==bff['ticks']
 os.kill(args.bff_pid,signal.SIGTERM)
 for _ in range(200):
  try:
   if Path('/proc/'+str(args.bff_pid)+'/stat').read_text().rsplit(')',1)[1].split()[0]=='Z':break
  except FileNotFoundError:break
  time.sleep(.1)
 else:raise RuntimeError('BFF did not exit gently; no force kill')
 with bff['log'].open('ab') as log:new=subprocess.Popen(bff['argv'],cwd=root,env=bff['env'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 record['new_bff_pid']=new.pid;save()
 for _ in range(120):
  try:
   status,body=health(18799)
   if status==200 and body.get('ok') is True and body.get('db')=='ok':break
  except Exception:pass
  time.sleep(.25)
 else:raise RuntimeError('BFF health not confirmed')
 record['bff_health']={'http_status':status,'ok':body['ok'],'db':body['db'],'schema_ok':body.get('schema',{}).get('ok')}
 assert process(args.expected_re_pid,root/'.workspaces/research-engine-r4',re['argv'][1:])['ticks']==re['ticks']
 record['re_health_status'],record['re_health']=health(18804)
 with opener.open('http://127.0.0.1:19536/quant/factor',timeout=5) as response:record['frontend_http_status']=response.status
 record['after_input_contract']=advice_contract()
 assert record['after_input_contract']['run_id_schema'] is not None and record['after_input_contract']['run_id_optional'] and record['after_input_contract']['additional_properties'] is False
 with opener.open('http://127.0.0.1:19536/quant-delivery/v5/factor-factory.html',timeout=5) as response:record['prototype_http_status']=response.status
 record['postload']=counts();record['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();record['success']=True;save()
 print(json.dumps({'success':True,'new_bff_pid':new.pid,'re_pid_unchanged':args.expected_re_pid,'bff_health':record['bff_health'],'source_head':record['source_head'],'evidence':str(proof/'advice-load.json')}))
except BaseException as exc:record.update(success=False,error_type=type(exc).__name__,error=str(exc)[:1200]);save();raise
