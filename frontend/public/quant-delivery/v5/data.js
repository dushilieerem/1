'use strict';
/* 数据资源：只读目录 + 版本与使用 + 数据需求 + 质量（采集、清洗、发布由数据平台负责） */
const PIT = { pit: ['历史时点', 'Point-in-time', 'green'], ann: ['按公告日', 'By announcement date', 'green'], cur: ['当前版本', 'Current vintage', 'amber'], snap: ['仅快照', 'Snapshot only', 'amber'] };
const DS = [
  ['price_daily', '日行情', 'Daily prices', 14, '2005–', '11-05', 'pit', 'ok', ['停牌日保留前收盘，标记 suspended', 'Suspended days keep the previous close, flagged']],
  ['adj_factor', '复权因子', 'Adjustment factors', 3, '2005–', '11-05', 'pit', 'ok', ['', '']],
  ['limit_status', '涨跌停与停牌', 'Limit & suspension status', 5, '2010–', '11-05', 'pit', 'ok', ['', '']],
  ['index_member', '指数成分', 'Index constituents', 4, '2010–', '11-05', 'pit', 'warn', ['中证800、沪深300 为历史时点；部分行业指数仅有当前快照', 'CSI 800 / CSI 300 are point-in-time; some sector indices are current snapshots only']],
  ['industry_sw', '申万行业分类', 'SW industry classification', 6, '2014–', '11-01', 'cur', 'warn', ['只有当前分类版本，历史回测存在行业口径偏差', 'Only the current classification; backtests carry industry-definition bias']],
  ['fin_statement', '财务报表', 'Financial statements', 112, '2007–', '11-05', 'ann', 'ok', ['按首次公告日可得，修订另存', 'Available from first announcement; restatements stored separately']],
  ['consensus', '一致预期', 'Consensus estimates', 18, '2012–', '11-05', 'pit', 'warn', ['单一来源；发布时间戳按日对齐', 'Single source; release timestamps aligned to day']],
  ['analyst_cov', '分析师覆盖', 'Analyst coverage', 6, '2012–', '10-31', 'pit', 'ok', ['', '']],
  ['market_cap', '市值与股本', 'Market cap & shares', 7, '2005–', '11-05', 'pit', 'ok', ['', '']]
];
const VIEWS = [['r20261105', '11-05 18:58', ['当前', 'Current'], ['策略 S1–S4 · 组合 PF-1（每日跟随当前视图）', 'Strategy S1–S4 · PF-1 (follows current daily)']], ['r20261104', '11-04 18:31', ['历史', 'History'], ['因子 T1、T2', 'Factor T1, T2']], ['r20261031', '10-31 18:30', ['历史', 'History'], ['因子 T4、T6 · 策略库 ST-01、ST-02 入库证据', 'Factor T4, T6 · evidence for ST-01, ST-02']]];
const REQ0 = [
  { id: 'DR-12', n: ['北向持股日度时点数据', 'Daily point-in-time northbound holdings'], from: ['因子课题 T3', 'Factor topic T3'], st: 'doing', at: '11-04', note: ['数据业务处理中：历史回补 2017 年起', 'Data team working on it: backfill from 2017'] },
  { id: 'DR-11', n: ['分钟成交（主动买卖）', 'Minute trades (active buy/sell)'], from: ['因子课题 T5', 'Factor topic T5'], st: 'hold', at: '11-04', note: ['等待研究负责人批准 T5 扩展数据范围', 'Waiting for the lead to approve T5’s scope extension'] },
  { id: 'DR-09', n: ['分析师覆盖历史', 'Analyst coverage history'], from: ['因子课题 T2', 'Factor topic T2'], st: 'done', at: '10-28', note: ['已发布于 r20261031', 'Published in r20261031'] },
  { id: 'DR-07', n: ['港股通日内资金流', 'Intraday Connect flows'], from: ['研究员 张新迪', 'Researcher Zhang Xindi'], st: 'no', at: '10-20', note: ['数据源授权不覆盖，不予支持', 'Not covered by the data licence'] }
];
const RST = { new: ['已提交', 'Submitted', 'blue'], doing: ['处理中', 'In progress', 'purple'], hold: ['等待授权', 'Awaiting approval', 'amber'], done: ['已发布', 'Published', 'green'], no: ['不予支持', 'Not supported', 'gray'] };
const QC = [['缺失率', 'Missing rate', 'ok', '0.02%'], ['重复记录', 'Duplicates', 'ok', '0'], ['停牌与行情一致', 'Suspension vs prices', 'ok', ['通过', 'Pass']], ['复权连续性', 'Adjustment continuity', 'ok', ['通过', 'Pass']], ['财报公告日对齐', 'Statement date alignment', 'na', ''], ['一致预期时间戳', 'Consensus timestamps', 'na', '']];
const P = { key: 'data', title: ['数据资源', 'Data'], tab: 'catalog', tabs: [['catalog'], ['versions'], ['requests'], ['quality']], sel: null, req: SV.flag('reqs') || [] };

