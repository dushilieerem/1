import {useEffect,useState} from 'react';
import {researchFetch} from '@/lib/researchClient';
import {WorkspaceHeading} from './QuantWorkspacePages';

type Event={severity:string;kind:string;object:string;detail:string;at:string;ref:string};
type Data={counts:{running:number;errors:number;strategy_trials_30d:number;factor_trials_30d:number};events:Event[];limitations:string[]};
const SEV:Record<string,[string,string]>={info:['提示','badge gray'],warning:['警告','badge warn'],serious:['严重','badge bad']};

export function QuantMonitorPage(){
 const [data,setData]=useState<Data>(),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const load=()=>{setLoading(true);researchFetch('/api/inst/quant/monitor/overview').then(r=>r.ok?r.json():Promise.reject(Error('巡检读取失败'))).then(setData).catch(e=>setError(e instanceof Error?e.message:String(e))).finally(()=>setLoading(false));};
 useEffect(load,[]);
 return <><WorkspaceHeading eyebrow="MONITORING & RISK" title="运行与风险" description="只读查看真实任务失败、F0/S0 停止与组合状态；巡检常驻任务、风险规则和恢复流程尚未接入。"><button className="btn" onClick={load} disabled={loading}>刷新巡检</button></WorkspaceHeading>
 {error&&<div className="card card-pad"><p className="hint error">{error}</p></div>}
 {loading?<div className="card card-pad"><p role="status">正在读取真实运行记录…</p></div>:data&&<>
  <div className="sys-strip"><div className="sys-state"><span className="ico">◉</span><div><b>运行巡检</b><small className="fine">按需读取真实记录；非定时任务</small></div></div><div className="kpis"><div className="kpi"><span>执行中</span><b>{data.counts.running}</b><small>因子计算</small></div><div className="kpi"><span>错误</span><b>{data.counts.errors}</b><small>因子候选</small></div><div className="kpi"><span>近30日试验</span><b>{data.counts.factor_trials_30d + data.counts.strategy_trials_30d}</b><small>因子+策略</small></div></div></div>
  <div className="card"><div className="card-head"><h2>事件</h2><span className="fine">{data.events.length} 条真实记录</span></div><div className="table-wrap"><table className="table"><thead><tr><th>等级</th><th>类型</th><th>对象</th><th>详情</th><th>时间</th></tr></thead><tbody>{data.events.length===0?<tr><td colSpan={5} className="empty">当前没有失败或停止记录。</td></tr>:data.events.map(e=><tr key={e.kind+e.ref+e.at}><td><span className={SEV[e.severity]?.[1]||'badge'}>{SEV[e.severity]?.[0]||e.severity}</span></td><td>{e.kind}</td><td>{e.object}</td><td className="fine">{e.detail}</td><td>{new Date(e.at).toLocaleString()}</td></tr>)}</tbody></table></div></div>
  <div className="card"><div className="card-head"><h2>未接入能力</h2></div><div className="card-body"><ul className="checklist">{data.limitations.map(x=><li key={x}>{x}</li>)}</ul></div></div>
 </>}
 </>;
}
