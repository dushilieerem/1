'use strict';
/* 策略研究 V5（交互原型，场景数据）
   与因子工厂同一套研究框架：课题 → 研究树 → 台账 K → 校正门槛 → 封存验证 → 独立复核 → 入库。
   策略特有的证据：扣费后超额、换手与费用拖累、成本敏感性、参数邻域稳健性。 */

/* ---------- research policy (defaults, to be calibrated by the institution) ---------- */
const POL = { ex: 3.0, dd: 12, to: 15, nb: 6, vex: 0, vir: .3, cost: .2 };
const needIR = K => +(0.5 + 0.15 * Math.sqrt(2 * Math.log(Math.max(1, K)))).toFixed(2);
const FAC = {
  rev5: { n: ['5日反转', '5-day reversal'], src: 'lib', speed: 1.6, a: 6.6 },
  abto: { n: ['换手率异动', 'Abnormal turnover'], src: 'lib', speed: 1.3, a: 4.6 },
  crm: { n: ['一致预期调整动量', 'Consensus revision momentum'], src: 'lib', speed: .45, a: 3.8 },
  pead: { n: ['盈余公告漂移 PEAD', 'Post-earnings drift (PEAD)'], src: 'lib', speed: .35, a: 3.2 },
  lowvol: { n: ['低波动', 'Low volatility'], src: 'lib', speed: .5, a: 2.4 },
  sv12: { n: ['SV01_0012 ROE 稳定性', 'SV01_0012 ROE stability'], src: 'imp', speed: .2, a: 2.0 }
};
const SCOPE = ['中证800 历史时点成分 · 基准 中证800 · 研发 2019–2024 · 封存 2025 · 双边成本 0.2%', 'CSI 800 point-in-time · benchmark CSI 800 · dev 2019–2024 · sealed 2025 · 0.2% round-trip'];

/* deterministic scenario backtest: same recipe → same result (a recompute does not add to K) */
function bt(p) {
  const fs = p.f.map(k => FAC[k]); const speed = fs.reduce((a, x) => a + x.speed, 0) / fs.length;
  const alpha = fs.reduce((a, x) => a + x.a * Math.exp(-p.reb * x.speed / 22), 0) * [1, .78, .6][fs.length - 1];
  const to = +(speed * 120 / p.reb * (p.buf ? .62 : 1) * Math.pow(60 / p.N, .25)).toFixed(1);
  const gross = +(alpha - (p.N - 50) * .012).toFixed(1);
  const drag = +(to * POL.cost).toFixed(1), ex = +(gross - drag).toFixed(1), te = 4.2 + 40 / p.N;
  const ir = +(ex / te).toFixed(2), dd = +(5.5 + te * .9 - (p.buf ? .4 : 0)).toFixed(1);
  return { gross, drag, ex, ir, dd, to, ex2: +(gross - 2 * drag).toFixed(1) };
}
function nbhd(p) { let ok = 0; const grid = []; for (const N of [p.N - 20, p.N, p.N + 20]) { const row = []; for (const reb of [5, 10, 20]) { const r = bt({ ...p, N: Math.max(20, N), reb }); const g = r.ex >= POL.ex && r.ir >= .5; ok += g; row.push({ N: Math.max(20, N), reb, r, g }); } grid.push(row); } return { ok, grid }; }
const gates = (m, K, nb) => [
  [t('扣费后年化超额', 'Net annual excess'), `${m.ex}%`, `≥ ${POL.ex}%`, m.ex >= POL.ex],
  [t('信息比率（按试验数校正）', 'Information ratio (trial-adjusted)'), m.ir.toFixed(2), `≥ ${needIR(K).toFixed(2)} · K=${K}`, m.ir >= needIR(K)],
  [t('相对基准最大回撤', 'Max relative drawdown'), `${m.dd}%`, `≤ ${POL.dd}%`, m.dd <= POL.dd],
  [t('单边年换手', 'One-way annual turnover'), `${m.to}×`, `≤ ${POL.to}×`, m.to <= POL.to],
  [t('2 倍成本下超额', 'Excess at 2× cost'), `${m.ex2}%`, '> 0', m.ex2 > 0],
  [t('参数邻域达标', 'Parameter neighbourhood'), nb == null ? t('未检验', 'Not run') : `${nb}/9`, `≥ ${POL.nb}/9`, nb == null ? null : nb >= POL.nb]
];
const pass = (m, K, nb) => gates(m, K, nb).every(g => g[3] !== false);

/* ---------- scenario topics ---------- */
const R = (f, N, reb, buf) => ({ f, N, reb, buf: !!buf });
const TOPICS = [
  { id: 'S1', name: ['拥挤反转与预期修正双因子', 'Crowded reversal + revision momentum'], status: 'run', budget: 10, tokens: 9,
    act: ['研究系统正在推进：首版换手过高', 'Research system working: first version turns over too much'],
    nodes: [{ id: 'V1', parent: null, by: 'agent', title: ['等权双因子 · 前 50 · 5 日调仓', 'Equal-weight pair · top 50 · 5-day'], status: 'run', rc: R(['rev5', 'crm'], 50, 5),
      why: ['反转捕捉短期过度反应，预期修正提供慢变量，两者相关低，组合后预期更稳。', 'Reversal captures short-term overreaction, revisions add a slow signal; low correlation should stabilise the mix.'], steps: [{ k: 'C' }, { k: 'B', K: 1 }] }] },
  { id: 'S2', name: ['预期修正低换手组合', 'Low-turnover revision strategy'], status: 'review', budget: 8, tokens: 14,
    act: ['候选 SC1 已提交审查', 'Candidate SC1 submitted for review'],
    nodes: [
      { id: 'V1', parent: null, by: 'agent', title: ['预期修正 + PEAD · 前 30 · 5 日', 'Revisions + PEAD · top 30 · 5-day'], status: 'fail', rc: R(['crm', 'pead'], 30, 5),
        why: ['两个慢变量都反映盈利信息扩散，换手天然低。', 'Both slow signals reflect earnings-information diffusion, so turnover is naturally low.'],
        steps: [{ k: 'C' }, { k: 'B', K: 1 }, { k: 'D', txt: ['超额略低于门槛、跟踪误差大 → 拉长调仓、扩大持仓', 'Excess just below the bar with high tracking error → slower rebalance, more names'] }] },
      { id: 'V2', parent: 'V1', by: 'agent', title: ['前 80 · 10 日调仓', 'Top 80 · 10-day'], status: 'review', rc: R(['crm', 'pead'], 80, 10),
        why: ['降低跟踪误差，减少单年依赖。', 'Lower tracking error and less dependence on a single year.'],
        steps: [{ k: 'C' }, { k: 'B', K: 2 }, { k: 'R', nb: 8 }, { k: 'D', txt: ['研发门槛全部达标 → 申请封存验证', 'All development gates passed → request sealed validation'] }, { k: 'V', ex: 2.4, ir: .52 }, { k: 'D', txt: ['封存通过 → 提交审查，候选 SC1', 'Sealed passed → submitted as SC1'] }] }] },
  { id: 'S3', name: ['质量与低波（导入因子）', 'Quality + low vol (imported factor)'], status: 'aband', budget: 6, tokens: 11,
    act: ['已放弃：扣费后无稳定超额', 'Abandoned: no stable net excess'],
    nodes: [
      { id: 'V1', parent: null, by: 'agent', title: ['ROE 稳定性 + 低波 · 前 50 · 10 日', 'ROE stability + low vol · top 50 · 10-day'], status: 'fail', rc: R(['sv12', 'lowvol'], 50, 10),
        why: ['防御型组合，验证在 A 股是否有扣费后超额。', 'A defensive mix; check for net excess in A-shares.'],
        steps: [{ k: 'C' }, { k: 'B', K: 1 }, { k: 'D', txt: ['超额不足 → 改 20 日调仓', 'Too little excess → 20-day rebalance'] }] },
      { id: 'V2', parent: 'V1', by: 'agent', title: ['20 日调仓', '20-day rebalance'], status: 'aband', rc: R(['sv12', 'lowvol'], 50, 20),
        why: ['降低成本。', 'Lower cost.'],
        steps: [{ k: 'C' }, { k: 'B', K: 2 }, { k: 'X', txt: ['仍低于门槛，且导入因子未经 V5 复核 → 放弃，建议先在因子工厂复核 SV01_0012', 'Still below the bar and the imported factor is unreviewed → abandoned; review SV01_0012 in the factor factory first'] }] }] },
  { id: 'S4', name: ['北向持股增强', 'Northbound-holdings tilt'], status: 'wait', budget: 6, tokens: 1,
    act: ['等待因子：因子课题 T3 的数据请求 DR-12 尚未发布', 'Waiting for factor: data request DR-12 of factor topic T3 not yet published'], nodes: [] }
];
const SC = [{ id: 'SC1', topic: 'S2', node: 'V2', status: SV.flag('SC1') === 'done' ? 'approved' : (SV.flag('SC1') || 'pending'), time: '11-06 06:12',
  ai: [['机制清楚：两个盈利信息扩散类因子，换手 4 倍左右，成本拖累小。', 'Clear mechanism: two earnings-diffusion factors, ~4× turnover, small cost drag.'],
    ['参数邻域 8/9 达标，结果不依赖单一参数点。', 'Neighbourhood 8/9 passes; result does not hinge on one parameter point.'],
    ['封存 2025 超额 2.4%、IR 0.52，弱于研发期，属正常衰减范围。', 'Sealed 2025 excess 2.4%, IR 0.52 — weaker than development, within normal decay.'],
    ['风险：与 ST-02 共用 PEAD，进入组合前需看重叠率。', 'Risk: shares PEAD with ST-02; check overlap before portfolio use.']],
  limits: [['冲击成本与容量未建模；按双边 0.2% 估计。', 'Impact cost and capacity not modelled; 0.2% round-trip assumed.'], ['封存期仅 2025 一年。', 'Sealed period is 2025 only.']] }];

