"""Library comparison orchestration. All factor execution stays in ResearchEngine."""
import copy
import hashlib
import re
import time
from services.core.env_config import env
from services.core.re_config import RE_BASE
from services.core.lan_http import request_json
from .source_contract import validated_quant_code as validated_factor_code
from .asset_context import catalogue,duplicate_matches
from .novelty_policy import policy,evaluate_comparison,DEFAULTS
from .policy import WorkflowError,digest


def comparison_request(snapshot,development,refs,rules):
    candidate=copy.deepcopy(snapshot['request'])
    candidate.update(start=snapshot['plan']['developmentStart'],end=snapshot['plan']['developmentEnd'])
    if candidate.get('factor_code'):
        candidate['factor_code']=validated_factor_code(candidate['factor_code'],candidate['factor_name'])
    references=[{'reference_id':f['library_name']+':'+f['factor_name'],'factor_name':f['factor_name'],'library_name':f['library_name']} for f in refs['builtins']]
    references += [{'reference_id':f['source_id'],'factor_name':f['factor_name'],'factor_code':f['factor_code'],'source_hash':hashlib.sha256(f['factor_code'].encode()).hexdigest()} for f in refs['owned']]
    meta=development['meta']
    spec_hash=meta.get('spec_hash')
    if not spec_hash:raise WorkflowError('研发结果缺少候选规格指纹，不能提交查重')
    return {'candidate':candidate,'references':references,'expected_data_release_id':meta['data_release_id'],'expected_candidate_source_hash':meta['factor_source_hash'],'expected_candidate_spec_hash':spec_hash,'method':'daily_abs_spearman','min_pairs':int(rules['minPairs']),'reference_warmup_sessions':252}


def validate_result(result,payload,development):
    meta=result.get('meta') or {}
    if meta.get('request_hash')!=digest(payload):raise WorkflowError('对照结果与固定输入不匹配。')
    if meta.get('candidate_backtest_spec_hash')!=development['meta']['spec_hash']:raise WorkflowError('对照与研发的候选计算规格不同。')
    expected={r['reference_id'] for r in payload['references']}
    rows=result.get('comparisons') or []
    if result.get('expected_count')!=len(expected) or len(rows)!=len(expected) or {r.get('reference_id') for r in rows}!=expected:
        raise WorkflowError('返回清单与冻结对照库不一致，不能以部分库冒充完整比较。')
    if meta.get('reference_source_hash')!=digest([(r['reference_id'],r.get('source_hash')) for r in rows]):raise WorkflowError('对照源码清单指纹不一致。')
    if any(r.get('status')=='succeeded' and not r.get('source_hash') for r in rows):raise WorkflowError('有效对照缺少源码指纹。')


