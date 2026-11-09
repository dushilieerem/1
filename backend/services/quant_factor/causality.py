"""Single-flight bounded synthetic diagnostic; never an investment backtest."""
from __future__ import annotations
import functools,hashlib,json,os,signal,subprocess,sys,threading
from pathlib import Path
from .source_contract import inspect_source,VERSION
from .source_compat import RE_POLICY_SHA256
_LOCK=threading.Lock()

def diagnose_source(source,entry):
 root=Path(__file__).resolve().parents[3]
 actual=root/'.workspaces/research-engine-r4/app/services/novelty/source.py'
 if not actual.is_file() or hashlib.sha256(actual.read_bytes()).hexdigest()!=RE_POLICY_SHA256:raise ValueError('当前隔离计算服务的源码支持版本无法核对，请先确认实现契约')
 return _diagnose_cached(source,entry,RE_POLICY_SHA256)

def _run_worker(payload):
 root=Path(__file__).resolve().parents[3]
 if not _LOCK.acquire(blocking=False):raise ValueError('实现或规格检查正在执行，请稍后重试；未发起真实计算')
 try:
  env=os.environ.copy();temporary=root/'institutional-workflow/runtime/causality-tmp';temporary.mkdir(parents=True,exist_ok=True);env['TMPDIR']=str(temporary)
  for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
  process=subprocess.Popen([sys.executable,'-m','services.quant_factor.causality_worker'],cwd=root/'backend',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
  try:out,err=process.communicate(json.dumps(payload,ensure_ascii=False),timeout=15)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGKILL);process.communicate();raise ValueError('实现或规格检查超过15秒已终止，仅结束本次独立检查进程，未发起真实研究') from None
  try:result=json.loads(out)
  except ValueError:raise ValueError('独立检查未能完成，退出状态 '+str(process.returncode)+'；请核对代码和计算依赖') from None
  if process.returncode or result.get('passed') is not True:raise ValueError('检查未通过：'+str(result.get('error') or '无法确认'))
  return result
 finally:_LOCK.release()

@functools.lru_cache(maxsize=64)
def _diagnose_cached(source,entry,policy_sha256):
 contract=inspect_source(source,entry);result=_run_worker({'source':source,'entry':entry})
 if result.get('wrapped_source_sha256')!=contract['wrapped_source_sha256']:raise ValueError('实现检查与执行包装后的源码身份不一致')
 return {'contract':contract,'diagnostic':result,'contract_version':VERSION}
