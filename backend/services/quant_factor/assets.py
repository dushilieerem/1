"""CR-095 institution research admission and immutable, permission-scoped assets.

This registry reuses candidate.archive. It does not publish to a personal,
community or official library and never upgrades historical research feedback.
"""
from __future__ import annotations
import copy
from contextlib import nullcontext
from datetime import datetime, timezone
from services.core.db import get_conn
from services.factor.detect_store import _row_project
from . import ledger, store
from .policy import WorkflowError, digest, snapshot, evaluate, compare_identity
from .metrics import threshold, default_lags
from .novelty_policy import DEFAULTS, evaluate_comparison, policy

SCHEMA='quant.research-asset.v1'
PURPOSE='research_admission'
CATEGORIES=('动量因子','技术复合因子','区间与通道因子','反转因子','日内结构因子','流动性因子','资金流与量能因子','量价关系因子','估值因子','规模因子','Beta因子','波动率因子','风险分布因子','待分类')


def context(c,row):
    uid,org,project=row['user_id'],row['org_id'],row['project_id']
    topic=c.execute('SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,project)).fetchone()
    if not topic:raise WorkflowError('候选缺少固定任务与试验台账')
    project_row=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s',(uid,project)).fetchone()
    trials=[dict(t) for t in c.execute('SELECT * FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no',(uid,org,topic['id'])).fetchall()]
    sealed=c.execute('SELECT * FROM quant_factor_sealed_validations WHERE user_id=%s AND org_id=%s AND candidate_id=%s',(uid,org,row['id'])).fetchone()
    running=c.execute("SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND status LIKE '%%_running'",(uid,org,project)).fetchone()['n']
    unrecorded=c.execute("""SELECT COUNT(*) AS n FROM quant_factor_candidates q
        WHERE q.user_id=%s AND q.org_id=%s AND q.project_id=%s
          AND q.evidence->'development'->'result' IS NOT NULL
          AND q.evidence->'development'->'result' NOT IN ('null'::jsonb,'{}'::jsonb)
          AND NOT EXISTS (SELECT 1 FROM quant_factor_trials t WHERE t.user_id=q.user_id AND t.org_id=q.org_id
             AND t.project_id=q.project_id AND t.report_id='qf_'||q.id||'_development')""",(uid,org,project)).fetchone()['n']
    dispatch=c.execute("SELECT COUNT(*) AS n FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND status IN ('queued','running')",(uid,org,topic['id'])).fetchone()['n']
    return {'topic':dict(topic),'current_hash':digest(snapshot(_row_project(dict(project_row)))) if project_row else None,
            'trials':trials,'sealed':dict(sealed) if sealed else None,'inflight':int(running)+int(dispatch),'dispatch_inflight':int(dispatch),'unrecorded_metrics':int(unrecorded)}


def validate_evidence(row,facts):
    snap=row.get('snapshot') or {};evidence=row.get('evidence') or {}
    if not row.get('snapshot_hash') or digest(snap)!=row['snapshot_hash']:raise WorkflowError('冻结候选内容与版本指纹不一致')
    if facts.get('current_hash')!=row['snapshot_hash']:raise WorkflowError('当前研究输入已改变，不能批准旧版本')
    if facts.get('unrecorded_metrics'):raise WorkflowError('任务中已有数值结果尚未完整落账，请先恢复台账再审批')
    if facts.get('inflight'):raise WorkflowError('任务仍有在途研究或检验，停止并核对固定版本后再审批')
    if row.get('status')!='development_passed':raise WorkflowError('候选未完成研发检验')
    topic=facts['topic'];sealed=facts.get('sealed') or {}
    if not topic.get('policy_version'):raise WorkflowError('缺少固定政策版本')
    if sealed.get('status')!='passed':raise WorkflowError('独立封存验证尚未通过，不能批准研究用途')
    if sealed.get('snapshot_hash')!=row['snapshot_hash'] or sealed.get('topic_id')!=topic['id']:raise WorkflowError('封存证据与候选/任务版本不一致')
    for key in ('view_id','contract_revision','view_manifest_sha256'):
        if topic.get(key) and sealed.get(key)!=topic[key]:raise WorkflowError('封存数据身份与任务固定版本不一致')
    method=evidence.get('method') or {}
    if not all(method.get(k) for k in ('method_id','method_version','contract_version','code_revision','config_digest')) or method.get('config_digest')!=row['snapshot_hash']:
        raise WorkflowError('缺少本次固定研究方法版本记录，历史证据不能补造方法身份')
    execution=method.get('execution_config') or {}
    if execution.get('snapshot_hash')!=row['snapshot_hash'] or method.get('execution_config_digest')!=digest(execution):raise WorkflowError('固定执行配置身份不完整或不一致')
    dev=evidence.get('development') or {};dev_result=dev.get('result') or {}
    if snap.get('request',{}).get('factor_code'):
        from .source_contract import inspect_source,VERSION
        actual=inspect_source(snap['request']['factor_code'],snap['request']['factor_name'])
        checked=evidence.get('source_contract') or {};diagnostic=checked.get('diagnostic') or {}
        if checked.get('contract_version')!=VERSION or checked.get('contract')!=actual or diagnostic.get('passed') is not True or diagnostic.get('wrapped_source_sha256')!=actual['wrapped_source_sha256'] or dev_result.get('meta',{}).get('factor_source_hash')!=actual['wrapped_source_sha256']:
            raise WorkflowError('缺少与实际执行源码一致的因果性与计算契约检查，历史结果不能补造批准')
    if not dev.get('report_id') or not dev.get('run_id'):raise WorkflowError('缺少可追溯的研发报告与运行标识')
    if not any(t.get('report_id')==dev['report_id'] for t in facts['trials']):raise WorkflowError('研发结果尚未完整落入任务台账')
    k=ledger.current_k(facts['trials'],topic['primary_holding_period'])
    if k<1 or k>topic['max_trials']:raise WorkflowError('任务试验计数缺失或超出授权预算，不能批准')
    dev_gate=evaluate(dev_result,snap['rules'],k)
    if not dev_gate['passed']:raise WorkflowError('按任务当前 K 重新核验，研发硬门槛未达标')
    sealed_data=sealed.get('result') or {};sealed_result=sealed_data.get('result') or {}
    if not sealed.get('report_id') or not sealed_data.get('run_id'):raise WorkflowError('封存报告身份不完整')
    compare_identity(dev_result,sealed_result)
    observations=next((c['actual'] for c in dev_gate['checks'] if c['name']=='有效IC观测数'),0)
    sealed_gate=evaluate(sealed_result,snap['rules'],k,lags=default_lags(int(observations)))
    if not sealed_gate['passed']:raise WorkflowError('独立验证的实际数值门槛未达标')
    kind=snap.get('plan',{}).get('researchPurpose')
    if (snap.get('rules') or {}).get('acceptanceMode')=='flow_test':
        # Isolated UI flow test: gates are real, but novelty/library-admission
        # evidence is intentionally out of scope. Registration is blocked later.
        return {'k':k,'threshold':threshold(k,(snap.get('rules') or {}).get('alpha',0.05)),
                'development_gate':dev_gate,'sealed_gate':sealed_gate,
                'novelty_gate':{'passed':True,'complete':True,'flow_test':True,'limitation':'流程测试不执行查重'},
                'topic':topic,'sealed':sealed,'method':method,'kind':kind,'flow_test':True,
                'limitation':'流程测试，不可入库，不作研究结论'}
    n=dev.get('novelty') or {};refs=evidence.get('library_reference') or {};ng=n.get('gate') or {}
    if snap.get('plan',{}).get('diagnostic') or n.get('diagnostic') or refs.get('diagnostic') or n.get('reference_scope')=='diagnostic':
        raise WorkflowError('小范围诊断不能替代完整准入证据')
    count=refs.get('count')
    if not isinstance(count,int) or count<1 or n.get('reference_hash')!=refs.get('hash') or n.get('reference_count')!=count or ng.get('expected_count')!=count:
        raise WorkflowError('查重报告与完整固定对照清单不一致')
    kind=snap.get('plan',{}).get('researchPurpose')
    rules=policy(snap['plan']) if kind=='discovery' else {**DEFAULTS,'researchPurpose':kind}
    from .novelty import comparison_request,validate_result
    comparison={'meta':n.get('meta') or {},'comparisons':n.get('comparisons') or [],'expected_count':count}
    validate_result(comparison,comparison_request(snap,dev_result,refs,rules),dev_result)
    actual=evaluate_comparison(comparison,rules,dev_result.get('meta',{}).get('data_release_id'),dev_result.get('meta',{}).get('factor_source_hash'))
    if not actual['complete']:raise WorkflowError('缺少完整、有效的实际查重结果与范围')
    if kind=='discovery' and not actual['passed']:raise WorkflowError('新发现未通过正式重复性门槛')
    if kind=='replication':
        req=snap.get('request') or {}
        if not req.get('library_name') or req.get('factor_code'):raise WorkflowError('复现记录缺少明确的既有因子身份，或实现已改变')
    elif kind!='discovery':raise WorkflowError('历史研究类型未明确，不能自动升级为机构资产')
    return {'k':k,'threshold':threshold(k,(snap.get('rules') or {}).get('alpha',0.05)),'development_gate':dev_gate,'sealed_gate':sealed_gate,'novelty_gate':actual,'topic':topic,'sealed':sealed,'method':method,'kind':kind}


def eligibility(row,c=None,for_submission=False):
    with nullcontext(c) if c is not None else get_conn() as connection:
        facts=context(connection,row)
        if for_submission:facts['inflight']-=facts.get('dispatch_inflight',0)
        return validate_evidence(row,facts)


def _report(block,gate):
    result=block.get('result') or {};meta=result.get('meta') or {};metrics=result.get('metrics') or {}
    return {'report_id':block.get('report_id'),'run_id':block.get('run_id'),'gate':copy.deepcopy(gate),
            'metrics':{k:metrics[k] for k in ('rank_ic','ic','max_drawdown','sharpe','annual_return','turnover') if k in metrics},
            'meta':{k:meta[k] for k in ('data_release_id','spec_hash','factor_source_hash') if k in meta}}


def approve(uid,org,cid,note,metadata,acknowledged):
    if not acknowledged:raise WorkflowError('请确认已查看全部试验、封存结果和局限')
    if not note.strip():raise WorkflowError('请填写批准依据')
    category=str(metadata.get('category') or '')
    tags=metadata.get('tags') or []
    name=str(metadata.get('display_name') or '').strip()
    if category not in CATEGORIES or not name or len(name)>100:raise WorkflowError('请确认资产名称与业务分类')
    if not isinstance(tags,list) or len(tags)>12 or any(not isinstance(t,str) or not t.strip() or len(t)>40 for t in tags):raise WorkflowError('标签格式无效')
    with get_conn() as c:
        # Global order: actor advisory -> topic advisory -> project -> candidate.
        # The first read only resolves identity; all facts are re-read under locks.
        identity=c.execute('SELECT user_id,project_id FROM quant_factor_candidates WHERE id=%s AND org_id=%s',(cid,org)).fetchone()
        if not identity:raise KeyError(cid)
        c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,identity['user_id']))
        topic=c.execute('SELECT id FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(identity['user_id'],org,identity['project_id'])).fetchone()
        if not topic:raise WorkflowError('候选缺少任务台账')
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f"quant-factor-start:{identity['user_id']}:{org}:{topic['id']}",))
        c.execute('SELECT id FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(identity['user_id'],identity['project_id']))
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s FOR UPDATE',(cid,org)).fetchone()
        from .review import ensure_reviewer,ensure_assigned
        ensure_reviewer(row,uid);row=dict(row);card=dict(row.get('archive') or {});rev=dict(card.get('review') or {})
        ensure_assigned(rev,uid)
        if card.get('research_asset'):
            if rev.get('decision')!='approve_research_and_register':raise WorkflowError('登记与审批记录不一致')
            return detail(uid,org,card['research_asset']['id'],full=True,c=c)
        if rev.get('purpose')!=PURPOSE:raise WorkflowError('此事项不是研究资产审批；旧反馈和封存失败复盘不能升级为批准')
        if rev.get('status')!='requested':raise WorkflowError('此版本已有决定，不能覆盖')
        facts=eligibility(row,c)
        if facts.get('flow_test'):raise WorkflowError('流程测试候选不可登记入库；该候选仅用于验证审批流程')
        now=datetime.now(timezone.utc).isoformat();snap=row['snapshot'];dev=row['evidence']['development'];seal=facts['sealed']
        asset={'schema':SCHEMA,'id':('qfa_' if facts['kind']=='discovery' else 'qfr_')+cid,
               'org_id':org,'candidate_id':cid,'snapshot_hash':row['snapshot_hash'],'version':1,
               'kind':'novel_factor' if facts['kind']=='discovery' else 'replication_validation',
               'display_name':name,'hypothesis':snap['plan']['hypothesis'],'definition':copy.deepcopy(snap['request']),
               'source_hash':dev['result']['meta']['factor_source_hash'],'method':copy.deepcopy(facts['method']),
               'topic_id':facts['topic']['id'],'policy_version':facts['topic']['policy_version'],
               'data':{k:(facts['topic'][k].isoformat() if hasattr(facts['topic'].get(k),'isoformat') else copy.deepcopy(facts['topic'].get(k))) for k in ('view_id','release_ids','view_manifest_sha256','contract_revision','as_of','development_start','development_end','validation_start','validation_end','primary_holding_period')},
               'k':facts['k'],'threshold':facts['threshold'],'rules':copy.deepcopy(snap['rules']),
               'category':category,'tags':list(dict.fromkeys(t.strip() for t in tags)),
               'classification_source':{'kind':'reviewer_confirmed','actor_id':uid,'at':now},
               'approval':{'reviewer_id':uid,'at':now,'note':note.strip()},'purpose':'research_only',
               **({'flow_test':True} if (row['snapshot'].get('rules') or {}).get('acceptanceMode')=='flow_test' else {}),
               'development_result_hash':digest(dev['result']),'novelty_result_hash':digest(dev['novelty']),
               'development_report':_report(dev,facts['development_gate']),
               'sealed_report':{'report_id':seal['report_id'],'run_id':seal['result']['run_id'],'passed':True,'result_hash':digest(seal['result']),'summary':_report({**seal['result'],'report_id':seal['report_id']},facts['sealed_gate'])},
               'novelty_report':{'reference_hash':dev['novelty']['reference_hash'],'gate':facts['novelty_gate'],
                                  'meta':copy.deepcopy(dev['novelty'].get('meta') or {})}}
        asset['registration_hash']=digest(asset)
        rev.update(status='reviewed',decision='approve_research_and_register',note=note.strip(),reviewer_id=uid,reviewed_at=now)
        card.update(review=rev,approved=True,research_asset=asset)
        c.execute('UPDATE quant_factor_candidates SET archive=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND org_id=%s',
                  (store.encode(card),store.encode([{'at':now,'action':'research_asset_registered','asset_id':asset['id'],'reviewer_id':uid,'snapshot_hash':row['snapshot_hash'],'purpose':'research_only'}]),cid,org))
    return serialize(asset,org,full=True)


def serialize(asset,org,full=False):
    if not isinstance(asset,dict) or asset.get('schema')!=SCHEMA or asset.get('org_id')!=org or asset.get('purpose')!='research_only':raise KeyError('asset')
    raw={k:v for k,v in asset.items() if k!='registration_hash'}
    if not asset.get('registration_hash') or digest(raw)!=asset['registration_hash']:raise WorkflowError('登记快照完整性核验失败')
    keys=('schema','id','org_id','candidate_id','snapshot_hash','version','kind','display_name','hypothesis','source_hash','method','topic_id','policy_version','data','k','threshold','rules','category','tags','classification_source','approval','purpose','development_report','novelty_report','registration_hash')
    out={k:copy.deepcopy(asset.get(k)) for k in keys}
    req=asset.get('definition') or {}
    novelty=asset.get('novelty_report') or {};gate=novelty.get('gate') or {};meta=novelty.get('meta') or {}
    out['novelty_report']={'reference_hash':novelty.get('reference_hash'),'gate':{k:copy.deepcopy(gate.get(k)) for k in ('passed','complete','expected_count','compared_count','max_abs_correlation','threshold')},'meta':{k:meta[k] for k in ('request_hash','candidate_backtest_spec_hash','candidate_source_hash','data_release_id','reference_source_hash') if k in meta}}
    out['definition']={k:copy.deepcopy(req[k]) for k in ('factor_name','factor_code','library_name','universe','benchmark') if k in req}
    seal=asset.get('sealed_report') or {}
    out['sealed_report']={**copy.deepcopy(seal.get('summary') or {}),'report_id':seal.get('report_id'),'passed':True}
    return out


def list_assets(uid,org):
    with get_conn() as c:
        rows=c.execute("SELECT archive->'research_asset' AS asset FROM quant_factor_candidates WHERE org_id=%s AND archive->>'approved'='true' AND archive->'research_asset'->>'schema'=%s ORDER BY updated_at DESC",(org,SCHEMA)).fetchall()
    keys=('id','kind','display_name','hypothesis','version','category','tags','source_hash','purpose','approval','candidate_id','snapshot_hash')
    return [{**{k:copy.deepcopy(a[k]) for k in keys},'source_factor':{k:a['definition'][k] for k in ('factor_name','library_name') if k in a['definition']}} for row in rows for a in [serialize(row['asset'],org)] ]


def detail(uid,org,asset_id,full=False,c=None):
    with nullcontext(c) if c is not None else get_conn() as connection:
        row=connection.execute("SELECT archive->'research_asset' AS asset,snapshot_hash,snapshot,evidence FROM quant_factor_candidates WHERE org_id=%s AND archive->>'approved'='true' AND archive->'research_asset'->>'id'=%s",(org,asset_id)).fetchone()
    if not row:raise KeyError(asset_id)
    asset=row['asset']
    if row['snapshot_hash']!=asset['snapshot_hash'] or digest(row['snapshot'])!=asset['snapshot_hash']:raise WorkflowError('原候选与登记时冻结版本不一致')
    dev=(row.get('evidence') or {}).get('development') or {}
    if digest(dev.get('result') or {})!=asset['development_result_hash'] or digest(dev.get('novelty') or {})!=asset['novelty_result_hash']:raise WorkflowError('研究报告与登记时的证据指纹不一致')
    with nullcontext(c) if c is not None else get_conn() as connection:
        sealed=connection.execute('SELECT result,report_id FROM quant_factor_sealed_validations WHERE org_id=%s AND candidate_id=%s',(org,asset['candidate_id'])).fetchone()
    if not sealed or digest(sealed['result'])!=asset['sealed_report']['result_hash']:raise WorkflowError('封存报告与登记时的证据指纹不一致')
    return serialize(asset,org,full)


def full_report(uid,org,asset_id,phase):
    from .asset_reports import full_report as read_report
    return read_report(uid,org,asset_id,phase)
