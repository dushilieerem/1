'use strict';
// Design-only state. No business API, model, database or real review is called.
const KEY = 'svquant.factor.design.v4.20261105';
const $ = (q, r = document) => r.querySelector(q);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const steps = [['F1','研究起点','任务与参考资产'],['F2','假设与计划','机制、表达式、门槛'],['F3','因子实现','代码与静态检查'],['F4','研发检验','效果、稳健性、去重'],['F5','独立验证','冻结候选与证据'],['F6','资产管理','复核、入库与跟踪']];
const initialCode = '# 因子表达式示意；正式实现需适配平台计算接口\ndef compute(data):\n    gap = data.open / data.close.shift(1) - 1\n    return -gap.rolling(5).mean()';
function fresh(scenario = 'revision') { return {schema:4, page:'workflow', stage:'F2', workStage:'F1', scenario, status:'idle', cursor:0, follow:true, active:'H1', view:'H1', agentTab:'work', name:'交易拥挤与短期回补', goal:'研究开盘偏离与成交拥挤是否包含短期回补信息，寻找相对已有反转因子的增量。', universe:'沪深 300 历史成分', budget:6, authorized:false, spent:0, versions:[{id:'H1', parent:null, owner:'人工草稿', title:'开盘偏离后的短期回补', hypothesis:'开盘价相对前收盘的偏离，可能由短期情绪和流动性冲击造成；观察其后续回补。', expression:'-ts_mean(open / delay(close, 1) - 1, 5)', window:'5', code:initialCode, saved:true, locked:false, checked:false}], experiments:[], logs:[], messages:[{who:'agent',text:'我会围绕这项研究使用因子库、代码检查和检验工具。你可以自己编辑，也可以委托我连续研究；遇到权限边界时我会停下来。'}], review:'none', dataVersion:'行情快照 D1', note:'', next:'完善研究假设，然后实现并检验。'}; }
let state;
try { const parsed = JSON.parse(sessionStorage.getItem(KEY)); state = parsed?.schema === 4 ? parsed : fresh(); } catch { state = fresh(); }
let timer = null, modal = '', lastFocus = null, toastTimer;
function persist() { try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch {} }
function v(id = state.view) { return state.versions.find(x => x.id === id); }
function active() { return v(state.active); }
function log(title, detail, stage = state.workStage) { state.logs.push({title,detail,stage,time:new Date().toLocaleTimeString('zh-CN',{hour12:false})}); }
function toast(text) { $('#toast').textContent=text; $('#toast').classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),3000); }
function badge(text, type = '') { return `<span class="badge ${type}">${esc(text)}</span>`; }
function btn(text, action, kind = '', extra = '') { return `<button class="btn ${kind}" data-action="${action}" ${extra}>${text}</button>`; }
function field(label, key, value, options={}) { const attrs = `data-bind="${key}" ${options.disabled?'disabled':''}`; return `<label class="field ${options.full?'full':''}"><span>${label}</span>${options.type==='textarea'?`<textarea ${attrs} class="${options.code?'code':''}" rows="${options.rows||3}">${esc(value)}</textarea>`:`<input ${attrs} value="${esc(value)}" ${options.type==='number'?'type="number" min="1" max="12"':''}>`}${options.help?`<small>${options.help}</small>`:''}</label>`; }
function readonly() { return !!v().locked || (['running','paused'].includes(state.status) && state.authorized && state.view===state.active); }
function card(title, sub, body, actions='') { return `<section class="card"><div class="card-head"><div><h3>${title}</h3>${sub?`<p>${sub}</p>`:''}</div>${actions}</div><div class="card-body">${body}</div></section>`; }
function render() {
  const focused=document.activeElement; const key=focused?.dataset?.bind; const chatFocused=focused?.id==='chat-input'; const selection=key||chatFocused?[focused.selectionStart,focused.selectionEnd]:null;
  persist();
  $('#scenario').value=state.scenario;
  document.querySelectorAll('[data-page]').forEach(x=>{x.classList.toggle('active',x.dataset.page===state.page);x.setAttribute('aria-current',x.dataset.page===state.page?'page':'false');});
  $('#content').innerHTML = state.page==='library'?library():state.page==='experiments'?experimentsPage():workflow();
  const advance=$('[data-action="advance"]'); advance.disabled = !['running','paused'].includes(state.status);
  const restored=key?document.querySelector(`[data-bind="${key}"]`):chatFocused?$('#chat-input'):null; if(restored&&!restored.disabled){restored.focus({preventScroll:true});try{restored.setSelectionRange(...selection);}catch{}}
}
function statusInfo() {
  if (state.status==='running') return ['研究中',state.next,'purple'];
  if (state.status==='paused') return ['已暂停', '已完成的工具结果已保留。可以查看、另开分支，或继续原研究。','amber'];
  if (state.status==='needs-data') return ['等待补充数据','成交量字段校验失败；不将数据不完整认定为因子无效。','amber'];
  if (state.status==='needs-scope') return ['等待授权','Agent 建议引入分钟数据，超出当前日频研究范围。','amber'];
  if (state.status==='review') return ['待人工复核','候选与证据包已冻结；Agent 不代替独立复核。','green'];
  if (state.status==='complete') return ['已登记研究资产','此为原型审批结果；尚无组合或实盘授权。','green'];
  if (state.status==='stopped') return ['研究已结束','达到本轮停止条件，失败记录与结论已留档。','amber'];
  if(state.logs.length&&!state.authorized)return ['人工研究中','人工操作与产物已保留，可继续使用工具或委托 Agent。',''];
  return ['待启动','自己完成当前环节，或委托 Agent 连续研究。',''];
}
function toolbarActions() {
  if (state.status==='running') return btn('暂停并接管','pause')+btn('查看授权','policy','ghost');
  if (state.status==='paused') return btn('继续原研究','resume','primary')+btn('另开人工分支','branch');
  if (state.status==='needs-data') return btn('处理数据问题','data-request','primary');
  if (state.status==='needs-scope') return btn('查看变更请求','scope-request','primary');
  if (state.status==='review') return btn('查看复核包','review-active','primary');
  if (['complete','stopped'].includes(state.status)) return btn('查看研究记录','history');
  return btn('✧ 委托 Agent 完成研究','delegate','primary');
}
function stepStatus(id) {
  if(state.workStage===id && state.status==='running') return '正在工作';
  if(id==='F6' && state.review==='pending') return '待复核';
  if(id==='F6' && state.review==='approved') return '已登记';
  if(id==='F5' && state.experiments.some(e=>e.kind==='validation')) return '证据已冻结';
  if(id==='F4' && state.experiments.length) return `${state.experiments.filter(e=>e.kind==='research').length} 轮记录`;
  if(id==='F2') return `${state.versions.length} 个假设版本`;
  if(id==='F3' && active().checked) return '实现已检查';
  return steps.find(s=>s[0]===id)[2];
}
function workflow() {
  const [st,desc,tone] = statusInfo();
  return `<div class="task-head"><div><span class="code">QF-026 · 研究任务</span><h2>${esc(state.name)}</h2><div class="task-meta"><span>${esc(state.universe)}</span><span>日频 · 2023–2024 研发</span><span>${esc(state.dataVersion)}</span></div></div><div class="actions">${btn('研究约定','policy','small')}${btn('版本与记录','history','small')}</div></div>
  <div class="status-strip ${tone==='amber'?'warning':''}"><div class="status-icon">${state.status==='running'?'✧':'◉'}</div><div class="status-main"><div>${badge(st,tone)} <strong>${state.status==='running'?`${state.workStage} ${steps.find(s=>s[0]===state.workStage)[1]}`:state.status==='idle'?'研究可以从这里继续':'当前研究状态'}</strong></div><p>${esc(desc)}</p>${!state.follow && state.status==='running'?`<small>你正在查看 ${state.stage} · ${state.view}。${btn('跟随 Agent','follow','small ghost')}</small>`:''}</div><div class="actions">${toolbarActions()}</div></div>
  <nav class="step-nav" aria-label="因子研究环节">${steps.map(([id,name])=>`<button class="step ${state.stage===id?'active':''} ${state.workStage===id&&state.status==='running'?'working':''}" data-stage="${id}" aria-current="${state.stage===id?'step':'false'}"><span class="num">${id.slice(1)}</span><span><strong>${name}</strong><small>${stepStatus(id)}</small></span></button>`).join('')}</nav>
  <div class="work-grid"><div class="work-main">${stageView()}</div>${agentPanel()}</div>`;
}
function versionBar() { return `<div class="section-title"><div>${badge(state.view,'purple')} <b>${esc(v().title)}</b><small class="muted"> · ${esc(v().owner)}</small></div><div class="actions"><select class="version-select" id="version" aria-label="假设版本">${state.versions.map(x=>`<option value="${x.id}" ${x.id===state.view?'selected':''}>${x.id}${x.id===state.active?(state.authorized?' · Agent 当前分支':' · 当前研究'):''}${x.locked?' · 已留证':''}</option>`).join('')}</select>${btn('另开分支','branch','small')}</div></div>`; }
function lockHint() { return readonly()?`<div class="readonly-note">${v().locked?'此版本已有实验或复核证据，保留原样。':state.status==='paused'?'这是 Agent 暂停时保留的分支；人工修改请建立副本，继续原研究时不会覆盖。':'Agent 正在使用此版本；人工修改请建立独立分支。'} ${btn('建立可编辑副本','branch','small ghost')}</div>`:''; }
function stageView() {
  const item=v(), locked=readonly();
  if(state.stage==='F1') return card('研究任务','从研究问题出发，也可以直接使用已有因子资产。',`<div class="field-grid">${field('研究名称','name',state.name,{full:true,disabled:state.authorized})}${field('研究问题与目标','goal',state.goal,{type:'textarea',full:true,disabled:state.authorized,rows:4})}${field('研究范围','universe',state.universe,{disabled:state.authorized})}<label class="field"><span>研究类型</span><input value="新因子发现 · 必须检查已有因子相似度" disabled></label></div><div class="hint">数据、因子库可直接取用。当前任务无需等待其他研究员完成新的交付。</div><div class="actions">${btn('保存研究任务','save-task','primary',state.authorized?'disabled':'')}${btn('浏览已有因子','library')}${btn('让助手完善任务','assist')}</div>`)+card('参考资料与输入','研究开始时形成输入快照，后续变化另存版本。',`<div class="artifact"><span class="artifact-icon">▤</span><div class="artifact-info"><b>${esc(state.dataVersion)} · 日频行情</b><small>open / close / volume · 历史成分与交易日历</small></div>${badge('示例','')}</div><div class="artifact"><span class="artifact-icon">ƒ</span><div class="artifact-info"><b>已有因子目录 L1</b><small>短期反转、成交量变化、波动率 · 检验时冻结比较清单</small></div>${btn('查看资产','library','small')}</div>`);
  if(state.stage==='F2') return versionBar()+card('研究假设与计划','人工编辑与 Agent 修订使用同一份研究记录。',`${item.parent?`<div class="decision-box"><span class="return-arrow">↶</span><div><b>${item.owner==='Agent 修订'?'从研发检验返回修订':'人工建立研究分支'} · ${esc(item.parent)} → ${item.id}</b><p>${item.owner==='Agent 修订'?'E1 的预测能力未达预设门槛。保留原假设，新增成交拥挤条件，检验是否具有增量。':'从已有版本建立人工分支，原实验记录不变。'}</p></div></div>`:''}${lockHint()}<div class="field-grid">${field('假设名称','v.title',item.title,{full:true,disabled:locked})}${field('经济机制与可证伪解释','v.hypothesis',item.hypothesis,{type:'textarea',full:true,rows:4,disabled:locked})}${field('候选表达式','v.expression',item.expression,{type:'textarea',code:true,full:true,rows:2,disabled:locked})}${field('观察窗口（交易日）','v.window',item.window,{disabled:locked})}<label class="field"><span>预测目标</span><input value="下一交易日收益 · 正向 Rank IC" disabled></label></div><div class="actions">${btn('保存研究计划','save-version','primary',locked?'disabled':'')}${btn('让助手提出修改建议','assist','',locked?'disabled':'')}${btn('进入因子实现 →','go-F3','ghost')}</div>`,badge(item.saved?'已保存':'草稿',item.saved?'green':'amber'))+card('预先约定的检验规则','后续失败不能通过降低门槛获得通过。',`<div class="mini-stats"><div class="stat"><span>研发 / 独立验证 Rank IC</span><b>≥ 0.020</b></div><div class="stat"><span>与库内因子最大相似度</span><b>&lt; 0.80</b></div><div class="stat"><span>最多候选检验</span><b>${state.spent} / ${state.budget}</b></div></div><p class="subtle">示例规则还包括：有效观测 ≥ 120 天，覆盖率 ≥ 90%，最大回撤 ≤ 30%；完整比较清单必须可计算。真实门槛需按研究场景预先制定。</p><div class="link-row">${btn('查看完整授权与数据划分','policy','ghost small')}</div>`);
  if(state.stage==='F3') return versionBar()+card('因子代码','使用平台的因子计算接口；同一份代码可由人或 Agent 维护。',`${lockHint()}<div class="field-grid">${field('实现代码 · Python 示意','v.code',item.code,{type:'textarea',code:true,full:true,rows:11,disabled:locked})}</div><div class="actions">${btn('保存实现','save-version','primary',locked?'disabled':'')}${btn('检查代码（演示）','check-code')}${btn('让助手生成实现','assist','',locked?'disabled':'')}${btn('进入研发检验 →','go-F4','ghost')}</div>${item.checked?'<div class="hint success">示例检查完成：输出形状、字段依赖与未来数据检查已列入验证清单。本原型未执行 Python。</div>':'<div class="hint">代码、依赖和输入快照将绑定到每一次实验；修改后需要重新检验。</div>'}`,badge(item.checked?'检查记录已生成':'待检查',item.checked?'green':'amber'))+card('工具与依赖','人工与 Agent 共用相同工具入口。',`<div class="tool-chips"><span>因子代码编辑器</span><span>字段与算子目录</span><span>静态校验</span><span>计算引擎</span></div><p class="subtle">依赖字段：open、close、volume。时间口径：当日收盘后形成信号，下一交易日执行。</p>`);
  if(state.stage==='F4') return versionBar()+card('研发检验','固定输入运行检验；失败记录保留，并形成下一轮研究依据。',`<div class="field-grid"><label class="field"><span>研发区间</span><input value="2023-01-01 — 2024-12-31" disabled></label><label class="field"><span>数据与因子库快照</span><input value="${esc(state.dataVersion)} / 目录 L1" disabled></label><label class="field"><span>基准 / 分层</span><input value="沪深 300 / 5 组" disabled></label><label class="field"><span>交易成本</span><input value="佣金 3bp · 印花税 5bp · 滑点 1bp" disabled></label></div><div class="actions">${btn('运行研发检验（演示）','manual-run','primary',state.status==='running'||state.spent>=state.budget||['needs-data','needs-scope','review','complete','stopped'].includes(state.status)||!item.checked?'disabled':'')}${btn('让助手解释检验结果','explain')}${btn('查看全部实验','experiments','ghost')}</div>${!item.checked?'<p class="subtle">请先在因子实现环节生成检查记录。</p>':''}<p class="subtle">此原型返回固定场景报告，不计算当前表达式，也不代表真实投资表现。</p>`)+card('当前版本的检验记录',`${state.view} · 研究结果、相似度与失败原因`,experimentTable(state.experiments.filter(e=>e.version===state.view)));
  if(state.stage==='F5') { const pass=state.experiments.find(e=>e.version===state.view&&e.kind==='research'&&e.result==='pass'), validation=state.experiments.find(e=>e.version===state.view&&e.kind==='validation'); return versionBar()+card('独立验证','先冻结候选，再使用未参与迭代的数据验证一次。',`<div class="roadmap"><span class="${pass?'active':''}">研发检验达标</span><span class="${validation?'active':''}">候选版本冻结</span><span class="${validation?'active':''}">独立验证留证</span></div><div class="definition"><b>验证区间</b><span>2025-01-01 — 2025-12-31 · 示例封存区间</span><b>冻结对象</b><span>${state.view} · 表达式 / 代码 / 数据快照 / 参数 / 比较清单</span><b>失败处理</b><span>停止当前候选，记录结论；不反复查看此区间调参。</span></div><div class="hint ${pass?'':'warning'}">${pass?'当前候选具有完整的示例研发证据。独立验证结果将附在原候选上。':'当前版本尚无达标研发证据。你仍可查看本页和规则；暂不能发起独立验证。'}</div><div class="actions">${btn(validation?'验证已完成':'冻结并验证（演示）','manual-validate','primary',!pass||validation||state.status==='running'?'disabled':'')}${validation?btn('查看验证报告','report','',`data-id="${validation.id}"`):''}</div>`)+(validation?card('验证证据','样本外结果与研发结果分开保存。',experimentTable([validation])):''); }
  return versionBar()+card('因子资产与研究复核','只有证据完整的候选进入人工复核；其他结果作为研究记录留档。',`<div class="mini-stats"><div class="stat"><span>研究候选</span><b>${state.view}</b></div><div class="stat"><span>当前用途</span><b>研究用途</b></div><div class="stat"><span>复核状态</span><b>${state.view!==state.reviewVersion?'未提交':state.review==='approved'?'已通过（演示）':state.review==='pending'?'待人工复核':state.review==='rejected'?'已退回':'未提交'}</b></div></div><div class="field-grid">${field('研究说明 / 局限','note',state.note||'关注相对于已有反转因子的增量；样本与交易成本设定仍有局限，不直接构成实盘方案。',{type:'textarea',full:true,rows:3,disabled:state.review==='approved'})}</div><div class="actions">${btn('保存研究说明','save-note')}${btn(state.view!==state.reviewVersion||state.review==='none'?'提交研究复核（演示）':'查看复核包','review','primary')}</div><div class="hint">研究入库、公司共享准入与实盘授权是不同决策。此页不授予交易权限。</div>`)+card('候选证据包','每个报告都绑定当时的假设和代码，历史结果不会随页面编辑而改变。',experimentTable(state.experiments.filter(e=>e.version===state.view)));
}
function agentPanel() {
 const last=state.logs.at(-1), [st,,tone]=statusInfo();
 let body='';
 if(state.agentTab==='work') body=`<div class="agent-callout"><span class="badge ${tone}"><span class="dot ${state.status==='running'?'live':''}"></span>${st}</span><h4>${last?esc(last.title):'等待你的研究委托'}</h4><p>${last?esc(last.detail):'你可以手动完成各环节，也可以交给我连续推进。研究记录始终保留在左侧。'}</p></div><div class="agent-block"><label>当前分支</label><b>${state.active} · ${esc(active().title)}</b><p>已用检验 ${state.spent} / ${state.budget} 次${state.view!==state.active?` · 你正在查看 ${state.view}`:''}</p></div><div class="agent-block"><label>下一步</label><p>${esc(state.next)}</p></div><div class="agent-block"><label>最近工作记录 <small>演示事件</small></label>${state.logs.length?`<ol class="event-list">${state.logs.slice(-4).reverse().map(e=>`<li><b>${esc(e.title)}</b><p>${esc(e.detail)}</p><small>${e.stage} · ${e.time}</small></li>`).join('')}</ol>`:'<p class="subtle">运行后展示工具调用、结果、修订理由和产物链接。</p>'}</div><div class="link-row">${btn('完整记录','history','small ghost')}</div>`;
 if(state.agentTab==='chat') body=`<p class="subtle">与当前研究共享上下文 · 本原型使用预设回复</p><div class="chat-log">${state.messages.slice(-6).map(m=>`<div class="bubble ${m.who==='user'?'user':''}"><small>${m.who==='user'?'你':'因子研究助手'}</small><p>${esc(m.text)}</p></div>`).join('')}</div><div class="quick-prompts"><button data-action="explain">为什么返回假设？</button><button data-action="assist">帮我完善当前环节</button></div><form id="chat-form"><label class="field"><span>补充研究意见</span><textarea id="chat-input" placeholder="例如：先检查不同年份是否稳定" rows="3" required>${esc(state.chatDraft||'')}</textarea></label><button class="btn primary" type="submit">发送意见</button></form>`;
 if(state.agentTab==='tools') body=`<div class="agent-block"><label>当前环节的职责</label><b>${({F1:'识别研究机会，组织输入',F2:'提出假设，制定可证伪计划',F3:'实现候选，修复代码错误',F4:'运行检验，诊断与决定返工',F5:'冻结候选，形成独立证据',F6:'整理报告，提交人工复核'})[state.stage]}</b></div><div class="agent-block"><label>可调用工具</label><div class="tool-chips">${({F1:['因子库检索','数据目录','任务编辑'],F2:['表达式编辑','文献/证据检索','研究计划'],F3:['代码生成','静态校验','沙箱执行'],F4:['因子计算','IC / 分层分析','相关性去重','诊断报告'],F5:['候选冻结','独立验证','证据归档'],F6:['因子卡片','报告打包','复核申请']})[state.stage].map(t=>`<span>${t}</span>`).join('')}</div></div><div class="agent-block"><label>共享研究状态</label><p>同一任务、假设版本、数据快照和实验记录；跨步骤不丢失上下文。</p></div><div class="agent-block"><label>自主行动边界</label><p>可修订假设、实现和诊断；修改研究范围、门槛、数据授权或预算时必须暂停申请。</p></div>${btn('查看本次授权','policy','small')}`;
 return `<aside class="card agent-panel" aria-label="因子研究助手"><div class="agent-head"><span class="agent-mark">✧</span><div><h3>因子研究助手</h3><p>与当前研究共同工作</p></div></div><div class="agent-tabs"><button data-agent-tab="work" class="${state.agentTab==='work'?'active':''}">当前工作</button><button data-agent-tab="chat" class="${state.agentTab==='chat'?'active':''}">对话</button><button data-agent-tab="tools" class="${state.agentTab==='tools'?'active':''}">工具与权限</button></div><div class="agent-body">${body}</div><div class="agent-foot">所有行动与产物留在当前研究中</div></aside>`;
}
function experimentTable(rows) {
 if(!rows.length) return '<div class="empty"><b>这个版本还没有实验记录</b><p>运行检验后，报告、代码快照和判定依据会保存在这里。</p></div>';
 return `<div class="table-wrap"><table class="table"><thead><tr><th>实验 / 输入版本</th><th>检验类型</th><th>Rank IC</th><th>结论</th><th></th></tr></thead><tbody>${rows.map(e=>`<tr><td><b>${e.id}</b><small>${e.version} · ${e.data}</small></td><td>${e.kind==='validation'?'独立验证':'研发检验'}</td><td>${e.result==='incomplete'?'—':e.ic.toFixed(3)}</td><td>${badge(e.result==='pass'?'达标':e.result==='incomplete'?'证据不足':'未达标',e.result==='pass'?'green':'amber')}</td><td>${btn('报告 ↗','report','small ghost',`data-id="${e.id}"`)}</td></tr>`).join('')}</tbody></table></div>`;
}
const assets=[{id:'FAC-018',name:'短期价格反转',type:'复现基线',status:'研究可用',owner:'团队因子库'},{id:'FAC-042',name:'成交量变化',type:'量价因子',status:'研究可用',owner:'团队因子库'},{id:'FAC-067',name:'低波动率',type:'风险特征',status:'研究可用',owner:'团队因子库'}];
function library() {
 const rows=state.review==='approved'?[{id:'FAC-NEW',name:state.name,type:'本任务产物',status:'已通过（演示）',owner:state.active},...assets]:assets;
 return card('因子资产','既有资产随时可用；不必等待另一条研究任务。',`<label class="field"><span>搜索资产</span><input id="asset-search" placeholder="名称、分类或编号"></label><div class="table-wrap"><table class="table"><thead><tr><th>因子</th><th>分类</th><th>来源</th><th>状态</th><th></th></tr></thead><tbody id="asset-rows">${rows.map(a=>`<tr data-asset="${esc(a.name+a.type+a.id)}"><td><b>${a.name}</b><small>${a.id} · 示例资产</small></td><td>${a.type}</td><td>${a.owner}</td><td>${badge(a.status,'green')}</td><td>${btn('查看卡片','asset-detail','small',`data-id="${a.id}"`)}</td></tr>`).join('')}</tbody></table></div><p id="asset-empty" class="empty" hidden>没有匹配的示例资产。</p><div class="hint">使用已有因子时标记为复现或基线。新发现必须另做相似度与增量价值检查。</div>`);
}
function experimentsPage() {
 return `<div class="task-head"><div><span class="code">QF-026</span><h2>${esc(state.name)}</h2><p class="muted">任务、版本与证据在一个研究空间中连续积累。</p></div>${btn('返回工作台','workflow')}</div>`+card('研究版本',`${state.versions.length} 个版本 · 历史记录不覆盖`,state.versions.map(x=>`<div class="artifact"><span class="artifact-icon">${x.id}</span><div class="artifact-info"><b>${esc(x.title)}</b><small>${x.parent?`来源 ${x.parent} · `:''}${esc(x.owner)} · ${x.locked?'已有证据，保留原样':'可编辑草稿'}</small></div>${x.id===state.active?badge('Agent 分支','purple'):''}${btn('打开','open-version','small',`data-id="${x.id}"`)}</div>`).join(''))+card('全部实验','研发失败、工具异常和独立验证分别保留。',experimentTable(state.experiments))+card('操作与决策记录','展示可核查的行动依据和工具结果，不展示模型内部思维。',timeline());
}
function timeline() { return state.logs.length?`<ol class="event-list">${state.logs.slice().reverse().map(e=>`<li><b>${esc(e.title)}</b><p>${esc(e.detail)}</p><small>${e.time} · ${e.stage} · 场景事件</small></li>`).join('')}</ol>`:'<div class="empty">启动研究或进行人工操作后生成记录。</div>'; }
function stageTo(id, follow=false) { state.stage=id;state.page='workflow';state.follow=follow;render(); }
function work(id,next) { state.workStage=id;state.next=next; if(state.follow){state.stage=id;state.view=state.active;state.page='workflow';} }
function addVersion(owner, source=v(), improve=false) {
 const clone=JSON.parse(JSON.stringify(source));
 const item={...clone,id:`H${state.versions.length+1}`,parent:source.id,owner,locked:false,checked:false,saved:owner!=='人工分支'};
 if(improve) {item.title='成交拥挤条件下的偏离回补';item.hypothesis='仅凭开盘偏离的预测力不足。检验相对成交量较高时是否存在更强的情绪冲击及回补，其他范围保持不变。';item.expression='-ts_mean(open / delay(close, 1) - 1, 5) * rank(volume / ts_mean(volume, 20))';item.code='# H2 · 增加成交拥挤条件；表达式实现示意\ndef compute(data):\n    gap = data.open / data.close.shift(1) - 1\n    crowding = data.volume / data.volume.rolling(20).mean()\n    return -gap.rolling(5).mean() * crowding.rank(axis=1, pct=True)';}
 state.versions.push(item);return item;
}
function experiment(version,kind='research',result) {
 if(kind==='research'&&state.spent>=state.budget){state.status='stopped';state.next='达到检验上限。保留当前结论，可新建后续研究。';log('到达研究预算上限','停止新检验，不追加预算。');return null;}
 const item=v(version),pass=result==='pass'||(!result&&item.parent!==null);
 const e={id:`E${state.experiments.length+1}`,version,kind,result:result||(pass?'pass':'fail'),ic:result==='incomplete'?null:kind==='validation'?0.023:pass?0.026:0.008,similarity:result==='incomplete'?null:pass?0.62:0.71,coverage:result==='incomplete'?null:0.94,drawdown:result==='incomplete'?null:kind==='validation'?0.14:0.16,observations:result==='incomplete'?null:244,data:state.dataVersion,snapshot:JSON.parse(JSON.stringify(item))};
 state.experiments.push(e);item.locked=true;
 if(kind==='research') state.spent++;
 log(`${e.id} · ${kind==='validation'?'独立验证':'研发检验'}${e.result==='incomplete'?'证据不足':e.result==='pass'?'达标':'未达标'}`,e.result==='incomplete'?'volume 字段覆盖不足，停止计算，未生成有效指标。':`${version} · 示例 Rank IC ${e.ic.toFixed(3)}；${e.result==='pass'?'固定门槛与完整性检查通过。':'低于预设 0.020，进入诊断。'}`,kind==='validation'?'F5':'F4');
 if(e.result==='fail' && state.spent>=state.budget){state.status='stopped';state.next='未达门槛且达到本次上限，保留失败记录并停止。';log('到达研究预算上限','不再生成新候选，不放宽门槛。','F4');}
 return e;
}
function tick() {
 clearTimeout(timer);
 if(state.status!=='running')return;
 if(modal){schedule();return;}
 const i=state.cursor++;
 if(i===0){work('F1','检查已有资产和输入口径，确认本轮研究计划。');log('输入与已有资产已登记','绑定行情快照 D1、比较目录 L1；将已有反转因子作为对照。');}
 if(i===1){active().saved=true;work('F2','计划已保存，接下来编写因子实现。');log('研究计划已保存',`${state.active} · 预先固定日频范围、检验门槛与 ${state.budget} 次上限。`);}
 if(i===2){active().checked=true;work('F3','代码检查完成，运行第一次研发检验。');log('代码实现与检查已完成','生成因子实现，登记依赖字段和代码快照。');}
 if(i===3){work('F4','诊断预测能力，决定继续、返工或停止。');if(state.scenario==='data'&&!state.dataResolved){experiment(state.active,'research','incomplete');state.status=state.spent>=state.budget?'stopped':'needs-data';state.next='补齐 volume 字段并产生新数据快照后再检验。';log('数据条件不足，暂停研究','已生成数据请求 DR-01；不继续生成假设或计算无效指标。');}else experiment(state.active,'research','fail');}
 if(i===4){if(state.scenario==='scope'&&!state.scopeDecision){state.status='needs-scope';work('F2','等待你决定是否增加分钟数据；门槛不会自动变化。');log('范围外变更需要授权','建议分析开盘后分钟量价；当前任务只允许日频。');}else revise();}
 if(i===5){active().checked=true;work('F3','实现修订假设，并用相同研发规则重新检验。');log('修订实现已保存',`${state.active} 引入相对成交拥挤条件；原 H1 和 E1 仍可打开。`);}
 if(i===6){work('F4','研发达标后冻结当前候选，进入一次独立验证。');experiment(state.active,'research','pass');}
 if(i===7&&state.status==='running'){work('F5','独立验证通过后整理证据，交给人工复核。');experiment(state.active,'validation','pass');}
 if(i===8&&state.status==='running'){work('F6','等待独立复核；不会自动授予共享或交易权限。');state.status='review';state.review='pending';state.reviewVersion=state.active;log('研究复核包已提交','包含假设版本、两轮研发记录、独立验证、比较清单和局限。人工作出研究用途决定。');}
 render();schedule();
}
function revise(){const item=addVersion('Agent 修订',active(),true);state.active=item.id;if(state.follow)state.view=item.id;work('F2','修订假设后重做实现；保留旧版本和失败证据。');log(`返回假设环节 · ${item.parent} → ${item.id}`,'依据研发失败新增成交拥挤条件；未改变门槛、时间区间、成本或预算。');}
function schedule(){clearTimeout(timer);if(state.status==='running')timer=setTimeout(tick,3600);}
function start(){closeModal();state.authorized=true;state.status='running';state.follow=true;state.active=state.view;state.next='先检查任务、数据与已有资产。';log('研究委托已确认',`允许在约定范围内跨步骤修订，最多 ${state.budget} 次研发检验。`,'F1');render();tick();}
function pause(){clearTimeout(timer);state.status='paused';log('人工暂停研究','后续动作停止，已完成的版本与工具结果保留。');render();}
function openModal(title,body,footer='',wide=false,kind='info') {
 modal=kind;lastFocus=document.activeElement;
 $('#overlay').innerHTML=`<div class="modal-backdrop"><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header class="modal-header"><div><span class="eyebrow">FACTOR RESEARCH · DESIGN PREVIEW</span><h2 id="modal-title">${title}</h2></div><button class="modal-close" data-action="close" aria-label="关闭对话框">×</button></header><div class="modal-body">${body}</div>${footer?`<footer class="modal-footer">${footer}</footer>`:''}</section></div>`;
 $('.modal-close').focus();
}
function closeModal(){modal='';$('#overlay').innerHTML='';if(lastFocus?.isConnected)lastFocus.focus();}
function policyContent() {return `<p class="subtle">一次授权覆盖本任务内的连续研究，不需要每填写一个字段都审批。</p><div class="definition"><b>研究目标</b><span>${esc(state.goal)}</span><b>数据范围</b><span>${esc(state.universe)} · 日频 open / close / volume</span><b>研发 / 验证</b><span>2023–2024 用于研发；2025 为一次独立验证，验证反馈不得反复调参。</span><b>固定门槛</b><span>正向 Rank IC ≥ 0.020；有效观测 ≥ 120；覆盖 ≥ 90%；相似度 &lt; 0.80 且比较完整；最大回撤 ≤ 30%。</span><b>本次上限</b><span>${state.budget} 个研发候选检验，含首次与失败；不自动增加预算。</span></div><div class="split"><div class="hint success"><b>可以自主完成</b><p>修复实现、补做诊断、在 3 / 5 / 10 日窗口及成交拥挤机制内修订假设，调用已有工具并整理研究报告。</p></div><div class="hint warning"><b>必须停下申请</b><p>新增数据授权、扩大研究范围、修改门槛或预算；申请公司共享准入与真实交易。</p></div></div>`;}
function report(id) {
 const e=state.experiments.find(x=>x.id===id);if(!e)return;
 const points=Array.from({length:25},(_,i)=>({x:35+i*25,y:160-i*(e.result==='pass'?3.2:0.7)+Math.sin(i*1.6)*9,by:164-i*1.4+Math.sin(i*.9)*12}));
 const curve=points.map(p=>`${p.x},${p.y}`).join(' '),base=points.map(p=>`${p.x},${p.by}`).join(' ');
 const chart=e.result==='incomplete'?'<div class="empty"><b>没有有效计算结果</b><p>字段不足时不显示零值或伪造曲线。补齐数据后另开实验。</p></div>':`<div class="mini-stats"><div class="stat"><span>Rank IC</span><b>${e.ic.toFixed(3)}</b><small>预设 ≥ 0.020</small></div><div class="stat"><span>最大相似度</span><b>${e.similarity.toFixed(2)}</b><small>完整比较 · 示例</small></div><div class="stat"><span>最大回撤</span><b>${(e.drawdown*100).toFixed(1)}%</b><small>含示例成本口径</small></div></div><div class="row-flex"><h3>分层多头与基准净值</h3><span class="badge prototype">示例曲线 · 非计算结果</span></div><div class="legend"><span style="color:#794c9b">━ 因子最高组</span><span style="color:#9ba5b7">━ 沪深 300</span></div><svg class="chart" viewBox="0 0 680 215" role="img" aria-label="示例净值对比，鼠标悬停可查看数值"><g stroke="#eeeaf3">${[40,80,120,160,200].map(y=>`<line x1="35" y1="${y}" x2="650" y2="${y}"/>`).join('')}</g><g fill="#94899f" font-size="10"><text x="4" y="44">1.30</text><text x="4" y="124">1.10</text><text x="4" y="204">0.90</text><text x="35" y="212">期初</text><text x="610" y="212">期末</text></g><polyline points="${base}" fill="none" stroke="#9ba5b7" stroke-width="2"/><polyline points="${curve}" fill="none" stroke="#794c9b" stroke-width="2.5"/>${points.map((p,i)=>`<rect x="${p.x-12}" y="20" width="25" height="180" fill="transparent" data-chart-index="${i}" data-chart-factor="${(1+(160-p.y)/400).toFixed(3)}" data-chart-base="${(1+(160-p.by)/400).toFixed(3)}"/><circle cx="${p.x}" cy="${p.y}" r="3" fill="#794c9b" pointer-events="none"/>`).join('')}</svg><div class="chart-readout" id="chart-readout">将鼠标放在曲线上，查看示例净值对比。</div>`;
 openModal(`${e.id} · ${e.kind==='validation'?'独立验证':'研发检验'}报告`,`${badge('全部为固定场景数据','prototype')} ${badge(e.result==='pass'?'达标':e.result==='incomplete'?'证据不足':'未达标',e.result==='pass'?'green':'amber')}<p class="subtle">报告绑定 ${e.version} / ${e.data} / 比较目录 L1。指标与曲线用于讨论展示方式，不反映编辑后的表达式。</p>${chart}<h3>判定与下一步</h3><div class="hint ${e.result==='pass'?'success':'warning'}">${e.result==='pass'?(e.kind==='validation'?'独立验证示例通过，等待人工研究复核；不自动批准共享或实盘。':'研发示例达标，可冻结候选进入一次独立验证。'):e.result==='incomplete'?'补充字段与有效覆盖，形成新快照后重新检验，不把缺失值当作 0。':'Rank IC 0.008 低于预设 0.020。允许在原机制范围内另建假设版本，原门槛不变。'}</div><h3>输入快照 · ${e.version}</h3><div class="diff"><b>${esc(e.snapshot.title)}</b><p>${esc(e.snapshot.hypothesis)}</p><code>${esc(e.snapshot.expression)}</code></div><p class="subtle">正式版报告应包含分年稳定性、分层收益、换手成本、暴露、数据质量、相似度明细与完整计算来源。</p>`,btn('关闭','close')+btn('打开此假设版本','open-version','primary',`data-id="${e.version}"`),true,'report');
}
function reviewModal(){
 if(['approved','rejected'].includes(state.review)&&state.view===state.reviewVersion){openModal('已完成的研究复核（演示）',`<div class="hint">${state.review==='approved'?'已批准研究用途':'已退回并结束本轮'}</div><p>${esc(state.reviewNote)}</p><p class="subtle">保留此次意见；修改结论应使用新的复核记录。</p>`,btn('关闭','close'));return;}
 const id=state.view, val=state.experiments.find(e=>e.version===id&&e.kind==='validation'&&e.result==='pass');
 if(!val){openModal('研究复核尚未就绪','<div class="hint warning">当前版本缺少完整达标的独立验证证据，不能进入正式研究复核。研发失败仍可保存为研究记录。</div>'+experimentTable(state.experiments.filter(e=>e.version===id)),btn('关闭','close')+btn('查看独立验证','go-F5','primary'));return;}
 state.reviewVersion=id;
 openModal('独立复核视角 · 研究用途',`${badge('仅模拟角色与审批交互','prototype')}<p>研究员提交证据包，独立复核人查看假设、全部实验及研究局限。以下操作不会产生真实审批。</p><div class="definition"><b>候选</b><span>${id} · ${esc(v().title)}</span><b>证据</b><span>研发报告、完整比较清单、冻结输入、独立验证 ${val.id}</span><b>申请用途</b><span>团队研究资产；不含公司正式共享准入与交易授权</span></div><label class="field"><span>复核意见</span><textarea id="review-note" rows="3" placeholder="请写明研究价值、局限及后续关注项">证据链完整，可作为后续策略研究的候选输入；仍需检验组合中的增量与容量。</textarea></label><label class="check-row"><input id="review-check" type="checkbox"> 已检查版本、证据和局限（演示）</label>`,btn('返回研究','close')+btn('退回并结束本轮（演示）','reject-review')+btn('批准研究用途（演示）','approve-review','primary'),true,'review');
}
function assist() {
 const stage=state.stage;
 if(['F4','F5','F6'].includes(stage)){explain();return;}
 const disabled=state.status==='running'||(stage==='F1'&&state.authorized);
 const proposal=stage==='F1'?'补充与已有反转因子的增量比较，并明确 next-day 收益及固定数据范围。':stage==='F2'?'在开盘偏离的原假设上增加相对成交拥挤条件，检验情绪冲击机制；门槛与数据区间保持不变。':'按当前表达式生成日频计算示意；登记依赖并检查未来数据使用。';
 openModal('助手建议 · 等待采纳',`<p class="subtle">预设交互示例，尚未修改当前字段。</p><div class="diff"><b>当前内容 · ${state.view}</b><p>${esc(stage==='F1'?state.goal:stage==='F2'?v().hypothesis:v().code)}</p></div><div class="diff new"><b>建议修改</b><p>${proposal}</p></div><p class="subtle">${readonly()?'采纳时另建版本，不覆盖已有证据。':'采纳后可继续编辑，保存时形成当前草稿。'}${disabled?' Agent 正在工作，请先暂停或另开人工分支。':''}</p>`,btn('暂不采纳','close')+btn('采纳到当前研究','apply-assist','primary',disabled?'disabled':''),true,'assist');
}
function explain(){state.agentTab='chat';const e=state.experiments.at(-1);state.messages.push({who:'agent',text:e?`${e.id} 属于 ${e.version}。${e.result==='fail'?'预测能力没有达到预先约定的门槛，因此建议返回 F2 建立新假设，并保留失败记录。':e.result==='incomplete'?'字段证据不足，先修复数据，不能据此认定因子失败。':'当前示例证据达标，但仍由独立复核人决定研究用途。'} 此处展示行动依据与结果摘要，数值为场景预设。`:'当前尚无实验。开始委托后，我会把工具结果、下一步和返工理由记录到这项研究中。'});render();}
function resetScenario(scenario){clearTimeout(timer);state=fresh(scenario);closeModal();render();}
function action(a,el) {
 if(a==='close'){closeModal();return;}
 if(a.startsWith('go-')){closeModal();stageTo(a.slice(3));return;}
 if(['workflow','library','experiments'].includes(a)){closeModal();state.page=a;state.follow=false;render();return;}
 if(a==='delegate'){openModal('委托 Agent 完成这项研究',policyContent()+`<label class="field"><span>最多候选检验次数（含首次）</span><input id="budget-input" type="number" value="${state.budget}" min="1" max="12"></label><div class="hint">开始后可自主往返各环节，达到门槛送审，或在预算 / 证据 / 权限边界停止。本页仅播放交互场景。</div>`,btn('取消','close')+btn('确认授权并开始演示','start','primary'),true,'delegate');return;}
 if(a==='start'){if(!state.name.trim()||!state.goal.trim()){toast('请先补充研究名称和研究问题');return;}const b=Number($('#budget-input').value);if(!Number.isInteger(b)||b<1||b>12){toast('请输入 1–12 的整数上限');return;}state.budget=b;start();return;}
 if(a==='policy'){openModal('本次研究约定',policyContent(),btn('知道了','close'),true,'policy');return;}
 if(a==='pause'){pause();return;}
 if(a==='resume'){state.status='running';log('继续原研究',`沿 ${state.active} 继续，当前人工分支与字段不被覆盖。`);render();schedule();return;}
 if(a==='follow'){state.follow=true;state.stage=state.workStage;state.view=state.active;render();return;}
 if(a==='advance'){if(['running','paused'].includes(state.status)){const paused=state.status==='paused';state.status='running';tick();if(paused&&state.status==='running'){clearTimeout(timer);state.status='paused';render();}}return;}
 if(a==='reset'||a==='new-project'){openModal(a==='reset'?'重置演示场景':'新建研究任务',`<p>本原型一次预览一项任务。${a==='reset'?'重置':'新建'}会清除本标签页的演示编辑、实验和审批记录。</p><p>需要保留时，可先导出场景记录；正式产品的历史任务应独立保存。</p>`,btn('取消','close')+btn('导出当前记录','export')+btn(a==='reset'?'确认重置':'创建空白研究','reset-confirm','primary',`data-empty="${a==='new-project'?'yes':'no'}"`),false,'reset');return;}
 if(a==='reset-confirm'){const empty=el.dataset.empty==='yes';resetScenario(empty?'manual':state.scenario);if(empty){state.name='未命名因子研究';state.goal='';state.stage='F1';v().title='待补充研究假设';v().hypothesis='';v().expression='';v().code='';v().saved=false;render();}return;}
 if(a==='branch'){const parent=v();const item=addVersion('人工分支',parent);state.view=item.id;if(!state.authorized)state.active=item.id;state.follow=false;state.stage='F2';state.page='workflow';log(`人工建立分支 ${item.id}`,`来自 ${parent.id}；${state.authorized?`Agent 仍使用 ${state.active}，`:''}不会覆盖既有实验。`,'F2');render();toast(`已建立 ${item.id}，可以编辑`);return;}
 if(a==='open-version'){closeModal();state.view=el.dataset.id;stageTo('F2');return;}
 if(a==='save-task'){if(!state.name.trim()||!state.goal.trim()){toast('请填写研究名称和研究问题');return;}log('人工保存研究任务','研究范围与目标已记录。','F1');render();toast('研究任务已保存（原型）');return;}
 if(a==='save-version'){if(readonly())return;if(!['3','5','10'].includes(v().window.trim())){toast('本次研究约定只允许 3、5、10 日窗口');return;}if(!v().title.trim()||!v().hypothesis.trim()||!v().expression.trim()){toast('请补齐假设名称、经济机制和表达式');return;}v().saved=true;log(`保存 ${state.view}`,`人工保存 ${state.stage} 草稿，尚未形成新的计算证据。`,state.stage);render();toast('当前草稿已保存');return;}
 if(a==='check-code'){if(!v().code.trim()){toast('请先补充实现代码');return;}v().checked=true;log(`${state.view} 代码检查示例`,'已生成交互示例检查记录，未执行或真实校验 Python。','F3');render();return;}
 if(a==='manual-run'){if(!v().checked||state.status==='running')return;if(!state.authorized)state.active=state.view;experiment(state.view);state.workStage='F4';state.next='根据研发证据决定修订假设或继续验证。';render();return;}
 if(a==='manual-validate'){const evidence=state.experiments.find(e=>e.version===state.view&&e.kind==='research'&&e.result==='pass');if(!evidence)return;if(!state.authorized)state.active=state.view;experiment(state.view,'validation','pass');state.review='pending';state.reviewVersion=state.view;state.status='review';state.workStage='F6';state.next='研究证据包等待人工复核。';render();return;}
 if(a==='save-note'){log('保存研究说明','研究局限与用途说明已记录。','F6');render();toast('说明已保存');return;}
 if(a==='report'){report(el.dataset.id);return;}
 if(a==='history'){openModal('版本与研究记录',`<div class="pill-list">${state.versions.map(x=>`<span>${x.id}${x.parent?` ← ${x.parent}`:''} · ${esc(x.owner)}</span>`).join('')}</div>${timeline()}`,btn('关闭','close')+btn('导出场景记录','export'),true,'history');return;}
 if(a==='review-active'){state.view=state.reviewVersion||state.active;reviewModal();return;}
 if(a==='review'){reviewModal();return;}
 if(a==='approve-review'||a==='reject-review'){if(!$('#review-check').checked||!$('#review-note').value.trim()){toast('请填写意见，并确认已检查证据');return;}state.reviewNote=$('#review-note').value;state.review=a==='approve-review'?'approved':'rejected';state.status=a==='approve-review'?'complete':'stopped';state.active=state.reviewVersion;log(a==='approve-review'?'人工研究复核通过（演示）':'人工复核退回（演示）',state.reviewNote,'F6');closeModal();render();toast('已记录原型交互；没有真实审批');return;}
 if(a==='assist'){assist();return;}
 if(a==='apply-assist'){const s=state.stage;let item=v();if(s==='F1')state.goal+=' 明确下一交易日收益目标，并检验相对已有因子的增量。';else{if(readonly()){item=addVersion('人工采纳助手建议');state.view=item.id;state.follow=false;}if(s==='F2'){item.hypothesis='在相对成交量较高时，开盘偏离可能包含更强的情绪冲击与回补信息；检验其对已有反转因子的增量。';item.expression='-ts_mean(open / delay(close, 1) - 1, 5) * rank(volume / ts_mean(volume, 20))';item.title='成交拥挤条件下的偏离回补';}else item.code=item.expression.includes('volume')?'# 成交拥挤回补实现示意；本原型未执行\ndef compute(data):\n    gap = data.open / data.close.shift(1) - 1\n    crowding = data.volume / data.volume.rolling(20).mean()\n    return -gap.rolling(5).mean() * crowding.rank(axis=1, pct=True)':'# 依据当前表达式的实现示意\n# 正式版由工具生成并验证，当前原型未执行\ndef compute(data):\n    gap = data.open / data.close.shift(1) - 1\n    return -gap.rolling(5).mean()';item.saved=false;item.checked=false;}log('已采纳助手建议','先写入草稿，再由研究工具形成新的验证证据。',s);closeModal();render();return;}
 if(a==='explain'){explain();return;}
 if(a==='data-request'){openModal('DR-01 · 数据补充请求','<div class="hint warning">volume 字段覆盖不足，当前实验无有效指标。</div><div class="definition"><b>所需输入</b><span>固定股票范围与研发区间的成交量字段、质量报告</span><b>处理方式</b><span>向数据资源模块发起补充请求；完成后登记新快照 D2，旧快照和失败实验保持不变。</span></div><p class="subtle">下面按钮只模拟收到数据回执，不实际采集或变更数据库。</p>',btn('继续等待','close')+btn('模拟数据已补齐','data-resolved','primary'),false,'data');return;}
 if(a==='data-resolved'){state.dataVersion='行情快照 D2';state.dataResolved=true;state.next='D2 已就绪，重新检验原候选并保留旧实验。';state.status='running';state.cursor=3;log('收到数据补充回执（演示）','D2 通过字段检查，旧 E1 与 D1 保留；重新检验同一假设。','F4');closeModal();render();schedule();return;}
 if(a==='scope-request'){openModal('变更请求 · 引入分钟数据','<div class="split"><div class="diff"><b>当前授权</b><p>日频量价 · 固定快照 · 固定检验上限</p></div><div class="diff new"><b>建议后续研究</b><p>开盘后 30 分钟的量价结构 · 需分钟数据与新评测计划</p></div></div><p>这是范围变更，不能在原任务里悄悄换数据后继续。你可以要求 Agent 保持日频继续，或结束本轮并为分钟研究建立后续计划。</p>',btn('暂不决定','close')+btn('建立后续研究计划','scope-new')+btn('保持日频，继续研究','scope-keep','primary'),true,'scope');return;}
 if(a==='scope-keep'){state.scopeDecision='keep';state.status='running';log('人工保持原授权','拒绝扩展分钟数据，要求在原日频范围内寻找修改。','F2');revise();closeModal();render();schedule();return;}
 if(a==='scope-new'){state.status='stopped';state.followup='开盘后分钟量价研究 · 待数据授权与新计划';state.next='当前任务留档，后续分钟研究等待新计划与数据授权。';log('建立后续研究计划（演示）',state.followup,'F2');closeModal();render();return;}
 if(a==='asset-detail'){const a=assets.find(x=>x.id===el.dataset.id)||{name:state.name,id:'FAC-NEW',type:'本任务产物'};openModal(`${a.name} · 资产卡片`,`${badge('示例资产','prototype')}<div class="definition"><b>编号</b><span>${a.id}</span><b>类型</b><span>${a.type}</span><b>可用内容</b><span>因子定义、版本、输入口径、检验报告与使用限制</span><b>研究使用</b><span>可作为基线或组合输入；复现已有因子不能标记为新因子发现。</span></div><p class="subtle">本轮原型重点评审因子研究交互；真实资产详情继续由平台因子库提供。</p>`,btn('关闭','close'));return;}
 if(a==='export'){const blob=new Blob([JSON.stringify({prototype:true,notice:'交互原型场景记录，非真实研究或审批',state},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='factor-v4-design-scenario.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出原型场景记录');}
}
document.addEventListener('click',event=>{
 const el=event.target.closest('button');if(!el||el.disabled)return;
 if(el.dataset.page){state.page=el.dataset.page;state.follow=false;render();return;}
 if(el.dataset.stage){stageTo(el.dataset.stage);return;}
 if(el.dataset.agentTab){state.agentTab=el.dataset.agentTab;render();return;}
 if(el.dataset.action==='switch-scenario'){resetScenario(el.dataset.scenario);return;}
 if(el.dataset.action)action(el.dataset.action,el);
});
document.addEventListener('input',event=>{
 const el=event.target;
 if(el.dataset.bind){const key=el.dataset.bind;if(key.startsWith('v.')){if(readonly())return;v()[key.slice(2)]=el.value;v().saved=false;v().checked=false;}else state[key]=el.value;persist();}
 if(el.id==='chat-input'){state.chatDraft=el.value;persist();}
 if(el.id==='asset-search'){const query=el.value.trim().toLowerCase();let visible=0;document.querySelectorAll('[data-asset]').forEach(row=>{row.hidden=!row.dataset.asset.toLowerCase().includes(query);if(!row.hidden)visible++;});$('#asset-empty').hidden=visible>0;}
});
document.addEventListener('change',event=>{
 if(event.target.id==='version'){state.view=event.target.value;state.follow=false;render();}
 if(event.target.id==='scenario'){const selected=event.target.value;event.target.value=state.scenario;openModal('切换演示场景','<p>切换后将重置本标签页的场景任务。可以先导出当前研究记录。</p>',btn('取消','close')+btn('导出记录','export')+btn('确认切换','switch-scenario','primary',`data-scenario="${selected}"`),false,'switch');}
});
document.addEventListener('submit',event=>{
 if(event.target.id!=='chat-form')return;event.preventDefault();const input=$('#chat-input'),message=input.value.trim();if(!message)return;
 state.chatDraft='';state.messages.push({who:'user',text:message},{who:'agent',text:'已将意见附到这项研究。正式产品会由研究 Agent 判断是否需要返工或请求授权；此原型不连接模型，不会假装理解并执行任意指令。你可用“帮我完善当前环节”预览建议与采纳。'});log('收到人工补充意见',message,state.stage);render();
});
document.addEventListener('pointerover',event=>{const p=event.target.closest('[data-chart-index]');if(p&&$('#chart-readout'))$('#chart-readout').textContent=`示例观测 ${Number(p.dataset.chartIndex)+1} / 25 · 因子最高组 ${p.dataset.chartFactor} · 沪深 300 ${p.dataset.chartBase}`;});
document.addEventListener('keydown',event=>{
 if(!modal)return;if(event.key==='Escape'){closeModal();return;}
 if(event.key==='Tab'){const nodes=[...$('.modal').querySelectorAll('button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),a[href]')];const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
});
window.addEventListener('hashchange',()=>{if(location.hash==='#workflow'){state.page='workflow';render();}});
window.addEventListener('pagehide',()=>{clearTimeout(timer);persist();});
render();
if(state.status==='running')schedule();
