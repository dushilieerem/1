import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

type Topic={id:string;project_id:string;project_name:string;status:string;k:number;max_trials:number};
type Branch={id:string;source:string;parent_id?:string|null;status:string};

export function QuantFactorManualPage(){
 const [items,setItems]=useState<Array<{topic:Topic;branch:Branch}>>([]);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 useEffect(()=>{let alive=true;researchFetch('/api/inst/quant/factor-workflow/topics').then(r=>r.ok?r.json():Promise.reject(Error('课题读取失败'))).then(async d=>{
  const list:Topic[]=d.topics||[];const out=[];for(const t of list){const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(t.id)+'/ledger');if(!r.ok)continue;const led=await r.json();for(const b of led.branches||[])if(b.source==='manual')out.push({topic:t,branch:b});}
  if(alive)setItems(out);
 }).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[]);
 return <><WorkspaceHeading title="人工研究" description="列出本机构课题的真实人工分支；从研究树接手会创建人工分支，进入工作台后检验计入同课题台账。"><Link className="btn" to="/quant/factor">打开研究运行</Link></WorkspaceHeading><FactorModuleTabs active="manual"/>
 {error&&<div className="card card-pad"><p className="hint error">{error}</p></div>}
 {loading?<div className="card card-pad"><p role="status">正在读取人工分支…</p></div>:items.length===0?<div className="card card-pad"><h2>还没有人工分支</h2><p className="hint">请先在研究运行的研究树中选择分支并点“从此分支接手”。不会用演示数据填充。</p><Link className="btn primary" to="/quant/factor">去研究树接手</Link></div>:<div className="card"><div className="card-head"><h2>我的人工分支</h2><span className="fine">{items.length} 个</span></div><div className="table-wrap"><table className="table"><thead><tr><th>课题</th><th>分支</th><th>来源</th><th>K / 预算</th><th>操作</th></tr></thead><tbody>{items.map(({topic,branch})=><tr key={branch.id}><td><strong>{topic.project_name||topic.id.slice(0,8)}</strong><p className="fine">{topic.id.slice(0,8)} · {topic.status}</p></td><td>{branch.id.slice(0,8)}{branch.parent_id&&<span className="fine"> ← {branch.parent_id.slice(0,8)}</span>}</td><td>人工</td><td>{topic.k} / {topic.max_trials}</td><td><Link className="btn small primary" to={'/quant/factor/workflow/'+topic.project_id+'/F4?branch='+branch.id}>进入工作台</Link> <Link className="btn small" to={'/quant/factor/ledger?project='+topic.project_id}>台账</Link></td></tr>)}</tbody></table></div><p className="fine card-pad">工作台 URL 绑定该分支；打开时激活此分支，检验/提交/交回按该分支执行并计入同课题台账。</p></div>}
 </>;
}
