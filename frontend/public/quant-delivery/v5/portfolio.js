'use strict';
/* 组合与执行 · 仅模拟（交互原型，场景数据） */
const STRATS = () => { const s = SV.D.strategies.map(x => ({ ...x })); if (SV.flag('SC1') === 'done') s.push({ id: 'ST-03', n: ['预期修正低换手组合', 'Low-turnover revision strategy'], p: ['中证800 · 前 80 只 · 10 日调仓', 'CSI 800 · top 80 · rebalance 10d'], ir: .7, vir: .52, ex: 3.3, to: 4.5, at: '11-06' }); return s; };
const META = { 'ST-01': { N: 60, ind: { e: .22, h: .14, b: .08 } }, 'ST-02': { N: 80, ind: { e: .12, h: .28, b: .18 } }, 'ST-03': { N: 80, ind: { e: .10, h: .24, b: .20 } } };
const LIMIT = { stock: 3, ind: 25, overlap: 40, liq: 5 };
const IND = { e: ['电子', 'Electronics'], h: ['医药生物', 'Healthcare'], b: ['银行', 'Banks'] };

const VERS = () => {
  const v3 = SV.pfv3();
  return [
    { v: 'v1', w: { 'ST-01': 100 }, by: ['王衡', 'Wang Heng'], ap: ['周宁', 'Zhou Ning'], at: '08-12', st: 'retired', note: ['首个模拟方案', 'First simulated plan'] },
    { v: 'v2', w: { 'ST-01': 60, 'ST-02': 40 }, by: ['王衡', 'Wang Heng'], ap: ['周宁', 'Zhou Ning'], at: '10-20', st: v3 === 'approved' ? 'retired' : 'running', note: ['加入 ST-02', 'Added ST-02'] },
    { v: 'v3', w: { 'ST-01': 40, 'ST-02': 60 }, by: ['王衡', 'Wang Heng'], ap: v3 === 'approved' ? ['周宁', 'Zhou Ning'] : null, at: '11-06', st: v3 === 'approved' ? 'running' : v3, note: ['降低反转策略权重：近 20 日 ST-01 回撤较大', 'Lower the reversal weight after ST-01’s recent drawdown'] },
    ...(SV.flag('PFv4') ? [{ v: 'v4', w: SV.flag('PFv4'), by: ['王衡', 'Wang Heng'], ap: SV.flag('PFv4st') === 'approved' ? ['周宁', 'Zhou Ning'] : null, at: clock().slice(0, 5), st: SV.flag('PFv4st') || 'pending', note: ['新提交的方案', 'Newly submitted plan'] }] : [])
  ];
};
const VST = { running: ['模拟运行中', 'Running (simulated)', 'live'], pending: ['待审批', 'Pending approval', 'purple'], retired: ['已停用', 'Retired', 'gray'], returned: ['已退回', 'Returned', 'amber'], approved: ['已批准', 'Approved', 'green'] };

function checks(w) {
  const ids = Object.keys(w).filter(k => w[k] > 0), sum = ids.reduce((a, k) => a + (+w[k] || 0), 0);
  const stock = Math.max(...ids.map(k => w[k] / META[k].N), 0) + (ids.length > 1 ? Math.min(...ids.map(k => w[k] / META[k].N)) : 0);
  const ind = Object.keys(IND).map(i => [i, ids.reduce((a, k) => a + w[k] * META[k].ind[i], 0)]).sort((a, b) => b[1] - a[1])[0];
  const overlap = ids.length > 1 ? 18 : 0;
  return [
    [t('权重合计', 'Weights sum'), `${sum}%`, '= 100%', sum === 100, true],
    [t('单票集中度（合并持仓后）', 'Single-name weight (merged)'), `${stock.toFixed(1)}%`, `≤ ${LIMIT.stock}%`, stock <= LIMIT.stock, true],
    [t('行业集中度', 'Industry concentration'), `${tx(IND[ind[0]])} ${ind[1].toFixed(1)}%`, `≤ ${LIMIT.ind}%`, ind[1] <= LIMIT.ind, true],
    [t('策略间持仓重叠', 'Holdings overlap'), `${overlap}%`, `≤ ${LIMIT.overlap}% ${t('（提示）', '(warning)')}`, overlap <= LIMIT.overlap, false],
    [t('流动性：持仓 / 日均成交额', 'Liquidity: position / ADV'), '0.8%', `≤ ${LIMIT.liq}%`, true, true]
  ];
}
const checkTable = c => `<table class="gates">${c.map(([n, v, need, ok, hard]) => `<tr><td>${n}${hard ? '' : ` <span class="subtle">${t('提示项', 'warning only')}</span>`}</td><td class="r">${v}</td><td class="r subtle">${need}</td><td class="r">${ok ? '<span class="ok-t">✓</span>' : `<span class="${hard ? 'bad-t' : 'warn-t'}">✗</span>`}</td></tr>`).join('')}</table>`;
const hardFail = c => c.some(x => x[4] && !x[3]);

