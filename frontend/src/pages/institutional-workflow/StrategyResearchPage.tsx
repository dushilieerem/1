import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {WorkspaceHeading} from './QuantWorkspacePages';

type Topic={id:string;name:string;universe:string;benchmark:string;status:string;k?:number;branch_count:number;trial_count:number;max_trials:number;development_start?:string;development_end?:string};
type Branch={id:string;source:string;hypothesis:string;version:number;status:string;review_status?:string;sealed?:{status:string;result?:{excess_return?:number};gate?:Gate}|null;recipe:{factors:Array<{factor:string;library?:string;direction:string}>;top_n:number;rebalance_days:number;buffer?:number}};
type Gate={basis?:string;checks?:Array<{name:string;actual:number|null;threshold?:number;passed:boolean|null}>;passed?:boolean;complete?:boolean;pending?:string[];policy_status?:string};
type CurvePoint={date:string;value:number};
type TrialReport={equity_curve?:CurvePoint[];benchmark_curve?:CurvePoint[];annual_returns?:Array<{year:number;return_value:number}>;assumptions?:Record<string,string>;period_excess?:number};
type Trial={id:string;trial_no:number;branch_id:string;outcome:string;metrics?:{annual_return?:number;max_drawdown?:number;turnover?:number};gate?:Gate;effective_gate?:Gate;report_id?:string;rerun_of?:string|null;report?:TrialReport};
type Ledger={topic:Topic;branches:Branch[];trials:Trial[];k:number;ir_threshold?:number;policy?:{version:string}};
type Report={trial:Trial;branch:Branch;topic:Topic;diagnostics:Record<string,{payload:Record<string,unknown>}>;sealed?:{status:string;result?:{excess_return?:number;metrics?:Record<string,number>};gate?:Gate;report_id?:string}|null;policy?:{version:string}};
type Factor={source_library:string;factor_name:string;display_name?:string};
type Tab='run'|'manual'|'review'|'library'|'capability';
const check=(t:Trial|Report['trial'],name:string)=>(t.effective_gate||t.gate)?.checks?.find(c=>c.name.includes(name));
const pct=(v:number|null|undefined,digits=2)=>v==null?'—':(v*100).toFixed(digits)+'%';
const legacyGate=(g?:Gate)=>!!g?.checks?.length&&g.basis!=='annual';
const gateText=(t:Trial)=>{const g=t.effective_gate||t.gate;if(!g?.checks?.length)return '无门槛记录';if(legacyGate(g))return '旧口径，待重算';if(g.complete)return g.passed?'门槛通过':'门槛未通过';return `待补 ${g.pending?.length||0} 项`;};
const statusText=(s:string)=>s==='active'?'运行中':s==='paused'?'暂停':s==='archived'?'已归档':s==='frozen'?'待复核':s==='submitted'?'待复核':s==='approved'?'已入库':s==='rejected'?'已驳回':s;
const branchStatusText=(b:Branch)=>b.sealed?.status==='failed'?'封存失败':b.sealed?.status==='error'?'封存错误':b.sealed?.status==='passed'&&b.review_status==='sealed_passed'?'已封存待提交':b.status==='frozen'?'已冻结':b.status==='submitted'?'待复核':b.status==='approved'?'已入库':b.status==='rejected'?'已驳回':statusText(b.status);
const outcomeText=(t:Trial)=>{const g=t.effective_gate||t.gate;if(legacyGate(g))return '旧口径结果，待按年化重算';if(t.outcome==='error')return g?.complete&&g.passed?'执行未完成（诊断后门槛通过）':'执行错误（门槛未齐）';if(t.outcome==='failed')return '门槛未通过';if(t.outcome==='passed')return '门槛通过';return t.outcome;};

