import {useEffect,useRef,useState} from 'react';
import {loadFactors,builtinCategoryLabelsFromFactors,SV_CATEGORY_LABEL_ORDER,type FactorMeta} from '@/lib/factorCatalog';
import {createProject,saveProject} from '@/lib/detectStore';
import {researchFetch,subscribeAuth} from '@/lib/researchClient';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';
import {useNavigate,useSearchParams} from 'react-router-dom';
import {getQuantSession} from '@/lib/quantAuth';
import {loadResearchAssets,loadResearchAsset,reuseResearchAsset,type ResearchAsset,type ResearchAssetSummary} from '@/lib/factorResearchAssets';
import {FactorResearchAssetDetails} from './FactorResearchAssetDetails';
import {FactorLibraryDetailDrawer} from './FactorLibraryDetailDrawer';
import {DataDialog} from './QuantDataCatalog';

type Reference={rank_ic:number|null;rank_ic_raw?:number|null;rank_ic_note?:string;turnover:number|null;universe:string;period:string;note:string}|null;
type Imported={id:string;source_library:string;source_factor_id:string;factor_name:string;display_name:string;definition:string;category:string;status:string;metrics_status:string;reference:Reference};
export type Row={assetId?:string;importedId?:string;sourceFactorId?:string;kind:'platform'|'imported'|'research';name:string;library:string;display:string;definition:string;category:string;tags:string[];status:string;reference:Reference;body?:string};