/* ---------- state ---------- */
const P = {
  key: 'strategy', title: ['策略研究', 'Strategy research'], tab: 'ops',
  tabs: [['ops'], ['wb'], ['review'], ['lib'], ['caps']],
  sel: 'S1', node: null, sysOn: !SV.flag('pause_S0'), sim: { on: true, i: 0 }, rv: { sel: 'SC1', ack: false }, libSel: null,
  wb: { topic: 'S1', node: null, tool: 'recipe', rc: null, last: null, nb: null, chat: null },
  feed: [['10:52:10', 'S2', ['候选 SC1 提交审查', 'Candidate SC1 submitted']], ['10:31:44', 'S3', ['课题放弃：扣费后无稳定超额', 'Topic abandoned: no stable net excess']], ['09:58:02', 'S4', ['等待因子 T3（DR-12）', 'Waiting for factor T3 (DR-12)']]]
};
const topic = id => TOPICS.find(x => x.id === id);
const nodeOf = (tp, id) => tp.nodes.find(x => x.id === id);
const K = tp => tp.nodes.reduce((a, n) => a + n.steps.filter(s => s.k === 'B').length, 0);
const lastB = n => [...n.steps].reverse().find(s => s.k === 'B');
const lastR = n => [...n.steps].reverse().find(s => s.k === 'R');
const lastV = n => [...n.steps].reverse().find(s => s.k === 'V');
const isRes = () => SV.role === 'researcher';
const fname = k => tx(FAC[k].n);
const feed = (tp, txt) => { P.feed.unshift([clock(), tp, txt]); P.feed = P.feed.slice(0, 30); };
const ST = { run: ['运行中', 'Running', 'live'], review: ['待复核', 'In review', 'purple'], wait: ['等待因子', 'Waiting for factor', 'amber'], aband: ['已放弃', 'Abandoned', 'gray'], paused: ['已暂停', 'Paused', 'gray'], done: ['已入库', 'Admitted', 'green'] };
const NST = { run: ['进行中', 'In progress', 'live'], fail: ['未达标', 'Below bar', 'red'], review: ['待复核', 'In review', 'purple'], aband: ['已放弃', 'Abandoned', 'gray'], human: ['人工进行中', 'Human, in progress', 'blue'], submitted: ['已提交审查', 'Submitted', 'purple'], approved: ['已入库', 'Admitted', 'green'], returned: ['已交回 Agent', 'Returned', 'gray'] };

/* ---------- shared fragments ---------- */
function recipe(rc) {
  return `<div class="recipe"><div><span>${t('因子与方向', 'Factors & direction')}</span>${rc.f.map(k => `${fname(k)}${FAC[k].src === 'imp' ? ` <span class="badge amber">${t('导入 · 未经 V5 复核', 'Imported · not V5-reviewed')}</span>` : ''}`).join('<br>')}</div>
  <div><span>${t('合成与选股', 'Combine & select')}</span>${rc.f.length > 1 ? t('等权 z 分数合成', 'Equal-weight z-score') : t('单因子', 'Single factor')} · ${t('前', 'top')} ${rc.N} ${t('只等权', 'equal-weight')}</div>
  <div><span>${t('调仓', 'Rebalance')}</span>${t(`每 ${rc.reb} 个交易日`, `every ${rc.reb} days`)}${rc.buf ? t(' · 缓冲区 1.5N', ' · buffer 1.5N') : ''}</div></div>
  <small style="display:block;margin-top:6px">${t('模板：A 股日频纯多头 · 收盘出信号、次日开盘成交', 'Template: A-share daily long-only · signal at close, fill next open')} · ${tx(SCOPE)}</small>`;
}
function gateTable(m, Kv, nb) {
  return `<table class="gates">${gates(m, Kv, nb).map(([n, v, need, ok]) => `<tr><td>${n}</td><td class="r">${v}</td><td class="r subtle">${need}</td><td class="r">${ok == null ? '<span class="subtle">—</span>' : ok ? '<span class="ok-t">✓</span>' : '<span class="bad-t">✗</span>'}</td></tr>`).join('')}</table>`;
}
function chips(tp, n) {
  return n.steps.map(s => {
    if (s.k === 'C') return `<span class="chip">${t('配方', 'Recipe')}</span>`;
    if (s.k === 'B') { const m = bt(n.rc), ok = pass(m, s.K, null); return `<button class="chip ${ok ? 'ok' : 'fail'}" data-a="report" data-v="${tp.id}|${n.id}|${s.K}">B${s.K} · ${t('超额', 'ex')} ${m.ex}% · IR ${m.ir.toFixed(2)}</button>`; }
    if (s.k === 'R') return `<span class="chip ${s.nb >= POL.nb ? 'ok' : 'fail'}">${t('邻域', 'Nbhd')} ${s.nb}/9</span>`;
    if (s.k === 'V') return `<span class="chip ${s.ex > POL.vex && s.ir >= POL.vir ? 'ok' : 'fail'}">${t('封存', 'Sealed')} · ${s.ex}% · IR ${s.ir}</span>`;
    return `<span class="chip dec">${tx(s.txt)}</span>`;
  }).join('<span class="arrow">›</span>');
}
function tree(tp, parent) {
  return tp.nodes.filter(n => n.parent === parent).map(n => `<div class="branch-wrap"><div class="branch ${n.by === 'human' ? 'human' : ''} ${n.status === 'aband' ? 'aband' : ''} ${P.node === n.id ? 'sel' : ''}" data-a="node" data-v="${n.id}">
    <div class="bh"><span class="hid">${n.id}</span><span class="bt">${tx(n.title)}</span>${SV.badge(NST[n.status])}<span class="by">${n.by === 'human' ? t('张新迪 · 人工', 'Zhang Xindi · human') : t('研究系统', 'Research system')}</span></div>
    <div class="steps">${chips(tp, n)}</div></div>${tp.nodes.some(x => x.parent === n.id) ? `<div class="children">${tree(tp, n.id)}</div>` : ''}</div>`).join('');
}