export function StrategyResearchPage(){
 const [tab,setTab]=useState<Tab>('run');
 const [authOpen,setAuthOpen]=useState(false);
 const [topics,setTopics]=useState<Topic[]>([]),[selected,setSelected]=useState<string>();
 const [ledger,setLedger]=useState<Ledger|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [library,setLibrary]=useState<Array<{id:string;topic_name:string;hypothesis:string;recipe:{factors?:Array<{factor:string}>;top_n:number;rebalance_days:number};version:number;trial_count:number;sealed_result?:{excess_return?:number}}>>([]);
 const [report,setReport]=useState<Report>();
 const [reviewQueue,setReviewQueue]=useState<Array<{id:string;topic_name:string;hypothesis:string}>>([]),[reviewErr,setReviewErr]=useState('');
 const [factors,setFactors]=useState<Factor[]>([]),[creating,setCreating]=useState(false),[extra,setExtra]=useState(0);
 const [form,setForm]=useState({name:'CSI500 新课题',universe:'CSI500',benchmark:'CSI500',development_start:'2022-01-01',development_end:'2024-12-31',validation_start:'2025-01-01',validation_end:'2025-12-31',cost_bps:10,max_trials:8,factor:'SV06_0010',library:'主因子库',direction:'negative',factor2:'',direction2:'positive',factor3:'',direction3:'positive',top_n:50,rebalance_days:20});

 const loadLedger=async(id:string)=>{const r=await researchFetch('/api/inst/quant/strategy-research/topics/'+encodeURIComponent(id)+'/ledger');if(!r.ok)throw Error('策略台账读取失败');setLedger(await r.json());};
 useEffect(()=>{let alive=true;researchFetch('/api/inst/quant/strategy-research/topics').then(r=>r.ok?r.json():Promise.reject(Error('策略课题读取失败'))).then(d=>{if(!alive)return;const list=d.topics||[];setTopics(list);setSelected(cur=>cur&&list.some((t:Topic)=>t.id===cur)?cur:list[0]?.id);}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[]);
 useEffect(()=>{if(!selected){setLedger(null);return;}let alive=true;loadLedger(selected).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));});return()=>{alive=false;};},[selected]);
 useEffect(()=>{let alive=true;void researchFetch('/api/inst/quant/strategy-research/library').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d)setLibrary(d.strategies||[]);});return()=>{alive=false;};},[]);
 useEffect(()=>{if(tab!=='review')return;let alive=true;setReviewErr('');void researchFetch('/api/inst/quant/strategy-research/reviews').then(async r=>{if(!alive)return;if(r.status===403)return setReviewErr('当前账号没有独立复核权限；策略审查在统一审查入口按复核角色展示。');if(!r.ok)throw Error('审查队列读取失败');const d=await r.json();setReviewQueue(d.branches||[]);}).catch(e=>{if(alive)setReviewErr(e instanceof Error?e.message:String(e));});return()=>{alive=false;};},[tab]);
 useEffect(()=>{if(!creating||factors.length)return;void researchFetch('/api/inst/quant/factor-workflow/imports/svquant-existing/reference').then(r=>r.ok?r.json():null).then(d=>{if(d)setFactors((d.items||[]).map((x:Factor)=>({source_library:x.source_library,factor_name:x.factor_name,display_name:x.display_name})));});},[creating,factors.length]);

 async function run(path:string,kind:string){
  if(busy)return;setBusy(true);setError('');
  try{const r=await researchFetch('/api/inst/quant/strategy-research'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:kind==='seal'?JSON.stringify({idempotency_key:crypto.randomUUID()}):undefined});const d=await r.json();if(!r.ok)throw Error(typeof (d.detail||d.error)==='string'?(d.detail||d.error):'操作失败');if(selected)await loadLedger(selected);if(kind==='backtest'&&d.trial_id)await openReport(d.trial_id);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }
 async function openReport(tid:string){setError('');try{const r=await researchFetch('/api/inst/quant/strategy-research/trials/'+encodeURIComponent(tid)+'/report');const d=await r.json();if(!r.ok)throw Error(typeof (d.detail||d.error)==='string'?(d.detail||d.error):'报告读取失败');setReport(d);}catch(e){setError(e instanceof Error?e.message:String(e));}}
 async function createTopic(){
  if(busy)return;setBusy(true);setError('');
  try{
   const body={name:form.name,objective:'页面新建策略课题',universe:form.universe,benchmark:form.benchmark,development_start:form.development_start,development_end:form.development_end,validation_start:form.validation_start,validation_end:form.validation_end,cost_bps:Number(form.cost_bps),max_trials:Number(form.max_trials)};
   const r=await researchFetch('/api/inst/quant/strategy-research/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const t=await r.json();if(!r.ok)throw Error(typeof (t.detail||t.error)==='string'?(t.detail||t.error):'建课题失败');
   const rb=await researchFetch('/api/inst/quant/strategy-research/topics/'+encodeURIComponent(t.id)+'/branches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hypothesis:form.name+' 初始配方：'+[form.factor,extra>=1?form.factor2:'',extra>=2?form.factor3:''].filter(Boolean).join(' + '),factors:[{factor:form.factor,library:form.library,direction:form.direction},...(extra>=1&&form.factor2?[{factor:form.factor2,library:(factors.find(x=>x.factor_name===form.factor2)?.source_library)||form.library,direction:form.direction2}]:[]),...(extra>=2&&form.factor3?[{factor:form.factor3,library:(factors.find(x=>x.factor_name===form.factor3)?.source_library)||form.library,direction:form.direction3}]:[])],top_n:Number(form.top_n),rebalance_days:Number(form.rebalance_days),buffer:0})});
   const b=await rb.json();if(!rb.ok)throw Error(typeof (b.detail||b.error)==='string'?(b.detail||b.error):'建分支失败');
   const rl=await researchFetch('/api/inst/quant/strategy-research/topics');const d=await rl.json();setTopics(d.topics||[]);setSelected(t.id);setCreating(false);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }

 const tabs:Array<[Tab,string]>=[['run','研究运行'],['manual','人工研究'],['review','审查'],['library','策略库'],['capability','能力与评测']];
 const selectedTopic=topics.find(t=>t.id===selected);
 return <><WorkspaceHeading eyebrow="" title="策略研究" description="用因子库里的因子构建交易规则；研究系统自主推进，你可以随时观察、介入或亲自研究。"><button className="btn" onClick={()=>setAuthOpen(v=>!v)}>研究授权</button><button className="btn primary" onClick={()=>setCreating(v=>!v)}>{creating?'收起新建':'新建课题'}</button></WorkspaceHeading>
 <nav className="tabs" aria-label="策略模块视图">{tabs.map(([k,label])=><button key={k} className={'tab'+(tab===k?' sel':'')} aria-current={tab===k?'page':undefined} onClick={()=>setTab(k)}>{label}</button>)}</nav>
 {authOpen&&<div className="card card-pad" style={{marginBottom:14}}><p className="fine">研究授权：当前登录成员可在本机构范围创建策略课题、运行回测与申请封存；预算、股票池、区间、成本与门槛由课题计划冻结。Agent 只能在授权范围内调整 TopN 与调仓周期，不能批准入库；入库只授予研究用途，实盘不在本期。</p></div>}
 {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
 {creating&&<div className="card"><div className="card-head"><h2>新建策略课题</h2><span className="fine">计划与初始配方一次冻结；预算 {form.max_trials}</span></div><div className="card-body"><div className="form-grid">
  <label className="field"><span>课题名称</span><input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
  <label className="field"><span>股票池</span><select value={form.universe} onChange={e=>setForm({...form,universe:e.target.value,benchmark:e.target.value})}><option>CSI500</option><option>CSI300</option><option>ALL_A</option></select></label>
  <label className="field"><span>研发开始</span><input value={form.development_start} onChange={e=>setForm({...form,development_start:e.target.value})}/></label>
  <label className="field"><span>研发结束</span><input value={form.development_end} onChange={e=>setForm({...form,development_end:e.target.value})}/></label>
  <label className="field"><span>封存开始</span><input value={form.validation_start} onChange={e=>setForm({...form,validation_start:e.target.value})}/></label>
  <label className="field"><span>封存结束</span><input value={form.validation_end} onChange={e=>setForm({...form,validation_end:e.target.value})}/></label>
  <label className="field"><span>单边成本 bps</span><input type="number" value={form.cost_bps} onChange={e=>setForm({...form,cost_bps:Number(e.target.value)})}/></label>
  <label className="field"><span>试验预算</span><input type="number" value={form.max_trials} onChange={e=>setForm({...form,max_trials:Number(e.target.value)})}/></label>
  <label className="field"><span>因子（导入/已入库）</span><select value={form.factor} onChange={e=>{const f=factors.find(x=>x.factor_name===e.target.value);setForm({...form,factor:e.target.value,library:f?.source_library||form.library});}}>{factors.length===0&&<option value={form.factor}>{form.factor}</option>}{factors.map(f=><option key={f.source_library+':'+f.factor_name} value={f.factor_name}>{f.factor_name} · {f.display_name||''}（{f.source_library}）</option>)}</select></label>
  <label className="field"><span>方向</span><select value={form.direction} onChange={e=>setForm({...form,direction:e.target.value})}><option value="positive">正向</option><option value="negative">负向</option></select></label>
  {extra>=1&&<label className="field"><span>因子 2</span><select value={form.factor2} onChange={e=>setForm({...form,factor2:e.target.value})}><option value="">不使用</option>{factors.map(f=><option key={'2'+f.source_library+f.factor_name} value={f.factor_name}>{f.factor_name} · {f.display_name||''}</option>)}</select><select value={form.direction2} onChange={e=>setForm({...form,direction2:e.target.value})}><option value="positive">正向</option><option value="negative">负向</option></select></label>}
  {extra>=2&&<label className="field"><span>因子 3</span><select value={form.factor3} onChange={e=>setForm({...form,factor3:e.target.value})}><option value="">不使用</option>{factors.map(f=><option key={'3'+f.source_library+f.factor_name} value={f.factor_name}>{f.factor_name} · {f.display_name||''}</option>)}</select><select value={form.direction3} onChange={e=>setForm({...form,direction3:e.target.value})}><option value="positive">正向</option><option value="negative">负向</option></select></label>}
  <div className="field"><span>组合</span><div className="form-actions" style={{margin:0,padding:0,border:0}}><button type="button" className="btn small" disabled={extra>=2} onClick={()=>setExtra(extra+1)}>添加因子（最多 3 个）</button>{extra>0&&<button type="button" className="btn small" onClick={()=>setExtra(0)}>清除附加因子</button>}</div><small>等权合成；1—3 个因子。</small></div>
  <label className="field"><span>TopN</span><input type="number" min={5} max={300} value={form.top_n} onChange={e=>setForm({...form,top_n:Number(e.target.value)})}/></label>
  <label className="field"><span>调仓周期（日）</span><input type="number" min={1} max={60} value={form.rebalance_days} onChange={e=>setForm({...form,rebalance_days:Number(e.target.value)})}/></label>
 </div><div className="form-actions"><button className="btn primary" disabled={busy} onClick={()=>void createTopic()}>创建课题与首分支</button><span className="fine">创建后仍需运行回测；回测计入 K，确定性重算不计。因子来自导入资产时标注“未经 V5 复核”。</span></div></div></div>}
 {loading?<div className="card card-pad"><p role="status">正在读取真实策略课题…</p></div>:tab==='run'&&(topics.length===0?<div className="card card-pad"><h2>还没有策略课题</h2><p className="hint">使用右上角“新建课题”从因子库建立首个课题。</p></div>:<>
  <div className="sys-strip"><div className="sys-state"><span className="ico">⌁</span><div><b>{topics.some(t=>t.status==='active')?'策略研究系统运行中':topics.length?'策略研究系统空闲（无进行中课题）':'策略研究系统待建课题'}</b><small className="fine">授权：按课题计划与登录角色</small></div></div><div className="kpis"><div className="kpi"><span>课题</span><b>{topics.length}</b><small>研究中 {topics.filter(t=>t.status==='active').length} · 暂停 {topics.filter(t=>t.status==='paused').length}</small></div><div className="kpi"><span>试验台账</span><b>{topics.reduce((n,t)=>n+t.trial_count,0)}</b><small>次（含 rerun）</small></div><div className="kpi"><span>分支</span><b>{topics.reduce((n,t)=>n+t.branch_count,0)}</b><small>个冻结配方</small></div><div className="kpi"><span>门槛政策</span><b>{ledger?.policy?.version||'strategy-v5-p0'}</b><small>需按机构政策校准</small></div></div></div>
  <div className="topic-grid wide">{topics.map(t=><button key={t.id} className={'topic'+(selected===t.id?' sel':'')} onClick={()=>setSelected(t.id)}><div className="top"><span className="tid">{t.id.slice(0,8)} · {t.universe}</span><span className="badge live">{statusText(t.status)}</span></div><h3>{t.name}</h3><div className="act">{t.development_start||''} → {t.development_end||''}</div><div className="bar"><i style={{width:Math.min(100,(t.k??0)/Math.max(1,t.max_trials)*100)+'%'}}/></div><div className="meta"><span>分支 <b>{t.branch_count}</b></span><span>试验 <b>{t.trial_count}</b></span><span>预算 <b>{t.max_trials}</b></span></div></button>)}</div>
  <div className="ops-grid"><div>{ledger&&<LedgerCard ledger={ledger} busy={busy} run={run} openReport={openReport}/>}</div><aside className="side"><SystemStatus/></aside></div></>)}
 {tab==='manual'&&<ManualView ledger={ledger} busy={busy} run={run} openReport={openReport}/>}
 {tab==='review'&&<div className="card"><div className="card-head"><h2>策略审查</h2><span className="fine">独立复核角色可见；研究员不能自审</span></div><div className="card-body">{reviewErr?<p className="hint">{reviewErr} <Link className="text-link" to="/quant/reviews/factors">前往统一审查入口</Link></p>:reviewQueue.length===0?<p className="empty">待我复核的策略候选为空。</p>:<ul>{reviewQueue.map(x=><li key={x.id}><b>{x.topic_name}</b> · {x.id.slice(0,8)}<p className="fine">{x.hypothesis}</p></li>)}</ul>}<p className="fine">复核人可在统一审查入口查看封存结果、全量试验并批准/驳回；批准只授予研究用途。</p></div></div>}
 {tab==='library'&&<LibraryView library={library}/>}
 {tab==='capability'&&<CapabilityView/>}
 {report&&<ReportCard report={report} onClose={()=>setReport(undefined)}/>}
 </>;
}

function LedgerCard({ledger,busy,run,openReport}:{ledger:Ledger;busy:boolean;run:(p:string,k:string)=>Promise<void>;openReport:(id:string)=>Promise<void>}){
 return <div className="card"><div className="card-head"><div><div className="row-flex"><span className="tid">{ledger.topic.id.slice(0,8)}</span><h2>{ledger.topic.name}</h2></div><p className="fine">{ledger.topic.universe} / {ledger.topic.benchmark} · K {ledger.k} / {ledger.topic.max_trials} · 策略门槛 {ledger.policy?.version||''} · IR 门槛 {ledger.ir_threshold?.toFixed(2)??'—'}</p></div></div><div className="card-body">
  {ledger.branches.map(b=>{const bt=ledger.trials.filter(t=>t.branch_id===b.id&&!t.rerun_of).slice(-1)[0];const g=bt?.effective_gate||bt?.gate;const gatePassed=!!(g?.complete&&g.passed);
   return <div className="branch human" key={b.id}><div className="bh"><span className="hid">{b.id.slice(0,8)}</span><span className="bt">{b.hypothesis}</span><span className="by">v{b.version} · {(b.recipe.factors||[]).map(f=>f.factor).join(' + ')} · TopN {b.recipe.top_n} / {b.recipe.rebalance_days}日 · {branchStatusText(b)}{b.sealed?' · 封存 '+b.sealed.status:''}</span></div><div className="form-actions">
    <button className="btn small primary" disabled={busy||b.status!=='active'} onClick={()=>void run('/branches/'+b.id+'/backtest','backtest')}>运行真实回测</button>
    <button className="btn small" disabled={busy||b.status!=='active'} onClick={()=>void run('/branches/'+b.id+'/diagnostics/cost-2x','cost')}>2×成本</button>
    <button className="btn small" disabled={busy||b.status!=='active'} onClick={()=>void run('/branches/'+b.id+'/diagnostics/neighborhood','nbhd')}>3×3邻域（9次）</button>
    {b.status==='active'&&<button className="btn small" disabled={busy||!gatePassed} title={gatePassed?'':'研发与稳健性门槛未全部通过'} onClick={()=>void run('/branches/'+b.id+'/seal','seal')}>申请封存</button>}
    {b.status==='frozen'&&b.review_status==='sealed_passed'&&<button className="btn small primary" disabled={busy} onClick={()=>void run('/branches/'+b.id+'/submit-review','submit')}>提交复核</button>}
   </div>{b.sealed&&<p className="fine">封存 {b.sealed.status}{b.sealed.result?.excess_return!=null?` · 区间累计超额 ${pct(b.sealed.result.excess_return)}`:''}{b.sealed.gate?.basis==='annual'&&b.sealed.gate?.checks?.[0]?.actual!=null?` · 年化超额 ${pct(b.sealed.gate.checks[0].actual)}`:b.sealed.gate?.checks?.[0]?.actual!=null?' · 封存超额为旧口径（累计）':''}。封存失败保持失败，不进入复核。</p>}</div>;})}
  {ledger.branches.length===0&&<p className="empty">课题没有分支。</p>}
  <h3 style={{marginTop:14}}>策略台账</h3><div className="table-wrap"><table className="table strategy-table"><thead><tr><th>#</th><th>分支</th><th>状态</th><th>扣费后超额</th><th>IR</th><th>相对回撤</th><th>单边年换手</th><th>门槛</th><th>报告</th></tr></thead><tbody>{ledger.trials.map(t=>{const ex=check(t,'超额'),ir=check(t,'信息比率'),dd=check(t,'回撤'),to=check(t,'换手');return <tr key={t.id}><td>{t.trial_no}{t.rerun_of?'（rerun）':''}</td><td>{t.branch_id.slice(0,8)}</td><td className="nowrap">{t.outcome} · {outcomeText(t)}</td><td>{pct(ex?.actual)}{legacyGate(t.effective_gate||t.gate)&&<span className="fine">（旧）</span>}</td><td>{ir?.actual==null?'—':ir.actual.toFixed(2)}</td><td>{pct(dd?.actual)}</td><td>{to?.actual==null?'—':to.actual.toFixed(1)+'×'}</td><td>{gateText(t)}</td><td>{t.report_id?<button className="text-link" disabled={!t.id} onClick={()=>void openReport(t.id)}>真实报告</button>:'—'}</td></tr>;})}</tbody></table></div>
  {ledger.trials.length===0&&<p className="empty">尚无回测记录。</p>}
  <p className="fine">口径：扣费后年化超额相对课题基准；IR=日超额均值/跟踪误差年化；相对回撤按策略/基准净值；换手为单边年化。2 倍成本与 3×3 邻域为稳健性检验，不计 K；未执行时标“待补”，不冒充整体通过。</p>
 </div></div>;
}

function ManualView({ledger,busy,run,openReport}:{ledger:Ledger|null;busy:boolean;run:(p:string,k:string)=>Promise<void>;openReport:(id:string)=>Promise<void>}){
 const [tool,setTool]=useState<'recipe'|'test'|'robust'|'seal'|'submit'>('recipe');
 const [branchId,setBranchId]=useState<string>();
 const [diag,setDiag]=useState<Record<string,{payload:{cells?:Array<{top_n:number;rebalance_days:number;excess:number;ir:number;passed:boolean}>;passed_cells?:number}}>>({});
 const branch=ledger?.branches.find(b=>b.id===branchId)||ledger?.branches[0];
 useEffect(()=>{if(!ledger||!branch){return;}setBranchId(cur=>cur&&ledger.branches.some(b=>b.id===cur)?cur:ledger.branches[0]?.id);},[ledger?.topic.id]);
 useEffect(()=>{if(tool!=='robust'||!branch)return;let alive=true;void researchFetch('/api/inst/quant/strategy-research/branches/'+encodeURIComponent(branch.id)+'/diagnostics').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d)setDiag(d.diagnostics||{});});return()=>{alive=false;};},[tool,branch?.id]);
 if(!ledger)return <div className="card card-pad"><p className="empty">先在“研究运行”选择课题。</p></div>;
 if(!branch)return <div className="card"><div className="card-body empty"><b>还没有接手的版本</b>在研究运行里选择一个版本，点“运行真实回测”或新建分支。<div style={{marginTop:12}}><Link className="btn primary" to="/quant/strategy">去研究运行</Link></div></div></div>;
 const trials=ledger.trials.filter(t=>t.branch_id===branch.id);
 const latest=trials.filter(t=>!t.rerun_of).slice(-1)[0];
 const gate=latest?.effective_gate||latest?.gate;
 const k=ledger.k, bar=ledger.ir_threshold;
 const tools:[typeof tool,string][]=[['recipe','配方'],['test','回测'],['robust','稳健性'],['seal','封存验证'],['submit','提交']];
 const nb=diag.neighborhood?.payload;
 const body=tool==='recipe'?<>
   <div className="kv"><span>因子与方向</span><div>{(branch.recipe.factors||[]).map(f=>f.factor+'/'+f.direction).join(' + ')}</div><span>持仓与调仓</span><div>TopN {branch.recipe.top_n} · {branch.recipe.rebalance_days} 日 · buffer {branch.recipe.buffer??0}</div><span>股票池/区间/成本</span><div>{ledger.topic.universe} / {ledger.topic.benchmark} · 由课题固定；单边成本按课题设定</div></div>
   <p className="hint">只开放受控模板参数；任意代码策略、优化器不在本期。修改配方需新建分支。</p>
   <div className="form-actions"><Link className="btn" to="/quant/factor/library">从因子库选择</Link><Link className="btn" to="/quant/strategy">新建分支</Link></div>
  </>:tool==='test'?<>
   <p className="fine">本次回测将记为课题第 {k+1} 次，IR 门槛升到 {bar?.toFixed(2)??'—'}。</p>
   <div className="form-actions" style={{marginTop:8}}><button className="btn primary" disabled={busy||branch.status!=='active'} onClick={()=>void run('/branches/'+branch.id+'/backtest','backtest')}>运行回测</button>{latest&&<button className="btn" onClick={()=>void openReport(latest.id)}>查看完整报告</button>}<span className="fine">真实 RE；确定性重算不计 K</span></div>
   {gate&&<div className="table-wrap" style={{marginTop:12}}><table className="table"><thead><tr><th>门槛</th><th>实际</th><th>要求</th><th>结果</th></tr></thead><tbody>{(gate.checks||[]).map(c=><tr key={c.name}><td>{c.name}</td><td>{c.actual==null?'—':Number(c.actual).toFixed(4)}</td><td>{c.threshold==null?'—':Number(c.threshold).toFixed(3)}</td><td className={c.passed?'ok-t':c.passed===false?'bad-t':''}>{c.passed==null?'待补':c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div>}
  </>:tool==='robust'?<>
   <p className="fine">2 倍成本与 3×3 邻域为稳健性检查，不计 K。邻域按年化超额 ≥3% 且 IR ≥0.5 判定。</p>
   <div className="form-actions" style={{marginTop:8}}><button className="btn" disabled={busy||branch.status!=='active'} onClick={()=>void run('/branches/'+branch.id+'/diagnostics/cost-2x','cost')}>2 倍成本</button><button className="btn" disabled={busy||branch.status!=='active'} onClick={()=>void run('/branches/'+branch.id+'/diagnostics/neighborhood','nbhd')}>3×3 邻域（9 次）</button></div>
   {nb?.cells?<div style={{marginTop:12}}><p>邻域：{nb.passed_cells}/9 通过</p><div className="table-wrap"><table className="table"><thead><tr><th>TopN</th><th>调仓</th><th>年化超额</th><th>IR</th><th>结果</th></tr></thead><tbody>{nb.cells.map((c,i)=><tr key={i}><td>{c.top_n}</td><td>{c.rebalance_days}</td><td>{pct(c.excess)}</td><td>{c.ir?.toFixed(2)}</td><td className={c.passed?'ok-t':'bad-t'}>{c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div></div>:<p className="empty">尚未执行邻域诊断。</p>}
  </>:tool==='seal'?<>
   <p className="fine">封存期每个候选只能使用一次；封存扣费后年化超额 &gt; 0 且 IR ≥ 0.3 才通过。失败保持失败，不进入复核。</p>
   {branch.sealed?<p>封存 {branch.sealed.status}{branch.sealed.result?.excess_return!=null?` · 区间累计超额 ${pct(branch.sealed.result.excess_return)}`:''}{branch.sealed.gate?.basis==='annual'&&branch.sealed.gate?.checks?.[0]?.actual!=null?` · 年化超额 ${pct(branch.sealed.gate.checks[0].actual)}`:''}</p>:<button className="btn primary" disabled={busy||branch.status!=='active'||!(gate?.complete&&gate.passed)} onClick={()=>void run('/branches/'+branch.id+'/seal','seal')}>申请封存验证</button>}
   {!(gate?.complete&&gate.passed)&&!branch.sealed&&<p className="hint warning">研发与稳健性门槛未全部通过，不能申请封存。</p>}
  </>:<>
   <p className="fine">封存通过后由独立复核人在审查中心决定是否入库；研究员不能审批自己的候选。</p>
   <button className="btn primary" disabled={busy||branch.status!=='frozen'||branch.review_status!=='sealed_passed'} onClick={()=>void run('/branches/'+branch.id+'/submit-review','submit')}>{branch.review_status==='submitted'?'已提交':'提交审查'}</button>
   {branch.review_status!=='sealed_passed'&&<p className="hint">封存验证通过后才能提交。</p>}
  </>;
 return <><div className="status-strip"><span className="status-icon">⌁</span><div className="status-main"><b>{ledger.topic.name} / {branch.id.slice(0,8)} · {branch.hypothesis.slice(0,40)}</b><p>课题台账 K={k} · 当前 IR 门槛 {bar?.toFixed(2)??'—'} · 预算 {k}/{ledger.topic.max_trials} · 分支状态 {branchStatusText(branch)}</p></div><div className="actions">{ledger.branches.length>1&&<select value={branch.id} onChange={e=>setBranchId(e.target.value)}>{ledger.branches.map(b=><option key={b.id} value={b.id}>{b.id.slice(0,8)} · v{b.version}</option>)}</select>}</div></div>
 <div className="wb-grid"><div><div className="tool-tabs">{tools.map(([id,label])=><button key={id} className={tool===id?'on':''} onClick={()=>setTool(id)}>{label}</button>)}</div><div className="card"><div className="card-body">{body}</div></div></div>
 <div className="card asst"><div className="card-head"><h2>研究助手</h2></div><div className="chat"><div className="msg ai">已加载 {branch.id.slice(0,8)}。助手只写草稿，执行由你确认；策略助手接口尚未接入，本区暂不产生模型建议。</div></div><div className="compose"><div className="qp"><button disabled>为什么不达标</button><button disabled>怎么降换手</button><button disabled>过拟合风险</button></div></div></div></div></>;
}
function LibraryView({library}:{library:Array<{id:string;topic_name:string;hypothesis:string;recipe:{factors?:Array<{factor:string}>;top_n:number;rebalance_days:number};version:number;trial_count:number;sealed_result?:{excess_return?:number}}>}){
 return <div className="card"><div className="card-head"><h2>策略库</h2><span className="fine">仅复核批准的研究用途版本；组合模块只读选用</span></div><div className="card-body">{library.length===0?<p className="empty">暂无已入库策略；需完成封存并通过独立复核。</p>:<div className="table-wrap"><table className="table"><thead><tr><th>课题</th><th>版本</th><th>配方</th><th>试验</th><th>封存超额</th><th>假设</th></tr></thead><tbody>{library.map(x=><tr key={x.id}><td>{x.topic_name}</td><td>v{x.version} · {x.id.slice(0,8)}</td><td>{(x.recipe.factors||[]).map(f=>f.factor).join(' + ')} · TopN {x.recipe.top_n} / {x.recipe.rebalance_days}日</td><td>{x.trial_count}</td><td>{x.sealed_result?.excess_return==null?'—':pct(x.sealed_result.excess_return)}</td><td className="fine">{x.hypothesis.slice(0,80)}</td></tr>)}</tbody></table></div>}</div></div>;
}

function CapabilityView(){
 const units=[
  ['S0 研究决策','复用 F0 决策引擎，真实回测','可用'],
  ['S5 封存验证','独立区间执行，超额>0 且 IR≥0.3','可用（真实执行）'],
  ['S6 独立复核','复核人领取/批准/驳回，不能自审','可用（需复核角色）'],
  ['RE 策略回测','共享 9527 factor_refs','可用'],
  ['六门槛','超额/IR/相对回撤/换手/2×成本/邻域','可用（policy strategy-v5-p0）'],
  ['策略库','已批准版本只读列表','可用（当前为空）'],
  ['参数优化器','多种模板/优化器','未接入（M2 不做）'],
  ['模拟跟踪','观察中/待组合评估','未接入（M4）'],
 ];
 return <div className="card"><div className="card-head"><h2>能力与评测</h2><span className="fine">按真实接入状态展示，不填评测分</span></div><div className="card-body"><div className="table-wrap"><table className="table"><thead><tr><th>能力</th><th>实现</th><th>状态</th><th>评测分</th></tr></thead><tbody>{units.map(([n,d,s])=><tr key={n}><td>{n}</td><td className="fine">{d}</td><td><span className={'badge '+(s==='可用'||s.startsWith('可用')?'live':'gray')}>{s}</span></td><td>待接入</td></tr>)}</tbody></table></div><p className="fine">缺口：冲击成本与容量未建模；buffer 未在生成代码中建模；未接入参数优化器与模拟跟踪。</p></div></div>;
}

function ReportCard({report,onClose}:{report:Report;onClose:()=>void}){
 const t=report.trial,g=t.effective_gate||t.gate;
 const cost=report.diagnostics?.cost_2x?.payload as {excess?:number;passed?:boolean}|undefined;
 const nb=report.diagnostics?.neighborhood?.payload as {passed_cells?:number;cells?:Array<{top_n:number;rebalance_days:number;excess:number;ir:number;passed:boolean}>}|undefined;
 return <div className="card" style={{marginTop:16}}><div className="card-head"><div><h2>试验报告 · #{t.trial_no}</h2><p className="fine">{report.topic.name} / {report.topic.universe} · {report.topic.development_start} → {report.topic.development_end} · 分支 {report.branch.id.slice(0,8)}</p></div><button className="btn small" onClick={onClose}>关闭</button></div><div className="card-body">
  <div className="kv"><span>执行状态</span><div>{t.outcome} · {outcomeText(t)}</div><span>策略</span><div>{(report.branch.recipe.factors||[]).map(f=>f.factor+'/'+f.direction).join(' + ')} · TopN {report.branch.recipe.top_n} / {report.branch.recipe.rebalance_days}日</div><span>成本</span><div>{report.policy?.version} · 单边成本按课题设定；执行 next_open，未建模冲击成本与容量</div></div>
  <h3>净值与基准</h3><NavChart strategy={t.report?.equity_curve} benchmark={t.report?.benchmark_curve}/>
  <p className="fine">区间累计超额（另列，不参与门槛）：{pct(t.report?.period_excess)}。年化门槛见下表。</p>
  <h3>分年表现</h3>{(t.report?.annual_returns||[]).length===0?<p className="empty">该试验未保存分年表现（旧试验）。</p>:<div className="table-wrap"><table className="table"><thead><tr><th>年度</th><th>策略收益</th></tr></thead><tbody>{(t.report?.annual_returns||[]).map(x=><tr key={x.year}><td>{x.year}</td><td>{pct(x.return_value)}</td></tr>)}</tbody></table></div>}
  <h3>绩效（相对课题基准）</h3><div className="table-wrap"><table className="table"><thead><tr><th>扣费后年化超额</th><th>IR</th><th>相对回撤</th><th>单边年换手</th><th>策略年化（净）</th><th>组合最大回撤</th></tr></thead><tbody><tr><td>{pct(check(t,'超额')?.actual)}</td><td>{check(t,'信息比率')?.actual==null?'—':Number(check(t,'信息比率')?.actual).toFixed(2)}</td><td>{pct(check(t,'回撤')?.actual)}</td><td>{check(t,'换手')?.actual==null?'—':Number(check(t,'换手')?.actual).toFixed(1)+'×'}</td><td>{pct(t.metrics?.annual_return)}</td><td>{pct(t.metrics?.max_drawdown==null?undefined:Math.abs(Number(t.metrics.max_drawdown)))}</td></tr></tbody></table></div>
  <p className="fine">引擎返回的是扣费后净值与相对基准区间超额；未单独返回毛收益与基准曲线到台账，报告不伪造“扣费前”。</p>
  <h3>六项门槛（当前 K 校正）</h3>{legacyGate(g)&&<p className="hint warning">该试验为年化口径修正前的历史结果，下列数值仅为旧口径记录，不能作为正式验收；需用同配方重跑后按年化门槛判断。</p>}<div className="table-wrap"><table className="table"><thead><tr><th>检查</th><th>实际</th><th>要求</th><th>结果</th></tr></thead><tbody>{(g?.checks||[]).map(c=><tr key={c.name}><td>{c.name}</td><td>{c.actual==null?'—':Number(c.actual).toFixed(4)}</td><td>{c.threshold==null?'—':Number(c.threshold).toFixed(3)}</td><td className={c.passed?'ok-t':c.passed===false?'bad-t':''}>{c.passed==null?'待补':c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div>
  <h3>稳健性</h3><p>2 倍成本：{cost?.excess==null?'未执行':(pct(cost.excess)+' · '+(cost.passed?'通过':'未通过'))}</p><p>参数邻域：{nb?.passed_cells==null?'未执行':`${nb.passed_cells}/9 通过`}</p>{nb?.cells&&<div className="table-wrap"><table className="table"><thead><tr><th>TopN</th><th>调仓</th><th>超额</th><th>IR</th><th>结果</th></tr></thead><tbody>{nb.cells.map((c,i)=><tr key={i}><td>{c.top_n}</td><td>{c.rebalance_days}</td><td>{pct(c.excess)}</td><td>{c.ir?.toFixed(2)}</td><td className={c.passed?'ok-t':'bad-t'}>{c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div>}
  <h3>封存</h3><p>{report.sealed?`${report.sealed.status} · 区间累计超额 ${report.sealed.result?.excess_return==null?'—':pct(report.sealed.result.excess_return)} · ${report.sealed.gate?.basis==='annual'?'年化超额':'封存超额（旧口径）'} ${report.sealed.gate?.checks?.[0]?.actual==null?'—':pct(report.sealed.gate.checks[0].actual)} · 报告 ${report.sealed.report_id||'—'}`:'尚无封存记录。封存通过后才可提交独立复核。'}</p>
 </div></div>;
}

function NavChart({strategy,benchmark}:{strategy?:CurvePoint[];benchmark?:CurvePoint[]}){
 if(!strategy?.length||!benchmark?.length)return <p className="empty">该试验未保存净值曲线（旧试验）；新试验会保存策略与基准曲线。</p>;
 const w=760,h=190,pad=34;
 const byDate=new Map(benchmark.map(p=>[p.date,p.value]));
 const rows0=strategy.filter(p=>byDate.has(p.date));
 const step=Math.max(1,Math.ceil(rows0.length/240));
 const rows=rows0.filter((_,i)=>i%step===0||i===rows0.length-1);
 if(rows.length<2)return <p className="empty">曲线日期不足，无法绘制。</p>;
 const s0=rows[0].value,b0=byDate.get(rows[0].date)||1;
 const s=rows.map(p=>p.value/s0),b=rows.map(p=> (byDate.get(p.date)||b0)/b0);
 const all=[...s,...b],min=Math.min(...all),max=Math.max(...all),span=max-min||1;
 const x=(i:number)=>pad+i*(w-2*pad)/(rows.length-1), y=(v:number)=>h-pad-(v-min)/span*(h-2*pad);
 const path=(arr:number[])=>arr.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
 return <div><svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="策略与基准净值对比" style={{background:'#fff',border:'1px solid var(--line)',borderRadius:8}}>
  <line x1={pad} y1={y(min)} x2={w-pad} y2={y(min)} stroke="#E5E7EB"/><line x1={pad} y1={y(max)} x2={w-pad} y2={y(max)} stroke="#E5E7EB"/>
  <path d={path(b)} fill="none" stroke="#2F6DB0" strokeWidth="2"><title>基准净值</title></path>
  <path d={path(s)} fill="none" stroke="#65358D" strokeWidth="2"><title>策略净值</title></path>
  <text x={pad} y={12} fontSize="10" fill="#6d5f7a">归一化净值 · {rows[0].date} → {rows[rows.length-1].date}</text>
  <text x={pad} y={h-8} fontSize="10" fill="#6d5f7a">低 {min.toFixed(3)}</text><text x={w-pad} y={h-8} fontSize="10" fill="#6d5f7a" textAnchor="end">高 {max.toFixed(3)}</text>
 </svg><div className="fine" style={{display:'flex',gap:16,marginTop:6}}><span><i style={{display:'inline-block',width:12,height:2,background:'#65358D',marginRight:6}}/>策略</span><span><i style={{display:'inline-block',width:12,height:2,background:'#2F6DB0',marginRight:6}}/>基准</span></div></div>;
}

function SystemStatus(){
 const rows=[['S0','研究决策','复用 F0 决策引擎；每课题一个'],['S1','因子选择','从因子库选择；导入资产标注未复核'],['S2','配方构造','受控模板：1–3 因子等权、TopN、调仓'],['S3','回测与诊断','真实 RE；成本与参数邻域可复算'],['S4','稳健性检验','2×成本与 3×3 邻域；不计 K'],['S5','独立复核','封存→提交→复核；不能自审']];
 return <div className="card"><div className="card-head"><div><h2>研究系统组成</h2></div><span className="fine">按真实状态</span></div><div className="card-body"><div className="units">{rows.map(([id,n,d])=><div className="unit" key={id}><span className="ui">{id}</span><div><b>{n}</b><small>{d}</small></div></div>)}</div></div></div>;
}
