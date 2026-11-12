import {useEffect,useState} from 'react';
import {researchFetch} from '@/lib/researchClient';
import {WorkspaceHeading} from './QuantWorkspacePages';
type Unit={code:string;name:string;skill:string;calls:number;tokens_in:number;tokens_out:number;last_at?:string;method_version:string;failure_rate:number|null};
type Data={window_days:number;units:Unit[];limitations:string[]};
export function QuantAgentsPage(){
 const [data,setData]=useState<Data>(),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{let alive=true;researchFetch('/api/inst/quant/agents/overview').then(r=>r.ok?r.json():Promise.reject(Error('Agent 用量读取失败'))).then(d=>{if(alive)setData(d);}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[]);
 return <><WorkspaceHeading eyebrow="AGENT MANAGEMENT" title="Agent 管理" description="只读查看能力单元的方法版本、调用与 Token；暂停接口和失败率待接入。"><span className="fine">近 {data?.window_days??30} 天</span></WorkspaceHeading>
 {error&&<div className="card card-pad"><p className="hint error">{error}</p></div>}
 {loading?<div className="card card-pad"><p role="status">正在读取真实用量…</p></div>:data&&<><div className="card"><div className="table-wrap"><table className="table"><thead><tr><th>单元</th><th>能力</th><th>skill</th><th>近30日调用</th><th>Token 入/出</th><th>失败率</th><th>最近调用</th><th>操作</th></tr></thead><tbody>{data.units.length===0?<tr><td colSpan={8} className="empty">近 30 天没有模型调用记录。</td></tr>:data.units.map(u=><tr key={u.skill}><td><b>{u.code}</b></td><td>{u.name}</td><td className="fine">{u.skill}</td><td>{u.calls}</td><td>{u.tokens_in.toLocaleString()} / {u.tokens_out.toLocaleString()}</td><td>{u.failure_rate==null?'待接入':(u.failure_rate*100).toFixed(1)+'%'}</td><td>{u.last_at?new Date(u.last_at).toLocaleString():'—'}</td><td><button className="btn small" disabled title="暂停接口待接入">暂停</button></td></tr>)}</tbody></table></div></div>
 <div className="card"><div className="card-head"><h2>未接入能力</h2></div><div className="card-body"><ul className="checklist">{data.limitations.map(x=><li key={x}>{x}</li>)}</ul></div></div></>}
 </>;
}
