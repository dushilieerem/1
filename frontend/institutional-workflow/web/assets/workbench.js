/* Real research workbench. Human forms and AI share product-owned tools. */
'use strict';
(() => {
  const root = document.querySelector('#sv-quant');
  const modal = document.querySelector('#modal');
  let state, catalog, capabilities, currentReport, preview, online = true, pending = false;
  let route = [], selectedAgent = '', comparison = new Set(), stateRefreshedAt=0;
  const drafts = {
    factor: {name: '', expression: '', reason: '', preprocess: 'none', horizon: 5, groups: 4},
    strategy: {name: '', rebalance: 5, top_n: 4, cost_bps: 10, weights: {}},
    portfolio: {name: '', weights: {}}, data: {},
    assistant: {factor: '', strategy: ''}
  };
  const factorSelections={};
  const draftKey='svquant.workflow.factor.draft.v1';
  try{const saved=JSON.parse(sessionStorage.getItem(draftKey)||'null');if(saved&&typeof saved==='object'){
    for(const k of ['name','expression','reason','preprocess','horizon','groups','data_version','start','end','symbols','factor_id','parent_id','research_id'])if(k in saved)drafts.factor[k]=saved[k];
  }}catch{}
  drafts.factor.research_id=drafts.factor.research_id||crypto.randomUUID();
  function persistFactor(){try{sessionStorage.setItem(draftKey,JSON.stringify(drafts.factor));}catch{}}
  const names = {home:'研究总览', data:'数据资源', factor:'因子工厂', strategy:'策略研究', portfolio:'组合研究', review:'研究审查', experiments:'实验记录', assistant:'AI 助手', settings:'连接与方法'};
  const labels = {factor:'因子',strategy:'策略',portfolio:'组合',queued:'排队中',running:'运行中',completed:'已完成',failed:'失败',published:'已发布',cancelled:'已取消',interrupted:'已中断',not_submitted:'未送审',pending:'待审查',approved:'已登记',returned:'退回补证',rejected:'不采纳',pass:'通过',warn:'需关注',fail:'未通过'};
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function formatReply(value) {
    const inline=s=>esc(s).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
    const lines=String(value).split('\n'),out=[];
    for(let i=0;i<lines.length;i++) {
      const l=lines[i].trim();if(!l)continue;
      if(l.startsWith('|')&&/^\|[ :|\-]+\|$/.test((lines[i+1]||'').trim())) {
        const cells=s=>s.trim().slice(1,-1).split('|').map(x=>x.trim());
        let html='<div class="sv-tablewrap"><table><thead><tr>'+cells(l).map(x=>'<th>'+inline(x)+'</th>').join('')+'</tr></thead><tbody>';i++;
        while(i+1<lines.length&&lines[i+1].trim().startsWith('|'))html+='<tr>'+cells(lines[++i]).map(x=>'<td>'+inline(x)+'</td>').join('')+'</tr>';
        out.push(html+'</tbody></table></div>');continue;
      }
      if(/^#{1,4}\s/.test(l))out.push('<h3>'+inline(l.replace(/^#{1,4}\s+/,''))+'</h3>');
      else out.push('<p>'+inline(l)+'</p>');
    }
    return out.join('');
  }
  const num = (v,n=3) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(n) : '—';
  const pct = v => typeof v === 'number' && Number.isFinite(v) ? (100*v).toFixed(2)+'%' : '—';
  const when = v => v ? new Date(v*1000).toLocaleString('zh-CN',{hour12:false}) : '—';
  const badge = value => `<span class="sv-status ${['approved','pass','completed'].includes(value)?'good':['failed','fail','rejected'].includes(value)?'bad':['pending','warn','returned'].includes(value)?'warn':''}">${esc(labels[value] || value)}</span>`;
  const btn = (title,action,id='',primary=false,disabled=false) => `<button type="button" class="sv-btn ${primary?'active':''}" data-action="${action}" data-id="${esc(id)}" ${disabled?'disabled':''}>${esc(title)}</button>`;
  const goto = (title,path,primary=false) => btn(title,'nav',path,primary);
  const empty = text => `<div class="empty">${esc(text)}</div>`;
  const note = (text,kind='') => `<div class="note ${kind}">${esc(text)}</div>`;
  const table = (headers,rows) => `<div class="sv-tablewrap"><table><thead><tr>${headers.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(c=>`<tr>${c.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const metric = (name,value) => `<div class="metric"><b>${value}</b><small>${esc(name)}</small></div>`;
  const field = (group,key,title,type='text',attrs='') => `<label class="field">${esc(title)}<input type="${type}" data-group="${group}" data-key="${key}" value="${esc(drafts[group][key])}" ${attrs}></label>`;
  const area = (group,key,title,attrs='') => `<label class="field">${esc(title)}<textarea data-group="${group}" data-key="${key}" ${attrs}>${esc(drafts[group][key])}</textarea></label>`;
  const select = (group,key,title,options) => `<label class="field">${esc(title)}<select data-group="${group}" data-key="${key}">${options.map(([v,t])=>`<option value="${esc(v)}" ${String(drafts[group][key])===String(v)?'selected':''}>${esc(t)}</option>`).join('')}</select></label>`;
  const library = kind => state.library.filter(x=>x.kind===kind);
  const active = x => ['running','queued'].includes(x.status);
  async function api(path,body) {
    const response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value=await response.json();
    if(!response.ok) throw new Error(value.error || value.detail || '请求失败');
    return value;
  }
  function toast(text) {const el=document.querySelector('#toast');el.textContent=text;el.className='show';clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className='',6000);}
  function published() {return (catalog?.releases || []).filter(r=>r.status==='published');}
  function release(group) {return published().find(r=>r.version===drafts[group].data_version) || published()[0];}
  function defaults() {
    const r=published()[0];if(!r)return;
    for(const k of ['factor','strategy','data']) if(!drafts[k].data_version) Object.assign(drafts[k],{data_version:r.version,start:r.quality.start,end:r.quality.end,symbols:[...r.symbols]});
  }
  function dataFields(group) {
    const r=release(group);if(!r)return note('没有可用的已发布数据，请先检查本地数据服务。','error');
    return `${select(group,'data_version','固定行情版本',published().map(r=>[r.version,r.version]))}
      <div class="two">${field(group,'start','开始日期','date',`min="${r.quality.start}" max="${r.quality.end}"`)}${field(group,'end','结束日期','date',`min="${r.quality.start}" max="${r.quality.end}"`)}</div>
      <details><summary class="fine">研究证券池 · 已选 ${(drafts[group].symbols||[]).length} / ${r.symbols.length} 只</summary><div class="universe">${r.symbols.map(s=>`<label><input type="checkbox" data-symbol="${esc(s)}" data-group="${group}" ${(drafts[group].symbols||[]).includes(s)?'checked':''}>${esc(s)}</label>`).join('')}</div></details>`;
  }
  function tabs(kind,items) {return `<div class="tabs">${items.map(([id,title])=>`<button type="button" data-action="nav" data-id="${kind}/${id}" aria-selected="${kind==='factor'&&id==='start'?!['definitions','library'].includes(route[1]):(route[1]||'tools')===id}">${esc(title)}</button>`).join('')}</div>`;}
  const fillStages={factor:['start','design','test'],strategy:['goal','rules']};
  const stageTasks={factor:{design:'校验并保存当前表单中的因子定义，不修改研究假设。',test:'严格按当前表单的因子、固定数据版本和参数完成一次因子检验，读取结果，不提交审批。',results:'只读取当前表单关联的已有因子实验报告，复核指标和限制，不新建实验，不提交审批。'},strategy:{backtest:'使用当前表单选定的已登记因子及权重、数据和参数完成一次策略回测，读取结果，不提交审批。'}};
  const formRequests=new Map();
  function receiveFormPatches(){
    for(const job of state.agents){
      const request=formRequests.get(job.id);
      if(!request||!['completed','failed','cancelled'].includes(job.status))continue;
      formRequests.delete(job.id);
      if(job.status!=='completed'||!Object.keys(job.form_patch||{}).length)continue;
      const draft=drafts[job.module];
      if(JSON.stringify(draft)!==request.before){toast('AI 填写建议已生成；你已编辑草稿，请查看建议后选择应用');continue;}
      applyFormPatch(job);toast('AI 已填写当前草稿，请检查参数后再执行');
    }
  }
  function applyFormPatch(job){
    Object.assign(drafts[job.module],job.form_patch);
    if(job.module==='factor'&&['name','expression','preprocess'].some(k=>k in job.form_patch)){
      drafts.factor.parent_id=drafts.factor.factor_id||drafts.factor.parent_id;delete drafts.factor.factor_id;
    }
  }
  function assistantPane(module='factor') {
    if(module==='factor'&&route[0]==='factor')return factorAgentPanel(route[1]||'start');
    const a=state.agents.find(a=>a.module===module);
    const stage=route[1]||businessFlows[module]?.[0]?.[0];
    const canFill=fillStages[module]?.includes(stage);
    const patchJob=state.agents.find(j=>j.module===module&&j.stage===stage&&j.status==='completed'&&Object.keys(j.form_patch||{}).length);
    return `<aside class="assistant"><div class="agent-mark">AI</div><h2>${module==='factor'?'因子研究':'策略研究'}助手</h2><p>与人工共用表单和研究工具。先检查输入，再执行计算。</p>
      ${canFill?btn('AI 填写本页','fill-form',module,true,state.agents.some(active)||!state.connection.configured):''}
      ${stageTasks[module]?.[stage]?btn('AI 执行本环节','stage-ai',module,true,state.agents.some(active)||!state.connection.configured):''}
      ${patchJob?`<details><summary>最近一次 AI 填写建议</summary><pre>${esc(JSON.stringify(patchJob.form_patch,null,2))}</pre>${btn('应用到当前草稿','apply-form',patchJob.id)}</details>`:''}
      <label class="field">委托任务<textarea data-group="assistant" data-key="${module}" placeholder="例如：检验 20 日低波动因子，解释 IC 与分层结果">${esc(drafts.assistant[module])}</textarea></label>
      ${btn('交给 AI 执行','ask',module,true,state.agents.some(active)||!state.connection.configured)}
      <div class="fine">${state.connection.configured?'DeepSeek 已连接':'尚未配置模型连接'} · 每次最多 2 个实验<br>真实工具调用与结果全部保留</div>
      ${!state.connection.configured?goto('配置连接','settings'):''}
      ${a?`<div class="section">${badge(a.status)}<p class="fine">${esc(a.message.slice(0,100))}</p>${goto('查看工具执行记录','assistant/'+a.id)}${(a.run_ids||[]).map(r=>goto('打开本次实验报告','report/'+r)).join('')}</div>`:''}
    </aside>`;
  }

  const toolLabels={fill_form:'填写页面草稿',validate_expression:'校验因子表达式',save_factor:'保存因子定义',run_factor:'计算因子与检验指标',read_report:'读取实验报告',submit_review:'提交研究审查'};
  const intentLabels={fill_form:'填写本页',stage:'执行本环节',research:'自由委托'};
  function factorAgentPanel(stage){
    const blocked=state.agents.some(active)||!state.connection.configured;
    const role=stage==='start'?'因子研究助手':stage==='register'?'研究登记助手':'因子实验助手';
    return `<section class="assistant factor-assistant"><div class="toolbar"><div><span class="kicker">${esc(role)}</span><h2>Agent 运行台</h2></div>${badge(state.connection.configured?'可委托':'连接待配置')}</div>
      <div class="factor-ai-actions">${fillStages.factor.includes(stage)?btn('AI 填写本页','fill-form','factor',true,blocked):''}${stageTasks.factor[stage]?btn('AI 执行本环节','stage-ai','factor',false,blocked):''}</div>
      ${!state.connection.configured?`<p class="fine">当前没有模型连接；人工工具和历史记录可继续使用。${goto('配置连接','settings')}</p>`:''}
      <details class="factor-request"><summary>补充要求 / 自由委托</summary><p class="fine">一键执行使用左侧当前参数；自由委托可在因子工具范围内安排工作。</p>${area('assistant','factor','给 Agent 的要求','maxlength="1600" placeholder="例如：解释这次检验的不足，需要补哪些证据"')}${btn('发送委托','ask','factor',false,blocked)}</details>
      <div id="factor-live" data-stage="${esc(stage)}">${factorLive(stage)}</div>
    </section>`;
  }
  function factorLive(stage){
    const all=state.agents.filter(a=>a.module==='factor');
    const relevant=all.filter(a=>FactorTrace.belongs(a,stage,drafts.factor));
    const selected=factorSelections[stage];
    const job=all.find(a=>a.id===selected)||relevant[0];
    const historical=job&&!FactorTrace.belongs(job,stage,drafts.factor);
    const stageTitle=id=>factorStages.find(x=>x[0]===id)?.[1]||'旧记录 · 未标注环节';
    const options=all.map(a=>`<option value="${esc(a.id)}" ${job?.id===a.id?'selected':''}>${esc(stageTitle(a.stage))} / ${esc(intentLabels[a.intent]||'历史委托')} / ${esc(a.form?.name||a.message.slice(0,22))} / ${esc(labels[a.status])}</option>`).join('');
    const picker=all.length?`<label class="field trace-picker">查看任务<select id="factor-task-select"><option value="" ${!job?'selected':''}>当前研究 · 本环节任务</option>${options}</select></label>`:'';
    if(!job)return picker+`<div class="trace-empty"><strong>本环节尚无 Agent 任务</strong><p>${['results','register'].includes(stage)?'选择已有研究结果，在自由委托中说明复核要求。':'可以填写左侧参数后委托 AI。'}任务开始后，这里展示实际调用、返回结果和产物。</p><p class="fine">上方可选择历史记录；历史结果不会被标成本次运行。</p></div>`;
    const entries=FactorTrace.events(job),calls=entries.filter(x=>x.kind==='tool');
    const completed=calls.filter(x=>x.status==='completed').length,failed=calls.filter(x=>x.status==='failed').length;
    const runIds=[...new Set([...(job.run_ids||[]),...(job.evidence_ids||[])])];
    const factors=job.factor_ids||entries.filter(x=>x.output?.factor_id).map(x=>x.output.factor_id);
    const duration=job.finished?Math.max(0,Math.round((job.finished-job.created)*10)/10)+' 秒':active(job)?'任务尚未结束':'历史耗时未记录';
    const timeline=entries.map(x=>{
      if(x.kind==='model')return `<li class="trace-model"><span>${x.status==='running'?'◌':'·'}</span><div><strong>${x.status==='running'?'正在请求模型':x.selected_tools?.length?'模型选择：'+esc(x.selected_tools.map(n=>toolLabels[n]||n).join('、')):x.status==='failed'?'模型请求失败':'模型请求记录'}</strong><small>${when(x.at)}${x.duration_ms!==undefined?' · '+(x.duration_ms/1000).toFixed(1)+' 秒':''}</small>${x.error?`<p>${esc(x.error)}</p>`:''}</div></li>`;
      if(x.kind==='control')return `<li class="trace-model"><span>■</span><div>${esc(x.text)}<small>${when(x.at)}</small></div></li>`;
      const status=({completed:'工具返回',failed:'调用失败',cancelled:'停止接收',running:'调用中',unknown:'结果未确认',recorded:'历史记录'})[x.status]||'记录';
      const output=x.output;
      const brief=output?.error?output.error:output?.form_patch?'已生成 '+Object.keys(output.form_patch).length+' 项填写建议':output?.factor_id?'已保存定义 '+output.factor_id:output?.run_id?'关联实验 '+output.run_id+' · '+(labels[output.status]||output.status):output?.normalized?'表达式校验通过':output?'已收到工具结果':'等待工具返回';
      return `<li class="trace-tool ${x.status==='failed'?'trace-error':''}"><div class="trace-tool-head"><strong>${esc(toolLabels[x.tool]||x.text)}</strong>${badge(status)}</div><small>${when(x.at)}${x.duration_ms!==undefined?' · '+(x.duration_ms/1000).toFixed(1)+' 秒':''}</small><p>${esc(brief)}</p>${output?.summary?`<div class="trace-result-summary"><span>Rank IC ${num(output.summary.rank_ic_mean)}</span><span>ICIR ${num(output.summary.ic_ir)}</span><span>有效日 ${esc(output.summary.valid_days??'—')}</span></div>`:''}
        <details data-trace-key="${esc(x.key)}"><summary>查看实际输入与输出</summary><h4>输入参数</h4><pre>${esc(x.inputRecorded===false?'没有已执行工具的输入记录；请查看返回原因。':JSON.stringify(x.input??x.detail??{},null,2))}</pre><h4>工具输出</h4><pre>${esc(output?JSON.stringify(output,null,2):'尚未返回；不代表已完成。')}</pre></details></li>`;
    }).join('');
    return picker+`${historical?note('正在查看历史任务：'+stageTitle(job.stage)+'。不代表当前草稿的执行状态。'):''}
      <div class="trace-status" role="status"><span class="trace-dot ${active(job)?'is-running':''}"></span><strong>${online?FactorTrace.activity(job):'连接中断 · 以下为最后获取的记录'}</strong>${badge(job.status)}</div>
      <p class="fine">最近同步 ${when(stateRefreshedAt)}</p><details data-trace-key="goal-${esc(job.id)}"><summary>任务目标、方法与用量</summary><p class="trace-task">${esc(job.message)}</p><div class="fine">${esc(job.id)} · ${when(job.created)}<br>${esc(job.model||'历史模型未记录')} · 方法 v${job.method?.version??'—'} · ${duration}${job.usage?.uncertain?' · '+job.usage.uncertain+' Tokens 未确认':''}</div></details>
      <div class="trace-metrics"><span><b>${completed}</b>工具返回</span><span><b>${failed}</b>调用失败</span><span><b>${job.usage?.tokens??'—'}</b>确认 Tokens</span></div>

      <details data-trace-key="input-${esc(job.id)}"><summary>本次委托的固定输入与工具范围</summary><pre>${esc(JSON.stringify(job.form||{},null,2))}</pre><p class="fine">${esc((job.allowed_tools||[]).map(n=>toolLabels[n]||n).join('、')||'历史记录未保存授权工具清单')}</p></details>
      ${active(job)?`<div class="trace-controls">${btn('停止后续调用','cancel-ai',job.id)}<small>已发出的请求可能继续完成；修改表单不会改变本次固定输入。</small></div>`:''}
      <ol class="trace-timeline">${timeline||'<li class="fine">任务已入队，尚无工具执行记录。</li>'}</ol>
      ${job.error?note(job.error,'error'):''}
      ${Object.keys(job.form_patch||{}).length?`<details data-trace-key="patch-${esc(job.id)}"><summary>填写建议 · 对照当前草稿</summary>${table(['字段','当前草稿','AI 建议'],Object.entries(job.form_patch).map(([k,v])=>[esc(k),esc(drafts.factor[k]??''),esc(v)]))}${btn('应用到当前草稿','apply-form',job.id,false,job.status!=='completed')}</details>`:''}
      ${factors.length||runIds.length?`<div class="trace-artifacts"><h3>产物与证据</h3>${factors.map(id=>btn('载入定义 '+id,'load-factor',id)).join('')}${runIds.map(id=>{const r=state.runs.find(r=>r.id===id);return `<div>${goto((r?.name||'实验报告')+' · '+(labels[r?.status]||'查看'),'report/'+id)}<small>${esc(id)}${job.run_ids?.includes(id)?' · 本次生成':' · 本次读取'}</small></div>`;}).join('')}</div>`:''}
      ${job.reply?`<details data-trace-key="reply-${esc(job.id)}"><summary>Agent 结论与后续建议</summary><div class="reply">${formatReply(job.reply)}</div><p class="fine">这是模型解读；计算事实以工具输出和报告为准。</p></details>`:''}
      ${!active(job)&&!calls.length&&!Object.keys(job.form_patch||{}).length?note('本次任务没有工具调用或表单产物；文本回复不代表完成了因子检验。'):''}`;
  }
  function updateFactorLive(){
    const host=document.querySelector('#factor-live');if(!host||host.contains(document.activeElement))return;
    const open=[...host.querySelectorAll('details[open][data-trace-key]')].map(x=>x.dataset.traceKey);
    const scroller=host.querySelector('.trace-timeline'),scroll=scroller?.scrollTop||0;
    host.innerHTML=factorLive(host.dataset.stage);
    for(const el of host.querySelectorAll('details[data-trace-key]'))el.open=open.includes(el.dataset.traceKey);
    const next=host.querySelector('.trace-timeline');if(next)next.scrollTop=scroll;
  }

  const businessFlows={
    data:[
      ['source','数据接入','明确来源与范围','数据接入 Agent','匹配数据需求，规划增量采集与补采','发布目录查询；采集控制待接','来源方案、采集批次','规划职责；当前可选择已有发布版本'],
      ['clean','加工清洗','字段与规则标准化','数据加工 Agent','识别字段与异常，建议清洗规则、提取事件','字段说明；清洗编辑与事件提取待接','标准数据、加工记录','待接入加工工具'],
      ['quality','质量核验','核对覆盖与时点','数据质量 Agent','定位质量问题，提出隔离、修复或补采建议','已发布质量报告；完整时点核验待接','质量证据、问题清单','可查看质量；自动诊断待接'],
      ['query','发布与查询','固定版本供研究使用','数据发布与维护 Agent','整理版本说明，核对可用范围与发布依据','固定版本与真实查询；发布控制待接','发布版本、查询结果','查询可用；发布与维护Agent待接'],
      ['maintain','持续维护','修订与影响追踪','数据发布与维护 Agent','监测更新和历史修订，识别受影响研究','版本目录；依赖分析与回滚待接','维护记录、影响清单','当前为迁移发布快照，未启动更新调度']
    ],
    factor:[
      ['start','研究起点','假设与存量复用','因子研究 Agent','提出机制、作用方向与验证计划，查找可复用因子','因子定义、因子库、报告读取','研究假设、候选思路','通用助手可承担部分职责'],
      ['design','表达式设计','编写、校验与保存','因子实验 Agent','把假设转成表达式，根据校验反馈修改','validate_expression、save_factor','固定因子定义','工具已接入；服务器 AI 待连接验证'],
      ['test','计算检验','数据与诊断参数','因子实验 Agent','选择参数并调用真实工具，保留失败结果','run_factor、read_report','因子值、检验报告','工具已接入；服务器 AI 待连接验证'],
      ['results','结果复核','证据与补充验证','独立验证 Agent','复核口径、时点与稳健性，指出补证需求','报告读取；独立封存验证待接','复核意见、补证清单','报告解读可用；独立验证角色待接'],
      ['register','研究登记','候选送审与入库','因子资产 / 候选评审 Agent','整理因子卡和证据，提出送审或归档建议','read_report、submit_review；人工登记','研究资产、用途与决定记录','送审工具已接；AI没有批准权限']
    ],
    strategy:[
      ['goal','研究目标','目标与基线','策略设计 Agent','明确研究问题、信号假设与评价条件','因子库、原始报告','策略研究目标','由通用策略助手承担部分职责'],
      ['factors','选用因子','复用库内成果','策略设计 Agent','选择因子和相对权重，检查重复与适用范围','已登记因子库、read_report','固定因子组合','库内复用可用；全面查重待接'],
      ['rules','策略构建','信号转为持仓规则','策略设计 Agent','配置评分、选股、持仓、调仓和成本假设','排名加权、前N只等权、固定调仓','可执行规则配置','规则配置已接；任意代码与模型训练待接'],
      ['backtest','回测复核','运行、诊断与迭代','策略实验 / 独立验证 Agent','运行回测、解释收益回撤和成本，提出有限改进','run_strategy、read_report、实验对比','回测证据、修订方案','AI接口已接；独立验证待接'],
      ['register','登记与跟踪','审查、入库与观察','模拟跟踪与准入 Agent','整理策略卡和准入材料，跟踪运行偏差','研究送审、策略库；模拟跟踪待接','策略资产、准入材料','仅研究登记可用；模拟和资金准入待接']
    ],
    portfolio:[
      ['goal','组合目标','资金用途与约束','组合配置 Agent','把目标转成配置要求和风险预算','策略库与研究报告','组合目标、约束说明','人工研究工具可用；组合AI执行待接'],
      ['allocate','配置权重','选择策略与现金','组合配置 Agent','提出策略权重及现金比例，比较配置方案','固定权重混合；约束优化器待接','候选配置','人工固定权重可用；AI执行待接'],
      ['evaluate','组合评价','计算历史整体表现','组合配置 Agent','调用组合工具，对照配置目标解释结果','历史组合计算、研究报告','组合表现与计算证据','人工工具可用；AI执行待接'],
      ['risk','风险复核','暴露与极端情景','组合风险 Agent','检查相关性、集中度、流动性和压力情景','基础回撤报告；穿透与压力测试待接','风险报告、调整建议','基础历史指标可读；完整风险工具待接'],
      ['proposal','方案交付','研究登记与投资申请','投资方案 Agent','汇总配置、风险、实施和退出条件，准备审批材料','研究报告、研究登记；投资审批与执行待接','研究组合、待审投资方案','研究登记可用；资金批准和交易执行待接']
    ],
    review:[
      ['screen','候选筛选','先检查硬条件','候选评审 Agent','检查失败项和重复，筛出值得人审的候选','报告硬检查；绩效优选、全库去重待接','候选清单、归档原因','已有硬失败拦截；自动优选待接'],
      ['evidence','证据复核','检查报告与用途','独立验证 Agent','对照原始证据、时点和统计口径，指出缺项','原始报告、输入快照；封存验证待接','复核意见、补证要求','报告可查；独立验证待接'],
      ['decision','人工决定','登记、退回或否决','候选评审与送审 Agent','整理摘要并送审，跟踪人工决定','submit_review；人工决定工具','带依据的研究决定','AI仅能送审，人工决定'],
      ['archive','资产登记','保留用途与血缘','因子资产 / 策略资产职责','整理资产用途、依赖与后续复检要求','研究库、报告导出','固定研究资产、决定记录','研究库可用；生命周期自动化待接']
    ]
  };
  function stageOf(kind){return businessFlows[kind].find(x=>x[0]===route[1])||businessFlows[kind][0];}
  function flowNav(kind,stage){return `<nav class="factor-flow module-flow" style="--steps:${businessFlows[kind].length}" aria-label="${names[kind]}流程">${businessFlows[kind].map(([id,title,hint],i)=>`<button type="button" data-action="module-step" data-id="${kind}/${id}" aria-current="${stage===id?'step':'false'}"><span class="step-number">${i+1}</span><span><strong>${title}</strong><small>${hint}</small></span></button>`).join('')}</nav>`;}
  function agentPoint(kind,step){const x=businessFlows[kind].find(x=>x[0]===step)||stageOf(kind);return `<details class="agent-point"><summary>本环节 Agent · ${esc(x[3])}</summary><p>${esc(x[4])}</p><dl><dt>工具</dt><dd>${esc(x[5])}</dd><dt>交付</dt><dd>${esc(x[6])}</dd><dt>当前接入</dt><dd>${esc(x[7])}</dd></dl><p class="fine">角色是职责设计；当前已接能力由通用助手执行，不代表已部署独立角色。</p></details>`;}
  function moduleShell(kind,body){const x=stageOf(kind),i=businessFlows[kind].indexOf(x);return flowNav(kind,x[0])+`<div class="workspace"><section class="sv-panel"><h2>${i+1}. ${x[1]}</h2>${body}<div class="factor-next">${i?goto('上一步：'+businessFlows[kind][i-1][1],kind+'/'+businessFlows[kind][i-1][0]):'<span></span>'}${i<businessFlows[kind].length-1?goto('下一步：'+businessFlows[kind][i+1][1],kind+'/'+businessFlows[kind][i+1][0]):''}</div></section><aside>${kind==='strategy'?assistantPane('strategy'):''}${agentPoint(kind,x[0])}</aside></div>`;}
  function moduleRecords(kind){return runTable(state.runs.filter(r=>r.kind===kind));}
  function resourceNav(kind,items){return `<div class="tabs">${items.map(([id,title])=>`<button data-action="nav" data-id="${kind}/${id}" aria-selected="${id==='flow'?!['library','definitions'].includes(route[1]):route[1]===id}">${title}</button>`).join('')}</div>`;}

  function overview() {
    const running=state.runs.filter(active).length, pendingReview=state.runs.filter(r=>r.review==='pending').length;
    const cards=[['data','01','数据资源','选择行情版本，核查质量与覆盖范围',`${published().length} 个已发布版本`],['factor','02','因子工厂','定义表达式，检验 IC、分层与稳定性',`${state.factors.length} 个定义 · ${library('factor').length} 个库内因子`],['strategy','03','策略研究','复用因子库，构建规则并运行回测',`${library('strategy').length} 个库内策略`],['portfolio','04','组合研究','配置策略权重，评估历史组合表现',`${library('portfolio').length} 个研究组合`],['review','05','研究审查','查看计算证据，登记成果或退回补证',`${pendingReview} 项待审查`]];
    return `<div class="stats">${[[state.runs.length,'累计实验'],[running,'正在计算'],[pendingReview,'等待审查'],[state.library.length,'已登记研究资产']].map(([v,t])=>`<div class="stat"><strong>${v}</strong><span>${t}</span></div>`).join('')}</div>
      <div class="sv-map">${cards.map(([id,n,title,desc,foot])=>`<button class="sv-platform" data-action="nav" data-id="${id}"><b>${n}</b><div><strong>${title}</strong><span>${businessFlows[id].map(x=>x[1]).join(' → ')}</span><small class="fine">${esc([...new Set(businessFlows[id].map(x=>x[3]))].join(' · '))}</small><div class="platform-foot">${foot}</div></div></button>`).join('')}</div>
      <div class="section"><div class="toolbar"><h2>最近研究</h2>${goto('全部实验','experiments')}</div>${runTable(state.runs.slice(0,5))}</div>
      ${note('共享数据版本 → 因子库 → 策略库 → 组合研究；研究审查贯穿成果登记。各模块可使用库内历史资产独立工作。')}<div class="sv-panel section"><h2>投后与风险 · 规划</h2><p>持仓监测 → 收益归因 → 风险处置 → 复盘改进</p><p class="fine">运行监测 Agent、归因复盘 Agent、风险处置 Agent。账户、交易和投后工具尚未接入。</p></div>`;
  }
  function dataPage() {
    const r=release('data');if(!r)return empty('尚无已发布版本，请检查固定数据服务。');const q=r.quality,step=stageOf('data')[0];let body='';
    if(step==='source')body=`<p>选择已有数据作为研究起点。</p>${dataFields('data')}${note('当前接入迁移的已发布行情。数据源凭证管理、自动采集与补采控制尚未接入本工作区。')}<h3>接入工具</h3>${btn('配置采集来源（待接入）','unavailable','',false,true)}`;
    if(step==='clean')body=`<h3>当前数据字段</h3>${table(['字段','口径'],[['open / high / low / close','后复权日线价格'],['volume','成交量，单位股'],['date / symbol','交易日期与证券代码']])}${note('当前使用已经清洗发布的行情。清洗规则编辑、原始数据对照和事件提取待接入，不能在这里修改发布数据。')}${btn('编辑清洗规则（待接入）','unavailable','',false,true)}`;
    if(step==='quality')body=`${dataFields('data')}<div class="metrics section">${metric('证券',r.symbols.length)}${metric('行情行数',q.rows??q.row_count??'—')}</div><h3>发布时的质量检查</h3>${(q.checks||[]).length?table(['检查项'],q.checks.map(k=>[esc(({unique_primary_key:'主键唯一',finite_positive_ohlc:'价格有效',ohlc_bounds:'高低价边界',volume_nonnegative:'成交量非负',coverage_90pct:'行情覆盖达标',aligned_latest_date:'最新日期对齐'})[k]||k)])):empty('版本没有返回逐项检查。')}${note('这些是发布版本保存的证据，不是刚执行的新检查；完整历史时点与跨源核验待接。')}`;
    if(step==='query')body=`${dataFields('data')}${btn('查询最近 30 行','preview','',true)}<div class="section"><h3>行情明细</h3>${preview?`${note('查询结果版本：'+preview.version)}${table(['日期','证券','开盘','最高','最低','收盘','成交量'],preview.rows.map(r=>[esc(r.date),esc(r.symbol),...['open','high','low','close'].map(k=>num(r[k],2)),num(r.volume,0)]))}`:empty('选择版本与区间，然后查询真实行情。')}</div>${goto('使用数据研究因子','factor/start')}`;
    if(step==='maintain')body=`<h3>固定发布目录</h3>${table(['版本','区间','状态'],published().map(v=>[esc(v.version),esc(v.quality.start)+' — '+esc(v.quality.end),badge(v.status)]))}<p class="fine">当前版本校验值：${esc(r.manifest_sha256)}</p>${note('本服务器使用迁移快照，尚未接持续更新、撤回影响传播和回滚工具。此处不会操作其他平台的数据服务。')}${btn('配置维护计划（待接入）','unavailable','',false,true)}`;
    return moduleShell('data',body);
  }
  const factorStages=[['start','研究起点','提出假设或复用定义'],['design','表达式设计','编写、校验与保存'],['test','计算检验','设置数据并运行'],['results','结果复核','检查指标与补证'],['register','研究登记','送审、决定与入库']];
  function factorFlow(stage) {
    return `<nav class="factor-flow" aria-label="因子研究流程">${factorStages.map(([id,title,hint],i)=>`<button type="button" data-action="factor-step" data-id="${id}" aria-current="${stage===id?'step':'false'}"><span class="step-number">${i+1}</span><span><strong>${title}</strong><small>${hint}</small></span></button>`).join('')}</nav>`;
  }
  function factorPage() {
    const stage=factorStages.some(x=>x[0]===route[1])?route[1]:'start';
    const top=tabs('factor',[['start','研究流程'],['definitions','因子定义'],['library','因子库']]);
    if(route[1]==='library')return top+libraryTable('factor')+`<div class="action-row section">${goto('开始新的因子研究','factor/start')}${goto('使用因子构建策略','strategy')}</div>`;
    if(route[1]==='definitions')return top+(state.factors.length?table(['因子','表达式','来源','操作'],state.factors.map(f=>[`${esc(f.name)}<div class="fine">${esc(f.id)}</div>`,`<code>${esc(f.expression)}</code>`,esc(f.source),btn('载入研究','load-factor',f.id)])):empty('暂无因子定义。可以手工填写，也可以委托 AI 创建。'));
    const d=drafts.factor, runs=state.runs.filter(r=>r.kind==='factor'&&(!d.factor_id||r.snapshot?.factor_id===d.factor_id));
    const index=factorStages.findIndex(x=>x[0]===stage);
    let body='';
    if(stage==='start')body=`${field('factor','name','因子名称','text','maxlength="80" placeholder="例如：20 日低波动"')}${area('factor','reason','研究假设','placeholder="预期作用方向是什么？为什么可能有效？准备验证什么？"')}<div class="action-row">${goto('从已有定义继续','factor/definitions')}${goto('查看已登记因子','factor/library')}</div><p class="fine section">本轮产出：研究问题与候选思路。已有定义可以直接载入，不必重新创建。</p>`;
    if(stage==='design')body=`${field('factor','name','因子名称','text','maxlength="80"')}${area('factor','expression','因子表达式','class="code" placeholder="-ts_std(close / delay(close, 1) - 1, 20)"')}<div class="chips">${[['momentum','填入动量表达式'],['volatility','填入低波动表达式'],['reversal','填入短期反转表达式']].map(([k,v])=>`<button data-action="example" data-id="${k}">${v}</button>`).join('')}${btn('表达式说明','syntax')}</div>${select('factor','preprocess','截面预处理',[['none','不预处理'],['zscore','标准化'],['winsor_zscore','缩尾后标准化']])}<div class="action-row">${btn('校验表达式','validate')}${btn('保存定义','save-factor')}</div><p class="fine section">本轮产出：可执行因子定义。保存草稿不等于登记入库。</p>`;
    if(stage==='test')body=`<p class="fine">当前表达式</p><pre>${esc(d.expression||'尚未填写；请先进入表达式设计，或载入已有定义。')}</pre>${dataFields('factor')}<div class="two section">${field('factor','horizon','前瞻持有期（交易日）','number','min="1" max="20" step="1"')}${field('factor','groups','分层数量（每层至少 2 只证券）','number','min="2" max="5" step="1"')}</div>${btn('运行因子检验','run','factor',true,pending||!d.expression.trim())}<p class="fine section">运行时固定定义、数据与参数。计算完成后可直接查看报告，未保存的定义会先保存。</p>`;
    if(stage==='results')body=`${note(d.factor_id?'以下为当前定义的实验；打开报告检查 IC、分层、分段和适用范围。':'以下为全部因子实验；可打开报告接续某次研究。')}${runTable(runs)}<p class="fine section">需要改进时回到表达式或检验设置。当前分段为研发对照，独立封存验证尚未接入。</p>${goto('对比实验','experiments')}`;
    if(stage==='register')body=`${!d.factor_id?note('尚未选定已保存的因子定义，以下展示全部已完成因子实验。'):''}${note('打开候选报告，填写提交依据后送审；人工检查证据与用途，决定登记、退回或不采纳。登记成功后可在因子库复用。')}${runTable(runs.filter(r=>r.status==='completed'))}<div class="action-row section">${goto('进入审查工作区','review')}${goto('查看因子库','factor/library')}</div><p class="fine section">不是每个实验都需要登记。差的结果保留记录；研究登记不等于投资批准。</p>`;
    const latest=runs[0];
    const context=`<div class="factor-context"><div><span class="fine">当前研究</span><strong>${esc(d.name||'新因子研究')}</strong></div><span>${d.factor_id?badge('已保存定义'):badge('未保存草稿')}${d.factor_id&&latest?` ${badge(latest.status)} ${badge(latest.review)}`:''} ${btn('新研究','new-factor')}</span></div>`;
    const footer=`<div class="factor-next">${index?goto('上一步：'+factorStages[index-1][1],'factor/'+factorStages[index-1][0]):'<span></span>'}${index<4?goto('下一步：'+factorStages[index+1][1],'factor/'+factorStages[index+1][0]):''}</div>`;
    return top+factorFlow(stage)+context+`<div class="workspace factor-workspace"><section class="sv-panel"><h2>${index+1}. ${factorStages[index][1]}</h2>${body}${footer}</section><aside>${assistantPane('factor')}${agentPoint('factor',stage)}</aside></div>`;
  }
  function components(kind,source) {
    const assets=library(source);
    if(!assets.length)return empty(`暂无已登记${labels[source]}。先完成研究审查，即可在这里反复复用。`)+goto('查看研究审查','review');
    return assets.map(a=>`<label class="check-row"><input type="checkbox" data-component="${a.id}" data-group="${kind}" ${Object.hasOwn(drafts[kind].weights,a.id)?'checked':''}><span>${esc(a.name)}<small class="fine"> · ${esc(a.run_id)}</small></span><input type="number" aria-label="${esc(a.name)}权重" min="0" max="${kind==='portfolio'?100:1000}" step="1" data-weight="${a.id}" data-group="${kind}" value="${drafts[kind].weights[a.id]??(kind==='portfolio'?100:1)}"></label>`).join('');
  }
  function strategyPage() {
    const top=resourceNav('strategy',[['flow','研究流程'],['library','策略库']]);if(route[1]==='library')return top+libraryTable('strategy');
    const step=stageOf('strategy')[0];let body='';
    if(step==='goal')body=`${field('strategy','name','策略名称','text','maxlength="80" placeholder="例如：低波动选股策略"')}${area('strategy','goal','研究目标与基线','placeholder="希望检验什么信号？与哪个基线比较？"')}${note('目标说明随人工回测输入保存。可以直接复用已有因子，不必等待新一批因子。')}${goto('查看已有策略','strategy/library')}`;
    if(step==='factors')body=`<p>选择已登记因子，设置相对权重。</p>${components('strategy','factor')}<div class="section">${goto('查看因子库与报告','factor/library')}</div>`;
    if(step==='rules')body=`<h3>信号与持仓规则</h3>${note('因子截面排名加权 → 选取最高分前N只 → 等权持有 → 按设定间隔调仓。收盘信号在下一交易日开盘执行。')}<div class="three section">${field('strategy','rebalance','调仓间隔（交易日）','number','min="1" max="60"')}${field('strategy','top_n','持仓证券数','number','min="1" max="16"')}${field('strategy','cost_bps','单边综合成本（bps）','number','min="0" max="200"')}</div>${note('目前支持上述规则配置；任意策略代码、机器学习训练和复杂交易限制待接入。')}`;
    if(step==='backtest')body=`${dataFields('strategy')}<p class="fine section">已选 ${Object.keys(drafts.strategy.weights).length} 个因子 · ${esc(drafts.strategy.rebalance)} 日调仓 · 成本 ${esc(drafts.strategy.cost_bps)} bps</p>${btn('运行策略回测','run','strategy',true,pending||!Object.keys(drafts.strategy.weights).length)}<div class="section"><h3>策略实验与报告</h3>${moduleRecords('strategy')}${goto('对比实验','experiments')}</div>${note('报告包含研发分段；受保护的独立验证尚未接入。')}`;
    if(step==='register')body=`${note('选择报告提交研究审查；批准登记后进入策略库。模拟跟踪、交易准入和真实资金批准尚未接入。')}${moduleRecords('strategy')}<div class="action-row section">${goto('研究审查','review/decision')}${goto('策略库','strategy/library')}</div>${btn('启动模拟跟踪（待接入）','unavailable','',false,true)}`;
    return top+moduleShell('strategy',body);
  }
  function portfolioPage() {
    const top=resourceNav('portfolio',[['flow','组合流程'],['library','组合库']]);if(route[1]==='library')return top+libraryTable('portfolio');
    const step=stageOf('portfolio')[0];let body='';
    if(step==='goal')body=`${field('portfolio','name','组合名称','text','maxlength="80"')}${area('portfolio','goal','目标与约束说明','placeholder="配置目标、资金用途及需要关注的风险"')}${note('当前约束说明作为人工研究输入保存，尚未接入自动约束优化和风险限额引擎。')}${goto('查看可复用策略','strategy/library')}`;
    if(step==='allocate')body=`<p>选择已登记策略并填写组合权重（%）。剩余部分作为现金，按零收益处理。</p>${components('portfolio','strategy')}${note('成分策略必须具有相同回测日历；当前为固定权重配置。')}`;
    if(step==='evaluate')body=`<p>已选 ${Object.keys(drafts.portfolio.weights).length} 个策略，配置权重合计 ${num(Object.values(drafts.portfolio.weights).reduce((a,b)=>a+Number(b),0),1)}%。</p>${btn('计算历史组合表现','run','portfolio',true,pending||!Object.keys(drafts.portfolio.weights).length)}${note('混合成分策略净收益；未计跨策略净额与额外再平衡成本。')}<div class="section"><h3>组合计算报告</h3>${moduleRecords('portfolio')}</div>`;
    if(step==='risk')body=`${note('先检查已有报告的回撤与成分配置。持仓穿透、相关性、流动性和压力测试仍待接入；历史回撤不代表完整风险评估。')}${moduleRecords('portfolio')}${btn('执行压力测试（待接入）','unavailable','',false,true)}`;
    if(step==='proposal')body=`${note('当前可以导出组合研究报告、提交研究登记。公司投资方案审批链、资金授权和订单执行待接入。')}${moduleRecords('portfolio')}<div class="action-row section">${goto('研究审查','review/decision')}${goto('组合库','portfolio/library')}</div>${btn('提交资金使用审批（待接入）','unavailable','',false,true)}`;
    return top+moduleShell('portfolio',body);
  }
  function runTable(runs,compare=false) {
    if(!runs.length)return empty('尚无实验记录。手工操作和 AI 运行都会出现在这里。');
    return table([...(compare?['对比']:[]),'实验','类型 / 来源','运行状态','研究审查','时间','操作'],runs.map(r=>[
      ...(compare?[`<input type="checkbox" aria-label="对比 ${esc(r.name)}" data-compare="${r.id}" ${comparison.has(r.id)?'checked':''} ${r.status!=='completed'?'disabled':''}>`]:[]),
      `${esc(r.name)}<div class="fine">${esc(r.id)}</div>`,`${esc(labels[r.kind])} · ${esc(r.source==='human'?'人工':r.source)}`,badge(r.status),badge(r.review),when(r.created),goto(active(r)?'查看运行':'打开报告','report/'+r.id)
    ]));
  }
  function libraryTable(kind) {
    const assets=library(kind);
    if(!assets.length)return empty(`尚无已登记${labels[kind]}。研究报告通过审查后可在这里复用。`);
    return table(['资产','结果摘要','登记时间','操作'],assets.map(a=>[`${esc(a.name)}<div class="fine">${esc(a.id)} · 仅供研究</div>`,kind==='factor'?`Rank IC ${num(a.summary.rank_ic_mean)}`:`年化 ${pct(a.summary.annual_return)} · 回撤 ${pct(a.summary.max_drawdown)}`,when(a.created),goto('原始报告','report/'+a.run_id)]));
  }
  function reviewPage() {
    const step=stageOf('review')[0],waiting=state.runs.filter(r=>r.review==='pending');let body='';
    if(step==='screen')body=`${note('已完成实验保留全部记录。送审时程序会拦截硬检查失败；完整绩效优选与去重待接入。')}<h3>待选择的完成实验</h3>${runTable(state.runs.filter(r=>r.status==='completed'&&['not_submitted','returned'].includes(r.review)))}<p class="fine">打开报告检查结果，值得进一步关注的再提交审查。</p>`;
    if(step==='evidence')body=`<h3>待审证据 · ${waiting.length}</h3>${runTable(waiting)}${note('复核研究假设、数据时点、指标口径、失败尝试与适用范围。打开原始报告可查看输入快照和结果血缘；独立验证未接通。')}`;
    if(step==='decision')body=`<h3>等待人工决定 · ${waiting.length}</h3>${waiting.length?table(['候选','类型','操作'],waiting.map(r=>[esc(r.name),esc(labels[r.kind]),goto('查看证据','report/'+r.id)+' '+btn('填写审查决定','decide',r.id,true)])):empty('没有待审候选。可以从候选筛选查看研究结果。')}${note('决定必须附依据。登记、退回补证或不采纳仅针对研究用途，不批准真实资金使用。')}`;
    if(step==='archive')body=`<h3>审查决定记录</h3>${runTable(state.runs.filter(r=>['approved','returned','rejected'].includes(r.review)))}<div class="action-row section">${goto('因子库','factor/library')}${goto('策略库','strategy/library')}${goto('组合库','portfolio/library')}</div>`;
    return moduleShell('review',body);
  }
  function chart(points,title,percent=false) {
    const p=points.filter(p=>typeof p.value==='number'&&Number.isFinite(p.value));
    if(p.length<2)return empty('可用观测不足，暂不绘制曲线。');
    const min=Math.min(...p.map(x=>x.value)),max=Math.max(...p.map(x=>x.value)),span=max-min||1;
    const stride=Math.max(1,Math.ceil(p.length/250)),display=p.filter((_,i)=>i%stride===0||i===p.length-1);
    const path=display.map((x,i)=>`${i?'L':'M'}${(45+(p.indexOf(x)/(p.length-1))*640).toFixed(2)},${(195-(x.value-min)/span*150).toFixed(2)}`).join(' ');
    return `<svg class="chart" viewBox="0 0 720 235" role="img" aria-label="${esc(title)}"><text x="45" y="22">${esc(title)}</text><path d="M45 45V195H685" stroke="#e4deeb" fill="none"/><path d="${path}" stroke="#7950ba" stroke-width="1.7" fill="none"/><text x="5" y="50">${esc(percent?pct(max):num(max,2))}</text><text x="5" y="195">${esc(percent?pct(min):num(min,2))}</text><text x="45" y="220">${esc(p[0].date)}</text><text x="600" y="220">${esc(p[p.length-1].date)}</text></svg>`;
  }
  function reportPage() {
    const r=currentReport;
    if(!r||r.id!==route[1])return empty('正在读取实验记录…');
    const report=r.report,s=report?.summary;
    const actions=`<div class="action-row">${goto('返回实验记录','experiments')}${active(r)?btn('取消实验','cancel',r.id):''}${r.status==='completed'?`<a class="sv-btn" href="/api/runs/${r.id}/export">导出完整记录</a>`:''}${r.status==='completed'&&['not_submitted','returned'].includes(r.review)?btn('提交研究审查','submit',r.id,true):''}${r.review==='pending'?btn('审查此实验','decide',r.id,true):''}${r.kind==='factor'?btn('接续因子研究','resume',r.id):''}</div>`;
    let result=`<div class="toolbar"><div><h2>${esc(r.name)}</h2><div class="fine">${esc(r.id)} · ${esc(r.source==='human'?'人工':r.source)} · ${when(r.created)}</div></div><div>${badge(r.status)} ${badge(r.review)}</div></div>${actions}`;
    if(r.error)result+=note(r.error,'error');
    if(active(r))result+=note('计算服务正在处理固定输入。关闭页面不会取消任务；可以继续处理其他研究。');
    if(report) {
      if(r.kind==='factor')result+=`<div class="metrics">${metric('平均 IC',num(s.ic_mean))}${metric('平均 Rank IC',num(s.rank_ic_mean))}${metric('ICIR · 未年化',num(s.ic_ir))}${metric('因子覆盖率',pct(report.coverage))}</div>${chart(report.daily_ic,'每日截面 IC')}${note(report.labels.ic+'。'+report.labels.ic_ir+'。')}
        <div class="two section"><section><h2>分层诊断</h2>${table(['层级','平均前瞻收益','有效日'],report.quantiles.map(q=>[esc(q.group),pct(q.mean_forward_return),q.days]))}<div class="fine">${esc(report.labels.quantiles)}</div></section><section><h2>参考因子相关性</h2>${table(['参考因子','平均排名相关'],report.correlations.map(c=>[esc(c.name),num(c.mean_rank_correlation)]))}</section></div>
        <div class="section"><h2>研发分段对照</h2>${table(['区间','IC','Rank IC','有效日'],report.segments.map(x=>[esc(x.name),num(x.ic_mean),num(x.rank_ic_mean),x.valid_days]))}</div>
        <details class="section"><summary>查看最近因子值</summary>${table(['日期','证券','因子值'],report.preview.slice(-16).map(p=>[esc(p.date),esc(p.symbol),num(p.value,6)]))}</details>`;
      else result+=`<div class="metrics">${metric('年化收益',pct(s.annual_return))}${metric('最大回撤',pct(s.max_drawdown))}${metric('夏普',num(s.sharpe,2))}${metric('总收益',pct(s.total_return))}</div>${chart(report.curve,'扣除设定成本后的历史净值')}
        ${report.segments?`<div class="section"><h2>研发分段对照</h2>${table(['区间','年化收益','最大回撤','夏普'],report.segments.map(x=>[esc(x.name),pct(x.annual_return),pct(x.max_drawdown),num(x.sharpe,2)]))}</div>`:''}
        ${report.positions?`<div class="section"><h2>期末研究持仓</h2>${table(['证券','权重'],report.positions.map(p=>[esc(p.symbol),pct(p.weight)]))}<p class="fine">平均单边换手 ${pct(s.daily_one_way_turnover)} / 交易日</p></div>`:''}`;
      result+=`<div class="section"><h2>检查与适用范围</h2>${report.checks.map(c=>`<div class="check-row">${badge(c.status)}<span>${esc(c.name)}<div class="fine">${esc(c.detail)}</div></span></div>`).join('')}${note(report.limitations.join('\n'),'warning')}</div>
        <details class="section"><summary>输入快照与结果血缘</summary><pre>${esc(JSON.stringify({input:r.snapshot, data:report.data,engine:report.engine,report_sha256:r.report_sha256},null,2))}</pre></details>`;
    }
    if(report?.components)result+=`<div class="section"><h2>组合配置</h2>${table(['成分回测','配置权重'],report.components.map(x=>[esc(state.runs.find(y=>y.id===x.run_id)?.name||x.run_id),pct(x.weight)]).concat([['现金（按零收益）',pct(report.summary.cash_weight)]]))}</div>`;
    if(r.submission)result+=note(`提交依据：${r.submission.note}`);
    if(r.decision)result+=note(`人工决定：${labels[r.review]} · ${r.decision.note}`);
    return (r.kind==='factor'?factorFlow(active(r)?'test':r.review==='pending'||r.review==='approved'?'register':'results'):businessFlows[r.kind]?flowNav(r.kind,r.kind==='strategy'?'backtest':'evaluate'):'')+result+`<div class="section"><h2>运行记录</h2>${r.logs.map(x=>`<div class="log"><time>${when(x.at)}</time>${esc(x.message)}</div>`).join('')||empty('任务已进入队列。')}</div>`;
  }
  function agentPage() {
    const a=state.agents.find(x=>x.id===(route[1]||selectedAgent))||state.agents[0];
    return `<div class="workspace"><section class="sv-panel"><div class="toolbar"><h2>工具执行记录</h2>${a&&active(a)?btn('停止本次任务','cancel-ai',a.id):''}</div>${state.agents.length?`<label class="field">历史委托<select id="agent-history">${state.agents.map(x=>`<option value="${x.id}" ${a?.id===x.id?'selected':''}>${esc(x.message.slice(0,40))} · ${labels[x.status]}</option>`).join('')}</select></label>`:''}
      ${a?`${badge(a.status)}<p class="section">${esc(a.message)}</p><div class="fine">方法版本 v${a.method.version} · ${when(a.created)}</div>${a.steps.map(x=>`<div class="log"><time>${when(x.at)}</time><strong>${esc(x.text)}</strong>${x.detail?`<details><summary class="fine">查看参数与观察</summary><pre>${esc(JSON.stringify(x.detail,null,2))}</pre></details>`:''}</div>`).join('')}${a.reply?`<div class="reply">${formatReply(a.reply)}</div><p class="fine">AI 解读供参考，请以关联报告中的计算表、口径与局限为准。因子工具已计算分层与分段诊断；按当日因子值排名分层，前瞻收益只用于评价，不用于分组。</p>`:''}${a.error?note(a.error,'error'):''}<div class="action-row section">${[...new Set([...a.run_ids,...(a.evidence_ids||[])])].map(id=>goto('打开 '+id,'report/'+id)).join('')}</div>`:empty('还没有委托记录。输入任务后，AI 会调用与人工相同的工具，并记录每次执行。')}</section>${assistantPane(a?.module==='strategy'?'strategy':'factor')}</div>`;
  }
  function settingsPage() {
    const u=state.connection.usage;
    return `<div class="two"><section class="sv-panel"><h2>模型连接</h2>${badge(state.connection.configured?'已配置':'未配置')}<p class="fine section">DeepSeek · https://api.deepseek.com<br>密钥只保留在本服务内存，重启后需要重新配置。</p><label class="field">API Key<input type="password" id="api-key" autocomplete="off" placeholder="${state.connection.configured?'已配置；留空保持不变':'填写密钥'}"></label><label class="field">模型<input id="model-name" value="${esc(u.model)}"></label><label class="field">本版累计额度（Tokens）<input id="token-limit" type="number" min="${u.tokens+u.reserved+u.uncertain}" max="200000" step="1000" value="${u.token_limit}"></label><p class="fine">上限不得超过已授权的 200,000 Tokens；只在主动委托时使用。</p>${btn('保存连接','connection','',true)}
      <div class="metrics">${metric('累计 Tokens',u.tokens.toLocaleString())}${metric('本版额度',u.token_limit.toLocaleString())}</div><p class="fine">请求 ${u.calls} 次 · 预留 ${u.reserved} · 未确定 ${u.uncertain}<br>单次委托最多 5 轮决策、4 次工具调用、2 个研究实验。</p></section>
      <section class="sv-panel"><h2>研究方法 · v${state.method.version}</h2><p class="fine">作为助手的补充方法说明；修改仅影响新委托，工具权限与数值计算口径保持由程序约束。</p><label class="field">方法说明<textarea id="method-prompt" style="min-height:240px">${esc(state.method.prompt)}</textarea></label>${btn('保存新版本','method','',true)}</section></div>
      ${note('当前为本地单用户研究工作台。数据源、实验和研究库是实际读写；企业身份权限、持续调度、完整数据维护和实盘执行仍需后续接入。')}<p class="fine"><a href="/prototype" target="_blank" rel="noopener">打开上一版静态流程原型</a>（历史样例，不与当前研究记录混用）</p>`;
  }
  function render() {
    if(!state)return;
    receiveFormPatches();persistFactor();
    const page=route[0]||'home',titles={...names,report:'研究报告'};
    const descriptions={home:'量化研究 · 实验、资产与审查',data:businessFlows.data.map(x=>x[1]).join(' → '),factor:'研究起点 → 表达式设计 → 计算检验 → 结果复核 → 研究登记',strategy:businessFlows.strategy.map(x=>x[1]).join(' → '),portfolio:businessFlows.portfolio.map(x=>x[1]).join(' → '),review:businessFlows.review.map(x=>x[1]).join(' → '),experiments:'人工与 AI 的全部研究，统一保留',assistant:'委托任务，查看实际调用与观察',settings:'配置模型连接与研究方法',report:'原始输入、实际结果与审查记录'};
    const contents={home:overview,data:dataPage,factor:factorPage,strategy:strategyPage,portfolio:portfolioPage,review:reviewPage,experiments:()=>`<div class="toolbar"><h2>研究实验 · ${state.runs.length}</h2>${btn('对比所选实验','compare')}</div>${runTable(state.runs,true)}`,assistant:agentPage,settings:settingsPage,report:reportPage};
    root.innerHTML=`<header class="sv-top"><div class="sv-brand"><span class="sv-seal">旸</span>旸谷资本<small>SUNVALLEY · 量化研究工作台</small></div><div class="sv-actions"><span class="sv-tag">${online?'服务器研究 · 实际计算':'服务连接中断'}</span><span class="sv-tag">${state.agents.some(active)?'AI 正在执行':state.connection.configured?'AI 已连接':'AI 待配置'}</span></div></header>
      <div class="sv-shell"><nav class="sv-nav" aria-label="研究导航"><div class="sv-navlabel">研究工作区</div>${Object.entries(names).map(([id,title])=>`<button data-action="nav" data-id="${id}" aria-current="${page===id?'page':'false'}">${title}${id==='review'&&state.runs.some(r=>r.review==='pending')?' · '+state.runs.filter(r=>r.review==='pending').length:''}</button>`).join('')}<div class="sv-footnote">固定数据 · 可复现研究<br>人工工具与 AI 共用<br>研究责任人</div></nav><main><div class="sv-header"><div><h1>${titles[page]||names.home}</h1><p class="sv-muted sv-small">${descriptions[page]||descriptions.home}</p></div>${page!=='home'?goto('研究总览','home'):''}</div>${(contents[page]||overview)()}<div class="footer">研究用途 · 当前证券池与回测假设不代表完整市场或实盘结果</div></main></div>`;
  }
  async function refresh(renderNow=true) {
    state=await api('state');online=true;stateRefreshedAt=Date.now()/1000;
    if(route[0]==='report'&&route[1])currentReport=await api('runs/'+encodeURIComponent(route[1]));
    if(renderNow)render();
  }
  async function navigate() {
    route=location.hash.slice(1).split('/');if(!route[0])route=['home'];
    // Old role links still land at the actual factor/strategy tool page.
    if(/^\d+$/.test(route[1]||''))route[1]=route[0]==='factor'?(factorStages[Number(route[1])-1]?.[0]||'start'):'tools';
    if(route[0]==='factor'&&(!route[1]||route[1]==='tools'))route[1]='start';
    render();
    if(route[0]==='report')try{currentReport=await api('runs/'+encodeURIComponent(route[1]));render();}catch(e){toast(e.message);}
    window.scrollTo(0,0);
  }
  function openModal(title,content) {modal.innerHTML=`<div class="head"><h2>${esc(title)}</h2><button data-action="close" aria-label="关闭">×</button></div><div class="body">${content}</div>`;modal.showModal();}
  function decisionDialog(id,submit=false) {
    openModal(submit?'提交研究审查':'研究资产审查',`<form id="review-form" data-run="${id}" data-submit="${submit}"><p>登记只代表纳入研究库，不等于允许交易或证明投资有效。</p>${submit?'':`<label>处理决定<select name="decision"><option value="approve">登记入研究库</option><option value="return">退回补证</option><option value="reject">不采纳</option></select></label>`}<label>依据与适用范围<textarea name="note" required minlength="4" maxlength="2000" placeholder="说明依据、适用范围及仍需验证的部分"></textarea></label><button type="submit">${submit?'提交审查':'保存人工决定'}</button></form>`);
  }
  async function saveFactor() {
    const d=drafts.factor;
    if(d.factor_id)return d.factor_id;
    const f=await api('factors',d);d.factor_id=f.id;return f.id;
  }
  root.addEventListener('input',event=> {
    const e=event.target,g=e.dataset.group;if(!g)return;
    if(e.dataset.key) {drafts[g][e.dataset.key]=e.type==='number'?Number(e.value):e.value;if(g==='factor'&&['name','expression','reason','preprocess'].includes(e.dataset.key)){if(drafts.factor.factor_id)drafts.factor.parent_id=drafts.factor.factor_id;delete drafts.factor.factor_id;}}
    if(e.dataset.symbol) {const s=new Set(drafts[g].symbols);e.checked?s.add(e.dataset.symbol):s.delete(e.dataset.symbol);drafts[g].symbols=[...s];}
    if(e.dataset.component){if(e.checked)drafts[g].weights[e.dataset.component]=g==='portfolio'?100:1;else delete drafts[g].weights[e.dataset.component];}
    if(e.dataset.weight&&Object.hasOwn(drafts[g].weights,e.dataset.weight))drafts[g].weights[e.dataset.weight]=Number(e.value);
    if(g==='factor')persistFactor();
  });
  root.addEventListener('change',event=> {
    const e=event.target;
    if(e.dataset.key==='data_version') {const r=release(e.dataset.group);Object.assign(drafts[e.dataset.group],{start:r.quality.start,end:r.quality.end,symbols:[...r.symbols]});render();}
    if(e.id==='factor-task-select'){factorSelections[route[1]||'start']=e.value;updateFactorLive();render();}
    if(e.id==='agent-history')location.hash='assistant/'+e.value;
    if(e.dataset.compare){e.checked?comparison.add(e.dataset.compare):comparison.delete(e.dataset.compare);}
  });
  async function action(e) {
    const target=e.target.closest('[data-action]');if(!target)return;
    const {action:a,id}=target.dataset;
    if(a==='nav'){location.hash=id;return;}
    if(a==='module-step'){
      const [kind,step]=id.split('/');
      if(route[0]==='report'&&currentReport?.kind===kind&&drafts[kind]){
        const snap=currentReport.snapshot;
        if(kind==='strategy')Object.assign(drafts.strategy,{...snap,weights:Object.fromEntries((snap.factors||[]).map(x=>[x.id,x.weight]))});
        if(kind==='portfolio')Object.assign(drafts.portfolio,{name:currentReport.name,goal:snap.goal||'',weights:Object.fromEntries((snap.strategies||[]).map(x=>[x.id,x.weight*100]))});
      }
      location.hash=id;return;
    }
    if(a==='factor-step'){
      if(route[0]==='report'&&currentReport?.kind==='factor'){
        const f=state.factors.find(x=>x.id===currentReport.snapshot.factor_id);
        if(f)Object.assign(drafts.factor,{...currentReport.snapshot,name:f.name,expression:f.expression,reason:f.reason,preprocess:f.preprocess,factor_id:f.id});
      }
      location.hash='factor/'+id;return;
    }
    if(a==='new-factor'){Object.assign(drafts.factor,{name:'',expression:'',reason:'',preprocess:'none',horizon:5,groups:4,research_id:crypto.randomUUID()});delete drafts.factor.factor_id;delete drafts.factor.parent_id;for(const k of Object.keys(factorSelections))delete factorSelections[k];persistFactor();location.hash='factor/start';render();return;}
    if(a==='close'){modal.close();return;}
    if(a==='reload'){location.reload();return;}
    target.disabled=true;
    try {
      if(a==='example') {
        const examples={momentum:['20 日动量','close / delay(close, 20) - 1'],volatility:['20 日低波动','-ts_std(close / delay(close, 1) - 1, 20)'],reversal:['5 日反转','-(close / delay(close, 5) - 1)']};
        [drafts.factor.name,drafts.factor.expression]=examples[id];delete drafts.factor.factor_id;render();return;
      }
      if(a==='syntax'){openModal('因子表达式',`<p>字段：${esc(capabilities.fields.join('、'))}</p><p>函数：${esc(Object.keys(capabilities.functions).join('、'))}</p><p>支持 + − × ÷ 与括号。delay、ts_mean、ts_std 等窗口为正整数，最多 252 日；不能调用任意 Python 或使用未来数据。</p><pre>close / delay(close, 20) - 1\n-ts_std(close / delay(close, 1) - 1, 20)\nrank(volume / ts_mean(volume, 20))</pre>`);return;}
      if(a==='validate'){const r=await api('validate',drafts.factor);toast('表达式通过校验：'+r.normalized);return;}
      if(a==='save-factor'){await saveFactor();toast('已保存因子定义');}
      if(a==='load-factor'||a==='resume') {
        const f=a==='load-factor'?state.factors.find(x=>x.id===id):state.factors.find(x=>x.id===currentReport.snapshot.factor_id);
        if(!f)throw Error('原始因子定义不可用');
        Object.assign(drafts.factor,{name:f.name,expression:f.expression,reason:f.reason,preprocess:f.preprocess,factor_id:f.id});
        if(a==='resume')Object.assign(drafts.factor,{...currentReport.snapshot,factor_id:f.id});
        location.hash='factor/design';render();return;
      }
      if(a==='run') {
        pending=true;let body={...drafts[id],kind:id};
        if(id==='factor')body.factor_id=await saveFactor();
        if(id==='strategy')body.factors=Object.entries(drafts.strategy.weights).map(([id,weight])=>({id,weight}));
        if(id==='portfolio')body.strategies=Object.entries(drafts.portfolio.weights).map(([id,weight])=>({id,weight:weight/100}));
        delete body.weights;const r=await api('runs',body);currentReport=r;location.hash='report/'+r.id;
      }
      if(a==='preview'){const d=drafts.data;preview=await api('preview',{version:d.data_version,start:d.start,end:d.end,symbols:d.symbols});}
      if(a==='cancel'){await api('cancel',{id});toast('已取消接收该实验结果');}
      if(a==='submit'||a==='decide'){decisionDialog(id,a==='submit');return;}
      if(a==='stage-ai'){
        const stage=route[1],form={...drafts[id]};
        if(id==='strategy')form.factors=Object.entries(form.weights).map(([id,weight])=>({id,weight}));
        if(id==='factor')form.run_ids=state.runs.filter(r=>r.kind==='factor'&&r.snapshot?.factor_id===form.factor_id).map(r=>r.id);
        if(id==='factor'&&stage==='results'&&!form.run_ids.length)throw Error('当前因子还没有可复核的实验，请先计算检验');
        const job=await api('assistant',{module:id,intent:'stage',stage,form,message:stageTasks[id][stage]});
        if(id==='factor')factorSelections[stage]=job.id;
        toast('任务已进入本环节运行台');
      }
      if(a==='fill-form'){
        const before=JSON.stringify(drafts[id]);
        const job=await api('assistant',{module:id,intent:'fill_form',stage:route[1]||businessFlows[id][0][0],form:JSON.parse(before),message:'请结合当前表单和真实可用的数据、工具，填写本环节的研究参数。'+(drafts.assistant[id]||'')});
        formRequests.set(job.id,{before});if(id==='factor')factorSelections[job.stage]=job.id;toast('AI 正在填写本页，完成后将回填未被你修改的草稿');
      }
      if(a==='apply-form'){const job=state.agents.find(j=>j.id===id);if(job)applyFormPatch(job);}
      if(a==='ask'){
        const message=(drafts.assistant[id]||'').trim();if(message.length<3)throw Error('请填写至少 3 字的委托任务');
        const job=await api('assistant',{module:id,message,stage:route[1]||'',form:drafts[id]||{}});selectedAgent=job.id;if(id==='factor'&&route[0]==='factor'){factorSelections[job.stage||'start']=job.id;}else location.hash='assistant/'+job.id;
      }
      if(a==='cancel-ai'){await api('assistant/cancel',{id});toast('已停止后续 AI 动作；已发出的请求可能仍会完成计费');}
      if(a==='connection'){const input=document.querySelector('#api-key');await api('connection',{api_key:input.value,model:document.querySelector('#model-name').value,token_limit:Number(document.querySelector('#token-limit').value)});input.value='';toast('连接配置已保存');}
      if(a==='method'){await api('method',{prompt:document.querySelector('#method-prompt').value});toast('已保存新的方法版本');}
      if(a==='compare'){
        if(comparison.size<2||comparison.size>3)throw Error('请选择 2–3 个已完成实验');
        const jobs=await Promise.all([...comparison].map(id=>api('runs/'+id)));
        if(new Set(jobs.map(x=>x.kind)).size>1)throw Error('请选择同一类型的实验进行对比');
        const factor=jobs[0].kind==='factor';
        openModal('实验对比',`<p>仅并列展示原始结果；区间、证券池和成本不同时不能直接比较优劣。</p>${table(['实验','数据 / 区间',factor?'Rank IC':'年化收益',factor?'ICIR':'最大回撤'],jobs.map(x=>[esc(x.name),`${esc(x.snapshot.data_version||'成分回测')}<br>${esc(x.snapshot.start||'')} – ${esc(x.snapshot.end||'')}`,factor?num(x.report.summary.rank_ic_mean):pct(x.report.summary.annual_return),factor?num(x.report.summary.ic_ir):pct(x.report.summary.max_drawdown)]))}`);return;
      }
      await refresh();
    } catch(err){toast(err.message);} finally {target.disabled=false;pending=false;}
  }
  document.addEventListener('click',action);
  modal.addEventListener('submit',async event=> {
    if(event.target.id!=='review-form')return;event.preventDefault();const f=event.target,b=f.querySelector('button[type=submit]');b.disabled=true;
    try{const values=new FormData(f);await api(f.dataset.submit==='true'?'submit':'review',{id:f.dataset.run,note:values.get('note'),decision:values.get('decision')});modal.close();await refresh();toast('研究记录已更新');}catch(err){toast(err.message);}finally{b.disabled=false;}
  });
  window.addEventListener('hashchange',navigate);
  let needsRender=false;
  async function tick() {
    try {
      const before=JSON.stringify([state,currentReport]);
      await refresh(false);
      needsRender=needsRender || before!==JSON.stringify([state,currentReport]);
      const editing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)||modal.open;
      if(route[0]==='factor'&&document.querySelector('#factor-live'))updateFactorLive();
      if(!editing&&needsRender){const opened=[...document.querySelectorAll('#factor-live details[open]')].map(x=>x.dataset.traceKey);const scroll=document.querySelector('#factor-live')?.scrollTop||0;render();for(const el of document.querySelectorAll('#factor-live details[data-trace-key]'))el.open=opened.includes(el.dataset.traceKey);const list=document.querySelector('#factor-live');if(list)list.scrollTop=scroll;needsRender=false;}
    }catch(e){online=false;updateFactorLive();if(!document.querySelector('input:focus,textarea:focus'))render();}
    setTimeout(tick,state?.agents.some(active)||state?.runs.some(active)?1800:5000);
  }
  async function boot() {
    try {const c=await api('catalog');catalog=c.catalog;capabilities=c.capabilities;defaults();await refresh(false);await navigate();setTimeout(tick,1800);}
    catch(err){root.innerHTML=`<div class="sv-panel"><h1>研究工作台暂未连接</h1><p>${esc(err.message)}</p><p>请检查本地数据服务和计算服务，再刷新页面。</p><button data-action="reload">重新连接</button></div>`;}
  }
  boot();
})();
