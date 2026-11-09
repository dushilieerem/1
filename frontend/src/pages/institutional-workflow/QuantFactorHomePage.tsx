import {useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactElement} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {createProject,saveProject} from '@/lib/detectStore';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';
import {newUuidV4} from '@/lib/uuid';
import {getQuantSession} from '@/lib/quantAuth';
import {ensureBranchForStart,ensureTopicForProject,type TaskIdentity} from '@/lib/factorTaskIdentity';

type Topic={id:string;display_no?:number;project_id:string;project_name:string;view_id:string;primary_holding_period:number;max_trials:number;max_sealed:number;sealed_used?:number;status:string;dispatch_status?:string|null;dispatch_stop_reason?:string|null;pending_review?:number;sealed_passed?:number;latest_outcome?:string|null;research_purpose?:string|null;k:number;branch_count:number;trial_count:number;created_at?:string};
type Branch={id:string;topic_id:string;parent_id?:string|null;source:string;status:string;hypothesis_version:number;implementation_version:number;created_at?:string;display_label?:string;display_title?:string;hypothesis_text?:string;source_label?:string;display_status?:string};
type Trial={trial_no:number;branch_id:string;kind:string;outcome:string;executor:string;report_id?:string|null;created_at?:string;returned_metrics?:boolean;rerun_of?:string|null;result_summary?:{gate?:{checks?:{name:string;actual:number|null;threshold:number;passed:boolean}[]}}};
type Ledger={topic:Topic;branches:Branch[];trials:Trial[];k:number;threshold:number|null;threshold_next_if_counted:number;next_trial_no:number;dispatch?:{status:string;stop_reason:string}|null};

const statusText=(t:Pick<Topic,'status'|'dispatch_status'|'pending_review'|'sealed_passed'|'latest_outcome'>)=>{
 if(t.status==='paused')return '已暂停';
 if(t.status==='archived')return '已归档';
 if((t.pending_review||0)>0)return '待复核';
 if(t.dispatch_status==='running')return '研究决策运行中';
 if(t.dispatch_status==='queued')return '排队中';
 if(t.dispatch_status==='stopped'){
  if((t.sealed_passed||0)>0)return '已停止 · 待提交复核';
  if(t.latest_outcome==='passed')return '已停止 · 待封存';
  return '已停止 · 待人工复盘';
 }
 if(t.dispatch_status==='completed')return '研究决策完成';
 if(t.dispatch_status==='error'||t.dispatch_status==='failed')return '研究决策异常';
 return '待启动';
};

const purposeText=(p?:string|null)=>p==='replication'?'复现':p==='discovery'?'新发现':'类型未记录';
const outcomeText=(t:Trial)=>t.outcome==='passed'?'通过':t.outcome==='failed'?'未达标':t.outcome==='error'?'执行错误':t.outcome;
const nwText=(t:Trial)=>{const c=t.result_summary?.gate?.checks?.find(x=>x.name==='方向 NW t');return c&&typeof c.actual==='number'?` · NW t ${c.actual.toFixed(2)} / 需 ${c.threshold.toFixed(2)}`:'';};

