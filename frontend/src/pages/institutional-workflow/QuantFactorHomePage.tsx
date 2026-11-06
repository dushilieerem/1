import {useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactElement} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

type Topic={id:string;project_id:string;project_name:string;view_id:string;primary_holding_period:number;max_trials:number;max_sealed:number;sealed_used?:number;status:string;k:number;branch_count:number;trial_count:number;created_at?:string};
type Branch={id:string;topic_id:string;parent_id?:string|null;source:string;status:string;hypothesis_version:number;implementation_version:number;created_at?:string};
type Trial={trial_no:number;branch_id:string;kind:string;outcome:string;executor:string;report_id?:string|null;created_at?:string;returned_metrics?:boolean;rerun_of?:string|null;result_summary?:{gate?:{checks?:{name:string;actual:number|null;threshold:number;passed:boolean}[]}}};
type Ledger={topic:Topic;branches:Branch[];trials:Trial[];k:number;threshold:number|null;threshold_next_if_counted:number;next_trial_no:number};

const statusText=(s:string)=>s==='active'?'研究中':s==='paused'?'已暂停':s==='archived'?'已归档':s;
const outcomeText=(t:Trial)=>t.outcome==='passed'?'通过':t.outcome==='failed'?'未达标':t.outcome==='error'?'执行错误':t.outcome;
const nwText=(t:Trial)=>{const c=t.result_summary?.gate?.checks?.find(x=>x.name==='方向 NW t');return c&&typeof c.actual==='number'?` · NW t ${c.actual.toFixed(2)} / 需 ${c.threshold.toFixed(2)}`:'';};

