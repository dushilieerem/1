(function(){
'use strict';
const C=window.ProtoConfig,M=window.ProtoModel,B=JSON.parse(document.getElementById('blueprint').textContent),V=window.createProtoViews(C,M,B);
const root=document.getElementById('app'),modal=document.getElementById('modal'),timers=new Map();
let state,storageFailed=false;
const ui={page:'overview',sub:'',agentTab:'task',methodTab:'responsibility',reviewTab:'pending',reviewId:'',agentId:'F-A1',roleFilter:'',scenario:'normal',instructions:{},errors:{},jobSelected:{},assetSearch:''};
function initial(){return M.makeState(C,B);}
try{const raw=JSON.parse(localStorage.getItem(C.storageKey)||'null');if(raw?.schema===3&&Array.isArray(raw.tasks)&&raw.tasks.every(t=>t.values&&t.outputs&&Array.isArray(t.jobs))&&raw.assets&&Array.isArray(raw.reviews)&&raw.methods&&raw.plans&&raw.selected)state=M.recover(raw);else state=initial();}catch{state=initial();}
function persist(){try{localStorage.setItem(C.storageKey,JSON.stringify(state));}catch{if(!storageFailed)toast('浏览器存储不可用：本页仍可操作，关闭前请导出场景记录。');storageFailed=true;}}
function toast(text){const target=document.getElementById('toast');target.textContent=text;target.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>target.classList.remove('show'),4500);}
function route(){const parts=location.hash.slice(1).split('/');ui.page=parts[0]||'overview';ui.sub=parts[1]||'';const module=V.mod(ui.page);if(module&&!['library','experiments'].includes(ui.sub)){const valid=module.stages.some(s=>s.id===ui.sub);if(!valid)ui.sub=M.selected(state,module.id).current;}if(ui.page==='agents'&&B.roles[ui.sub])ui.agentId=ui.sub;}
function current(){const module=V.mod(ui.page);if(!module)return null;const task=M.selected(state,module.id),stage=V.stage(ui.sub)||module.stages[0];return {module,task,stage};}
function render(keep=false){const scroll=window.scrollY;root.innerHTML=V.render(state,ui);if(location.protocol==='file:')root.querySelectorAll('[data-live-link]').forEach(a=>a.href='http://127.0.0.1:18796/#home');if(keep)window.scrollTo({top:scroll,behavior:'instant'});}
function navigate(path){modal.close();document.body.classList.remove('menu-open');const hash='#'+path;if(location.hash===hash){route();render();window.scrollTo({top:0,behavior:'instant'});}else location.hash=path;}
function showDialog(title,body,wide=false){modal.classList.toggle('wide',wide);modal.innerHTML='<div class="dialog-head"><h2>'+V.e(title)+'</h2><button class="close" data-action="close-dialog" aria-label="关闭弹窗">×</button></div><div class="dialog-body">'+body+'</div>';modal.showModal();}
function refreshAgent(){const ctx=current(),panel=document.getElementById('agent-panel');if(!ctx||!panel)return;
 const open=[...panel.querySelectorAll('details[open]')].map(x=>x.dataset.trace).filter(Boolean);
 const focused=panel.contains(document.activeElement)?document.activeElement:null;const saved=focused?{id:focused.id,start:focused.selectionStart,end:focused.selectionEnd}:null;
 panel.innerHTML=V.agent(state,ui,ctx.task,ctx.stage);
 for(const id of open){const detail=[...panel.querySelectorAll('details[data-trace]')].find(x=>x.dataset.trace===id);if(detail)detail.open=true;}
 if(saved?.id){const input=document.getElementById(saved.id);if(input){input.focus({preventScroll:true});if(typeof input.setSelectionRange==='function'&&saved.start!==null)input.setSelectionRange(saved.start,saved.end);}}
}
function errorFor(task,stage,error){ui.errors[task.id+':'+stage.id]=error.message;render(true);}
function newTaskDialog(moduleId){const module=V.mod(moduleId)||V.mod('factor');showDialog('新建任务','<form id="new-task-form"><div class="form-grid"><label class="field"><span>业务模块</span><select id="new-module">'+B.modules.map(m=>'<option value="'+m.id+'"'+(m.id===module.id?' selected':'')+'>'+V.e(m.name)+'</option>').join('')+'</select></label><label class="field"><span>任务名称</span><input id="new-name" value="新的'+V.e(module.name.replace('平台',''))+'任务" maxlength="80"></label></div><div class="hint">建立独立任务，已有资产仍可复用。其他任务不因这个任务等待而被阻断。</div><div class="dialog-foot">'+V.button('取消','close-dialog')+V.button('建立任务','create-task','',true)+'</div></form>');}
function startSimulation(mode,forceNormal=false){
 const ctx=current();if(!ctx)return;
 const {task,stage}=ctx;
 try{
 if(mode==='execute'){const errors=M.validation(state,task,stage.id,C);if(errors.length)throw Error(errors.join('\n'));}
 delete ui.errors[task.id+':'+stage.id];
 const job=M.startJob(task,stage.id,mode,C,forceNormal?'normal':ui.scenario,ui.instructions[task.id]||'');
 ui.jobSelected[task.id+stage.id]=job.id;ui.agentTab='task';persist();render(true);toast(mode==='fill'?'开始预览本环节的填写建议。':'开始预览本环节的工具执行。');
 const tick=()=>{
 if(job.status!=='running'){clearInterval(timers.get(job.id));timers.delete(job.id);return;}
 if(job.phase<job.tools.length){M.advanceJob(job);persist();refreshAgent();return;}
 clearInterval(timers.get(job.id));timers.delete(job.id);
 if(mode==='fill'){
 if(job.caseName==='failure'){job.status='failed';job.error='模拟模型返回失败：草稿未被覆盖，可重试或人工填写。';}
 else {const result=M.completeFill(state,task,job,C);toast(result.conflict?'你已修改表单，AI建议保留为待应用草案。':'填写建议已回填，可继续编辑。');}
 }else {const result=M.executeJob(state,task,job,C);toast(result?'本环节产物已生成（场景预览）。':job.error||'预览已结束。');}
 persist();const now=current();if(now?.task.id===task.id&&now?.stage.id===stage.id)render(true);else if(ui.page==='overview')render(true);
 };
 timers.set(job.id,setInterval(tick,850));
 }catch(error){errorFor(task,stage,error);}
}
function artifactDialog(taskId,stageId,artifactId){const t=M.getTask(state,taskId),o=M.artifact(t,stageId,artifactId);if(!o)throw Error('此环节还没有产物。');showDialog(o.title,'<div class="policy-strip"><span>'+V.e(o.id)+'</span><span>输入版本 v'+o.revision+'</span><span>场景产物</span>'+V.tag(o.stale?'stale':o.passed?'completed':'needs_evidence')+'</div><p>'+V.e(o.summary)+'</p><h3 style="margin-top:20px">输入快照</h3><pre class="json">'+V.e(JSON.stringify(o.snapshot,null,2))+'</pre><div class="dialog-foot">'+V.button('导出本产物','export-artifact',taskId+'|'+stageId+'|'+o.id)+'</div>');}
function exportJSON(filename,value){const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function architecture(){showDialog('业务模块与协作边界','<div class="doc-preview"><p>五个业务模块通过数据版本、因子库、策略库与方案快照协作。现有资产可直接复用，各研究任务独立推进。</p><div class="grid-2" style="margin-top:20px">'+B.modules.map(m=>'<article class="card card-pad"><h3>'+V.e(m.name)+'</h3><p class="fine" style="margin:8px 0">'+V.e(m.purpose)+'</p><div class="fine">'+m.stages.map(s=>s.id+' '+V.e(s.name)).join(' → ')+'</div><div class="actions" style="margin-top:13px">'+V.button('进入模块','nav',m.id)+V.button('查看鱼骨图','blueprint',m.id)+'</div></article>').join('')+'</div><h2>公共入口</h2><p>管理驾驶舱汇总事实；审查中心按用途与权限处理决定；Agent管理维护工具、方法和运行政策。</p><h2>18类逻辑职责</h2><p>每个角色有明确任务、工具、交付与边界。计算、调度和硬检查由程序执行，Agent选择工具、诊断与协同。</p></div>',true);}
root.addEventListener('submit',event=>event.preventDefault());modal.addEventListener('submit',event=>event.preventDefault());
document.addEventListener('click',event=>{
 const target=event.target.closest('[data-action]');if(!target||target.disabled)return;
 const action=target.dataset.action,id=target.dataset.id||'';
 try{
 if(action==='nav'){ui.assetSearch='';navigate(id);}
 else if(action==='menu')document.body.classList.toggle('menu-open');
 else if(action==='close-dialog')modal.close();
 else if(action==='help')showDialog('原型说明','<div class="doc-preview"><p>这是一版用于产品评审的完整交互原型。场景资产、研究指标、工具事件、审批和部署回执均为预览数据。</p><ul><li>支持人工填写、Agent回填、工具过程预览、失败重试、审查与资产复用。</li><li>操作保存在当前浏览器的本原型空间，刷新可继续；不代表服务器共享存储。</li><li>不请求模型、不采集真实数据、不运行真实回测、不提交交易。</li><li>可从左下角打开现有已接通的真实研究工具工作台。</li></ul><div class="dialog-foot">'+V.button('导出场景记录','export-state')+V.button('恢复初始场景','reset-confirm')+'</div></div>');
 else if(action==='architecture')architecture();
 else if(action==='blueprint'){const key=id==='agents'?'agent-management':id;showDialog('业务拆解 · '+(V.mod(id)?.name||id),'<div class="diagram">'+(B.diagrams[key]||'<p>本图暂无内容。</p>')+'</div>',true);}
 else if(action==='new-task')newTaskDialog(id||ui.page);
 else if(action==='create-task'){const type=document.getElementById('new-module').value,name=document.getElementById('new-name').value.trim();if(!name)throw Error('请填写任务名称。');const t=M.newTask(state,type,C,name);persist();navigate(type+'/'+V.mod(type).code+'1');toast('独立研究任务已建立。');}
 else if(action==='open-task'){const t=M.getTask(state,id);state.selected[t.module]=t.id;persist();navigate(t.module+'/'+t.current);}
 else if(action==='save-draft'){persist();toast(storageFailed?'本页草稿仍在内存，请导出保存。':'草稿已保存在当前浏览器。');}
 else if(action==='manual'){const {task,stage}=current();delete ui.errors[task.id+':'+stage.id];try{const out=M.execute(state,task,stage.id,C,ui.scenario);persist();render(true);toast(out.passed?'产物已生成（场景预览）。':'证据或门槛未满足，已保留结果与原因。');}catch(error){errorFor(task,stage,error);}}
 else if(action==='ai-fill')startSimulation('fill');
 else if(action==='ai-run')startSimulation('execute');
 else if(action==='cancel-job'){for(const t of state.tasks){const job=t.jobs.find(j=>j.id===id);if(job){M.cancelJob(job);clearInterval(timers.get(id));timers.delete(id);persist();render(true);toast('已停止后续预览调用，草稿和已生成记录保留。');break;}}}
 else if(action==='retry-job'){const {task}=current(),job=task.jobs.find(j=>j.id===id);if(job){ui.scenario='normal';startSimulation(job.mode,true);}}
 else if(action==='agent-tab'){ui.agentTab=id;refreshAgent();}
 else if(action==='patch'){const t=M.getTask(state,id),patch=t.patch;if(!patch)throw Error('没有待应用的填写建议。');showDialog('核对填写建议',V.table(['字段','当前草稿','AI建议（预览）'],Object.entries(patch.values).map(([key,value])=>[V.e(C.stages[patch.stage].fields.find(f=>f.key===key)?.label||key),V.e(JSON.stringify(t.values[key])),V.e(JSON.stringify(value))]))+'<div class="hint warning">应用会覆盖表中对应字段；只对当前草稿生效。</div><div class="dialog-foot">'+V.button('保留当前草稿','close-dialog')+V.button('应用填写建议','apply-patch',id,true)+'</div>',true);}
 else if(action==='apply-patch'){const t=M.getTask(state,id);if(t.patch)M.applyPatch(state,t,t.patch,C);persist();modal.close();render(true);toast('建议已应用到草稿。');}
 else if(action==='chat-send'){const t=M.getTask(state,id),input=document.getElementById('chat-input'),message=input.value.trim();if(!message)throw Error('请先写下委托要求。');t.messages.push({from:'user',text:message,time:M.stamp()},{from:'assistant',text:'委托要求已记录（原型回执）。返回「运行」后，可用当前输入预览本环节执行；需要人工决定的事项仍会进入审查。',time:M.stamp()});ui.instructions[t.id]=message;persist();refreshAgent();}
 else if(action==='artifact'){const [taskId,stageId,artifactId]=id.split('|');artifactDialog(taskId,stageId,artifactId);}
 else if(action==='export-artifact'){const [taskId,stageId,artifactId]=id.split('|'),t=M.getTask(state,taskId);exportJSON(stageId+'-prototype-artifact.json',{prototype:true,taskId,artifact:M.artifact(t,stageId,artifactId)});toast('已导出场景产物。');}
 else if(action==='task-archive'){const t=M.getTask(state,id);showDialog('研究档案 · '+t.name,'<div class="policy-strip"><span>当前输入 v'+t.revision+'</span><span>'+Object.keys(t.outputs).length+' 项当前产物</span><span>'+t.history.length+' 项历史产物</span></div>'+V.table(['步骤','产物','状态','操作'],Object.entries(t.outputs).map(([sid,o])=>[V.e(sid),V.e(o.title),V.tag(o.stale?'stale':o.passed?'completed':'needs_evidence'),V.button('查看快照','artifact',t.id+'|'+sid)]))+'<details class="small-details"><summary>全部任务与版本记录</summary><pre class="json">'+V.e(JSON.stringify({task:t.id,revision:t.revision,history:t.history,upstream:t.upstream},null,2))+'</pre></details>');}
 else if(action==='asset-detail'){const [kind,assetId]=id.split('|'),a=state.assets[kind].find(x=>x.id===assetId);if(!a)throw Error('资产不存在。');showDialog(a.name,V.table(['项目','内容'],[['编号 / 版本',V.e(a.id+' / '+a.version)],['定义 / 范围',V.e(a.expr)],['状态',V.tag(a.status)],['使用范围',V.e(a.use)],['说明',V.e(a.detail)]])+'<div class="hint">场景资产；正式版本须绑定来源、验证证据、用途与责任记录。</div>'+(a.taskId?'<div class="dialog-foot">'+V.button('查看研究档案','task-archive',a.taskId)+'</div>':''));}
 else if(action==='use-asset'){const [kind,assetId]=id.split('|'),t=M.selectAsset(state,kind,assetId,C);persist();navigate(t.module+'/'+V.mod(t.module).code+'1');toast('已从存量资产建立下游研究，不等待上游新批次。');}
 else if(action==='resume-factor'){const t=M.resumeFactor(state,id,C);persist();navigate('factor/F3');toast('已载入因子定义，可直接开始复现。');}
 else if(action==='review-item'){ui.reviewTab='pending';ui.reviewId=id;navigate('review');}
 else if(action==='task-review'){const r=state.reviews.find(x=>x.taskId===id);if(!r)throw Error('尚无审查记录。');ui.reviewId=r.id;ui.reviewTab=['approved','rejected','expired'].includes(r.status)?'processed':r.status;navigate('review');}
 else if(action==='review-tab'){ui.reviewTab=id;render();}
 else if(action==='review-select'){ui.reviewId=id;render(true);}
 else if(action==='decide'){const [rid,decision]=id.split('|'),note=document.getElementById('review-note')?.value||'';M.decide(state,rid,decision,note);persist();ui.reviewTab=decision==='returned'?'returned':'processed';ui.reviewId=rid;render();toast('决定已记录（场景），相关资产状态已同步。');}
 else if(action==='review-evidence'){const r=state.reviews.find(x=>x.id===id);if(!r)throw Error('审查记录不存在');showDialog('审查证据快照 · '+r.version,'<div class="policy-strip"><span>'+V.e(r.name)+'</span><span>输入 v'+r.revision+'</span><span>提交时固定快照</span></div><p class="fine">此处保留提交时的输入和产物，不随源任务之后的编辑变化。</p>'+V.table(['步骤','证据 / 产物','生成版本'],(r.evidence||[]).map(o=>[V.e(o.stage),V.e(o.title)+'<br><small>'+V.e(o.id)+'</small>','v'+o.revision]))+'<details class="small-details"><summary>查看提交时输入与完整证据</summary><pre class="json">'+V.e(JSON.stringify({snapshot:r.snapshot,evidence:r.evidence,checks:r.checks},null,2))+'</pre></details>',true);}
 else if(action==='review-policy')showDialog('审查分层与授权',V.table(['事项','处理方式','决定责任'],[['普通研究实验','自动留档，无需逐次签字','研究人员按需介入'],['不达标或证据不足候选','自动归档或退回补证','规则与候选评审'],['共享研究准入','独立证据与优选候选送审','研究负责人'],['投资与资金方案','风险检查、授权匹配、版本绑定','投资负责人'],['风险恢复','措施回执、复测与恢复条件','风控负责人']])+'<div class="hint">预览身份仅用于评审交互，不是实际身份认证。正式系统必须在服务端校验权限。</div>');
 else if(action==='role'||action==='select-role'){ui.agentId=id;ui.roleFilter='';ui.methodTab=action==='role'?'responsibility':ui.methodTab;navigate('agents/'+id);}
 else if(action==='method-tab'){ui.methodTab=id;render(true);}
 else if(action==='save-method'){M.saveMethod(state,id,{prompt:document.getElementById('method-prompt').value,skills:document.getElementById('method-skills').value,knowledge:document.getElementById('method-knowledge').value});persist();render(true);toast('方法草案已保存，旧评测不再代表新版。');}
 else if(action==='evaluate-method'){M.evaluateMethod(state,id);persist();render(true);toast('已完成评测流转预览，不代表真实模型评测。');}
 else if(action==='publish-method'){M.publishMethod(state,id);persist();render(true);toast('方法版本已发布（场景）。');}
 else if(action==='skill-picker')showDialog('共享 Skill 库 · 场景装配','<div class="method-fields">'+['时点一致性核对','失败实验归档','证据与报告复核','工具错误诊断','成本敏感性分析'].map((skill,i)=>'<label class="check"><input type="checkbox" data-skill="'+V.e(skill)+'"'+(i===0?' checked':'')+'>'+V.e(skill)+' <span class="fine">· 公司共享 v1</span></label>').join('')+'</div><div class="dialog-foot">'+V.button('装配到当前草案','add-skills',id,true)+'</div>');
 else if(action==='add-skills'){const added=[...modal.querySelectorAll('[data-skill]:checked')].map(x=>x.dataset.skill),m=state.methods[id];M.saveMethod(state,id,{prompt:document.getElementById('method-prompt')?.value??m.prompt,skills:[...new Set([...(document.getElementById('method-skills')?.value??m.skills).split('\n'),...added])].join('\n'),knowledge:document.getElementById('method-knowledge')?.value??m.knowledge});persist();modal.close();ui.methodTab='configuration';render(true);toast('Skill已装配到草案，需重新评测后发布。');}
 else if(action==='save-plan'){const form=target.closest('form'),data={scope:form.elements.scope.value,trigger:form.elements.trigger.value,budget:form.elements.budget.value,maxTasks:form.elements.maxTasks.value,enabled:form.elements.enabled.checked};if(!data.scope.trim())throw Error('请填写运行范围。');M.savePlan(state,id,data);persist();render(true);toast('运行计划已保存（预览），不会创建真实后台任务。');}
 else if(action==='incident'){const t=M.selected(state,'monitor');M.edit(state,t,'event',id,'T2',C);t.values.affected=state.incidents.find(i=>i.id===id)?.object||'';persist();navigate('monitor/T2');}
 else if(action==='export-state')exportJSON('sunvalley-prototype-v3-scene.json',{prototype:true,...state});
 else if(action==='reset-confirm')showDialog('恢复初始场景','<p>只重置这个浏览器里V3原型的场景记录、草稿和预览任务。现有工具工作台和服务器研究数据不受影响。</p><div class="dialog-foot">'+V.button('取消','close-dialog')+V.button('确认恢复场景','reset-state','',true)+'</div>');
 else if(action==='reset-state'){for(const timer of timers.values())clearInterval(timer);timers.clear();state=initial();ui.errors={};ui.reviewTab='pending';ui.reviewId='';ui.methodTab='responsibility';ui.agentId='F-A1';ui.roleFilter='';ui.scenario='normal';ui.agentTab='task';ui.instructions={};ui.jobSelected={};persist();navigate('overview');toast('已恢复原型初始场景。');}
 }catch(error){toast(error.message);}
});
document.addEventListener('input',event=>{
 const input=event.target,ctx=current();
 if(input.dataset.field&&ctx){try{const value=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?'':Number(input.value)):input.value;M.edit(state,ctx.task,input.dataset.field,value,ctx.stage.id,C);delete ui.errors[ctx.task.id+':'+ctx.stage.id];persist();const label=document.getElementById('draft-status');if(label)label.textContent='已保存草稿 · v'+ctx.task.revision;const rev=document.querySelector('.taskbar .badge');if(rev)rev.textContent='v'+ctx.task.revision;const out=ctx.task.outputs[ctx.stage.id],status=document.querySelector('.result-card .card-head .badge');if(out?.stale&&status){status.className='badge warn';status.textContent='需重跑';}}catch(error){toast(error.message);}}
 if(input.dataset.instruction)ui.instructions[input.dataset.instruction]=input.value;
 if(input.id==='asset-search'){ui.assetSearch=input.value;const pos=input.selectionStart;render(true);const next=document.getElementById('asset-search');next?.focus({preventScroll:true});next?.setSelectionRange(pos,pos);}
});
document.addEventListener('change',event=>{
 const input=event.target;
 if(input.id==='persona'){state.persona=input.value;persist();render(true);}
 if(input.id==='task-select'){const t=M.getTask(state,input.value);state.selected[t.module]=t.id;persist();navigate(t.module+'/'+t.current);}
 if(input.dataset.multi){const ctx=current();if(ctx){const key=input.dataset.multi,values=[...document.querySelectorAll('[data-multi="'+key+'"]:checked')].map(x=>x.value);try{M.edit(state,ctx.task,key,values,ctx.stage.id,C);persist();document.getElementById('draft-status').textContent='已保存草稿 · v'+ctx.task.revision;}catch(error){toast(error.message);}}}
 if(input.id==='job-select'){const ctx=current();if(ctx){ui.jobSelected[ctx.task.id+ctx.stage.id]=input.value;refreshAgent();}}
 if(input.id==='simulation-case')ui.scenario=input.value;
 if(input.id==='role-filter'){ui.roleFilter=input.value;render(true);}
});
modal.addEventListener('click',event=>{if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)modal.close();}});
window.addEventListener('hashchange',()=>{route();render();window.scrollTo({top:0,behavior:'instant'});});
persist();route();render();
})();
