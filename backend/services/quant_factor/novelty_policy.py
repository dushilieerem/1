"""Product gates only. Factor-value computation belongs to ResearchEngine."""
from .policy import WorkflowError,number

DEFAULTS={'maxAbsCorrelation':.8,'minDays':60,'minPairs':30,'minCoverage':.8}

def policy(plan):
    kind=plan.get('researchPurpose','legacy')
    if kind not in ('discovery','replication','legacy'):raise WorkflowError('请选择新因子挖掘或已有因子复现。')
    if kind!='discovery':return {'researchPurpose':kind}
    raw=plan.get('noveltyPolicy') or {}
    out={k:number(raw.get(k),k,*limits) for k,limits in {'maxAbsCorrelation':(0,.9999),'minDays':(2,10000),'minPairs':(3,10000),'minCoverage':(.1,1)}.items()}
    for k in ('minDays','minPairs'):
        if out[k]!=int(out[k]):raise WorkflowError(k+'必须为整数')
    if raw.get('scope')!='all_accessible':raise WorkflowError('新因子检验必须明确完整可访问因子库范围。')
    return {'researchPurpose':kind,'scope':'all_accessible',**out}

def evaluate_comparison(result,rules,expected_release,expected_source):
    """Normalized adapter input. Missing/partial facts are never a green gate."""
    meta=result.get('meta') or {}
    if not expected_release or meta.get('data_release_id')!=expected_release:raise WorkflowError('去重检验的数据版本与研发结果不一致。')
    if not expected_source or meta.get('candidate_source_hash')!=expected_source:raise WorkflowError('去重检验的候选源码指纹不一致。')
    if not meta.get('spec_hash'):raise WorkflowError('去重检验缺少计算规格指纹。')
    rows=result.get('comparisons') or [];expected=result.get('expected_count')
    if isinstance(expected,bool) or not isinstance(expected,int) or expected<1:raise WorkflowError('没有明确的因子库比较清单，不能认定去重通过。')
    ids=[r.get('reference_id') for r in rows]
    complete=len(rows)==expected and all(ids) and len(set(ids))==expected
    failed=[];compared=[]
    for r in rows:
        if r.get('status')!='succeeded':failed.append(r.get('reference_id'));continue
        try:
            rho=number(r.get('mean_abs_spearman'),'绝对相关均值',0,1)
            days=number(r.get('valid_days'),'有效相关天数',0,100000)
            pairs=number(r.get('min_pairs'),'有效配对数',0,100000)
            coverage=number(r.get('coverage'),'共同样本覆盖率',0,1)
        except WorkflowError:failed.append(r.get('reference_id'));continue
        if days!=int(days) or pairs!=int(pairs) or days<rules['minDays'] or pairs<rules['minPairs'] or coverage<rules['minCoverage']:
            failed.append(r.get('reference_id'));continue
        compared.append({**r,'mean_abs_spearman':rho})
    complete=complete and not failed and len(compared)==expected
    closest=max(compared,key=lambda r:r['mean_abs_spearman']) if compared else None
    max_rho=closest['mean_abs_spearman'] if closest else None
    return {'status':'failed' if max_rho is not None and max_rho>rules['maxAbsCorrelation'] else 'passed' if complete else 'incomplete',
            'passed':bool(complete and max_rho<=rules['maxAbsCorrelation']),'complete':complete,
            'expected_count':expected,'compared_count':len(compared),'failed_references':failed,
            'max_abs_correlation':max_rho,'closest':closest,'threshold':rules['maxAbsCorrelation'],
            'residual':result.get('residual',{'status':'not_supported'}),
            'limitation':'仅说明本次指定范围内的因子值差异；不证明全球首创，也不等同于组合增量收益。'}

def handoff_allowed(candidate):
    plan=candidate.get('snapshot',{}).get('plan',{})
    if plan.get('researchPurpose')!='discovery':return False
    n=candidate.get('evidence',{}).get('development',{}).get('novelty',{})
    return n.get('gate',{}).get('passed') is True and n.get('gate',{}).get('complete') is True
