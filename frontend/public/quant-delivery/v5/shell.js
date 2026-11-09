'use strict';
/* SVQuant 机构量化 V5 · 统一外壳与贯通场景数据（交互原型） */
const $ = s => document.querySelector(s);
const store = (() => { try { return JSON.parse(localStorage.getItem('svq5') || '{}'); } catch (e) { return {}; } })();
let L = store.lang || 'zh';
const t = (z, e) => L === 'en' ? e : z;
const tx = a => a == null ? '' : Array.isArray(a) ? (L === 'en' ? a[1] : a[0]) : a;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const clock = () => new Date().toTimeString().slice(0, 8);

const SV = {
  /* ---------- persistence shared by every page ---------- */
  save() { store.lang = L; localStorage.setItem('svq5', JSON.stringify(store)); },
  get role() { return store.role || 'researcher'; },
  set role(v) { store.role = v; SV.save(); },
  get notes() { return !!store.notes; },
  set notes(v) { store.notes = v; SV.save(); },
  flag(k, v) { store.f = store.f || {}; if (v === undefined) return store.f[k]; store.f[k] = v; SV.save(); },
  log(mod, txt) { store.ev = store.ev || []; store.ev.unshift({ time: clock(), mod, txt }); store.ev = store.ev.slice(0, 30); SV.save(); },
  reset() { const keep = { lang: L }; localStorage.setItem('svq5', JSON.stringify(keep)); location.reload(); },
  setLang(v) { L = v; SV.save(); },

  ROLE: { researcher: ['研究员 · 张新迪', 'Researcher · Zhang Xindi', '研', 'R'], reviewer: ['复核人 · 周宁', 'Reviewer · Zhou Ning', '复', 'V'], lead: ['投资负责人 · 王衡', 'Investment lead · Wang Heng', '负', 'L'] },

  /* ---------- navigation ---------- */
  NAV: [
    ['WORKSPACE', '工作空间', [['overview', '◫', '管理驾驶舱', 'Cockpit', 'index.html']]],
    ['MODULES', '业务模块', [['data', '▤', '数据资源', 'Data', 'data.html'], ['factor', 'ƒ', '因子工厂', 'Factor factory', 'factor-factory.html'], ['strategy', '⌁', '策略研究', 'Strategy research', 'strategy.html'], ['portfolio', '◈', '组合与执行', 'Portfolio', 'portfolio.html'], ['risk', '◎', '运行与风险', 'Operations & risk', 'risk.html']]],
    ['COLLABORATION', '协作与管理', [['review', '▣', '审查中心', 'Review centre', 'review.html'], ['agents', '✧', 'Agent 管理', 'Agents', 'agents.html']]]
  ],
  sidebar(cur) {
    const pend = SV.reviews().filter(r => r.mine).length;
    return `<a class="brand" href="index.html"><span class="seal">旸</span><span><strong>${t('旸谷资本', 'Sunvalley')}</strong><small>SUNVALLEY CAPITAL</small></span></a>
    <div class="workspace"><b>${t('SVQuant · 机构量化平台', 'SVQuant · Institutional Quant')}</b><span>${t('研究与运行工作区', 'Research & operations')}</span></div>
    <nav>${SV.NAV.map(([en, zh, items]) => `<div class="nav-label">${t(zh, en)}</div>` + items.map(([k, ico, z, e, href]) => {
      const cnt = k === 'review' && pend ? `<i class="count">${pend}</i>` : k === 'risk' && SV.openSevere() ? `<i class="count red-c">!</i>` : '';
      return `<a class="nav-item${k === cur ? ' selected' : ''}" href="${href}"${k === cur ? ' aria-current="page"' : ''}><span>${ico}</span>${t(z, e)}${cnt}</a>`; }).join('')).join('')}</nav>
    <footer><span>${t('设计预览 V5 · 场景数据', 'Design preview V5 · scenario data')}</span><a href="README.md">${t('产品说明 ↗', 'Product notes ↗')}</a></footer>`;
  },
  topbar(crumb) {
    const r = SV.ROLE[SV.role];
    return `<span class="crumb">${t('机构工作区', 'Workspace')} <i>/</i> ${crumb}</span>
    <div class="identity"><span class="view-chip" title="${t('当前研究数据视图', 'Current research data view')}">${t('数据视图', 'Data view')} <b>r20261105</b></span><span class="lang"><button class="${L === 'zh' ? 'on' : ''}" data-a="lang" data-v="zh">中</button><button class="${L === 'en' ? 'on' : ''}" data-a="lang" data-v="en">EN</button></span>
    <span class="avatar">${L === 'en' ? r[3] : r[2]}</span><span>${tx(r)}</span></div>`;
  },
  demo(open, extra) {
    if (!open) return `<button class="demo-fab" data-a="demo">${t('演示控制', 'Demo controls')}</button>`;
    const seg = (cur, act, opts) => `<div class="seg">${opts.map(([v, z, e]) => `<button class="${cur === v ? 'on' : ''}" data-a="${act}" data-v="${v}">${t(z, e)}</button>`).join('')}</div>`;
    return `<div class="demo-panel"><h4>${t('演示控制（不属于产品界面）', 'Demo controls (not part of the product)')}<button class="text-btn" data-a="demo">${t('收起', 'Hide')}</button></h4>
    <div class="grp"><span>${t('身份', 'Identity')}</span>${seg(SV.role, 'role', [['researcher', '研究员', 'Researcher'], ['reviewer', '复核人', 'Reviewer'], ['lead', '负责人', 'Lead']])}</div>
    ${extra || ''}
    <div class="grp"><span>${t('设计说明', 'Design notes')}</span>${seg(String(SV.notes), 'notes', [['false', '隐藏', 'Hide'], ['true', '显示', 'Show']])}</div>
    <div class="grp"><button class="btn small" data-a="resetall">${t('重置全部演示数据', 'Reset all demo data')}</button></div></div>`;
  },
  note(n) { return SV.notes ? `<div class="design-note">${tx(n)}</div>` : ''; },
  head(eyebrow, z, e, pz, pe, actions) {
    return `<div class="page-head"><div><span class="eyebrow">${eyebrow}</span><h1>${t(z, e)}</h1><p>${t(pz, pe)}</p></div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>
    <div class="preview-bar"><span>${t('交互原型 · 场景数据：不调用模型、计算服务或真实审批，所有数值为演示。', 'Interactive prototype · scenario data: no models, compute or real approvals; all numbers are illustrative.')}</span></div>`;
  },
  tabs(list, cur) { return `<nav class="tabs">${list.map(([k, z, e, c]) => `<button class="${cur === k ? 'active' : ''}" data-a="tab" data-v="${k}">${t(z, e)}${c ? `<span class="count">${c}</span>` : ''}</button>`).join('')}</nav>`; },
  badge(x) { return `<span class="badge ${x[2]}">${tx(x)}</span>`; },
  modal(title, sub, body, foot) { $('#overlay').innerHTML = `<div class="modal-backdrop" data-a="closebg"><div class="modal wide" role="dialog" aria-modal="true"><div class="modal-header"><div><h2>${title}</h2>${sub ? `<small>${sub}</small>` : ''}</div><button class="modal-close" data-a="close">×</button></div><div class="modal-body">${body}</div>${foot ? `<div class="modal-footer">${foot}</div>` : ''}</div></div>`; },
  close() { $('#overlay').innerHTML = ''; },
  toast(m) { const el = $('#toast'); el.textContent = m; el.classList.add('show'); clearTimeout(SV._tt); SV._tt = setTimeout(() => el.classList.remove('show'), 2600); },

  /* ---------- page boot for the new module pages (factor.html keeps its own loop) ---------- */
  boot(P) {
    SV.P = P; P.demoOpen = false;
    const tabs = (P.tabs || []).map(x => x[0]);
    const h = location.hash.slice(1); if (tabs.includes(h)) P.tab = h;
    const draw = () => {
      document.documentElement.lang = L === 'en' ? 'en' : 'zh-CN'; document.title = `${tx(P.title)} · SVQuant`;
      $('#sidebar').innerHTML = SV.sidebar(P.key); $('#topbar').innerHTML = SV.topbar(tx(P.title)); $('#demo').innerHTML = SV.demo(P.demoOpen, P.demoExtra && P.demoExtra());
      const y = window.scrollY; $('#main').innerHTML = P.render(); window.scrollTo(0, y);
    };
    SV.render = draw;
    const base = {
      lang: v => { SV.setLang(v); draw(); }, demo: () => { P.demoOpen = !P.demoOpen; draw(); },
      role: v => { SV.role = v; draw(); }, notes: v => { SV.notes = v === 'true'; draw(); }, resetall: () => SV.reset(),
      tab: v => { P.tab = v; history.replaceState(null, '', '#' + v); SV.close(); draw(); window.scrollTo(0, 0); },
      close: () => SV.close(), closebg: (v, el, e) => { if (e.target === el) SV.close(); }
    };
    document.addEventListener('click', e => { const el = e.target.closest('[data-a]'); if (!el) return; const f = (P.A || {})[el.dataset.a] || base[el.dataset.a]; if (!f) return; if (el.tagName === 'A' && !el.getAttribute('href')?.includes('.html')) e.preventDefault(); if (el.type !== 'checkbox') e.stopPropagation(); f(el.dataset.v, el, e); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') SV.close(); });
    if (P.onInput) document.addEventListener('input', P.onInput);
    window.addEventListener('hashchange', () => { const h2 = location.hash.slice(1); if (tabs.includes(h2) && h2 !== P.tab) { P.tab = h2; draw(); } });
    draw(); if (P.start) P.start();
  },

  /* ---------- small charts ---------- */
  line(series, opt) { // series: [{v:[...], c:'#..', w, dash}]
    opt = opt || {}; const W = 560, H = opt.h || 170, all = series.flatMap(s => s.v), lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * .08 || .01;
    const x = i => 34 + i * (W - 44) / (series[0].v.length - 1), y = v => 8 + (H - 30) * (1 - (v - lo + pad) / (hi - lo + 2 * pad));
    const ticks = [lo, (lo + hi) / 2, hi].map(v => `<text x="2" y="${y(v) + 3}" font-size="9" fill="#a69caf">${opt.fmt ? opt.fmt(v) : v.toFixed(2)}</text><line x1="32" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#f0ecf3"/>`).join('');
    const lab = (opt.labels || []).map(([i, s]) => `<text x="${x(i)}" y="${H - 6}" font-size="9" fill="#a69caf" text-anchor="middle">${s}</text>`).join('');
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">${ticks}${lab}${series.map(s => `<polyline fill="none" stroke="${s.c}" stroke-width="${s.w || 1.6}" ${s.dash ? 'stroke-dasharray="4 3"' : ''} points="${s.v.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}"/>`).join('')}</svg>`;
  },
  bars(vals, labels, fmt) {
    const W = 300, H = 150, m = Math.max(...vals.map(Math.abs)) || 1, bw = (W - 20) / vals.length, z = H / 2 - 6;
    return `<svg viewBox="0 0 ${W} ${H}" role="img"><line x1="10" x2="${W - 10}" y1="${z}" y2="${z}" stroke="#ddd5e4"/>${vals.map((v, i) => { const h = Math.abs(v) / m * (z - 16); return `<rect x="${12 + i * bw + bw * .18}" y="${v >= 0 ? z - h : z}" width="${bw * .64}" height="${h}" rx="2" fill="${v >= 0 ? '#8e6bb0' : '#c98a97'}"/><text x="${12 + i * bw + bw / 2}" y="${v >= 0 ? z - h - 4 : z + h + 11}" font-size="9" text-anchor="middle" fill="#6d6378">${fmt ? fmt(v) : v}</text><text x="${12 + i * bw + bw / 2}" y="${H - 3}" font-size="9" text-anchor="middle" fill="#a69caf">${labels[i]}</text>`; }).join('')}</svg>`;
  },
  walk(seed, n, drift, vol) { let s = seed >>> 0; const r = () => { s += 0x6D2B79F5; let x = Math.imul(s ^ s >>> 15, 1 | s); x ^= x + Math.imul(x ^ x >>> 7, 61 | x); return ((x ^ x >>> 14) >>> 0) / 4294967296; };
    const out = [1]; for (let i = 1; i < n; i++) out.push(out[i - 1] * (1 + drift + vol * (r() + r() + r() - 1.5))); return out; },

  /* ---------- cross-module scenario (one story across all pages) ---------- */
  D: {
    today: '2026-11-06',
    view: { id: 'r20261105', at: '11-05 18:20', prev: ['r20261104', 'r20261031'] },
    factorLib: 8, factorTopics: { all: 6, run: 1, review: 1, wait: 2 },
    strategies: [ // admitted strategy library (also used by the portfolio)
      { id: 'ST-01', n: ['量价反转增强', 'Price-volume reversal'], f: ['5日反转', '换手率异动'], fe: ['5-day reversal', 'Abnormal turnover'], p: ['中证800 · 前 60 只 · 10 日调仓', 'CSI 800 · top 60 · rebalance 10d'], ir: .92, vir: .58, ex: 5.1, to: 14.2, at: '10-15' },
      { id: 'ST-02', n: ['盈余漂移低换手', 'Low-turnover earnings drift'], f: ['盈余公告漂移 PEAD'], fe: ['Post-earnings drift (PEAD)'], p: ['中证800 · 前 80 只 · 20 日调仓', 'CSI 800 · top 80 · rebalance 20d'], ir: .88, vir: .66, ex: 4.3, to: 6.1, at: '10-29' }
    ]
  },
  /* status helpers driven by persisted flags */
  e31() { return SV.flag('E31') || 'open'; },               // open → ack → resolved
  pfPaused() { return SV.e31() !== 'resolved'; },
  pfv3() { return SV.flag('PFv3') || 'pending'; },          // pending → approved / returned
  openSevere() { return SV.e31() !== 'resolved'; },
  reviews() {
    const role = SV.role, F = k => SV.flag(k);
    const items = [
      { id: 'C1', type: 'factor', obj: ['因子候选 C1 · 拥挤条件下的偏离回补（市值行业中性）', 'Factor candidate C1 · crowded-gap reversal (neutralised)'], by: ['研究系统 · T1/H2a', 'Research system · T1/H2a'], wait: ['1 天', '1 day'], who: 'reviewer', href: 'factor.html#review', st: F('C1') || 'pending' },
      { id: 'SC1', type: 'strategy', obj: ['策略候选 SC1 · 预期修正低换手', 'Strategy candidate SC1 · low-turnover revisions'], by: ['研究系统 · S2/V2', 'Research system · S2/V2'], wait: ['5 小时', '5 hours'], who: 'reviewer', href: 'strategy.html#review', st: F('SC1') || 'pending' },
      { id: 'PF-1 v3', type: 'portfolio', obj: ['组合方案 PF-1 v3 · 调整策略权重 60/40 → 40/60', 'Portfolio PF-1 v3 · reweight 60/40 → 40/60'], by: ['王衡', 'Wang Heng'], wait: ['3 小时', '3 hours'], who: 'reviewer', href: 'portfolio.html#versions', st: SV.pfv3() },
      { id: 'E-31', type: 'risk', obj: ['严重事件 E-31 · PF-1 单日亏损越线，已自动暂停调仓', 'Severe event E-31 · PF-1 daily loss breach, rebalancing auto-paused'], by: ['组合风险巡检', 'Portfolio risk check'], wait: ['17 小时', '17 hours'], who: 'lead', href: 'risk.html#events', st: SV.e31() === 'resolved' ? 'done' : 'pending' },
      { id: 'T5', type: 'auth', obj: ['授权申请 · T5 扩展数据范围到分钟成交', 'Authorisation · T5 extend data scope to minute trades'], by: ['研究系统 · 因子 T5', 'Research system · factor T5'], wait: ['2 天', '2 days'], who: 'lead', href: 'factor.html#ops', st: F('T5') || 'pending' }
    ];
    return items.map(x => ({ ...x, mine: x.st === 'pending' && (x.who === role || (x.who === 'reviewer' && role === 'lead' && x.type !== 'portfolio')) }));
  },
  TYPES: { factor: ['因子候选', 'Factor candidate', 'purple'], strategy: ['策略候选', 'Strategy candidate', 'purple'], portfolio: ['组合审批', 'Portfolio approval', 'blue'], risk: ['风险事件', 'Risk event', 'red'], auth: ['授权申请', 'Authorisation', 'amber'] }
};