/* ---------- 研究运行 ---------- */
function pageOps() {
  const tp = topic(P.sel); if (!P.node && tp.nodes.length) P.node = tp.nodes[tp.nodes.length - 1].id;
  const n = P.node && nodeOf(tp, P.node);
  const tr = TOPICS.reduce((a, x) => a + K(x), 0), tk = TOPICS.reduce((a, x) => a + x.tokens, 0), pend = SC.filter(c => c.status === 'pending').length;
  const sys = `<div class="sys"><div class="sys-state"><span class="ico">⌁</span><div><b><span class="live-dot ${P.sysOn ? '' : 'off'}"></span> ${P.sysOn ? t('策略研究系统运行中', 'Strategy research system running') : t('策略研究系统已暂停', 'Strategy research system paused')}</b><small>${t('授权至 2026-11-30 · 投资负责人 批准', 'Authorised to 2026-11-30 by the investment lead')}</small></div></div>
    <div class="kpis"><div class="kpi"><span>${t('课题', 'Topics')}</span><b>${TOPICS.length}</b><small>${t(`运行 ${TOPICS.filter(x => x.status === 'run').length}`, `${TOPICS.filter(x => x.status === 'run').length} running`)}</small></div>
    <div class="kpi"><span>${t('本月回测（计入台账）', 'Backtests this month (ledger)')}</span><b>${tr}</b><small>/ 60</small></div><div class="kpi"><span>Token</span><b>${tk}k</b><small>/ 600k</small></div><div class="kpi"><span>${t('待复核候选', 'Candidates in review')}</span><b>${pend}</b></div></div>
    <button class="btn small" data-a="sys" ${SV.role === 'lead' ? '' : 'disabled'}>${P.sysOn ? t('暂停系统', 'Pause system') : t('恢复系统', 'Resume system')}</button></div>`;
  const board = `<div class="topic-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">${TOPICS.map(x => `<button class="topic ${x.id === P.sel ? 'sel' : ''}" data-a="topic" data-v="${x.id}"><div class="top"><span class="tid">${x.id}</span>${SV.badge(ST[x.status])}</div><h3>${tx(x.name)}</h3><div class="act">${tx(x.act)}</div>
    <div class="bar"><i style="width:${Math.min(100, K(x) / x.budget * 100)}%"></i></div><div class="meta"><span>${t('回测', 'Backtests')} <b>${K(x)}</b> / ${x.budget}</span><span>Token <b>${x.tokens}k</b></span></div></button>`).join('')}</div>`;
  let detail = `<div class="card"><div class="card-body empty"><b>${t('还没有版本', 'No versions yet')}</b>${tx(tp.act)}</div></div>`;
  if (n) {
    const b = lastB(n), m = bt(n.rc), r = lastR(n), v = lastV(n), Kn = K(tp);
    detail = `<div class="card"><div class="card-head"><div><h2>${n.id} · ${tx(n.title)}</h2><p>${tx(n.why)}</p></div>${SV.badge(NST[n.status])}</div><div class="card-body">
      ${recipe(n.rc)}
      ${b ? `<h3 style="margin:16px 0 8px">${t('最近一次回测', 'Latest backtest')} B${b.K} · ${t('门槛按课题当前', 'bar at current')} K=${Kn}</h3>${gateTable(m, Kn, r ? r.nb : null)}` : ''}
      ${v ? `<div class="hint ${v.ex > POL.vex && v.ir >= POL.vir ? 'success' : 'warning'}" style="margin:12px 0 0">${t('封存验证 2025', 'Sealed 2025')}：${t('超额', 'excess')} ${v.ex}% · IR ${v.ir} · ${t('每个候选只用一次', 'used once per candidate')}</div>` : ''}
      </div><div class="card-footer"><small>${t('所有回测进入课题台账；同一配方重算不计 K', 'Every backtest enters the topic ledger; recomputing the same recipe does not add to K')}</small><div class="row-flex" style="display:flex;gap:6px">
      ${b ? `<button class="btn small" data-a="report" data-v="${tp.id}|${n.id}|${b.K}">${t('查看报告', 'Report')}</button>` : ''}<button class="btn small" data-a="comment">${t('给研究意见', 'Comment')}</button><button class="btn small primary" data-a="takeover" data-v="${n.id}" ${isRes() ? '' : 'disabled'}>${n.by === 'human' ? t('打开工作台', 'Open workbench') : t('从这里接手', 'Take over from here')}</button></div></div></div>`;
  }
  return sys + SV.note(['<b>设计要点</b>：策略研究与因子工厂是同一套研究系统：S0 研究决策复用 F0 的决策引擎，只换动作白名单。策略特有的过拟合来源是参数和因子组合的反复试探，所以每次看过结果的回测都计入台账 K，信息比率门槛随 K 提高；另外要求成本翻倍仍有超额、参数邻域多数达标，防止挑中一个孤立的好参数。', '<b>Design</b>: strategy research reuses the factor research system: S0 reuses the F0 decision engine with a strategy action whitelist. Overfitting in strategies comes from repeatedly trying parameters and factor mixes, so every viewed backtest enters ledger K and the IR bar rises with K; strategies must also survive doubled costs and pass in most of the parameter neighbourhood.'])
    + board + `<div class="ops-grid"><div><div class="card"><div class="card-head"><div><h2>${t('研究树', 'Research tree')} · ${tp.id} ${tx(tp.name)}</h2><p>${t('每个节点是一个固定配方版本；修订、分支、放弃都留痕', 'Each node is a frozen recipe version; revisions, branches and drops are all recorded')}</p></div><button class="btn small" data-a="pausetopic" ${tp.status === 'run' || tp.status === 'paused' ? '' : 'disabled'}>${tp.status === 'paused' ? t('继续课题', 'Resume') : t('暂停课题', 'Pause topic')}</button></div><div class="card-body">${tp.nodes.length ? `<div class="tree">${tree(tp, null)}</div>` : `<div class="empty">${tx(tp.act)}<br><a href="factor.html#ops">${t('查看因子课题 T3 →', 'Open factor topic T3 →')}</a></div>`}</div></div>${detail}</div>
    <div class="side"><div class="card"><div class="card-head"><h2>${t('研究系统组成', 'System units')}</h2></div><div class="card-body"><div class="units">${UNITS.map(u => `<div class="unit ${u[3]}"><span class="ui">${u[0]}</span><div><b>${tx(u[1])}</b><small>${tx(u[2])}</small></div></div>`).join('')}</div></div></div>
    <div class="card"><div class="card-head"><h2>${t('实时动态', 'Live feed')}</h2></div><div class="card-body" style="padding-top:6px"><ul class="feed">${P.feed.map(([tm, tg, x]) => `<li><time>${tm}</time><span class="tg">${tg}</span>${tx(x)}</li>`).join('')}</ul></div></div></div></div>`;
}
const UNITS = [['S0', ['研究决策', 'Research decision'], ['复用 F0 决策引擎 · 每课题一个', 'Reuses the F0 engine · one per topic'], 'agent'], ['S1', ['因子选择', 'Factor selection'], ['从因子库检索、查相关与状态', 'Search library, correlations, status'], ''], ['S2', ['配方构造', 'Recipe builder'], ['在模板参数内生成配方', 'Builds recipes within template parameters'], ''], ['S3', ['回测与诊断', 'Backtest & diagnosis'], ['调用 RE 回测，解读成本与分年', 'Runs RE backtests; reads costs and years'], ''], ['S4', ['稳健性检验', 'Robustness'], ['参数邻域、成本敏感性', 'Neighbourhood, cost sensitivity'], ''], ['S5', ['独立复核', 'Independent review'], ['封存期 · 不共享研究上下文', 'Sealed period · no shared context'], 'indep']];

