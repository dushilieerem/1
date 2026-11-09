import {staticResearchSample,researchScopeLabel} from '@/lib/factorPresentation';
import {useEffect,useState} from 'react';
import {getProject,saveProject,DETECT_UNIVERSE_OPTIONS,DETECT_BENCHMARK_OPTIONS,DETECT_GROUP_OPTIONS,type DetectProject,type DetectProjectConfig} from '@/lib/detectStore';
const keys=['universe','benchmark','portfolioType','groups','rebalanceDays','executionTiming','commissionRate','stampTax','slippageRate','filterSt','filterSuspended','filterLimitUp','filterLimitDown'] as const;
const fingerprint=(c:DetectProjectConfig)=>JSON.stringify(keys.map(k=>c[k]));
export function FactorResearchParameters({project,onSaved,onDirty}:{project:DetectProject;onSaved:(p:DetectProject)=>void;onDirty:(dirty:boolean)=>void}){
 const [draft,setDraft]=useState(project.config),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{setDraft(project.config);},[project]);
 const sample=staticResearchSample(draft);
 const dirty=fingerprint(draft)!==fingerprint(project.config);
 useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
 function change<K extends keyof DetectProjectConfig>(key:K,value:DetectProjectConfig[K]){setDraft(d=>({...d,[key]:value}));setNotice('');}
 async function save(){if(busy)return;setBusy(true);setError('');try{
  if(draft.executionTiming==='same_close')throw Error('固定版本检验须使用次日成交。');
  if(!Number.isInteger(draft.rebalanceDays)||draft.rebalanceDays<1||draft.rebalanceDays>252)throw Error('调仓间隔须为 1—252 个交易日。');
  for(const k of ['commissionRate','stampTax','slippageRate'] as const)if(!Number.isFinite(draft[k])||draft[k]<0||draft[k]>.1)throw Error('费用率须为 0%—10%。');
  const fresh=await getProject(project.id);if(!fresh)throw Error('研究读取失败，未覆盖原记录。');
  const config={...fresh.config};for(const k of keys)Object.assign(config,{[k]:draft[k]});
  const saved=await saveProject({...fresh,config});onSaved(saved);setNotice('研发参数已保存。下方检验将冻结这些参数。');
 }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 return <form onSubmit={e=>{e.preventDefault();void save();}} aria-label="机构因子研发参数">
 <div className="form-grid"><label className="field"><span>研究股票池</span>{sample?<><input readOnly aria-label="实际研究样本" value={researchScopeLabel(draft)}/><details><summary>查看固定证券清单</summary><p className="break-words">{sample.join('、')}</p></details><small>静态研究样本，不代表历史指数成分。此处查看已保存范围，股票池选项不会覆盖它。</small></>:<select value={draft.universe} onChange={e=>change('universe',e.target.value)}>{DETECT_UNIVERSE_OPTIONS.map(x=><option key={x.code} value={x.code}>{x.code==='CSI_ALL'?'全A（当前数据口径含B股）':x.label}</option>)}</select>}</label><label className="field"><span>比较基准</span><select value={draft.benchmark} onChange={e=>change('benchmark',e.target.value)}>{DETECT_BENCHMARK_OPTIONS.map(x=><option key={x.code} value={x.code}>{x.label}</option>)}</select></label>
 <label className="field"><span>分层数</span><select value={draft.groups} onChange={e=>change('groups',Number(e.target.value))}>{DETECT_GROUP_OPTIONS.map(n=><option key={n} value={n}>{n} 组</option>)}</select></label><label className="field"><span>调仓间隔（交易日）</span><input type="number" required min={1} max={252} value={draft.rebalanceDays} onChange={e=>change('rebalanceDays',Number(e.target.value))}/></label>
 <label className="field"><span>收益诊断组合</span><select value={draft.portfolioType} onChange={e=>change('portfolioType',e.target.value)}><option value="long_only">多头组合</option><option value="long_short">多空诊断组合</option></select></label><label className="field"><span>成交时点</span><select value={draft.executionTiming||'next_close'} onChange={e=>change('executionTiming',e.target.value as DetectProjectConfig['executionTiming'])}>{draft.executionTiming==='same_close'&&<option value="same_close">历史同日收盘（须更改）</option>}<option value="next_open">次日开盘</option><option value="next_close">次日收盘</option></select></label>
 {([['commissionRate','单边佣金率（%）'],['stampTax','卖出印花税率（%）'],['slippageRate','滑点率（%）']] as const).map(([key,label])=><label className="field" key={key}><span>{label}</span><input required type="number" min={0} max={10} step={.001} value={Number((draft[key]*100).toFixed(8))} onChange={e=>change(key,Number(e.target.value)/100)}/></label>)}
 <label className="field"><span>计算区间</span><input readOnly value={project.config.researchPlan?project.config.researchPlan.developmentStart+' 至 '+project.config.researchPlan.developmentEnd:'先在 F2 保存研发区间'}/></label></div>
 <div className="check-grid">{([['filterSt','排除 ST'],['filterSuspended','检查停牌'],['filterLimitUp','检查涨停买入限制'],['filterLimitDown','检查跌停卖出限制']] as const).map(([key,label])=><label className="check" key={key}><input type="checkbox" checked={draft[key]} onChange={e=>change(key,e.target.checked)}/>{label}</label>)}</div>
 <p className="hint">检验使用平台现有计算引擎。IC 当前口径为未来 1 日收益；数据版本、费用、成交限制和因子源码随每次实验保存。多空组合用于研究诊断，不代表可实际做空。</p>
 {error&&<p className="hint error" role="alert">{error}</p>}{notice&&<p className="hint success" role="status">{notice}</p>}<div className="form-actions"><button className="btn primary" disabled={busy||!dirty}>保存研发参数</button><span className="fine">{dirty?'参数有修改，保存后才能冻结检验':'使用当前已保存参数'}</span></div></form>;
}
