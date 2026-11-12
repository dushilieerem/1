import {formatGateNumber} from '@/lib/factorPresentation';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {researchFetch,subscribeAuth} from '@/lib/researchClient';
import {reviewLabels} from './FactorReviewRequest';
import {FactorNoveltyEvidence,type NoveltyEvidence} from './FactorNoveltyEvidence';
import {factorBusinessCategories,type ResearchAsset} from '@/lib/factorResearchAssets';
import {WorkspaceHeading,FactorModuleTabs,executionLabels} from './QuantWorkspacePages';

type Check={name:string;actual:number|null;operator:string;threshold:number|boolean;passed:boolean;reason?:string};
type Item={feedback_materials?:{missing:string[];allowed_decisions:string[];grants_admission:boolean};is_author?:boolean;admission?:{allowed:boolean;reason:string};review_actions?:{can_claim:boolean;can_decide:boolean};id:string;name?:string;snapshot_hash:string;status:string;
 archive:{research_asset?:ResearchAsset;note:string;review:{purpose?:string;status:string;question:string;decision?:string;note?:string;independent_opinion?:{verdict:string;rationale:string;limitations:string[];generated_at:string;model?:string}}};
 snapshot?:{name:string;plan:Record<string,unknown>;request:Record<string,unknown>};
 evidence?:Record<string,{novelty?:NoveltyEvidence;run_id:string;report_id?:string;gate?:{passed:boolean;checks:Check[]}}>;
 k?:number;threshold?:number|null;trials?:Array<{counts_toward_k?:boolean;trial_no:number;branch_id:string;branch_label?:string;outcome:string;report_id?:string|null;rerun_of?:string|null}>;sealed?:{status:string;result?:Record<string,unknown>;report_id?:string;created_at?:string}|null};

async function api<T>(path:string,body?:unknown):Promise<T>{
 const r=await researchFetch('/api/factor-workflow/reviews'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const d=await r.json();
 if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'复核服务暂不可用');
 return d;
}

function ReviewDecisionDialog({title,busy,onClose,children,returnFocus}:{title:string;busy:boolean;onClose:()=>void;children:ReactNode;returnFocus:HTMLElement|null}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const trigger=returnFocus;const el=dialog.current;if(el){if(typeof el.showModal==='function')el.showModal();else el.setAttribute('open','');}return()=>{if(el?.open&&typeof el.close==='function')el.close();if(trigger?.isConnected)trigger.focus({preventScroll:true});else document.querySelector<HTMLElement>('[data-registered-asset-entry]')?.focus();};},[]);
 return <dialog ref={dialog} className="factor-review-dialog" aria-label={title} onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>{children}</dialog>;
}

export function FactorReviewPage(){
 const {pathname}=useLocation();
 return pathname.endsWith('/strategies')?<StrategyReviewSection/>:<FactorReviewContent/>;
}