def assess(uid,snapshot,development,reference=None,compute=True,progress=None,org=None):
    rules=policy(snapshot['plan'])
    if rules['researchPurpose']=='replication':rules={**DEFAULTS,**rules}
    if rules['researchPurpose'] not in ('discovery','replication'):
        return {'status':'not_assessed','message':'已有或历史研究：没有数值去重证据，不作为新发现。','gate':{'passed':False,'complete':False}}
    refs=reference or catalogue(uid, org)
    base={'reference_hash':refs['hash'],'reference_scope':refs['scope'],'reference_count':refs['count']}
    empty={'passed':False,'complete':False,'expected_count':refs['count'],'compared_count':0,'max_abs_correlation':None,'threshold':rules['maxAbsCorrelation'],'limitation':'尚未取得完整数值对照，不能认定去重通过。'}
    duplicates=duplicate_matches(snapshot['request'].get('factor_code',''),refs)
    if not snapshot['request'].get('factor_code') and any(f['library_name']==snapshot['request'].get('library_name') and f['factor_name']==snapshot['request']['factor_name'] for f in refs['builtins']):
        duplicates.append({'name':snapshot['request']['factor_name'],'source_id':'builtin','library':snapshot['request']['library_name']})
    if duplicates and rules['researchPurpose']=='discovery':
        return {**base,'status':'failed','message':'与已有因子定义重复；改名、局部变量改名或改注释不作为新成果送审。','duplicates':duplicates,'gate':{**empty,'limitation':'源码/来源去重已命中，未执行数值相关性计算。'}}
    if not compute:
        return {**base,'status':'deferred','message':'研发数值门槛尚未通过，先改进候选；尚未执行全库数值对照，不认定为新发现。','gate':empty}
    rid=None
    from .re_client import base as compute_base
    base_url=compute_base()+'/api/factor/novelty'
    token=env('QUANT_NOVELTY_SERVICE_TOKEN',env('RE_SERVICE_TOKEN','')) or ''
    headers={'X-Service-Token':token} if token else None
    def cancel():
        if rid:
            try:request_json(base_url+'/'+rid,method='DELETE',timeout=15,headers=headers)
            except Exception:pass
    try:
        payload=comparison_request(snapshot,development,refs,rules)
        from .resources import preflight
        resource=preflight('novelty',payload)
        if not resource['allowed']:
            return {**base,'status':'resource_pending','message':'研发数值检验已完成；正式查重范围尚未获准，未执行全库比较。'+ '；'.join(resource.get('reasons') or []),'resource_preflight':resource,'gate':empty}
        from . import research_queue
        external_intent=research_queue.external_begin('novelty',{'base':compute_base()},digest(payload))
        status,_,task=request_json(base_url,method='POST',payload=payload,timeout=30,headers=headers)
        if status in (400,401,403,404,405,413,422,429):research_queue.external_update(external_intent,status='failed')
        if status not in (200,202) or not isinstance(task,dict):raise WorkflowError('因子值对照提交失败，HTTP '+str(status))
        rid=task.get('run_id')
        if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{32}',rid):raise WorkflowError('对照服务未返回有效任务编号。')
        base['run_id']=rid
        research_queue.external_update(external_intent,run_id=rid,status=task.get('status','queued'))
        if progress and progress('novelty_submitted','正在比较冻结清单中的真实因子值。',run_id=rid,tool='ResearchEngine.factor_novelty') is False:
            cancel();return {**base,'status':'cancelled','message':'已请求取消对照，保留原研发报告。','gate':empty}
        deadline=time.monotonic()+1260;last=-1
        while time.monotonic()<deadline:
            status,_,task=request_json(base_url+'/'+rid,method='GET',timeout=30,headers=headers)
            if status!=200 or not isinstance(task,dict):raise WorkflowError('因子值对照状态读取失败，HTTP '+str(status))
            research_queue.external_update(external_intent,run_id=rid,status=task.get('status'))
            done=task.get('processed_references',0)
            if progress:
                action='novelty_progress' if done!=last else None
                if progress(action,f'已处理 {done} / {refs["count"]} 个对照；完成不等于通过。',run_id=rid) is False:
                    cancel();return {**base,'status':'cancelled','message':'已请求取消对照，保留原研发报告。','gate':empty}
            last=done
            if task.get('status')=='succeeded':break
            if task.get('status') in ('failed','cancelled'):
                if 'Data release differs' in str(task.get('error','')):
                    raise WorkflowError('行情版本已更新，与原研发报告不同。需恢复原数据版本后重试，或登记新的研究版本；不能把新版相关性拼接到旧报告。')
                raise WorkflowError('对照任务未成功完成：'+task['status'])
            time.sleep(2)
        else:raise WorkflowError('因子库对照超时；未重复计算回测。')
        result=task.get('result') or {}
        validate_result(result,payload,development)
        gate=evaluate_comparison(result,rules,development['meta']['data_release_id'],development['meta']['factor_source_hash'])
        status=gate['status']
        message={'passed':'完整冻结对照库的预登记相关性门槛通过；仍需样本外与人工研究复核。','failed':'已识别与既有因子高度相关；新发现不能送审，复现仅作为原定义的验证记录。','incomplete':'对照存在失败或覆盖不足，不能认定通过；请查看逐项证据。'}[status]
        return {**base,'status':status,'message':message,'gate':gate,'comparisons':result['comparisons'],'meta':result['meta']}
    except Exception as exc:
        cancel()
        message=str(exc) if isinstance(exc,WorkflowError) else '因子库对照服务异常，原研发报告已保留。'
        return {**base,'status':'unavailable','message':message+' 可恢复服务后仅重试冻结库对照。','gate':empty}
