import {useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactElement} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {researchFetch} from '@/lib/researchClient';
import {createProject,saveProject,getProject,type DetectProject} from '@/lib/detectStore';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';
import {newUuidV4} from '@/lib/uuid';
import {getQuantSession} from '@/lib/quantAuth';
import {runTaskCreation,type TaskIdentity} from '@/lib/factorTaskIdentity';
import {deriveFactorTaskState} from '@/lib/factorTaskState';
import {clearStartKey,getOrCreateStartKey} from '@/lib/factorStartRequest';

type Topic={id:string;display_no?:number;project_id:string;project_name:string;view_id:string;primary_holding_period:number;max_trials:number;max_sealed:number;sealed_used?:number;status:string;dispatch_status?:string|null;dispatch_stop_reason?:string|null;dispatch_action?:string|null;pending_review?:number;sealed_passed?:number;sealed_running?:number;sealed_failed?:number;approved_count?:number;registered_count?:number;latest_outcome?:string|null;research_purpose?:string|null;k:number;branch_count:number;trial_count:number;development_start?:string;development_end?:string;validation_start?:string;validation_end?:string;created_at?:string;updated_at?:string};
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
const executorText=(value:string)=>value==='human'?'人工研究':value==='agent'?'研究系统':value==='service'?'计算服务':'研究执行';
const outcomeText=(t:Trial)=>t.outcome==='passed'?'通过':t.outcome==='failed'?'未达标':t.outcome==='error'?'执行错误':t.outcome;
const nwText=(t:Trial)=>{const c=t.result_summary?.gate?.checks?.find(x=>x.name==='方向 NW t');return c&&typeof c.actual==='number'?` · NW t ${c.actual.toFixed(2)} / 需 ${c.threshold.toFixed(2)}`:'';};

