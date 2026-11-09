/* CR-080 design scenarios. No API calls, model requests, approvals or persistent writes. */
(() => {
  'use strict';
  L = 'zh';
  const root = document.getElementById('method-preview');
  const dlg = document.getElementById('pm-dialog');
  const scenarios = {
    a: { topic:'T1',title:'成交拥挤与短期反转',run:'样例运行 A',method:'研究决策与专职单元',version:'factor-current@1.0',k:2,budget:8,current:'Ha',
      actors:['研究决策','假设研究','实现生成','计算服务'],
      status:'等待 Ha 的研发检验回执',next:'计算结束后，研究方法依据实际证据决定修订、开分支或停止。',
      nodes:[{id:'H1',parent:null,title:'拥挤交易后的短期反转',state:'已检验 · 保留记录',trial:'E1',definition:'hypothesis:H1@1 / factor:H1@1',reason:'初始假设：价格短期超调可能在随后回补。',change:'初始版本',result:'样例：研发门槛未达标，存在极端值影响。',code:'反转信号 × 成交拥挤条件\n示意定义，非可执行代码'},
      {id:'Ha',parent:'H1',title:'削弱极端换手的影响',state:'等待研发检验',trial:'E2',definition:'hypothesis:Ha@1 / factor:Ha@1',reason:'依据 E1 的失败证据调整极端值处理，保持原研究目标。',change:'从 H1 固定产物派生；增加稳健变换。',result:'样例：已提交计算，暂无结果。',code:'稳健变换(反转信号 × 成交拥挤条件)\n示意定义，非可执行代码'}],
      events:[{time:'09:41',actor:'计算服务',kind:'平台证据',node:'H1',text:'E1 完成，报告记录实际阻断与输入版本。',evidence:'E1'},
      {time:'09:42',actor:'研究决策',kind:'研究提案',node:'Ha',text:'引用 E1，选择从 H1 派生修订，而非重复检验同一定义。'},
      {time:'09:43',actor:'假设研究 → 实现生成',kind:'产物',node:'Ha',text:'保存 Ha 的新假设与实现；父版本和变化说明可追溯。'},
      {time:'09:44',actor:'计算服务',kind:'等待',node:'Ha',text:'E2 已预留预算并提交。尚无回执，不显示通过指标。',evidence:'E2'}]},
    b: {topic:'T2',title:'成交拥挤与短期反转',run:'样例运行 B',method:'候选树搜索',version:'factor-search@0.1',k:3,budget:8,current:'Hb',
      actors:['研究规划','候选实现 A','候选实现 B','证据分析','计算服务'],
      status:'等待 Hb 的研发检验回执',next:'规划单元比较已有分支证据，选择下一次研究动作；不会因为增加参与者而增加页面。',
      nodes:[{id:'H1',parent:null,title:'拥挤交易后的短期反转',state:'已检验 · 保留记录',trial:'E1',definition:'hypothesis:H1@1 / factor:H1@1',reason:'初始假设与授权范围固定在本次运行。',change:'初始版本',result:'样例：研发门槛未达标，存在极端值影响。',code:'反转信号 × 成交拥挤条件\n示意定义，非可执行代码'},
      {id:'Ha',parent:'H1',title:'稳健化换手条件',state:'停止此分支',trial:'E2',definition:'hypothesis:Ha@1 / factor:Ha@1',reason:'候选实现 A 尝试稳定极端值的影响。',change:'从 H1 固定产物派生；稳健变换。',result:'样例：与已有参考重复，保留报告并停止此分支。',code:'稳健变换(反转信号 × 成交拥挤条件)\n示意定义，非可执行代码'},
      {id:'Hb',parent:'H1',title:'分离上涨与下跌时的拥挤效应',state:'等待研发检验',trial:'E3',definition:'hypothesis:Hb@1 / factor:Hb@1',reason:'证据分析建议检查拥挤效应的非对称性，仍在原授权内。',change:'从 H1 派生另一条假设；不覆盖 Ha 或 E2。',result:'样例：已提交计算，暂无结果。',code:'分方向构造拥挤反转信号\n示意定义，非可执行代码'}],
      events:[{time:'10:12',actor:'证据分析',kind:'研究解释',node:'Ha',text:'读取 E1、E2 的绑定证据，区分研发未达标与定义重复。',evidence:'E2'},
      {time:'10:13',actor:'研究规划',kind:'研究提案',node:'Hb',text:'停止 Ha，从 H1 固定版本生成不同机制的 Hb。'},
      {time:'10:14',actor:'候选实现 B',kind:'产物',node:'Hb',text:'保存新假设与受限实现，引用 H1 版本并记录变化。'},
      {time:'10:15',actor:'计算服务',kind:'等待',node:'Hb',text:'平台校验权限、定义和预算后提交 E3，参与者不能自行填写通过结果。',evidence:'E3'}]}
  };
  const ui={which:'a',selected:{a:'Ha',b:'Hb'},paused:{a:false,b:false},notes:{a:'',b:''},open:false,message:''};
  const E=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const current=()=>scenarios[ui.which];
  function tree(parent=null){const s=current();return s.nodes.filter(n=>n.parent===parent).map(n=>`<div class="branch-wrap"><button type="button" class="branch${ui.selected[ui.which]===n.id?' sel':''}" data-pm="node" data-id="${E(n.id)}" aria-pressed="${ui.selected[ui.which]===n.id}"><span class="bh"><span class="hid">${E(n.id)}</span><span class="bt">${E(n.title)}</span></span><span class="steps"><span class="chip">${E(n.trial)}</span><span class="by">${E(n.state)}</span></span><span class="desc">${E(n.change)}</span></button>${s.nodes.some(x=>x.parent===n.id)?`<div class="children">${tree(n.id)}</div>`:''}</div>`).join('');}
  function render(){const s=current(),n=s.nodes.find(x=>x.id===ui.selected[ui.which]);
    document.getElementById('sidebar').innerHTML=SV.sidebar('factor');
    root.innerHTML=`<div class="page-head"><div><span class="eyebrow">FACTOR FACTORY</span><h1>因子工厂</h1><p>观察研究、核验证据，在需要时介入。</p></div><a class="btn small" href="factor.html">返回完整 V5 原型</a></div>
    <div class="pm-banner"><span><b>CR-080 设计预览 · 场景数据</b>　不连接真实研究服务。选择的是两个独立样例运行，不能热切换已有运行的方法。</span><a href="docs/机构量化V5-研究方法模块化与界面契约.md">查看设计规格 ↗</a></div>
    <nav class="pm-tabs" aria-label="因子模块视图"><a class="active" aria-current="page" href="factor-methods.html">研究运行</a><a href="factor.html#wb">人工研究</a><a href="factor.html#review">审查</a><a href="factor.html#lib">因子库</a><a href="factor.html#caps">能力与评测</a></nav>
    <div class="pm-run-selector" aria-label="独立样例运行">${Object.entries(scenarios).map(([id,d])=>`<button class="topic${ui.which===id?' sel':''}" type="button" data-pm="run" data-id="${id}" aria-pressed="${ui.which===id}"><span class="top"><span class="tid">${d.topic} · ${d.run}</span><span class="badge purple">${E(d.method)}</span></span><h3>${E(d.title)}</h3><p>固定方法 ${E(d.version)} · ${d.nodes.length} 条研究分支</p></button>`).join('')}</div>
    <div class="sys"><div class="sys-state"><span class="ico">${ui.paused[ui.which]?'Ⅱ':'◷'}</span><div><b>${ui.paused[ui.which]?'已暂停领取新动作（样例）':E(s.status)}</b><small>样例运行状态 · 实际系统以服务端事件为准</small></div></div><div class="kpis"><div class="kpi"><span>已记入 K</span><b>${s.k-1}</b></div><div class="kpi"><span>在途预留</span><b>1</b></div><div class="kpi"><span>授权试验上限</span><b>${s.budget}</b></div></div><button class="btn small" data-pm="pause">${ui.paused[ui.which]?'恢复样例':'暂停样例'}</button></div>
    <div class="pm-columns"><div class="pm-stack"><section class="pm-card"><div class="pm-row"><h2>${s.topic} · 研究树</h2><span class="badge">日频研究 · 样例数据视图</span></div><div class="pm-subtitle">假设与实现的演变；点选节点查看对应版本和试验。</div><div class="tree pm-tree">${tree()}</div><div class="pm-method"><span>本次运行的方法</span><b>${E(s.version)}</b><button class="text-btn" data-pm="method">查看组成与版本</button></div></section>
    <details class="pm-card pm-execution" ${ui.open?'open':''}><summary>执行详情 <small>${s.actors.length} 类参与者 · 最近 ${s.events.length} 条样例事件</small></summary><p class="pm-subtitle pm-spaced">${E(s.next)}</p><div class="pm-participants">${s.actors.map(a=>`<span>${E(a)}</span>`).join('')}</div><ol class="pm-event-list">${s.events.map(e=>`<li class="pm-event"><time>${e.time}</time><div><div class="pm-row"><b>${E(e.actor)}</b><span class="badge">${E(e.kind)}</span></div><p>${E(e.text)}</p><div class="actions"><button class="text-btn" data-pm="node" data-id="${E(e.node)}">定位 ${E(e.node)}</button>${e.evidence?`<button class="text-btn" data-pm="evidence" data-id="${E(e.evidence)}">查看 ${E(e.evidence)} 证据</button>`:''}</div></div></li>`).join('')}</ol></details></div>
    <div class="pm-stack"><section class="pm-card pm-detail" aria-label="分支详情"><span class="pm-label">选中分支 · ${E(n.id)}</span><h2>${E(n.title)}</h2><p>${E(n.reason)}</p><dl class="pm-facts"><dt>固定产物</dt><dd>${E(n.definition)}</dd><dt>父版本</dt><dd>${n.parent?E(n.parent)+' · 固定版本 1':'初始假设'}</dd><dt>试验</dt><dd>${E(n.trial)} · ${E(n.state)}</dd><dt>变化说明</dt><dd>${E(n.change)}</dd></dl><pre class="pm-code">${E(n.code)}</pre><p>${E(n.result)}</p><div class="actions pm-spaced"><button class="btn small" data-pm="evidence" data-id="${E(n.trial)}">查看试验证据</button><a class="btn small" href="factor.html#wb">人工研究原型 ↗</a></div></section>
    <section class="pm-card pm-note"><h2>给研究意见</h2><p class="pm-subtitle">意见附在当前课题，供下一次决策参考；不会改写冻结证据或研究门槛。</p><label for="pm-opinion">${s.topic} · 补充意见（仅本页样例）</label><textarea id="pm-opinion" placeholder="例如：请比较现有两个分支的重复风险，引用对应的试验证据。">${E(ui.notes[ui.which])}</textarea><button class="btn small" data-pm="note">记录样例意见</button><div class="pm-message" role="status">${E(ui.message)}</div></section></div></div>
    <div class="pm-footer">研究树记录成果关系；执行详情记录 Agent 与工具协作。方法升级后，课题、试验、证据和审批入口保持一致。</div>`;
    root.querySelector('.pm-execution').addEventListener('toggle',e=>{ui.open=e.target.open;});
    root.querySelector('#pm-opinion').addEventListener('input',e=>{ui.notes[ui.which]=e.target.value;});
  }
  function modal(title,body){dlg.innerHTML=`<h2 id="pm-dialog-title">${E(title)}</h2>${body}<div class="pm-close"><button class="btn primary" data-pm="close">关闭</button></div>`;dlg.showModal();}
  document.addEventListener('click',e=>{const b=e.target.closest('[data-pm]');if(!b)return;const a=b.dataset.pm,s=current();
    if(a==='run'){ui.which=b.dataset.id;ui.message='';render();}
    if(a==='node'){ui.selected[ui.which]=b.dataset.id;render();}
    if(a==='pause'){ui.paused[ui.which]=!ui.paused[ui.which];ui.message='样例状态已更新；没有暂停或恢复真实任务，在途记录保留。';render();}
    if(a==='note'){ui.message=ui.notes[ui.which].trim()?'样例意见已记录于本页，未发送至研究系统。':'请先填写补充意见。';root.querySelector('[role="status"]').textContent=ui.message;}
    if(a==='method'){modal('本次运行的研究方法',`<p>只读版本身份。修改默认方法不会改变当前运行；迁移另建运行并保留课题台账与预算。</p><dl class="pm-facts"><dt>样例运行</dt><dd>${s.run} · ${s.topic}</dd><dt>固定版本</dt><dd>${E(s.version)}</dd><dt>参与者</dt><dd>${s.actors.map(E).join('、')}</dd><dt>平台职责</dt><dd>授权与预算、工具执行、证据留存、独立验证与人工准入</dd><dt>输入</dt><dd>固定授权、研发证据、所选父版本、预算和用户意见</dd><dt>输出</dt><dd>假设、实现、受控试验请求、候选建议和工作事件</dd></dl><p>这是契约交互样例，不表示第二种研究算法已开发或已通过效果评测。</p>`);}
    if(a==='evidence'){const n=s.nodes.find(x=>x.trial===b.dataset.id);modal(`${n.trial} · 试验证据（样例）`,`<p>${E(n.result)}</p><dl class="pm-facts"><dt>所属对象</dt><dd>${s.topic} / ${n.id} / ${n.trial}</dd><dt>固定产物</dt><dd>${E(n.definition)}</dd><dt>来源方法</dt><dd>${E(s.version)}</dd><dt>计量状态</dt><dd>${n.id===s.current?'已预留一次额度，尚未落账；不显示虚构指标。':'已落账一次；历史结果不可覆盖。'}</dd><dt>真实报告</dt><dd>本附件没有真实计算报告，正式页面应链接平台计算证据。</dd><dt>封存与准入</dt><dd>未提交独立验证，不能申请入库。</dd></dl>`);}
    if(a==='close')dlg.close();
  });
  render();
})();
