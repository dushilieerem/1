import {useEffect,useMemo,useState,type ReactElement} from 'react';
import {Link} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

type Topic={id:string;project_id:string;project_name:string;view_id:string;primary_holding_period:number;max_trials:number;max_sealed:number;status:string;k:number;branch_count:number;trial_count:number;created_at?:string};
type Branch={id:string;topic_id:string;parent_id?:string|null;source:string;status:string;hypothesis_version:number;implementation_version:number;created_at?:string};
type Trial={trial_no:number;branch_id:string;kind:string;outcome:string;executor:string;report_id?:string|null;created_at?:string;returned_metrics?:boolean;rerun_of?:string|null};
type Ledger={topic:Topic;branches:Branch[];trials:Trial[];k:number;threshold:number|null;threshold_next_if_counted:number;next_trial_no:number};

const statusText=(s:string)=>s==='active'?'运行中':s==='archived'?'已归档':s;
const outcomeText=(t:Trial)=>t.outcome==='passed'?'通过':t.outcome==='failed'?'未达标':t.outcome==='error'?'执行错误':t.outcome;

export function QuantFactorHomePage(){
 const [topics,setTopics]=useState<Topic[]>([]);
 const [selected,setSelected]=useState<string>();
 const [ledger,setLedger]=useState<Ledger>();
 const [node,setNode]=useState<string>();
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);

 useEffect(()=>{
  let alive=true;setLoading(true);
  researchFetch('/api/inst/quant/factor-workflow/topics')
   .then(r=>r.ok?r.json():Promise.reject(Error('课题读取失败')))
   .then(d=>{if(!alive)return;const list=d.topics||[];setTopics(list);setSelected(cur=>cur&&list.some((t:Topic)=>t.id===cur)?cur:list[0]?.id);})
   .catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));})
   .finally(()=>{if(alive)setLoading(false);});
  return()=>{alive=false;};
 },[]);

 useEffect(()=>{
  if(!selected){setLedger(undefined);return;}
  let alive=true;
  researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(selected)+'/ledger')
   .then(r=>r.ok?r.json():Promise.reject(Error('研究树读取失败')))
   .then(d=>{if(!alive)return;setLedger(d);setNode(cur=>cur&&(d.branches||[]).some((b:Branch)=>b.id===cur)?cur:(d.branches||[])[0]?.id);})
   .catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));});
  return()=>{alive=false;};
 },[selected]);

 const children=useMemo(()=>{const map=new Map<string,Branch[]>();for(const b of ledger?.branches||[])map.set(b.parent_id||'root',[...(map.get(b.parent_id||'root')||[]),b]);return map;},[ledger]);
 const trialsByBranch=useMemo(()=>{const map=new Map<string,Trial[]>();for(const t of ledger?.trials||[])map.set(t.branch_id,[...(map.get(t.branch_id)||[]),t]);return map;},[ledger]);
 const topic=topics.find(t=>t.id===selected);
 const selectedBranch=(ledger?.branches||[]).find(b=>b.id===node);
 const feed=useMemo(()=>[...(ledger?.trials||[])].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||'')).slice(0,12),[ledger]);
 const totalTrials=topics.reduce((n,t)=>n+t.trial_count,0);

 function branchNode(b:Branch,depth=0):ReactElement{
  const trials=trialsByBranch.get(b.id)||[];
  return (
   <div key={b.id} className="branch-wrap" style={{marginLeft:depth?26:0}}>
    <div className={'branch'+(b.source==='manual'?' human':'')+(node===b.id?' sel':'')} onClick={()=>setNode(b.id)} role="button" tabIndex={0}>
     <div className="bh">
      <span className="hid">{b.id.slice(0,8)}</span>
      <span className="bt">{b.source==='manual'?'人工分支':'Agent 分支'} · 假设 v{b.hypothesis_version} / 实现 v{b.implementation_version}</span>
      <span className={'badge '+(b.status==='active'?'live':'gray')}>{b.status==='active'?'进行中':b.status}</span>
      <span className="by">{trials.length} 次试验</span>
     </div>
     {trials.length>0&&<div className="steps">{trials.map(t=><span key={t.trial_no} className={'chip '+(t.outcome==='passed'?'ok':t.outcome==='failed'?'fail':'warn')}>E{t.trial_no} · {outcomeText(t)}{t.rerun_of?' · rerun':''}</span>)}</div>}
    </div>
    {(children.get(b.id)||[]).map(c=>branchNode(c,depth+1))}
   </div>
  );
 }

 const topicCards=topics.map(t=>(
  <button key={t.id} className={'topic'+(selected===t.id?' sel':'')} onClick={()=>setSelected(t.id)}>
   <div className="top"><span className="tid">{t.id.slice(0,8)} · {t.primary_holding_period} 日</span><span className={'badge '+(t.status==='active'?'live':'gray')}>{statusText(t.status)}</span></div>
   <h3>{t.project_name||'未命名课题'}</h3>
   <div className="act">{t.trial_count>0?'已登记研发检验与台账。':'等待第一次真实研发检验。'}</div>
   <div className="bar"><i style={{width:Math.min(100,t.k/Math.max(1,t.max_trials)*100)+'%'}}/></div>
   <div className="meta"><span>试验 <b>{t.k}/{t.max_trials}</b></span><span>分支 <b>{t.branch_count}</b></span><span>封存 <b>0/{t.max_sealed}</b></span></div>
  </button>
 ));

 const tree=(ledger?.branches||[]).length>0?<div className="tree">{(children.get('root')||[]).map(b=>branchNode(b))}</div>:<div className="empty"><b>课题还没有分支</b>真实空态：无分支时不显示模拟节点。</div>;

 const trials=(selectedBranch?trialsByBranch.get(selectedBranch.id):[])||[];
 const detail=selectedBranch?(
  <div className="card">
   <div className="card-head">
    <div><div className="row-flex"><span className="hid">{selectedBranch.id.slice(0,8)}</span><h2>{selectedBranch.source==='manual'?'人工分支':'Agent 分支'}</h2></div>
     <p className="fine">假设 v{selectedBranch.hypothesis_version} · 实现 v{selectedBranch.implementation_version} · {selectedBranch.status}</p></div>
    <Link className="btn small primary" to={'/quant/factor/workflow/'+(topic?.project_id||'')+'/F4'}>打开人工工作台（项目级，非按分支写入）</Link>
   </div>
   <div className="card-body">
    <div className="kv">
     <span>分支来源</span><div>{selectedBranch.source==='manual'?'人工':'Agent'}（parent：{selectedBranch.parent_id?selectedBranch.parent_id.slice(0,8):'无'}）</div>
     <span>说明</span><div className="fine">分支级人工回写尚未实现；此处只读展示真实试验。</div>
    </div>
    <h3 style={{margin:'16px 0 4px'}}>试验与决定</h3>
    {trials.length===0?<p className="subtle">该分支尚无记录。</p>:trials.map(t=>(
     <div className="trial-row" key={t.trial_no}>
      <span className="tk">E{t.trial_no}</span>
      <div className="tb"><b>{outcomeText(t)} · {t.kind}</b><small>{new Date(t.created_at||'').toLocaleString()} · {t.executor} · {t.returned_metrics?'已返回研发指标':'未返回指标'}{t.rerun_of?' · 确定性 rerun':''}</small></div>
      {t.report_id?<Link className="btn small" to={'/quant/factor/report/'+t.report_id}>报告</Link>:<span className="fine">无报告</span>}
     </div>
    ))}
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
      <div className="unit agent"><span className="ui">F0</span><div><b>研究决策</b><small>自动推进：未接入</small></div></div>
      <div className="unit"><span className="ui">F1</span><div><b>起点检索</b><small>因子库与历史试验：可用</small></div></div>
      <div className="unit agent"><span className="ui">F2</span><div><b>假设研究</b><small>Agent 草稿：可用，需人工确认</small></div></div>
      <div className="unit agent"><span className="ui">F3</span><div><b>因子实现</b><small>Agent 生成与校验：可用</small></div></div>
      <div className="unit"><span className="ui">F4</span><div><b>检验诊断</b><small>真实 RE 研发检验：可用</small></div></div>
      <div className="unit indep"><span className="ui">F5</span><div><b>独立复核</b><small>封存验证：未上线</small></div></div>
     </div>
     <div className="svc"><span>数据视图</span><span>因子计算</span><span>试验台账</span><span>因子库查重</span><span>封存样本（未上线）</span></div>
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
    <div className="actions"><Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'}>人工工作台（项目级）</Link><Link className="btn small" to={'/quant/factor/ledger?project='+topic.project_id}>台账</Link></div>
   </div>
   <div className="card-body">
    <div className="ledger">
     <span>试验台账 <b>{ledger?.k??topic.k}</b> / {topic.max_trials}</span>
     <span>分支 <b>{topic.branch_count}</b></span>
     <span>当前 t*(K) <b>{ledger?.threshold==null?'待接入':ledger.threshold.toFixed(3)}</b></span>
     <span>下一次可计数检验 t* <b>{ledger?.threshold_next_if_counted?.toFixed(3)||'待接入'}</b></span>
    </div>
    <div className="section-title" style={{marginTop:16}}><h3>研究树</h3><span className="subtle">点击分支查看试验与报告</span></div>
    {tree}
   </div>
  </div>
 ):null;

 return (
  <>
   <WorkspaceHeading title="研究运行" description="课题看板、研究树与真实台账；失败和 rerun 同样留痕。">
    <Link className="btn" to="/quant/factor/library">因子库</Link>
    <Link className="btn" to="/quant/factor/experiments">历史报告</Link>
   </WorkspaceHeading>
   <FactorModuleTabs active="home"/>
   <div className="sys">
    <div className="sys-state"><span className="ico">⇅</span><div><b>研究系统</b><small className="fine">{loading?'读取中':`真实课题 ${topics.length} 个 · 台账 ${totalTrials} 次`}</small></div></div>
    <div className="kpis">
     <div className="kpi"><span>课题</span><b>{topics.length}</b><small>运行 {topics.filter(t=>t.status==='active').length}</small></div>
     <div className="kpi"><span>试验台账</span><b>{totalTrials}</b><small>次</small></div>
     <div className="kpi"><span>封存样本已用</span><b>—</b><small>待接入</small></div>
     <div className="kpi"><span>待人决定</span><b>—</b><small>审查队列待接入</small></div>
     <div className="kpi"><span>Token</span><b>—</b><small>未上报</small></div>
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
