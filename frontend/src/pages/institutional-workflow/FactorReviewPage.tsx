import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {researchFetch,subscribeAuth} from '@/lib/researchClient';
import {reviewLabels} from './FactorReviewRequest';
import {FactorNoveltyEvidence,type NoveltyEvidence} from './FactorNoveltyEvidence';
import {WorkspaceHeading,FactorModuleTabs} from './QuantWorkspacePages';

type Check={name:string;actual:number|null;operator:string;threshold:number|boolean;passed:boolean;reason?:string};
type Item={id:string;name?:string;snapshot_hash:string;status:string;
 archive:{note:string;review:{status:string;question:string;decision?:string;note?:string;independent_opinion?:{verdict:string;rationale:string;limitations:string[];generated_at:string;model?:string}}};
 snapshot?:{name:string;plan:Record<string,unknown>;request:Record<string,unknown>};
 evidence?:Record<string,{novelty?:NoveltyEvidence;run_id:string;report_id?:string;gate?:{passed:boolean;checks:Check[]}}>;
 k?:number;threshold?:number|null;trials?:Array<{trial_no:number;branch_id:string;outcome:string;report_id?:string|null;rerun_of?:string|null}>};

async function api<T>(path:string,body?:unknown):Promise<T>{
 const r=await researchFetch('/api/factor-workflow/reviews'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const d=await r.json();
 if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'复核服务暂不可用');
 return d;
}

