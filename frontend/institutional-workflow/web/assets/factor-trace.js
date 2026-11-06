/* Evidence projection for the factor workbench; no model-generated progress. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.FactorTrace=factory();})(typeof window==='object'?window:this,function(){
  const active=j=>['queued','running'].includes(j.status);
  function belongs(job,stage,draft){
    if(job.module!=='factor'||job.stage!==stage)return false;
    const f=job.form||{};
    if(draft.factor_id)return f.factor_id===draft.factor_id||(job.factor_ids||[]).includes(draft.factor_id);
    return Boolean(draft.research_id&&f.research_id===draft.research_id);
  }
  function events(job){
    const out=[];
    for(const [index,s] of (job.steps||[]).entries()){
      if(s.kind==='tool'){
        out.push({...s,key:s.id||'legacy-'+index,tool:s.tool||s.text.replace(/^调用 /,''),input:s.detail,status:s.status||'unknown'});
      }else if(s.kind==='observation'){
        const name=s.tool||s.text.replace(/ 返回结果$/,'');
        const match=out.slice().reverse().find(x=>x.kind==='tool'&&!x.output&&(s.call_id?x.call_id===s.call_id:x.tool===name));
        const status=s.status||(s.detail?.error||['failed','interrupted'].includes(s.detail?.status)?'failed':s.detail?.status==='cancelled'?'cancelled':'completed');
        if(match){match.output=s.detail;match.status=status;match.finished=s.at;}
        else out.push({...s,kind:'tool',key:s.id||'legacy-'+index,tool:name,output:s.detail,status,inputRecorded:false});
      }else out.push({...s,key:s.id||'legacy-'+index,status:s.status||'recorded'});
    }
    return out.map(x=>({...x,status:active(job)?x.status:(['running','unknown'].includes(x.status)?(job.status==='cancelled'?'cancelled':'unknown'):x.status)}));
  }
  function activity(job){
    if(job.status==='cancelled')return '已停止后续调用';
    if(job.status==='interrupted')return '服务中断，原记录已保留';
    if(job.status==='failed')return '任务失败，请查看原因';
    if(job.status==='completed')return '任务已结束，请检查产物';
    if(job.status==='queued')return '等待执行';
    return ({context:'读取研究上下文',model:'正在请求模型',tool:'正在调用工具',compute:'计算服务正在运行',observation:'处理工具返回结果'})[job.activity]||'任务执行中';
  }
  return {belongs,events,activity};
});