export function QuantFactorHomePage(){
 const [topics,setTopics]=useState<Topic[]>([]);
 const [selected,setSelected]=useState<string>();
 const [ledger,setLedger]=useState<Ledger>();
 const [node,setNode]=useState<string>();
 const [f0,setF0]=useState<{id:string;status:string;decision?:{candidate_status?:string;reason?:string;steps?:Array<{step:number;decision:{action:string;rationale:string};usage?:{tokens_in?:number;tokens_out?:number};result:{status?:string;candidate_status?:string;reason?:string;needed_capabilities?:string[]}}>};stop_reason?:string}>();
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[starting,setStarting]=useState(false);
 const canManage=!!getQuantSession()?.can_manage;
 const [paused,setPaused]=useState(false),[controlBusy,setControlBusy]=useState(false);
 const [loading,setLoading]=useState(true);
 const [stageView,setStageView]=useState<'prepare'|'development'|'validation'|'approval'>('prepare');
 const [pending,setPending]=useState<number|null>(null);
 const [sealedUsed,setSealedUsed]=useState<number|null>(null);
 const [authOpen,setAuthOpen]=useState(false);
 const [creating,setCreating]=useState(false),[creatingBusy,setCreatingBusy]=useState(false),[createErr,setCreateErr]=useState('');
 const [createdTask,setCreatedTask]=useState<TaskIdentity>();
 const creatingLock=useRef(false);
 const [importedFactors,setImportedFactors]=useState<Array<{source_library:string;factor_name:string;display_name?:string}>>([]);
 const [nt,setNt]=useState({name:'新因子挖掘任务',universe:'CSI500',benchmark:'CSI500',development_start:'2022-01-01',development_end:'2024-12-31',validation_start:'2025-01-01',validation_end:'2025-12-31',holding:1,max_trials:8,max_sealed:1,factor:'',library:'主因子库',direction:'negative',hypothesis:'短周期因子在截面上有稳定预测力',acceptance:'方向 Rank IC ≥ 0.005，NW t ≥ t*(K)，有效观测 ≥ 60，最大回撤 ≤ 0.5',purpose:'discovery' as 'replication'|'discovery'});
 const treeRef=useRef<HTMLDivElement|null>(null);
 const [treeLines,setTreeLines]=useState<string[]>([]);
 const navigate=useNavigate();

 useEffect(()=>{
  let alive=true;setLoading(true);
  researchFetch('/api/inst/quant/factor-workflow/topics')
   .then(r=>r.ok?r.json():Promise.reject(Error('挖掘任务读取失败')))
   .then(d=>{if(!alive)return;const list=d.topics||[];setTopics(list);setSelected(cur=>cur&&list.some((t:Topic)=>t.id===cur)?cur:list[0]?.id);})
   .catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e));})
   .finally(()=>{if(alive)setLoading(false);});
  void researchFetch('/api/inst/quant/factor-workflow/overview').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d?.counts)setSealedUsed(Number(d.counts.sealed_used)||0);});
  void researchFetch('/api/inst/quant/factor-workflow/pending-review-count').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d&&typeof d.count==='number')setPending(d.count);});
  return()=>{alive=false;};
 },[]);

 async function refreshTopics(){
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics');
  if(!r.ok)return;
  const d=await r.json();const list=d.topics||[];
  setTopics(list);
  setSelected(cur=>cur&&list.some((t:Topic)=>t.id===cur)?cur:list[0]?.id);
 }
 async function refreshLedgerFor(id:string){
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(id)+'/ledger');
  if(!r.ok)return;
  const d=await r.json();setLedger(d);
  setNode(cur=>cur&&(d.branches||[]).some((b:Branch)=>b.id===cur)?cur:(d.branches||[])[0]?.id);
 }
 async function refreshPending(){
  const r=await researchFetch('/api/inst/quant/factor-workflow/pending-review-count');
  if(!r.ok)return;
  const d=await r.json();if(d&&typeof d.count==='number')setPending(d.count);
 }
 async function refreshAfterRun(){
  if(!selected)return;
  await Promise.all([refreshTopics(),refreshLedgerFor(selected),refreshPending()]);
 }

 useEffect(()=>{let alive=true;void researchFetch('/api/inst/quant/factor-workflow/controls').then(r=>r.ok?r.json():null).then(d=>{if(alive&&d)setPaused(!!d.paused);});return()=>{alive=false;};},[]);

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
  if(!ledger||!selectedBranch||starting)return;
  setStarting(true);setError('');setNotice('正在提交研究决策…');
  try{
   const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/branches/'+encodeURIComponent(selectedBranch.id)+'/f0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idempotency_key:newUuidV4()})});
   const d=await r.json();if(!r.ok){setNotice('');setError(typeof d.detail==='string'?d.detail:'F0 启动失败');return;}
   setF0(d);
   setTopics(list=>list.map(t=>t.id===ledger.topic.id?{...t,dispatch_status:d.status,dispatch_stop_reason:''}:t));
   setNotice(d.status==='queued'?'研究决策已提交，正在排队…':d.status==='running'?'研究决策已启动，正在运行…':'研究决策已创建，状态：'+d.status);
  }catch(e){setNotice('');setError(e instanceof Error?e.message:String(e));}finally{setStarting(false);}
 }
 useEffect(()=>{if(!f0||!['queued','running'].includes(f0.status))return;const t=setInterval(()=>{void researchFetch('/api/inst/quant/factor-workflow/f0-runs/'+f0.id).then(r=>r.ok?r.json():null).then(d=>{if(!d)return;setF0(d);if(!['queued','running'].includes(d.status))void refreshAfterRun();});},4000);return()=>clearInterval(t);},[f0?.id,f0?.status,selected]);
 useEffect(()=>{if(!f0||!ledger)return;setTopics(list=>list.map(t=>t.id===ledger.topic.id?{...t,dispatch_status:f0.status,dispatch_stop_reason:f0.stop_reason||''}:t));},[f0?.status,f0?.stop_reason]);
 async function toggleGlobalPause(){
  if(!canManage||controlBusy)return;setControlBusy(true);setError('');setNotice('');
  try{const r=await researchFetch('/api/inst/quant/factor-workflow/controls/pause',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paused:!paused})});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'全局暂停操作失败');setPaused(!!d.paused);setNotice(d.paused?'全部研究已暂停：不再启动新的自动动作，在途计算保留记录。':'全部研究已恢复，可继续启动。');}
  catch(e){setError(e instanceof Error?e.message:String(e));}finally{setControlBusy(false);}
 }
 async function setTopicStatus(status:'paused'|'active'){
  if(!ledger)return;
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/'+(status==='paused'?'pause':'resume'),{method:'POST'});
  const d=await r.json();if(!r.ok){setError(typeof d.detail==='string'?d.detail:'挖掘任务状态更新失败');return;}
  setTopics(list=>list.map(t=>t.id===d.id?{...t,status:d.status}:t));
  setNotice(status==='active'?'挖掘任务已恢复，点击“启动研究”开始研究决策。':'挖掘任务已暂停，不会继续调度。');
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
 useEffect(()=>{if(!creating||importedFactors.length)return;void researchFetch('/api/inst/quant/factor-workflow/imports/svquant-existing/reference').then(r=>r.ok?r.json():null).then(d=>{if(d)setImportedFactors(d.items||[]);});},[creating,importedFactors.length]);
 async function loadFirstBranch(topicId:string):Promise<string|undefined>{
  try{const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(topicId)+'/ledger');if(!r.ok)return undefined;const d=await r.json();return d.branches?.[0]?.id;}catch{return undefined;}
 }
 async function startCreatedTask(task:TaskIdentity){
  const prep=await ensureBranchForStart(task,{loadLedger:async id=>{const branchId=await loadFirstBranch(id);return {branches:branchId?[{id:branchId}]:[]};}});
  setCreatedTask(prep.identity);
  if(prep.error){setError(prep.error);return false;}
  const topicId=prep.identity.topicId!;const branchId=prep.identity.branchId!;
  try{
   const fr=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(topicId)+'/branches/'+encodeURIComponent(branchId)+'/f0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idempotency_key:newUuidV4()})});
   const fd=await fr.json();if(!fr.ok){setError(typeof (fd.detail||fd.error)==='string'?(fd.detail||fd.error):'任务已创建，但启动失败，可在任务详情重试。');return false;}
   setNotice('挖掘任务已创建并启动研究，等待排队/运行状态。');return true;
  }catch(e){setError('任务已创建，但启动请求失败：'+(e instanceof Error?e.message:String(e))+'；请稍后重试，不会重复创建任务。');return false;}
 }
 async function createTopic(start=true){
  if(creatingLock.current)return;
  creatingLock.current=true;setCreatingBusy(true);setCreateErr('');setError('');
  try{
   let task:TaskIdentity|undefined=createdTask;
   if(!task){
    const p=await createProject(nt.factor,nt.hypothesis,nt.name);
    const plan={revision:'nt-'+Date.now(),hypothesis:nt.hypothesis,candidateExpression:'',improvementScope:'只改进实现，不改变经济假设和方向',target:'未来1个交易日收益',frequency:'daily',acceptance:nt.acceptance,developmentStart:nt.development_start,developmentEnd:nt.development_end,validationStart:nt.validation_start,validationEnd:nt.validation_end,maxTrials:Number(nt.max_trials),researchPurpose:nt.purpose,...(nt.purpose==='discovery'?{noveltyPolicy:{scope:'all_accessible' as const,maxAbsCorrelation:0.7,minDays:60,minPairs:30,minCoverage:0.8}}:{}),rules:{minSignedIc:0.005,maxDrawdown:0.5,minObservations:60,direction:nt.direction as 'positive'|'negative',icMetric:'rank_ic' as const}};
    const saved=await saveProject({...p,name:nt.name,description:nt.hypothesis,config:{...p.config,universe:nt.universe,benchmark:nt.benchmark,factorCodes:nt.factor?[nt.factor]:[],weights:nt.factor?[1]:[],powers:nt.factor?[1]:[],factorLibraries:nt.factor?{[nt.factor]:nt.library}:{},researchPlan:plan,researchContext:{direction:'因子研究',question:nt.hypothesis,background:'新建挖掘任务：'+nt.factor}}});
    task={projectId:saved.id};setCreatedTask(task);
   }
   if(!task.topicId){
    const vr=await researchFetch('/api/inst/quant/factor-workflow/published-view');const v=await vr.json();if(!vr.ok)throw Error('发布视图读取失败');
    const body={view_id:v.view_id,release_id:'',release_ids:v.release_ids||{},view_manifest_sha256:v.view_manifest_sha256||'',contract_revision:v.contract_revision||'',as_of:v.as_of,development_start:nt.development_start,development_end:nt.development_end,validation_start:nt.validation_start,validation_end:nt.validation_end,primary_holding_period:Number(nt.holding),policy_version:'v5-p0',max_trials:Number(nt.max_trials),max_sealed:Number(nt.max_sealed)};
    const identity=await ensureTopicForProject(task,{
     listProjectTopics:async(projectId)=>{
      const r=await researchFetch('/api/inst/quant/factor-workflow/projects/'+encodeURIComponent(projectId)+'/topics');if(!r.ok)throw Error('读取项目已有挖掘任务失败');const d=await r.json();return (d.topics||[]).map((t:{id:string;branch_id?:string|null})=>({id:t.id,branch_id:t.branch_id}));
     },
     createTopic:async(projectId)=>{
      const tr=await researchFetch('/api/inst/quant/factor-workflow/projects/'+encodeURIComponent(projectId)+'/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const td=await tr.json();if(!tr.ok)throw Error(typeof (td.detail||td.error)==='string'?(td.detail||td.error):'建挖掘任务失败');return {id:td.topic.id};
     },
    });
    task=identity;setCreatedTask(identity);
   }
   const rl=await researchFetch('/api/inst/quant/factor-workflow/topics');const d=await rl.json();setTopics(d.topics||[]);if(task.topicId)setSelected(task.topicId);
   if(!start){setNotice('草稿已保存，未启动研究。');setCreating(false);setCreatedTask(undefined);return;}
   const ok=await startCreatedTask(task);
   setCreating(false);
   if(ok)setCreatedTask(undefined);
  }catch(e){setCreateErr(e instanceof Error?e.message:String(e));}
  finally{creatingLock.current=false;setCreatingBusy(false);}
 }
 const topic=topics.find(t=>t.id===selected);
 useEffect(()=>{if(!topic)return;if((topic.pending_review||0)>0||(topic.sealed_passed||0)>0)setStageView('validation');else if((topic.trial_count||0)>0)setStageView('development');else setStageView('prepare');},[topic?.id]); // 仅切换任务时定位真实当前环节；用户点环节不反向推进
 const stageDefs=[
  {id:'prepare' as const,label:'研究准备',hint:'任务、数据视图与预算'},
  {id:'development' as const,label:'因子研发',hint:'真实检验与迭代'},
  {id:'validation' as const,label:'独立验证',hint:'封存与复核'},
  {id:'approval' as const,label:'审批入库',hint:'审批与因子库'},
 ];
 const stageDone=(id:typeof stageDefs[number]['id'])=>{
  if(id==='prepare')return !!topic;
  if(id==='development')return (topic?.trial_count||0)>0&&((topic?.pending_review||0)>0||(topic?.sealed_passed||0)>0);
  if(id==='validation')return (topic?.sealed_passed||0)>0&&(topic?.pending_review||0)===0;
  return false;
 };
 const stageCurrent=(id:typeof stageDefs[number]['id'])=>{
  if(!topic)return id==='prepare';
  if(id==='prepare')return false;
  if(id==='development')return (topic.trial_count||0)===0||((topic.pending_review||0)===0&&(topic.sealed_passed||0)===0);
  if(id==='validation')return (topic.pending_review||0)>0;
  return false;
 };
 const agentWork=!topic?'暂无挖掘任务：可新建任务或从因子库发起。':topic.dispatch_status==='running'||topic.dispatch_status==='queued'?'研究决策正在推进当前分支，页面只读观察，不会推动阶段。':(topic.pending_review||0)>0?'独立验证有结果待复核，等待人工决定。':(topic.sealed_passed||0)>0?'封存已通过，等待提交独立复核。':topic.trial_count===0?'等待启动首次真实研发检验。':'当前无自动运行；可查看研究树、重试启动或到人工工作台接手。';
 const stagePanel=topic?(
  <div className="stage-panel">
   <div className="stage-panel-head"><div><span className="eyebrow">CURRENT STAGE VIEW</span><h3>{stageDefs.find(s=>s.id===stageView)?.label}</h3></div><span className="badge">{stageCurrent(stageView)?'当前环节':stageDone(stageView)?'已发生过':'未开始'}</span></div>
   {stageView==='prepare'&&<p className="fine">挖掘任务 T{topic.display_no??'—'} · {purposeText(topic.research_purpose)} · 视图 {topic.view_id} · 主持有期 {topic.primary_holding_period} 日 · 试验预算 {topic.max_trials}。阶段导航只用于查看，不会改变任务状态或阶段。</p>}
   {stageView==='development'&&<p className="fine">已登记 {topic.trial_count} 次检验，计入 K {topic.k}/{topic.max_trials}，分支 {topic.branch_count} 个。研究树与迭代记录在下方详情中，保留 H1/Ha/Hb 与虚线父子关系。</p>}
   {stageView==='validation'&&<p className="fine">封存通过 {topic.sealed_passed||0} 次，待复核 {topic.pending_review||0} 项。独立验证由真实封存记录和复核意见构成，不能通过点击阶段推进。</p>}
   {stageView==='approval'&&<p className="fine">待审批 {pending==null?'读取中':pending} 项。审批与入库在“待审批”和“因子库”入口完成，本页只显示真实状态。</p>}
   <div className="actions"><Link className="btn small" to={'/quant/reviews/factors'}>查看待审批</Link><Link className="btn small" to="/quant/factor/library">打开因子库</Link></div>
  </div>
 ):null;
 const selectedBranch=(ledger?.branches||[]).find(b=>b.id===node);
 const feed=useMemo(()=>[...(ledger?.trials||[])].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||'')).slice(0,12),[ledger]);
 const totalTrials=topics.reduce((n,t)=>n+t.trial_count,0);
 const capabilityGaps=useMemo(()=>Array.from(new Set((f0?.decision?.steps||[]).flatMap(s=>s.result?.needed_capabilities||[]))),[f0]);

 function branchNode(b:Branch,depth=0):ReactElement{
  const trials=trialsByBranch.get(b.id)||[];
  return (
   <div key={b.id} className="branch-wrap">
    <div className={'branch'+(b.source==='manual'?' human':'')+(node===b.id?' sel':'')} data-bid={b.id} data-parent={b.parent_id||''} onClick={()=>setNode(b.id)} role="button" tabIndex={0}>
     <div className="bh">
      <span className="hid">{b.display_label||'H?'}</span>
      <span className="bt" title={b.display_title}>{b.display_title? (b.display_title.length>70?b.display_title.slice(0,70)+'…':b.display_title) : ('假设 v'+b.hypothesis_version+'（未命名）')}</span>
      <span className={'badge '+(b.display_status==='研发通过'||b.display_status==='封存通过，待提交'?'live':b.display_status?.includes('失败')||b.display_status==='未达标'?'gray':'gray')}>{b.display_status||b.status}</span>
      <span className="by">{b.source_label||(b.source==='manual'?'人工':'Agent')} · v{b.hypothesis_version}/v{b.implementation_version} · {trials.length} 次</span>
     </div>
     {trials.length>0&&<div className="steps">{trials.map(t=>{const checks=t.result_summary?.gate?.checks||[];const ic=checks.find(c=>c.name.includes('Rank IC')||c.name.includes('方向IC'));const nw=checks.find(c=>c.name.includes('NW t'));const label=`E${t.trial_no}${ic?.actual!=null?` · IC ${Number(ic.actual).toFixed(3)}`:''}${nw?.actual!=null?` · t ${Number(nw.actual).toFixed(2)} / ${Number(nw.threshold).toFixed(2)}`:` · ${outcomeText(t)}`}${t.rerun_of?' · rerun':''}${t.outcome==='passed'?' ✓':t.outcome==='failed'?' ✗':''}`;const title=checks.map(c=>`${c.name}: ${c.actual==null?'—':Number(c.actual).toFixed(3)} / ${String(c.threshold)}`).join(' · ');return t.report_id?<Link key={t.trial_no} className={'chip '+(t.outcome==='passed'?'ok':t.outcome==='failed'?'fail':'warn')} title={title} to={'/quant/factor/report/'+t.report_id}>{label}</Link>:<span key={t.trial_no} className={'chip '+(t.outcome==='passed'?'ok':t.outcome==='failed'?'fail':'warn')} title={title}>{label}</span>;})}</div>}
    </div>
    {(children.get(b.id)||[]).length>0&&<div className="children">{(children.get(b.id)||[]).map(c=>branchNode(c,depth+1))}</div>}
   </div>
  );
 }

 const topicCards=topics.map(t=>(
  <button key={t.id} className={'topic'+(selected===t.id?' sel':'')} onClick={()=>setSelected(t.id)}>
   <div className="top"><span className="tid">T{t.display_no??'—'} · {purposeText(t.research_purpose)}</span><span className={'badge '+((t.pending_review||0)>0?'live':t.dispatch_status==='running'?'live':t.dispatch_status==='stopped'?'warn':'gray')}>{statusText(t)}</span></div>
   <h3>{t.project_name||'未命名挖掘任务'}</h3>
   <div className="act">{t.trial_count>0?'已登记研发检验与台账。':'等待第一次真实研发检验。'}</div>
   <div className="bar"><i style={{width:Math.min(100,t.k/Math.max(1,t.max_trials)*100)+'%'}}/></div>
   <div className="meta"><span>台账 <b>{t.trial_count}</b> 条</span><span>计入 K <b className={t.k>t.max_trials?"bad-t":undefined}>{t.k}/{t.max_trials}</b></span><span>分支 <b>{t.branch_count}</b></span><span>封存 <b>{t.sealed_used??0}/{t.max_sealed}</b></span></div>
  </button>
 ));

 const tree=(ledger?.branches||[]).length>0?<div className="tree" ref={treeRef}>{treeLines.length>0&&<svg className="tree-lines" aria-hidden="true">{treeLines.map((d,i)=><path key={i} d={d} fill="none" stroke="#cbb8dc" strokeWidth="1" strokeDasharray="4 4"/>)}</svg>}{(children.get('root')||[]).map(b=>branchNode(b))}</div>:<div className="empty"><b>挖掘任务还没有分支</b>真实空态：无分支时不显示模拟节点。</div>;

 const trials=(selectedBranch?trialsByBranch.get(selectedBranch.id):[])||[];
 const detail=selectedBranch?(
  <div className="card">
   <div className="card-head">
    <div><div className="row-flex"><span className="hid">{selectedBranch.display_label||'H?'}</span><h2>{selectedBranch.display_title||('假设 v'+selectedBranch.hypothesis_version+'（未命名）')}</h2><span className="badge">{selectedBranch.display_status||selectedBranch.status}</span></div>
     <p className="fine">{selectedBranch.source_label||(selectedBranch.source==='manual'?'人工':'Agent')} · 假设 v{selectedBranch.hypothesis_version} / 实现 v{selectedBranch.implementation_version} · 内部 ID {selectedBranch.id.slice(0,8)}</p></div>
    <div className="actions"><button className="btn small primary" onClick={()=>void takeOver()}>从此分支接手</button><button className="btn small" onClick={()=>void handBackF0()} disabled={f0&&['queued','running'].includes(f0.status)}>交回研究系统</button>{f0&&f0.stop_reason?.includes('中断')&&<button className="btn small" onClick={()=>void resumeF0()}>继续研究决策</button>}<Link className="btn small" to={'/quant/factor/workflow/'+(topic?.project_id||'')+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>打开人工工作台</Link>{f0&&<span className="fine">研究决策：{f0.status}{f0.decision?.candidate_status?' · '+f0.decision.candidate_status:''}{f0.stop_reason?' · '+f0.stop_reason:''}</span>}</div>
   </div>
   <div className="card-body">
    {selectedBranch.hypothesis_text&&<p className="agent-brief" style={{marginBottom:12}}>{selectedBranch.hypothesis_text}</p>}
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
    {f0?.decision?.steps&&<div style={{marginTop:14}}><h3 style={{margin:'0 0 6px'}}>研究决策记录</h3>{f0.decision.steps.map(s=><div className="trial-row" key={s.step}><span className="tk">S{s.step}</span><div className="tb"><b>{s.decision.action}</b><small>{s.decision.rationale}</small></div><span className="fine">{s.result.status||''}{s.result.candidate_status?' · '+s.result.candidate_status:''}</span></div>)}</div>}
   </div>
  </div>
 ):null;

 const side=(
  <aside className="side">
   <div className="card">
    <div className="card-head"><div><h2>研究系统</h2><p className="fine">按真实状态标注，未接入不显示模拟运行</p></div></div>
    <div className="card-body">
     <div className="units">
      <div className="unit"><span className="ui">⇅</span><div><b>挖掘任务调度</b><small>规则排队/跨挖掘任务预算：未接入</small></div></div>
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
    <div><div className="row-flex"><span className="tid">T{topic.display_no??'—'} · {purposeText(topic.research_purpose)}</span><h2>{topic.project_name||'未命名挖掘任务'}</h2><span className={'badge '+((topic.pending_review||0)>0?'live':topic.dispatch_status==='running'?'live':topic.dispatch_status==='stopped'?'warn':'gray')}>{statusText(topic)}</span></div>
     <p className="fine">视图 {topic.view_id} · 主持有期 {topic.primary_holding_period} 日</p></div>
    <div className="actions">{topic.status==='active'&&(!topic.dispatch_status||topic.dispatch_status==='idle')?<button className="btn small primary" disabled={starting||!selectedBranch} onClick={()=>void handBackF0()}>{starting?'正在提交…':'启动研究'}</button>:null}{topic.status==='active'?<button className="btn small" onClick={()=>void setTopicStatus('paused')}>暂停挖掘任务</button>:topic.status==='paused'?<button className="btn small" onClick={()=>void setTopicStatus('active')}>继续挖掘任务</button>:null}<Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>打开人工工作台</Link><Link className="btn small" to={'/quant/factor/ledger?project='+topic.project_id}>台账</Link><button className="btn small ghost" disabled title="待接入（P1）：研究意见写回研究决策上下文尚未实现">给研究意见</button></div>
   </div>
   <div className="card-body">
    <div className="ledger">
     <span>台账 <b>{ledger?.trials.length??0}</b> 条 · 计入 K <b className={(ledger?.k??topic.k)>topic.max_trials?"bad-t":undefined}>{ledger?.k??topic.k}</b> / {topic.max_trials}</span>
     <span>分支 <b>{topic.branch_count}</b></span>
     <span>当前 t*(K) <b>{ledger?.threshold==null?'待接入':ledger.threshold.toFixed(3)}</b></span>
     <span>下一次可计数检验 t* <b>{ledger?.threshold_next_if_counted?.toFixed(3)||'待接入'}</b></span>
     {ledger?.dispatch&&<span title={ledger.dispatch.stop_reason}>调度 <b>{ledger.dispatch.status==='running'?'研究决策运行中':ledger.dispatch.status==='stopped'?'研究决策已停止':ledger.dispatch.status}</b>{ledger.dispatch.stop_reason?' · 交人工复盘':''}</span>}
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
    <button className="btn primary" onClick={()=>setCreating(v=>!v)}>{creating?'收起新建':'新建挖掘任务'}</button>
   </WorkspaceHeading>
   <FactorModuleTabs active="home"/>
   {authOpen&&<div className="card card-pad" style={{marginBottom:14}}><p className="fine">当前登录成员可在本机构范围创建因子挖掘任务、运行检验与申请封存；数据视图与预登记门槛由挖掘任务计划固定，Agent 不能改门槛、扩预算或批准入库。新建挖掘任务从因子库选择已授权资产开始。</p></div>}
   <div className="sys compact">
    <div className="sys-state"><span className="ico">⇅</span><div><b><span className={"live-dot"+(topics.some(t=>t.dispatch_status==='running'||t.dispatch_status==='queued')?'':' off')}/> {topics.some(t=>t.dispatch_status==='running'||t.dispatch_status==='queued')?'因子研究系统运行中':topics.some(t=>(t.pending_review||0)>0)?'因子研究系统空闲 · 待复核':topics.some(t=>t.dispatch_status==='stopped'&&(t.sealed_passed||0)>0)?'因子研究系统空闲 · 待提交复核':topics.some(t=>t.dispatch_status==='stopped'&&t.latest_outcome==='passed')?'因子研究系统空闲 · 待封存':topics.some(t=>t.dispatch_status==='stopped')?'因子研究系统空闲 · 待人工复盘':'因子研究系统空闲 · 待启动'}</b><small className="fine">{loading?'读取中':`真实挖掘任务 ${topics.length} 个 · 台账 ${totalTrials} 次 · 运行中 ${topics.filter(t=>t.dispatch_status==='running'||t.dispatch_status==='queued').length}`}</small></div></div>
    <div className="kpis">
     <div className="kpi"><span>挖掘任务</span><b>{topics.length}</b><small>运行中 {topics.filter(t=>t.dispatch_status==='running'||t.dispatch_status==='queued').length} · 待复核 {topics.filter(t=>(t.pending_review||0)>0).length} · 待复盘 {topics.filter(t=>t.dispatch_status==='stopped'&&!(t.pending_review||0)&&!(t.sealed_passed||0)&&t.latest_outcome!=='passed').length}</small></div>
     <div className="kpi"><span>试验台账</span><b>{totalTrials}</b><small>次</small></div>
     <div className="kpi"><span>封存样本已用</span><b>{sealedUsed==null?'—':sealedUsed}</b><small>累计封存（含失败）</small></div>
     <div className="kpi"><span>待人决定</span><b>{pending==null?'—':pending}</b><small>待复核候选</small></div>
     <div className="kpi"><span>Token</span><b>{f0?.decision?.steps?f0.decision.steps.reduce((n,s)=>n+(s.usage?.tokens_in||0)+(s.usage?.tokens_out||0),0):'—'}</b><small>最近一次研究决策</small></div>
    </div><div className="actions"><button className="btn small" disabled={!canManage||controlBusy} onClick={()=>void toggleGlobalPause()} title={canManage?(paused?"恢复全部自动研究":"全局暂停，不启动新自动动作"):"需要研究负责人权限"}>{paused?"恢复全部":"暂停全部（AC-12）"}</button></div>
   </div>
   {!loading&&<div className="stage-board">
    <div className="stage-nav" role="tablist" aria-label="因子业务环节（仅查看）">
     {stageDefs.map((s,i)=><button key={s.id} type="button" role="tab" aria-selected={stageView===s.id} className={'stage-step'+(stageView===s.id?' active':'')+(stageDone(s.id)?' done':'')} onClick={()=>setStageView(s.id)}><span className="stage-no">{i+1}</span><span><b>{s.label}</b><small>{s.hint}</small></span></button>)}
    </div>
    <div className="stage-work"><span className={'live-dot'+(topic?.dispatch_status==='running'||topic?.dispatch_status==='queued'?'':' off')}/><div><b>当前 Agent 工作</b><p className="fine">{agentWork}</p></div></div>
    {stagePanel}
    {!topic&&<div className="stage-panel"><p className="fine">还没有真实挖掘任务。可以新建任务，或从因子库选择已授权因子发起研究；阶段导航只用于查看，不会自动推进。</p><div className="actions"><button className="btn small primary" onClick={()=>setCreating(true)}>新建挖掘任务</button><Link className="btn small" to="/quant/factor/library">从因子库开始</Link></div></div>}
   </div>}
   {creating&&<div className="modal-backdrop" role="dialog" aria-modal="true" onClick={()=>setCreating(false)}><div className="modal" onClick={e=>e.stopPropagation()}><div className="modal-header"><div><h2>新建研究挖掘任务</h2><p className="fine">创建后冻结数据视图、区间、预算与初始因子</p></div><button className="btn small" onClick={()=>setCreating(false)}>取消</button></div><div className="modal-body">{createErr&&<p className="hint error">{createErr}</p>}<div className="form-grid">
    <label className="field"><span>挖掘任务名称</span><input value={nt.name} onChange={e=>setNt({...nt,name:e.target.value})}/></label>
    <label className="field"><span>挖掘任务类型</span><select value={nt.purpose} onChange={e=>setNt({...nt,purpose:e.target.value as 'replication'|'discovery'})}><option value="replication">复现（已有因子）</option><option value="discovery">新发现（需因子库新颖性检验）</option></select><small>复现：存量因子直接进检验。新发现：走 0.70 相关性去重门槛；当前共享 9527 未提供新颖性/ R4 接口，新发现可能在对照阶段报“不可用”，不会伪造通过。</small></label>
    <label className="field"><span>股票池</span><select value={nt.universe} onChange={e=>setNt({...nt,universe:e.target.value,benchmark:e.target.value})}><option>CSI500</option><option>CSI300</option><option>ALL_A</option></select></label>
    <label className="field"><span>起点因子（可选）</span><select value={nt.factor} onChange={e=>{const f=importedFactors.find(x=>x.factor_name===e.target.value);setNt({...nt,factor:e.target.value,library:f?.source_library||nt.library});}}><option value="">不预选（新发现由研究系统生成）</option>{importedFactors.length===0&&nt.factor&&<option value={nt.factor}>{nt.factor}</option>}{importedFactors.map(f=><option key={f.source_library+':'+f.factor_name} value={f.factor_name}>{f.factor_name} · {f.display_name||''}（{f.source_library}）</option>)}</select><small>导入资产标注“未经 V5 复核”；源码因子可后续在 F3 改写。</small></label>
    <label className="field"><span>方向</span><select value={nt.direction} onChange={e=>setNt({...nt,direction:e.target.value})}><option value="positive">正向</option><option value="negative">负向</option></select></label>
    <label className="field"><span>研发开始</span><input value={nt.development_start} onChange={e=>setNt({...nt,development_start:e.target.value})}/></label>
    <label className="field"><span>研发结束</span><input value={nt.development_end} onChange={e=>setNt({...nt,development_end:e.target.value})}/></label>
    <label className="field"><span>样本外开始</span><input value={nt.validation_start} onChange={e=>setNt({...nt,validation_start:e.target.value})}/></label>
    <label className="field"><span>样本外结束</span><input value={nt.validation_end} onChange={e=>setNt({...nt,validation_end:e.target.value})}/></label>
    <label className="field"><span>主持有期（日）</span><input type="number" value={1} readOnly disabled/><small>首期真实检验仅支持 1 日；R2 多持有期未接入，不接受 5 日等未支持值。</small></label>
    <label className="field"><span>试验预算</span><input type="number" min={1} max={1000} value={nt.max_trials} onChange={e=>setNt({...nt,max_trials:Number(e.target.value)})}/></label>
    <label className="field"><span>封存预算</span><input type="number" min={1} max={3} value={nt.max_sealed} onChange={e=>setNt({...nt,max_sealed:Number(e.target.value)})}/></label>
    <label className="field full"><span>授权数据范围</span><input readOnly value="当前发布视图；提交时锁定 view_id、release_ids、manifest 与 as_of"/><small>原型弹窗显式展示授权数据范围；实际版本在创建时写入挖掘任务。</small></label>
    <label className="field full"><span>研究假设</span><textarea value={nt.hypothesis} onChange={e=>setNt({...nt,hypothesis:e.target.value})}/></label>
    <label className="field full"><span>补充研究目标 / 说明（不改变执行门槛）</span><textarea value={nt.acceptance} onChange={e=>setNt({...nt,acceptance:e.target.value})}/><small>以下执行门槛由政策冻结，本说明不会改变门槛或权限。</small></label>
    <div className="field full"><span>实际执行门槛（只读）</span><div className="kv"><span>方向 Rank IC</span><div>≥ 0.005</div><span>最大回撤</span><div>≤ 0.50</div><span>有效观测</span><div>≥ 60</div><span>NW t</span><div>≥ t*(K)（Bonferroni，K 随试验数校正）</div><span>主持有期</span><div>1 日</div><span>股票池 / 基准</span><div>{nt.universe} / {nt.benchmark}</div><span>查重相关上限</span><div>0.70（新发现）</div></div></div>
   </div><div className="form-actions"><button className="btn primary" disabled={creatingBusy||!nt.name.trim()} onClick={()=>void createTopic(true)}>创建并启动</button><button className="btn" disabled={creatingBusy||!nt.name.trim()} onClick={()=>void createTopic(false)}>保存草稿</button><span className="fine">创建并启动会发真实研究请求；保存草稿只建任务不启动。</span></div></div></div></div>}
   {f0?.status==='stopped'&&f0.stop_reason&&!f0.stop_reason.includes('封存完成')&&!f0.stop_reason.includes('预算耗尽')&&<div className="card card-pad"><p className="hint error" role="alert"><b>研究决策已停止</b> · {f0.stop_reason}</p><p className="fine">阶段：研究决策执行；已保存的分支、试验和报告不会丢失。核对原因后可重试启动，或打开人工工作台接管。</p><div className="form-actions"><button className="btn small primary" disabled={starting||!selectedBranch} onClick={()=>void handBackF0()}>重试启动</button><Link className="btn small" to={'/quant/factor/workflow/'+(topic?.project_id||'')+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>打开人工工作台</Link></div></div>}
   {notice&&<div className="card card-pad"><p className="hint" role="status">{notice}</p></div>}
   {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
   {loading?(
    <div className="card card-pad"><p role="status">正在读取真实挖掘任务、分支与台账…</p></div>
   ):topics.length===0?(
    <div className="card card-pad">
     <h2>还没有 V5 挖掘任务</h2>
     <p className="hint">研究树只展示已登记的挖掘任务台账；没有数据时保留位置并说明，不用原型数据填充。</p>
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
