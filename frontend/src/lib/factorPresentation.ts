export type CandidateIdentity={trial_no?:number|null;trial_numbers?:number[];branch_id?:string|null;branch_label?:string|null;relation_status?:string;creation_label?:string;execution_label?:string};
export function staticResearchSample(value:unknown):string[]|undefined{
 if(!value||typeof value!=='object')return;const v=value as Record<string,unknown>;const snapshot=v.universe_snapshot as {symbols?:unknown}|undefined;const symbols=snapshot?.symbols??v.researchUniverseSymbols;
 if(Array.isArray(symbols)&&symbols.length&&symbols.every(x=>typeof x==='string'&&x.trim()))return [...symbols] as string[];
}
export function researchScopeLabel(value:unknown,fallback='未记录股票池'):string{
 const sample=staticResearchSample(value);if(sample)return `静态研究样本 · ${sample.length} 只`;
 if(value&&typeof value==='object'){const universe=(value as Record<string,unknown>).universe;if(typeof universe==='string'&&universe)return universe;}
 return fallback;
}
export function trialCandidateLabel(value:{presentation?:CandidateIdentity;status:string}):string{
 const identity=value.presentation;const numbers=identity?.trial_numbers?.length?identity.trial_numbers:typeof identity?.trial_no==='number'?[identity.trial_no]:[];
 const experiment=numbers.length?numbers.map(n=>'E'+n).join(' / '):'待关联试验';
 const status:Record<string,string>={development_running:'研发检验中',development_passed:'研发条件通过',development_failed:'研发未达标',development_error:'研发需要处理',cancelled:'已停止',validation_passed:'历史复验通过',validation_failed:'历史复验未通过'};
 return `${experiment} · ${identity?.branch_label||'分支待确认'} · ${status[value.status]||'记录待确认'}`;
}
export function selectCandidate<T extends {id:string;presentation?:CandidateIdentity}>(items:T[],candidateId:string|null,branchId:string|null):{candidate?:T;reason?:string}{
 const requested=candidateId?items.find(x=>x.id===candidateId):undefined;
 if(candidateId&&!requested)return {reason:'指定候选不存在或无权读取，请明确选择候选。'};
 if(requested&&branchId&&requested.presentation?.branch_id!==branchId)return {reason:'指定候选与当前查看分支不一致，请明确选择对应候选。'};
 if(requested)return {candidate:requested};
 if(branchId){const matched=items.find(x=>x.presentation?.branch_id===branchId&&x.presentation?.relation_status!=='conflict');return matched?{candidate:matched}:{reason:'当前分支尚无可确认的冻结候选，请明确选择候选；不会自动显示其他分支的结果。'};}
 return {candidate:items[0]};
}
export function noveltyEventLabel(event:{action:string;status?:string},novelty?:{status?:string;run_id?:string;duplicates?:unknown[];gate?:{compared_count?:number}}):string|undefined{
 if(['novelty_started','novelty_assessment_started'].includes(event.action))return '核对查重条件';
 if(!['novelty_completed','novelty_status_updated','novelty_retry_completed'].includes(event.action))return;
 const status=event.status||novelty?.status;
 if(status==='deferred')return '研发未达标，未执行数值查重';
 if(status==='resource_pending')return '查重范围待确认，未执行数值对照';
 if(status==='failed'&&!novelty?.run_id)return '定义重复性检查未通过';
 if(status==='unavailable')return '查重尚未完成，需要处理';
 if(['passed','failed','incomplete'].includes(status||'')&&novelty?.run_id)return '因子值对照已返回';
 return '查重状态已更新';
}

export function formatGateNumber(value:unknown,missing='无法计算 / 缺数据'):string{if(typeof value==='number'&&Number.isFinite(value))return Number(value.toPrecision(4)).toString();if(typeof value==='boolean')return value?'是':'否';return missing;}
