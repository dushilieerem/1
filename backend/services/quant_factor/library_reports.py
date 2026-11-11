"""UX106 read-only catalogue reports: public scalar history and only one's own runs.
No migration, cache lookup, report computation, or write-capable catalogue helper.
"""
from __future__ import annotations
import math
import re
import base64
import json
from datetime import datetime
from urllib.parse import quote
from services.core.db import get_conn
from .policy import digest
from .library_source import SourceLookupError

METRIC_UNITS={**dict.fromkeys(('rank_ic','ic_mean','ic_std'),'correlation'),
 **dict.fromkeys(('annual_return','max_drawdown','turnover','q1_turnover','q5_turnover',
 'q1_return','q5_return','long_short_spread','win_rate','volatility'),'ratio'),
 **dict.fromkeys(('sharpe','ir'),'number'),**dict.fromkeys(('coverage_pool','coverage_total'),'reported_coverage')}
PERCENT_POINTS={k for k,v in METRIC_UNITS.items() if v in ('correlation','ratio')}
PARAMETERS=('universe','universe_snapshot','benchmark','start','end','period','portfolio_type','rebalance_days',
 'execution_timing','filter_limit_up','filter_limit_down','filter_suspended','filter_st','groups',
 'commission_rate','stamp_tax','slippage_rate','analysis_level')
VERSION_KEYS=('factor_source_hash','spec_hash','data_release_id','execution_version','metric_version')


def number(value):
 if isinstance(value,bool) or not isinstance(value,(int,float)):return None
 return value if math.isfinite(value) else None


def iso(value):
 return value.isoformat() if hasattr(value,'isoformat') else value if isinstance(value,str) and value else None


def mapping(value):return value if isinstance(value,dict) else {}


def flag(value):
 return bool(value) if isinstance(value,(int,bool)) and value in (0,1) else None


def summary(row):
 raw={k:number(row.get(k)) for k in METRIC_UNITS}
 known=row.get('rules_version')=='yg_v1'
 units={k:('percent_points' if k in PERCENT_POINTS else v) if known else 'unknown' for k,v in METRIC_UNITS.items()}
 key={k:row.get(k) for k in ('library','factor_name','universe','period','filter_limit_up','filter_suspended','rules_version')}
 key['computed_at']=iso(row.get('computed_at'))
 metrics={k:((v/100 if k in PERCENT_POINTS and v is not None else v) if known else None) for k,v in raw.items()}
 invalid=[k for k in ('rank_ic','ic_mean') if metrics[k] is not None and not -1<=metrics[k]<=1]
 for k in invalid:metrics[k]=None
 notes=[str(v) for v in (row.get('error'),row.get('ic_unavailable_reason')) if v]
 if not known:notes.append('历史指标口径尚未核对；原值保留在来源详情中')
 if invalid:notes.append('相关指标超出有效范围，已保留原值供核对')
 return {'id':'history_'+digest(key),'kind':'platform_history_summary','status':'failed' if row.get('error') else 'saved',
  'computed_at':key['computed_at'],'parameters':{'universe':row.get('universe'),'lookback_period':row.get('period'),
   'filter_limit_up':flag(row.get('filter_limit_up')),'filter_suspended':flag(row.get('filter_suspended'))},
  'date_range':None,'metrics':metrics,
  'metric_units':dict(METRIC_UNITS),'missing_sections':['equity_curve','benchmark_curve','ic_series'],
  'calculation_note':'；'.join(notes) or None,
  'provenance':{'source':'platform_metric_store','rules_version':row.get('rules_version'),'source_metrics':raw,
   'source_metric_units':units,'factor_source_hash':None,'data_release_id':None}}


def matches(request,library,factor_id):
 # A saved local/custom override or ambiguous multi-library request isn't this catalogue definition.
 req=mapping(request)
 if req.get('factor_name') not in (None,'',factor_id) or req.get('factor_code') not in (None,''):return False
 candidates=[]
 for key in ('library_name','library_names'):
  value=req.get(key)
  if value in (None,'',[]):continue
  if isinstance(value,str):values=[value]
  elif isinstance(value,list) and len(value)==1 and isinstance(value[0],str):values=value
  else:return False
  candidates.extend(values)
 return bool(candidates) and all(value==library for value in candidates)


def saved_report(row):
 # row contains only SQL-projected list metadata, never a result body or series.
 req=mapping(row.get('parameters'));actual=mapping(row.get('actual_date_range'));rid=str(row['id'])
 return {'id':rid,'kind':'member_saved_report','label':str(row.get('description') or row.get('factor_name') or '已保存报告'),
  'report_url':'/quant/factor/report/'+quote(rid,safe=''),'status':'failed' if row.get('result_error') else 'saved',
  'finished_at':iso(row.get('finished_at')),'elapsed_seconds':number(row.get('elapsed_sec')),
  'actual_date_range':{k:actual[k] for k in ('start','end') if actual.get(k)} or None,
  'parameters':req,'version':{k:row.get(k) for k in VERSION_KEYS},
  'sections':{k:bool(row.get('has_'+k)) for k in ('equity_curve','benchmark_curve','ic_series','rank_ic_series')},
  'server_verified':row.get('server_verified') is True}