function FactorReviewContent(){
 const [items,setItems]=useState<Item[]>([]),[current,setCurrent]=useState<Item>(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [evidence,setEvidence]=useState('');
 const [modal,setModal]=useState<'approve_research_and_register'|'research_supported'|'needs_revision'|'rejected'|null>(null);
 const [name,setName]=useState(''),[category,setCategory]=useState('待分类'),[tags,setTags]=useState(''),[note,setNote]=useState(''),[ack,setAck]=useState(false);
 const serial=useRef(0);const decisionTrigger=useRef<HTMLElement|null>(null);
 useEffect(()=>{let alive=true;const n=++serial.current;void api<{candidates:Item[]}>('').then(d=>{if(alive&&n===serial.current)setItems(d.candidates);}).catch(e=>{if(alive)setError(e.message);});const off=subscribeAuth(()=>{++serial.current;setItems([]);setCurrent(undefined);setModal(null);});return()=>{alive=false;++serial.current;off();};},[]);
 useEffect(()=>{if(!current&&items.length&&!busy)void select(items[0].id);},[items,current]);
 async function select(id:string){const n=++serial.current;setBusy(true);setError('');setCurrent(undefined);setModal(null);setEvidence('');try{const c=await api<Item>('/'+id);if(n===serial.current)setCurrent(c);}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 async function claim(){if(!current||busy)return;const n=serial.current;setBusy(true);setError('');try{const c=await api<Item>('/'+current.id+'/claim',{});if(n===serial.current)setCurrent(c);}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 async function generateOpinion(){if(!current||busy||!current.review_actions?.can_decide)return;const n=serial.current;setBusy(true);setError('');try{await api<unknown>('/'+current.id+'/independent-opinion',{});const c=await api<Item>('/'+current.id);if(n===serial.current)setCurrent(c);}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 function openDecision(value:NonNullable<typeof modal>){decisionTrigger.current=document.activeElement instanceof HTMLElement?document.activeElement:null;setModal(value);setName(current?.snapshot?.request?.factor_name as string||current?.snapshot?.name||'');setCategory('待分类');setTags('');setNote('');setAck(false);setError('');}
 async function save(){if(!current||!modal||busy||!current.review_actions?.can_decide)return;const n=serial.current;setBusy(true);setError('');try{await api<unknown>('/'+current.id,{decision:modal,note,...(modal==='approve_research_and_register'?{acknowledged:ack,display_name:name,category,tags:tags.split(/[，,、]/).map(x=>x.trim()).filter(Boolean)}:{})});const c=await api<Item>('/'+current.id);if(n===serial.current){setCurrent(c);setItems(a=>a.map(x=>x.id===c.id?{...x,...c}:x));setModal(null);}}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 const development=current?.evidence?.development;
 const checks=development?.gate?.checks||[];
 const noveltyOk=development?.novelty?.gate?.complete===true&&(current?.snapshot?.plan?.researchPurpose==='replication'||development?.novelty?.gate?.passed===true);
 const purpose=current?.archive.review.purpose;
 const admission=purpose==='research_admission';
 const replication=current?.snapshot?.plan?.researchPurpose==='replication';
 const canDecide=!!current?.review_actions?.can_decide;
 const registered=current?.archive.research_asset;
 const decisionLabel=modal==='approve_research_and_register'?(replication?'登记复现验证记录':'批准研究用途并入库'):modal==='needs_revision'?'复核不通过（任务结束）':modal==='rejected'?'驳回':'认可研究依据';
 const statusLabel=(value?:string)=>executionLabels[value||'']||({requested:'待审批',reviewed:'已决定',passed:'通过',failed:'未通过',error:'运行异常'}[value||'']||value||'未记录');
 return <><WorkspaceHeading eyebrow="FACTOR FACTORY" title="待审批" description="核对固定材料，由独立复核人作出研究用途决定。"/><FactorModuleTabs active="review"/>
 {error&&!modal&&<p className="hint error" role="alert">{error}</p>}
 {items.length>1&&<label className="field" style={{marginBottom:14}}><span>选择待处理事项</span><select disabled={busy} value={current?.id||''} onChange={e=>void select(e.target.value)}>{items.map(item=><option key={item.id} value={item.id}>{item.name||item.snapshot?.name||'未命名候选'} · {item.archive.review.status==='requested'?'待处理':'已决定'}</option>)}</select></label>}
 {!current?<div className="card card-pad"><p className="empty">{busy?'正在读取固定材料…':items.length?'选择事项查看材料':'暂无待处理的因子事项'}</p></div>:<div className="ff-stage-grid">
  <article className="card"><div className="card-head"><div><h2>{registered?.display_name||current.snapshot?.name||current.name}</h2><p>{purpose==='seal_failed_review'?'封存未通过 · 失败复盘':admission?(replication?'已有因子复现验证审批':'研究资产审批'):'研究反馈'} · {statusLabel(current.archive.review.status)}</p><div className="actions" style={{marginTop:8}}><span className="fine">{current.archive.review.status==='reviewed'?'复核已完成':current.is_author?'作者只读':current.review_actions?.can_claim?'未领取':canDecide?'我在复核':'已由其他复核人领取'}</span>{current.review_actions?.can_claim&&<button className="btn small primary" disabled={busy} onClick={()=>void claim()}>领取复核</button>}</div></div></div>
   <div className="card-body"><dl className="ff-kv"><dt>研究假设</dt><dd>{String(current.snapshot?.plan?.hypothesis||'未记录')}</dd><dt>实现</dt><dd>{String(current.snapshot?.request?.factor_name||'未记录')} · 固定版本</dd><dt>研发试验</dt><dd>已记录 {current.trials?.length||0} 次</dd><dt>独立验证</dt><dd>{current.sealed?statusLabel(current.sealed.status):'尚无封存记录'}</dd><dt>用途</dt><dd>机构内部研究，不授予实盘权限</dd></dl>
    {current.archive.review.status==='reviewed'&&<section className="hint" aria-label="复核结果" style={{marginTop:14}}><h3>复核已完成</h3><b>{reviewLabels[current.archive.review.decision||'']||'决定已保存'}</b><p>{current.archive.review.note||'未填写决定说明'}</p></section>}
    {registered&&<div className="hint success" style={{marginTop:14}}><b>{registered.kind==='replication_validation'?'复现验证记录已登记':'研究资产已登记'}</b><p>{registered.display_name} · 第 {registered.version} 版 · 研究用途</p><Link data-registered-asset-entry className="btn small" to={'/quant/factor/library?asset='+encodeURIComponent(registered.id)}>在因子库查看登记与报告</Link></div>}
    <hr className="ff-divider"/><div className="actions">{[['definition','查看定义与实现'],['reports','查看验证证据'],['trials','查看全部试验'],['opinion','独立分析意见']].map(([key,label])=><button className="btn small" key={key} onClick={()=>setEvidence(evidence===key?'':key)}>{label}</button>)}</div>
    {evidence&&<section style={{marginTop:16}}>
     {evidence==='definition'&&<><h3>冻结假设与实现</h3><p className="ff-copy">{String(current.snapshot?.plan?.hypothesis||'未记录')}</p>{current.snapshot?.request?.factor_code?<pre className="ff-code">{String(current.snapshot.request.factor_code)}</pre>:<p>已有定义：{String(current.snapshot?.request?.library_name||'未记录')} / {String(current.snapshot?.request?.factor_name||'未记录')}</p>}</>}
     {evidence==='reports'&&<><h3>研发门槛与独立验证</h3><div className="table-wrap"><table className="table"><thead><tr><th>检查</th><th>实际</th><th>要求</th><th>结论</th></tr></thead><tbody>{checks.map(c=><tr key={c.name}><td>{c.name}</td><td title={String(c.actual)}>{formatGateNumber(c.actual)}{c.reason&&<small>{c.reason}</small>}</td><td title={String(c.threshold)}>{c.operator} {formatGateNumber(c.threshold,'未记录')}</td><td>{c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div><p className="fine">封存：{statusLabel(current.sealed?.status)}；完整明细按当前身份可见。</p>{current.sealed?.result&&<div className="table-wrap"><table className="table"><thead><tr><th>独立验证检查</th><th>实际</th><th>要求</th><th>结论</th></tr></thead><tbody>{((current.sealed.result.gate as {checks?:Check[]}|undefined)?.checks||[]).map(c=><tr key={c.name}><td>{c.name}</td><td title={String(c.actual)}>{formatGateNumber(c.actual)}{c.reason&&<small>{c.reason}</small>}</td><td title={String(c.threshold)}>{c.operator} {formatGateNumber(c.threshold,'未记录')}</td><td>{c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div>}<FactorNoveltyEvidence evidence={development?.novelty} purpose={current.snapshot?.plan?.researchPurpose as string|undefined}/></>}
     {evidence==='trials'&&<><h3>全部试验与预算记录</h3><p className="fine">计入预算 {current.k??'未记录'} 次，当前统计门槛 {current.threshold==null?'未记录':current.threshold.toFixed(3)}</p><div className="table-wrap"><table className="table"><thead><tr><th>试验</th><th>分支</th><th>结果</th><th>计入预算</th></tr></thead><tbody>{(current.trials||[]).map(t=><tr key={t.trial_no}><td>{t.trial_no}</td><td>{t.branch_label||'分支未记录'}</td><td>{statusLabel(t.outcome)}</td><td>{t.counts_toward_k===true?'是':t.counts_toward_k===false?'否':'未确认'}</td></tr>)}</tbody></table></div></>}
     {evidence==='opinion'&&<><h3>独立分析意见</h3>{current.archive.review.independent_opinion?<><p>{current.archive.review.independent_opinion.rationale}</p><ul>{current.archive.review.independent_opinion.limitations.map(x=><li key={x}>{x}</li>)}</ul></>:<p className="fine">尚未生成独立意见。</p>}<button className="btn small" disabled={busy||!canDecide} onClick={()=>void generateOpinion()}>生成独立分析意见</button><p className="fine">模型意见是建议，不作批准决定。</p></>}
    </section>}
   </div>{purpose==='research_feedback_only'&&<details className="small-details"><summary>研究复盘的材料范围与缺项</summary><p>此事项仅用于研究复盘，不授予研究资产准入。</p>{[...new Set(current.feedback_materials?.missing||[])].map((text,i)=><p key={i}>{text}</p>)}</details>}<div className="card-footer">{current.is_author?<p className="fine">研究材料只读，审批由独立复核人处理。</p>:current.archive.review.status==='reviewed'?<p>{reviewLabels[current.archive.review.decision||'']||current.archive.review.decision} · {current.archive.review.note}</p>:<><div className="actions">{admission?<button className="btn small primary" disabled={busy||!canDecide||!current.admission?.allowed} onClick={()=>openDecision('approve_research_and_register')}>{replication?'登记复现验证记录':'批准研究用途并入库'}</button>:!['seal_failed_review','research_feedback_only'].includes(purpose||'')&&<button className="btn small primary" disabled={busy||!canDecide||!noveltyOk} onClick={()=>openDecision('research_supported')}>认可研究依据</button>}<button className="btn small" disabled={busy||!canDecide} onClick={()=>openDecision('needs_revision')}>复核不通过</button><button className="btn small" disabled={busy||!canDecide} onClick={()=>openDecision('rejected')}>驳回</button></div>{admission&&!current.admission?.allowed&&<p className="fine" style={{marginTop:8}}>{current.admission?.reason||'准入证据尚未完整，暂不能批准。'}</p>}</>}</div>
  </article><aside className="ff-live"><h3>独立审查</h3><div className="ff-now">人作决定，系统保留依据。</div><p>核对固定定义、全部试验、研发与独立验证证据及使用边界。</p><hr className="ff-divider"/><p>补证只补缺失材料；改变实现需要新的候选，不能覆盖冻结结果。</p><p>旧研究反馈与封存失败复盘不能直接升级成资产批准。</p></aside>
 </div>}
 {modal&&current&&<ReviewDecisionDialog returnFocus={decisionTrigger.current} title={decisionLabel} busy={busy} onClose={()=>setModal(null)}><form className="modal" onSubmit={e=>{e.preventDefault();void save();}}><div className="modal-header"><h2>{decisionLabel}</h2><button type="button" className="btn small" disabled={busy} onClick={()=>setModal(null)}>取消</button></div><div className="modal-body">{error&&<p className="hint error" role="alert">{error}</p>}{modal==='approve_research_and_register'&&<><label className="field"><span>因子名称</span><input autoFocus required maxLength={100} value={name} onChange={e=>setName(e.target.value)}/></label><label className="field"><span>业务分类</span><select value={category} onChange={e=>setCategory(e.target.value)}>{factorBusinessCategories.map(c=><option key={c}>{c}</option>)}</select></label><label className="field"><span>标签（选填，以逗号分隔）</span><input value={tags} onChange={e=>setTags(e.target.value)}/></label></>}<label className="field"><span>复核依据</span><textarea required maxLength={3000} value={note} onChange={e=>setNote(e.target.value)}/></label>{modal==='approve_research_and_register'&&<label className="checks"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>我已核对全部试验、冻结材料、封存结果与局限</label>}<div className="form-actions"><button className="btn primary" disabled={busy||!note.trim()||(modal==='approve_research_and_register'&&(!ack||!name.trim()||!current.admission?.allowed))}>{busy?'正在提交…':decisionLabel}</button></div></div></form></ReviewDecisionDialog>}
 </>;
}

type StrategyItem={id:string;topic_id:string;hypothesis:string;owner_id:number;status:string;review_status?:string;topic_name:string;universe:string;benchmark:string};
type StrategyDetail={branch:StrategyItem&{reviewer_id?:number|null;review_decision?:string;review_note?:string};topic:{name:string;universe:string;benchmark:string};trials:Array<{trial_no:number;outcome:string;rerun_of?:string|null;gate?:Gate;effective_gate?:Gate}>;effective_gate?:Gate;sealed?:{status:string;gate?:Gate;result?:{excess_return?:number;metrics?:Record<string,number>}}|null;events:Array<{action:string;note:string;created_at:string}>};
type Gate={checks?:Array<{name:string;actual:number|null;threshold?:number;passed:boolean|null}>;complete?:boolean;passed?:boolean;pending?:string[]};

function StrategyReviewSection(){
 const [items,setItems]=useState<StrategyItem[]>([]),[current,setCurrent]=useState<StrategyDetail>(),[error,setError]=useState(''),[busy,setBusy]=useState(false),[note,setNote]=useState(''),[denied,setDenied]=useState(false);
 const api=async(path:string,body?:unknown)=>{const r=await researchFetch('/api/inst/quant/strategy-research/reviews'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof (d.detail||d.error)==='string'?(d.detail||d.error):'策略复核服务不可用');return d;};
 useEffect(()=>{let alive=true;void researchFetch('/api/inst/quant/strategy-research/reviews').then(async r=>{if(!alive)return;if(r.status===403){setDenied(true);return;}const d=await r.json();if(!r.ok)throw Error(typeof (d.detail||d.error)==='string'?(d.detail||d.error):'策略复核服务不可用');setItems(d.branches||[]);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[]);
 async function select(id:string){setBusy(true);setError('');try{setCurrent(await api('/'+id));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 async function claim(id:string){setBusy(true);setError('');try{await api('/'+id+'/claim',{});setCurrent(await api('/'+id));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 async function save(id:string,decision:'approved'|'rejected'){if(!note.trim())return;setBusy(true);setError('');try{await api('/'+id,{decision,note});setItems(a=>a.filter(x=>x.id!==id));setCurrent(undefined);setNote('');}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 const g=current?.effective_gate;
 return <div className="card" style={{marginTop:16}}><div className="card-head"><h2>策略候选</h2><span className="fine">封存通过并提交的冻结配方；研究员不能自审</span></div><div className="card-body">
  {error&&<p className="hint error" role="alert">{error}</p>}
  {denied?<p className="hint">当前角色无策略复核权限；策略候选只对独立复核人展示。</p>:items.length===0?<p className="empty">没有待审策略候选</p>:<div className="queue" style={{display:'flex',gap:8,flexWrap:'wrap'}}>{items.map(i=><button key={i.id} className={'qi'+(current?.branch.id===i.id?' sel':'')} disabled={busy} onClick={()=>void select(i.id)}><span className="subtle">{i.id.slice(0,8)} · {i.status}</span><b>{i.topic_name}</b><small>{i.hypothesis.slice(0,60)}</small></button>)}</div>}
  {current&&<div style={{marginTop:12}}>
   <p className="fine">{current.topic.name} · {current.topic.universe}/{current.topic.benchmark} · 封存 {current.sealed?.status||'—'} · {current.branch.review_status||''}</p>
   <p>{current.branch.hypothesis}</p>
   <div className="table-wrap"><table className="table"><thead><tr><th>试验</th><th>结果</th><th>计入 K</th></tr></thead><tbody>{current.trials.map(t=><tr key={t.trial_no}><td>#{t.trial_no}{t.rerun_of?'（rerun）':''}</td><td>{t.outcome}</td><td>{t.rerun_of?'否':'是'}</td></tr>)}</tbody></table></div>
   <h4>门槛</h4><div className="table-wrap"><table className="table"><thead><tr><th>检查</th><th>实际</th><th>要求</th><th>结果</th></tr></thead><tbody>{(g?.checks||[]).map(c=><tr key={c.name}><td>{c.name}</td><td>{c.actual==null?'—':Number(c.actual).toFixed(4)}</td><td>{c.threshold==null?'—':Number(c.threshold).toFixed(3)}</td><td className={c.passed?'ok-t':c.passed===false?'bad-t':''}>{c.passed==null?'待补':c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div>
   <h4>封存结果</h4><p className="fine">{current.sealed?`${current.sealed.status} · 超额 ${current.sealed.result?.excess_return==null?'—':(Number(current.sealed.result.excess_return)*100).toFixed(2)+'%'}`:'尚无封存记录'}</p>
   {current.branch.reviewer_id==null?<button className="btn small" disabled={busy} onClick={()=>void claim(current.branch.id)}>领取复核</button>:<><label className="field" style={{display:'block',marginTop:10}}><span>复核依据</span><textarea rows={3} value={note} onChange={e=>setNote(e.target.value)}/></label><div className="decision" style={{marginTop:10}}><button className="btn primary" disabled={busy||!note.trim()} onClick={()=>void save(current.branch.id,'approved')}>批准入库</button><button className="btn danger" disabled={busy||!note.trim()} onClick={()=>void save(current.branch.id,'rejected')}>驳回</button></div></>}
  </div>}
 </div></div>;
}