function pageCatalog() {
  const d = DS.find(x => x[0] === P.sel);
  return SV.note(['<b>设计要点</b>：数据的采集、清洗和发布由数据平台完成，研究端只读。每个数据集写明时点口径和已知限制，研究和回测报告引用的都是带版本号的视图。', '<b>Design</b>: collection, cleaning and publishing belong to the data platform; research is read-only. Each dataset states its point-in-time basis and known limits; research and backtests cite versioned views.'])
    + `<div class="status-strip"><span class="status-icon">▤</span><div class="status-main"><b>${t('当前研究数据视图 r20261105', 'Current research view r20261105')}</b><p>${t('11-05 18:58 由数据平台发布 · 9 个数据集 · 下次发布约 11-06 18:30', 'Published by the data platform 11-05 18:58 · 9 datasets · next around 11-06 18:30')}</p></div></div>
    <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('数据集', 'Dataset')}</th><th>${t('字段', 'Fields')}</th><th>${t('覆盖', 'Coverage')}</th><th>${t('更新至', 'Updated')}</th><th>${t('时点口径', 'PIT basis')}</th><th>${t('质量', 'Quality')}</th><th>${t('已知限制', 'Known limits')}</th></tr></thead><tbody>
    ${DS.map(x => `<tr data-a="sel" data-v="${x[0]}" style="cursor:pointer"><td><b>${t(x[1], x[2])}</b><small class="mono">${x[0]}</small></td><td>${x[3]}</td><td>${x[4]}</td><td class="mono">${x[5]}</td><td>${SV.badge(PIT[x[6]])}</td><td>${SV.badge(x[7] === 'ok' ? ['通过', 'Pass', 'green'] : ['有限制', 'Limited', 'amber'])}</td><td>${tx(x[8]) || '—'}</td></tr>`).join('')}
    <tr><td><b>${t('北向持股', 'Northbound holdings')}</b><small class="mono">hk_hold</small></td><td colspan="6"><span class="subtle">${t('未发布 · 数据需求 DR-12 处理中', 'Not published · request DR-12 in progress')}</span></td></tr></tbody></table></div></div>
    ${d ? `<div class="drawer"><h3>${t(d[1], d[2])} <span class="mono">${d[0]}</span></h3><div class="kv" style="margin-top:8px"><span>${t('字段示例', 'Sample fields')}</span><b class="mono">${d[0] === 'price_daily' ? 'open, high, low, close, volume, amount, turnover, suspended …' : t('完整字段表由数据平台提供', 'Full field list from the data platform')}</b><span>${t('可得时点', 'Available at')}</span><b>${t('T 日 18:30 后（研究与回测按 T+1 使用）', 'After 18:30 on T (used from T+1 in research and backtests)')}</b><span>${t('使用方', 'Used by')}</span><b>${t('因子 T1–T6 · 策略 S1–S4 · PF-1', 'Factor T1–T6 · Strategy S1–S4 · PF-1')}</b></div></div>` : ''}`;
}
function pageVersions() {
  return `<div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('视图', 'View')}</th><th>${t('发布时间', 'Published')}</th><th>${t('状态', 'Status')}</th><th>${t('锁定此视图的研究与组合', 'Locked by')}</th></tr></thead><tbody>
  ${VIEWS.map((v, i) => `<tr><td class="mono"><b>${v[0]}</b></td><td>${v[1]}</td><td>${SV.badge(i ? ['历史', 'History', 'gray'] : ['当前', 'Current', 'green'])}</td><td>${tx(v[3])}</td></tr>`).join('')}</tbody></table></div>
  <div class="card-footer"><small>${t('课题创建时锁定视图；报告绑定视图版本，事后可按同一视图复现', 'Topics lock a view at creation; reports bind the view so results can be reproduced')}</small></div></div>`;
}
function pageRequests() {
  const all = [...P.req, ...REQ0];
  return `<div class="card"><div class="card-head"><div><h2>${t('数据需求', 'Data requests')}</h2><p>${t('提交后转给数据业务处理，状态在这里同步', 'Routed to the data team; status syncs here')}</p></div><button class="btn primary small" data-a="newreq">＋ ${t('提交需求', 'New request')}</button></div>
  <div class="table-wrap"><table class="table"><thead><tr><th>${t('编号', 'ID')}</th><th>${t('需求', 'Request')}</th><th>${t('来源', 'From')}</th><th>${t('提交', 'Filed')}</th><th>${t('状态', 'Status')}</th><th>${t('说明', 'Note')}</th></tr></thead><tbody>
  ${all.map(r => `<tr><td class="mono">${r.id}</td><td><b>${tx(r.n)}</b></td><td>${tx(r.from)}</td><td class="mono">${r.at}</td><td>${SV.badge(RST[r.st])}</td><td>${tx(r.note)}</td></tr>`).join('')}</tbody></table></div></div>`;
}
function pageQuality() {
  return `<div class="card"><div class="card-head"><div><h2>${t('质量检查 · r20261105', 'Quality checks · r20261105')}</h2><p>${t('来自数据平台的发布检查', 'From the data platform’s release checks')}</p></div></div><div class="card-body"><table class="gates">${QC.map(q => `<tr><td>${t(q[0], q[1])}</td><td class="r">${q[2] === 'na' ? `<span class="badge gray">${t('待接入', 'Not connected')}</span>` : tx(q[3])}</td><td class="r">${q[2] === 'ok' ? '<span class="ok-t">✓</span>' : '<span class="subtle">—</span>'}</td></tr>`).join('')}</table>
  <div class="hint" style="margin:12px 0 0">${t('“待接入”表示数据平台尚未提供该项检查结果，研究端不自行计算。', '“Not connected” means the data platform does not yet publish that check; research does not compute it itself.')}</div></div></div>`;
}
P.render = () => SV.head('DATA RESOURCES', '数据资源', 'Data resources', '查看研究可用的数据、口径和版本；需要新数据时提交需求。', 'Browse research data, definitions and versions; file a request when you need new data.')
  + SV.tabs([['catalog', '数据目录', 'Catalogue'], ['versions', '版本与使用', 'Versions & usage'], ['requests', '数据需求', 'Requests', [...P.req, ...REQ0].filter(r => r.st === 'doing' || r.st === 'new' || r.st === 'hold').length], ['quality', '质量', 'Quality']], P.tab)
  + { catalog: pageCatalog, versions: pageVersions, requests: pageRequests, quality: pageQuality }[P.tab]();
