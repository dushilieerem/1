"""Private bounded synthetic-only Panel/FactorEngine diagnostic subprocess.

This entry point never calls DataEngine.get_instance(), compute(), a model,
backtest runner or a remote service. It supplies synthetic fields explicitly to
compute_from_spec. Resource limits apply only to this new process, not BFF/RE.
"""
from __future__ import annotations
import json,sys,resource,hashlib
from pathlib import Path

def run_fixture(source,entry,scope=None):
 import numpy as np
 import pandas as pd
 root=Path(__file__).resolve().parents[3]
 sys.path.insert(0,str(root/'.workspaces/research-engine-r4'))
 from app.models.data import Panel
 from app.models.factor_backtest import FactorBacktestSpec
 from app.services.factor.engine import FactorEngine
 from app.services.factor import sqlite_loader,loader,runner
 from types import SimpleNamespace
 sqlite_loader.load_factor_tool=lambda:SimpleNamespace()  # Contract disallows tool calls; avoid any external source DB.
 from app.services.data.engine import DataEngine
 def no_real_data(*args,**kwargs):raise AssertionError('synthetic diagnostic must not access real DataEngine')
 DataEngine.get_instance=no_real_data
 def no_database(*args,**kwargs):raise FileNotFoundError('synthetic fixture has no external factor database')
 loader.SQLiteFactorRepository=no_database;runner.SQLiteFactorRepository=no_database
 from services.factor.code_validation import validated_factor_code
 scope=scope or {'mode':'legacy_probe','security_count':8,'scope_hash':None}
 count=scope.get('security_count')
 if type(count) is not int or not 1<=count<=80:raise ValueError('合成诊断范围无效')
 rng=np.random.default_rng(9701);dates=pd.bdate_range('2020-01-01',periods=640,name='date');symbols=['fixture_'+str(i) for i in range(count)]
 close=50+np.cumsum(rng.normal(0,.3,(640,count)),axis=0)
 opening=close*(1+rng.normal(0,.002,(640,count)))
 high=np.maximum(opening,close)*(1+rng.uniform(.001,.02,(640,count)))
 low=np.minimum(opening,close)*(1-rng.uniform(.001,.02,(640,count)))
 volume=rng.uniform(10000,1000000,(640,count));volume[35,2%count]=0;volume[210,5%count]=0
 amount=close*volume;turnover=volume/rng.uniform(100000000,200000000,(640,count))
 arrays={'open':opening,'high':high,'low':low,'close':close,'volume':volume,'amount':amount,'turnover':turnover}
 for name in ('open','high','low','close'):
  for day,symbol in [(95,1),(559,3),(599,6)]:arrays[name][day,symbol%count]=np.nan
 fields={name:pd.DataFrame(values,index=dates,columns=symbols) for name,values in arrays.items()}
 wrapped=validated_factor_code(source,entry);sha=hashlib.sha256(wrapped.encode()).hexdigest()
 from app.schemas.backtest import FactorBacktestRequest
 from app.schemas.factor_novelty import NoveltyRequest
 request=FactorBacktestRequest(factor_name=entry,factor_code=wrapped,start='2020-01-01',end='2020-03-31')
 actual_hash=runner._request_factor_source_hash(request)
 if actual_hash!=sha:raise ValueError('研发/查重请求的实际源码哈希与包装源码不一致')
 NoveltyRequest(candidate=request,references=[{'reference_id':'fixture-reference','factor_name':'fixture_reference','factor_code':'def fixture_reference(self): return self.close.shift(1)'}],expected_data_release_id='synthetic-only',expected_candidate_source_hash=actual_hash,expected_candidate_spec_hash='synthetic-only',min_pairs=3)
 def compute(current):
  spec=FactorBacktestSpec(factor_name=entry,factor_code=wrapped,factor_source_hash=sha,library_names=(),universe=tuple(symbols),start=str(current['close'].index[0].date()),end=str(current['close'].index[-1].date()))
  try:result=FactorEngine().compute_from_spec(spec,Panel(current,symbols=symbols))
  except ValueError as exc:
   if '没有有效数值' in str(exc):raise ValueError('合成诊断覆盖不足或实现未产生有效输出（'+str(len(current['close']))+'行/'+str(count)+'证券）；这不是实际行情不足或研究不成立的结论，请核对诊断范围与公式前提') from None
   raise
  if not result.index.equals(current['close'].index) or not result.columns.equals(current['close'].columns):raise ValueError('实现输出的日期或证券对齐不一致')
  if np.isinf(result.to_numpy(dtype=float)).any():raise ValueError('实现产生无穷值，请明确异常和缺失值处理')
  return result
 full=compute(fields);cutoffs=(560,600)
 for cutoff in cutoffs:
  prefix=compute({k:v.iloc[:cutoff].copy() for k,v in fields.items()})
  changed={k:v.copy() for k,v in fields.items()}
  for name in ('open','high','low','close'):changed[name].iloc[cutoff:]=changed[name].iloc[cutoff:]*3.7+123.0
  changed['volume'].iloc[cutoff:]=changed['volume'].iloc[cutoff:]*2.3
  changed['amount'].iloc[cutoff:]=changed['close'].iloc[cutoff:]*changed['volume'].iloc[cutoff:]
  changed['turnover'].iloc[cutoff:]=changed['turnover'].iloc[cutoff:]*1.7
  perturbed=compute(changed).iloc[:cutoff];baseline=full.iloc[:cutoff]
  for label,result in [('prefix',prefix),('future_perturbation',perturbed)]:
   if not np.array_equal(baseline.isna().to_numpy(),result.isna().to_numpy()) or not np.allclose(baseline.to_numpy(dtype=float),result.to_numpy(dtype=float),rtol=1e-9,atol=1e-12,equal_nan=True):raise ValueError('因果性诊断未通过（'+label+'，截断'+str(cutoff)+'行）：过去输出受到未来数据或全区间统计影响')
 return {'passed':True,'fixture':'synthetic-panel-prefix-v3','diagnostic_scope':scope,'execution_path':'actual isolated RE FactorEngine.compute_from_spec + app.models.data.Panel','rows':640,'columns':count,'cutoff_rows':list(cutoffs),'fixture_properties':['physical_ohlc','independent_positive_volume','amount_price_volume','fractional_turnover','bounded_missing_price','zero_volume'],'checks':['date_and_column_alignment','missing_positions','prefix','future_perturbation'],'rtol':1e-9,'atol':1e-12,'wrapped_source_sha256':sha,'actual_re_source_hash':actual_hash,'actual_re_novelty_schema_accepted':True,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'limitation':'有界合成缺陷检测，不是实际研究绩效或任意程序无前视证明'}

