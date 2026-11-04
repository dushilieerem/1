import {useState} from 'react';
export const reviewLabels:Record<string,string>={research_supported:'研究依据基本充分',needs_revision:'需要补充研究',rejected:'不支持研究结论'};
export function FactorReviewRequest({review,busy,onSubmit}:{review?:{status:string;question:string;decision?:string;note?:string};busy:boolean;onSubmit:(note:string)=>void}){
 const [question,setQuestion]=useState('');
 return <section className="rounded-lg border p-4"><h3 className="text-sm font-semibold">独立研究复核</h3><p className="mt-2 text-xs text-slate-500">按需提交固定版本和证据，由另一位复核员反馈。失败实验也可提交方法复盘；不会自动入队或授予正式准入。</p>{review?<div className="mt-3 text-sm"><p>{review.status==='requested'?'等待独立复核':reviewLabels[review.decision||'']}</p><p className="mt-2">复核问题：{review.question}</p>{review.note&&<p className="mt-2 whitespace-pre-wrap">复核意见：{review.note}</p>}</div>:<><label className="mt-3 block text-sm">需要复核的问题<textarea rows={2} maxLength={3000} className="mt-2 w-full rounded border p-2" value={question} onChange={e=>setQuestion(e.target.value)}/></label><button disabled={busy||!question.trim()} className="mt-2 rounded-lg border px-3 py-2 text-sm disabled:opacity-40" onClick={()=>onSubmit(question)}>提交研究复核</button></>}</section>;
}
