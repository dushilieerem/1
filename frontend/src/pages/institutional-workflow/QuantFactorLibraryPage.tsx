import {useEffect,useState} from 'react';
import {loadFactors,type FactorMeta} from '@/lib/factorCatalog';
import {createProject,saveProject} from '@/lib/detectStore';
import {researchFetch,subscribeAuth} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';
import {useNavigate} from 'react-router-dom';

type Reference={rank_ic:number|null;rank_ic_raw?:number|null;rank_ic_note?:string;turnover:number|null;universe:string;period:string;note:string}|null;
type Imported={id:string;source_library:string;source_factor_id:string;factor_name:string;display_name:string;definition:string;category:string;status:string;metrics_status:string;reference:Reference};
type Row={kind:'platform'|'imported';name:string;library:string;display:string;definition:string;category:string;status:string;reference:Reference;body?:string};

export function QuantFactorLibraryPage(){
 const navigate=useNavigate();
 const [imported,setImported]=useState<Imported[]>([]);
 const [factors,setFactors]=useState<FactorMeta[]>([]);
 const [filter,setFilter]=useState('all');
 const [query,setQuery]=useState('');
 const [selected,setSelected]=useState<Row>();
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 useEffect(()=>{
  let alive=true;setLoading(true);
  researchFetch('/api/inst/quant/factor-workflow/imports/svquant-existing/reference')
   .then(r=>r.ok?r.json():Promise.reject(Error('导入资产读取失败')))
   .then(d=>{if(alive)setImported(d.items||[]);}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));});
  loadFactors(true).then(list=>{if(alive)setFactors(list.filter(f=>f.library!=='custom_lib'));}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(alive)setLoading(false);});
  const off=subscribeAuth(()=>location.reload());return()=>{alive=false;off();};
 },[]);
 async function reuse(name:string,library:string,body?:string,definition?:string){
  if(busy)return;setBusy(true);setError('');
  try{
   const p=await createProject(name,definition||name,'复现：'+name);
   await saveProject({...p,config:{...p.config,factorCodes:[name],weights:[1],powers:[1],factorLibraries:{[name]:library},...(body?{draftFactor:{name,body,description:definition||'',category:'已有因子复现'}}:{}),researchContext:{direction:'已有因子复现',question:definition||name,background:'复用来源：'+library+' / '+name}}});
   navigate('/quant/factor/workflow/'+p.id+'/F1');
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }
 const importedKeys=new Set(imported.map(x=>x.source_library+':'+x.factor_name));
 const pool:Row[]=[
  ...imported.map(x=>({kind:'imported' as const,name:x.factor_name,library:x.source_library,display:x.display_name||x.factor_name,definition:x.definition,category:x.category||'未分类',status:'导入（未经 V5 复核）',reference:x.reference,body:undefined})),
  ...factors.filter(f=>!importedKeys.has(f.library+':'+f.name)).map(f=>({kind:'platform' as const,name:f.name,library:f.library,display:f.displayName||f.name,definition:f.description,category:f.libraryLabel||'未分类',status:'平台内置',reference:null as Reference,body:f.body})),
 ];
 const rows=pool.filter(x=>filter==='all'||(filter==='imported'&&x.kind==='imported')||(filter==='platform'&&x.kind==='platform')).filter(x=>[x.name,x.display,x.definition,x.library].join(' ').toLowerCase().includes(query.toLowerCase()));
 return <>
  <WorkspaceHeading eyebrow="FACTOR FACTORY" title="因子库" description="真实目录与导入资产；参考指标为 SVQuant 面板口径，V5 正式指标缺失时显示待接入。"><button className="btn" onClick={()=>location.reload()} disabled={loading}>刷新目录</button></WorkspaceHeading>
  <FactorModuleTabs active="library"/>
  {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
  <div className="filters">{[['all','全部'],['imported','SVQuant 已有'],['platform','平台内置']].map(([k,label])=><button key={k} className={filter===k?'on':''} onClick={()=>setFilter(k)}>{label}</button>)}<button disabled title="研究用途/观察/停用状态尚未接入（P2）">研究用途</button><button disabled title="研究用途/观察/停用状态尚未接入（P2）">观察</button><button disabled title="研究用途/观察/停用状态尚未接入（P2）">停用</button><input className="search" style={{marginLeft:'auto',maxWidth:260}} value={query} placeholder="检索名称、定义、来源" onChange={e=>setQuery(e.target.value)}/></div>
  <div className="card"><div className="table-wrap"><table className="table library-table"><thead><tr><th>因子</th><th>来源</th><th>类别</th><th>Rank IC</th><th>t</th><th>日均单边换手</th><th>近 60 日 IC</th><th>状态</th><th>操作</th></tr></thead><tbody>
   {loading?<tr><td colSpan={9}>正在读取真实因子目录…</td></tr>:rows.map(x=><tr key={x.library+':'+x.name}><td><button className="text-link" onClick={()=>setSelected(x)}><strong>{x.display}</strong></button><p className="fine">{x.name}</p></td><td>{x.kind==='imported'?'SVQuant 已有':x.library}</td><td>{x.category||'—'}</td><td>{x.reference?.rank_ic!=null?Number(x.reference.rank_ic).toFixed(3):x.reference?.rank_ic_raw!=null?<span title={'原值 '+x.reference.rank_ic_raw}>口径异常</span>:'待接入'}</td><td>待接入</td><td>{x.reference?.turnover==null?'待接入':(Number(x.reference.turnover)*100).toFixed(2)+'%'}</td><td>待接入</td><td><span className={'badge '+(x.kind==='imported'?'gray':'blue')}>{x.status}</span></td><td><button className="btn small" disabled={busy} onClick={()=>setSelected(x)}>详情</button></td></tr>)}</tbody></table></div>{!loading&&rows.length===0&&<p className="card-pad empty">没有符合条件的因子。</p>}<div className="card-body" style={{borderTop:'1px solid var(--line)'}}><p className="fine">统一口径：真实因子目录；已有 Rank IC/换手为 SVQuant 面板口径。平台共 {pool.length} 项，当前显示 {rows.length} 项；t 与近 60 日 IC 待接入（P2），不填场景值。</p></div></div>
  {selected&&<div className="card card-pad" style={{marginTop:12}}><div className="row-flex"><h2>{selected.display}</h2><span className="badge gray">{selected.status}</span></div><div className="kv" style={{marginTop:10}}><span>标识</span><div>{selected.name}</div><span>来源</span><div>{selected.library}</div><span>定义</span><div>{selected.definition}</div><span>参考指标</span><div>{selected.reference?`${selected.reference.universe} / ${selected.reference.period} · Rank IC ${selected.reference.rank_ic==null?'待接入':Number(selected.reference.rank_ic).toFixed(3)} · 换手 ${selected.reference.turnover==null?'待接入':(Number(selected.reference.turnover)*100).toFixed(0)+'%'}`:'无参考缓存；V5 正式指标待接入'}</div></div><p className="fine">参考指标是 yg_v1 面板口径（多空、20 日调仓、零费率），不是 import-benchmark-v1 正式指标；Rank IC 为小数、换手为单边日均比例；源表按百分数点存储，已除以 100。不从汇总 IC 反推 NW t。</p>{selected.body?<pre className="code-preview">{selected.body}</pre>:<p className="hint">源码不可见（RE 内置），以可执行库/因子引用登记。</p>}<button className="btn primary" disabled={busy} onClick={()=>void reuse(selected.name,selected.library,selected.body,selected.definition)}>基于此因子建立研究</button></div>}
 </>;
}