def execution_identity(payload):
 """Pure existing RE DTO/spec identity, no market data or factor computation."""
 root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'.workspaces/research-engine-r4'))
 from app.schemas.backtest import FactorBacktestRequest
 from app.services.factor import runner
 from services.factor.code_validation import validated_factor_code
 request=dict(payload['request']);expected=dict(payload['expected'])
 raw_hash=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 if request.get('factor_code'):
  request['factor_code']=validated_factor_code(request['factor_code'],request['factor_name'])
  if not request.get('library_name') and hashlib.sha256(request['factor_code'].encode()).hexdigest()!=expected['factor_source_hash']:raise ValueError('固定源码与已登记研发结果的身份不一致')
 dto=FactorBacktestRequest.model_validate(request)
 # Expected source is frozen development evidence; actual returned source is checked later.
 runner._request_factor_source_hash=lambda req:expected['factor_source_hash']
 spec=runner._request_spec(dto)
 return {'passed':True,'request_hash':raw_hash,'expected_identity':{'data_release_id':expected['data_release_id'],'factor_source_hash':expected['factor_source_hash'],'spec_hash':spec.identity(data_release_id=expected['data_release_id'])},'identity_method':'actual isolated RE FactorBacktestRequest/_request_spec/identity; expected frozen source; no DataEngine or execution','execution_version':spec.execution_version,'metric_version':spec.metric_version}

def main():
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
 resource.setrlimit(resource.RLIMIT_CPU,(6,8))
 resource.setrlimit(resource.RLIMIT_FSIZE,(1024**2,1024**2));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 try:
  payload=json.loads(sys.stdin.read(100000));result=execution_identity(payload) if payload.get('mode')=='spec_identity' else run_fixture(payload['source'],payload['entry'],payload.get('diagnostic_scope'));result['limits']={'address_space_bytes':2*1024**3,'cpu_soft_seconds':6,'cpu_hard_seconds':8}
  print(json.dumps(result,ensure_ascii=False))
 except Exception as exc:
  print(json.dumps({'passed':False,'error':type(exc).__name__+': '+str(exc)[:1200]},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
