import {useEffect,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import {listAllDetectRuns,listRuns,type DetectRunRecord} from '@/lib/detectStore';
import {subscribeAuth} from '@/lib/researchClient';
import {WorkspaceHeading,FactorModuleTabs} from './QuantWorkspacePages';
import {quantReportPath} from './QuantFactorShell';
export function QuantFactorReportsPage(){
 const {projectId}=useParams(),[runs,setRuns]=useState<DetectRunRecord[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;setLoading(true);setError('');setRuns([]);(projectId?listRuns(projectId):listAllDetectRuns()).then(r=>{if(alive)setRuns(r);}).catch(e=>{if(alive)setError(e.message);}).finally(()=>{if(alive)setLoading(false);});const off=subscribeAuth(()=>setRevision(n=>n+1));return()=>{alive=false;off();};},[projectId,revision]);
 return <><WorkspaceHeading title="因子工厂" description="保存每次实验的代码、参数、数据版本与结果，失败研究同样留档。"><button className="btn" onClick={()=>setRevision(n=>n+1)}>刷新记录</button>{projectId&&<Link className="btn primary" to={'/quant/factor/workflow/'+projectId+'/F4'}>返回研发检验</Link>}</WorkspaceHeading><FactorModuleTabs active="experiments" projectId={projectId}/><div className="card"><div className="card-head"><h2>{projectId?'当前研究的实验报告':'我的实验报告'}</h2><span className="fine">{runs.length} 份已保存报告</span></div>{loading?<p className="card-pad" role="status">正在读取报告…</p>:error?<p role="alert" className="hint error">{error}<button className="btn small" onClick={()=>setRevision(n=>n+1)}>重新读取</button></p>:<><div className="table-wrap"><table className="table"><thead><tr><th>因子 / 实验</th><th>完成时间</th><th>耗时</th><th>操作</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td><strong>{r.factorName||r.description||'因子实验'}</strong><p className="fine">{r.remark||r.id}</p></td><td>{r.finishedAt?new Date(r.finishedAt).toLocaleString():'未记录'}</td><td>{r.elapsedSec} 秒</td><td><Link className="btn small" to={quantReportPath(r.id)}>查看实验报告</Link></td></tr>)}</tbody></table></div>{runs.length===0&&<p className="empty">当前没有已保存的检测报告。从研发检验执行真实实验后，报告会出现在这里。</p>}</>}</div></>;
}
