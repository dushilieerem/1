"""Frozen same-organization report projection. No author-private project/run access."""
from __future__ import annotations
import copy
from services.core.db import get_conn
from .policy import digest,WorkflowError
from .library_reports import number,iso,mapping,PARAMETERS

REQUEST_KEYS=PARAMETERS+('factor_name','factor_code','library_name','library_names','ic_horizons','params',
 'factor_params','universe_asset','benchmark_asset','frozen_data_view')
META_SCALARS=('factor','universe','portfolio_type','rebalance_days','groups','benchmark','filter_limit_up',
 'filter_limit_down','filter_suspended','filter_st','commission_rate','stamp_tax','slippage_rate',
 'execution_timing','execution_version','metric_version','data_release_id','spec_hash','factor_source_hash',
 'actual_end','factor_price_adjustment','factor_price_source','factor_price_precision',
 'return_price_adjustment','return_price_source','return_price_precision')
DEFINITION_KEYS=('forward_return_days','rolling_ir_window','ic_unavailable_reason','ic_metric','return_price',
 'signal_price','execution_timing','signal_lag','ic_method','rank_ic_method','universe','min_cross_section',
 'ic_formula','rank_ic_formula','forward_return_definition','cumulative_ic_definition','rolling_ir_definition',
 'ic_type','rank_ic_type','ic_horizons','ic_std_ddof','signal_lag_days','groups','analysis_level','factor_preprocess',
 'grouping_method','group_order','curve_first_value','group_metric_returns','benchmark_metric_returns',
 'group_annualization','benchmark_annualization','group_volatility_ddof','benchmark_volatility_ddof',
 'group_max_drawdown','relative_metric_returns','relative_annual_excess_return','relative_excess_volatility_ddof',
 'relative_information_ratio','benchmark_win_rate','industry_return_method','industry_grouping_method')


def pick(raw,keys):
 return {k:copy.deepcopy(raw[k]) for k in keys if k in raw}


def scalar_map(value,kind='number'):
 raw=mapping(value)
 if kind=='number':return {str(k):number(v) for k,v in raw.items() if v is None or isinstance(v,(int,float)) and not isinstance(v,bool)}
 return {str(k):v for k,v in raw.items() if isinstance(v,str)}


def entries(raw):return raw if isinstance(raw,list) else []


def points(raw,keys):
 return [pick(r,keys) for r in raw if isinstance(r,dict)] if isinstance(raw,list) else []


def result_projection(raw):
 """Explicit report DTO, excluding signatures, private lineage, arbitrary meta and matrices.
 Numeric metric dictionaries are the public RE schema; series retain their original order/values.
 """
 r=mapping(raw);out=pick(r,('error','final_equity','excess_return'))
 out['metrics']=scalar_map(r.get('metrics'))
 out['date_range']=pick(mapping(r.get('date_range')),('start','end'))
 for key in ('equity_curve','benchmark_curve'):
  if key in r:out[key]=None if r[key] is None else points(r[key],('date','value','drawdown'))
 for key,keys in [('annual_returns',('year','return_value')),('drawdowns',('start','end','depth','peak','trough','recovery','days'))]:
  if key in r:out[key]=points(r[key],keys)
 fa=mapping(r.get('factor_analysis'))
 if 'factor_analysis' in r:
  a=pick(fa,('ic_mean','ic_std','rank_ic_mean'))
  a['layered_returns']=scalar_map(fa.get('layered_returns'))
  a['definition']=pick(mapping(fa.get('definition')),DEFINITION_KEYS)
  for key,keys in [('ic_series',('date','value','sample_size')),('rank_ic_series',('date','value','sample_size')),('cumulative_ic_series',('date','value')),('rolling_ir_series',('date','value','window','sample_size'))]:
   if key in fa:a[key]=points(fa[key],keys)
  if 'cumulative_series' in fa:a['cumulative_series']=[{**pick(x,('date',)),**{k:v for k,v in scalar_map(x).items() if k.startswith('layer') or k=='long_short'}} for x in entries(fa['cumulative_series']) if isinstance(x,dict)]
  if 'quantile_metrics' in fa:a['quantile_metrics']=points(fa['quantile_metrics'],('quantile','annual_return','volatility','sharpe','max_drawdown','annual_excess_return','excess_volatility','information_ratio','benchmark_win_rate','turnover'))
  if 'industry_equity_curves' in fa:a['industry_equity_curves']=[{**pick(x,('industry_code','industry_name')),'points':points(x.get('points'),('date','value'))} for x in entries(fa['industry_equity_curves']) if isinstance(x,dict)]
  if 'industry_group_equity_curves' in fa:a['industry_group_equity_curves']=[{**pick(x,('industry_code','industry_name')),'points':[{**pick(y,('date',)),'groups':scalar_map(y.get('groups'))} for y in entries(x.get('points')) if isinstance(y,dict)]} for x in entries(fa['industry_group_equity_curves']) if isinstance(x,dict)]
  if 'ic_horizons' in fa:a['ic_horizons']={str(k):{**pick(mapping(x),('horizon','ic_mean','ic_std','rank_ic_mean','ic_ir','valid_days','unavailable_reason')),'ic_series':points(mapping(x).get('ic_series'),('date','value','sample_size')),'rank_ic_series':points(mapping(x).get('rank_ic_series'),('date','value','sample_size'))} for k,x in mapping(fa['ic_horizons']).items() if str(k).isdigit()}
  out['factor_analysis']=a if r['factor_analysis'] is not None else None
 meta=mapping(r.get('meta'));m=pick(meta,META_SCALARS)
 for key in ('cost_model','execution_model','filter_status'):m[key]=scalar_map(meta.get(key),'string')
 if isinstance(meta.get('warnings'),list):m['warnings']=[v for v in meta['warnings'] if isinstance(v,str)]
 if isinstance(meta.get('factor_price_fields'),list):m['factor_price_fields']=[v for v in meta['factor_price_fields'] if isinstance(v,str)]
 # Actual data identity is audit evidence; omit local directories/file paths.
 identity=mapping(meta.get('frozen_data_identity'))
 if identity:m['frozen_data_identity']=pick(identity,('view_id','view_manifest_sha256','daily_release','daily_dataset_sha256','identity_hash','schema_version'))
 receipt=mapping(meta.get('controlled_execution'))
 if receipt:m['controlled_execution']=pick(receipt,('version','policy_hash','peak_rss_bytes','elapsed_seconds','limits','child_pid','address_space_semantics','rss_semantics'))
 for key in ('universe_asset','benchmark_asset'):
  if key in meta:m[key]=pick(mapping(meta[key]),('id','version','content_hash','constituent_count','membership_mode','pricing'))
 if 'timings_seconds' in meta:m['timings_seconds']=scalar_map(meta['timings_seconds'])
 out['meta']=m
 return out


