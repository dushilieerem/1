"""Deterministic development facts. Sealed evidence is never traversed."""
import math,copy
from .research_contract import fingerprint
VERSION='quant.development-diagnosis.v1'

def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def describe(candidate,trial,current_k,threshold):
 report=(candidate.get('evidence') or {}).get('development') or {};saved=report.get('gate') or {};snapshot=candidate['snapshot'];rules=snapshot['rules']
 report_id=report.get('report_id')
 if not report_id or trial.get('report_id')!=report_id:raise ValueError('所选E与研发报告不一致，不能用另一版本解释')
 if not isinstance(current_k,int) or isinstance(current_k,bool) or current_k<0:raise ValueError('当前K未确认')
 metric=rules.get('icMetric','ic')
 if metric not in ('ic','rank_ic'):raise ValueError('IC口径未确认')
 series_key='rank_ic_series' if metric=='rank_ic' else 'ic_series'
 analysis=(report.get('result') or {}).get('factor_analysis') or {};series=analysis.get(series_key)
 series_known=isinstance(series,list);points=[]
 if series_known:
  for item in series:
   if isinstance(item,dict):
    value=item.get('value',item.get('ic'))
    if finite(value):points.append((str(item.get('date') or ''),float(value)))
  points.sort(key=lambda item:item[0])
 temporal=bool(points) and all(len(date)==10 and date[4:5]=='-' and date[7:8]=='-' for date,_ in points) and len({date for date,_ in points})==len(points)
 sign=1 if rules['direction']=='positive' else -1
 def summary(values):
  return {'valid_observations':len(values),'signed_mean':sign*sum(v for _,v in values)/len(values) if values else None,'start':values[0][0] if values else None,'end':values[-1][0] if values else None}
 checks=[{key:check.get(key) for key in ('name','actual','operator','threshold','passed','reason')} for check in saved.get('checks') or []]
 historical_k=saved.get('k_used',saved.get('k',trial.get('k_at_report')))
 if not isinstance(historical_k,int) or isinstance(historical_k,bool):historical_k=None
 historic_threshold=next((check['threshold'] for check in checks if check['name']=='方向 NW t' and finite(check.get('threshold'))),None)
 facts={'schema':VERSION,'evaluation_stage':'development','metric_type':metric,'candidate_id':candidate['id'],'snapshot_hash':candidate.get('snapshot_hash'),'report_id':report_id,'trial_no':trial.get('trial_no'),'branch_id':trial.get('branch_id'),'historical_k':historical_k,'historical_k_source':'saved_gate' if isinstance(saved.get('k_used',saved.get('k')),int) else 'derived_counted_topic_prefix' if historical_k is not None else 'unknown','historical_threshold':historic_threshold,'current_k':current_k,'current_threshold':threshold(max(current_k,1)),'next_new_trial_k':current_k+1,'next_new_trial_threshold':threshold(current_k+1),'historical_gate':{'passed':saved.get('passed'),'numerical_passed':saved.get('numerical_passed'),'checks':checks},'series':{'source':series_key,'state':'available' if series_known else 'missing','summary':summary(points) if series_known else None,'temporal_order_confirmed':temporal,'first_half':summary(points[:len(points)//2]) if temporal else None,'second_half':summary(points[len(points)//2:]) if temporal else None},'novelty_status':(report.get('novelty') or {}).get('status','unknown'),'limitations':['仅研发结果，不包含封存数值；描述性分段不是新增门槛']}
 return {'facts':facts,'facts_hash':fingerprint(facts)}


def read(uid,org,candidate_id):
 """Read-only adapter for an authorized frozen development report, including legacy."""
 from . import store,ledger
 from .metrics import threshold
 candidate=store.read(uid,org,candidate_id)
 topics=ledger.list_topics(uid,org,candidate['project_id'])
 if len(topics)!=1:raise ValueError('研发诊断需要明确的任务台账，未猜测其他任务证据')
 topic=topics[0];trials=ledger._trials(uid,org,topic['id'])
 report=((candidate.get('evidence') or {}).get('development') or {}).get('report_id')
 trial=next((t for t in trials if t.get('report_id')==report),None)
 if not trial:raise ValueError('研发报告尚无对应台账，未用其他E的结果解释')
 historical_k=ledger.current_k([t for t in trials if t['trial_no']<=trial['trial_no']],topic['primary_holding_period'])
 return attach_parent(uid,org,candidate,describe(candidate,{**trial,'k_at_report':historical_k},ledger.current_k(trials,topic['primary_holding_period']),threshold))


def parent_comparison(candidate,parent):
 """Descriptive comparison of the explicitly selected frozen parent, no new test."""
 import difflib
 from .research_contract import fingerprint
 request=candidate['snapshot']['request'];old_request=parent['snapshot']['request']
 def conditions(snapshot):
  return {'request':{k:v for k,v in snapshot['request'].items() if k not in ('factor_code','factor_name')},'rules':snapshot['rules'],
   'contract':snapshot['plan'].get('researchContract'),'development':[snapshot['plan'].get('developmentStart'),snapshot['plan'].get('developmentEnd')]}
 same=fingerprint(conditions(candidate['snapshot']))==fingerprint(conditions(parent['snapshot']))
 source=request.get('factor_code','');old=old_request.get('factor_code','')
 new_gate=((candidate.get('evidence') or {}).get('development') or {}).get('gate') or {};old_gate=((parent.get('evidence') or {}).get('development') or {}).get('gate') or {}
 old_checks={c['name']:c for c in old_gate.get('checks') or []}
 deltas=[]
 if same:
  for check in new_gate.get('checks') or []:
   previous=old_checks.get(check['name'],{});actual=check.get('actual');before=previous.get('actual')
   deltas.append({'name':check['name'],'parent_actual':before,'actual':actual,'change':actual-before if finite(actual) and finite(before) else None})
 diff=''.join(difflib.unified_diff(old.splitlines(True),source.splitlines(True),fromfile='selected_parent',tofile='candidate',n=2))
 return {'parent_candidate_id':parent['id'],'parent_report_id':((parent.get('evidence') or {}).get('development') or {}).get('report_id'),
  'same_execution_conditions':same,'source_changed':source!=old,'source_diff':diff[:1800],'source_diff_truncated':len(diff)>1800,'gate_changes':deltas,
  'limitation':'描述性研发差异，不是额外市场检验；不同固定条件不计算指标差值'}


def attach_parent(uid,org,candidate,diagnosis):
 from . import store
 bound=(candidate.get('snapshot',{}).get('plan',{}).get('researchProposal') or {}).get('binding') or {}
 facts=copy.deepcopy(diagnosis['facts'])
 if not bound.get('parent_candidate_id'):facts['parent_comparison']={'state':'not_recorded','reason':'本版本无已记录的冻结父试验，未猜测来源'}
 else:
  parent=store.read(uid,org,bound['parent_candidate_id'])
  if parent['project_id']!=candidate['project_id'] or parent['snapshot_hash']!=bound.get('parent_snapshot_hash'):raise ValueError('诊断父版本与已选提案不一致')
  facts['parent_comparison']=parent_comparison(candidate,parent)
 return {'facts':facts,'facts_hash':fingerprint(facts)}
