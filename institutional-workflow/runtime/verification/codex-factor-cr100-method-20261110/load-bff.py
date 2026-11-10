"""Explicitly authorised CR100 budget BFF-only reload, preserving original process configuration."""
from pathlib import Path
import sys,os,json,time,signal,subprocess,datetime,urllib.request
root=Path(__file__).resolve().parents[4];pid=int(sys.argv[1]);proof=root/'institutional-workflow/runtime/verification/codex-factor-cr100-method-20261110'
original={}
for item in Path('/proc/'+str(pid)+'/environ').read_bytes().split(b'\0'):
 if b'=' in item:
  k,v=item.split(b'=',1);original[k.decode()]=v.decode()
argv=[x.decode() for x in Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\0') if x];cwd=Path('/proc/'+str(pid)+'/cwd').resolve();log=Path('/proc/'+str(pid)+'/fd/1').resolve()
assert cwd==root and len(argv)==2 and argv[1]=='institutional-workflow/runtime/start_quant_bff.py'
assert root in log.parents and log.suffix=='.log'
assert original.get('QUANT_FACTOR_RE_BASE')=='http://127.0.0.1:18804'
os.environ.update(original);sys.path.insert(0,str(root/'backend'))
from services.quant_factor.re_client import headers
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def read(url,auth=None):
 with opener.open(urllib.request.Request(url,headers=auth or {}),timeout=8) as r:return r.status,json.load(r)
before=subprocess.run([argv[0],str(proof/'preload-readonly.py'),str(pid)],cwd=root,env=original,capture_output=True,text=True);assert before.returncode==0
counts=json.loads(before.stdout);assert not any(counts['counts'].values())
status,cap=read('http://127.0.0.1:18804/api/factor/compute-capabilities',headers());assert status==200 and cap['activity']=={'queued':0,'running':0}
record={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'counts_before':counts,'old_pid':pid,'argv':argv,'cwd':str(cwd),'environment_preserved':True,'private_re_base':'http://127.0.0.1:18804','private_re_activity':cap['activity'],'re_not_restarted':True,'frontend_not_restarted':True}
os.kill(pid,signal.SIGTERM)
for _ in range(150):
 try:
  state=Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1].split()[0]
  if state=='Z':break
 except FileNotFoundError:break
 time.sleep(.1)
else:raise RuntimeError('Original18799 did not exit gracefully; refused force kill or duplicate startup')
with log.open('ab') as stream:new=subprocess.Popen(argv,cwd=cwd,env=original,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
record['new_pid']=new.pid
for _ in range(60):
 try:
  code,health=read('http://127.0.0.1:18799/api/health')
  if code==200 and health.get('ok'):break
 except Exception:pass
 time.sleep(.25)
else:raise RuntimeError('new BFF health not confirmed; inspect original service log')
record['health']={'http_status':code,'ok':health.get('ok'),'db':health.get('db'),'schema_ok':(health.get('schema') or {}).get('ok')}
with opener.open('http://127.0.0.1:19536/quant/factor',timeout=8) as r:record['frontend_http_status']=r.status
_,after=read('http://127.0.0.1:18804/api/factor/compute-capabilities',headers());record['private_re_activity_after']=after['activity'];record['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();record['no_model_backtest_approval_submitted']=True
(proof/'load-evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps(record,ensure_ascii=False))
