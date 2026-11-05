'use strict';
/* 管理驾驶舱：全链路状态 + 待我处理 + 最近动态。所有数字来自各模块的同一份场景状态。 */
const P = { key: 'overview', title: ['管理驾驶舱', 'Cockpit'], tab: 'main', tabs: [['main']] };
P.render = () => {
  const rv = SV.reviews(), pend = k => rv.filter(x => x.type === k && x.st === 'pending').length, mine = k => rv.filter(x => x.mine && (!k || k.includes(x.type))).length;
  const stratN = SV.D.strategies.length + (SV.flag('SC1') === 'done' ? 1 : 0), paused = SV.pfPaused();
  const f0p = SV.flag('pause_F0'), s0p = SV.flag('pause_S0');
  const todo = [
    [t('候选待复核', 'Candidates to review'), pend('factor') + pend('strategy'), t(`因子 ${pend('factor')} · 策略 ${pend('strategy')}`, `${pend('factor')} factor · ${pend('strategy')} strategy`), 'review.html#factor', mine(['factor', 'strategy'])],
    [t('组合待审批', 'Portfolio approvals'), pend('portfolio'), 'PF-1 v3', 'portfolio.html#versions', mine(['portfolio'])],
    [t('风险事件待处置', 'Risk events open'), pend('risk'), pend('risk') ? 'E-31 · ' + t('严重', 'severe') : t('无', 'None'), 'risk.html#events', mine(['risk'])],
    [t('授权申请', 'Authorisation requests'), pend('auth'), pend('auth') ? t('T5 扩展数据范围', 'T5 data scope') : t('无', 'None'), 'review.html#auth', mine(['auth'])],
    [t('我的人工研究', 'My research'), 1, t('因子 T1 / H2c 进行中', 'Factor T1 / H2c in progress'), 'factor.html#wb', SV.role === 'researcher' ? 1 : 0]
  ];
  const chain = [
    ['data.html', t('数据资源', 'Data'), 'r20261105', t('9 个数据集 · 需求 DR-12 处理中', '9 datasets · request DR-12 in progress'), ''],
    ['factor.html', t('因子工厂', 'Factor factory'), t('8 + 导入 331', '8 + 331 imported'), t(`课题 6 · ${f0p ? 'F0 已暂停' : '运行 1'} · 待复核 ${pend('factor')}`, `6 topics · ${f0p ? 'F0 paused' : '1 running'} · ${pend('factor')} in review`), f0p ? 'warn' : ''],
    ['strategy.html', t('策略研究', 'Strategy research'), t(`策略库 ${stratN}`, `Library ${stratN}`), t(`课题 4 · ${s0p ? 'S0 已暂停' : '运行 1'} · 待复核 ${pend('strategy')}`, `4 topics · ${s0p ? 'S0 paused' : '1 running'} · ${pend('strategy')} in review`), s0p ? 'warn' : ''],
    ['portfolio.html', t('组合与执行（模拟）', 'Portfolio (simulated)'), 'PF-1', paused ? t('新调仓已暂停 · 近 20 日超额 +0.6%', 'Rebalancing paused · 20-day excess +0.6%') : t('模拟运行中 · 近 20 日超额 +0.6%', 'Running · 20-day excess +0.6%'), paused ? 'warn' : ''],
    ['risk.html', t('运行与风险', 'Operations & risk'), paused ? t('1 严重', '1 severe') : t('正常', 'Normal'), t('巡检 4 项按时运行', '4 checks on schedule'), paused ? 'bad' : '']
  ];
  const bm = SV.walk(91, 60, .0004, .012), pf = bm.map((v, i) => v * (1 + i * .0004) * (i > 52 ? 1 - (i - 52) * .002 : 1));
  const base = [['16:09', t('策略', 'Strategy'), t('S1：S0 修订为 V2（降低换手）', 'S1: S0 revised to V2 (lower turnover)')], ['15:42', t('风险', 'Risk'), t('E-31 严重：PF-1 单日亏损越线，自动暂停调仓', 'E-31 severe: PF-1 daily loss breach, rebalancing paused')], ['10:58', t('因子', 'Factor'), t('T1 候选 C1 提交审查', 'T1 candidate C1 submitted')], ['06:12', t('策略', 'Strategy'), t('S2 候选 SC1 提交审查', 'S2 candidate SC1 submitted')], ['11-05', t('数据', 'Data'), t('r20261105 发布（延迟 38 分钟）', 'r20261105 published (38 min late)')]];
  const MODN = { factor: t('因子', 'Factor'), strategy: t('策略', 'Strategy'), portfolio: t('组合', 'Portfolio'), risk: t('风险', 'Risk'), data: t('数据', 'Data'), agents: 'Agent' };
  const ev = [...((JSON.parse(localStorage.getItem('svq5') || '{}').ev) || []).map(e => [e.time.slice(0, 5), MODN[e.mod] || e.mod, tx(e.txt)]), ...base].slice(0, 8);
  return SV.head('COCKPIT', '管理驾驶舱', 'Cockpit', '从数据到模拟组合的整条链路，以及今天需要你处理的事。', 'The whole chain from data to simulated portfolios, and what needs you today.')
    + SV.note(['<b>设计要点</b>：驾驶舱只汇总，不另存数字：每个数都来自对应模块的列表，点进去就是那张列表。上面一行按当前身份显示“待我处理”。', '<b>Design</b>: the cockpit only aggregates: every number comes from a module list and links to it. The top row shows what is assigned to the current identity.'])
    + `<div class="todo">${todo.map(([a, n, s, href, m]) => `<a class="${m ? 'hot' : ''}" href="${href}"><span>${a}${m ? ` · <b class="ok-t" style="font-size:10px">${t('待我', 'mine')}</b>` : ''}</span><b>${n}</b><small>${s}</small></a>`).join('')}</div>
    <div class="section-title"><h3>${t('研究到运行', 'From research to operations')}</h3><small>${t('点击进入模块', 'Click to open a module')}</small></div>
    <div class="chain">${chain.map(([href, n, b, s, f]) => `<a class="stage" href="${href}"><span class="sn">${n}${f ? `<span class="badge ${f === 'bad' ? 'red' : 'amber'}">${f === 'bad' ? t('需处理', 'Action') : t('注意', 'Watch')}</span>` : ''}</span><b>${b}</b><small>${s}</small></a>`).join('')}</div>
    <div class="grid2"><div class="card"><div class="card-head"><div><h2>${t('模拟组合 PF-1', 'Simulated portfolio PF-1')}</h2><p>${t('近 60 个交易日 · 模拟资金 1 亿元', 'Last 60 trading days · ¥100m simulated')}</p></div><a class="text-btn" href="portfolio.html#run">${t('详情 →', 'Details →')}</a></div><div class="card-body"><div class="chart-box" style="border:0;padding:0">${SV.line([{ v: bm, c: '#b9b0c2' }, { v: pf, c: '#3b5f9e', w: 2 }], { labels: [[0, '08-11'], [30, '09-24'], [59, '11-06']] })}<div class="cap"><span class="legend-i"><i style="background:#3b5f9e"></i>PF-1</span><span class="legend-i"><i style="background:#b9b0c2"></i>${t('中证800', 'CSI 800')}</span></div></div></div></div>
    <div class="card"><div class="card-head"><h2>${t('最近动态', 'Recent activity')}</h2></div><div class="card-body" style="padding-top:6px"><ul class="feed">${ev.map(([a, m, x]) => `<li><time>${a}</time><span class="tg">${m}</span>${x}</li>`).join('')}</ul></div></div></div>
    <div class="card"><div class="card-head"><div><h2>${t('本月研究用量', 'Research usage this month')}</h2><p>${t('计入台账的试验数与 Token；上限来自研究授权', 'Ledger trials and tokens; caps from research authorisation')}</p></div><a class="text-btn" href="agents.html">${t('Agent 管理 →', 'Agents →')}</a></div><div class="card-body"><div class="grid3" style="grid-template-columns:repeat(4,minmax(0,1fr))">
    ${[[t('因子试验', 'Factor trials'), 14, 120], [t('策略回测', 'Strategy backtests'), 6, 60], [t('因子 Token', 'Factor tokens'), 1092, 1600], [t('策略 Token', 'Strategy tokens'), 157, 600]].map(([a, u, c]) => `<div class="stat"><span>${a}</span><b>${u}${a.includes('Token') ? 'k' : ''} <small>/ ${c}${a.includes('Token') ? 'k' : ''}</small></b><div class="bar" style="margin-top:6px"><i style="width:${u / c * 100}%"></i></div></div>`).join('')}</div></div></div>`;
};
SV.boot(P);
