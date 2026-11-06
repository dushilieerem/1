import {useEffect,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

type Trial={trial_no:number;branch_id:string;kind:string;outcome:string;executor:string;report_id?:string|null;created_at?:string;returned_metrics?:boolean;rerun_of?:string|null};
type Topic={id:string;display_no?:number;project_id:string;view_id:string;primary_holding_period:number;max_trials:number;max_sealed:number;status:string};
type Ledger={topic:Topic;branches:Array<{id:string;display_label?:string}>;trials:Trial[];k:number;threshold:number|null;threshold_next_if_counted:number;next_trial_no:number};

export function QuantFactorLedgerPage(){
 const [params]=useSearchParams();
 const projectId=params.get('project')||'';
 const [topic,setTopic]=useState<Topic>();
 const [ledger,setLedger]=useState<Ledger>();
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(false);
 useEffect(()=>{
  if(!projectId){setTopic(undefined);setLedger(undefined);return;}
  let alive=true;setLoading(true);setError('');
  researchFetch('/api/inst/quant/factor-workflow/projects/'+encodeURIComponent(projectId)+'/topics')
   .then(r=>r.ok?r.json():Promise.reject(Error('台账读取失败')))
   .then(async d=>{if(!alive)return;const first=(d.topics||[])[0];if(!first){setTopic(undefined);setLedger(undefined);return;}setTopic(first);const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(first.id)+'/ledger');if(!r.ok)throw Error('台账明细读取失败');const detail=await r.json();if(alive)setLedger(detail);})
   .catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));})
   .finally(()=>{if(alive)setLoading(false);});
  return()=>{alive=false;};
 },[projectId]);
 return <><WorkspaceHeading title="因子工厂 · 台账" description="课题级只追加台账：每次完成的研发检验如实登记 K 与结果，失败也保留。"><span className="fine">当前 K：{ledger?ledger.k:'—'}</span></WorkspaceHeading><FactorModuleTabs active="ledger" projectId={projectId||undefined}/>
 {!projectId&&<div className="card card-pad"><p className="empty">请从研究工作流程进入台账，或在地址中带 <code>?project=课题ID</code>。</p></div>}
 {projectId&&loading&&<div className="card card-pad"><p role="status">正在读取真实台账…</p></div>}
 {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
 {projectId&&!loading&&!error&&!topic&&<div className="card card-pad"><h2>尚未建立 V5 台账</h2><p className="hint">该研究没有课题台账。演示课题应已预建；普通课题需先完成一次研发检验并登记，不能在这里补造试验。</p></div>}
 {ledger&&<div className="card"><div className="card-head"><h2>课题 T{ledger.topic.display_no??'—'}</h2><span className="fine">状态 {ledger.topic.status} · 数据视图 {ledger.topic.view_id}</span></div><div className="card-pad metric-strip"><div><small>当前 K</small><strong>{ledger.k}</strong></div><div><small>当前 t*(K)</small><strong>{ledger.threshold==null?'待接入':ledger.threshold.toFixed(4)}</strong></div><div><small>下一次可计数检验 t*</small><strong>{ledger.threshold_next_if_counted.toFixed(4)}</strong></div><div><small>试验预算</small><strong>{ledger.trials.length} / {ledger.topic.max_trials}</strong></div><div><small>主持有期</small><strong>{ledger.topic.primary_holding_period} 日</strong></div></div><div className="table-wrap"><table className="table"><thead><tr><th>#</th><th>分支</th><th>类型 / 结果</th><th>执行者</th><th>计入 K</th><th>报告</th><th>时间</th></tr></thead><tbody>{ledger.trials.map(t=><tr key={t.trial_no}><td>{t.trial_no}</td><td>{((ledger.branches as Array<{id:string;display_label?:string}>).find(b=>b.id===t.branch_id)?.display_label)||t.branch_id.slice(0,8)}</td><td><span className="badge">{t.kind}</span> {t.outcome}{t.rerun_of&&<span className="fine">（rerun）</span>}</td><td>{t.executor}</td><td>{t.rerun_of?'否':['passed','failed','error','timeout','cancelled'].includes(t.outcome)?(t.returned_metrics?'是':'否'):'—'}</td><td>{t.report_id?<Link className="btn small" to={'/quant/factor/report/'+t.report_id}>真实报告</Link>:'—'}</td><td>{t.created_at?new Date(t.created_at).toLocaleString():'—'}</td></tr>)}</tbody></table></div>{ledger.trials.length===0&&<p className="card-pad empty">台账已建立，尚未登记试验。回到 F4 运行一次真实研发检验后会出现记录。</p>}<p className="fine card-pad">K 只统计研究者或 Agent 已看到研发区间结果的检验；rerun、静态检查、封存不计。R1 未接入时 NW t 显示待接入，本页不伪造显著性。</p></div>}
 </>;
}
