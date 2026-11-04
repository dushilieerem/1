"""Isolated server development stack; access workspace through SSH forwarding."""
import argparse,json,os,signal,subprocess,sys,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
PROJECT=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('WORKFLOW_HOME',str(PROJECT/'institutional-workflow'))).resolve()
RUNTIME=ROOT/'runtime'
PORTS={'data':18766,'compute':18798,'workspace':18796}
def health():
 result={}
 for name,port in PORTS.items():
  try:
   with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/'+('api/health' if name=='workspace' else 'health'),timeout=2) as r:result[name]=json.load(r)
  except Exception:result[name]=None
 return result
def run(name):
 import uvicorn
 if name=='data':
  sys.path.insert(0,str(ROOT/'sunvalley-data'))
  from sunvalley_data.market.pipeline import MarketService
  from fastapi import FastAPI
  from fastapi.responses import JSONResponse
  service=MarketService(RUNTIME/'data');app=FastAPI()
  @app.get('/health')
  def check():return {'service':'workflow-published-snapshot','ok':True,'read_only':True}
  @app.get('/state')
  def state():return service.state()
  @app.post('/query')
  def query(body:dict):
   try:return service.query(body)
   except (ValueError,KeyError,TypeError) as e:return JSONResponse({'detail':str(e)},400)
 elif name=='workspace':
  sys.path.insert(0,str(PROJECT/'backend'))
  from services.workflow_workspace.server import create_app
  key_path=RUNTIME/'secrets'/'model-key'
  key=key_path.read_text().strip() if key_path.is_file() else ''
  app=create_app(RUNTIME/'workspace',PROJECT/'frontend/institutional-workflow/web','http://127.0.0.1:18798',18796,key)
 else:
  sys.path.insert(0,str(ROOT/'research-engine-git'))
  from app.services.workflow_tools.server import create_app
  app=create_app('http://127.0.0.1:18766',RUNTIME/'compute-cache')
 uvicorn.run(app,host='127.0.0.1',port=PORTS[name],log_level='warning')
def supervise():
 import fcntl
 lock=(RUNTIME/'supervisor.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 children=[];logs=[];stop=RUNTIME/'stop-request'
 def halt(*args):stop.touch()
 signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
 try:
  for name in PORTS:
   log=(RUNTIME/(name+'.log')).open('ab');logs.append(log)
   children.append(subprocess.Popen([sys.executable,str(PROJECT/'scripts/workflow_stack.py'),name],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log))
  while not stop.exists():
   state={'pid':os.getpid(),'heartbeat':time.time(),'children':[p.pid for p in children]}
   temp=RUNTIME/'supervisor.tmp';temp.write_text(json.dumps(state));temp.replace(RUNTIME/'supervisor.json')
   if any(p.poll() is not None for p in children):raise RuntimeError('A service exited; inspect runtime logs')
   time.sleep(1)
 finally:
  for p in children:
   if p.poll() is None:p.terminate()
  for p in children:
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for log in logs:log.close()
  lock.close()
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=[*PORTS,'start','status','stop','supervise']);a=parser.parse_args();RUNTIME.mkdir(exist_ok=True)
 if a.action in PORTS:run(a.action)
 elif a.action=='supervise':supervise()
 elif a.action=='status':print(json.dumps(health(),ensure_ascii=False))
 elif a.action=='stop':(RUNTIME/'stop-request').touch()
 else:
  if any(health().values()):raise SystemExit('Service already running; inspect status before starting')
  (RUNTIME/'stop-request').unlink(missing_ok=True)
  with (RUNTIME/'supervisor.log').open('ab') as log:subprocess.Popen([sys.executable,str(PROJECT/'scripts/workflow_stack.py'),'supervise'],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
  print('Start requested; use status to verify')