/* ---------- report ---------- */
function report(tp, n, Kat) {
  const m = bt(n.rc), r = lastR(n), nb = r ? r.nb : null, seed = (tp.id + n.id).split('').reduce((a, c) => a * 31 + c.charCodeAt(0), 7);
  const bm = SV.walk(seed, 72, .006, .05), net = bm.map((v, i) => v * Math.pow(1 + m.ex / 1200, i) * (1 + .012 * Math.sin(i / 7))), gr = bm.map((v, i) => v * Math.pow(1 + m.gross / 1200, i) * (1 + .012 * Math.sin(i / 7)));
  const years = [2019, 2020, 2021, 2022, 2023, 2024].map((y, i) => +(m.ex + [1.4, 3.1, -.8, -1.9, .6, -1.6][i] * (1 + (seed % 5) / 10)).toFixed(1));
  const g = nbhd(n.rc);
  return `<div class="metrics" style="grid-template-columns:repeat(5,minmax(0,1fr))">${[[t('扣费后年化超额', 'Net excess'), m.ex + '%'], [t('信息比率', 'IR'), m.ir.toFixed(2)], [t('相对最大回撤', 'Max rel. DD'), m.dd + '%'], [t('单边年换手', 'Turnover'), m.to + '×'], [t('费用拖累', 'Cost drag'), m.drag + '%']].map(([a, b]) => `<div class="stat"><span>${a}</span><b>${b}</b></div>`).join('')}</div>
  <div class="charts" style="grid-template-columns:1.6fr 1fr"><div class="chart-box"><h4>${t('净值（2019–2024 研发期）', 'NAV (2019–2024 development)')}</h4>${SV.line([{ v: bm, c: '#b9b0c2' }, { v: gr, c: '#bba0d3', dash: 1 }, { v: net, c: '#65358d', w: 2 }], { labels: [[0, '2019'], [24, '2021'], [48, '2023'], [71, '2024']] })}
    <div class="cap"><span class="legend-i"><i style="background:#65358d"></i>${t('扣费后', 'Net')}</span><span class="legend-i"><i style="background:#bba0d3"></i>${t('扣费前', 'Gross')}</span><span class="legend-i"><i style="background:#b9b0c2"></i>${t('中证800', 'CSI 800')}</span></div></div>
    <div class="chart-box"><h4>${t('分年超额（扣费后）', 'Excess by year (net)')}</h4>${SV.bars(years, ['19', '20', '21', '22', '23', '24'], v => v.toFixed(1))}</div></div>
  <div class="grid2" style="margin-top:12px"><div><h3 style="margin-bottom:6px">${t('门槛（按当时 K=', 'Gates (at K=')}${Kat})</h3>${gateTable(m, Kat, nb)}</div>
    <div><h3 style="margin-bottom:6px">${t('参数邻域 · 扣费后超额 %（✓ 为达标）', 'Neighbourhood · net excess % (✓ passes)')}</h3><table class="heat"><tr><th>N \\ ${t('调仓', 'reb')}</th>${[5, 10, 20].map(x => `<th>${x}${t('日', 'd')}</th>`).join('')}</tr>${g.grid.map(row => `<tr><th>${row[0].N}</th>${row.map(c => `<td class="${c.g ? 'h2' : c.r.ex > 0 ? 'h1' : 'h0'} ${c.N === n.rc.N && c.reb === n.rc.reb ? 'cur' : ''}">${c.r.ex}${c.g ? ' ✓' : ''}</td>`).join('')}</tr>`).join('')}</table>
    <h3 style="margin:12px 0 6px">${t('成本敏感性', 'Cost sensitivity')}</h3><div class="kv"><span>0.5×</span><b>${(m.gross - m.drag / 2).toFixed(1)}%</b><span>1×</span><b>${m.ex}%</b><span>2×</span><b class="${m.ex2 > 0 ? '' : 'bad-t'}">${m.ex2}%</b></div></div></div>
  <div class="hint" style="margin:14px 0 0">${t('回测引擎：RE 策略回测 · 数据视图 r20261105 · 报告绑定该版本配方。未建模：冲击成本、容量；涨跌停与停牌的处理以 RE 实际口径为准并在报告中写明。', 'Engine: RE strategy backtest · data view r20261105 · report bound to this recipe version. Not modelled: impact cost, capacity; limit-up/down and suspension handling follow RE and are stated in the report.')}</div>`;
}

