'use strict';
/* CR-083 + CR-099 + CR-102 design only. No fetch, model calls, compute, or real approvals. */
(() => {
  const q = s => document.querySelector(s);
  const safe = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stages = [
    ['研究准备','研究准备 Agent','明确方向与可用数据'],
    ['因子研发','因子研发 Agent','生成、检验与迭代'],
    ['独立验证','独立复核 Agent','冻结候选，核验结果'],
    ['审批入库','成果管理 Agent · 人工审批','审查证据，登记资产']
  ];
  const status = {running:['研发中','purple'],error:['运行异常','red'],waiting:['等待计算服务','amber'],review:['待审批','amber'],admitted:['已入库','green'],returned:['待补证','amber'],rejected:['已驳回',''],ended:['未达标，已结束',''],draft:['待启动',''],queued:['排队中','purple'],paused:['已暂停','']};
  const tasks = [
    {id:'A',name:'低换手条件下的价格偏离',state:'running',step:1,k:2,max:8,version:3,direction:'量价关系',goal:'研究日频价格偏离与成交活跃度的关系，控制无效换手。',note:''},
    {id:'B',name:'波动收缩后的价格修复',state:'error',step:0,k:0,max:8,version:1,direction:'风险与波动',goal:'寻找日频波动收缩后的价格修复特征。',note:''},
    {id:'C',name:'无条件短期价格反转',state:'ended',step:1,k:2,max:8,version:2,direction:'量价关系',goal:'检验无条件短期价格反转是否提供稳定的方向信息。',note:'',stopReason:'两次研发检验未支持原假设，Agent 决定结束这个方向'}
  ];
  let selected='A', viewing=1, tab=['tasks','review','library'].includes(location.hash.slice(1))?location.hash.slice(1):'tasks', role='researcher', taskFilter='recent', taskText='', category='all', query='', tags=[], availability='all', sort='name', page=1, toastTimer, serial=0;
  let autoState='researching', autoDirection='优先研究量价关系，避免重复尝试没有新增依据的方向。';
  tasks[0].origin='system'; tasks[0].reason='先前无条件短期反转未达到研发要求；这次检验成交活跃度是否提供新的条件信息。';
  tasks[0].difference='加入成交活跃度条件，保持研发口径，检验其增量；尚未证明有效。'; tasks[0].experience='C'; tasks[2].origin='system'; tasks[0].familyK=4; tasks[2].familyK=4; tasks[2].hypothesis='近期价格偏离本身可能在下一交易日回补；在已记录范围内检验无条件反转。'; tasks[2].implementation='-rank(close / close.shift(5) - 1)';
  const categories=["动量因子", "技术复合因子", "反转因子", "Beta因子", "区间与通道因子", "流动性因子", "资金流与量能因子", "量价关系因子", "日内结构因子", "波动率因子", "估值因子", "风险分布因子"];
  const library=[
    {code:'F-001',name:'短期价格反转',cat:'反转因子',tags:['日频','价格'],state:'可研究',description:'衡量近期价格变动的反转特征。',origin:'公司基础因子目录',report:'参考报告'},
    {code:'F-002',name:'成交活跃度变化',cat:'流动性因子',tags:['日频','量价'],state:'可研究',description:'成交活跃度相对历史水平的变化。',origin:'公司基础因子目录',report:'参考报告'},
    {code:'F-003',name:'中期价格动量',cat:'动量因子',tags:['日频','价格'],state:'可研究',description:'中期价格趋势强弱。',origin:'公司基础因子目录',report:'参考报告'},
    {code:'F-004',name:'历史收益波动率',cat:'波动率因子',tags:['日频','风险'],state:'可研究',description:'历史收益率的离散程度。',origin:'公司基础因子目录',report:'参考报告'},
    {code:'F-005',name:'账面市值比',cat:'估值因子',tags:['基本面','价值'],state:'可研究',description:'账面价值相对于市场价值的比例。',origin:'公司基础因子目录',report:'参考报告'},
    {code:'F-006',name:'收益分布偏度',cat:'风险分布因子',tags:['日频','风险'],state:'可研究',description:'历史收益分布的不对称程度。',origin:'公司基础因子目录',report:'参考报告'},
    {code:'F-007',name:'量价偏离旧版本',cat:'量价关系因子',tags:['日频','量价'],state:'暂停使用',description:'保留历史研究引用，不用于新研究。',origin:'机构研究成果',report:'历史报告'}
  ];
  const current=()=>tasks.find(x=>x.id===selected);
  const badge=(state)=>{const s=status[state]||[state,''];return '<span class="badge '+s[1]+'">'+safe(s[0])+'</span>';};
  const editActions=new Set(['new','manual','takeover','pause','resume','opinion','edit-prep','request-scope','improve','return-agent','confirm-return','feedback','auto-settings','auto-pause','auto-reconsider']);
  const btn=(label,action,value='',cls='')=>'<button type="button" class="btn '+cls+'" data-action="'+action+'" data-value="'+safe(value)+'"'+(role==='reviewer'&&editActions.has(action)?' disabled title="独立复核人只读研究内容"':'')+'>'+label+'</button>';
  const pill=x=>'<span class="ff-pill">'+safe(x)+'</span>';
  const scope=()=>'<dl class="ff-kv"><dt>数据频率</dt><dd>日频</dd><dt>研究范围</dt><dd>中证500 · 已授权行情字段</dd><dt>数据版本</dt><dd>任务启动时固定，报告可追溯</dd><dt>研发区间</dt><dd>2024-01-02 — 2025-12-31（样例）</dd><dt>试验上限</dt><dd>'+current().max+' 次，历史消耗保留</dd>'+(current().familyK?'<dt>相关研究累计</dt><dd>'+current().familyK+' 次，含来源研究；不因新建任务清零</dd>':'')+'<dt>用途</dt><dd>因子研究，不涉及实盘交易</dd></dl>';
  function draw(){
    q('#sidebar').innerHTML=SV.sidebar('factor');
    const nav=q('#sidebar a[aria-current="page"]'); if(nav) nav.href='factor-factory.html';
    q('#factory').innerHTML='<div class="ff-preview"><span>设计预览 · 场景数据，不连接真实系统</span><div class="actions"><label>任务场景 <select id="preview-state" aria-label="设计预览场景">'+[['running','研发中'],['paused','人工接手'],['queued','排队中'],['ended','未达标结束'],['waiting','等待验证'],['review','待审批'],['admitted','已入库']].map(([v,n])=>'<option value="'+v+'"'+(tasks.find(x=>x.id==='A').state===v?' selected':'')+'>'+n+'</option>').join('')+'</select></label><label>自主研究 <select id="preview-autonomy" aria-label="自主研究设计场景">'+[['researching','已开启'],['off','已关闭'],['waiting','等待机会'],['error','选题异常']].map(([v,n])=>'<option value="'+v+'"'+(autoState===v?' selected':'')+'>'+n+'</option>').join('')+'</select></label><label>预览身份 <select id="preview-role" aria-label="设计预览身份"><option value="researcher"'+(role==='researcher'?' selected':'')+'>研究员</option><option value="reviewer"'+(role==='reviewer'?' selected':'')+'>独立复核人</option></select></label></div></div>'+
      '<div class="page-head"><div><span class="eyebrow">FACTOR RESEARCH</span><h1>因子工厂</h1><p>挖掘、验证和积累可复用的因子。</p></div><div class="actions">'+btn('人工研究','manual','','')+btn('＋ 启动挖掘','new','','primary')+'</div></div>'+
      '<nav class="tabs" aria-label="因子工厂导航">'+[['tasks','挖掘任务'],['review','待审批'],['library','因子库']].map(([v,n])=>'<button data-action="tab" data-value="'+v+'" class="'+(tab===v?'active':'')+'"'+(tab===v?' aria-current="page"':'')+'>'+n+(v==='review'&&tasks.some(x=>x.state==='review')?' <span class="count">1</span>':'')+'</button>').join('')+'</nav><div id="ff-content">'+(tab==='tasks'?taskPage():tab==='review'?reviewPage():libraryPage())+'</div>';
  }
  function taskPage(){
    const filtered=tasks.filter(x=>(taskFilter==='all'||taskFilter==='recent'&&!['ended','rejected','admitted'].includes(x.state)||taskFilter===x.state)&&x.name.includes(taskText));
    return autonomyBar()+'<div class="ff-columns"><aside class="ff-task-list" aria-label="挖掘任务列表"><h2>我的挖掘任务</h2><input class="ff-task-filter" id="task-search" aria-label="搜索挖掘任务" placeholder="搜索任务" value="'+safe(taskText)+'"><select id="task-filter" class="ff-task-filter" aria-label="任务状态">'+[['recent','运行与待处理'],['all','全部任务'],['ended','已结束']].map(([v,n])=>'<option value="'+v+'"'+(taskFilter===v?' selected':'')+'>'+n+'</option>').join('')+'</select><div id="task-items">'+taskItems(filtered)+'</div></aside><section class="ff-detail">'+taskDetail()+'</section></div>';
  }
  function autonomyBar(){
    const active=tasks.filter(x=>x.state==='running').length, waiting=tasks.filter(x=>x.state==='queued').length;
    const title={researching:'已开启',off:'选题已暂停',waiting:'等待新的研究机会',error:'选题未完成'}[autoState];
    const description=autoState==='off'?'暂停新增自动任务；已有研究仍按各自状态执行。':autoState==='waiting'?'目前没有足够的新依据。数据或研究方向变化后再考虑，已有记录保留。':autoState==='error'?'选题服务尚未返回完整结果，未创建新的研究任务。':'根据可用数据和研究经验，在授权范围内自动选题与启动。';
    return '<section class="ff-autonomy" aria-label="自主研究"><div><div class="ff-auto-title"><h2>自主研究</h2><span class="badge '+(autoState==='error'?'red':autoState==='off'?'':'purple')+'">'+title+'</span></div><p>'+description+'</p><div class="ff-auto-meta"><span>同时研究 1 项</span><span>正在研究 '+active+' 项</span><span>待启动 '+waiting+' 项</span></div></div><div class="ff-auto-actions">'+(autoState==='off'?btn('开启自主研究','auto-settings','','primary'):btn('暂停选题','auto-pause','','small'))+btn('研究范围与方向','auto-settings','','small')+(autoState==='waiting'?btn('重新考虑','auto-reconsider','','small'):'')+'</div></section>';
  }
  function planningBasis(t){
    if(t.origin!=='system')return '<div class="ff-planning-basis"><div class="ff-label">选题来源</div><p>由研究员创建。研究中可提出建议或交给 Agent 继续。</p></div>';
    return '<section class="ff-planning-basis" aria-label="选题依据"><div class="ff-label">为什么研究这个方向</div><p>'+safe(t.reason||'根据授权范围及已检索的研究资料提出；具体结论需经过检验。')+'</p>'+(t.difference?'<p><b>本次变化：</b>'+safe(t.difference)+'</p>':'')+(t.experience?'<div class="ff-evidence-link"><span>参考经验 · 在原范围内未获支持</span>'+btn('查看先前研究','prior-research',t.experience,'small')+'</div>':'<p class="muted">暂无可引用的历史结论。</p>')+'</section>';
  }
  function autonomySettings(){
    dialog(autoState==='off'?'开启自主研究':'研究范围与方向','<p class="ff-copy">系统在以下范围内自行选题、研究和总结；有价值的成果进入人工审查。</p><div class="ff-auto-scope"><h3>已授权研究范围</h3>'+scope()+'<p>同时进行1项后台研究；其余任务排队。Token用量持续记录。</p></div><label class="field">希望优先研究的方向（选填）<textarea name="direction" rows="3" placeholder="例如：优先研究量价关系，避开已反复失败且没有新依据的方向。">'+safe(autoDirection)+'</textarea></label><div class="hint">方向是研究建议，不会修改数据权限或检验要求。这里为交互设计样例，不启动真实研究。</div>','<button type="submit" class="btn primary">'+(autoState==='off'?'开启自主研究':'保存方向')+'</button>','auto-settings');
  }
  function taskItems(list){return list.length?list.map(x=>'<button class="ff-task '+(x.id===selected?'selected':'')+'" data-action="task" data-value="'+x.id+'"'+(x.id===selected?' aria-current="true"':'')+'><div class="ff-task-row">'+badge(x.state)+'<small>'+ (x.origin==='system'?'系统发起':'人工发起') +'</small></div><strong>'+safe(x.name)+'</strong><small>'+stages[x.step][0]+' · 已检验 '+x.k+'/'+x.max+' 次</small></button>').join(''):'<div class="empty">没有匹配的任务</div>';}
  function taskDetail(){
    const t=current();
    return '<header class="ff-detail-head"><div>'+badge(t.state)+'<h2>'+safe(t.name)+'</h2><p>'+(t.origin==='system'?'系统发起':'人工发起')+' · '+safe(({new:'新因子挖掘',improve:'改进已有因子',reproduce:'复现已有因子'})[t.purpose||'new'])+' · 日频 · 中证500 · 第 '+t.version+' 版</p></div><div class="actions">'+btn('范围与预算','scope','','small')+(t.state==='running'?btn('暂停','pause','','small'):['paused','draft','error'].includes(t.state)?btn(t.state==='error'?'重试启动':t.state==='draft'?'启动挖掘':'恢复','resume','','small'):'')+'</div></header>'+
      '<nav class="ff-steps" aria-label="任务业务环节">'+stages.map((s,i)=>'<button class="ff-step '+(i===viewing?'selected ':'')+(i===t.step?'current ':'')+(i<t.step?'done':'')+'" data-action="stage" data-value="'+i+'" aria-label="查看'+s[0]+'"><span class="ff-num">'+(i<t.step?'✓':i+1)+'</span><span><b>'+s[0]+'</b><small>'+s[1]+'</small><em>'+(i<t.step?'已完成':i===t.step?(t.state==='admitted'?'已完成':'当前环节'):'尚未开始')+'</em></span></button>').join('')+'</nav>'+
      (t.state==='error'?'<div class="ff-error" role="alert"><b>启动未完成</b><p>任务配置转换失败，Agent 尚未开始研究。本次没有产生试验或研究结果。</p>'+btn('重试启动','resume','','small')+'<details><summary>诊断详情</summary>配置中的日期字段未按接口格式编码。此为故障状态样例。</details></div>':'')+
      outcomeSummary()+'<div class="ff-stage-grid ff-work-panels"><div class="ff-work-main"><div class="ff-stage-main">'+stageContent()+'</div><div class="ff-history">'+researchHistory(t)+'</div></div>'+activity()+'</div>';
  }
  function outcomeSummary(){
    const t=current();
    if(t.state==='ended')return '<section class="ff-outcome" aria-label="研究结果"><div class="ff-label">最近结论</div><h3>本次研究未达到要求</h3><p>'+safe(t.stopReason||('已用完 '+t.max+' 次试验额度，研究已停止。'))+' 全部尝试和报告已保留，可用于复盘。</p><div class="actions">'+btn('查看试验报告','report','','small')+btn('提交研究复盘','feedback','','small')+'</div></section>';
    if(t.state==='paused')return '<section class="ff-outcome" aria-label="人工接力"><div class="ff-label">当前由你接手</div><h3>当前人工工作版本 · 第 '+t.version+' 版</h3><p>保存后交回 Agent，系统将从这个版本继续；已用的 '+t.k+' 次试验不会清零。</p><div class="actions">'+btn('继续编辑','manual','','small')+btn('交回 Agent','return-agent','','small primary')+'</div></section>';
    return '';
  }
  function stageContent(){
    const t=current(), head=stages[viewing];
    let body='', foot='';
    if(viewing>t.step) body='<div class="empty"><b>'+head[0]+'尚未开始</b>'+head[2]+'。满足条件后系统会推进，切换页面不会开始执行。</div>';
    else if(viewing===0){
      body='<div class="ff-copy"><div class="ff-label">研究目标</div><p>'+safe(t.goal)+'</p>'+planningBasis(t)+'<hr class="ff-divider">'+scope()+'</div>';
      foot=btn('编辑研究准备','edit-prep','','small');
    } else if(viewing===1){
      if(['queued','draft'].includes(t.state)&&!t.implementation&&!t.k) body='<div class="empty"><b>尚无因子定义</b>运行开始后，研究结果会显示在这里。</div>';
      else body='<div class="section-title"><div><div class="ff-label">当前候选 · 第 '+t.version+' 版</div><h3>'+safe(t.id==='A'?'低活跃度下的价格偏离修复':t.name)+'</h3></div>'+pill('假设 Ha')+'</div><div class="ff-copy"><p>'+safe(t.hypothesis||'近期价格偏离在低成交活跃度时可能更易回补；研发中比较不同窗口，检验这种条件是否提供稳定的增量信息。')+'</p></div><details class="ff-source"><summary>查看定义与实现 · 第 '+t.version+' 版</summary><pre class="ff-code">'+safe(t.implementation||'-rank(price_deviation_5d)\n  × rank(1 / (1 + relative_activity_20d))')+'</pre><small>设计样例，未执行计算。</small></details><hr class="ff-divider"><div class="section-title"><h3>研发检验</h3><small>已检验 '+t.k+' 次 / 上限 '+t.max+' 次</small></div><div class="ff-copy"><p>上一版：覆盖不足，已保留结果。</p><p>本版：'+(t.state==='running'?'正在检验修改后的实现':t.state==='ended'?(t.stopReason||'试验额度用尽，未达到要求'):t.state==='paused'?'已暂停，等待人工处理':t.state==='queued'?'保存版本已排队，等待继续检验':'结果已保存')+'。</p></div>';
      foot=btn('查看试验报告','report','','small')+btn('人工接手','manual','','small')+btn('给研究建议','opinion','','small');
    } else if(viewing===2){
      body='<div class="hint">候选版本已经固定。验证结果用于决定是否可送审，不回传封存细节供继续调参。</div><dl class="ff-kv"><dt>冻结版本</dt><dd>低活跃度下的价格偏离修复 · 第3版</dd><dt>证据范围</dt><dd>定义、实现、研发试验、数据与政策版本</dd><dt>重复性检查</dt><dd>'+(t.state==='waiting'?'等待计算服务':'已完成（场景）')+'</dd><dt>独立样本验证</dt><dd>'+(t.state==='waiting'?'尚未执行':'已完成（场景）')+'</dd></dl>'+(t.state==='waiting'?'<div class="hint warning" style="margin-top:18px">尚缺可用的因子相关性计算服务。结果未返回前不能送审。</div>':'');
      foot=btn('查看验证证据','report','','small');
    } else {
      body=t.state==='admitted'?'<div class="hint success">已批准研究用途，并登记因子第1版。</div><dl class="ff-kv"><dt>因子名称</dt><dd>低活跃度下的价格偏离修复</dd><dt>业务分类</dt><dd>量价关系因子</dd><dt>标签</dt><dd>日频 · 量价</dd><dt>审批</dt><dd>独立复核人 · 审批意见与证据版本已留存（场景）</dd></dl>':'<div class="ff-copy"><p>'+(t.state==='returned'?'待补充审查材料。修改实现需另建候选，冻结结果不能覆盖。':t.state==='rejected'?'本候选已驳回，记录与证据保留。':'候选与报告已经整理完成，等待独立复核人审查。研究员可以查看证据，不能批准自己的成果。')+'</p>'+(t.reviewOpinion?'<p>审查意见：'+safe(t.reviewOpinion)+'</p>':'')+'</div>';
      foot=btn(t.state==='admitted'?'在因子库查看':'查看审批材料',t.state==='admitted'?'library-new':'tab',t.state==='admitted'?'':'review','small primary');
    }
    return '<article class="card ff-stage-card"><div class="card-head"><div><h2>'+head[0]+'</h2><p>'+head[2]+'</p></div>'+pill(head[1])+'</div><div class="card-body" tabindex="0" role="region" aria-label="'+head[0]+'内容">'+body+'</div>'+(foot?'<div class="card-footer"><div class="actions">'+foot+'</div></div>':'')+'</article>';
  }
  function activity(){
    const t=current(), messages=t.state==='running'?['正在检验第'+t.version+'版实现','已修订缺失值处理','已读取上一轮检验报告']:t.state==='error'?['准备阶段发生异常','任务已创建，配置尚未送入研究系统']:t.state==='waiting'?['等待相关性计算服务','候选第3版已冻结','研发检验完成']:t.state==='review'?['已整理因子说明与标签建议','已提交独立审查','验证证据已固定']:t.state==='admitted'?['已登记研究用途因子','独立复核人已批准']:t.state==='returned'?['待补充审查材料','原冻结证据保持不变']:t.state==='rejected'?['独立复核人已驳回','审查意见与全部证据已归档']:t.state==='ended'?[t.stopReason||'试验额度已用尽，任务结束','已归档全部试验']:t.state==='paused'?['任务已暂停，未发出新计算']:t.state==='queued'?['样例请求已进入排队状态，未提交真实服务']:['草稿已保存，尚未启动'];
    return '<aside class="ff-live" aria-label="Agent 工作状态"><div class="ff-live-head"><div class="ff-label">当前工作</div><h3>'+stages[t.step][1]+'</h3><div class="ff-now">'+messages[0]+'</div><p>场景记录 · 不自动推进</p></div><div class="ff-live-body" tabindex="0" role="region" aria-label="Agent 运行记录"><ol>'+messages.map((m,i)=>'<li><time>'+(i===0?'最近一次操作':'此前')+'</time>'+m+'</li>').join('')+'</ol>'+(t.note?'<p style="margin-top:10px">已提交意见：'+safe(t.note)+'</p>':'')+'</div><div class="ff-live-foot"><div class="ff-label">需要你处理</div><p>'+(t.state==='review'?'等待独立复核人查看证据并决定。':t.state==='error'?'重试启动；重复异常请联系维护人员。':t.state==='waiting'?'已记录服务缺口，暂不能继续验证。':t.state==='paused'?'完成人工操作后恢复研究。':t.state==='returned'?'补齐审查要求的材料，再申请复核。':t.state==='ended'?'可查看全部试验，提交研究复盘。':'当前无需人工审批。')+'</p><div class="actions" style="margin-top:14px">'+btn('给研究建议','opinion','','small')+'</div></div></aside>';
  }
  function researchHistory(t){
    if(!t.k) return '<details class="ff-fold"><summary>研究历程与全部试验</summary><div class="empty">尚无试验记录；启动后按实际事件积累。</div></details>';
    return '<details class="ff-fold"><summary>研究历程 · 查看假设、分支与版本</summary><div class="ff-tree"><div class="ff-node"><b>H1</b><span>初始假设 · 无条件价格偏离</span><small>已检验</small>'+btn('试验1','report','','small')+'</div><div class="ff-children"><div class="ff-branch"><div class="ff-node"><b>Ha</b><span>引入成交活跃度条件</span><small>第'+t.version+'版 · '+safe(status[t.state][0])+'</small>'+btn('试验2','report','','small')+'</div></div><div class="ff-branch"><div class="ff-node"><b>Hb</b><span>调整观察窗口</span><small>已停止，保留证据</small></div></div></div></div></details><details class="ff-fold"><summary>全部试验 · 已计入 '+t.k+' 次 / 预算 '+t.max+' 次</summary><div><div class="table-wrap"><table class="table"><thead><tr><th>试验</th><th>假设与实现</th><th>结果</th><th>计入预算</th><th>报告</th></tr></thead><tbody><tr><td>1</td><td>H1 · 第1版</td><td>未达标</td><td>是</td><td>'+btn('查看','report','','small')+'</td></tr><tr><td>2</td><td>Ha · 第2版</td><td>覆盖不足</td><td>是</td><td>'+btn('查看','report','','small')+'</td></tr></tbody></table></div><small>这里只展示两条设计样例；实际台账显示全部执行记录。</small></div></details>';
  }
  function reviewPage(){
    const candidate=tasks.find(x=>['review','admitted','returned','rejected'].includes(x.state));
    if(!candidate)return '<div class="card"><div class="empty"><b>暂无待审批因子</b>研发和独立验证通过后，候选会自动出现在这里。'+ '<p style="margin-top:12px">可在页面上方的设计预览中切换“待审批”场景。</p></div></div>';
    selected=candidate.id;
    return '<div class="ff-stage-grid"><article class="card"><div class="card-head"><div><h2>低活跃度下的价格偏离修复</h2><p>来源：'+safe(candidate.name)+' · 冻结候选第3版</p></div>'+badge(candidate.state)+'</div><div class="card-body"><div class="hint">以下为审批布局样例。真实审批必须绑定当前候选的完整计算证据。</div><dl class="ff-kv"><dt>研究假设</dt><dd>成交活跃度条件能提供价格偏离之外的增量信息。</dd><dt>实现版本</dt><dd>第3版，定义与实现只读</dd><dt>数据与范围</dt><dd>日频 · 中证500 · 固定版本</dd><dt>研发试验</dt><dd>全部试验及预算记录</dd><dt>独立验证</dt><dd>样本外检验、重复性与证据完整性检查</dd><dt>建议用途</dt><dd>研究使用；不授予实盘权限</dd><dt>建议分类</dt><dd>量价关系因子</dd><dt>建议标签</dt><dd>日频、量价</dd></dl><hr class="ff-divider"><div class="actions">'+btn('查看定义与实现','definition','','small')+btn('查看验证报告','report','','small')+btn('查看全部试验','history','','small')+'</div><hr class="ff-divider"><p class="ff-copy">局限：验证仅适用于已记录的数据和研究范围，不保证未来表现。</p></div><div class="card-footer"><small>'+(candidate.state==='admitted'?'审批记录已保留。':candidate.state!=='review'?'审查意见：'+safe(candidate.reviewOpinion||''):role==='reviewer'?'当前预览身份：独立复核人':'当前为研究员视角，只能查看材料。')+'</small><div class="actions">'+(candidate.state==='admitted'?btn('查看入库因子','library-new','','small primary'):candidate.state!=='review'?badge(candidate.state):'<button type="button" class="btn small" data-action="decision" data-value="reject"'+(role!=='reviewer'?' disabled':'')+'>驳回</button><button type="button" class="btn small" data-action="decision" data-value="return"'+(role!=='reviewer'?' disabled':'')+'>退回补证</button><button type="button" class="btn small primary" data-action="decision" data-value="approve"'+(role!=='reviewer'?' disabled':'')+'>批准研究用途</button>')+'</div></div></article><aside class="ff-live"><h3>独立审查</h3><div class="ff-now">人作决定，系统保留依据。</div><p>成果管理 Agent 整理说明和标签建议。复核人核对定义、全部试验、冻结证据及使用边界。</p><hr class="ff-divider"><p>补证只补缺失材料；改变实现需生成新候选，不能改写已冻结的验证结果。</p></aside></div>';
  }
  function catMatch(f,cat){return cat==='all'||f.cat===cat;}
  function filteredLibrary(){return library.filter(f=>catMatch(f,category)&&(availability==='all'||f.state===availability)&&(!tags.length||tags.some(t=>f.tags.includes(t)))&&[f.name,f.code,f.description,...f.tags].join(' ').toLowerCase().includes(query.toLowerCase())).sort((a,b)=>sort==='code'?a.code.localeCompare(b.code):a.name.localeCompare(b.name,'zh-CN'));}
  function libraryPage(){
    return '<div class="ff-library"><aside class="ff-categories" aria-label="因子分类"><h3>分类</h3>'+categoryButton('all','全部因子')+categories.map(c=>categoryButton(c,c)).join('')+'</aside><section style="min-width:0"><div class="ff-toolbar"><input id="factor-search" aria-label="搜索因子名称、代码或标签" placeholder="搜索名称、代码、说明或标签" value="'+safe(query)+'"><select id="factor-availability" aria-label="因子可用状态">'+[['all','全部可用状态'],['可研究','可研究'],['已审核','已审核'],['暂停使用','暂停使用']].map(([v,n])=>'<option value="'+v+'"'+(availability===v?' selected':'')+'>'+n+'</option>').join('')+'</select>'+btn('清空筛选','clear-filters','','small')+'</div><div class="ff-tags"><span>标签 · 包含任一</span>'+['日频','量价','价格','基本面','价值','风险','规模'].map(t=>'<button class="ff-tag '+(tags.includes(t)?'on':'')+'" data-action="tag" data-value="'+t+'" aria-pressed="'+tags.includes(t)+'">'+t+'</button>').join('')+'</div><div id="factor-results">'+libraryResults()+'</div></section></div>';
  }
  function categoryButton(cat,label,child=false){return '<button class="ff-category '+(child?'child ':'')+(category===cat?'on':'')+'" data-action="category" data-value="'+cat+'" aria-pressed="'+(category===cat)+'">'+label+'<span>'+library.filter(f=>catMatch(f,cat)).length+'</span></button>';}
  function libraryResults(){
    const found=filteredLibrary(), per=5,total=Math.max(1,Math.ceil(found.length/per)); page=Math.min(page,total);
    return '<div class="ff-results"><span>'+safe(category==='all'?'全部分类':category)+' · '+found.length+' 个样例因子'+(tags.length?' · '+tags.join(' / '):'')+'</span><label>排序 <select id="factor-sort" aria-label="因子排序"><option value="name"'+(sort==='name'?' selected':'')+'>名称</option><option value="code"'+(sort==='code'?' selected':'')+'>代码</option></select></label></div><div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>因子名称 / 代码</th><th>分类</th><th>标签</th><th>状态</th><th>操作</th></tr></thead><tbody>'+found.slice((page-1)*per,page*per).map(f=>'<tr><td><b>'+safe(f.name)+'</b><small>'+f.code+'</small></td><td>'+f.cat+'</td><td>'+f.tags.map(pill).join('')+'</td><td>'+pill(f.state)+'</td><td>'+btn('详情','factor',f.code,'small')+'</td></tr>').join('')+'</tbody></table></div>'+(found.length?'':'<div class="empty"><b>没有匹配的因子</b>尝试减少筛选条件。<p>'+btn('清空筛选','clear-filters','','small')+'</p></div>')+'</div><div class="ff-footer"><span>可按分类、标签与状态组合查找。</span><div class="actions"><button class="btn small" data-action="page" data-value="-1"'+(page===1?' disabled':'')+'>上一页</button><span>'+page+' / '+total+'</span><button class="btn small" data-action="page" data-value="1"'+(page===total?' disabled':'')+'>下一页</button></div></div>';
  }

  function toast(message){const el=q('#factory-toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),4000);}
  function dialog(title,body,footer='',formAction=''){
    const d=q('#factory-dialog');
    d.innerHTML='<form id="ff-form"'+(formAction?' data-submit="'+formAction+'"':'')+'><header class="ff-modal-head"><h2 id="factory-dialog-title">'+title+'</h2><button type="button" class="text-btn" data-action="close" aria-label="关闭对话框">关闭 ×</button></header><div class="ff-modal-body">'+body+'</div><footer class="ff-modal-footer">'+btn('取消','close')+footer+'</footer></form>';
    if(!d.open)d.showModal();
  }
  function newTask(reference){
    dialog('启动因子挖掘','<div class="field-grid"><label class="field full">任务类型<select name="purpose" id="new-purpose"><option value="new"'+(!reference?' selected':'')+'>新因子挖掘</option><option value="improve"'+(reference?' selected':'')+'>改进已有因子</option><option value="reproduce">复现已有因子</option></select></label><label class="field full">挖掘方向<select name="direction"><option>量价关系</option><option>风险与波动</option><option>基本面与规模</option><option>系统建议方向（授权范围内）</option></select></label><label class="field full">任务名称<input name="name" required maxlength="70" placeholder="例如：低换手条件下的价格偏离" value="'+safe(reference?'改进 '+reference.name:'')+'"></label><label class="field full">研究目标（选填）<textarea name="goal" placeholder="希望研究什么现象，重点控制哪些风险？"></textarea></label><label class="field full" id="reference-field"'+(!reference?' hidden':'')+'>参考因子<select name="reference"'+(reference?' required':' disabled')+'><option value="">请选择</option>'+library.filter(f=>f.state!=='暂停使用').map(f=>'<option value="'+f.code+'"'+(reference?.code===f.code?' selected':'')+'>'+f.name+'</option>').join('')+'</select><small>改进和复现需要指定已有因子；新挖掘不以已有因子冒充新成果。</small></label></div><details class="ff-fold"><summary>范围与预算 · 日频 / 中证500 / 最多8次试验</summary><div><p class="ff-copy">使用机构当前授权的日频数据范围。研发与验证区间在计划中固定；扩大范围或额度需要负责人授权。</p></div></details><div class="hint">创建后系统自动准备、研发和验证。只有授权、明确人工介入或最终审批才需要人处理。</div>', '<button type="submit" name="intent" value="draft" class="btn">保存草稿</button><button type="submit" name="intent" value="start" class="btn primary">创建并启动</button>', 'create');
  }
  function report(){
    dialog('试验与验证报告','<div class="hint">报告布局为场景示意，未加载真实检验数值。</div><dl class="ff-kv"><dt>因子与版本</dt><dd>低活跃度下的价格偏离修复 · 第3版</dd><dt>研究范围</dt><dd>日频 / 中证500 / 固定数据版本</dd><dt>研发证据</dt><dd>覆盖率、IC、显著性、分组表现、换手与成本、分期稳定性</dd><dt>对照与基准</dt><dd>组合与基准的同期曲线、超额表现、同区间参数</dd><dt>独立验证</dt><dd>冻结候选、独立样本结果、查重范围与相关性</dd><dt>全部试验</dt><dd>包括未通过与停止的尝试，不能只呈现最好一次</dd></dl><hr class="ff-divider"><p class="ff-copy">每份报告对应一次试验的固定版本。完整试验记录保留失败尝试，研究结论只适用于报告中的样本与区间。</p>',btn('关闭报告','close','','primary'));
  }
  function manual(){
    const t=current();
    if(t.state==='running'){
      dialog('接手当前研究','<p class="ff-copy">先暂停到安全边界，再从当前实现派生人工版本。已执行的版本和报告保持只读；人工检验仍计入本任务的预算。</p><div class="hint">设计操作，不会暂停任何真实服务。</div>',btn('暂停并打开人工工作台','takeover','','primary'));
      return;
    }
    if(!['paused','draft'].includes(t.state)){
      dialog('人工研究','<p class="ff-copy">'+(t.state==='error'?'当前启动异常，请先排除问题后再恢复研究。':'此任务当前不接受直接修改。冻结的验证版本和历史结果保留。')+'</p>',btn('关闭','close','','primary'));
      return;
    }
    dialog('人工研究 · '+safe(t.name),'<div class="hint">人工结果使用同一任务、版本和试验台账。此编辑器仅保存当前页面的设计样例。</div><div class="field-grid"><label class="field full">研究假设<textarea name="hypothesis" required>'+safe(t.hypothesis||'研究价格偏离与成交活跃度的条件关系。')+'</textarea></label><label class="field full">因子实现<textarea class="code" name="implementation" required>'+safe(t.implementation||'signal = -rank(price_deviation_5d)\n# 编辑当前人工版本的实现')+'</textarea></label></div><div class="actions">'+btn('检验当前版本','sample-test','','small')+btn('AI 辅助修改','sample-assist','','small')+'</div>', '<button class="btn primary" type="submit">保存人工草稿</button>','manual-save');
  }
  function factorDetail(code){
    const f=library.find(x=>x.code===code);if(!f)return;
    dialog(safe(f.name),'<dl class="ff-kv"><dt>因子代码</dt><dd>'+f.code+'</dd><dt>说明</dt><dd>'+safe(f.description)+'</dd><dt>分类</dt><dd>'+safe(f.cat)+'</dd><dt>标签</dt><dd>'+f.tags.map(pill).join(' ')+'</dd><dt>可用状态</dt><dd>'+f.state+'</dd><dt>报告</dt><dd>'+f.report+' · 来源、数据范围与版本随报告保留</dd><dt>来源</dt><dd>'+f.origin+'</dd><dt>使用边界</dt><dd>用于授权范围内的研究；不代表可直接实盘使用。</dd></dl><div class="hint">全部为设计样例。正式目录使用真实分类、权限和报告。</div>',btn('查看报告','report','','')+(f.state!=='暂停使用'?btn('用此因子改进','improve',f.code,'primary'):''));
  }
  function decision(kind){
    if(role!=='reviewer'||current().state!=='review')return;
    const label={approve:'批准研究用途',return:'退回补证',reject:'驳回'}[kind];
    dialog(label,'<div class="field-grid"><label class="field full">审查意见<textarea name="reason" required minlength="4" placeholder="请说明依据、限制或需补充的材料。"></textarea></label>'+(kind==='approve'?'<label class="field">确认分类<select name="category"><option>量价关系因子</option><option>反转因子</option></select></label><label class="field">标签<input name="tags" value="日频,量价" required></label>':'')+'</div><label class="check"><input type="checkbox" name="read" required>我已核对冻结版本、完整试验和验证材料；此操作仅用于设计场景。</label>', '<button class="btn primary" type="submit">'+label+'</button>','decision-'+kind);
  }
  function setTab(value){tab=value;history.replaceState(null,'','#'+value);draw();}
  function addAdmitted(){if(!library.some(f=>f.code==='F-008')) library.push({code:'F-008',name:'低活跃度下的价格偏离修复',cat:'量价关系因子',tags:['日频','量价'],state:'已审核',description:'成交活跃度条件下的价格偏离修复特征。',origin:'机构研究成果',report:'独立验证报告 · 冻结第3版'});}
  q('#factory').addEventListener('click',handleClick);q('#factory-dialog').addEventListener('click',handleClick);
  function handleClick(event){
    const el=event.target.closest('[data-action]');if(!el||el.disabled)return;
    const action=el.dataset.action,v=el.dataset.value,t=current();
    if(role==='reviewer'&&editActions.has(action))return;
    if(action==='auto-settings'){autonomySettings();return;}
    if(action==='auto-pause'){autoState='off';draw();toast('设计场景已暂停新增选题；已有任务状态保留。');return;}
    if(action==='auto-reconsider'){dialog('重新考虑研究方向','<p class="ff-copy">当前没有足够的新依据。你可以补充方向或新资料，再让系统考虑一次。</p><label class="field">新的依据或希望调整的方向<textarea name="direction" required minlength="4" placeholder="说明与上一次不同的信息。"></textarea></label><div class="hint">正式系统保留本次请求和原决定，不会因刷新自动重复选题。</div>','<button type="submit" class="btn primary">提交方向</button>','auto-reconsider');return;}
    if(action==='prior-research'){selected=v;viewing=current().step;taskFilter='all';taskText='';draw();return;}
    if(action==='close'){q('#factory-dialog').close();return;}
    if(action==='tab'){setTab(v);return;}
    if(action==='new'){newTask();return;}
    if(action==='task'){selected=v;viewing=current().step;draw();return;}
    if(action==='stage'){viewing=Number(v);draw();return;}
    if(action==='scope'){dialog('范围与预算',scope()+'<hr class="ff-divider"><p class="ff-copy">已用 '+t.k+' 次 / 上限 '+t.max+' 次。变更通过负责人授权产生新计划；旧试验、消耗与证据不会清零。</p>',btn('申请调整','request-scope','','primary'));return;}
    if(action==='request-scope'){dialog('申请范围或预算调整','<div class="field-grid"><label class="field full">希望调整的内容<textarea name="change" required placeholder="填写原范围、新范围与理由；可用数据权限和验证门槛不能由意见改写。"></textarea></label></div>', '<button type="submit" class="btn primary">提交授权申请</button>','scope-request');return;}
    if(action==='pause'){t.state='paused';draw();toast('场景任务已暂停；未操作真实服务。');return;}
    if(action==='resume'){t.state='queued';draw();toast('样例已进入排队状态。真实实现需获得服务返回的运行标识，不能只改界面。');return;}
    if(action==='manual'){manual();return;}
    if(action==='return-agent'){dialog('交回 Agent','<dl class="ff-kv"><dt>使用版本</dt><dd>当前保存的人工第 '+t.version+' 版</dd><dt>已有试验</dt><dd>'+t.k+' 次；预算不重置</dd><dt>接下来</dt><dd>先检验此版本；已有匹配报告时复用证据，再决定是否修改。</dd></dl><div class="hint">设计交互，不会启动真实 Agent。</div>',btn('确认交回','confirm-return','','primary'));return;}
    if(action==='confirm-return'){t.state='queued';q('#factory-dialog').close();draw();toast('样例已交回，真实系统须绑定保存版本后继续。');return;}
    if(action==='feedback'){dialog('提交研究复盘','<p class="ff-copy">本次研究未达标。复盘用于核对证据、总结原因，不能批准入库。</p><label class="field">希望复核的问题<textarea name="question" required placeholder="说明未通过的检验，以及希望进一步核对的问题。"></textarea></label><div class="hint">此处仅演示复盘表单，不提交真实审批。</div>','<button class="btn primary" type="submit">保存复盘草稿</button>','feedback');return;}
    if(action==='takeover'){t.implementation=t.implementation||'-rank(price_deviation_5d)\n  × rank(1 / (1 + relative_activity_20d))';t.hypothesis=t.hypothesis||'近期价格偏离在低成交活跃度时可能更易回补。';t.state='paused';t.version++;draw();manual();return;}
    if(action==='sample-test'){toast('此原型不发计算；正式系统应提交真实检验并返回运行标识。');return;}
    if(action==='sample-assist'){toast('AI 辅助在正式系统生成修改建议；确认后写入新的人工版本。');return;}
    if(action==='opinion'){dialog('给研究建议','<label class="field">建议<textarea name="opinion" required placeholder="例如：优先检查极端行情中的稳定性。">'+safe(t.note)+'</textarea></label><div class="hint">意见作为下一次研究决策的输入，不会自动扩大预算或放宽门槛。</div>','<button type="submit" class="btn primary">提交建议</button>','opinion');return;}
    if(action==='edit-prep'){dialog('调整研究准备','<label class="field">研究目标<textarea name="goal" required>'+safe(t.goal)+'</textarea></label><div class="hint">运行中的任务先暂停，再保存为新版本；已消耗预算和旧试验保留。范围扩大另走授权。</div>','<button type="submit" class="btn primary">暂停并保存新版本</button>','prepare');return;}
    if(action==='report'){report();return;}
    if(action==='definition'){dialog('冻结定义与实现','<p class="ff-copy">低成交活跃度条件下，近期价格偏离更容易回补。</p><pre class="ff-code">'+safe(t.implementation||'-rank(price_deviation_5d)\n  × rank(1 / (1 + relative_activity_20d))')+'</pre><small>场景表达式。正式系统展示完整受限实现、参数与不可变版本。</small>',btn('关闭','close','','primary'));return;}
    if(action==='history'){setTab('tasks');viewing=1;draw();q('.ff-fold').open=true;return;}
    if(action==='decision'){decision(v);return;}
    if(action==='library-new'){addAdmitted();category='all';query='低活跃度';tags=[];availability='all';page=1;setTab('library');return;}
    if(action==='category'){category=v;page=1;draw();return;}
    if(action==='tag'){tags=tags.includes(v)?tags.filter(x=>x!==v):[...tags,v];page=1;draw();return;}
    if(action==='clear-filters'){category='all';query='';tags=[];availability='all';page=1;draw();return;}
    if(action==='page'){page+=Number(v);q('#factor-results').innerHTML=libraryResults();return;}
    if(action==='factor'){factorDetail(v);return;}
    if(action==='improve'){newTask(library.find(f=>f.code===v));return;}
  }
  q('#factory').addEventListener('input',event=>{
    if(event.target.id==='factor-search'){query=event.target.value;page=1;q('#factor-results').innerHTML=libraryResults();}
    if(event.target.id==='task-search'){taskText=event.target.value;const filtered=tasks.filter(x=>(taskFilter==='all'||taskFilter==='recent'&&!['ended','rejected','admitted'].includes(x.state)||taskFilter===x.state)&&x.name.includes(taskText));q('#task-items').innerHTML=taskItems(filtered);}
  });
  q('#factory').addEventListener('change',event=>{
    const el=event.target;
    if(el.id==='preview-autonomy'){autoState=el.value;draw();return;}
    if(el.id==='preview-role'){role=el.value;draw();}
    if(el.id==='preview-state'){const t=tasks.find(x=>x.id==='A');t.state=el.value;t.step=['running','paused','queued','ended'].includes(el.value)?1:el.value==='waiting'?2:3;selected=t.id;viewing=t.step;if(t.state==='admitted')addAdmitted();draw();toast('已切换独立设计场景，未触发真实工作。');}
    if(el.id==='task-filter'){taskFilter=el.value;draw();}
    if(el.id==='factor-availability'){availability=el.value;page=1;draw();}
    if(el.id==='factor-sort'){sort=el.value;q('#factor-results').innerHTML=libraryResults();}
  });
  q('#factory-dialog').addEventListener('change',event=>{
    if(event.target.id==='new-purpose'){const need=event.target.value!=='new';q('#reference-field').hidden=!need;const input=q('#reference-field select');input.disabled=!need;input.required=need;}
  });
  q('#factory-dialog').addEventListener('submit',event=>{
    event.preventDefault();const form=event.target;if(!form.reportValidity())return;const fd=new FormData(form),type=form.dataset.submit,t=current();
    if(type==='auto-settings'||type==='auto-reconsider'){
      if(role==='reviewer')return;
      autoDirection=String(fd.get('direction')||'').trim();
      autoState='researching';
      q('#factory-dialog').close();draw();toast('自主研究场景已更新；未调用模型或创建真实任务。');return;
    }
    if(type==='create'){
      const draft=event.submitter?.value==='draft';const purpose=fd.get('purpose');
      const created={id:'N'+(++serial),name:fd.get('name').trim(),state:draft?'draft':'queued',step:0,k:0,max:8,version:1,direction:fd.get('direction'),goal:fd.get('goal').trim()||'依据选定方向，在已授权日频数据内提出并检验因子假设。',purpose,note:''};
      if(!created.name){toast('请填写任务名称。');return;}
      tasks.unshift(created);selected=created.id;viewing=0;taskText='';taskFilter='recent';tab='tasks';history.replaceState(null,'','#tasks');
    } else if(type==='opinion')t.note=fd.get('opinion').trim();
    else if(type==='prepare'){t.goal=fd.get('goal').trim();t.state='paused';t.version++;}
    else if(type==='manual-save'){t.hypothesis=fd.get('hypothesis');t.implementation=fd.get('implementation');}
    else if(type==='feedback'){t.feedbackDraft=fd.get('question');}
    else if(type?.startsWith('decision-')){
      if(role!=='reviewer'||t.state!=='review')return;
      const kind=type.slice(9);t.reviewOpinion=fd.get('reason');t.reviewDecision=kind;
      if(kind==='approve'){t.state='admitted';t.step=3;addAdmitted();const f=library.find(x=>x.code==='F-008');f.cat=fd.get('category');f.tags=fd.get('tags').split(/[,，]/).map(x=>x.trim()).filter(Boolean);}
      else if(kind==='reject'){t.state='rejected';}
      else {t.state='returned';}
    }
    q('#factory-dialog').close();draw();toast(type==='create'?'场景任务已保存；未创建真实研究或调用模型。':type?.startsWith('decision-')?'设计决定已记录；没有提交真实审批或入库。':'样例已保存；未写入真实系统。');
  });
  window.addEventListener('hashchange',()=>{const v=location.hash.slice(1);if(['tasks','review','library'].includes(v)){tab=v;draw();}});
  draw();
})();
