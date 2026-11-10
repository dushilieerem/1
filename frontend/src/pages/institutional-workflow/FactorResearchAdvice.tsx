import {useEffect,useRef,useState} from 'react';
import {researchFetch} from '@/lib/researchClient';
import {getQuantSession} from '@/lib/quantAuth';
import {getProject} from '@/lib/detectStore';
import {newUuidV4} from '@/lib/uuid';

type Target={run_id:string;branch_id:string;control_epoch:string;candidate_id?:string|null;label:string};
type Attempt={request_key:string;message:string;target:Target};
type Draft={text:string;open:boolean;target?:Target;attempt?:Attempt;state:'editing'|'unknown'|'rejected';message:string};
type Props={topicId:string;projectId:string;canSubmit:boolean;branches:Array<{id:string;display_label?:string;implementation_version?:number}>;candidate?:{id?:string;branch_id?:string}};
const blank=():Draft=>({text:'',open:false,state:'editing',message:''});
function load(key:string):Draft{
 try{const value=JSON.parse(sessionStorage.getItem(key)||'null');if(value&&typeof value.text==='string'&&value.text.length<=1000&&['editing','unknown','rejected'].includes(value.state))return value;}catch{}return blank();
}
function errorMessage(value:any){const message=typeof value?.error==='string'?value.error:typeof value?.detail==='string'?value.detail:'';return message&&message!=='invalid JSON'?message:'建议内容未能确认，请重新选择当前研究版本后提交。';}
function sameReceipt(receipt:any,attempt:Attempt){
 const input=receipt?.input;
 return !!receipt?.id&&receipt.request_key===attempt.request_key&&receipt.run_id===attempt.target.run_id&&input?.message===attempt.message&&input?.branch_id===attempt.target.branch_id&&input?.control_epoch===attempt.target.control_epoch&&(input?.candidate_id||null)===(attempt.target.candidate_id||null)&&['pending','adopted','not_adopted'].includes(receipt.status);
}
export function FactorResearchAdvice(props:Props){
 const session=getQuantSession();const key=['quant.research-advice.v1',session?.org.id,session?.user.id,props.topicId].join(':');
 return <AdviceEditor key={key} {...props} storageKey={key}/>;
}
function AdviceEditor({storageKey,...props}:Props&{storageKey:string}){
 const [draft,setDraft]=useState<Draft>(()=>load(storageKey));const [busy,setBusy]=useState(false);const [preview,setPreview]=useState<Target>();const [notice,setNotice]=useState('');
 const alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 function persist(next:Draft){try{sessionStorage.setItem(storageKey,JSON.stringify(next));}catch{}setDraft(next);}
 async function currentTarget():Promise<Target>{
  const project=await getProject(props.projectId);
  const response=await researchFetch('/api/inst/quant/factor-workflow/topics/'+props.topicId+'/f0-runs');const run=await response.json();
  if(!response.ok)throw Error(errorMessage(run));
  if(!project?.config.v5ActiveBranch||!project.config.v5ControlEpoch||!run?.id||!['queued','running'].includes(run.status))throw Error('本次研究已暂停或结束，不能提交新的建议。原文字已保留。');
  const branch=props.branches.find(b=>b.id===project.config.v5ActiveBranch);
  return {run_id:run.id,branch_id:project.config.v5ActiveBranch,control_epoch:project.config.v5ControlEpoch,
   candidate_id:props.candidate?.branch_id===project.config.v5ActiveBranch?props.candidate.id:null,
   label:branch?.display_label?branch.display_label+' · 第'+(branch.implementation_version||1)+'版':'当前研究版本'};
 }
 async function open(){
  if(busy)return;if(draft.attempt||draft.open||(!props.canSubmit&&draft.text)){persist({...draft,open:true});return;}
  setBusy(true);setNotice('');
  try{const target=await currentTarget();if(alive.current)persist({...draft,target,open:true,message:''});}
  catch(error){if(alive.current)persist({...draft,open:true,state:'rejected',message:error instanceof Error?error.message:String(error)});}
  finally{if(alive.current)setBusy(false);}
 }
 async function chooseCurrent(){
  if(busy||draft.attempt||!props.canSubmit)return;setBusy(true);
  try{const target=await currentTarget();if(alive.current)setPreview(target);}
  catch(error){if(alive.current)persist({...draft,state:'rejected',message:error instanceof Error?error.message:String(error)});}
  finally{if(alive.current)setBusy(false);}
 }
 async function submit(){
  if(busy)return;const confirming=!!draft.attempt;
  if(!confirming&&(!props.canSubmit||!draft.target||draft.text.trim().length<2))return;
  const attempt=draft.attempt||{request_key:newUuidV4(),message:draft.text.trim(),target:draft.target!};
  // Save the exact body/key before dispatch; a refresh cannot create a new identity.
  const frozen:Draft={...draft,text:attempt.message,open:true,attempt,state:'unknown',message:'这笔建议的保存结果尚未确认。继续确认不会重复创建。'};
  persist(frozen);setBusy(true);setNotice('');
  try{
   const {label,...target}=attempt.target;
   const response=await researchFetch('/api/inst/quant/factor-workflow/topics/'+props.topicId+'/research-advice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_key:attempt.request_key,message:attempt.message,...target})});
   let result:any={};try{result=await response.json();}catch{}if(!alive.current)return;
   if(!response.ok){
    const deterministic=result.saved===false||(response.status>=400&&response.status<500&&!confirming&&![408,429].includes(response.status));
    if(deterministic){persist({...frozen,attempt:undefined,state:'rejected',message:response.status===403&&!result.error&&!result.detail?'当前没有提交研究建议的权限，这笔建议未保存。':errorMessage(result)});return;}
    persist({...frozen,message:response.status===403||response.status===401?'当前无权确认这笔建议的保存结果。原文字已保留，请恢复访问后继续确认。':'这笔建议的保存结果尚未确认。请继续确认原提交，不会重复创建。'});return;
   }
   if(!sameReceipt(result,attempt)){persist({...frozen,message:'返回的保存记录与这笔建议尚未对应。原文字已保留，请继续确认原提交。'});return;}
   persist(blank());setPreview(undefined);
   setNotice(result.status==='pending'?'研究建议已保存，等待系统处理；尚不代表已采用。':result.status==='adopted'?'原研究建议已保存，系统已记录采用结果。':'原研究建议已保存，系统记录为未采用。'+(result.reason||''));
  }catch{if(alive.current)persist({...frozen,message:'这笔建议的保存结果尚未确认。原文字已保留，请继续确认原提交，不会重复创建。'});}
  finally{if(alive.current)setBusy(false);}
 }
 const pending=!!draft.attempt;
 return <div className="field">
  {notice&&<p className="hint" role="status">{notice}</p>}
  {!draft.open?(props.canSubmit||draft.text?<button className="btn small" disabled={busy} onClick={()=>void open()}>{props.canSubmit?'给研究建议':'查看未提交建议'}</button>:null):<>
   <label htmlFor="research-advice">给当前研究的建议</label>
   {draft.target&&<small>建议目标：{draft.target.label}</small>}
   <textarea id="research-advice" maxLength={1000} value={draft.text} readOnly={pending} disabled={busy} onChange={e=>{if(!pending&&!busy)persist({...draft,text:e.target.value});}}/>
   {draft.message&&<p className="hint error" role="status">{draft.message}</p>}
   <div className="actions">
    {pending?<button className="btn small" disabled={busy} onClick={()=>void submit()}>{busy?'正在确认…':'确认原提交'}</button>:draft.state==='rejected'?props.canSubmit&&<button className="btn small" disabled={busy} onClick={()=>void chooseCurrent()}>选择当前研究版本</button>:<button className="btn small" disabled={busy||!props.canSubmit||draft.text.trim().length<2} onClick={()=>void submit()}>{busy?'正在保存…':'提交研究建议'}</button>}
    <button className="btn small" disabled={busy} onClick={()=>{setPreview(undefined);persist({...draft,open:false});}}>关闭建议编辑</button>
   </div>
   {preview&&<div className="hint"><p>改为向 {preview.label} 提交保留的建议文字？</p><button className="btn small" disabled={busy} onClick={()=>{persist({...draft,target:preview,attempt:undefined,state:'editing',message:''});setPreview(undefined);}}>确认使用当前研究版本</button><button className="btn small" onClick={()=>setPreview(undefined)}>暂不更改</button></div>}
   <small>{pending?'确认前保留原内容和目标，不会自动转给其他研究版本。':props.canSubmit?'不改变门槛或源码；修改实现请明确暂停后接手。':'本次研究已暂停或结束，当前文字保留，可复制或明确关闭。'}</small>
  </>}
 </div>;
}