/* ---------- 人工研究 ---------- */
function wbNode() { const tp = topic(P.wb.topic); return { tp, n: tp && P.wb.node && nodeOf(tp, P.wb.node) }; }
function pageWB() {
  const { tp, n } = wbNode();
  if (!n) return `<div class="card"><div class="card-body empty"><b>${t('还没有接手的版本', 'Nothing taken over yet')}</b>${t('在研究运行里选一个版本，点“从这里接手”。也可以直接接手 S1 的首个版本：', 'Pick a version in Research operations and take over. Or take over S1’s first version now:')}<br><br><button class="btn primary" data-a="takeover" data-v="V1" ${isRes() ? '' : 'disabled'}>${t('接手 S1 / V1', 'Take over S1 / V1')}</button></div></div>`;
  const rc = P.wb.rc, Kn = K(tp), tools = [['recipe', '配方', 'Recipe'], ['test', '回测', 'Backtest'], ['robust', '稳健性', 'Robustness'], ['seal', '封存验证', 'Sealed validation'], ['submit', '提交', 'Submit']];
  const m = P.wb.last, okDev = m && pass(m, Kn, P.wb.nb);
  let body = '';
  if (P.wb.tool === 'recipe') body = `<div class="field-grid"><div class="field full">${t('因子与方向（从因子库选 1～3 个）', 'Factors (pick 1–3 from the library)')}<div class="pill-list">${Object.keys(FAC).map(k => `<label style="display:flex;gap:5px;align-items:center;font-size:11.5px;border:1px solid var(--line);border-radius:6px;padding:4px 8px"><input type="checkbox" data-a="fac" data-v="${k}" ${rc.f.includes(k) ? 'checked' : ''}>${fname(k)}${FAC[k].src === 'imp' ? ` <span class="badge amber">${t('导入', 'Imported')}</span>` : ''}</label>`).join('')}</div></div>
    <label class="field">${t('持仓数 N', 'Holdings N')}<select data-k="N">${[30, 50, 60, 80, 100].map(x => `<option ${rc.N === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
    <label class="field">${t('调仓周期', 'Rebalance')}<select data-k="reb">${[5, 10, 20].map(x => `<option value="${x}" ${rc.reb === x ? 'selected' : ''}>${t(`${x} 个交易日`, `${x} days`)}</option>`).join('')}</select></label>
    <label class="field">${t('持仓缓冲区', 'Holding buffer')}<select data-k="buf"><option value="0" ${rc.buf ? '' : 'selected'}>${t('不使用', 'None')}</option><option value="1" ${rc.buf ? 'selected' : ''}>${t('排名前 1.5N 内不卖出', 'Keep while ranked within 1.5N')}</option></select></label>
    <label class="field">${t('股票池 · 基准 · 区间 · 成本', 'Universe · benchmark · period · cost')}<input disabled value="${t('由课题固定', 'Fixed by topic')}"><small>${tx(SCOPE)}</small></label></div>
    <div class="hint">${t('只开放模板参数；任意代码策略、优化器不在本期范围。', 'Template parameters only; custom-code strategies and optimisers are out of scope this release.')}</div>`;
  if (P.wb.tool === 'test') body = `${recipe(rc)}<div style="display:flex;gap:8px;align-items:center;margin:14px 0"><button class="btn primary" data-a="runbt">${t('运行回测', 'Run backtest')}</button><small>${t(`本次将记为课题第 ${Kn + 1} 次回测，信息比率门槛升到 ${needIR(Kn + 1).toFixed(2)}`, `This will be backtest ${Kn + 1}; the IR bar rises to ${needIR(Kn + 1).toFixed(2)}`)}</small></div>${m ? gateTable(m, Kn, P.wb.nb) + `<div style="margin-top:8px"><button class="text-btn" data-a="report" data-v="${tp.id}|${n.id}|${Kn}">${t('查看完整报告', 'Full report')} →</button></div>` : ''}`;
  if (P.wb.tool === 'robust') body = m ? (() => { const g = nbhd(rc); return `<p class="subtle" style="margin-bottom:8px">${t('在当前配方周围 3×3 的持仓数与调仓周期上重算；邻域检验属于稳健性检查，不另计 K。', 'Recomputed on the 3×3 grid around the recipe; robustness checks do not add to K.')}</p><table class="heat"><tr><th>N \\ ${t('调仓', 'reb')}</th>${[5, 10, 20].map(x => `<th>${x}${t('日', 'd')}</th>`).join('')}</tr>${g.grid.map(row => `<tr><th>${row[0].N}</th>${row.map(c => `<td class="${c.g ? 'h2' : c.r.ex > 0 ? 'h1' : 'h0'} ${c.N === rc.N && c.reb === rc.reb ? 'cur' : ''}">${c.r.ex}${c.g ? ' ✓' : ''}</td>`).join('')}</tr>`).join('')}</table><div style="margin-top:12px"><button class="btn" data-a="nb">${t('记录邻域结果', 'Record result')}（${g.ok}/9）</button></div>`; })() : `<div class="empty">${t('先运行回测', 'Run a backtest first')}</div>`;
  if (P.wb.tool === 'seal') body = okDev ? (lastV(n) ? `<div class="hint success">${t('已完成封存验证', 'Sealed validation done')}：${lastV(n).ex}% · IR ${lastV(n).ir}</div>` : `<div class="hint">${t('封存期 2025 每个候选只能使用一次；申请后配方冻结。', 'The 2025 sealed period can be used once per candidate; the recipe freezes on request.')}</div><button class="btn primary" data-a="seal">${t('申请封存验证', 'Request sealed validation')}</button>`) : `<div class="empty">${t('研发期门槛全部达标（含参数邻域）后才能申请', 'Available once every development gate passes, including the neighbourhood')}</div>`;
  if (P.wb.tool === 'submit') body = lastV(n) ? `<div class="hint">${t('提交后由独立复核人在审查中心决定是否入库；研究员不能审批自己的候选。', 'An independent reviewer decides in the review centre; researchers cannot approve their own candidates.')}</div><button class="btn primary" data-a="submit" ${n.status === 'submitted' ? 'disabled' : ''}>${n.status === 'submitted' ? t('已提交', 'Submitted') : t('提交审查', 'Submit for review')}</button>` : `<div class="empty">${t('封存验证后才能提交', 'Submit after sealed validation')}</div>`;
  const chat = P.wb.chat || (P.wb.chat = [{ ai: 1, txt: [`已加载 ${tp.id}/${n.id}。我可以解释回测结果、建议降低换手的改法，或检查过拟合风险。改动先写进草稿，由你确认。`, `Loaded ${tp.id}/${n.id}. I can explain results, suggest ways to cut turnover or check overfitting risk. Changes go to your draft for you to confirm.`] }]);
  return SV.note(['<b>设计要点</b>：人工研究与 S0 用同一套工具和同一本台账：人工回测同样增加 K，门槛同样提高；助手只能写草稿，执行由人确认。', '<b>Design</b>: people use the same tools and ledger as S0: manual backtests add to K and raise the bar; the assistant only drafts and the person confirms.'])
    + `<div class="status-strip"><span class="status-icon">⌁</span><div class="status-main"><b>${tp.id} / ${n.id} · ${tx(n.title)}</b><p>${t('课题台账', 'Ledger')} K=${Kn} · ${t('当前信息比率门槛', 'IR bar')} ${needIR(Kn).toFixed(2)} · ${t('预算', 'budget')} ${Kn}/${tp.budget}</p></div><div class="actions"><button class="btn small" data-a="handback">${t('交回研究系统', 'Hand back')}</button></div></div>
    <div class="wb-grid"><div><div class="tool-tabs">${tools.map(([k, z, e]) => `<button class="${P.wb.tool === k ? 'on' : ''}" data-a="tool" data-v="${k}">${t(z, e)}</button>`).join('')}</div><div class="card"><div class="card-body">${body}</div></div></div>
    <div class="card asst"><div class="card-head"><h2>${t('研究助手', 'Research assistant')}</h2></div><div class="chat" id="chat">${chat.map(c => `<div class="msg ${c.ai ? 'ai' : 'me'}">${tx(c.txt)}${c.card ? `<div class="toolcard">${c.card}</div>` : ''}</div>`).join('')}</div>
    <div class="compose"><div class="qp"><button data-a="ask" data-v="why">${t('为什么不达标', 'Why below bar')}</button><button data-a="ask" data-v="turn">${t('怎么降换手', 'Cut turnover')}</button><button data-a="ask" data-v="over">${t('过拟合风险', 'Overfitting risk')}</button></div></div></div></div>`;
}
const REPLY = {
  why: m => m ? [`扣费前超额 ${m.gross}%，费用拖累 ${m.drag}%（单边年换手 ${m.to}×，按双边 0.2%）。主要问题是${m.to > POL.to ? '换手过高' : m.ir < .6 ? '波动相对超额偏大' : '分年表现不稳'}。`, `Gross ${m.gross}%, drag ${m.drag}% (${m.to}× turnover at 0.2%). Main issue: ${m.to > POL.to ? 'turnover' : m.ir < .6 ? 'volatility vs excess' : 'year-to-year instability'}.`] : ['还没有回测结果。', 'No backtest yet.'],
  turn: () => ['两种改法：① 调仓从 5 日改 10 日；② 加持仓缓冲区（排名前 1.5N 内不卖出）。②通常保留更多信号。已写入草稿：缓冲区开启、10 日调仓。', 'Two options: (1) rebalance every 10 days; (2) add a 1.5N holding buffer, which usually keeps more signal. Drafted: buffer on, 10-day rebalance.'],
  over: () => [`当前课题已回测 ${K(topic(P.wb.topic))} 次，信息比率门槛已按次数提高。建议先看参数邻域：如果只有当前点达标，说明结果偏偶然。`, `This topic has ${K(topic(P.wb.topic))} backtests and the IR bar is adjusted for that. Check the neighbourhood: if only this point passes, the result is likely luck.`]
};

/* ---------- 审查 ---------- */
function pageReview() {
  const c = SC.find(x => x.id === P.rv.sel) || SC[0]; const tp = topic(c.topic), n = nodeOf(tp, c.node), m = bt(n.rc), v = lastV(n), r = lastR(n), Kn = K(tp);
  const can = !isRes() && c.status === 'pending';
  const all = tp.nodes.flatMap(x => x.steps.filter(s => s.k === 'B').map(s => ({ s, x }))).sort((a, b) => a.s.K - b.s.K);
  return SV.note(['<b>设计要点</b>：复核人只审通过门槛的候选，但看到课题的全部回测（包括失败、放弃），门槛按课题当前 K 重新计算。入库只授权“可用于模拟组合”，实盘不在本期。', '<b>Design</b>: reviewers see only passing candidates but every backtest in the topic, with the bar recomputed at the current K. Admission grants simulated-portfolio use only.'])
    + `<div class="rv-grid"><div class="queue">${SC.map(x => `<button class="qi ${x.id === c.id ? 'sel' : ''}" data-a="cand" data-v="${x.id}"><span class="mono">${x.id} · ${x.topic}/${x.node}</span><b>${tx(topic(x.topic).name)}</b>${SV.badge(x.status === 'pending' ? ['待复核', 'Pending', 'purple'] : x.status === 'approved' ? ['已入库', 'Admitted', 'green'] : ['已处理', 'Handled', 'gray'])}<small>${x.time}</small></button>`).join('')}<a class="subtle" href="review.html">${t('在审查中心查看全部待办 →', 'All items in the review centre →')}</a></div>
    <div><div class="card"><div class="card-head"><div><h2>${c.id} · ${tx(tp.name)}</h2><p>${tp.id}/${n.id} · ${t('提交于', 'submitted')} ${c.time}</p></div></div><div class="card-body">${recipe(n.rc)}
    <div class="grid2" style="margin-top:14px"><div><h3 style="margin-bottom:6px">${t('门槛（按课题当前 K=', 'Gates (current K=')}${Kn})</h3>${gateTable(m, Kn, r ? r.nb : null)}<div class="hint success" style="margin:10px 0 0">${t('封存 2025', 'Sealed 2025')}：${v.ex}% · IR ${v.ir}（${t('要求', 'needs')} > 0 · ≥ ${POL.vir}）</div></div>
    <div><h3 style="margin-bottom:6px">${t('课题全部回测', 'Every backtest in the topic')}（${all.length}）</h3>${all.map(({ s, x }) => { const mm = bt(x.rc); return `<div class="trial-row"><span class="tk">B${s.K}</span><div class="tb">${x.id} · ${tx(x.title)}<small>${t('超额', 'excess')} ${mm.ex}% · IR ${mm.ir.toFixed(2)} · ${t('换手', 'turnover')} ${mm.to}×</small></div>${pass(mm, s.K, null) ? '<span class="ok-t">✓</span>' : '<span class="bad-t">✗</span>'}</div>`; }).join('')}
    <h3 style="margin:12px 0 6px">${t('独立复核意见（S5，不共享研究上下文）', 'Independent review (S5, no shared context)')}</h3><ul class="checklist">${c.ai.map(a => `<li>· ${tx(a)}</li>`).join('')}</ul><h3 style="margin:12px 0 6px">${t('局限', 'Limitations')}</h3><ul class="checklist">${c.limits.map(a => `<li>· ${tx(a)}</li>`).join('')}</ul></div></div></div>
    <div class="card-footer"><label style="display:flex;gap:6px;align-items:center;font-size:11.5px"><input type="checkbox" data-a="ack" ${P.rv.ack ? 'checked' : ''} ${can ? '' : 'disabled'}>${t('我已查看全部回测、封存结果与局限', 'I have read every backtest, the sealed result and limitations')}</label>
    <div class="decision">${isRes() ? `<span class="subtle">${t('研究员不能审批候选', 'Researchers cannot decide')}</span>` : ''}<button class="btn small" data-a="decide" data-v="archived" ${can ? '' : 'disabled'}>${t('归档', 'Archive')}</button><button class="btn small" data-a="decide" data-v="returned" ${can ? '' : 'disabled'}>${t('退回补证', 'Return')}</button><button class="btn small primary" data-a="decide" data-v="approved" ${can && P.rv.ack ? '' : 'disabled'}>${t('入库（可用于模拟组合）', 'Admit (simulated portfolios)')}</button></div></div></div></div></div>`;
}

/* ---------- 策略库 ---------- */
function libRows() {
  const rows = SV.D.strategies.map(s => ({ ...s, use: ['PF-1', 'PF-1'] }));
  if (SC[0].status === 'approved') rows.unshift({ id: 'ST-03', n: topic('S2').name, f: ['一致预期调整动量', '盈余公告漂移 PEAD'], fe: ['Consensus revision momentum', 'PEAD'], p: ['中证800 · 前 80 只 · 20 日调仓', 'CSI 800 · top 80 · rebalance 20d'], ir: bt(nodeOf(topic('S2'), 'V2').rc).ir, vir: .52, ex: bt(nodeOf(topic('S2'), 'V2').rc).ex, to: bt(nodeOf(topic('S2'), 'V2').rc).to, at: '11-06', use: ['—', '—'], fresh: 1 });
  return rows;
}
function pageLib() {
  const rows = libRows(), sel = rows.find(r => r.id === P.libSel);
  return SV.note(['<b>设计要点</b>：策略库只收经过复核的策略，每条显示来源因子及其状态、配方、研发与封存证据；组合模块只能从这里选策略。', '<b>Design</b>: only reviewed strategies enter the library, each with source factors and their status, recipe and evidence; the portfolio module selects only from here.'])
    + `<div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('策略', 'Strategy')}</th><th>${t('来源因子', 'Source factors')}</th><th>${t('配方', 'Recipe')}</th><th>${t('研发 IR / 封存 IR', 'Dev IR / sealed IR')}</th><th>${t('扣费后超额', 'Net excess')}</th><th>${t('换手', 'Turnover')}</th><th>${t('组合使用', 'Used by')}</th><th>${t('入库', 'Admitted')}</th></tr></thead><tbody>
    ${rows.map(r => `<tr data-a="libsel" data-v="${r.id}" style="cursor:pointer"><td><b>${r.id} · ${tx(r.n)}</b>${r.fresh ? `<small class="ok-t">${t('刚入库', 'Just admitted')}</small>` : ''}</td><td>${(L === 'en' ? r.fe : r.f).join('<br>')}<small>${t('因子库 · 已复核', 'Library · reviewed')}</small></td><td>${tx(r.p)}</td><td>${r.ir.toFixed(2)} / ${r.vir.toFixed(2)}</td><td>${r.ex}%</td><td>${r.to}×</td><td>${tx(r.use)}</td><td>${r.at}</td></tr>`).join('')}</tbody></table></div></div>
    ${sel ? `<div class="drawer"><h3>${sel.id} · ${tx(sel.n)}</h3><div class="kv" style="margin-top:8px"><span>${t('允许用途', 'Allowed use')}</span><b>${t('模拟组合；实盘需另行审批（本期不提供）', 'Simulated portfolios; live use needs separate approval (not in this release)')}</b><span>${t('证据', 'Evidence')}</span><b>${t('研发报告、参数邻域、成本敏感性、封存报告、复核记录', 'Development report, neighbourhood, cost sensitivity, sealed report, review record')}</b><span>${t('局限', 'Limitations')}</span><b>${t('冲击成本与容量未建模', 'Impact cost and capacity not modelled')}</b></div><div style="margin-top:10px"><a class="btn small" href="portfolio.html#plan">${t('在组合中使用 →', 'Use in a portfolio →')}</a></div></div>` : ''}`;
}

/* ---------- 能力与评测（MVP 只读） ---------- */
function pageCaps() {
  const AW = [[t('可自主执行', 'Autonomous'), t('在模板参数内改配方；换因子组合（仅限因子库已复核因子）；开分支；放弃分支；对达标候选申请一次封存验证；提交审查', 'Edit recipes within template parameters; change factor mix (reviewed library factors only); branch; drop; one sealed validation per passing candidate; submit')],
    [t('需要人确认', 'Needs a person'), t('使用导入或未复核因子；修改股票池、区间、成本或门槛；增加预算', 'Use imported/unreviewed factors; change universe, period, cost or gates; add budget')],
    [t('不允许', 'Never'), t('批准入库；删除或修改回测记录；重复使用封存期；下单', 'Admit strategies; delete or edit backtests; reuse the sealed period; place orders')]];
  return SV.note(['<b>设计要点</b>：S0 不是新写的 Agent：它就是 F0 的决策引擎（模型决策 + 白名单 + 程序校验 + 检查点），换成策略版动作白名单。评测与方法发布放到完善期，本期只读展示。', '<b>Design</b>: S0 is not a new agent but the F0 decision engine with a strategy whitelist. Evals and method releases come later; read-only here.'])
    + `<div class="card"><div class="card-head"><div><h2>${t('S0 研究决策 · 动作白名单', 'S0 research decision · action whitelist')}</h2><p>${t('程序校验每个动作；越权动作被拒绝并记录', 'Every action is validated by code; out-of-scope actions are rejected and logged')}</p></div></div><div class="card-body"><div class="split" style="grid-template-columns:1fr 1fr 1fr">${AW.map((a, i) => `<div class="diff ${i === 0 ? 'new' : ''}" ${i === 2 ? 'style="background:var(--red-bg);border-color:#efd3da"' : ''}><b>${a[0]}</b><p>${a[1]}</p></div>`).join('')}</div></div></div>
    <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('单元', 'Unit')}</th><th>${t('职责', 'Role')}</th><th>${t('方法版本', 'Method version')}</th><th>${t('本月调用', 'Calls this month')}</th></tr></thead><tbody>${UNITS.map((u, i) => `<tr><td><b>${u[0]} · ${tx(u[1])}</b></td><td>${tx(u[2])}</td><td class="mono">v1 · ${i === 0 ? 'F0 engine' : 'prompt v1'}</td><td>${[14, 9, 12, 11, 6, 2][i]}</td></tr>`).join('')}</tbody></table></div><div class="card-footer"><small>${t('用量与暂停在 Agent 管理中统一查看', 'Usage and pause controls live in Agent management')}</small><a class="text-btn" href="agents.html">${t('Agent 管理 →', 'Agents →')}</a></div></div>`;
}

/* ---------- simulation of S1 (S0 working on its own) ---------- */
const S1 = topic('S1');
const SIM = [
  () => { const n = nodeOf(S1, 'V1'); n.status = 'fail'; n.steps.push({ k: 'D', txt: ['扣费前超额高，但单边年换手超过 30 倍，费用吃掉大部分 → 降低换手：10 日调仓 + 缓冲区', 'High gross excess but turnover over 30× eats most of it → reduce turnover: 10-day + buffer'] }); S1.act = ['换手过高 → 修订为 V2', 'Turnover too high → revised into V2']; feed('S1', ['S0 决策：V1 换手过高，修订为 V2（理由引用 B1 换手与费用拖累）', 'S0: V1 turnover too high, revise to V2 (citing B1 turnover and drag)']); },
  () => { S1.nodes.push({ id: 'V2', parent: 'V1', by: 'agent', title: ['10 日调仓 + 缓冲区', '10-day + buffer'], status: 'run', rc: R(['rev5', 'crm'], 50, 10, 1), why: ['保留反转信号的同时减少无效交易。', 'Keep the reversal signal while cutting needless trades.'], steps: [{ k: 'C' }] }); P.node = 'V2'; feed('S1', ['V2 配方校验通过：参数在授权范围内', 'V2 recipe validated: parameters within authorisation']); },
  () => { nodeOf(S1, 'V2').steps.push({ k: 'B', K: 2 }); feed('S1', ['回测 B2 完成（课题第 2 次）', 'Backtest B2 done (2nd in topic)']); },
  () => { const n = nodeOf(S1, 'V2'); n.steps.push({ k: 'R', nb: nbhd(n.rc).ok }); feed('S1', [`稳健性：参数邻域 ${nbhd(n.rc).ok}/9`, `Robustness: neighbourhood ${nbhd(n.rc).ok}/9`]); },
  () => { const n = nodeOf(S1, 'V2'); const ok = pass(bt(n.rc), K(S1), lastR(n).nb);
    if (ok) { n.steps.push({ k: 'D', txt: ['研发门槛达标 → 申请封存验证', 'Development gates pass → request sealed validation'] }); feed('S1', ['S0 申请封存验证（每候选一次）', 'S0 requests sealed validation (once per candidate)']); }
    else { n.status = 'fail'; n.steps.push({ k: 'D', txt: ['信息比率低于按 K 校正的门槛，邻域只有 5/9 → 开分支 V2a：加入 PEAD', 'IR below the K-adjusted bar and neighbourhood only 5/9 → branch V2a: add PEAD'] }); S1.nodes.push({ id: 'V2a', parent: 'V2', by: 'agent', title: ['加入 PEAD · 前 60 · 10 日 + 缓冲区', 'Add PEAD · top 60 · 10-day + buffer'], status: 'run', rc: R(['rev5', 'crm', 'pead'], 60, 10, 1), why: ['加入第三个低相关的慢变量，降低跟踪误差和对单一参数点的依赖。', 'Add a third, low-correlation slow signal to cut tracking error and parameter dependence.'], steps: [{ k: 'C' }, { k: 'B', K: 3 }] }); P.node = 'V2a'; feed('S1', ['S0 决策：开分支 V2a 并回测 B3', 'S0: branch V2a and run B3']); } },
  () => { const n = S1.nodes[S1.nodes.length - 1]; if (!lastR(n)) { n.steps.push({ k: 'R', nb: nbhd(n.rc).ok }); feed('S1', [`稳健性：参数邻域 ${nbhd(n.rc).ok}/9`, `Robustness: ${nbhd(n.rc).ok}/9`]); } },
  () => { const n = S1.nodes[S1.nodes.length - 1]; n.steps.push({ k: 'V', ex: 1.8, ir: .38 }); feed('S1', ['封存验证 2025：超额 1.8%，IR 0.38，通过', 'Sealed 2025: excess 1.8%, IR 0.38, passed']); },
  () => { const n = S1.nodes[S1.nodes.length - 1]; n.status = 'submitted'; n.steps.push({ k: 'D', txt: ['提交审查 → 候选 SC2', 'Submitted → candidate SC2'] }); S1.status = 'review'; S1.act = ['候选 SC2 已提交审查', 'Candidate SC2 submitted'];
    SC.push({ id: 'SC2', topic: 'S1', node: n.id, status: 'pending', time: clock().slice(0, 5), ai: [['换手经缓冲区后降到 15 倍以内，扣费后仍达标。', 'Buffer brings turnover under 15×; still passes net of cost.'], ['反转部分对成本敏感，2 倍成本下超额明显收窄。', 'The reversal leg is cost-sensitive; excess narrows clearly at 2× cost.']], limits: [['冲击成本与容量未建模。', 'Impact and capacity not modelled.']] }); feed('S1', ['候选 SC2 提交审查', 'Candidate SC2 submitted']); SV.toast(t('S1 提交了新候选 SC2', 'S1 submitted candidate SC2')); }
];
let timer;
function simStep() { if (P.sim.i >= SIM.length) return; SIM[P.sim.i++](); S1.tokens += 2; SV.render(); }

P.render = () => SV.head('STRATEGY RESEARCH', '策略研究', 'Strategy research', '用因子库里的因子构建交易规则；研究系统自主推进，你可以随时观察、介入或亲自研究。', 'Build trading rules from library factors; the research system works on its own and you can watch, step in or research yourself.',
  `<button class="btn" data-a="auth">${t('研究授权', 'Authorisation')}</button><button class="btn primary" data-a="newtopic" ${isRes() || SV.role === 'lead' ? '' : 'disabled'}>＋ ${t('新建课题', 'New topic')}</button>`)
  + SV.tabs([['ops', '研究运行', 'Research operations'], ['wb', '人工研究', 'My research'], ['review', '审查', 'Review', SC.filter(c => c.status === 'pending').length], ['lib', '策略库', 'Library'], ['caps', '能力与评测', 'Capabilities']], P.tab)
  + { ops: pageOps, wb: pageWB, review: pageReview, lib: pageLib, caps: pageCaps }[P.tab]();
P.demoExtra = () => `<div class="grp"><span>${t('研究系统模拟', 'Research simulation')}</span><div class="row"><button class="btn small" data-a="simtoggle">${P.sim.on ? t('⏸ 暂停模拟', '⏸ Pause') : t('▶ 继续模拟', '▶ Resume')}</button><button class="btn small" data-a="simstep" ${P.sim.i >= SIM.length ? 'disabled' : ''}>${t('推进一步', 'Step')}</button></div></div>`;
P.start = () => { timer = setInterval(() => { if (P.sim.on && P.sysOn && S1.status === 'run' && P.tab === 'ops' && !$('#overlay').innerHTML) simStep(); if (P.sim.i >= SIM.length) clearInterval(timer); }, 3400); };
P.onInput = e => { const k = e.target.dataset.k; if (k && P.wb.rc) { P.wb.rc[k] = k === 'buf' ? e.target.value === '1' : +e.target.value; P.wb.last = null; P.wb.nb = null; } };
document.addEventListener('change', e => { if (e.target.dataset.k) SV.render(); });
P.A = {
  topic: v => { P.sel = v; P.node = null; SV.render(); }, node: v => { P.node = v; SV.render(); },
  report: v => { const [a, b, k] = v.split('|'); const tp = topic(a), n = nodeOf(tp, b); SV.modal(`${n.id} · ${t('回测报告', 'Backtest report')}`, `${tp.id} ${tx(tp.name)} · ${t('课题第', 'backtest')} ${k} ${t('次回测', 'of topic')}`, report(tp, n, +k), `<button class="btn" data-a="close">${t('关闭', 'Close')}</button>`); },
  sys: () => { P.sysOn = !P.sysOn; feed('—', P.sysOn ? ['研究系统恢复', 'System resumed'] : ['研究系统已暂停：不再调度新动作', 'System paused: no new actions']); SV.render(); },
  pausetopic: () => { const tp = topic(P.sel); tp.status = tp.status === 'run' ? 'paused' : 'run'; feed(tp.id, tp.status === 'paused' ? ['课题暂停', 'Topic paused'] : ['课题继续', 'Topic resumed']); SV.render(); },
  takeover: v => { const tp = topic(P.tab === 'ops' ? P.sel : 'S1'); let n = nodeOf(tp, v);
    if (n.by !== 'human') { const id = v + 'm'; if (!nodeOf(tp, id)) tp.nodes.push({ id, parent: v, by: 'human', title: [`接手自 ${v}`, `Taken over from ${v}`], status: 'human', rc: { ...n.rc, f: [...n.rc.f] }, why: n.why, steps: [{ k: 'C' }] }); feed(tp.id, [`张新迪 接手 ${v}，新建人工版本 ${id}`, `Zhang Xindi took over ${v} as ${id}`]); n = nodeOf(tp, id); }
    P.wb = { topic: tp.id, node: n.id, tool: 'recipe', rc: n.rc, last: null, nb: null, chat: null }; P.tab = 'wb'; history.replaceState(null, '', '#wb'); SV.render(); window.scrollTo(0, 0); },
  tool: v => { P.wb.tool = v; SV.render(); },
  fac: (v, el) => { const f = P.wb.rc.f; if (el.checked && f.length >= 3) { el.checked = false; SV.toast(t('最多 3 个因子', 'Up to 3 factors')); return; } if (el.checked) f.push(v); else if (f.length > 1) f.splice(f.indexOf(v), 1); else el.checked = true;
    if (FAC[v].src === 'imp' && el.checked) SV.toast(t('导入因子未经 V5 复核：回测可做，提交前需研究负责人确认', 'Imported factor not V5-reviewed: allowed in backtests, lead confirmation needed before submitting')); P.wb.last = null; P.wb.nb = null; SV.render(); },
  runbt: () => { const { tp, n } = wbNode(); const prev = n.steps.filter(s => s.k === 'B').map(s => s._sig); const sig = JSON.stringify(P.wb.rc);
    if (prev.includes(sig)) { SV.toast(t('同一配方已回测过：直接显示原结果，不计 K', 'Same recipe already tested: showing the original result, K unchanged')); P.wb.last = bt(P.wb.rc); SV.render(); return; }
    const Kn = K(tp) + 1; n.rc = { ...P.wb.rc, f: [...P.wb.rc.f] }; P.wb.rc = n.rc; n.steps.push({ k: 'B', K: Kn, _sig: sig }); P.wb.last = bt(n.rc); P.wb.nb = null;
    feed(tp.id, [`人工回测 B${Kn}（${n.id}）：超额 ${P.wb.last.ex}%，IR ${P.wb.last.ir.toFixed(2)} / 需 ${needIR(Kn).toFixed(2)}`, `Manual backtest B${Kn} (${n.id}): ${P.wb.last.ex}%, IR ${P.wb.last.ir.toFixed(2)} vs ${needIR(Kn).toFixed(2)}`]); SV.render(); },
  nb: () => { const { n } = wbNode(); const g = nbhd(P.wb.rc); P.wb.nb = g.ok; n.steps.push({ k: 'R', nb: g.ok }); SV.render(); },
  seal: () => { const { tp, n } = wbNode(); const m = P.wb.last; n.steps.push({ k: 'V', ex: +(m.ex * .55).toFixed(1), ir: +(m.ir * .6).toFixed(2) }); feed(tp.id, [`封存验证（${n.id}）完成`, `Sealed validation (${n.id}) done`]); SV.render(); },
  submit: () => { const { tp, n } = wbNode(); n.status = 'submitted'; const id = 'SC' + (SC.length + 1); SC.push({ id, topic: tp.id, node: n.id, status: 'pending', time: clock().slice(0, 5), ai: [['人工版本，复核意见生成中。', 'Human version; review opinion being prepared.']], limits: [['冲击成本与容量未建模。', 'Impact and capacity not modelled.']] }); n.steps.push({ k: 'D', txt: [`提交审查 → ${id}`, `Submitted → ${id}`] }); SV.toast(t('已提交审查', 'Submitted for review')); SV.render(); },
  handback: () => { const { tp, n } = wbNode(); n.status = 'returned'; n.steps.push({ k: 'D', txt: ['交回研究系统：作为 S0 下一步决策的输入', 'Handed back: input to S0’s next decision'] }); feed(tp.id, [`${n.id} 交回研究系统`, `${n.id} handed back`]); P.tab = 'ops'; P.sel = tp.id; P.node = n.id; SV.render(); },
  ask: v => { const q = { why: ['为什么不达标？', 'Why below the bar?'], turn: ['怎么降换手？', 'How to cut turnover?'], over: ['过拟合风险？', 'Overfitting risk?'] }[v]; P.wb.chat.push({ txt: q });
    P.wb.chat.push({ ai: 1, txt: REPLY[v](P.wb.last), card: v === 'turn' ? `<b>${t('草稿改动', 'Draft change')}</b><div class="tm"><span>${t('调仓', 'reb')} → 10</span><span>${t('缓冲区', 'buffer')} → 1.5N</span><button class="text-btn" data-a="adopt">${t('采纳', 'Adopt')}</button></div>` : '' }); SV.render(); },
  adopt: () => { Object.assign(P.wb.rc, { reb: 10, buf: true }); P.wb.last = null; P.wb.nb = null; P.wb.tool = 'test'; P.wb.chat.push({ ai: 1, txt: ['已写入配方草稿。运行回测会计入台账。', 'Written to the recipe draft. Running a backtest adds to the ledger.'] }); SV.render(); },
  cand: v => { P.rv.sel = v; P.rv.ack = false; SV.render(); }, ack: (v, el) => { P.rv.ack = el.checked; SV.render(); },
  decide: v => { const c = SC.find(x => x.id === P.rv.sel); c.status = v; SV.flag(c.id, v === 'approved' ? 'done' : v); const tp = topic(c.topic); nodeOf(tp, c.node).status = v === 'approved' ? 'approved' : 'fail'; if (v === 'approved') tp.status = 'done';
    SV.log('strategy', [`${c.id} ${{ approved: '入库，可用于模拟组合', returned: '退回补证', archived: '归档' }[v]}`, `${c.id} ${v}`]); P.rv.ack = false; SV.toast(t('决定已记录', 'Decision recorded')); SV.render(); },
  libsel: v => { P.libSel = P.libSel === v ? null : v; SV.render(); },
  simtoggle: () => { P.sim.on = !P.sim.on; SV.render(); }, simstep: () => simStep(),
  comment: () => SV.modal(t('给研究意见', 'Comment'), `${P.sel}`, `<div class="hint">${t('意见作为 S0 下一步决策的输入并留痕，不会扩大授权、门槛或预算。', 'Comments are logged input to S0; they never widen authorisation, gates or budget.')}</div><label class="field">${t('意见', 'Comment')}<textarea id="cmt">${t('优先控制换手，不要为了超额把持仓数降到 30 以下。', 'Prioritise turnover; do not cut holdings below 30 to chase excess.')}</textarea></label>`, `<button class="btn" data-a="close">${t('取消', 'Cancel')}</button><button class="btn primary" data-a="sendcmt">${t('发送', 'Send')}</button>`),
  sendcmt: () => { const x = $('#cmt').value.trim(); SV.close(); feed(P.sel, [`人工意见：“${x}”`, `Comment: “${x}”`]); SV.render(); },
  auth: () => { const dis = SV.role === 'lead' ? '' : 'disabled'; SV.modal(t('研究授权', 'Research authorisation'), t('策略研究系统 · 有效至 2026-11-30', 'Strategy research system · valid to 2026-11-30'), `<div class="field-grid"><label class="field">${t('本月回测上限', 'Monthly backtest cap')}<input ${dis} value="60"></label><label class="field">${t('Token 预算', 'Token budget')}<input ${dis} value="600k"></label><label class="field">${t('门槛政策版本', 'Gate policy')}<select ${dis}><option>${t('策略研究门槛 v1（演示默认值，需按机构政策校准）', 'Strategy gates v1 (demo defaults, calibrate to policy)')}</option></select></label><label class="field">${t('封存期', 'Sealed period')}<input disabled value="2025-01-01 ～ 2025-12-31"></label></div>`, `${dis ? `<span class="subtle" style="margin-right:auto">${t('仅投资负责人可修改', 'Only the investment lead can edit')}</span>` : ''}<button class="btn" data-a="close">${t('关闭', 'Close')}</button><button class="btn primary" data-a="close" ${dis}>${t('保存为新版本', 'Save as new version')}</button>`); },
  newtopic: () => SV.modal(t('新建策略课题', 'New strategy topic'), t('研究系统在授权与预算内自主推进', 'The research system proceeds within authorisation and budget'), `<div class="field-grid"><label class="field full">${t('研究目标', 'Objective')}<input id="ntn" value="${t('PEAD 与低波动的防御组合', 'Defensive PEAD + low-vol mix')}"></label><label class="field">${t('起始因子', 'Starting factors')}<select><option>${t('盈余公告漂移 PEAD、低波动', 'PEAD, low volatility')}</option></select><small>${t('从因子库选择；导入因子需负责人确认', 'From the library; imported factors need lead confirmation')}</small></label><label class="field">${t('回测预算', 'Backtest budget')}<input value="8"></label><label class="field full">${t('股票池 · 基准 · 区间 · 成本', 'Universe · benchmark · period · cost')}<input disabled value="${tx(SCOPE)}"></label></div>`, `<button class="btn" data-a="close">${t('取消', 'Cancel')}</button><button class="btn primary" data-a="mktopic">${t('创建', 'Create')}</button>`),
  mktopic: () => { const nm = $('#ntn').value.trim(); const id = 'S' + (TOPICS.length + 1); TOPICS.push({ id, name: [nm, nm], status: 'run', budget: 8, tokens: 0, act: ['排队中：等待 S0 规划首个配方', 'Queued: S0 planning the first recipe'], nodes: [] }); SV.close(); P.sel = id; P.node = null; feed(id, ['新建课题', 'Topic created']); SV.render(); }
};
SV.boot(P);