export function QuantFactorHomePage(){
 const [topics,setTopics]=useState<Topic[]>([]);
 const [selected,setSelected]=useState<string>();
 const [ledger,setLedger]=useState<Ledger>();
 const [node,setNode]=useState<string>();
 const [f0,setF0]=useState<{id:string;status:string;decision?:{candidate_status?:string;reason?:string;steps?:Array<{step:number;decision:{action:string;rationale:string};usage?:{tokens_in?:number;tokens_out?:number};result:{status?:string;candidate_status?:string;reason?:string;needed_capabilities?:string[]}}>};stop_reason?:string}>();
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 const [pending,setPending]=useState<number|null>(null);
 const [sealedUsed,setSealedUsed]=useState<number|null>(null);
 const [authOpen,setAuthOpen]=useState(false);
 const treeRef=useRef<HTMLDivElement|null>(null);
 const [treeLines,setTreeLines]=useState<string[]>([]);
 const navigate=useNavigate();

 useEffect(()=>{
  let alive=true;setLoading(true);
  researchFetch('/api/inst/quant/factor-workflow/topics')
   .then(r=>r.ok?r.json():Promise.reject(Error('课题读取失败')))
   .then(d=>{if(!alive)return;const list=d.topics||[];setTopics(list);setSelected(cur=>cur&&list.some((t:Topic)=>t.id===cur)?cur:list[0]?.id);})
   .catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));})
   .finally(()=>{if(alive)setLoading(false);});
  void researchFetch('/api/inst/quant/factor-workflow/overview').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d?.counts)setSealedUsed(Number(d.counts.sealed_used)||0);});
  void researchFetch('/api/inst/quant/factor-workflow/pending-review-count').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d&&typeof d.count==='number')setPending(d.count);});
  return()=>{alive=false;};
 },[]);

 useEffect(()=>{
  if(!selected){setLedger(undefined);return;}
  let alive=true;
  researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(selected)+'/ledger')
   .then(r=>r.ok?r.json():Promise.reject(Error('研究树读取失败')))
   .then(d=>{if(!alive)return;setLedger(d);setNode(cur=>cur&&(d.branches||[]).some((b:Branch)=>b.id===cur)?cur:(d.branches||[])[0]?.id);void researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(selected)+'/f0-runs').then(r=>r.ok?r.json():null).then(f=>{if(alive)setF0(f||undefined);});})
   .catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));});
  return()=>{alive=false;};
 },[selected]);

 async function handBackF0(){
  if(!ledger||!selectedBranch)return;
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/branches/'+encodeURIComponent(selectedBranch.id)+'/f0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idempotency_key:crypto.randomUUID()})});
  const d=await r.json();if(!r.ok){setError(typeof d.detail==='string'?d.detail:'F0 启动失败');return;}setF0(d);
 }
 useEffect(()=>{if(!f0||!['queued','running'].includes(f0.status))return;const t=setInterval(()=>{void researchFetch('/api/inst/quant/factor-workflow/f0-runs/'+f0.id).then(r=>r.ok?r.json():null).then(d=>{if(d)setF0(d);});},4000);return()=>clearInterval(t);},[f0?.id,f0?.status]);
 async function setTopicStatus(status:'paused'|'active'){
  if(!ledger)return;
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/'+(status==='paused'?'pause':'resume'),{method:'POST'});
  const d=await r.json();if(!r.ok){setError(typeof d.detail==='string'?d.detail:'课题状态更新失败');return;}
  setTopics(list=>list.map(t=>t.id===d.id?{...t,status:d.status}:t));
 }
 async function resumeF0(){if(!f0)return;const r=await researchFetch('/api/inst/quant/factor-workflow/f0-runs/'+f0.id+'/resume',{method:'POST'});const d=await r.json();if(!r.ok){setError(typeof d.detail==='string'?d.detail:'F0 继续失败');return;}setF0(d);}
 async function takeOver(){
  if(!ledger||!selectedBranch)return;
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/branches/'+encodeURIComponent(selectedBranch.id)+'/takeover',{method:'POST'});
  if(!r.ok){const d=await r.json().catch(()=>({}));setError(typeof d.detail==='string'?d.detail:'接手失败');return;}
  navigate('/quant/factor/workflow/'+ledger.topic.project_id+'/F4');
 }
 const children=useMemo(()=>{const map=new Map<string,Branch[]>();for(const b of ledger?.branches||[])map.set(b.parent_id||'root',[...(map.get(b.parent_id||'root')||[]),b]);return map;},[ledger]);
 const trialsByBranch=useMemo(()=>{const map=new Map<string,Trial[]>();for(const t of ledger?.trials||[])map.set(t.branch_id,[...(map.get(t.branch_id)||[]),t]);return map;},[ledger]);
 useLayoutEffect(()=>{
  const root=treeRef.current;
  if(!root){setTreeLines([]);return;}
  const draw=()=>{
   const cr=root.getBoundingClientRect();
   const cards=new Map<string,DOMRect>();
   root.querySelectorAll<HTMLElement>('[data-bid]').forEach(el=>cards.set(el.dataset.bid||'',el.getBoundingClientRect()));
   const paths:string[]=[];
   for(const b of ledger?.branches||[]){
    if(!b.parent_id)continue;
    const p=cards.get(b.parent_id),c=cards.get(b.id);
    if(!p||!c)continue;
    const x=c.left-cr.left-14, y1=p.bottom-cr.top, y2=c.top-cr.top+c.height/2;
    paths.push(`M ${x} ${y1} L ${x} ${y2} L ${c.left-cr.left} ${y2}`);
   }
   setTreeLines(paths);
  };
  const raf=requestAnimationFrame(draw);
  window.addEventListener('resize',draw);
  return ()=>{cancelAnimationFrame(raf);window.removeEventListener('resize',draw);};
 },[ledger]);
 const topic=topics.find(t=>t.id===selected);
 const selectedBranch=(ledger?.branches||[]).find(b=>b.id===node);
 const feed=useMemo(()=>[...(ledger?.trials||[])].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||'')).slice(0,12),[ledger]);
 const totalTrials=topics.reduce((n,t)=>n+t.trial_count,0);
 const capabilityGaps=useMemo(()=>Array.from(new Set((f0?.decision?.steps||[]).flatMap(s=>s.result?.needed_capabilities||[]))),[f0]);

 function branchNode(b:Branch,depth=0):ReactElement{
  const trials=trialsByBranch.get(b.id)||[];
  return (
   <div key={b.id} className="branch-wrap">
    <div className={'branch'+(b.source==='manual'?' human':'')+(node===b.id?' sel':'')} data-bid={b.id} onClick={()=>setNode(b.id)} role="button" tabIndex={0}>
     <div className="bh">
      <span className="hid">{b.id.slice(0,8)}</span>
      <span className="bt">{b.source==='manual'?'人工分支':'Agent 分支'} · 假设 v{b.hypothesis_version} / 实现 v{b.implementation_version}</span>
      <span className={'badge '+(b.status==='active'?'live':'gray')}>{b.status==='active'?'进行中':b.status}</span>
      <span className="by">{b.source==='manual'?'人工':'Agent'} · {trials.length} 次试验</span>
     </div>
     {trials.length>0&&<div className="steps">{trials.map(t=>{const checks=t.result_summary?.gate?.checks||[];const ic=checks.find(c=>c.name.includes('方向IC')||c.name.includes('方向 Rank IC'));const nw=checks.find(c=>c.name.includes('NW t'));return <span key={t.trial_no} className={'chip '+(t.outcome==='passed'?'ok':t.outcome==='failed'?'fail':'warn')} title={checks.map(c=>`${c.name}: ${c.actual==null?'—':Number(c.actual).toFixed(3)} / ${String(c.threshold)}`).join(' · ')}>{`E${t.trial_no}`}{ic?.actual!=null?` · IC ${Number(ic.actual).toFixed(3)}`:''}{nw?.actual!=null?` · t ${Number(nw.actual).toFixed(2)} / ${Number(nw.threshold).toFixed(2)}`:` · ${outcomeText(t)}`}{t.rerun_of?' · rerun':''}</span>;})}</div>}
    </div>
    {(children.get(b.id)||[]).length>0&&<div className="children">{(children.get(b.id)||[]).map(c=>branchNode(c,depth+1))}</div>}
   </div>
  );
 }

 const topicCards=topics.map(t=>(
  <button key={t.id} className={'topic'+(selected===t.id?' sel':'')} onClick={()=>setSelected(t.id)}>
   <div className="top"><span className="tid">{t.id.slice(0,8)} · {t.primary_holding_period} 日</span><span className={'badge '+(t.status==='active'?'live':'gray')}>{statusText(t.status)}</span></div>
   <h3>{t.project_name||'未命名课题'}</h3>
   <div className="act">{t.trial_count>0?'已登记研发检验与台账。':'等待第一次真实研发检验。'}</div>
   <div className="bar"><i style={{width:Math.min(100,t.k/Math.max(1,t.max_trials)*100)+'%'}}/></div>
   <div className="meta"><span>试验 <b>{t.k}/{t.max_trials}</b></span><span>分支 <b>{t.branch_count}</b></span><span>封存 <b>{t.sealed_used??0}/{t.max_sealed}</b></span></div>
  </button>
 ));

 const tree=(ledger?.branches||[]).length>0?<div className="tree" ref={treeRef}>{treeLines.length>0&&<svg className="tree-lines" aria-hidden="true">{treeLines.map((d,i)=><path key={i} d={d} fill="none" stroke="#cbb8dc" strokeWidth="1" strokeDasharray="4 4"/>)}</svg>}{(children.get('root')||[]).map(b=>branchNode(b))}</div>:<div className="empty"><b>课题还没有分支</b>真实空态：无分支时不显示模拟节点。</div>;

 const trials=(selectedBranch?trialsByBranch.get(selectedBranch.id):[])||[];
 const detail=selectedBranch?(
  <div className="card">
   <div className="card-head">
    <div><div className="row-flex"><span className="hid">{selectedBranch.id.slice(0,8)}</span><h2>{selectedBranch.source==='manual'?'人工分支':'Agent 分支'}</h2></div>
     <p className="fine">假设 v{selectedBranch.hypothesis_version} · 实现 v{selectedBranch.implementation_version} · {selectedBranch.status}</p></div>
    <div className="actions"><button className="btn small primary" onClick={()=>void takeOver()}>从此分支接手</button><button className="btn small" onClick={()=>void handBackF0()} disabled={f0&&['queued','running'].includes(f0.status)}>交回 Agent（F0）</button>{f0&&f0.stop_reason?.includes('中断')&&<button className="btn small" onClick={()=>void resumeF0()}>继续 F0</button>}<Link className="btn small" to={'/quant/factor/workflow/'+(topic?.project_id||'')+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>打开人工工作台</Link>{f0&&<span className="fine">F0：{f0.status}{f0.decision?.candidate_status?' · '+f0.decision.candidate_status:''}{f0.stop_reason?' · '+f0.stop_reason:''}</span>}</div>
   </div>
   <div className="card-body">
    <div className="kv">
     <span>分支来源</span><div>{selectedBranch.source==='manual'?'人工':'Agent'}（parent：{selectedBranch.parent_id?selectedBranch.parent_id.slice(0,8):'无'}）</div>
     <span>说明</span><div className="fine">“从此分支接手”会新建人工分支并把它设为工作台写入分支；交回按钮交给模型 F0 连续推进；预算/暂停/视图不符会停止。</div>
    </div>
    <h3 style={{margin:'16px 0 4px'}}>试验与决定</h3>
    {trials.length===0?<p className="subtle">该分支尚无记录。</p>:trials.map(t=>(
     <div className="trial-row" key={t.trial_no}>
      <span className="tk">E{t.trial_no}</span>
      <div className="tb"><b>{outcomeText(t)} · {t.kind}</b><small>{new Date(t.created_at||'').toLocaleString()} · {t.executor} · {t.returned_metrics?'已返回研发指标':'未返回指标'}{nwText(t)}{t.rerun_of?' · 确定性 rerun':''}</small></div>
      {t.report_id?<Link className="btn small" to={'/quant/factor/report/'+t.report_id}>报告</Link>:<span className="fine">无报告</span>}
     </div>
    ))}
    {f0?.decision?.steps&&<div style={{marginTop:14}}><h3 style={{margin:'0 0 6px'}}>F0 决策事件</h3>{f0.decision.steps.map(s=><div className="trial-row" key={s.step}><span className="tk">S{s.step}</span><div className="tb"><b>{s.decision.action}</b><small>{s.decision.rationale}</small></div><span className="fine">{s.result.status||''}{s.result.candidate_status?' · '+s.result.candidate_status:''}</span></div>)}</div>}
   </div>
  </div>
 ):null;

 const side=(
  <aside className="side">
   <div className="card">
    <div className="card-head"><div><h2>研究系统</h2><p className="fine">按真实状态标注，未接入不显示模拟运行</p></div></div>
    <div className="card-body">
     <div className="units">
      <div className="unit"><span className="ui">⇅</span><div><b>课题调度</b><small>规则排队/跨课题预算：未接入</small></div></div>
      <div className="unit agent"><span className="ui">F0</span><div><b>研究决策</b><small>模型决策 · 连续推进；封存通过后交人工</small></div></div>
      <div className="unit"><span className="ui">F1</span><div><b>起点检索</b><small>因子库与历史试验：可用</small></div></div>
      <div className="unit agent"><span className="ui">F2</span><div><b>假设研究</b><small>Agent 草稿：可用，需人工确认</small></div></div>
      <div className="unit agent"><span className="ui">F3</span><div><b>因子实现</b><small>Agent 生成与校验：可用</small></div></div>
      <div className="unit"><span className="ui">F4</span><div><b>检验诊断</b><small>真实 RE 研发检验：可用</small></div></div>
      <div className="unit indep"><span className="ui">F5</span><div><b>独立复核</b><small>独立意见可用 · 封存执行已接入（真实结果含失败）</small></div></div>
     </div>
     <div className="svc"><span>数据视图</span><span>因子计算</span><span>试验台账</span><span>因子库查重</span><span>封存执行（真实）</span></div>
    </div>
   </div>
   <div className="card">
    <div className="card-head"><h2>实时动态</h2><span className="live-dot off"/></div>
    <div className="card-body">{feed.length===0?<p className="subtle">暂无真实事件。</p>:<ul className="feed">{feed.map(t=><li key={t.trial_no}><time>{new Date(t.created_at||'').toLocaleTimeString()}</time><span className="tg">E{t.trial_no}</span>{outcomeText(t)} · {t.executor}{t.report_id?' · 有报告':''}</li>)}</ul>}</div>
   </div>
  </aside>
 );

 const main=topic?(
  <div className="card">
   <div className="card-head">
    <div><div className="row-flex"><span className="tid">{topic.id.slice(0,8)}</span><h2>{topic.project_name||'未命名课题'}</h2><span className="badge live">{statusText(topic.status)}</span></div>
     <p className="fine">视图 {topic.view_id} · 主持有期 {topic.primary_holding_period} 日</p></div>
    <div className="actions">{topic.status==='active'?<button className="btn small" onClick={()=>void setTopicStatus('paused')}>暂停课题</button>:topic.status==='paused'?<button className="btn small" onClick={()=>void setTopicStatus('active')}>继续课题</button>:null}<Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>打开人工工作台</Link><Link className="btn small" to={'/quant/factor/ledger?project='+topic.project_id}>台账</Link></div>
   </div>
   <div className="card-body">
    <div className="ledger">
     <span>试验台账 <b>{ledger?.k??topic.k}</b> / {topic.max_trials}</span>
     <span>分支 <b>{topic.branch_count}</b></span>
     <span>当前 t*(K) <b>{ledger?.threshold==null?'待接入':ledger.threshold.toFixed(3)}</b></span>
     <span>下一次可计数检验 t* <b>{ledger?.threshold_next_if_counted?.toFixed(3)||'待接入'}</b></span>
    </div>
    {capabilityGaps.length>0&&<p className="hint" role="status">需要的能力（F3 暂不支持）：{capabilityGaps.join('、')}。F0 已改用可实现的降级修订继续。</p>}
    <div className="section-title" style={{marginTop:16}}><h3>研究树</h3><span className="subtle">点击分支查看试验与报告</span></div>
    {tree}
   </div>
  </div>
 ):null;

 return (
  <>
   <WorkspaceHeading eyebrow="FACTOR FACTORY" title="因子工厂" description="研究系统持续挖掘因子：你可以随时观察、介入，或亲自研究。">
    <button className="btn" onClick={()=>setAuthOpen(v=>!v)}>研究授权</button>
    <Link className="btn primary" to="/quant/factor/library">新建课题</Link>
   </WorkspaceHeading>
   <FactorModuleTabs active="home"/>
   {authOpen&&<div className="card card-pad" style={{marginBottom:14}}><p className="fine">当前登录成员可在本机构范围创建因子课题、运行检验与申请封存；数据视图与预登记门槛由课题计划固定，Agent 不能改门槛、扩预算或批准入库。新建课题从因子库选择已授权资产开始。</p></div>}
   <div className="sys compact">
    <div className="sys-state"><span className="ico">⇅</span><div><b>研究系统</b><small className="fine">{loading?'读取中':`真实课题 ${topics.length} 个 · 台账 ${totalTrials} 次`}</small></div></div>
    <div className="kpis">
     <div className="kpi"><span>课题</span><b>{topics.length}</b><small>研究中 {topics.filter(t=>t.status==='active').length}</small></div>
     <div className="kpi"><span>试验台账</span><b>{totalTrials}</b><small>次</small></div>
     <div className="kpi"><span>封存样本已用</span><b>{sealedUsed==null?'—':sealedUsed}</b><small>累计封存（含失败）</small></div>
     <div className="kpi"><span>待人决定</span><b>{pending==null?'—':pending}</b><small>待复核候选</small></div>
     <div className="kpi"><span>F0 Token</span><b>{f0?.decision?.steps?f0.decision.steps.reduce((n,s)=>n+(s.usage?.tokens_in||0)+(s.usage?.tokens_out||0),0):'—'}</b><small>最近一次 F0</small></div>
    </div>
   </div>
   {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
   {loading?(
    <div className="card card-pad"><p role="status">正在读取真实课题、分支与台账…</p></div>
   ):topics.length===0?(
    <div className="card card-pad">
     <h2>还没有 V5 课题</h2>
     <p className="hint">研究树只展示已登记的课题台账；没有数据时保留位置并说明，不用原型数据填充。</p>
     <Link className="btn primary" to="/quant/factor/library">从因子库开始研究</Link>
    </div>
   ):(
    <div className="ops-grid">
     <div>
      <div className="topic-grid">{topicCards}</div>
      {main}
      {detail}
     </div>
     {side}
    </div>
   )}
  </>
 );
}