const P = { key: 'portfolio', title: ['组合与执行', 'Portfolio & execution'], tab: 'plan', tabs: [['plan'], ['run'], ['versions']], draft: null, cap: '100,000,000' };
const running = () => VERS().find(v => v.st === 'running');

function strip() {
  const r = running(), paused = SV.pfPaused();
  return `<div class="sim-bar"><b>${t('模拟环境', 'Simulated environment')}</b>${t('不连接真实账户，不产生真实订单；所有成交为按次日开盘价的模拟成交。', 'No real accounts or orders; every fill is simulated at the next open.')}</div>
  <div class="status-strip ${paused ? 'warning' : ''}"><span class="status-icon">◈</span><div class="status-main"><b>PF-1 · ${t('多策略 A 股增强', 'Multi-strategy A-share enhanced')} · ${r.v} ${paused ? t('· 新调仓已暂停', '· rebalancing paused') : t('· 模拟运行中', '· running (simulated)')}</b>
  <p>${t('模拟资金 1 亿元 · 基准 中证800 · 自 08-12 起', 'Simulated capital ¥100m · benchmark CSI 800 · since 08-12')} · ${Object.entries(r.w).map(([k, v]) => `${k} ${v}%`).join(' · ')}${paused ? ` · ${t('原因：严重事件 E-31（单日亏损越线）', 'Reason: severe event E-31 (daily loss breach)')}` : ''}</p></div>${paused ? `<div class="actions"><a class="btn small" href="risk.html#events">${t('查看事件 →', 'View event →')}</a></div>` : ''}</div>`;
}

