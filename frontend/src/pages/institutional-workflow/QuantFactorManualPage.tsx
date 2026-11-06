import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

type Topic={id:string;project_id:string;project_name:string;status:string;k:number;max_trials:number};
type Branch={id:string;source:string;parent_id?:string|null;status:string;hypothesis_version?:number;implementation_version?:number};
type Item={topic:Topic;branch:Branch;k:number;nextT?:number;view:string};

const STEPS:Array<[string,string,string]>=[['F1','起点','研究目标、资产与数据范围'],['F2','假设','可证伪条件与检验方法'],['F3','实现','代码与字段校验'],['F4','检验','真实研发回测与诊断'],['F5','封存','样本外验证，每候选一次'],['F6','提交','固定版本与复核材料']];

export function QuantFactorManualPage(){
 const [items,setItems]=useState<Item[]>([]),[selected,setSelected]=useState<string>();
 const [error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{let alive=true;researchFetch('/api/inst/quant/factor-workflow/topics').then(r=>r.ok?r.json():Promise.reject(Error('课题读取失败'))).then(async d=>{
  const list:Topic[]=d.topics||[];const out:Item[]=[];for(const t of list){const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(t.id)+'/ledger');if(!r.ok)continue;const led=await r.json();for(const b of led.branches||[])if(b.source==='manual')out.push({topic:t,branch:b,k:led.k,nextT:led.threshold_next_if_counted,view:led.topic?.view_id||''});}
  if(alive){setItems(out);setSelected(cur=>cur&&out.some(x=>x.branch.id===cur)?cur:out[0]?.branch.id);}
 }).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[]);
 const current=items.find(x=>x.branch.id===selected);
 const workbench=(x:Item,step:string)=>'/quant/factor/workflow/'+x.topic.project_id+'/'+step+'?branch='+x.branch.id;
 return <><WorkspaceHeading eyebrow="FACTOR FACTORY" title="人工研究" description="人工分支与 Agent 共用工具和试验台账；接手、检验、提交都绑定该分支。"><Link className="btn" to="/quant/factor">打开研究运行</Link></WorkspaceHeading><FactorModuleTabs active="manual"/>
 {error&&<div className="card card-pad"><p className="hint error">{error}</p></div>}
 {loading?<div className="card card-pad"><p role="status">正在读取人工分支…</p></div>:items.length===0?<div className="card"><div className="empty"><b>还没有打开的人工分支</b>在“研究运行”的研究树里选择任意分支“从此分支接手”，或新建课题。不会用演示数据填充。<div style={{marginTop:12}}><Link className="btn primary" to="/quant/factor">去研究运行</Link></div></div></div>:<>
  {current&&<div className="card">
   <div className="card-head"><div><div className="row-flex"><span className="subtle">{current.topic.project_name||current.topic.id.slice(0,8)} /</span><h2>{current.branch.id.slice(0,8)} · 人工分支</h2><span className={'badge '+(current.branch.status==='active'?'live':'gray')}>{current.branch.status==='active'?'进行中':current.branch.status}</span></div><p className="fine">假设 v{current.branch.hypothesis_version??1} / 实现 v{current.branch.implementation_version??1}{current.branch.parent_id?' · 接手自 '+current.branch.parent_id.slice(0,8):' · 根分支'} · 与 Agent 共用工具和试验台账</p></div><div className="actions"><Link className="btn small primary" to={workbench(current,'F4')}>打开工作台</Link><Link className="btn small" to={'/quant/factor/ledger?project='+current.topic.project_id}>台账</Link></div></div>
   <div className="card-body" style={{paddingTop:12,paddingBottom:12}}><div className="ledger"><span>课题试验台账 <b>{current.k}</b> 次</span><span>下一次检验需 t ≥ <b>{current.nextT==null?'—':current.nextT.toFixed(3)}</b></span><span>预算剩余 <b>{Math.max(0,current.topic.max_trials-current.k)}</b></span><span className="fine">视图 {current.view||'—'}</span></div></div>
   <div className="card-body" style={{paddingTop:0}}><div className="tool-tabs">{STEPS.map(([id,label,desc])=><Link key={id} className="tab" to={workbench(current,id)} title={desc}>{id} · {label}</Link>)}</div><p className="fine">每个页签打开该分支的真实工作台步骤；表单提交与检验仍走现有权限和台账，不会新建演示数据。</p></div>
  </div>}
  <div className="card" style={{marginTop:14}}><div className="card-head"><h2>我的人工分支</h2><span className="fine">{items.length} 个</span></div><div className="table-wrap"><table className="table"><thead><tr><th>课题</th><th>分支</th><th>来源</th><th>K / 预算</th><th>操作</th></tr></thead><tbody>{items.map(x=><tr key={x.branch.id} className={x.branch.id===selected?'sel':''}><td><strong>{x.topic.project_name||x.topic.id.slice(0,8)}</strong><p className="fine">{x.topic.id.slice(0,8)} · {x.topic.status}</p></td><td><button className="text-link" onClick={()=>setSelected(x.branch.id)}>{x.branch.id.slice(0,8)}</button>{x.branch.parent_id&&<span className="fine"> ← {x.branch.parent_id.slice(0,8)}</span>}</td><td>人工</td><td>{x.k} / {x.topic.max_trials}</td><td><Link className="btn small primary" to={workbench(x,'F4')}>进入工作台</Link></td></tr>)}</tbody></table></div></div>
 </>}
 </>;
}
