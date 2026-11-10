"""Task-local component/build runner: owns and bounds only its Node process group."""
import os,sys,time,json,signal,subprocess,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[4]
name=sys.argv[1];limit=int(sys.argv[2]);arguments=sys.argv[3:]
node=shutil.which('node')
if not node:raise SystemExit('Node must be explicitly available on PATH')
log=Path(__file__).with_name(name+'.log');receipt=Path(__file__).with_name(name+'-resources.json')
def rss_tree(pid):
 try:
  status=Path('/proc',str(pid),'status').read_text().splitlines()
  rss=int(next(line.split()[1] for line in status if line.startswith('VmRSS:')))*1024
  children=Path('/proc',str(pid),'task',str(pid),'children').read_text().split()
  return rss+sum(rss_tree(int(child)) for child in children)
 except (OSError,StopIteration):return 0
started=time.monotonic();peak=0;stopped=None
with log.open('w') as handle:
 env=os.environ.copy();env['NODE_OPTIONS']=(env.get('NODE_OPTIONS','')+' --max-old-space-size=2048').strip()
 process=subprocess.Popen([node,'--max-old-space-size=2048',*arguments],cwd=root/'frontend',env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
 while process.poll() is None:
  peak=max(peak,rss_tree(process.pid))
  available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
  if time.monotonic()-started>limit:stopped='wall_timeout'
  elif peak>3*1024**3:stopped='rss_stop_line'
  elif available<16*1024**3:stopped='host_available_stop_line'
  if stopped:
   os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
   break
  time.sleep(.2)
result={'exit_code':process.returncode,'stopped':stopped,'elapsed_seconds':round(time.monotonic()-started,3),'peak_rss_process_tree_bytes':peak,'node_heap_mib':int(next((arg.split('=',1)[1] for arg in reversed(arguments) if arg.startswith('--max-old-space-size=')), '2048')),'single_concurrency':True,'command':[node,'--max-old-space-size=2048',*arguments],'no_real_model_market_or_service_change':True}
receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(1 if stopped else process.returncode)