P.A = {
  sel: v => { P.sel = P.sel === v ? null : v; SV.render(); },
  newreq: () => SV.modal(t('提交数据需求', 'New data request'), t('转给数据业务处理', 'Routed to the data team'), `<div class="field-grid"><label class="field full">${t('需要的数据', 'Data needed')}<input id="rq" value="${t('机构调研记录（日度，按公告日）', 'Institutional site visits (daily, by announcement date)')}"></label><label class="field">${t('用途', 'Purpose')}<select><option>${t('因子研究', 'Factor research')}</option><option>${t('策略研究', 'Strategy research')}</option></select></label><label class="field">${t('区间与频率', 'Period & frequency')}<input value="${t('2015 至今 · 日度', '2015– · daily')}"></label><label class="field full">${t('关键字段', 'Key fields')}<textarea>${t('股票代码、调研日期、公告日期、参与机构数', 'Ticker, visit date, announcement date, number of institutions')}</textarea></label></div>`, `<button class="btn" data-a="close">${t('取消', 'Cancel')}</button><button class="btn primary" data-a="mkreq">${t('提交', 'Submit')}</button>`),
  mkreq: () => { const n = $('#rq').value.trim(); P.req.unshift({ id: 'DR-' + (13 + P.req.length), n: [n, n], from: [t('研究员 张新迪', 'Researcher Zhang Xindi'), 'Researcher Zhang Xindi'], st: 'new', at: '11-06', note: ['已转给数据业务', 'Routed to the data team'] }); SV.flag('reqs', P.req); SV.close(); SV.log('data', ['提交数据需求', 'Data request filed']); SV.toast(t('已提交，数据业务处理后会更新状态', 'Submitted; the data team will update the status')); SV.render(); }
};
SV.boot(P);
