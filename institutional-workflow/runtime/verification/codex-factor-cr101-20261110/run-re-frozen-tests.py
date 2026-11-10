from pathlib import Path
import subprocess,os,time,json,signal
root=Path(__file__).resolve().parents[4];repo=root/'.workspaces/research-engine-r4';e=Path(__file__).parent;env=os.environ.copy()
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
args=['/home/dev01/program/anaconda3/envs/researchengine/bin/python','-m','pytest','tests/test_frozen_data_view.py','tests/test_controlled_worker_engine.py','tests/test_controlled_compute.py::test_factor_entry_is_opt_in_and_required_mode_fails_closed','tests/test_controlled_compute.py::test_novelty_entry_is_opt_in_and_required_mode_fails_closed','-q','--basetemp',str(e/'re-fixture-tmp')]
assert root in (e/'re-fixture-tmp').resolve().parents
with (e/'re-frozen-view-tests.log').open('w') as output:
 process=subprocess.Popen(args,cwd=repo,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True);started=time.monotonic();peak=0;stop=None
 while process.poll() is None:
  try:peak=max(peak,int(Path(f'/proc/{process.pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'))
  except OSError:pass
  available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
  if time.monotonic()-started>80:stop='wall_timeout'
  elif peak>3*1024**3:stop='test_rss_stop'
  elif available<16*1024**3:stop='available_memory_stop'
  if stop:os.killpg(process.pid,signal.SIGKILL);break
  time.sleep(.2)
 process.wait(timeout=5)
meta={'exit_code':process.returncode,'elapsed_seconds':round(time.monotonic()-started,3),'peak_rss_bytes':peak,'stop_reason':stop,'args':args}
(e/'re-frozen-view-tests.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta));print((e/'re-frozen-view-tests.log').read_text()[-6000:])
raise SystemExit(process.returncode)