def full_report(uid,org,asset_id,phase):
 from .assets import serialize
 if phase not in ('development','sealed'):raise KeyError(phase)
 with get_conn() as c:
  row=c.execute("SELECT archive->'research_asset' AS asset,snapshot_hash,snapshot,evidence FROM quant_factor_candidates WHERE org_id=%s AND archive->>'approved'='true' AND archive->'research_asset'->>'id'=%s",(org,asset_id)).fetchone()
  if not row:raise KeyError(asset_id)
  asset=row['asset'];serialize(asset,org)  # validates registration hash and purpose before reading reports
  if row['snapshot_hash']!=asset['snapshot_hash'] or digest(row['snapshot'])!=asset['snapshot_hash']:raise WorkflowError('原候选与登记时冻结版本不一致')
  dev=mapping(mapping(row.get('evidence')).get('development'))
  if digest(dev.get('result') or {})!=asset['development_result_hash'] or digest(dev.get('novelty') or {})!=asset['novelty_result_hash']:raise WorkflowError('研究报告与登记时的证据指纹不一致')
  sealed=c.execute('SELECT result,report_id FROM quant_factor_sealed_validations WHERE org_id=%s AND candidate_id=%s',(org,asset['candidate_id'])).fetchone()
  frozen_seal=mapping(asset.get('sealed_report'))
  if not sealed or digest(sealed['result'])!=frozen_seal['result_hash'] or sealed['report_id']!=frozen_seal['report_id']:raise WorkflowError('封存报告与登记时的证据指纹不一致')
 if phase=='development':
  raw=dev['result'];request=mapping(asset.get('definition'));request_source='registered_definition'
  report=mapping(asset.get('development_report'));gate=report.get('gate');rid=report.get('report_id');block=dev
 else:
  block=mapping(sealed['result']);raw=mapping(block.get('result'));report=frozen_seal
  request=mapping(mapping(block.get('intent')).get('request'));request_source='sealed_intent'
  if not request:
   request=mapping(mapping(raw.get('meta')).get('spec'));request_source='recorded_spec' if request else 'incomplete_legacy'
  gate=mapping(frozen_seal.get('summary')).get('gate');rid=frozen_seal.get('report_id')
 if not isinstance(raw,dict) or not raw or not rid:raise WorkflowError('登记报告缺少可读取的原始计算结果')
 result=result_projection(raw);safe_request=pick(request,REQUEST_KEYS)
 for key in ('universe_asset','benchmark_asset'):
  if key in safe_request:safe_request[key]=pick(mapping(safe_request[key]),('id','version','content_hash','membership_mode','pricing'))
 # frozen_data_view contains a public view identity, never caller paths or auth tokens.
 if 'frozen_data_view' in safe_request:safe_request['frozen_data_view']=pick(mapping(safe_request['frozen_data_view']),('view_id','view_manifest_sha256','daily_release','daily_dataset_sha256'))
 return {'readonly':True,'phase':phase,'report_id':rid,
  'asset':{'id':asset['id'],'candidate_id':asset.get('candidate_id'),'display_name':asset['display_name'],'version':asset['version'],'kind':asset['kind'],'purpose':'research_only','approved_at':mapping(asset.get('approval')).get('at')},
  'novelty':{'status':'passed' if (mapping(asset.get('novelty_report')).get('gate') or {}).get('passed') is True else 'failed','gate':copy.deepcopy(mapping(asset.get('novelty_report')).get('gate') or {}),'reference_hash':mapping(asset.get('novelty_report')).get('reference_hash')},
  'run':{'id':rid,'factorName':request.get('factor_name') or mapping(asset.get('definition')).get('factor_name') or asset['display_name'],
   'description':asset['display_name'],'request':safe_request,'result':result,'projectId':None,
   'finishedAt':iso((raw if phase=='development' else block).get('finished_at') or (raw if phase=='development' else block).get('completed_at')),
   'elapsedSec':number((raw if phase=='development' else block).get('elapsed_seconds'))},
  'gate':copy.deepcopy(gate),'provenance':{'registration_hash':asset['registration_hash'],
   'source_result_hash':digest(raw),'result_projection_hash':digest(result),'request_source':request_source},
  'back_url':'/quant/factor/library?asset='+asset['id']}
