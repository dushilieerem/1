'use strict';
const MODULES={
 factor:{title:'因子工厂',icon:'ƒ',desc:'定义假设，构造因子，计算与检验，保留可复用的研究证据。',steps:['研究定义','表达式构造','计算检验','诊断比较','候选复核','研究资产'],roles:['因子假设助手','因子构造助手','因子检验助手','诊断分析助手','候选复核助手','资产管理助手'],fields:[['name','reason','data_version','start','end'],['expression','preprocess'],['horizon','groups'],[],[],[]],compute:2},
 strategy:{title:'策略研究',icon:'∿',desc:'从已有因子研究资产出发，制定规则并调用平台回测引擎。',steps:['研究目标','选择因子','交易规则','策略回测','候选复核','研究资产'],roles:['策略设计助手','因子组合助手','规则配置助手','回测分析助手','候选复核助手','资产管理助手'],fields:[['name','reason','data_version','start','end'],['factors'],['rebalance','top_n','cost_bps'],[],[],[]],compute:3},
 portfolio:{title:'投资组合',icon:'◈',desc:'复用策略回测证据，分析权重、净值和回撤，形成研究方案。',steps:['组合目标','策略配置','组合计算','风险检查','方案复核','方案留档'],roles:['组合规划助手','配置研究助手','组合计算助手','风险分析助手','方案复核助手','资产管理助手'],fields:[['name','reason'],['strategies'],[],[],[],[]],compute:2}
};
const LABEL={name:'任务名称',reason:'研究目标与依据',expression:'因子表达式',preprocess:'截面预处理',data_version:'真实数据版本',start:'开始日期',end:'结束日期',horizon:'前瞻收益周期（交易日）',groups:'分层数量',rebalance:'调仓周期（交易日）',top_n:'持仓股票数',cost_bps:'单边综合成本（bps）',factors:'因子研究资产',strategies:'策略资金配置'};
const METRIC={ic_mean:'平均 IC',rank_ic_mean:'平均 Rank IC',ic_ir:'ICIR（未年化）',rank_ic_ir:'Rank ICIR（未年化）',valid_days:'有效 IC 天数',sharpe:'夏普比率',max_drawdown:'最大回撤',total_return:'累计收益',annual_return:'年化收益',volatility:'年化波动',observations:'收益观察天数',daily_one_way_turnover:'日均单边换手',cash_weight:'现金比例'};
const STATUS={queued:'排队中',running:'运行中',completed:'已完成',failed:'失败',cancelled:'已停止',interrupted:'已中断',pending:'待审核',approved:'已审核',not_submitted:'研究留档',returned:'已退回',rejected:'未通过',pass:'通过',warn:'提示',fail:'失败'};
let S=null,C=null,dirty=false,busy=false,reportCache={},preview=null,aiSelected='',lastPaint='',dataVersion='',refreshTimer;
const esc=v=>String(v??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const json=v=>esc(JSON.stringify(v,null,2));
const num=(v,d=4)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(d):'—';
const when=v=>v?new Date(v*1000).toLocaleString('zh-CN',{hour12:false}):'—';
const badge=(x,label)=>'<span class="badge '+(x==='completed'||x==='approved'||x==='pass'?'green':x==='failed'||x==='fail'||x==='rejected'?'red':x==='pending'||x==='warn'?'amber':'')+'">'+esc(label||STATUS[x]||x)+'</span>';
const btn=(label,action,extra='',primary=false)=>'<button type="button" class="btn '+(primary?'primary':'')+'" data-action="'+action+'" '+extra+'>'+label+'</button>';
const go=(hash)=>{if(dirty&&!confirm('有尚未保存的参数，离开后将丢弃这些修改。'))return;dirty=false;location.hash=hash};
const route=()=>{const p=decodeURIComponent(location.hash.slice(1)||'overview').split('/');if(p[0]==='home')p[0]='overview';return p};
const task=()=>S?.tasks.find(t=>t.id===route()[2]&&t.module===route()[0]);
const latest=t=>t?S.runs.find(r=>r.task_id===t.id&&r.task_revision===t.revision):null;
const card=(title,body,extra='')=>'<section class="card '+extra+'"><div class="card-head"><h3>'+title+'</h3></div><div class="card-body">'+body+'</div></section>';
function toast(text,error=false){const el=document.getElementById('toast');el.textContent=text;el.className='show'+(error?' error':'');setTimeout(()=>el.className='',6500)}
async function api(path,body){let r;try{r=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})}catch{throw Error('连接中断，请检查 SSH 隧道与服务器服务后重试')}let d;try{d=await r.json()}catch{throw Error('服务器未返回有效响应')}if(!r.ok)throw Error(d.error||d.detail||'请求失败');return d}
function header(title,desc,actions=''){return '<div class="page-head"><div><div class="eyebrow">SUNVALLEY · QUANT RESEARCH</div><h1>'+title+'</h1><p>'+desc+'</p></div><div class="actions">'+actions+'</div></div>'}
function empty(text){return '<div class="empty">'+text+'</div>'}
function link(label,hash){return '<button type="button" class="text-btn" data-go="'+esc(hash)+'">'+esc(label)+'</button>'}
function shell(body){
 const p=route()[0];const nav=[['overview','◉','研究总览'],['data','▤','数据资源'],...Object.entries(MODULES).map(([k,m])=>[k,m.icon,m.title]),['monitor','◎','运行监控'],['assets','▧','研究资产'],['review','✓','研究审核'],['settings','⚙','AI 与方法']];
 return '<div class="app-shell"><aside class="sidebar"><div class="brand"><span class="seal">山</span><div><strong>SUNVALLEY</strong><small>INSTITUTIONAL QUANT</small></div></div><div class="workspace-name"><b>机构量化研究</b>服务器研发工作区</div><nav>'+nav.map(([k,i,l])=>'<button class="nav-item" data-go="'+k+'" aria-current="'+(p===k?'page':'false')+'"><span class="nav-icon">'+i+'</span>'+l+'</button>').join('')+'</nav><div class="sidebar-bottom"><a href="/assets/prototype-v3/prd.html" target="_blank" rel="noopener">产品需求文档 ↗</a><small>内部研究 · 无交易账户连接</small></div></aside><div><header class="topbar"><button class="btn menu-toggle" data-action="menu">☰ 菜单</button><div class="crumb">Sunvalley / 机构量化</div><div class="top-actions"><span id="live-status" class="fine">已连接服务器</span><span class="badge">'+(S.connection.configured?'AI 已连接':'AI 未配置')+'</span>'+btn('刷新','refresh')+'</div></header><main class="main">'+body+'<p class="bottom-caption">研究数据与实验保存在公司服务器。研究审核只登记研发成果，不授权资金、成交或上线交易。</p></main></div></div>';
}
function table(headers,rows){return '<div class="table-wrap"><table class="table"><thead><tr>'+headers.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'}
function runsTable(runs){return runs.length?table(['实验 / 版本','类型','运行状态','研究审核','创建时间'],runs.map(r=>[link(r.name,'report/'+r.id)+'<small class="block">'+esc(r.id)+(r.task_revision?' · v'+r.task_revision:'')+'</small>',MODULES[r.kind]?.title||esc(r.kind),badge(r.status),badge(r.review),when(r.created)])):empty('还没有实验。进入因子工厂创建研究任务。')}
function overview(){
 const active=S.runs.filter(r=>['queued','running'].includes(r.status)),pending=S.runs.filter(r=>r.review==='pending'),finished=S.runs.filter(r=>r.status==='completed');
 return header('研究总览','从真实数据出发，让研究步骤、AI 动作和结果证据对应起来。',btn('新建因子研究','new','data-module="factor"',true))+
 '<div class="kpis">'+[['研究任务',S.totals?.tasks??S.tasks.length],['运行中（计算 / AI）',(S.totals?.active_runs??active.length)+(S.totals?.active_agents??0)],['已完成实验',S.totals?.completed??finished.length],['待审核',S.totals?.pending??pending.length]].map(([k,v])=>'<div class="card kpi"><small>'+k+'</small><strong>'+v+'</strong></div>').join('')+'</div>'+
 '<div class="module-grid">'+[['data','▤','数据资源','版本选择 · 行情预览 · 质量记录'],...Object.entries(MODULES).map(([k,m])=>[k,m.icon,m.title,m.steps.join(' · ')]),['monitor','◎','运行监控','计算状态 · AI 调用 · 异常追踪']].map(([k,i,l,d])=>'<button class="module-card" data-go="'+k+'"><span class="module-num"><span class="module-icon">'+i+'</span>↗</span><h3>'+l+'</h3><div class="module-mini">'+d+'</div><div class="module-foot"><span>'+ (k==='data'?'已发布真实行情':k==='monitor'?'实际事件记录':'人工与 AI 共用工具')+'</span><b>进入模块</b></div></button>').join('')+'</div>'+
 '<div class="section-title">最近研究</div>'+card('实验记录',runsTable(S.runs.slice(0,8)))+
 '<div class="hint">当前使用固定 16 股历史行情进行功能联调。数据存在选样与历史复权限制；收益表现仅作研发参考。</div>';
}
function moduleHome(kind){
 const m=MODULES[kind],tasks=S.tasks.filter(t=>t.module===kind);
 return header(m.title,m.desc,btn('新建研究任务','new','data-module="'+kind+'"',true))+
 '<div class="step-nav">'+m.steps.map((x,i)=>'<div class="step"><span class="step-number">'+(i+1)+'</span><div><strong>'+x+'</strong><small>'+m.roles[i]+'</small></div></div>').join('')+'</div>'+
 card('研究任务',tasks.length?table(['任务','当前版本','最新实验','下一步','更新时间'],tasks.map(t=>{const r=latest(t);const next=r?.status==='completed'?4:r?m.compute:0;return [link(t.inputs.name,kind+'/'+next+'/'+t.id),'<span class="badge">v'+t.revision+'</span>',r?badge(r.status):'尚未计算',link(r?.status==='completed'?'查看结果':'继续研究',kind+'/'+next+'/'+t.id),when(t.updated)]})):empty('创建第一个任务，从研究目标开始；可以随时跳到已有资产继续工作。'))+
 card('可复用的'+(kind==='strategy'?'因子':kind==='portfolio'?'策略':'因子')+'资产',assetTable(kind==='portfolio'?'strategy':'factor',6),'result-card');
}
function field(k,value,t){
 const label=LABEL[k],c=C.capabilities,release=C.catalog.releases.find(r=>r.version===t.inputs.data_version);
 let input,help='';
 if(k==='reason'||k==='expression'){input='<textarea name="'+k+'" class="'+(k==='expression'?'code':'')+'" rows="4" maxlength="2000">'+esc(value)+'</textarea>';help=k==='expression'?'使用 close、open、high、low、volume 和已开放函数；禁止未来位移与任意 Python。':'写清经济假设、适用范围及计划比较的基线。'}
 else if(k==='data_version'){input='<select name="'+k+'">'+C.catalog.releases.filter(r=>r.status==='published').map(r=>'<option value="'+esc(r.version)+'" '+(r.version===value?'selected':'')+'>'+esc(r.version)+' · '+r.quality.start+' — '+r.quality.end+'</option>').join('')+'</select>';help='固定版本可复现。更换版本后请核对起止日期。'}
 else if(k==='preprocess'){input='<select name="'+k+'">'+c.preprocess.map(x=>'<option '+(x===value?'selected':'')+' value="'+x+'">'+({none:'不处理',zscore:'截面标准化',winsor_zscore:'去极值 + 截面标准化'}[x]||x)+'</option>').join('')+'</select>'}
 else if(['start','end'].includes(k)){input='<input type="date" name="'+k+'" value="'+esc(value)+'" min="'+esc(release?.quality.start)+'" max="'+esc(release?.quality.end)+'" required>'}
 else if(['horizon','groups','rebalance','top_n','cost_bps'].includes(k)){
  const bounds=[...(c.limits?.[k]||[0,200])];if(k==='top_n')bounds[1]=Math.min(bounds[1],release?.symbols.length||60);if(k==='groups')bounds[1]=Math.min(bounds[1],Math.floor((release?.symbols.length||60)/2));
  input='<input type="number" name="'+k+'" value="'+esc(value)+'" min="'+bounds[0]+'" max="'+bounds[1]+'" step="'+(k==='cost_bps'?'0.1':'1')+'" required>';
  help= k==='cost_bps'?'1 bps = 0.01%。统一单边综合成本假设。':k==='horizon'?'T 日因子对应 T+1 开盘至 T+h+1 开盘的收益。':k==='groups'?'Q1 为因子高值层，每层至少 2 只股票。':k==='rebalance'?'使用已有引擎的次日开盘向量化回测。':'参数范围来自服务端引擎能力。';
 } else input='<input name="'+k+'" value="'+esc(value)+'" maxlength="80" required>';
 return '<label class="field '+(['reason','expression','data_version'].includes(k)?'full':'')+'"><span>'+label+'</span>'+input+'<small class="help">'+help+'</small></label>';
}
function assetPicker(key,t){
 const kind=key==='factors'?'factor':'strategy',assets=S.assets.filter(a=>a.kind===kind),chosen=t.inputs[key]||[];
 return '<div class="full"><p class="fine">'+(key==='factors'?'选择已有因子并设置相对权重，计算时按权重合计归一化。未审核资产可用于探索。':'选择相同日期区间的策略回测。资金权重合计不超过 100%，剩余部分为零收益现金。')+'</p>'+
 (assets.length?table(['选用','研究资产','审核','权重（%）'],assets.map(a=>{const v=chosen.find(x=>x.id===a.id);return ['<input type="checkbox" name="asset" value="'+a.id+'" '+(v?'checked':'')+' aria-label="选用 '+esc(a.name)+'">',link(a.name,'report/'+a.id)+'<small class="block">'+a.id+'</small>',badge(a.review),'<input class="weight-input" aria-label="'+esc(a.name)+' 权重" type="number" name="weight:'+a.id+'" value="'+(v?v.weight*100:100)+'" min="0.01" max="100" step="0.01">']})):empty('尚无可复用的'+(kind==='factor'?'因子':'策略')+'。请先完成一个真实计算实验。'))+'</div>';
}
function taskPage(t,stage){
 const m=MODULES[t.module],r=latest(t),report=r?reportCache[r.id]:null,fields=m.fields[stage]||[],locked=r&&(['queued','running'].includes(r.status)||r.review==='pending');
 const form=fields.length?'<form id="step-form" data-task="'+t.id+'" data-revision="'+t.revision+'"><fieldset '+(locked?'disabled':'')+'><div class="form-grid">'+fields.map(k=>['factors','strategies'].includes(k)?assetPicker(k,t):field(k,t.inputs[k],t)).join('')+'</div><div class="form-actions"><button class="btn primary" type="submit">保存当前步骤</button>'+(t.module==='factor'&&stage===1?btn('校验表达式','validate'):'')+'<span id="dirty-label" class="fine">版本 v'+t.revision+' · 已保存</span></div></fieldset></form>':'';
 let content=form;
 if(stage===m.compute)content+=(fields.length?'<div class="hint">保存参数后执行。输入快照、数据版本与完整报告自动保留。</div>':'<p class="fine">调用现有 ResearchEngine 进行实际计算，重复运行相同版本将返回已有实验。</p>')+'<div class="form-actions">'+btn(r?.status==='completed'?'查看本版计算结果':'运行'+(t.module==='factor'?'因子检验':t.module==='strategy'?'策略回测':'组合分析'),'run',locked?'disabled':'',true)+(r&&['queued','running'].includes(r.status)?btn('取消实验','cancel','data-id="'+r.id+'"'):'')+'</div>';
 if(r)content+='<div class="run-line">'+badge(r.status)+' <span>'+esc(r.id)+'</span> · v'+r.task_revision+(r.error?'<p class="error-text">'+esc(r.error)+'</p>':'')+'</div>';
 if(stage>=m.compute&&report?.report)content+=reportView(report,stage===4?'screen':'all');
 else if(stage>=m.compute&&!r)content+=empty('当前版本尚无计算结果。完成参数配置后运行实际计算。');
 if(stage===4&&r?.status==='completed')content+=submissionForm(t,r);
 if(stage===5)content+='<div class="hint">实验结果已自动留档，可供下游研究。人工通过后增加“已审核”标识；不会自动投放资金。</div>'+assetTable(t.module,8,t.id);
 const older=S.runs.filter(x=>x.task_id===t.id&&x.task_revision!==t.revision);
 if(older.length)content+='<details class="small-details"><summary>历史实验（'+older.length+'）· 不代替当前版本证据</summary>'+runsTable(older)+'</details>';
 return header(m.title,m.desc,btn('返回任务列表','module-list'))+
 '<div class="card taskbar"><div class="taskbar-left"><span class="field-label">当前任务</span><select id="task-picker" aria-label="当前研究任务">'+S.tasks.filter(x=>x.module===t.module).map(x=>'<option value="'+x.id+'" '+(x.id===t.id?'selected':'')+'>'+esc(x.inputs.name)+'</option>').join('')+'</select><span class="badge">v'+t.revision+'</span></div>'+btn('新建任务','new','data-module="'+t.module+'"')+'</div>'+
 '<div class="step-nav">'+m.steps.map((x,i)=>'<button class="step" data-go="'+t.module+'/'+i+'/'+t.id+'" aria-current="'+(i===stage?'step':'false')+'"><span class="step-number">'+(i+1)+'</span><div><strong>'+x+'</strong><small>'+m.roles[i]+'</small></div></button>').join('')+'</div>'+
 '<div class="workspace-grid"><div>'+card('<span class="stage-id">'+(stage+1)+'</span> '+m.steps[stage],(locked?'<div class="hint">当前版本'+(r.review==='pending'?'正在审核，退回后可继续修改。':'正在计算，完成或取消后可修改。')+'</div>':'')+content)+'</div><aside id="agent-panel">'+agentPanel(t,stage)+'</aside></div>'+
 '<div class="next-row">'+(stage?btn('← 上一步','prev'):'<span></span>')+(stage<5?btn('下一步：'+m.steps[stage+1]+' →','next'):'<span></span>')+'</div>';
}
function metricValue(k,v){return typeof v==='number'?(['max_drawdown','total_return','annual_return','volatility','daily_one_way_turnover','cash_weight'].includes(k)?num(v*100,2)+'%':num(v,['observations','valid_days'].includes(k)?0:4)):'—'}
function chart(points,title){
 const values=(points||[]).filter(p=>typeof p.value==='number'&&Number.isFinite(p.value));
 if(values.length<2)return '';
 const min=Math.min(...values.map(p=>p.value)),max=Math.max(...values.map(p=>p.value)),range=max-min||1;
 const stride=Math.max(1,Math.floor(values.length/400)),pts=values.filter((_,i)=>i%stride===0||i===values.length-1);
 const coords=pts.map(p=>{const i=values.indexOf(p);return (38+i/(values.length-1)*640).toFixed(2)+','+(118-(p.value-min)/range*92).toFixed(2)}).join(' ');
 return '<figure class="chart"><figcaption>'+title+'</figcaption><svg viewBox="0 0 700 155" role="img" aria-label="'+esc(title)+'"><line x1="38" y1="118" x2="680" y2="118" stroke="#e6e0ed"/><polyline fill="none" stroke="#65358d" stroke-width="1.7" points="'+coords+'"/><text x="3" y="28">'+num(max,2)+'</text><text x="3" y="120">'+num(min,2)+'</text><text x="38" y="145">'+esc(values[0].date)+'</text><text x="600" y="145">'+esc(values.at(-1).date)+'</text></svg><small>展示 '+values.length+' 个交易日，完整数据可导出报告。</small></figure>';
}
function reportView(job,mode='all'){
 const r=job.report,screen=S.runs.find(x=>x.id===job.id)?.screen||S.assets.find(x=>x.id===job.id)?.screen;
 if(!r)return '<div class="hint">'+esc(job.error||'报告尚未生成')+'</div>';
 let body='<div class="result-metrics">'+Object.entries(r.summary||{}).filter(([k])=>METRIC[k]).map(([k,v])=>'<div><small>'+METRIC[k]+'</small><b>'+metricValue(k,v)+'</b></div>').join('')+'</div>';
 if(mode==='all'){
  body+=chart(r.curve||r.daily_rank_ic,r.curve?'研究净值（含成本假设）':'逐日 Rank IC');
  if(r.quantiles)body+=card('因子分层前瞻收益',table(['分层','平均前瞻收益','有效天数'],r.quantiles.map(q=>[esc(q.group),num(q.mean_forward_return*100,3)+'%',q.days]))+'<div class="hint">'+esc(r.labels?.quantiles)+'</div>','result-card');
  if(r.segments?.length){const keys=job.kind==='factor'?['rank_ic_mean','ic_ir','valid_days']:['total_return','sharpe','max_drawdown'];body+=card('研发分段对照',table(['区间',...keys.map(k=>METRIC[k])],r.segments.map(s=>[esc(s.name),...keys.map(k=>metricValue(k,s[k]))]))+'<div class="hint">可反复查看的研发对照；不作为受保护的独立留出验证。</div>','result-card')}
  if(r.correlations)body+=card('基线相关性',table(['基线','平均秩相关'],r.correlations.map(x=>[esc(x.name),num(x.mean_rank_correlation)])),'result-card');
  if(r.positions)body+=card('最后一期研究持仓',table(['证券','权重'],r.positions.map(x=>[esc(x.symbol),num(x.weight*100,2)+'%'])),'result-card');
 }
 body+='<div class="checks">'+(r.checks||[]).map(c=>'<p>'+badge(c.status)+' <b>'+esc(c.name)+'</b> '+esc(c.detail)+'</p>').join('')+'</div>';
 if(screen)body+='<div class="hint '+(screen.eligible?'success':'warning')+'"><b>'+ (screen.eligible?'达到研发候选筛选条件':'保留实验，暂不送审')+'</b><br>'+esc(screen.reasons.join('；')||'仍需人工结合完整证据审查。')+'<br><small>规则：'+esc(screen.policy.version)+' · 不是显著性证明或资金授权</small></div>';
 body+='<details class="small-details"><summary>数据依据、限制与固定输入</summary><p class="fine">报告 SHA-256：'+esc(job.report_sha256)+'</p><pre class="json">'+json({data:r.data,inputs:job.snapshot,limitations:r.limitations,engine:r.engine,code:r.code,screen:screen?.policy})+'</pre></details><div class="form-actions"><a class="btn" href="/api/runs/'+job.id+'/export" download>导出完整报告 JSON</a></div>';
 return body;
}
function submissionForm(t,r){return '<div class="hint">当前审核状态：'+badge(r.review)+'。审核登记用途为研究资产；无任何实盘权限。</div>'+(['not_submitted','returned'].includes(r.review)?'<form id="submission"><label class="field"><span>提交依据</span><textarea name="note" required minlength="4" maxlength="2000" placeholder="说明结果、已知限制和复核要点"></textarea></label><div class="form-actions"><button class="btn primary" '+(!r.screen.eligible?'disabled':'')+'>提交当前版本研究审核</button></div></form>':'')}
function agentPanel(t,stage){
 const jobs=S.agents.filter(a=>a.task_id===t.id),a=jobs.find(x=>x.id===aiSelected)||jobs[0],m=MODULES[t.module],hasFields=!!m.fields[stage]?.length;
 return card(m.roles[stage],'<div class="agent-desc">当前步骤：'+m.steps[stage]+'。AI 只能使用该步骤开放的工具，审批始终由人工执行。</div><form id="assistant-form"><label class="field"><span>交给助手的任务</span><textarea name="message" minlength="3" maxlength="2000" required placeholder="说明你的研究想法，或让助手完成当前步骤"></textarea></label><div class="agent-buttons"><button class="btn" name="intent" value="task_fill" '+(!hasFields?'disabled':'')+'>AI 建议填写</button><button class="btn primary" name="intent" value="task_stage">AI 执行本步骤</button></div></form>'+(!S.connection.configured?'<div class="hint warning">尚未连接模型。人工工具可正常使用；前往“AI 与方法”配置。</div>':'')+
 '<div class="section-title">实际运行记录</div>'+(jobs.length?'<select id="agent-picker" class="job-select" aria-label="助手运行历史">'+jobs.map(j=>'<option value="'+j.id+'" '+(j.id===a?.id?'selected':'')+'>'+when(j.created)+' · '+(STATUS[j.status]||j.status)+'</option>').join('')+'</select>':'')+
 (a?'<div class="job-summary">'+badge(a.status)+' <small>调用 '+a.usage.calls+' 次 · '+a.usage.tokens+' Tokens</small></div><p class="bubble user">'+esc(a.message)+'</p>'+
 (['running','queued'].includes(a.status)?btn('停止助手','cancel-ai','data-id="'+a.id+'"'):'')+
 '<ol class="trace">'+a.steps.map(s=>'<li><details><summary>'+esc(s.text)+' '+badge(s.status||'completed')+'</summary><small>'+when(s.at)+(s.duration_ms?' · '+num(s.duration_ms,0)+' ms':'')+'</small><pre>'+json(s.detail||s.selected_tools||{})+'</pre></details></li>').join('')+'</ol>'+
 (a.reply?'<p class="bubble">'+esc(a.reply)+'</p>':'')+(a.error?'<div class="hint error">'+esc(a.error)+'</div>':'')+
 (a.status==='completed'&&Object.keys(a.form_patch||{}).length?'<div class="hint">AI 字段建议，尚未保存（基于 v'+a.task_revision+'）。</div><pre class="json">'+json(a.form_patch)+'</pre>'+btn('采纳字段建议','apply-ai','data-id="'+a.id+'"',true):''):empty('尚无助手任务。启动后会显示模型选工具、工具参数、返回证据和异常。'))+
 '<div class="agent-note">展示可核验的动作记录，不展示模型私有推理。每轮最多 4 次工具调用、1 次实验；模型及失败消耗计入已授权额度。</div>');
}
function assetTable(kind,limit=50,taskId=null){
 const assets=S.assets.filter(a=>(!kind||a.kind===kind)&&(!taskId||a.task_id===taskId)).slice(0,limit);
 return assets.length?table(['研究资产','模块','审核状态','候选筛选','后续研究'],assets.map(a=>[link(a.name,'report/'+a.id)+'<small class="block">'+esc(a.id)+'</small>',MODULES[a.kind].title,badge(a.review),badge(a.screen.eligible?'pass':'warn',a.screen.eligible?'候选':'探索资产'),a.kind!=='portfolio'?btn(a.kind==='factor'?'用于策略':'用于组合','reuse','data-id="'+a.id+'" data-kind="'+a.kind+'"'):'研究方案留档'])):empty('没有符合条件的研究资产。所有实验仍保留在运行记录中。');
}
function assetsPage(){return header('研究资产','计算成功的资产可用于继续探索；人工审核作为单独的状态标识。')+card('因子、策略与组合',assetTable())+card('全部实验（含失败与未达标）',runsTable(S.runs),'result-card')}
function dataPage(){
 const releases=C.catalog.releases,release=releases.find(r=>r.version===dataVersion)||releases[0];if(!release)return header('数据资源','暂无真实数据版本。');
 dataVersion=release.version;const q=release.quality;
 return header('数据资源','先使用已发布真实行情支持研究。采集、清洗和更新调度按本期范围后续完善。')+
 '<div class="card taskbar"><label>发布版本 <select id="data-version">'+releases.map(r=>'<option '+(r.version===release.version?'selected':'')+' value="'+esc(r.version)+'">'+esc(r.version)+'</option>').join('')+'</select></label>'+badge('pass','已发布')+'</div>'+
 '<div class="kpis">'+[['证券数',release.symbols.length],['行情行数',q.rows],['交易日数',q.trading_days],['截至日期',q.end]].map(([k,v])=>'<div class="card kpi"><small>'+k+'</small><strong class="compact">'+esc(v)+'</strong></div>').join('')+'</div>'+
 '<div class="grid-2">'+card('查询真实行情','<form id="data-preview" class="form-grid"><label class="field"><span>证券</span><select name="symbol">'+release.symbols.map(x=>'<option>'+esc(x)+'</option>').join('')+'</select></label><label class="field"><span>开始日期</span><input type="date" name="start" value="'+q.start+'" min="'+q.start+'" max="'+q.end+'"></label><label class="field"><span>结束日期</span><input type="date" name="end" value="'+q.end+'" min="'+q.start+'" max="'+q.end+'"></label><div class="form-actions"><button class="btn primary">查询样本</button></div></form>')+
 card('发布质量记录','<p class="fine">来源：'+esc(C.catalog.source||'公开行情 / Tencent ifzq')+'</p><p>'+q.start+' — '+q.end+'</p><p>发布状态：'+esc(q.status)+'</p><div class="pill-list">'+q.checks.map(x=>'<span class="badge">'+esc(x)+'</span>').join('')+'</div><details class="small-details"><summary>来源限制与版本校验值</summary><pre class="json">'+json({manifest_sha256:release.manifest_sha256,limitations:q.limitations,coverage:q.coverage})+'</pre></details>')+'</div>'+
 (preview?card('查询结果（只读）',previewTable(preview),'result-card'):'')+
 '<div class="hint warning">当前为固定 16 股技术联调股票池；后复权历史可能修订，未覆盖历史 ST、停牌、涨跌停及容量。请勿将样本回测视为全市场结论。</div>';
}
function previewTable(p){
 const rows=p.rows||p.data||[];
 if(!Array.isArray(rows))return '<pre class="json">'+json(p)+'</pre>';
 if(!rows.length)return empty('该范围没有返回行情记录。');
 const keys=Object.keys(rows[0]);return table(keys.map(esc),rows.slice(0,30).map(r=>keys.map(k=>esc(r[k]))))+'<small>仅展示前 30 行。计算服务使用固定版本的完整区间数据。</small>';
}
function monitor(){const failures=S.runs.filter(r=>['failed','interrupted'].includes(r.status));return header('运行监控','查看真实计算队列、AI 工具调用和研究异常。尚未接入实盘账户。')+
 card('待处理异常',failures.length?table(['实验','状态','原因'],failures.map(r=>[link(r.name,'report/'+r.id),badge(r.status),esc(r.error||'服务重启导致中断，可重新发起')])):empty('当前没有失败或中断的实验。'))+
 card('计算队列',runsTable(S.runs.slice(0,20)),'result-card')+
 card('操作记录',table(['时间','动作','来源','说明'],S.events.slice(0,30).map(e=>[when(e.at||e.created),esc(e.action),esc(e.source),esc(e.detail)])),'result-card')}
function reviewPage(){
 const selected=route()[1],r=S.runs.find(x=>x.id===selected)||S.runs.find(x=>x.review==='pending'),full=r?reportCache[r.id]:null,pending=S.runs.filter(x=>x.review==='pending');
 return header('研究审核','审查固定版本的研究依据与限制；这里的批准只登记研究资产。')+
 '<div class="review-layout"><section class="card review-list">'+(pending.length?pending.map(x=>'<button class="review-item" data-go="review/'+x.id+'" aria-pressed="'+(x.id===r?.id)+'">'+badge(x.review)+'<strong>'+esc(x.name)+'</strong><p>'+esc(x.id)+'</p></button>').join(''):empty('没有待审核候选。'))+'</section><div>'+
 (full?card(esc(r.name),'<p class="fine">报告版本：'+esc(full.task_revision||'历史实验')+' · '+esc(full.id)+'</p><p>'+esc(full.submission?.note||'')+'</p>'+reportView(full,'screen')+(full.review==='pending'?'<form id="review-form" data-id="'+full.id+'"><label class="field"><span>审核依据（必填）</span><textarea name="note" minlength="4" required maxlength="2000"></textarea></label><div class="form-actions"><button class="btn primary" name="decision" value="approve">通过研究审核</button><button class="btn" name="decision" value="return">退回修改</button><button class="btn" name="decision" value="reject">不予登记</button></div></form>':badge(full.review))):card('审核边界',empty('通过筛选并提交的研究候选将显示在这里。')))+
 '<div class="hint">当前为 SSH 隔离的内部研发工作区，操作人记为研究责任人。公司统一身份、独立审批人和资金权限将在正式机构端接入后实施。</div></div></div>';
}
function settings(){const u=S.connection.usage;return header('AI 与研究方法','配置真实模型连接和共享研究方法。密钥不会写入报告或代码仓库。')+
 '<div class="grid-2">'+card('模型连接','<form id="settings-form"><label class="field"><span>DeepSeek API Key</span><input type="password" name="api_key" autocomplete="off" placeholder="'+(S.connection.configured?'已连接；留空保持当前配置':'填写密钥')+'"></label><label class="field"><span>模型</span><input name="model" value="'+esc(u.model)+'" required></label><label class="field"><span>本版本累计 Tokens 上限</span><input type="number" name="token_limit" min="'+(u.tokens+u.reserved+u.uncertain)+'" max="200000" value="'+u.token_limit+'" required></label><div class="form-actions"><button class="btn primary">保存连接</button></div></form><p class="fine">已用 '+u.tokens+' · 预留 '+u.reserved+' · 待核对 '+u.uncertain+' Tokens。密钥仅保留在服务进程内存，服务器重启后需重新配置。</p>')+
 card('研究方法 · v'+S.method.version,'<form id="method-form"><label class="field"><span>助手共享方法与约束</span><textarea name="prompt" minlength="10" maxlength="3000" rows="10" required>'+esc(S.method.prompt)+'</textarea></label><div class="form-actions"><button class="btn primary">保存新版本</button></div></form><div class="hint">方法版本随每次 AI 任务冻结。工具权限和参数校验由服务端执行，修改提示词不能获取审批权限。</div>')+'</div>'+
 card('当前实现范围','<p>支持：真实行情查询、因子表达式、IC / 分层 / 分段诊断、已有引擎策略回测、固定权重组合分析、研究候选筛选、版本化审核和步骤助手。</p><p class="fine">后续：完整数据采集治理、严格独立留出验证、参数搜索、模拟成交、账户监控、企业身份权限、独立 Skill 版本发布与 Agent 训练。</p>','result-card')}
function render(){
 if(!S||!C)return;const p=route(),kind=p[0];let html;
 if(MODULES[kind]){const t=task(),stage=Number(p[1]);html=t&&Number.isInteger(stage)&&stage>=0&&stage<6?taskPage(t,stage):moduleHome(kind)}
 else if(kind==='data')html=dataPage();
 else if(kind==='monitor')html=monitor();
 else if(kind==='assets')html=assetsPage();
 else if(kind==='review')html=reviewPage();
 else if(kind==='settings')html=settings();
 else if(kind==='report'){const r=reportCache[p[1]];html=header('研究报告',r?esc(r.name)+' · '+esc(r.id):'正在读取报告')+(r?card('固定输入与计算证据',badge(r.status)+reportView(r)):'')}
 else html=overview();
 document.getElementById('app').innerHTML=shell(html);lastPaint=JSON.stringify(S);document.body.classList.remove('menu-open');
}
async function refresh(force=false){
 const next=await api('v3/state');S=next;if(!C||force)C=await api('catalog');
 const p=route(),t=task();let rid=p[0]==='report'?p[1]:p[0]==='review'?(p[1]||S.runs.find(r=>r.review==='pending')?.id):latest(t)?.id;
 if(rid)reportCache[rid]=await api('runs/'+rid);
 if(force||lastPaint!==JSON.stringify(S)&&!dirty&&!document.activeElement?.closest('form')&&!document.activeElement?.closest('details'))render();
 else if(lastPaint!==JSON.stringify(S)){const e=document.getElementById('live-status');if(e)e.textContent='数据已更新 · 当前编辑已保留';}
}
async function saveForm(form){
 const t=task(),d=new FormData(form),patch={};
 for(const k of MODULES[t.module].fields[Number(route()[1])]){
  if(k==='factors'||k==='strategies'){patch[k]=d.getAll('asset').map(id=>({id,weight:Number(d.get('weight:'+id))/100}))}
  else patch[k]=['horizon','groups','rebalance','top_n','cost_bps'].includes(k)?Number(d.get(k)):String(d.get(k)||'');
 }
 const saved=await api('v3/tasks/update',{id:t.id,revision:Number(form.dataset.revision),patch});dirty=false;return saved;
}
document.addEventListener('input',e=>{if(e.target.closest('#step-form')){dirty=true;const x=document.getElementById('dirty-label');if(x)x.textContent='有未保存修改'}});
document.addEventListener('change',async e=>{try{
 if(e.target.id==='task-picker')go(task().module+'/'+route()[1]+'/'+e.target.value);
 if(e.target.id==='data-version'){dataVersion=e.target.value;preview=null;render()}
 if(e.target.id==='agent-picker'){aiSelected=e.target.value;render()}
}catch(err){toast(err.message,true)}});
document.addEventListener('submit',async e=>{
 e.preventDefault();if(busy)return;busy=true;
 try{
 const f=e.target,d=new FormData(f),t=task();
 if(f.id==='step-form'){await saveForm(f);toast('已保存当前步骤')}
 else if(f.id==='assistant-form'){
  if(dirty)throw Error('请先保存当前步骤参数，再交给 AI');
  const a=await api('assistant',{task_id:t.id,revision:t.revision,stage:Number(route()[1]),intent:e.submitter.value,message:d.get('message')});aiSelected=a.id;toast('助手已启动，执行记录将持续更新');
 }else if(f.id==='submission'){const r=latest(t);await api('v3/tasks/submit',{id:t.id,revision:t.revision,run_id:r.id,note:d.get('note')});toast('已提交当前版本，等待人工审核')}
 else if(f.id==='review-form'){await api('review',{id:f.dataset.id,decision:e.submitter.value,note:d.get('note')});toast('审核决定已记录')}
 else if(f.id==='settings-form'){await api('connection',{api_key:d.get('api_key'),model:d.get('model'),token_limit:Number(d.get('token_limit'))});f.reset();toast('连接配置已保存')}
 else if(f.id==='method-form'){await api('method',{prompt:d.get('prompt')});toast('研究方法已保存为新版本')}
 else if(f.id==='data-preview'){preview=await api('preview',{data_version:dataVersion,symbols:[d.get('symbol')],start:d.get('start'),end:d.get('end')})}
 await refresh(true);
 }catch(err){toast(err.message,true)}finally{busy=false}
});
document.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-go]');if(nav){go(nav.dataset.go);return}
 const b=e.target.closest('[data-action]');if(!b||busy)return;const action=b.dataset.action,t=task();busy=true;
 try{
  if(action==='menu'){document.body.classList.toggle('menu-open');return}
  if(action==='refresh'){if(dirty)throw Error('请先保存当前修改，再刷新');await refresh(true);return}
  if(action==='new'){if(dirty)throw Error('请先保存当前修改');const nt=await api('v3/tasks',{module:b.dataset.module});S.tasks.unshift(nt);go(nt.module+'/0/'+nt.id);return}
  if(action==='module-list'){go(t.module);return}
  if(action==='next'||action==='prev'){go(t.module+'/'+(Number(route()[1])+(action==='next'?1:-1))+'/'+t.id);return}
  if(action==='validate'){const value=document.querySelector('[name="expression"]').value;const v=await api('validate',{expression:value});toast('表达式校验通过：'+v.normalized);return}
  if(action==='run'){if(dirty)throw Error('请先保存当前步骤参数');await api('v3/tasks/run',{id:t.id,revision:t.revision});toast('已提交真实计算')}
  if(action==='cancel'){await api('cancel',{id:b.dataset.id});toast('已停止接收此实验结果')}
  if(action==='cancel-ai'){await api('assistant/cancel',{id:b.dataset.id});toast('助手已停止后续调用')}
  if(action==='apply-ai'){if(dirty)throw Error('请先保存手工修改，避免覆盖');await api('v3/assistant/apply',{id:b.dataset.id});toast('已采纳并保存为任务参数')}
  if(action==='reuse'){const kind=b.dataset.kind==='factor'?'strategy':'portfolio',a=S.assets.find(x=>x.id===b.dataset.id),inputs={};inputs[kind==='strategy'?'factors':'strategies']=[{id:a.id,weight:1}];if(kind==='strategy'&&a.data)Object.assign(inputs,{data_version:a.data.version,start:a.data.start,end:a.data.end});const nt=await api('v3/tasks',{module:kind,inputs});S.tasks.unshift(nt);go(kind+'/0/'+nt.id);return}
  await refresh(true);
 }catch(err){toast(err.message,true)}finally{busy=false}
});
window.addEventListener('hashchange',()=>{dirty=false;aiSelected='';refresh(true).catch(e=>toast(e.message,true))});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
refresh(true).catch(e=>{document.getElementById('app').innerHTML='<div class="connection-error"><h1>暂时无法连接研究服务</h1><p>'+esc(e.message)+'</p><p>请检查服务器服务及 SSH 连接。</p><button class="btn" onclick="location.reload()">重试</button></div>'});
refreshTimer=setInterval(()=>{if(!document.hidden&&!busy)refresh().catch(()=>{const el=document.getElementById('live-status');if(el)el.textContent='连接中断 · 等待恢复'})},5000);