def _cursor(value,scope):
 if not value:return None
 try:
  if len(value)>2048:raise ValueError()
  data=json.loads(base64.urlsafe_b64decode(value+'='*(-len(value)%4)))
  if set(data)!= {'at','id','scope'} or data['scope']!=scope or not isinstance(data['id'],str) or not 0<len(data['id'])<=200:raise ValueError()
  if data['at'] is not None:datetime.fromisoformat(data['at'].replace('Z','+00:00'))
  return data
 except Exception:raise SourceLookupError(400,'invalid_cursor','报告列表位置已失效，请重新打开') from None


def _next_cursor(row,scope):
 return base64.urlsafe_b64encode(json.dumps({'at':iso(row.get('finished_at')),'id':row['id'],'scope':scope},separators=(',',':')).encode()).decode().rstrip('=')


def _runs(c,uid,factor_id,library,cursor,limit):
 # Identity filtering happens BEFORE LIMIT/keyset pagination, including both
 # library aliases; an explicit conflicting alias or code override is rejected.
 optional="COALESCE(request->'{key}','null'::jsonb) IN ('null'::jsonb,'\"\"'::jsonb,'[]'::jsonb)"
 clauses=[];args=[uid,factor_id]
 for key in ('library_name','library_names'):
  clauses.append('('+optional.format(key=key)+f" OR request->>'{key}'=%s OR request->'{key}'=jsonb_build_array(%s::text))")
  args.extend((library,library))
 clauses.append("(request->>'library_name'=%s OR request->'library_name'=jsonb_build_array(%s::text) OR request->>'library_names'=%s OR request->'library_names'=jsonb_build_array(%s::text))")
 args.extend((library,library,library,library))
 clauses.append("COALESCE(request->>'factor_code','')=''")
 clauses.append("COALESCE(request->>'factor_name','') IN ('',%s)");args.append(factor_id)
 if cursor:
  clauses.append("(COALESCE(finished_at,'-infinity'::timestamptz),id)<(COALESCE(%s::timestamptz,'-infinity'::timestamptz),%s)")
  args.extend((cursor['at'],cursor['id']))
 args.append(limit+1)
 params=','.join("'"+k+"',request->'"+k+"'" for k in PARAMETERS)
 versions=','.join("result->'meta'->>'"+k+"' AS "+k for k in VERSION_KEYS)
 def has(path):return "CASE WHEN jsonb_typeof("+path+")='array' THEN jsonb_array_length("+path+")>0 ELSE false END"
 flags=','.join(has("result->'"+k+"'")+" AS has_"+k for k in ('equity_curve','benchmark_curve'))+','+','.join(has("result->'factor_analysis'->'"+k+"'")+" AS has_"+k for k in ('ic_series','rank_ic_series'))
 sql="""SELECT id,factor_name,description,finished_at,elapsed_sec,
  jsonb_build_object("""+params+""") AS parameters,result->'date_range' AS actual_date_range,
  result->>'error' AS result_error,(result->'_svquant_verified'='true'::jsonb) AS server_verified,
  """+versions+','+flags+" FROM detect_runs WHERE user_id=%s AND factor_name=%s AND "+' AND '.join(clauses)+" ORDER BY finished_at DESC NULLS LAST,id DESC LIMIT %s"
 return c.execute(sql,tuple(args)).fetchall()


def imported_reports(uid,org,imported_id,private_reports_allowed=True,cursor=None,limit=50):
 scope=digest({'uid':uid,'org':org,'imported_id':imported_id});position=_cursor(cursor,scope)
 if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=50:raise SourceLookupError(400,'invalid_limit','每页报告数量不正确')
 history_limit=100
 try:
  with get_conn() as c:
   row=c.execute('SELECT id,source_library,source_factor_id,factor_name,display_name,category FROM quant_factor_imported_factors WHERE id=%s AND org_id=%s',(imported_id,org)).fetchone()
   if not row:raise SourceLookupError(404,'factor_not_found','因子不存在或无权访问')
   library=row['source_library'];factor_id=row['source_factor_id']
   if not library or library in ('custom_lib','user_lib') or not re.fullmatch(r'SV[0-9]{2}_[0-9]+',str(factor_id)):raise SourceLookupError(404,'factor_not_found','这份目录缺少可核对的来源身份')
   history=c.execute('SELECT * FROM factor_dashboard_metrics WHERE library=%s AND factor_name=%s ORDER BY computed_at DESC,universe,period,filter_limit_up,filter_suspended,rules_version LIMIT %s',(library,factor_id,history_limit+1)).fetchall()
   runs=_runs(c,uid,factor_id,library,position,limit) if private_reports_allowed else []
 except SourceLookupError:raise
 except Exception:raise SourceLookupError(503,'reports_unavailable','报告暂不可读，请稍后重试') from None
 page=runs[:limit]
 return {'factor':{'imported_id':row['id'],'library_name':library,'factor_id':factor_id,
   'display_name':row.get('display_name') or row.get('factor_name') or factor_id,'category':row.get('category')},
  'history_summaries':[summary(dict(r)) for r in history[:history_limit]],
  'history_page':{'limit':history_limit,'has_more':len(history)>history_limit},
  'saved_reports':[saved_report(dict(r)) for r in page],
  'saved_reports_page':{'limit':limit,'has_more':len(runs)>limit,'next_cursor':_next_cursor(page[-1],scope) if len(runs)>limit else None},
  'private_reports_allowed':bool(private_reports_allowed)}
