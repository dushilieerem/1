import {formatGateNumber,staticResearchSample,researchScopeLabel,trialCandidateLabel,type CandidateIdentity} from '@/lib/factorPresentation';
import {useEffect,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import {getRun,getProject,DETECT_BENCHMARK_OPTIONS,DETECT_UNIVERSE_OPTIONS,optionLabel} from '@/lib/detectStore';
import {researchFetch,subscribeAuth} from '@/lib/researchClient';
import {loadFactorAssetReport,reportDate,type FactorAssetReport,type ReadonlyFactorReportRun,type FactorReportPhase} from '@/lib/factorLibraryReports';
import {WorkspaceHeading,FactorModuleTabs} from './QuantWorkspacePages';
import {quantReportsPath} from './QuantFactorShell';
import {FactorReportChart} from './FactorReportChart';
import {alignedCurves,relativeCurve,curveReturn,periodReturns,icStats,groupSeries,formatResearchNumber as fmt,metricLabels,percentKeys,finite} from './factorReportData';
export {formatResearchNumber} from './factorReportData';
function exportRecord(run:ReadonlyFactorReportRun){const url=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='factor-report-'+run.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function Metric({label,value,percent=false,hint}:{label:string;value:unknown;percent?:boolean;hint?:string}){return <div className="qr-metric"><span>{label}</span><strong>{fmt(value,percent)}</strong>{hint&&<small>{hint}</small>}</div>;}
function RecordDetails({value,label='完整记录'}:{value:unknown;label?:string}){return <details className="qr-data"><summary>{label}</summary><pre className="code-preview">{JSON.stringify(value,null,2)}</pre></details>;}
export type ResearchGate={passed:boolean;numerical_passed?:boolean;checks:Array<{name:string;actual:number|null;operator:string;threshold:number|boolean;passed:boolean;reason?:string}>};
export type ResearchNovelty={status?:string;message?:string;duplicates?:Array<{name?:string}>;gate?:{passed?:boolean;complete?:boolean;threshold?:number;max_abs_correlation?:number|null;compared_count?:number;expected_count?:number;flow_test?:boolean;limitation?:string;closest?:{reference_id?:string;factor_name?:string;mean_abs_spearman?:number}|null}};
const percentGate=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?(value*100).toFixed(1)+'%':'—';
export function ResearchGateSummary({gate,phase='development',novelty,purpose}:{gate:ResearchGate;phase?:FactorReportPhase;novelty?:ResearchNovelty;purpose?:string}){
 const passed=gate.numerical_passed??gate.passed;const number=formatGateNumber;const stage=phase==='sealed'?'独立验证':'研发';
 const isFlowTest=novelty?.status==='skipped_flow_test'||novelty?.gate?.flow_test===true;
 const noveltyApplicable=purpose==='discovery'||(!purpose&&!!novelty&&!isFlowTest);
 const noveltyPassed=novelty?.gate?.passed===true;
 const overall=passed&&(!noveltyApplicable||(noveltyPassed&&!isFlowTest));
 const noveltyLabel=isFlowTest?'流程测试未执行':noveltyPassed?'通过':novelty?.status==='failed'?'未通过':novelty?.status==='deferred'?'待执行':novelty?.status==='unavailable'?'不可用':novelty?.status==='incomplete'||novelty?.status==='resource_pending'?'未完成':'未记录';
 const noveltyHint=novelty?.duplicates?.length?('定义重复：'+novelty.duplicates.map(d=>d.name).filter(Boolean).join('、')):novelty?.message||novelty?.gate?.limitation;
 const headline=!passed?stage+'数值条件未通过':isFlowTest?stage+'流程测试（未执行正式查重，不可入库）':noveltyApplicable&&!noveltyPassed?stage+'数值通过，查重未通过':stage+'硬门槛通过（数值+查重）';
 return <section className={'qr-gate qr-gate-summary '+(overall?'passed':'failed')} aria-label={stage+'门槛结论'}><h3>{headline}</h3><div className="qr-gate-checks">{gate.checks.map((c,i)=><div className="qr-gate-check" key={i}><strong>{c.name}</strong><span className={c.passed?'pass':'fail'}>{c.passed?'通过':'未通过'}</span><span title={String(c.actual)}>实际值 <b>{number(c.actual)}</b></span><span title={String(c.threshold)}>门槛 {c.operator} {number(c.threshold)}</span>{c.reason&&<p>{c.reason}</p>}</div>)}{noveltyApplicable&&<div className="qr-gate-check"><strong>因子库相关性</strong><span className={noveltyPassed&&!isFlowTest?'pass':'fail'}>{noveltyLabel}</span><span title={String(novelty?.gate?.max_abs_correlation??'')}>最大绝对相关 <b>{percentGate(novelty?.gate?.max_abs_correlation)}</b></span><span title={String(novelty?.gate?.threshold??'')}>门槛 &lt; {percentGate(novelty?.gate?.threshold)}</span><span>对照 {novelty?.gate?.compared_count??0}/{novelty?.gate?.expected_count??0}</span>{novelty?.gate?.closest&&<p>最接近：{novelty.gate.closest.factor_name||novelty.gate.closest.reference_id||'未记录'}{typeof novelty.gate.closest.mean_abs_spearman==='number'?' · '+percentGate(novelty.gate.closest.mean_abs_spearman):''}</p>}{noveltyHint&&<p>{noveltyHint}</p>}</div>}</div></section>;
}
function factorWindow(code:string):number|undefined{
 const pct=code.match(/pct_change\(\s*(\d+)\s*\)/);if(pct)return Number(pct[1]);
 const shift=code.match(/shift\(\s*(\d+)\s*\)/);if(shift)return Number(shift[1]);
 return undefined;
}
function explainFactorCode(code:string):string[]{
 const notes:string[]=[];
 const pct=code.match(/pct_change\(\s*(\d+)\s*\)/);
 if(pct)notes.push(`使用过去 ${pct[1]} 个交易日的收益率（pct_change(${pct[1]})）。`);
 const shift=code.match(/shift\(\s*(\d+)\s*\)/);
 if(shift)notes.push(`使用前第 ${shift[1]} 个交易日的值（shift(${shift[1]})），实际形成期为 ${shift[1]} 日。`);
 if(/\.rank\(\s*axis=1\s*,\s*pct=True\s*\)/.test(code))notes.push('在每个交易日横截面内做百分位排名（0—1）。');
 if(/rolling\(\s*window=\s*(\d+)/.test(code)){const m=code.match(/rolling\(\s*window=\s*(\d+)/);if(m)notes.push(`使用 ${m[1]} 日滚动窗口计算波动/统计量。`);}
 if(/amount/.test(code))notes.push('使用成交额（amount）构造价格/强度代理。');
 if(/volume/.test(code))notes.push('使用成交量（volume）参与构造或归一化。');
 if(/open|high|low/.test(code))notes.push('使用开盘、最高或最低价，包含日内结构信息。');
 if(/return\s+-/.test(code))notes.push('最终取负：原始数值越低，因子值越高（反转/负向映射）。');
 if(/return\s+[^-]/.test(code)&&!notes.some(n=>n.includes('因子值')))notes.push('因子值保持原始方向；数值越高表示信号越强。');
 if(/close/.test(code)&&!notes.some(n=>n.includes('收盘')))notes.push('核心输入包含收盘价（close）。');
 if(!notes.length)notes.push('实现包含自定义计算；具体经济含义请结合研究假设和源码阅读。');
 return notes;
}

function FactorDefinitionCard({run,request,plan,hypothesis,background,summary,planner,onShowSource}:{run:ReadonlyFactorReportRun;request:ReadonlyFactorReportRun['request'];plan?:Record<string,unknown>;hypothesis?:string;background?:string;summary?:string;planner?:string;onShowSource:()=>void}){
 const req=request as Record<string,unknown>;
 const rules=(plan?.rules||{}) as Record<string,unknown>;
 const contract=(plan?.researchContract||{}) as Record<string,unknown>;
 const code=typeof req.factor_code==='string'?req.factor_code:'';
 const name=run.factorName||String(contract.factor_name||'未命名因子');
 const description=hypothesis|| (typeof plan?.hypothesis==='string'?plan.hypothesis:'') || run.description?.replace(/ \/ (development|validation)$/,'') || '该报告未保存研究假设；请查看下方实现或输入与来源。';
 const fields=Array.isArray(contract.allowed_fields)?contract.allowed_fields.map(String):[];
 const notes=explainFactorCode(code);
 const window=factorWindow(code);
 const ranked=/\.rank\(/.test(code);
 const formula=window&&/close/.test(code)?`S_i,t = -${ranked?'rank_pct':'1'} × (close_i,t / close_i,t-${window} - 1)`:undefined;
 const hypothesisWindow=(()=>{const h=description;const m=h.match(/r(\d+)_i,t/)||h.match(/过去\s*(\d+)\s*个交易日/)||h.match(/(\d+)\s*个交易日/);return m?Number(m[1]):undefined;})();
 const taskWindow=(()=>{const m=(run.description||'').match(/(\d+)\s*日/);return m?Number(m[1]):undefined;})();
 const mismatch=window!=null&&hypothesisWindow!=null&&window!==hypothesisWindow;
 const nameMismatch=window!=null&&taskWindow!=null&&window!==taskWindow;
 return <section className="card qr-section" aria-label="因子说明"><h3>因子说明</h3>
  <p><b>因子名称：</b>{name}{planner&&<small className="fine"> · {planner==='model'?'模型策划':'模板回退'}</small>}</p>
  <p><b>研究假设：</b>{description}</p>
  {formula&&<p><b>实现公式（按代码）：</b><code>{formula}</code></p>}
  {mismatch&&<p className="hint warning">实现实际使用 {window} 日窗口，研究假设写的是 {hypothesisWindow} 日；请核对实现与假设是否一致，不能只看任务名称。</p>}
  {nameMismatch&&<p className="hint warning">任务名称写的是 {taskWindow} 日，但实现/冻结假设实际是 {window} 日；以代码和假设为准，任务名称只是历史标签。</p>}
  {background&&<p><b>研究背景：</b>{background}</p>}
  {summary&&<p><b>提案摘要：</b>{summary}</p>}
  <p><b>实现要点：</b></p><ul>{notes.map((n,i)=><li key={i}>{n}</li>)}</ul>
  <dl className="details-grid">
   <dt>方向 / 预测目标</dt><dd>{String(rules.direction||'未记录')} / {String(plan?.target||'未来1个交易日收益')}</dd>
   <dt>样本 / 区间</dt><dd>{staticResearchSample(request)?researchScopeLabel(request):'股票池未记录'} / {String(req.start||'—')} — {String(req.end||'—')}</dd>
   <dt>调仓 / 成交</dt><dd>{String(req.rebalance_days??'—')} 日 / {String(req.execution_timing||'未记录')}</dd>
   <dt>允许字段</dt><dd>{fields.length?fields.join('、'):String(req.field_restriction||'按报告请求')}</dd>
  </dl>
  {code?<details className="small-details"><summary>查看因子实现代码</summary><pre className="code-preview">{code}</pre></details>:<p className="fine">本报告没有保存因子源码；请查看输入与来源。</p>}
  <p className="fine">说明由冻结代码与研究提案生成，是阅读辅助，不替代源码和统计检验。</p>
  <button className="btn small" onClick={onShowSource}>查看输入与来源</button>
 </section>;
}

export function QuantFactorReportPage(){
 const [gate,setGate]=useState<ResearchGate>(),[novelty,setNovelty]=useState<ResearchNovelty>(),[gateError,setGateError]=useState('');
 const [identity,setIdentity]=useState<CandidateIdentity>(),[candidateStatus,setCandidateStatus]=useState('');
 const [researchDefinition,setResearchDefinition]=useState<{hypothesis?:string;plan?:Record<string,unknown>;request?:Record<string,unknown>}>();
 const [researchContext,setResearchContext]=useState<{background?:string;summary?:string;planner?:string}>();
 const {runId='',assetId='',phase=''}=useParams(),assetMode=Boolean(assetId),[assetReport,setAssetReport]=useState<FactorAssetReport>(),[run,setRun]=useState<ReadonlyFactorReportRun>(),[loading,setLoading]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0),[view,setView]=useState('summary'),[industry,setIndustry]=useState('');
 useEffect(()=>{let alive=true;const controller=new AbortController();setRun(undefined);setAssetReport(undefined);setResearchDefinition(undefined);setError('');setLoading(true);setView('summary');setIndustry('');
  void(async()=>{if(assetMode){const data=await loadFactorAssetReport(assetId,phase,controller.signal);if(alive){setAssetReport(data);setRun(data.run);const asset=data.asset as {hypothesis?:string;definition?:Record<string,unknown>};setResearchDefinition({hypothesis:asset?.hypothesis,request:asset?.definition});}}else{const record=await getRun(runId);if(!alive)return;if(!record)throw Error('报告不存在、无权访问或服务暂不可用。');setRun(record);}})().catch(e=>{if(alive&&!controller.signal.aborted)setError(e instanceof Error?e.message:'报告暂时无法读取。');}).finally(()=>{if(alive)setLoading(false);});const off=subscribeAuth(()=>setRevision(n=>n+1));return()=>{alive=false;controller.abort();off();};
 },[runId,assetId,phase,assetMode,revision]);
 useEffect(()=>{let alive=true;setGate(undefined);setIdentity(undefined);setCandidateStatus('');setNovelty(undefined);setGateError('');
  if(assetMode){if(assetReport){const asset=assetReport.asset as {hypothesis?:string;definition?:Record<string,unknown>};setResearchDefinition({hypothesis:asset?.hypothesis,request:asset?.definition});setGate(assetReport.gate);}return;}
  setResearchDefinition(undefined);
  const match=run?.id.match(/^qf_([0-9a-f-]{36})_(development|validation)$/);if(match)researchFetch('/api/factor-workflow/candidates/'+match[1]).then(async response=>{if(!response.ok)throw Error('门槛记录暂不可读');return response.json();}).then(data=>{if(alive){setIdentity(data.presentation);setCandidateStatus(data.status);setGate(data.evidence?.[match[2]]?.gate);setNovelty(data.evidence?.[match[2]]?.novelty);const snapshot=(data.snapshot||{}) as {plan?:Record<string,unknown>;request?:Record<string,unknown>};setResearchDefinition({hypothesis:typeof snapshot.plan?.hypothesis==='string'?snapshot.plan.hypothesis:undefined,plan:snapshot.plan,request:snapshot.request});}}).catch(()=>{if(alive)setGateError('研究门槛记录暂不可读，以下报告计算结果仍可查看。');});return()=>{alive=false;};
 },[run?.id,assetMode,assetReport]);
 useEffect(()=>{let alive=true;if(!run?.projectId){setResearchContext(undefined);return;}void getProject(run.projectId).then(project=>{if(!alive||!project)return;const cfg=project.config as unknown as Record<string,unknown>;const context=(cfg.researchContext||{}) as Record<string,unknown>;const agent=(cfg.agentV0||{}) as Record<string,unknown>;const proposal=(agent.proposal||{}) as Record<string,unknown>;setResearchContext({background:typeof context.background==='string'?context.background:undefined,summary:typeof proposal.summary==='string'?proposal.summary:undefined,planner:typeof agent.planner==='string'?agent.planner:undefined});}).catch(()=>{});return()=>{alive=false;};},[run?.projectId]);
 const result=run?.result,meta=result?.meta||{},fa=result?.factor_analysis,request=run?.request||{},metrics=result?.metrics||{};
 const benchmark=optionLabel(request?.benchmark||'',DETECT_BENCHMARK_OPTIONS)||'基准',benchName=benchmark+'基准';
 const mainReturn=curveReturn(result?.equity_curve),benchReturn=curveReturn(result?.benchmark_curve),relative=relativeCurve(result?.equity_curve,result?.benchmark_curve),relativeReturn=curveReturn(relative);
 const equity=alignedCurves([{name:'研究组合',points:result?.equity_curve,color:'#7651a1'},{name:benchName,points:result?.benchmark_curve,color:'#9aa9ba',dashed:true}],true);
 const drawdown=alignedCurves([{name:'组合回撤',points:result?.equity_curve?.map(p=>({date:p.date,value:finite(p.drawdown)?p.drawdown*100:null})),color:'#ad708a'},{name:'基准回撤',points:result?.benchmark_curve?.map(p=>({date:p.date,value:finite(p.drawdown)?p.drawdown*100:null})),color:'#a2aebb',dashed:true}]);drawdown.percent=true;drawdown.series[0].area=true;
 const relativePlot=alignedCurves([{name:'相对基准收益',points:relative,color:'#258f90'}],true);
 const ic=result?icStats(result):{count:0,positive:null,ir:null};
 const dailyIc=alignedCurves([{name:'日度 Pearson IC',points:fa?.ic_series,color:'#7651a1'}]);dailyIc.series[0].kind='bar';
 const monthly=periodReturns(result?.equity_curve),monthlyBench=new Map(periodReturns(result?.benchmark_curve).map(x=>[x.month,x.value]));
 const warnings=Array.isArray(meta.warnings)?meta.warnings.filter((x):x is string=>typeof x==='string'):[];
 const groups=fa?.quantile_metrics||[],industryCurves=fa?.industry_equity_curves||[],industryGroups=fa?.industry_group_equity_curves||[];
 const selectedIndustry=industry||industryGroups[0]?.industry_code||industryGroups[0]?.industry_name||'';
 const selectedGroup=industryGroups.find(x=>(x.industry_code||x.industry_name)===selectedIndustry);
 const industryKeys=[...new Set((selectedGroup?.points||[]).flatMap(p=>Object.keys(p.groups||{})))];
 const hasBenchmark=(result?.benchmark_curve||[]).some(p=>finite(p.value));
 const candidateId=run?.id.match(/^qf_([0-9a-f-]{36})_(development|validation)$/)?.[1];const returnQuery=candidateId?'?candidate='+encodeURIComponent(candidateId)+(identity?.branch_id?'&branch='+encodeURIComponent(identity.branch_id):''):'';
 const stage=assetMode?(phase==='sealed'?'独立验证':'研发检验'):run?.id.endsWith('_validation')?'样本外复验':run?.id.endsWith('_development')?'研发检验':'因子实验';
 const backToAsset='/quant/factor/library?asset='+encodeURIComponent(assetId);
 return <div className="quant-factor-report"><WorkspaceHeading title="因子研究报告" description="以固定输入与真实计算结果，评估因子的预测能力、收益风险与适用边界。">{run&&<button className="btn" onClick={()=>exportRecord(run)}>导出完整报告</button>}<Link className="btn" to={assetMode?backToAsset:quantReportsPath(run?.projectId||undefined)}>{assetMode?'返回因子详情':'实验记录'}</Link></WorkspaceHeading><FactorModuleTabs active={assetMode?'library':'experiments'} projectId={assetMode?undefined:run?.projectId||undefined}/>
 {loading?<p role="status" className="card card-pad">正在读取报告…</p>:error?<p className="hint error" role="alert">{error}<button className="btn small" onClick={()=>setRevision(n=>n+1)}>重试</button></p>:run&&result&&<>
 <section className="card qr-hero"><div><div className="qr-eyebrow">FACTOR RESEARCH <span>{stage}</span>{identity&&<span>{trialCandidateLabel({presentation:identity,status:candidateStatus})}</span>}</div><h2>{assetReport?.asset.display_name||run.description?.replace(/ \/ (development|validation)$/,'')||run.factorName}</h2><p className="qr-factor-name">{run.factorName}{assetReport&&<> · 第 {assetReport.asset.version} 版 · 审批时固定报告</>}</p><div className="qr-facts"><span><small>实际区间</small>{result.date_range?.start||'未返回'} — {result.date_range?.end||'未返回'}</span><span><small>股票池</small>{staticResearchSample(request)?researchScopeLabel(request):optionLabel(request?.universe||'',DETECT_UNIVERSE_OPTIONS)||'未注明'}</span><span><small>比较基准</small>{benchmark||'未注明'}</span><span><small>成交 / 调仓</small>{({next_open:'次日开盘',next_close:'次日收盘',same_close:'当日收盘'} as Record<string,string>)[request?.execution_timing||'']||'未注明'} / {request?.rebalance_days??'—'} 日</span></div></div>{assetMode?<Link className="btn primary" to={backToAsset}>返回因子详情 →</Link>:<Link className="btn primary" to={'/quant/factor/workflow/'+run.projectId+(stage==='样本外复验'?'/F5':'/F4')+returnQuery}>返回研究任务 →</Link>}</section>
 {gate&&<ResearchGateSummary gate={gate} phase={assetReport?.phase} novelty={novelty} purpose={typeof researchDefinition?.plan?.researchPurpose==='string'?researchDefinition.plan.researchPurpose:undefined}/>}
 {result.error&&<p className="hint warning">本次计算未完成：{String(result.error)}</p>}
 <FactorDefinitionCard run={run} request={request} plan={researchDefinition?.plan} hypothesis={researchDefinition?.hypothesis} background={researchContext?.background} summary={researchContext?.summary} planner={researchContext?.planner} onShowSource={()=>setView('definition')}/>
 <div className="qr-metrics"><Metric label="组合累计收益" value={mainReturn} percent hint="按报告净值序列计算"/><Metric label="年化收益" value={metrics.annual_return} percent hint="报告统计"/><Metric label="相对基准收益" value={relativeReturn} percent hint="组合净值 ÷ 基准净值 − 1"/><Metric label="最大回撤" value={metrics.max_drawdown} percent hint="报告统计"/><Metric label="夏普比率" value={metrics.sharpe??metrics.sharpe_ratio} hint="风险调整表现"/><Metric label="Rank IC" value={metrics.rank_ic??fa?.rank_ic_mean} hint="因子与前瞻收益的秩相关"/></div>

 {gate&&novelty&&!novelty.gate?.passed&&(gate.numerical_passed??gate.passed)&&<p className="hint warning">准入结论：数值门槛已通过，但查重未通过或不可用，不能进入封存/复核入库；这不是数值失败，不应盲目调参。</p>}
 {gateError&&<p className="hint warning">{gateError}</p>}
 {warnings.length>0&&<details className="qr-warning"><summary>本次计算有 {warnings.length} 项数据或执行提示</summary><ul>{warnings.map((w,i)=><li key={i}>{w}</li>)}</ul></details>}
 <div className="tabs qr-tabs" role="tablist" aria-label="报告内容">{[['summary','收益与风险'],['groups','分组表现'],['diagnostics','IC 诊断'],['industry','行业分析'],['definition','输入与来源']].map(([id,label])=><button className="tab" role="tab" key={id} aria-selected={view===id} onClick={()=>setView(id)}>{label}</button>)}</div>
 {view==='summary'&&<>
 <FactorReportChart title="累计收益 · 组合与基准" subtitle={'主组合：'+(request?.portfolio_type==='long_short'?'Q1 − QN 多空诊断':'Q1 多头组合')+'；Q1 为因子值最高组。累计收益 = 净值 − 1。'} plot={equity} height={360}/>
 {!hasBenchmark&&<p className="hint warning">本次报告未返回有效基准序列，无法进行基准对比；请检查计算服务与基准数据。</p>}
 <div className="qr-two"><FactorReportChart title="动态回撤" subtitle="使用引擎实际返回的回撤序列；缺失值保留断点。" plot={drawdown} height={270}/><FactorReportChart title="相对基准收益" subtitle="净值比率口径，不是累计收益相减；仅对齐同一交易日期。" plot={relativePlot} height={270}/></div>
 <div className="qr-two"><section className="card qr-section"><h3>收益与风险指标</h3><dl className="report-metrics">{[['基准累计收益',benchReturn,true],['日收益胜率',metrics.win_rate,true],['年化波动率',metrics.volatility,true],['Sortino 比率',metrics.sortino,false],['Calmar 比率',metrics.calmar,false],['换手率（引擎口径）',metrics.turnover,true]].map(([label,v,p])=><div key={String(label)}><dt>{String(label)}</dt><dd>{fmt(v,Boolean(p))}</dd></div>)}</dl></section><section className="card qr-section"><h3>交易成本</h3><p>主组合与分组收益的成本口径须分别核对。</p><dl className="report-metrics">{[['佣金',metrics.commission_cost],['印花税',metrics.stamp_tax_cost],['滑点',metrics.slippage_cost],['累计成本 / 净值',metrics.total_cost]].map(([label,v])=><div key={String(label)}><dt>{String(label)}</dt><dd>{fmt(v,true)}</dd></div>)}</dl><p className="fine">成本为期间相对组合净值的累计比例，不是现金金额。{String((meta.cost_model as Record<string,unknown>|undefined)?.note||'成本详细定义见输入与来源。')}</p></section></div>
 <div className="qr-two"><section className="card qr-section"><h3>月度收益</h3><p>根据报告净值计算；首尾月份可能为不完整月份。</p><div className="qr-table-scroll"><table><thead><tr><th>月份</th><th>研究组合</th><th>{benchmark}</th></tr></thead><tbody>{monthly.map(row=><tr key={row.month}><td>{row.month}</td><td>{fmt(row.value,true)}</td><td>{fmt(monthlyBench.get(row.month),true)}</td></tr>)}</tbody></table>{!monthly.length&&<p className="qr-empty">无有效净值序列。</p>}</div></section><section className="card qr-section"><h3>分年收益</h3><p>使用引擎年度返回值；区间首尾年度可能不完整。</p><table><thead><tr><th>年份</th><th>组合收益</th></tr></thead><tbody>{result.annual_returns?.map(row=><tr key={row.year}><td>{row.year}</td><td>{fmt(row.return_value,true)}</td></tr>)}</tbody></table>{!result.annual_returns?.length&&<p className="qr-empty">引擎未返回年度收益。</p>}</section></div>
 <section className="card qr-section"><h3>回撤区间</h3><div className="qr-table-scroll"><table><thead><tr><th>起点</th><th>谷底日期</th><th>回撤深度</th><th>恢复日期</th><th>区间天数</th></tr></thead><tbody>{result.drawdowns?.map((d,i)=><tr key={i}><td>{d.start}</td><td>{d.end}</td><td>{fmt(d.depth,true)}</td><td>{d.recovery||'区间内未恢复'}</td><td>{fmt(d.days)}</td></tr>)}</tbody></table></div>{!result.drawdowns?.length&&<p className="qr-empty">引擎未返回回撤区间。</p>}</section>
 </>}
 {view==='groups'&&<><p className="qr-note">Q1 为因子值最高组，QN 为最低组。{(meta.cost_model as Record<string,unknown>|undefined)?.layered_and_long_short==='gross'?'本次分组曲线为未扣交易成本的收益，主组合已扣成本，二者不能直接视为同一条曲线。':'分组与主组合的费用口径见输入与来源。'}</p><FactorReportChart title="分组累计收益" subtitle="观察分层单调性、组间差异及相对基准表现。" plot={groupSeries(result,benchName)}/><section className="card qr-section"><h3>分组绩效分析</h3><div className="qr-table-scroll"><table><thead><tr><th>分组</th><th>年化收益</th><th>年化波动</th><th>夏普</th><th>最大回撤</th><th>年化超额</th><th>信息比率</th><th>跑赢基准比例</th><th>日均单边换手</th></tr></thead><tbody>{groups.map(g=><tr key={g.quantile}><td><strong>{g.quantile==='benchmark'?benchmark:g.quantile}</strong></td><td>{fmt(g.annual_return,true)}</td><td>{fmt(g.volatility,true)}</td><td>{fmt(g.sharpe)}</td><td>{fmt(g.max_drawdown,true)}</td><td>{fmt(g.annual_excess_return,true)}</td><td>{fmt(g.information_ratio)}</td><td>{fmt(g.benchmark_win_rate,true)}</td><td>{fmt(g.turnover,true)}</td></tr>)}</tbody></table></div>{!groups.length&&<p className="qr-empty">本次计算未返回分组绩效。</p>}<p className="fine">年化超额、信息比率使用引擎口径；与上方“净值比率超额”不是同一指标。</p></section><section className="card qr-section"><h3>分层收益摘要</h3><dl className="report-metrics">{Object.entries(fa?.layered_returns||{}).map(([k,v])=><div key={k}><dt>{k==='groups'?'分组数':k==='spread'?'Q1 − QN 收益差':k==='long_short_return'?'多空累计收益':k.replace('layer','Q')}</dt><dd>{fmt(v,k!=='groups')}</dd></div>)}</dl></section></>}
 {view==='diagnostics'&&<><div className="qr-metrics four"><Metric label="Pearson IC 均值" value={metrics.ic??fa?.ic_mean}/><Metric label="IC IR（非年化）" value={ic.ir} hint="Pearson IC 均值 ÷ 标准差"/><Metric label="IC 为正比例" value={ic.positive} percent/><Metric label="有效 IC 观测数" value={ic.count} hint="实际返回的有效日度 IC"/></div><p className="qr-note">预测期限：{String(fa?.definition?.forward_return_days||'未返回')} 个交易日。当前日度序列是 Pearson IC，不能当作 Rank IC 序列；具体成交对齐口径见输入与来源。</p><FactorReportChart title="日度 Pearson IC" subtitle="横截面因子值与前瞻收益的相关性。" plot={dailyIc}/><div className="qr-two"><FactorReportChart title="累计 IC" subtitle="IC 的累加，不是投资组合累计收益。" plot={alignedCurves([{name:'累计 Pearson IC',points:fa?.cumulative_ic_series,color:'#258f90'}])} height={270}/><FactorReportChart title="滚动 IC IR" subtitle={'引擎窗口：'+String(fa?.definition?.rolling_ir_window||'未返回')+' 个观测。'} plot={alignedCurves([{name:'滚动 IC IR',points:fa?.rolling_ir_series,color:'#ba9557'}])} height={270}/></div>{fa?.definition?.ic_unavailable_reason&&<p className="hint warning">{String(fa.definition.ic_unavailable_reason)}</p>}</>}
 {view==='industry'&&<>{industryCurves.length?<FactorReportChart title="行业收益对比" subtitle="按引擎返回行业与收益口径展示，不补齐缺失行业。" plot={alignedCurves(industryCurves.map(c=>({name:c.industry_name||c.industry_code||'未命名行业',points:c.points})),true)}/>:<section className="card qr-section"><h3>本次报告未返回行业收益序列</h3><p className="qr-empty">当前不能判断行业贡献或暴露。行业数据与分析返回后会自动展示；空结果不会用示例数据代替。</p></section>}{industryGroups.length>0&&<><label className="field qr-industry"><span>行业分组诊断</span><select value={selectedIndustry} onChange={e=>setIndustry(e.target.value)}>{industryGroups.map(x=><option key={x.industry_code||x.industry_name} value={x.industry_code||x.industry_name}>{x.industry_name||x.industry_code}</option>)}</select></label><FactorReportChart title="行业内分组累计收益" plot={alignedCurves(industryKeys.map(k=>({name:k,points:selectedGroup?.points?.map(p=>({date:p.date,value:p.groups?.[k]}))})),true)}/></>}<section className="card qr-section"><h3>风格因子回归</h3><dl className="report-metrics">{Object.entries(metrics).filter(([k])=>k.startsWith('ff3_')).map(([k,v])=><div key={k}><dt>{metricLabels[k]||k}</dt><dd>{fmt(v)}</dd></div>)}</dl><p className="fine">FF3 为引擎返回的风格回归结果，不能替代行业归因。</p></section></>}
 {view==='definition'&&<><section className="card qr-section"><h3>当次实验设定</h3><dl className="details-grid"><dt>请求区间</dt><dd>{request.start||'未记录'} — {request.end||'未记录'}</dd><dt>分析级别</dt><dd>{request.analysis_level==='full'?'完整检测':'基础检测或历史未记录'}</dd><dt>佣金 / 印花税 / 滑点</dt><dd>{fmt(request.commission_rate,true)} / {fmt(request.stamp_tax,true)} / {fmt(request.slippage_rate,true)}</dd><dt>组合与分层</dt><dd>{request.portfolio_type||'未记录'} / {request.groups??'未记录'} 组</dd><dt>股票池 / 基准</dt><dd>{researchScopeLabel(request)} / {request.benchmark||'未记录'}</dd>{staticResearchSample(request)&&<><dt>固定证券清单</dt><dd className="break-words">{staticResearchSample(request)!.join('、')}<small className="block">静态研究样本，不代表历史指数成分。</small></dd></>}<dt>因子价格复权</dt><dd>{String(meta.factor_price_adjustment||'未返回')}</dd><dt>因子来源</dt><dd>{String(request.library_name||'本研究受限代码')}</dd></dl><RecordDetails label="执行、费用与诊断口径" value={{execution_model:meta.execution_model,cost_model:meta.cost_model,filter_status:meta.filter_status,definition:fa?.definition,assumptions:result.assumptions}}/><h3>冻结的因子实现</h3><pre className="code-preview">{request.factor_code||run.draftFactor?.body||'平台内置定义；使用来源库与源码指纹追溯。'}</pre><RecordDetails label="完整计算请求" value={request}/></section><section className="card qr-section"><h3>全部返回指标</h3><dl className="report-metrics">{Object.entries(metrics).map(([k,v])=><div key={k}><dt>{metricLabels[k]||k}</dt><dd>{fmt(v,percentKeys.has(k))}</dd></div>)}</dl></section><section className="card qr-section"><h3>数据与结果追溯</h3><dl className="details-grid">{['data_release_id','spec_hash','factor_source_hash','metric_version','execution_version'].map(k=><div className="detail-row" key={k}><dt>{k}</dt><dd>{String(meta[k]||'未返回')}</dd></div>)}</dl><p className="fine">报告 {run.id} · {reportDate(run.finishedAt)} · 耗时 {run.elapsedSec!=null&&run.elapsedSec>=0?run.elapsedSec+' 秒':'未记录'}。签名仅证明来源与完整性，不代表质量合格。</p>{assetReport&&<><p className="fine">批准时间 {reportDate(assetReport.asset.approved_at)}；报告时间未保存时不以批准时间替代。</p><RecordDetails label="登记版本与报告完整性" value={assetReport.provenance}/></>}<RecordDetails label="完整计算返回" value={result}/></section></>}
 <footer className="qr-footer">{stage} · 真实历史数据计算 · 研究结果不代表正式准入或实盘成交。图表缺失值保留断点，缩放仅改变显示范围。</footer>
 </> }</div>;
}