const categoryLabel=(value?:string)=>{const label=(value||'').trim();return label&&!/^SV[0-9]+$/i.test(label)?label:'';};
export function QuantFactorLibraryPage(){
 const navigate=useNavigate();
 const [search,setSearch]=useSearchParams();const assetId=search.get('asset');
 const [researchAssets,setResearchAssets]=useState<ResearchAssetSummary[]>([]),[assetDetail,setAssetDetail]=useState<ResearchAsset>();
 const detailSerial=useRef(0);const canReuse=getQuantSession()?.permissions.quant==='write';
 const [imported,setImported]=useState<Imported[]>([]);
 const [factors,setFactors]=useState<FactorMeta[]>([]);
 const [category,setCategory]=useState('all'),[tag,setTag]=useState('all');
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
  void loadResearchAssets().then(d=>{if(alive)setResearchAssets(d.assets||[]);}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));});
  loadFactors(true).then(list=>{if(alive)setFactors(list.filter(f=>f.library!=='custom_lib'));}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(alive)setLoading(false);});
  const off=subscribeAuth(()=>location.reload());return()=>{alive=false;++detailSerial.current;off();};
 },[]);
 useEffect(()=>{const n=++detailSerial.current;setAssetDetail(undefined);if(!assetId)return;setSelected(undefined);setError('');void loadResearchAsset(assetId).then(a=>{if(n===detailSerial.current)setAssetDetail(a);}).catch(e=>{if(n===detailSerial.current)setError(e instanceof Error?e.message:String(e));});return()=>{++detailSerial.current;};},[assetId]);
 function selectRow(row:Row){setSelected(row);setAssetDetail(undefined);setSearch(row.assetId?{asset:row.assetId}:{});}
 async function reuseFixedAsset(){if(!assetDetail||busy||!canReuse)return;setBusy(true);setError('');try{const project=await reuseResearchAsset(assetDetail);navigate('/quant/factor/workflow/'+project.id+'/F1');}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
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
  ...researchAssets.filter(a=>a.kind==='novel_factor').map(a=>({kind:'research' as const,assetId:a.id,name:a.source_factor?.factor_name||a.display_name,library:'机构研究库',display:a.display_name,definition:a.hypothesis,category:a.category,tags:a.tags,status:'已批准 · 研究用途',reference:null})),
  ...imported.map(x=>{const meta=factors.find(f=>f.library===x.source_library&&f.name===x.factor_name);return {kind:'imported' as const,importedId:x.id,sourceFactorId:x.source_factor_id,name:x.factor_name,library:x.source_library,display:x.display_name||x.factor_name,definition:x.definition,category:categoryLabel(x.category)||categoryLabel(meta?.libraryLabel)||'未分类',tags:[] as string[],status:'基础因子',reference:x.reference,body:undefined};}),
  ...factors.filter(f=>!importedKeys.has(f.library+':'+f.name)).map(f=>({kind:'platform' as const,name:f.name,library:f.library,display:f.displayName||f.name,definition:f.description,category:categoryLabel(f.libraryLabel)||'未分类',tags:[] as string[],status:'基础因子',reference:null as Reference,body:f.body})),
 ];
 const tags=[...new Set(pool.flatMap(x=>x.tags))].sort();
 const present=new Set(pool.map(x=>x.category));
 const categories=[...SV_CATEGORY_LABEL_ORDER,...builtinCategoryLabelsFromFactors(factors),...[...present].sort((a,b)=>a.localeCompare(b,'zh'))].filter((label,i,list)=>present.has(label)&&list.indexOf(label)===i);
 const rows=pool.filter(x=>category==='all'||x.category===category).filter(x=>tag==='all'||x.tags.includes(tag)).filter(x=>[x.name,x.display,x.definition,...x.tags].join(' ').toLowerCase().includes(query.toLowerCase()));
 return <>
  <WorkspaceHeading eyebrow="FACTOR FACTORY" title="因子库" description="查找因子、查看研究证据并复用已批准的定义。"><button className="btn" onClick={()=>location.reload()} disabled={loading}>刷新目录</button></WorkspaceHeading>
  <FactorModuleTabs active="library"/>
  {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
  <div className="filters" role="group" aria-label="因子分类">{['all',...categories].map(key=><button key={key} className={category===key?'on':''} aria-pressed={category===key} onClick={()=>setCategory(key)}>{key==='all'?'全部':key} {key==='all'?pool.length:pool.filter(x=>x.category===key).length}</button>)}</div>
  <div className="filters"><input aria-label="搜索因子" className="search" style={{flex:'1 1 280px',maxWidth:640,margin:0}} value={query} placeholder="检索名称、定义、标签" onChange={e=>setQuery(e.target.value)}/>{tags.length>0&&<select aria-label="筛选标签" value={tag} onChange={e=>setTag(e.target.value)}><option value="all">全部标签</option>{tags.map(t=><option key={t} value={t}>{t}</option>)}</select>}</div>
  <div className="card"><div className="table-wrap"><table className="table library-table"><thead><tr><th>因子</th><th>业务分类</th><th>标签</th><th>Rank IC</th><th>t</th><th>日均单边换手</th><th>近 60 日 IC</th><th>状态</th><th>操作</th></tr></thead><tbody>
   {loading?<tr><td colSpan={9}>正在读取因子目录…</td></tr>:rows.map(x=><tr key={x.assetId||x.library+':'+x.name}><td><button className="text-link" onClick={()=>selectRow(x)}><strong>{x.display}</strong></button><p className="fine">{x.name}</p></td><td>{x.category||'未分类'}</td><td className="fine">{x.tags.length?x.tags.join('、'):'未标注'}</td><td>{x.reference?.rank_ic!=null?Number(x.reference.rank_ic).toFixed(3):x.reference?.rank_ic_raw!=null?<span title={'原值 '+x.reference.rank_ic_raw}>口径异常</span>:'未计算'}</td><td>未计算</td><td>{x.reference?.turnover==null?'未计算':(Number(x.reference.turnover)*100).toFixed(2)+'%'}</td><td>未计算</td><td><span className={'badge '+(x.kind==='imported'?'gray':'blue')}>{x.status}</span></td><td><button className="btn small" disabled={busy} onClick={()=>selectRow(x)}>详情</button></td></tr>)}</tbody></table></div>{!loading&&rows.length===0&&<p className="card-pad empty">没有符合条件的因子。</p>}<details className="ff-fold"><summary>指标口径与来源</summary><div><p className="fine">历史参考指标来自原平台面板；与当前固定验证报告的范围可能不同，不能直接当作统一验证结果。Rank IC为小数，换手为单边日均比例；原始百分数点已换算。没有逐项标签时显示未标注，不从汇总IC反推统计显著性。</p><p className="fine">可访问因子 {pool.length} 项，当前显示 {rows.length} 项。</p></div></details></div>
  {selected&&!selected.assetId&&<FactorLibraryDetailDrawer key={selected.importedId||selected.library+':'+selected.name} row={selected} onClose={()=>setSelected(undefined)} busy={busy} canReuse={canReuse} onReuse={()=>void reuse(selected.name,selected.library,selected.body,selected.definition)} replications={researchAssets.filter(a=>a.kind==='replication_validation'&&a.source_factor?.factor_name===selected.name&&a.source_factor?.library_name===selected.library)} onReplication={id=>{setSelected(undefined);setSearch({asset:id});}}/>}
  {assetDetail&&<div className="quant-data ff-library-drawer"><DataDialog drawer title={assetDetail.display_name} subtitle={'第 '+assetDetail.version+' 版 · 已登记研究资产'} doneLabel="关闭" onClose={()=>{setAssetDetail(undefined);setSearch({});}}><FactorResearchAssetDetails asset={assetDetail} busy={busy} canReuse={canReuse} onReuse={()=>void reuseFixedAsset()}/></DataDialog></div>}

 </>;
}