export function QuantFactorHomePage(){
 const [topics,setTopics]=useState<Topic[]>([]);
 const [selected,setSelected]=useState<string>();
 const [ledger,setLedger]=useState<Ledger>();
 const [project,setProject]=useState<DetectProject>();
 const [candidate,setCandidate]=useState<{snapshot?:{name?:string;plan?:{hypothesis?:string};request?:{factor_name?:string;factor_code?:string;library_name?:string}}}>();
 const selectedRef=useRef(selected);selectedRef.current=selected;
 const [updatesError,setUpdatesError]=useState('');
 const [node,setNode]=useState<string>();
 const [f0,setF0]=useState<{id:string;status:string;decision?:{candidate_status?:string;reason?:string;current_action?:string;steps?:Array<{step:number;at?:string;decision:{action:string;rationale:string};usage?:{tokens_in?:number;tokens_out?:number};result:{status?:string;candidate_status?:string;reason?:string;branch_id?:string;needed_capabilities?:string[]}}>};stop_reason?:string}>();
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[starting,setStarting]=useState(false);
 const canManage=!!getQuantSession()?.can_manage;
 const canWrite=getQuantSession()?.permissions.quant==='write';
 const [paused,setPaused]=useState(false),[controlBusy,setControlBusy]=useState(false);
 const [loading,setLoading]=useState(true);
 const [stageView,setStageView]=useState<'prepare'|'development'|'validation'|'approval'>('prepare');
 const [taskQuery,setTaskQuery]=useState(''),[taskFilter,setTaskFilter]=useState<'recent'|'all'|'ended'>('recent');
 const [pending,setPending]=useState<number|null>(null);
 const [sealedUsed,setSealedUsed]=useState<number|null>(null);
 const [authOpen,setAuthOpen]=useState(false);
 const [creating,setCreating]=useState(false),[creatingBusy,setCreatingBusy]=useState(false),[createErr,setCreateErr]=useState('');
 const [createdTask,setCreatedTask]=useState<TaskIdentity>();
 const createdRun=useRef<{topicId:string;branchId:string;id:string;status:string}|undefined>(undefined);
 const creatingLock=useRef(false);
 const [importedFactors,setImportedFactors]=useState<Array<{source_library:string;factor_name:string;display_name?:string}>>([]);
 const [nt,setNt]=useState({name:'新因子挖掘任务',universe:'CSI500',benchmark:'CSI500',development_start:'2022-01-01',development_end:'2024-12-31',validation_start:'2025-01-01',validation_end:'2025-12-31',holding:1,max_trials:'',max_sealed:1,factor:'',library:'主因子库',direction:'negative',hypothesis:'短周期因子在截面上有稳定预测力',acceptance:'方向 Rank IC ≥ 0.005，NW t ≥ t*(K)，有效观测 ≥ 60，最大回撤 ≤ 0.5',purpose:'discovery' as 'replication'|'discovery'});
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
  setLedger(undefined);setF0(undefined);setProject(undefined);setNode(undefined);setUpdatesError('');setError('');setAuthOpen(false);
  if(!selected)return;
  let alive=true,busy=false;
  const id=selected;
  async function load(){
   if(busy)return;busy=true;
   try{
    const [lr,fr,tr]=await Promise.all([
     researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(id)+'/ledger'),
     researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(id)+'/f0-runs'),
     researchFetch('/api/inst/quant/factor-workflow/topics'),
    ]);
    if(!lr.ok||!fr.ok||!tr.ok)throw Error('状态更新中断，请刷新重试；已保存的研究记录保留。');
    const [d,f,t]=await Promise.all([lr.json(),fr.json(),tr.json()]);
    if(!alive||selectedRef.current!==id)return;
    setLedger(d);setF0(f||undefined);setTopics(t.topics||[]);setUpdatesError('');
    setNode(cur=>cur&&(d.branches||[]).some((b:Branch)=>b.id===cur)?cur:(d.branches||[])[0]?.id);
   }catch(e){if(alive&&selectedRef.current===id)setUpdatesError(e instanceof Error?e.message:String(e));}
   finally{busy=false;}
  }
  void load();const timer=setInterval(()=>void load(),4000);
  const pid=topics.find(t=>t.id===id)?.project_id;
  if(pid)void getProject(pid).then(p=>{if(alive&&selectedRef.current===id)setProject(p);}).catch(()=>{});
  return()=>{alive=false;clearInterval(timer);};
 },[selected]);

 async function handBackF0(){
  if(!ledger||ledger.topic.id!==selectedRef.current||!selectedBranch||starting)return;
  setStarting(true);setError('');setNotice('正在提交研究决策…');
  try{
   const requestKey=getOrCreateStartKey(sessionStorage,ledger.topic.id,selectedBranch.id,newUuidV4);
   const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/branches/'+encodeURIComponent(selectedBranch.id)+'/f0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idempotency_key:requestKey})});
   const d=await r.json();if(selectedRef.current!==ledger.topic.id)return;if(!r.ok){setNotice('');setError(typeof d.detail==='string'?d.detail:'F0 启动失败');return;}
   clearStartKey(sessionStorage,ledger.topic.id,selectedBranch.id);
   setF0(d);
   setTopics(list=>list.map(t=>t.id===ledger.topic.id?{...t,dispatch_status:d.status,dispatch_stop_reason:''}:t));
   setNotice(d.status==='queued'?'研究决策已提交，正在排队…':d.status==='running'?'研究决策已启动，正在运行…':'研究决策已创建，状态：'+d.status);
  }catch(e){setNotice('');setError(e instanceof Error?e.message:String(e));}finally{setStarting(false);}
 }

 async function toggleGlobalPause(){
  if(!canManage||controlBusy)return;setControlBusy(true);setError('');setNotice('');
  try{const r=await researchFetch('/api/inst/quant/factor-workflow/controls/pause',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paused:!paused})});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'全局暂停操作失败');setPaused(!!d.paused);setNotice(d.paused?'全部研究已暂停：不再启动新的自动动作，在途计算保留记录。':'全部研究已恢复，可继续启动。');}
  catch(e){setError(e instanceof Error?e.message:String(e));}finally{setControlBusy(false);}
 }
 async function setTopicStatus(status:'paused'|'active'){
  if(!ledger||ledger.topic.id!==selectedRef.current)return;
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(ledger.topic.id)+'/'+(status==='paused'?'pause':'resume'),{method:'POST'});
  const d=await r.json();if(!r.ok){setError(typeof d.detail==='string'?d.detail:'挖掘任务状态更新失败');return;}
  setTopics(list=>list.map(t=>t.id===d.id?{...t,status:d.status}:t));
  setNotice(status==='active'?'挖掘任务已恢复，可启动挖掘继续研究。':'挖掘任务已暂停，不会继续调度。');
 }
 async function resumeF0(){if(!f0)return;const r=await researchFetch('/api/inst/quant/factor-workflow/f0-runs/'+f0.id+'/resume',{method:'POST'});const d=await r.json();if(!r.ok){setError(typeof d.detail==='string'?d.detail:'F0 继续失败');return;}setF0(d);}
 async function takeOver(){
  if(!ledger||ledger.topic.id!==selectedRef.current||!selectedBranch)return;
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
 async function loadTopicLedger(topicId:string){
  const r=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(topicId)+'/ledger');if(!r.ok)throw Error('读取首分支失败');return r.json();
 }
 async function startF0(topicId:string,branchId:string){
  if(createdRun.current?.topicId===topicId&&createdRun.current.branchId===branchId)return;
  const requestKey=getOrCreateStartKey(sessionStorage,topicId,branchId,newUuidV4);
  const fr=await researchFetch('/api/inst/quant/factor-workflow/topics/'+encodeURIComponent(topicId)+'/branches/'+encodeURIComponent(branchId)+'/f0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idempotency_key:requestKey})});
  const fd=await fr.json();if(!fr.ok)throw Error(typeof (fd.detail||fd.error)==='string'?(fd.detail||fd.error):'启动失败');
  if(!fd.id)throw Error('尚未收到运行标识，请重试确认启动结果。');
  const accepted=['queued','running','completed'].includes(fd.status)||fd.rounds>0||fd.decision?.steps?.length>0;
  if(!accepted){clearStartKey(sessionStorage,topicId,branchId);throw Error('任务尚未运行，请查看当前状态与诊断详情。');}
  createdRun.current={topicId,branchId,id:fd.id,status:fd.status};
  clearStartKey(sessionStorage,topicId,branchId);
 }
 async function createTopic(start=true){
  if(creatingLock.current)return;
  if(!Number.isInteger(Number(nt.max_trials))||Number(nt.max_trials)<1){setCreateErr('请明确填写本任务的试验预算。');return;}
  if(nt.purpose==='replication'&&!nt.factor){setCreateErr('复现已有因子需选择起点因子。');return;}
  creatingLock.current=true;setCreatingBusy(true);setCreateErr('');setError('');
  try{
   // projectId 由客户端先确定，创建/保存都可安全重放；响应丢失不会换项目。
   let task:TaskIdentity=createdTask||{projectId:newUuidV4()};
   setCreatedTask(task);
   if(!task.topicId){
    const p=await createProject(nt.factor,nt.hypothesis,nt.name,task.projectId);
    const plan={revision:'nt-'+Date.now(),hypothesis:nt.hypothesis,candidateExpression:'',improvementScope:'只改进实现，不改变经济假设和方向',target:'未来1个交易日收益',frequency:'daily',acceptance:nt.acceptance,developmentStart:nt.development_start,developmentEnd:nt.development_end,validationStart:nt.validation_start,validationEnd:nt.validation_end,maxTrials:Number(nt.max_trials),researchPurpose:nt.purpose,...(nt.purpose==='discovery'?{noveltyPolicy:{scope:'all_accessible' as const,maxAbsCorrelation:0.7,minDays:60,minPairs:30,minCoverage:0.8}}:{}),rules:{minSignedIc:0.005,maxDrawdown:0.5,minObservations:60,direction:nt.direction as 'positive'|'negative',icMetric:'rank_ic' as const}};
    await saveProject({...p,id:task.projectId,name:nt.name,description:nt.hypothesis,config:{...p.config,universe:nt.universe,benchmark:nt.benchmark,factorCodes:nt.factor?[nt.factor]:[],weights:nt.factor?[1]:[],powers:nt.factor?[1]:[],factorLibraries:nt.factor?{[nt.factor]:nt.library}:{},researchPlan:plan,researchContext:{direction:'因子研究',question:nt.hypothesis,background:'新建挖掘任务：'+nt.factor}}});
    const vr=await researchFetch('/api/inst/quant/factor-workflow/published-view');const v=await vr.json();if(!vr.ok)throw Error('发布视图读取失败');
    const body={view_id:v.view_id,release_id:'',release_ids:v.release_ids||{},view_manifest_sha256:v.view_manifest_sha256||'',contract_revision:v.contract_revision||'',as_of:v.as_of,development_start:nt.development_start,development_end:nt.development_end,validation_start:nt.validation_start,validation_end:nt.validation_end,primary_holding_period:Number(nt.holding),policy_version:'v5-p0',max_trials:Number(nt.max_trials),max_sealed:Number(nt.max_sealed)};
    const result=await runTaskCreation(task,start,{
     listProjectTopics:async(projectId)=>{
      const r=await researchFetch('/api/inst/quant/factor-workflow/projects/'+encodeURIComponent(projectId)+'/topics');if(!r.ok)throw Error('读取项目已有挖掘任务失败');const d=await r.json();return (d.topics||[]).map((t:{id:string;branch_id?:string|null})=>({id:t.id,branch_id:t.branch_id}));
     },
     createTopic:async(projectId)=>{
      const tr=await researchFetch('/api/inst/quant/factor-workflow/projects/'+encodeURIComponent(projectId)+'/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const td=await tr.json();if(!tr.ok)throw Error(typeof (td.detail||td.error)==='string'?(td.detail||td.error):'建挖掘任务失败');return {id:td.topic.id};
     },
     loadLedger:loadTopicLedger,
     startF0,
    });
    task=result.identity;setCreatedTask(task);
    if(result.error)throw Error(result.error);
   } else if(start){
    // 创建已成功、F0 启动失败后重试：复用同一 topic/branch 与同一幂等键。
    const retry=await runTaskCreation(task,true,{listProjectTopics:async()=>[],createTopic:async()=>({id:''}),loadLedger:loadTopicLedger,startF0});
    task=retry.identity;setCreatedTask(task);
    if(retry.error)throw Error(retry.error);
   }
   const rl=await researchFetch('/api/inst/quant/factor-workflow/topics');if(!rl.ok)throw Error('任务已保存，但列表更新失败；请重试读取，已确认的运行不会再次启动。');const d=await rl.json();setTopics(d.topics||[]);setTaskFilter('recent');setTaskQuery('');if(task.topicId)setSelected(task.topicId);
   if(!start){setNotice('草稿已保存，未启动研究。');setCreating(false);setCreatedTask(undefined);return;}
   setNotice(createdRun.current&&['stopped','completed'].includes(createdRun.current.status)?'任务运行已结束，结果已保留。':'挖掘任务已提交，等待排队/运行状态。');setCreating(false);setCreatedTask(undefined);
  }catch(e){setCreateErr(e instanceof Error?e.message:String(e));}
  finally{creatingLock.current=false;setCreatingBusy(false);}
 }
 const topic=topics.find(t=>t.id===selected);
 const taskFacts=topic?{...topic,dispatch_action:f0?.decision?.current_action||topic.dispatch_action}:undefined;
 const taskState=taskFacts?deriveFactorTaskState(taskFacts):undefined;
 useEffect(()=>{if(taskState)setStageView(taskState.currentStage);},[topic?.id]); // 仅在换任务时定位真实当前环节；实时更新和人工查看不抢面板
 const stageDefs=taskState?.stages||[];
 const taskStateOf=(t:Topic)=>deriveFactorTaskState(t);
 const filteredTopics=useMemo(()=>{
  const q=taskQuery.trim().toLowerCase();
  return [...topics].filter(t=>{
   const s=taskStateOf(t);
   if(taskFilter==='recent'&&['ended','admitted'].includes(s.key)&&t.id!==selected)return false;
   if(taskFilter==='ended'&&!['ended','admitted'].includes(s.key))return false;
   return !q||(t.project_name||'').toLowerCase().includes(q);
  }).sort((a,b)=>{
   const rank=(t:Topic)=>{const k=taskStateOf(t).key;return k==='review'?0:k==='running'||k==='preparing'||k==='validating'?1:k==='error'||k==='waiting'?2:3;};
   return rank(a)-rank(b)||String(b.updated_at||b.created_at||'').localeCompare(String(a.updated_at||a.created_at||''));
  });
 },[topics,taskQuery,taskFilter,selected]);
 useEffect(()=>{if(!filteredTopics.length)return;if(!filteredTopics.some(t=>t.id===selected))setSelected(filteredTopics[0].id);},[filteredTopics.map(t=>t.id).join(','),selected]);
 const workLabels:Record<string,string>={run_test:'正在检验因子实现',revise:'正在修订假设与实现',pivot:'正在探索新的研究分支',request_seal:'正在整理并执行独立验证'};
 const agentWork=workLabels[f0?.decision?.current_action||'']||taskState?.label||'暂无运行中的任务';
 const selectedBranch=(ledger?.branches||[]).find(b=>b.id===node);
 const latestDevelopmentTrial=[...(ledger?.trials||[])].filter(t=>!String(t.kind).includes('sealed')).sort((a,b)=>b.trial_no-a.trial_no)[0];
 const currentBranchId=f0?.decision?.steps?.at(-1)?.result.branch_id||latestDevelopmentTrial?.branch_id;
 const currentBranch=(ledger?.branches||[]).find(b=>b.id===currentBranchId)||(ledger?.branches||[]).at(-1);
 const currentVersion=currentBranch?.implementation_version||1;
 const feed=useMemo(()=>{
  const actionLabels:Record<string,string>={run_test:'已执行研发检验',revise:'已修订研究版本',pivot:'已探索研究分支',request_seal:'已处理独立验证',stop:'研究已停止'};
  return [
   ...(ledger?.trials||[]).map(t=>({key:'trial-'+t.trial_no,at:t.created_at||'',label:outcomeText(t)+' · '+executorText(t.executor)+(t.report_id?' · 有报告':'')})),
   ...(f0?.decision?.steps||[]).filter(s=>s.at).map(s=>({key:'action-'+s.step,at:s.at||'',label:s.result.status==='stopped'?'研究操作已停止':s.result.status==='skipped'?'研究操作已跳过':actionLabels[s.decision.action]||'已保存研究操作'})),
  ].sort((a,b)=>b.at.localeCompare(a.at)).slice(0,5);
 },[ledger,f0]);
 const candidateReport=[...(ledger&&ledger.topic.id===selected?ledger.trials:[])].reverse().find(t=>t.branch_id===currentBranch?.id&&/^qf_.+_development$/.test(t.report_id||''))?.report_id;
 useEffect(()=>{
  setCandidate(undefined);const id=selected;
  if(!candidateReport)return;
  let alive=true;const cid=candidateReport.slice(3,-12);
  void researchFetch('/api/factor-workflow/candidates/'+encodeURIComponent(cid)).then(r=>r.ok?r.json():null).then(c=>{if(alive&&selectedRef.current===id)setCandidate(c||undefined);}).catch(()=>{});
  return()=>{alive=false;};
 },[candidateReport,selected,currentBranch?.id]);
 const totalTrials=topics.reduce((n,t)=>n+t.trial_count,0);
 const capabilityGaps=useMemo(()=>Array.from(new Set((f0?.decision?.steps||[]).flatMap(s=>s.result?.needed_capabilities||[]))),[f0]);

 function branchNode(b:Branch,depth=0):ReactElement{
  const trials=trialsByBranch.get(b.id)||[];
  return (
   <div key={b.id} className="branch-wrap">
    <div className={'branch'+(b.source==='manual'?' human':'')+(node===b.id?' sel':'')} data-bid={b.id} data-parent={b.parent_id||''} onClick={()=>setNode(b.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setNode(b.id);}}} role="button" tabIndex={0}>
     <div className="bh">
      <span className="hid">{b.display_label||'H?'}</span>
      <span className="bt" title={b.display_title}>{b.display_title? (b.display_title.length>70?b.display_title.slice(0,70)+'…':b.display_title) : ('假设 v'+b.hypothesis_version+'（未命名）')}</span>
      <span className={'badge '+(b.display_status==='研发通过'||b.display_status==='封存通过，待提交'?'live':b.display_status?.includes('失败')||b.display_status==='未达标'?'gray':'gray')}>{b.display_status||b.status}</span>
      <span className="by">{b.source==='manual'&&!b.parent_id?'初始分支':b.source_label||(b.source==='manual'?'人工':'Agent')} · v{b.hypothesis_version}/v{b.implementation_version} · {trials.length} 次</span>
     </div>
     {trials.length>0&&<div className="steps">{trials.map(t=>{const checks=t.result_summary?.gate?.checks||[];const ic=checks.find(c=>c.name.includes('Rank IC')||c.name.includes('方向IC'));const nw=checks.find(c=>c.name.includes('NW t'));const label=`E${t.trial_no}${ic?.actual!=null?` · IC ${Number(ic.actual).toFixed(3)}`:''}${nw?.actual!=null?` · t ${Number(nw.actual).toFixed(2)} / ${Number(nw.threshold).toFixed(2)}`:` · ${outcomeText(t)}`}${t.rerun_of?' · rerun':''}${t.outcome==='passed'?' ✓':t.outcome==='failed'?' ✗':''}`;const title=checks.map(c=>`${c.name}: ${c.actual==null?'—':Number(c.actual).toFixed(3)} / ${String(c.threshold)}`).join(' · ');return t.report_id?<Link key={t.trial_no} className={'chip '+(t.outcome==='passed'?'ok':t.outcome==='failed'?'fail':'warn')} title={title} to={'/quant/factor/report/'+t.report_id}>{label}</Link>:<span key={t.trial_no} className={'chip '+(t.outcome==='passed'?'ok':t.outcome==='failed'?'fail':'warn')} title={title}>{label}</span>;})}</div>}
    </div>
    {(children.get(b.id)||[]).length>0&&<div className="children">{(children.get(b.id)||[]).map(c=>branchNode(c,depth+1))}</div>}
   </div>
  );
 }

 const topicCards=filteredTopics.map(t=>{const s=taskStateOf(t);const stageName=s.stages.find(x=>x.id===s.currentStage)?.label||'';return (
  <button key={t.id} className={'ff-task'+(selected===t.id?' selected':'')} onClick={()=>setSelected(t.id)} aria-current={selected===t.id?'true':undefined}>
   <div className="ff-task-row"><span className={'badge '+s.tone}>{s.label}</span><small>日频</small></div>
   <strong>{t.project_name||'未命名挖掘任务'}</strong>
   <small>{stageName} · 已检验 {t.trial_count} 次 / 上限 {t.max_trials} 次</small>
   {t.updated_at||t.created_at?<time>{new Date(t.updated_at||t.created_at||'').toLocaleString()}</time>:null}
  </button>
 );});

 const tree=(ledger?.branches||[]).length>0?<div className="tree" ref={treeRef}>{treeLines.length>0&&<svg className="tree-lines" aria-hidden="true">{treeLines.map((d,i)=><path key={i} d={d} fill="none" stroke="#cbb8dc" strokeWidth="1" strokeDasharray="4 4"/>)}</svg>}{(children.get('root')||[]).map(b=>branchNode(b))}</div>:<div className="empty"><b>挖掘任务还没有分支</b>真实空态：无分支时不显示模拟节点。</div>;

 const trials=(selectedBranch?trialsByBranch.get(selectedBranch.id):[])||[];
 const detail=selectedBranch?(
  <div className="card">
   <div className="card-head">
    <div><div className="row-flex"><span className="hid">{selectedBranch.display_label||'H?'}</span><h2>{selectedBranch.display_title||('假设 v'+selectedBranch.hypothesis_version+'（未命名）')}</h2><span className="badge">{selectedBranch.display_status||selectedBranch.status}</span></div>
     <p className="fine">{selectedBranch.source_label||(selectedBranch.source==='manual'?'人工':'Agent')} · 假设 v{selectedBranch.hypothesis_version} / 实现 v{selectedBranch.implementation_version} · 内部 ID {selectedBranch.id.slice(0,8)}</p></div>
    <div className="actions"><button className="btn small primary" disabled={!canWrite} onClick={()=>void takeOver()}>从此分支接手</button><button className="btn small" onClick={()=>void handBackF0()} disabled={f0&&['queued','running'].includes(f0.status)}>交回研究系统</button>{f0&&f0.stop_reason?.includes('中断')&&<button className="btn small" onClick={()=>void resumeF0()}>继续研究决策</button>}<Link className="btn small" to={'/quant/factor/workflow/'+(topic?.project_id||'')+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>打开人工工作台</Link>{f0&&<span className="fine">研究决策：{f0.status}{f0.decision?.candidate_status?' · '+f0.decision.candidate_status:''}{f0.stop_reason?' · '+f0.stop_reason:''}</span>}</div>
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
  <aside className="ff-live" aria-label="Agent 工作状态">
   <div><div className="eyebrow">当前工作</div><h3>{taskState?.stages.find(s=>s.id===taskState.currentStage)?.role||'暂无运行中的任务'}</h3><div className="ff-now">{agentWork}</div></div>
   <div><div className="eyebrow">最近事件</div>{feed.length===0?<p className="subtle">尚无事件记录。</p>:<ol>{feed.map(t=><li key={t.key}><time>{t.at?new Date(t.at).toLocaleString():'时间未记录'}</time>{t.label}</li>)}</ol>}</div>
   <div><hr className="ff-divider"/><div className="eyebrow">需要你处理</div><p>{taskState?.needsYou||'新建任务后在这里显示。'}</p></div>
   <div className="actions" style={{marginTop:12}}>{(taskState?.key==='review'||taskState?.key==='approved_unregistered')&&<Link className="btn small primary" to="/quant/reviews/factors">查看待审批</Link>}</div>
  </aside>
 );

 const canStart=['draft','error','waiting'].includes(taskState?.key||'');
 const stageTitle=stageDefs.find(s=>s.id===stageView);
 const latestTrials=[...(ledger?.trials||[])].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||''));
 const sealedTrials=latestTrials.filter(t=>String(t.kind||'').includes('sealed'));
 const stageContent=!topic?null:(
  <article className="card ff-stage-card">
   <div className="card-head"><div><h2>{stageTitle?.label}</h2><p>{stageTitle?.role} · {stageTitle?.status==='done'?'已完成':stageTitle?.status==='current'?'当前环节':'尚未开始'}</p></div><span className="badge">{purposeText(topic.research_purpose)}</span></div>
   <div className="card-body">
    {stageView==='prepare'&&<>
     <dl className="ff-kv"><dt>研究目标</dt><dd>{project?.description||ledger?.branches?.[0]?.hypothesis_text||(ledger?.branches?.[0]?.display_title&&ledger.branches[0].display_title!=='初始假设'?ledger.branches[0].display_title:'尚无已保存假设；启动后由研究准备 Agent 生成。')}</dd><dt>任务类型</dt><dd>{purposeText(topic.research_purpose)}</dd><dt>数据范围</dt><dd>日频 · {topic.development_start||'—'} 至 {topic.validation_end||'—'} · 创建时锁定发布视图</dd><dt>试验预算</dt><dd>上限 {topic.max_trials} 次，已检验 {topic.trial_count} 次</dd><dt>用途</dt><dd>因子研究，不涉及实盘交易</dd></dl>
     <div className="actions" style={{marginTop:12}}>{topic.status==='active'&&canStart&&<button className="btn small primary" disabled={!canWrite||starting||!selectedBranch} onClick={()=>void handBackF0()}>{starting?'正在提交…':taskState?.key==='draft'?'启动挖掘':'重试启动'}</button>}{topic.status==='paused'?<button className="btn small" disabled={!canWrite} onClick={()=>void setTopicStatus('active')}>恢复任务</button>:topic.status==='active'&&['preparing','running','validating'].includes(taskState?.key||'')?<button className="btn small" disabled={!canWrite} onClick={()=>void setTopicStatus('paused')}>暂停任务</button>:null}</div>
    </>}
    {stageView==='development'&&<>
      <div className="ff-label">当前候选 · 第 {currentVersion} 版</div>
      <h3>{currentBranch?.display_title||candidate?.snapshot?.request?.factor_name||'尚无已保存候选'}</h3>
      <p className="ff-copy">{candidate?.snapshot?.plan?.hypothesis||currentBranch?.hypothesis_text||'尚无该版本已保存的假设。'}</p>
      {candidate?.snapshot?.request?.factor_code?<pre className="ff-code">{candidate.snapshot.request.factor_code}</pre>:candidate?.snapshot?.request?.library_name?<p className="ff-copy">已保存定义：{candidate.snapshot.request.factor_name}（{candidate.snapshot.request.library_name}）。完整定义与固定证据见试验报告。</p>:<p className="subtle">尚无该候选的已保存实现；有检验报告时可查看其固定版本。</p>}
      <hr className="ff-divider"/><h3>研发检验</h3>

     <div className="ff-now">已检验 {topic.trial_count} 次 / 上限 {topic.max_trials} 次 · 当前第 {currentVersion} 版</div>
     <dl className="ff-kv" style={{marginTop:10}}><dt>最新结果</dt><dd>{latestDevelopmentTrial?outcomeText(latestDevelopmentTrial)+(latestDevelopmentTrial.report_id?' · 有报告':''):'尚无研发检验'}</dd><dt>假设分支</dt><dd>{topic.branch_count} 个</dd><dt>当前状态</dt><dd>{taskState?.label}</dd></dl>
     <div className="actions" style={{marginTop:12}}><Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'}>人工研究</Link>{latestDevelopmentTrial?.report_id&&<Link className="btn small" to={'/quant/factor/report/'+latestDevelopmentTrial.report_id}>查看最新报告</Link>}<button className="btn small" onClick={()=>setStageView('validation')}>查看独立验证</button></div>
    </>}
    {stageView==='validation'&&<>
     <dl className="ff-kv"><dt>封存已用</dt><dd>{topic.sealed_used||0} / {topic.max_sealed}</dd><dt>验证通过</dt><dd>{topic.sealed_passed||0} 次</dd><dt>验证中</dt><dd>{topic.sealed_running||0} 次</dd><dt>验证失败</dt><dd>{topic.sealed_failed||0} 次</dd><dt>待审批</dt><dd>{topic.pending_review||0} 项</dd></dl>
     {sealedTrials.length>0?<div className="trial-list" style={{marginTop:10}}>{sealedTrials.slice(0,5).map(t=><div className="trial-row" key={t.trial_no}><span className="tk">验证</span><div className="tb"><b>{outcomeText(t)}</b><small>{new Date(t.created_at||'').toLocaleString()}</small></div>{t.report_id?<Link className="btn small" to={'/quant/factor/report/'+t.report_id}>报告</Link>:null}</div>)}</div>:<p className="subtle">尚无封存验证记录。</p>}
     <div className="actions" style={{marginTop:12}}>{(topic.pending_review||0)>0?<Link className="btn small primary" to="/quant/reviews/factors">进入待审批</Link>:<Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'}>人工研究</Link>}</div>
    </>}
    {stageView==='approval'&&<>
     <dl className="ff-kv"><dt>本任务待审批</dt><dd>{topic.pending_review||0} 项</dd><dt>已批准待登记</dt><dd>{topic.approved_count||0} 项</dd><dt>已入库</dt><dd>{topic.registered_count?topic.registered_count+' 项':'尚未完成入库'}</dd></dl>
     <p className="fine" style={{marginTop:10}}>{(topic.pending_review||0)>0?'审批由独立复核人完成，研究员只能查看证据。':(topic.approved_count||0)>0?'审批已通过，资产登记尚未完成。':'当前任务还没有进入审批的候选。'}</p>
     <div className="actions" style={{marginTop:12}}><Link className="btn small" to="/quant/reviews/factors">查看待审批</Link><Link className="btn small" to="/quant/factor/library">打开因子库</Link></div>
    </>}
   </div>
  </article>
 );
 const main=topic?(
  <section className="ff-detail">
   <header className="ff-detail-head">
    <div><span className={'badge '+taskState?.tone}>{taskState?.label}</span><h2>{topic.project_name||'未命名挖掘任务'}</h2><p>{purposeText(topic.research_purpose)} · 日频 · 已检验 {topic.trial_count} 次 / 上限 {topic.max_trials} 次 · 当前第 {currentVersion} 版</p></div>
    <div className="actions"><button className="btn small" onClick={()=>setAuthOpen(true)}>范围与预算</button>{topic.status==='active'&&canStart?<button className="btn small primary" disabled={!canWrite||starting||!selectedBranch} onClick={()=>void handBackF0()}>{starting?'正在提交…':taskState?.key==='draft'?'启动挖掘':'重试启动'}</button>:null}<Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'+(selectedBranch?'?branch='+selectedBranch.id:'')}>人工研究</Link></div>
   </header>
   {updatesError&&<p className="hint error" role="alert">{updatesError}</p>}<nav className="ff-steps" aria-label="任务业务环节">
    {stageDefs.map((s,i)=><button key={s.id} className={'ff-step '+(stageView===s.id?'selected ':'')+(s.status==='current'?'current ':'')+(s.status==='done'?'done':'')} onClick={()=>setStageView(s.id)} aria-current={s.status==='current'?'step':undefined} aria-label={'查看'+s.label}><span className="ff-num">{s.status==='done'?'✓':i+1}</span><span><b>{s.label}</b><small>{s.role}</small><em>{s.status==='done'?'已完成':s.status==='current'?'当前环节':'尚未开始'}</em></span></button>)}
   </nav>
   {taskState?.key==='error'&&<div className="ff-error" role="alert"><b>本次运行未完成</b><p>{taskState.needsYou}</p><div className="actions"><button className="btn small" disabled={!canWrite||starting||!selectedBranch} onClick={()=>void handBackF0()}>重试启动</button><Link className="btn small" to={'/quant/factor/workflow/'+topic.project_id+'/F4'}>人工接手</Link></div><details><summary>诊断详情</summary><p>{topic.dispatch_stop_reason||'服务未返回可读原因。'}</p>{f0?.stop_reason&&<p>{f0.stop_reason}</p>}</details></div>}
   <div className="ff-stage-grid"><div>{ledger?.topic.id===topic.id?stageContent:<div className="card card-pad" role="status">正在读取任务成果…</div>}</div>{side}</div>
   <details className="history-details" onToggle={e=>{if((e.currentTarget as HTMLDetailsElement).open)window.dispatchEvent(new Event('resize'));}}>
    <summary><span><b>研究历程与全部试验</b><small> {topic.branch_count} 个分支 · {topic.trial_count} 次试验</small></span><span className="subtle">展开查看</span></summary>
    <div className="ledger" style={{marginBottom:10}}><span>全部试验 <b>{ledger?.trials.length??0}</b> 条</span><span>计入 K <b className={(ledger?.k??topic.k)>topic.max_trials?"bad-t":undefined}>{ledger?.k??topic.k}</b> / {topic.max_trials}</span><span>当前 t*(K) <b>{ledger?.threshold==null?'待接入':ledger.threshold.toFixed(3)}</b></span>{ledger?.dispatch&&<span>调度 <b>{ledger.dispatch.status}</b>{ledger.dispatch.stop_reason?' · '+ledger.dispatch.stop_reason:''}</span>}</div>
    {capabilityGaps.length>0&&<p className="hint" role="status">所需能力暂不支持：{capabilityGaps.join('、')}。研究准备已改用可实现的降级修订继续。</p>}
    {tree}
    {detail}
    <h3 style={{margin:'16px 0 6px'}}>全部试验</h3>
    {latestTrials.length===0?<p className="subtle">尚无试验记录。</p>:<div className="table-wrap"><table className="table"><thead><tr><th>试验</th><th>分支</th><th>结果</th><th>时间</th><th>报告</th></tr></thead><tbody>{latestTrials.map(t=><tr key={t.trial_no}><td>{t.trial_no}</td><td>{t.branch_id.slice(0,8)}</td><td>{outcomeText(t)} · {t.kind}</td><td>{new Date(t.created_at||'').toLocaleString()}</td><td>{t.report_id?<Link to={'/quant/factor/report/'+t.report_id}>查看</Link>:'—'}</td></tr>)}</tbody></table></div>}
   </details>
  </section>
 ):null;

 return (
  <>
   <WorkspaceHeading eyebrow="FACTOR RESEARCH" title="因子工厂" description="挖掘、验证和积累可复用的因子。">
    <Link className="btn" to="/quant/factor/manual">人工研究</Link>
    <button className="btn primary" disabled={!canWrite} onClick={()=>{setCreatedTask(undefined);createdRun.current=undefined;setCreateErr('');setCreating(true);}}>{creating?'收起新建':'＋ 启动挖掘'}</button>
   </WorkspaceHeading>
   <FactorModuleTabs active="home"/>
   <div className="sys compact">
    <div className="sys-state"><span className="ico">⇅</span><div><b><span className={"live-dot"+(topics.some(t=>t.dispatch_status==='running'||t.dispatch_status==='queued')?'':' off')}/> {topics.some(t=>t.dispatch_status==='running'||t.dispatch_status==='queued')?'因子研究系统运行中':topics.some(t=>(t.pending_review||0)>0)?'因子研究系统空闲 · 待审批':topics.some(t=>t.dispatch_status==='stopped')?'因子研究系统空闲 · 待处理':'因子研究系统空闲'}</b><small className="fine">{loading?'读取中':`挖掘任务 ${topics.length} 个 · 运行中 ${topics.filter(t=>t.dispatch_status==='running'||t.dispatch_status==='queued').length} · 待审批 ${topics.filter(t=>(t.pending_review||0)>0).length}`}</small></div></div>
    <div className="actions"><button className="btn small" disabled={!canManage||!canWrite||controlBusy} onClick={()=>void toggleGlobalPause()} title={canManage?(paused?"恢复全部自动研究":"全局暂停，不启动新自动动作"):"需要研究负责人权限"}>{paused?"恢复全部":"全局暂停"}</button></div>
   </div>
   {creating&&<div className="modal-backdrop" role="dialog" aria-label="新建挖掘任务" aria-modal="true" onKeyDown={e=>{if(e.key==='Escape'&&!creatingBusy)setCreating(false);}} onClick={()=>{if(!creatingBusy)setCreating(false);}}><div className="modal" onClick={e=>e.stopPropagation()}><div className="modal-header"><div><h2>新建挖掘任务</h2><p className="fine">查看范围与预算后提交，草稿不会启动计算</p></div><button className="btn small" onClick={()=>{if(!creatingBusy)setCreating(false);}}>取消</button></div><div className="modal-body">{createErr&&<p className="hint error">{createErr}</p>}<fieldset className="form-grid ff-create-fields" disabled={creatingBusy||!!createdTask}>
    <label className="field"><span>挖掘任务名称</span><input value={nt.name} onChange={e=>setNt({...nt,name:e.target.value})}/></label>
    <label className="field"><span>挖掘任务类型</span><select value={nt.purpose} onChange={e=>setNt({...nt,purpose:e.target.value as 'replication'|'discovery'})}><option value="replication">复现（已有因子）</option><option value="discovery">新发现（需因子库新颖性检验）</option></select><small>新发现需通过真实重复性检查。计算服务不可用时任务会等待，不会显示验证通过。</small></label>
    <label className="field"><span>股票池</span><select value={nt.universe} onChange={e=>setNt({...nt,universe:e.target.value,benchmark:e.target.value})}><option>CSI500</option><option>CSI300</option><option>ALL_A</option></select></label>
    <label className="field"><span>起点因子（可选）</span><select value={nt.factor} onChange={e=>{const f=importedFactors.find(x=>x.factor_name===e.target.value);setNt({...nt,factor:e.target.value,library:f?.source_library||nt.library});}}><option value="">不预选（新发现由研究系统生成）</option>{importedFactors.length===0&&nt.factor&&<option value={nt.factor}>{nt.factor}</option>}{importedFactors.map(f=><option key={f.source_library+':'+f.factor_name} value={f.factor_name}>{f.factor_name} · {f.display_name||''}（{f.source_library}）</option>)}</select><small>参考因子不代表新发现成果；复现任务必须选择已有因子。</small></label>
    <label className="field"><span>方向</span><select value={nt.direction} onChange={e=>setNt({...nt,direction:e.target.value})}><option value="positive">正向</option><option value="negative">负向</option></select></label>
    <label className="field"><span>研发开始</span><input value={nt.development_start} onChange={e=>setNt({...nt,development_start:e.target.value})}/></label>
    <label className="field"><span>研发结束</span><input value={nt.development_end} onChange={e=>setNt({...nt,development_end:e.target.value})}/></label>
    <label className="field"><span>样本外开始</span><input value={nt.validation_start} onChange={e=>setNt({...nt,validation_start:e.target.value})}/></label>
    <label className="field"><span>样本外结束</span><input value={nt.validation_end} onChange={e=>setNt({...nt,validation_end:e.target.value})}/></label>
    <label className="field"><span>主持有期（日）</span><input type="number" value={1} readOnly disabled/><small>当前检验支持未来 1 个交易日收益。</small></label>
    <label className="field"><span>试验预算</span><input type="number" min={1} max={1000} value={nt.max_trials} onChange={e=>setNt({...nt,max_trials:e.target.value})}/></label>
    <label className="field"><span>封存预算</span><input type="number" min={1} max={3} value={nt.max_sealed} onChange={e=>setNt({...nt,max_sealed:Number(e.target.value)})}/></label>
    <label className="field full"><span>授权数据范围</span><input readOnly value="提交时使用当前已发布数据并固定其版本"/><small>创建后可在任务头部“范围与预算”查看实际保存结果。</small></label>
    <label className="field full"><span>研究假设</span><textarea value={nt.hypothesis} onChange={e=>setNt({...nt,hypothesis:e.target.value})}/></label>
    <label className="field full"><span>补充研究目标 / 说明（不改变执行门槛）</span><textarea value={nt.acceptance} onChange={e=>setNt({...nt,acceptance:e.target.value})}/><small>以下执行门槛由政策冻结，本说明不会改变门槛或权限。</small></label>
    <div className="field full"><span>实际执行门槛（只读）</span><div className="kv"><span>方向 Rank IC</span><div>≥ 0.005</div><span>最大回撤</span><div>≤ 0.50</div><span>有效观测</span><div>≥ 60</div><span>NW t</span><div>≥ t*(K)（Bonferroni，K 随试验数校正）</div><span>主持有期</span><div>1 日</div><span>股票池 / 基准</span><div>{nt.universe} / {nt.benchmark}</div><span>查重相关上限</span><div>0.70（新发现）</div></div></div>
   </fieldset>{createdTask&&<p className="fine">本次提交的任务身份已保留；重试会继续原任务。需要修改配置时请另建任务。</p>}<div className="form-actions"><button className="btn primary" disabled={creatingBusy||!nt.name.trim()} onClick={()=>void createTopic(true)}>{creatingBusy?'正在提交…':createdTask?.topicId?'重试启动':'创建并启动'}</button><button className="btn" disabled={creatingBusy||!nt.name.trim()} onClick={()=>void createTopic(false)}>保存草稿</button><span className="fine">创建并启动会发真实研究请求；保存草稿只建任务不启动。</span></div></div></div></div>}
   {authOpen&&topic&&<div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="范围与预算" onClick={()=>setAuthOpen(false)} onKeyDown={e=>{if(e.key==='Escape')setAuthOpen(false);}}><div className="modal" onClick={e=>e.stopPropagation()}><div className="modal-header"><h2>范围与预算</h2><button autoFocus className="btn small" onClick={()=>setAuthOpen(false)}>关闭</button></div><div className="modal-body"><h3>{topic.project_name}</h3><dl className="ff-kv"><dt>研发区间</dt><dd>{topic.development_start||'未记录'} 至 {topic.development_end||'未记录'}</dd><dt>独立验证区间</dt><dd>{topic.validation_start||'未记录'} 至 {topic.validation_end||'未记录'}</dd><dt>主持有期</dt><dd>{topic.primary_holding_period} 个交易日</dd><dt>试验预算</dt><dd>已计入 {topic.k} 次 / 上限 {topic.max_trials} 次</dd><dt>封存预算</dt><dd>已用 {topic.sealed_used||0} 次 / 上限 {topic.max_sealed} 次</dd><dt>数据版本</dt><dd>{topic.view_id||'未记录'}</dd><dt>股票池</dt><dd>当前任务未返回冻结的股票池授权记录；请以固定试验报告中的实际范围为准。</dd><dt>用途</dt><dd>研究使用，不授予实盘权限。</dd></dl><p className="hint">这里查看本任务已保存的范围与限额。扩大范围或预算需要负责人授权，不能在此直接修改。</p></div></div></div>}
   {notice&&<div className="card card-pad"><p className="hint" role="status">{notice}</p></div>}
   {error&&<div className="card card-pad"><p className="hint error" role="alert">{error}</p></div>}
   {loading?(
    <div className="card card-pad"><p role="status">正在读取挖掘任务…</p></div>
   ):topics.length===0?(
    <div className="card card-pad">
     <h2>还没有挖掘任务</h2>
     <p className="hint">没有真实任务时保留空态，不用原型数据填充。可以启动挖掘，或从因子库选择已授权因子发起研究。</p>
     <div className="actions" style={{marginTop:12}}><button className="btn primary" disabled={!canWrite} onClick={()=>{setCreatedTask(undefined);createdRun.current=undefined;setCreateErr('');setCreating(true);}}>启动挖掘</button><Link className="btn" to="/quant/factor/library">从因子库开始</Link></div>
    </div>
   ):(
    <div className="ff-columns">
     <aside className="ff-task-list" aria-label="挖掘任务列表">
      <h2>我的挖掘任务</h2>
      <input className="ff-task-filter" value={taskQuery} onChange={e=>setTaskQuery(e.target.value)} aria-label="搜索挖掘任务" placeholder="搜索任务"/>
      <select className="ff-task-filter" value={taskFilter} onChange={e=>setTaskFilter(e.target.value as 'recent'|'all'|'ended')} aria-label="任务状态"><option value="recent">运行与待处理</option><option value="all">全部任务</option><option value="ended">已结束</option></select>
      <div className="ff-task-items">{topicCards.length?topicCards:<div className="empty">没有匹配的任务</div>}</div>
     </aside>
     {main}
    </div>
   )}
  </>
 );
}