function pagePlan() {
  const lead = SV.role === 'lead', ss = STRATS();
  if (!P.draft) P.draft = { ...running().w };
  const w = P.draft, c = checks(w), bad = hardFail(c);
  return SV.note(['<b>设计要点</b>：组合只能从策略库选已复核的策略。风险检查是确定性规则，硬性项不通过就不能提交；提交后方案版本冻结，审批人不能是提交人。本期只有模拟，没有真实下单入口。', '<b>Design</b>: portfolios select only reviewed strategies from the library. Risk checks are deterministic; hard failures block submission. Submitted versions freeze and the approver cannot be the submitter. Simulation only — no real order entry.'])
    + `<div class="grid-side"><div class="card"><div class="card-head"><div><h2>${t('编辑方案（新版本草稿）', 'Edit plan (new version draft)')}</h2><p>${t('基于当前运行版本', 'Based on the running version')} ${running().v} · ${lead ? t('提交后需复核人审批', 'needs reviewer approval after submission') : t('仅投资负责人可编辑', 'Only the investment lead can edit')}</p></div></div>
    <div class="table-wrap"><table class="table"><thead><tr><th></th><th>${t('策略（来自策略库）', 'Strategy (from library)')}</th><th>${t('配方', 'Recipe')}</th><th>${t('研发 / 封存 IR', 'Dev / sealed IR')}</th><th>${t('权重 %', 'Weight %')}</th></tr></thead><tbody>
    ${ss.map(s => `<tr><td><input type="checkbox" data-a="pick" data-v="${s.id}" ${w[s.id] != null ? 'checked' : ''} ${lead ? '' : 'disabled'}></td><td><b>${s.id} · ${tx(s.n)}</b>${s.at === '11-06' ? `<small class="ok-t">${t('刚入库', 'Just admitted')}</small>` : ''}</td><td>${tx(s.p)}</td><td>${s.ir.toFixed(2)} / ${s.vir.toFixed(2)}</td><td class="wt">${w[s.id] != null ? `<input data-w="${s.id}" value="${w[s.id]}" ${lead ? '' : 'disabled'}>` : '<span class="subtle">—</span>'}</td></tr>`).join('')}</tbody></table></div>
    <div class="card-body"><div class="field-grid"><label class="field">${t('模拟资金（元）', 'Simulated capital (¥)')}<input value="${P.cap}" ${lead ? '' : 'disabled'}></label><label class="field">${t('有效期', 'Valid until')}<input value="2027-02-06" ${lead ? '' : 'disabled'}></label>
    <label class="field">${t('单票上限', 'Single-name cap')}<input disabled value="${LIMIT.stock}%"><small>${t('来自风险规则 v3', 'From risk rules v3')}</small></label><label class="field">${t('行业上限', 'Industry cap')}<input disabled value="${LIMIT.ind}%"><small>${t('来自风险规则 v3', 'From risk rules v3')}</small></label>
    <label class="field full">${t('调整说明', 'Reason for change')}<textarea id="why">${t('ST-01 近 20 日回撤较大，降低其权重。', 'Lower ST-01 after its recent drawdown.')}</textarea></label></div></div>
    <div class="card-footer"><small>${t('环境：模拟 · 提交后版本冻结', 'Environment: simulated · version freezes on submit')}</small><button class="btn primary" data-a="submitplan" ${lead && !bad ? '' : 'disabled'}>${t('提交审批', 'Submit for approval')}</button></div></div>
    <div class="side"><div class="card"><div class="card-head"><div><h2>${t('风险检查', 'Risk checks')}</h2><p>${t('随编辑实时重算', 'Recomputed as you edit')}</p></div>${bad ? SV.badge(['不能提交', 'Blocked', 'red']) : SV.badge(['可提交', 'OK to submit', 'green'])}</div><div class="card-body">${checkTable(c)}</div></div>
    <div class="card"><div class="card-body"><div class="hint" style="margin:0">${t('试一试：把权重改成合计不等于 100%，或把 ST-02 提到 100%（医药行业超过 25%），提交按钮会被禁用并显示原因。', 'Try: make weights not sum to 100%, or set ST-02 to 100% (healthcare above 25%); submission is blocked with the reason.')}</div></div></div></div></div>`;
}