export function FactorReviewPage(){
 const [items,setItems]=useState<Item[]>([]),[current,setCurrent]=useState<Item>(),[error,setError]=useState(''),[busy,setBusy]=useState(false),[note,setNote]=useState(''),[decision,setDecision]=useState('needs_revision'),[ack,setAck]=useState(false);
 const serial=useRef(0);
 useEffect(()=>{let alive=true;const n=++serial.current;void api<{candidates:Item[]}>('').then(d=>{if(alive&&n===serial.current)setItems(d.candidates);}).catch(e=>{if(alive)setError(e.message);});const off=subscribeAuth(()=>{++serial.current;setItems([]);setCurrent(undefined);setNote('');});return()=>{alive=false;++serial.current;off();};},[]);
 async function select(id:string){const n=++serial.current;setBusy(true);setError('');setCurrent(undefined);setNote('');setDecision('needs_revision');setAck(false);try{const c=await api<Item>('/'+id);if(n===serial.current)setCurrent(c);}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 async function generateOpinion(){if(!current||busy)return;const n=serial.current;setBusy(true);setError('');try{const c=await api<Item>('/'+current.id+'/independent-opinion',{});if(n===serial.current)setCurrent(c);}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 async function save(value=decision){if(!current||busy)return;const n=serial.current;setBusy(true);setError('');try{const c=await api<Item>('/'+current.id,{decision:value,note});if(n===serial.current){setCurrent(c);setItems(a=>a.map(x=>x.id===c.id?{...x,...c}:x));setAck(false);}}catch(e){if(n===serial.current)setError(e instanceof Error?e.message:String(e));}finally{if(n===serial.current)setBusy(false);}}
 const development=current?.evidence?.development;
 const checks=development?.gate?.checks||[];
 return <><WorkspaceHeading title="审查" description="独立复核冻结证据；只看候选、门槛与课题全部试验，不共享研究对话。"><span className="fine">仅复核权限可用</span></WorkspaceHeading><FactorModuleTabs active="review"/>
 {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
 <div className="rv-grid">
  <aside className="queue">{items.length===0?<div className="card card-pad"><p className="empty">没有待审候选</p></div>:items.map(i=><button key={i.id} disabled={busy} className={'qi'+(current?.id===i.id?' sel':'')} onClick={()=>void select(i.id)}><span className="subtle">{i.id.slice(0,8)} · {i.status}</span><b>{i.name||i.snapshot?.name||i.id}</b><small>{i.archive.review.status==='requested'?'待复核':'已复核'}</small></button>)}</aside>
  <div>
   {!current?<div className="card card-pad"><p className="empty">选择左侧候选查看冻结证据。</p></div>:<>
    <div className="card"><div className="card-head"><div><div className="row-flex"><span className="subtle">{current.id.slice(0,8)}</span><h2>{current.snapshot?.name||current.name}</h2><span className={'badge '+(current.archive.review.status==='requested'?'live':'gray')}>{current.archive.review.status}</span></div><p className="fine">固定版本 {current.snapshot_hash.slice(0,16)} · {current.status}</p></div><span className="subtle">独立复核只看冻结证据</span></div><div className="card-body"><div className="kv"><span>复核问题</span><div>{current.archive.review.question}</div><span>研究结论</span><div>{current.archive.note}</div></div></div></div>
    <div className="card"><div className="card-head"><h2>当前 K 与课题全部试验</h2><span className="fine">K {current.k??'—'} · t*(K) {current.threshold==null?'待接入':current.threshold.toFixed(3)}</span></div><div className="table-wrap"><table className="table"><thead><tr><th>试验</th><th>分支</th><th>结果</th><th>计入 K</th><th>报告</th></tr></thead><tbody>{(current.trials||[]).map(t=><tr key={t.trial_no}><td>#{t.trial_no}{t.rerun_of?'（rerun）':''}</td><td>{t.branch_id.slice(0,8)}</td><td>{t.outcome}</td><td>{t.rerun_of?'否':t.outcome}</td><td>{t.report_id?<Link className="btn small" to={'/quant/factor/report/'+t.report_id}>真实报告</Link>:'—'}</td></tr>)}</tbody></table></div>{(current.trials||[]).length===0&&<p className="card-pad empty">该候选没有关联 V5 课题台账，K/门槛不可用。</p>}</div>
    <div className="card"><div className="card-head"><h2>门槛检查</h2><span className="fine">按课题当前 K 校正</span></div><div className="table-wrap"><table className="table"><thead><tr><th>检查</th><th>实际</th><th>要求</th><th>结果</th></tr></thead><tbody>{checks.map(c=><tr key={c.name}><td>{c.name}</td><td>{c.actual==null?'—':Number(c.actual).toFixed(4)}</td><td>{c.operator} {String(c.threshold)}</td><td className={c.passed?'ok-t':'bad-t'}>{c.passed?'通过':'未通过'}</td></tr>)}</tbody></table></div></div>
    <div className="card"><div className="card-head"><h2>独立复核意见</h2><span className="fine">冻结证据 · 不共享研究对话</span></div><div className="card-body">{current.archive.review.independent_opinion?<><p><strong>{current.archive.review.independent_opinion.verdict}</strong> · {current.archive.review.independent_opinion.generated_at}</p><p>{current.archive.review.independent_opinion.rationale}</p>{(current.archive.review.independent_opinion.limitations||[]).length>0&&<ul className="checklist">{(current.archive.review.independent_opinion.limitations||[]).map(x=><li key={x}>{x}</li>)}</ul>}<p className="fine">模型意见仅为建议；最终决定由人工复核人保存。</p></>:<><p className="hint">尚未生成。独立复核使用冻结证据、不看研究对话，不改变门槛。</p><button className="btn small" disabled={busy} onClick={()=>void generateOpinion()}>生成独立复核意见（模型）</button></>}</div></div>
    <div className="card"><div className="card-head"><h2>复核决定</h2><span className="fine">入库只授予研究用途</span></div><div className="card-body">{current.archive.review.status==='reviewed'?<div><strong>{reviewLabels[current.archive.review.decision||'']}</strong><p className="fine">{current.archive.review.note}</p></div>:<><label className="checks"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/> 我已查看全部试验、门槛与局限</label><label className="field" style={{display:'block',marginTop:10}}><span>复核依据</span><textarea rows={3} maxLength={3000} value={note} onChange={e=>setNote(e.target.value)}/></label><div className="decision" style={{marginTop:10}}><button className="btn primary" disabled={busy||!ack||!note.trim()} onClick={()=>void save('research_supported')}>{reviewLabels.research_supported}</button><button className="btn" disabled={busy||!note.trim()} onClick={()=>void save('needs_revision')}>{reviewLabels.needs_revision}</button><button className="btn danger" disabled={busy||!note.trim()} onClick={()=>void save('rejected')}>{reviewLabels.rejected}</button></div></>}</div></div>
    <FactorNoveltyEvidence evidence={development?.novelty} purpose={current.snapshot?.plan?.researchPurpose as string|undefined}/>
   </>}
  </div>
 </div>
 <StrategyReviewSection/>
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
