from __future__ import annotations
import hashlib
import json
import math
from datetime import date
from services.factor.code_validation import validated_factor_code

class WorkflowError(ValueError):
    pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def number(value, name, low, high):
    if isinstance(value,bool): raise WorkflowError(name+'必须是数值')
    try: v=float(value)
    except (ValueError,TypeError): raise WorkflowError(name+'必须是数值') from None
    if not math.isfinite(v) or not low<=v<=high: raise WorkflowError(name+'超出有效范围')
    return v

def snapshot(project):
    c=project['config']; p=c.get('researchPlan') or {}
    if not p.get('revision') or not str(p.get('hypothesis','')).strip() or not str(p.get('acceptance','')).strip():
        raise WorkflowError('请先保存研究假设和筛选条件')
    dates=[]
    for k in ('developmentStart','developmentEnd','validationStart','validationEnd'):
        try: dates.append(date.fromisoformat(p[k]))
        except (ValueError,TypeError,KeyError): raise WorkflowError('请设置有效研发/验证日期') from None
    if not dates[0]<=dates[1]<dates[2]<=dates[3]: raise WorkflowError('研发与验证区间必须按时间分离，不能重叠')
    trials=number(p.get('maxTrials'), '尝试预算',1,1000)
    if trials!=int(trials): raise WorkflowError('尝试预算必须是整数')
    rules=p.get('rules') or {}
    rules={'minSignedIc':number(rules.get('minSignedIc'),'最低方向IC',0,1),
           'maxDrawdown':number(rules.get('maxDrawdown'),'最大回撤',0,1),
           'minObservations':number(rules.get('minObservations'),'最少IC观测数',2,10000),
           'direction':rules.get('direction')}
    if rules['direction'] not in ('positive','negative'): raise WorkflowError('请选择预设因子方向')
    if rules['minObservations']!=int(rules['minObservations']): raise WorkflowError('观测数必须为整数')
    codes=c.get('factorCodes') or []
    if len(codes)!=1: raise WorkflowError('冻结验证当前支持单因子；请在工程计算中保存单因子实现')
    name=codes[0]; draft=c.get('draftFactor') or {}
    request={'factor_name':name,'universe':c.get('universe') or 'CSI300','benchmark':c.get('benchmark') or 'CSI300',
             'portfolio_type':c.get('portfolioType') or 'long_only','groups':c.get('groups',5),
             'rebalance_days':c.get('rebalanceDays',5),'execution_timing':c.get('executionTiming') or 'next_close',
             'analysis_level':'full','commission_rate':c.get('commissionRate',.0003),
             'stamp_tax':c.get('stampTax',.0005),'slippage_rate':c.get('slippageRate',.0005),
             **{b:c.get(a,False) for a,b in [('filterSuspended','filter_suspended'),('filterSt','filter_st'),('filterLimitUp','filter_limit_up'),('filterLimitDown','filter_limit_down')]}}
    if request['execution_timing']=='same_close': raise WorkflowError('固定验证不允许收盘同刻成交，请使用次日成交')
    for k in ('commission_rate','stamp_tax','slippage_rate'): request[k]=number(request[k],k,0,.1)
    if draft.get('name')==name and draft.get('body'):
        try: validated_factor_code(draft['body'],name)
        except ValueError as exc: raise WorkflowError(str(exc)) from exc
        request['factor_code']=draft['body']
    else:
        library=(c.get('factorLibraries') or {}).get(name)
        if not library: raise WorkflowError('缺少因子实现或明确的来源库')
        request['library_name']=library
    return {'schema':1,'projectId':project['id'],'name':project['name'],'plan':p,'rules':rules,'request':request}

def evaluate(result, rules):
    if result.get('error'): raise WorkflowError('计算返回错误：'+str(result['error']))
    metrics=result.get('metrics') or {}; fa=result.get('factor_analysis') or {}; meta=result.get('meta') or {}
    if not all(meta.get(k) for k in ('data_release_id','spec_hash','factor_source_hash')):
        raise WorkflowError('计算结果缺少数据版本、计算规格或源码指纹')
    ic=number(metrics.get('ic',fa.get('ic_mean')),'IC',-1,1)
    drawdown=abs(number(metrics.get('max_drawdown'),'回撤',-1,1))
    series=fa.get('ic_series') or []
    observations=0
    for item in series:
        v=item.get('value',item.get('ic')) if isinstance(item,dict) else None
        if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v): observations+=1
    signed=ic*(1 if rules['direction']=='positive' else -1)
    checks=[{'name':'方向IC','actual':signed,'operator':'>=','threshold':rules['minSignedIc'],'passed':signed>=rules['minSignedIc']},
            {'name':'最大回撤','actual':drawdown,'operator':'<=','threshold':rules['maxDrawdown'],'passed':drawdown<=rules['maxDrawdown']},
            {'name':'有效IC观测数','actual':observations,'operator':'>=','threshold':rules['minObservations'],'passed':observations>=rules['minObservations']}]
    return {'passed':all(x['passed'] for x in checks),'checks':checks,'sealed':False,
            'limitation':'样本外复验；当前数据权限未封存，不构成独立封存验证或投资准入。'}

def compare_identity(development,validation):
    for key in ('data_release_id','factor_source_hash'):
        if not development['meta'].get(key) or development['meta'][key]!=validation['meta'].get(key):
            raise WorkflowError('复验期间'+key+'变化，结果不能与冻结候选合并；请重新研究')