function pageRun() {
  const r = running(), paused = SV.pfPaused();
  const bm = SV.walk(91, 60, .0004, .012), pf = bm.map((v, i) => v * (1 + i * .0004) * (i > 52 ? 1 - (i - 52) * .002 : 1));
  const orders = [['600xx1', t('某电子股 A', 'Electronics A'), t('买入', 'Buy'), '0.0 → 1.6%', '41.20'], ['000xx7', t('某医药股 B', 'Healthcare B'), t('买入', 'Buy'), '0.0 → 1.0%', '18.05'], ['601xx3', t('某银行股 C', 'Bank C'), t('卖出', 'Sell'), '1.0% → 0.0', '6.31'], ['300xx5', t('某电子股 D', 'Electronics D'), t('减持', 'Trim'), '2.1% → 1.6%', '77.90']];
  const log = [['11-06 15:40', paused ? t('组合风险巡检：E-31 未解除，今日不生成订单意图', 'Risk check: E-31 open, no order intents today') : t('生成 11-06 订单意图 36 笔', 'Generated 36 order intents for 11-06'), paused ? 'warn' : ''],
    ['11-06 09:31', t('按开盘价模拟成交 38 笔 · 模拟费用 1.9 万元', 'Simulated 38 fills at the open · simulated cost ¥19k'), ''],
    ['11-05 15:42', t('E-31 严重：单日亏损 -2.3%（阈值 -2.0%）→ 自动暂停新调仓', 'E-31 severe: daily loss -2.3% (limit -2.0%) → rebalancing auto-paused'), 'bad'],
    ['11-05 15:40', t('生成 11-05 订单意图 38 笔（运行键 PF-1/v2/2026-11-05）', 'Generated 38 order intents (run key PF-1/v2/2026-11-05)'), ''],
    ['11-05 15:41', t('重复触发同一运行键：结果不变，未重复成交', 'Same run key triggered again: unchanged, no duplicate fills'), '']];
  return `<div class="metrics">${[[t('模拟净值', 'Simulated NAV'), pf[59].toFixed(4)], [t('累计超额', 'Cumulative excess'), ((pf[59] / bm[59] - 1) * 100).toFixed(1) + '%'], [t('持仓 / 现金', 'Holdings / cash'), t('118 只 · 1.2%', '118 names · 1.2%')], [t('今日订单意图', 'Order intents today'), paused ? t('0（已暂停）', '0 (paused)') : '36']].map(([a, b]) => `<div class="stat"><span>${a}</span><b>${b}</b></div>`).join('')}</div>
  <div class="grid2"><div class="card"><div class="card-head"><div><h2>${t('模拟净值', 'Simulated NAV')}</h2><p>${t('PF-1 与中证800，近 60 个交易日', 'PF-1 vs CSI 800, last 60 trading days')}</p></div></div><div class="card-body"><div class="chart-box" style="border:0;padding:0">${SV.line([{ v: bm, c: '#b9b0c2' }, { v: pf, c: '#3b5f9e', w: 2 }], { labels: [[0, '08-11'], [30, '09-24'], [59, '11-06']], fmt: v => v.toFixed(2) })}<div class="cap"><span class="legend-i"><i style="background:#3b5f9e"></i>PF-1（${t('模拟', 'simulated')}）</span><span class="legend-i"><i style="background:#b9b0c2"></i>${t('中证800', 'CSI 800')}</span></div></div></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('运行记录', 'Run log')}</h2><p>${t('服务端每个交易日收盘后运行，不依赖页面打开', 'Runs on the server after each close; no page needs to be open')}</p></div></div><div class="card-body"><ul class="feed">${log.map(([a, b, k]) => `<li><time>${a}</time><span class="${k === 'bad' ? 'bad-t' : k === 'warn' ? 'warn-t' : ''}">${b}</span></li>`).join('')}</ul></div></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('订单意图 · 11-05 生成，11-06 开盘模拟成交', 'Order intents · generated 11-05, filled 11-06 open (simulated)')}</h2><p>${t('由各策略固定版本在数据视图 r20261105 上计算目标持仓，合并后生成；以下为部分示例', 'Target holdings from each frozen strategy version on view r20261105, merged; sample rows')}</p></div><span class="badge blue">${t('模拟', 'Simulated')}</span></div>
  <div class="table-wrap"><table class="table"><thead><tr><th>${t('代码', 'Code')}</th><th>${t('名称', 'Name')}</th><th>${t('方向', 'Side')}</th><th>${t('目标权重', 'Target weight')}</th><th>${t('模拟成交价（次日开盘）', 'Simulated fill (next open)')}</th><th>${t('来源策略', 'From')}</th><th>${t('状态', 'Status')}</th></tr></thead><tbody>
  ${orders.map((o, i) => `<tr><td class="mono">${o[0]}</td><td>${o[1]}</td><td>${o[2]}</td><td>${o[3]}</td><td>${o[4]}</td><td>${i % 2 ? 'ST-02' : 'ST-01'}</td><td>${SV.badge(['已模拟成交', 'Filled (sim)', 'green'])}</td></tr>`).join('')}</tbody></table></div></div>`;
}

function pageVersions() {
  const vs = VERS(), rv = SV.role === 'reviewer';
  return SV.note(['<b>设计要点</b>：每次修改权重或策略都是新版本，旧版本保留；审批绑定版本号、环境（模拟）、资金上限与有效期。提交人不能审批自己的方案。', '<b>Design</b>: every change is a new version and old ones stay. Approval binds version, environment (simulated), capital limit and expiry. Submitters cannot approve their own plan.'])
    + `<div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('版本', 'Version')}</th><th>${t('策略权重', 'Weights')}</th><th>${t('说明', 'Note')}</th><th>${t('提交人', 'Submitted by')}</th><th>${t('审批人', 'Approved by')}</th><th>${t('状态', 'Status')}</th><th></th></tr></thead><tbody>
    ${vs.map(v => `<tr><td><b>PF-1 ${v.v}</b><small>${v.at}</small></td><td>${Object.entries(v.w).map(([k, x]) => `${k} ${x}%`).join('<br>')}</td><td>${tx(v.note)}</td><td>${tx(v.by)}</td><td>${v.ap ? tx(v.ap) : '—'}</td><td>${SV.badge(VST[v.st])}</td>
    <td>${v.st === 'pending' ? (rv ? `<div style="display:flex;gap:6px"><button class="btn small" data-a="appr" data-v="${v.v}|returned">${t('退回', 'Return')}</button><button class="btn small primary" data-a="appr" data-v="${v.v}|approved">${t('批准（模拟）', 'Approve (simulated)')}</button></div>` : `<span class="subtle">${SV.role === 'lead' ? t('提交人不能审批自己的方案', 'Submitters cannot approve their own plan') : t('需复核人审批', 'Needs the reviewer')}</span>`) : ''}</td></tr>`).join('')}</tbody></table></div>
    <div class="card-footer"><small>${t('审批内容：环境 = 模拟 · 资金上限 1 亿元 · 有效期 3 个月 · 批准后下一交易日生效', 'Approval covers: environment = simulated · capital ¥100m · valid 3 months · effective next trading day')}</small></div></div>`;
}

P.render = () => SV.head('PORTFOLIO', '组合与执行', 'Portfolio & execution', '把复核通过的策略组成模拟组合，审批后由服务端每日生成订单意图并模拟成交。', 'Combine reviewed strategies into a simulated portfolio; once approved the server generates daily order intents and simulated fills.')
  + strip() + SV.tabs([['plan', '组合方案', 'Plan'], ['run', '模拟运行', 'Simulated run'], ['versions', '版本与审批', 'Versions & approval', VERS().filter(v => v.st === 'pending').length]], P.tab)
  + { plan: pagePlan, run: pageRun, versions: pageVersions }[P.tab]();
P.onInput = e => { const k = e.target.dataset.w; if (k) { P.draft[k] = +e.target.value || 0; const box = document.querySelector('.side .card .card-body'); if (box) { SV.render(); const el = document.querySelector(`[data-w="${k}"]`); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } } } };
P.A = {
  pick: (v, el) => { if (el.checked) P.draft[v] = 0; else delete P.draft[v]; SV.render(); },
  submitplan: () => { SV.flag('PFv4', { ...P.draft }); SV.flag('PFv4st', null); SV.log('portfolio', ['PF-1 v4 提交审批', 'PF-1 v4 submitted']); P.draft = null; P.tab = 'versions'; history.replaceState(null, '', '#versions'); SV.toast(t('已提交，版本 v4 冻结，等待复核人审批', 'Submitted; v4 frozen, awaiting the reviewer')); SV.render(); },
  appr: v => { const [ver, d] = v.split('|'); if (ver === 'v3') SV.flag('PFv3', d); else SV.flag('PFv4st', d);
    SV.log('portfolio', [`PF-1 ${ver} ${d === 'approved' ? '已批准（模拟），下一交易日生效' : '已退回'}`, `PF-1 ${ver} ${d}`]); SV.toast(d === 'approved' ? t('已批准：下一交易日起按新版本模拟运行', 'Approved: runs on the new version from the next trading day') : t('已退回', 'Returned')); SV.render(); }
};
SV.boot(P);
