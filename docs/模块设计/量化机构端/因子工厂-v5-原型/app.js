'use strict';
/* 因子工厂 V5 · 研究系统 + 人工工作台（交互原型，场景数据） */
const $ = s => document.querySelector(s);
let L = 'zh';
const t = (z, e) => L === 'en' ? e : z;
const tx = a => a == null ? '' : Array.isArray(a) ? (L === 'en' ? a[1] : a[0]) : a;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const clock = () => new Date().toTimeString().slice(0, 8);

/* ---------- statistics helpers ---------- */
function invN(p) { // Acklam inverse normal CDF
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.3577518672690, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425; let q, r;
  if (p < pl) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p <= 1 - pl) { q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); }
  q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
}
/* Bonferroni-adjusted two-sided 5% bar given K trials in the topic ledger */
const needT = K => invN(1 - 0.025 / Math.max(1, K));
const GATE = { ic: 0.02, cov: 0.90, corr: 0.70, holdT: 1.96 };
function rng(seed) { let s = seed >>> 0; return () => { s += 0x6D2B79F5; let x = Math.imul(s ^ s >>> 15, 1 | s); x ^= x + Math.imul(x ^ x >>> 7, 61 | x); return ((x ^ x >>> 14) >>> 0) / 4294967296; }; }
function gauss(r) { let u = 0, v = 0; while (!u) u = r(); while (!v) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
function hash(s) { let h = 2166136261; for (const ch of s) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }

/* ---------- scenario data ---------- */
const LIBNAME = {
  rev5: ['5日反转', '5-day reversal'], abto: ['换手率异动', 'Abnormal turnover'], crm: ['一致预期调整动量', 'Consensus revision momentum'],
  pead: ['盈余公告漂移 PEAD', 'Post-earnings drift (PEAD)'], lowvol: ['低波动', 'Low volatility'], c1: ['待审候选 C1', 'Pending candidate C1']
};
const SCOPE = ['日频 · 中证800 历史时点成分 · 研发 2019–2024 · 封存 2025', 'Daily · CSI 800 point-in-time · dev 2019–2024 · sealed 2025'];
const CODE = {
  H2a: 'gap   = open / delay(close, 1) - 1\ncrowd = rank(turnover / ts_mean(turnover, 20)) > 0.8\nalpha = neutralize(-gap * crowd, by=[log_mcap, sw_l1])',
  H2c: 'gap   = open / delay(close, 1) - 1\ncrowd = rank(turnover / ts_mean(turnover, 20)) > 0.8\nalpha = group_rank(-gap * crowd, sw_l1)',
  H2cS: 'gap   = open / delay(close, 1) - 1\ncrowd = rank(turnover / ts_mean(turnover, 20)) > 0.8\nalpha = neutralize(group_rank(-gap * crowd, sw_l1), by=[log_mcap])',
  T2: 'rev   = eps_fy1_consensus / delay(eps_fy1_consensus, 20) - 1\nalpha = neutralize(rev, by=[log_mcap, sw_l1, f_consensus_mom]) * (analyst_cnt >= 3)',
  tpl: '# 在此编写因子表达式\nalpha = '
};

const TOPICS = [
  { id: 'T1', name: ['成交拥挤与短期反转', 'Crowding and short-term reversal'], kind: 'new', status: 'review', budget: 12, tokens: 46,
    act: ['候选 C1 已提交审查；人工分支 H2c 进行中', 'Candidate C1 submitted for review; human branch H2c in progress'],
    nodes: [
      { id: 'H1', parent: null, by: 'agent', title: ['开盘偏离的短期回补', 'Short-term reversal of opening gaps'], status: 'fail',
        hyp: ['开盘价相对前收盘的大幅偏离多由短期情绪和流动性冲击造成，随后数日部分回补。', 'Large open-vs-previous-close gaps come from short-lived sentiment and liquidity shocks and partly revert over the following days.'],
        steps: [{ k: 'I', ok: true, note: ['表达式校验通过；开盘价按 T 日可得口径', 'Checks passed; open price as available on day T'] },
          { k: 'E', n: 1, ic: .008, t: 1.1, K: 1, corr: .41, cw: 'rev5', res: 'fail' },
          { k: 'D', txt: ['整体信号弱；分组显示高拥挤股票回补更明显 → 修订为 H2，另开方向 H3', 'Weak overall; reversal is stronger among crowded stocks → revise into H2, also try H3'] }] },
      { id: 'H2', parent: 'H1', by: 'agent', title: ['拥挤条件下的偏离回补', 'Gap reversal under crowding'], status: 'fail',
        hyp: ['只有在成交拥挤（换手相对自身历史显著放大）时，开盘偏离才主要反映非信息交易，回补更强。', 'Only when trading is crowded (turnover far above its own history) do gaps mainly reflect non-informational trading, so reversal is stronger.'],
        steps: [{ k: 'I', ok: true }, { k: 'E', n: 2, ic: .019, t: 2.0, K: 2, corr: .52, cw: 'rev5', res: 'fail' },
          { k: 'D', txt: ['收益集中在小市值股票（市值暴露 0.45）→ 分三条路继续', 'Returns concentrate in small caps (size exposure 0.45) → continue on three paths'] }] },
      { id: 'H2a', parent: 'H2', by: 'agent', title: ['市值与行业中性化', 'Size- and industry-neutralised'], status: 'review', code: CODE.H2a,
        hyp: ['去掉市值和行业暴露后，拥挤条件下的偏离回补仍然存在。', 'The crowded-gap reversal survives after removing size and industry exposure.'],
        steps: [{ k: 'I', ok: true, note: ['对对数市值、申万一级行业做截面回归取残差', 'Cross-sectional residual on log market cap and SW level-1 industry'] },
          { k: 'E', n: 3, ic: .024, t: 3.1, K: 3, corr: .62, cw: 'rev5', res: 'ok' },
          { k: 'D', txt: ['研发检验达标 → 申请封存验证', 'Development test passed → request sealed validation'] },
          { k: 'V', ic: .019, t: 2.3, res: 'ok' },
          { k: 'D', txt: ['独立复核通过 → 提交审查，候选 C1', 'Independent check passed → submitted as candidate C1'] }] },
      { id: 'H2b', parent: 'H2', by: 'agent', title: ['以换手突变替代拥挤代理', 'Turnover shock as crowding proxy'], status: 'aband',
        hyp: ['用换手率的突变替代相对换手作为拥挤代理。', 'Use turnover shocks instead of relative turnover as the crowding proxy.'],
        steps: [{ k: 'I', ok: true }, { k: 'E', n: 4, ic: .027, t: 2.9, K: 4, corr: .86, cw: 'abto', res: 'warn' },
          { k: 'X', txt: ['显著，但与库内“换手率异动”相关 0.86，属于重复 → 放弃', 'Significant, but correlates 0.86 with library "Abnormal turnover" — a duplicate → abandoned'] }] },
      { id: 'H2c', parent: 'H2', by: 'human', who: ['张新迪', 'Zhang Xindi'], title: ['行业内排序', 'Within-industry ranking'], status: 'human', code: CODE.H2c,
        hyp: ['在行业内对拥挤偏离排序，去掉行业轮动带来的共同波动。', 'Rank crowded gaps within each industry to strip common industry swings.'],
        steps: [{ k: 'I', ok: true, note: ['人工实现，尚未检验', 'Implemented by hand; not tested yet'] }] },
      { id: 'H3', parent: 'H1', by: 'agent', title: ['隔夜收益拥挤', 'Overnight-return crowding'], status: 'aband',
        hyp: ['隔夜收益的拥挤程度预测次日反转。', 'Crowding in overnight returns predicts next-day reversal.'],
        steps: [{ k: 'I', ok: true }, { k: 'E', n: 5, ic: .011, t: 1.3, K: 5, corr: .38, cw: 'rev5', res: 'fail' },
          { k: 'X', txt: ['机制不成立，预算内没有合理修订 → 放弃此方向', 'Mechanism not supported, no sensible revision within budget → direction abandoned'] }] }
    ] },
  { id: 'T2', name: ['分析师预期修正的滞后反应', 'Lagged reaction to analyst revisions'], kind: 'new', status: 'run', budget: 10, tokens: 2,
    act: ['排队中，即将开始', 'Queued, starting shortly'], nodes: [] },
  { id: 'T3', name: ['北向持股变化的信息含量', 'Information in northbound holdings'], kind: 'new', status: 'wait', budget: 8, tokens: 6,
    act: ['等待数据：北向持股日度时点数据尚未发布到研究数据视图（请求 DR-12）', 'Waiting for data: daily point-in-time northbound holdings not yet in the research view (request DR-12)'],
    nodes: [{ id: 'H1', parent: null, by: 'agent', title: ['北向增持领先收益', 'Northbound accumulation leads returns'], status: 'wait',
      hyp: ['北向资金持续增持的股票未来 20 日有超额收益。', 'Stocks with persistent northbound accumulation earn excess returns over 20 days.'],
      steps: [{ k: 'I', ok: false, note: ['字段 hk_hold_ratio 不在当前数据视图 → 已提交数据请求 DR-12', 'Field hk_hold_ratio is not in the current data view → data request DR-12 filed'] }] }] },
  { id: 'T4', name: ['盈余公告后漂移（复现）', 'Post-earnings drift (replication)'], kind: 'rep', status: 'done', budget: 4, tokens: 12,
    act: ['复现完成：结果与库内因子一致', 'Replication done: matches the library factor'],
    nodes: [{ id: 'H1', parent: null, by: 'agent', title: ['标准化未预期盈余 SUE', 'Standardised unexpected earnings'], status: 'done',
      hyp: ['公告后股价对未预期盈余反应不足。', 'Prices under-react to earnings surprises after announcements.'],
      steps: [{ k: 'I', ok: true, note: ['按公告日对齐，滞后一日可得', 'Aligned to announcement date, usable one day later'] },
        { k: 'E', n: 1, ic: .031, t: 4.2, K: 1, corr: .93, cw: 'pead', res: 'ok' },
        { k: 'D', txt: ['与库内 PEAD 相关 0.93，复现成功；记为复现，不作为新因子', 'Correlates 0.93 with library PEAD: replication confirmed; recorded as replication, not a new factor'] }] }] },
  { id: 'T5', name: ['分钟级主动买卖不平衡', 'Intraday order-flow imbalance'], kind: 'new', status: 'auth', budget: 10, tokens: 4,
    act: ['等待授权：需要分钟成交数据，超出本课题的日频范围', 'Awaiting authorisation: needs minute trades, outside this topic’s daily scope'],
    nodes: [{ id: 'H1', parent: null, by: 'agent', title: ['尾盘主动买入占比', 'Late-session active-buy share'], status: 'auth',
      hyp: ['尾盘主动买入占比高的股票次日有正收益。', 'Stocks with a high late-session active-buy share rise the next day.'],
      steps: [{ k: 'D', txt: ['需要分钟数据 → 已向研究负责人申请扩展数据范围', 'Needs minute data → asked the research lead to extend the data scope'] }] }] },
  { id: 'T6', name: ['小盘股中的低波动异象', 'Low-volatility anomaly in small caps'], kind: 'new', status: 'aband', budget: 6, tokens: 21,
    act: ['已放弃：三次尝试均未达到校正后门槛', 'Abandoned: no trial met the adjusted bar'],
    nodes: [
      { id: 'H1', parent: null, by: 'agent', title: ['小盘低波动', 'Small-cap low vol'], status: 'fail', hyp: ['小盘股中低波动股票长期跑赢。', 'Low-vol small caps outperform.'],
        steps: [{ k: 'I', ok: true }, { k: 'E', n: 1, ic: .012, t: 1.4, K: 1, corr: .74, cw: 'lowvol', res: 'fail' }, { k: 'D', txt: ['加入流动性过滤 → H2', 'Add a liquidity filter → H2'] }] },
      { id: 'H2', parent: 'H1', by: 'agent', title: ['加流动性过滤', 'With liquidity filter'], status: 'fail', hyp: ['排除流动性最差的 20% 后异象更明显。', 'Clearer after dropping the least liquid 20%.'],
        steps: [{ k: 'I', ok: true }, { k: 'E', n: 2, ic: .015, t: 1.8, K: 2, corr: .72, cw: 'lowvol', res: 'fail' }, { k: 'D', txt: ['改用残差波动 → H3', 'Switch to idiosyncratic volatility → H3'] }] },
      { id: 'H3', parent: 'H2', by: 'agent', title: ['残差波动', 'Idiosyncratic volatility'], status: 'aband', hyp: ['残差波动比总波动更能刻画异象。', 'Idiosyncratic vol captures it better than total vol.'],
        steps: [{ k: 'I', ok: true }, { k: 'E', n: 3, ic: .017, t: 2.0, K: 3, corr: .71, cw: 'lowvol', res: 'fail' },
          { k: 'X', txt: ['三次均未达到校正后门槛，且与库内低波动相关 0.71 → 放弃课题', 'None met the adjusted bar and it correlates 0.71 with library low-vol → topic abandoned'] }] }
    ] }
];

const CANDS = [
  { id: 'C1', topic: 'T1', node: 'H2a', by: 'agent', status: 'pending', time: '11-05 10:42',
    ai: [['机制与结果一致：拥挤越高回补越强，Q1→Q5 单调。', 'Mechanism matches results: stronger reversal with more crowding, Q1→Q5 monotonic.'],
      ['风险：5 日调仓换手较高，成本约吃掉三分之一多空收益；容量未评估。', 'Risk: 5-day rebalancing is turnover-heavy; costs eat about a third of long-short return; capacity not assessed.'],
      ['与 5 日反转相关 0.62，属于条件化的反转，增量信息需在组合中确认。', 'Correlates 0.62 with 5-day reversal — a conditional reversal; incremental value should be confirmed in portfolios.'],
      ['建议：研究用途入库，观察 3 个月衰减。', 'Suggest: admit for research use, watch decay for 3 months.']],
    limits: [['研发 2019–2024，封存 2025 单年；未覆盖极端行情。', 'Dev 2019–2024, sealed 2025 only; no extreme regimes covered.'], ['成本按双边 0.2% 估计，未计冲击成本。', 'Costs assumed 0.2% round-trip, no impact cost.']] }
];
const CAND_T2 = { id: 'C2', topic: 'T2', node: 'H2a', by: 'agent', status: 'pending', time: '',
  ai: [['机制清楚：预期上调后的滞后反应，衰减慢，换手低。', 'Clear mechanism: lagged response to upgrades; slow decay, low turnover.'],
    ['已对“一致预期调整动量”正交化，残差相关 0.33。', 'Orthogonalised to "Consensus revision momentum"; residual correlation 0.33.'],
    ['风险：分析师覆盖≥3 家限制了股票池，小盘覆盖不足。', 'Risk: ≥3 analysts narrows the universe; small caps under-covered.'],
    ['建议：研究用途入库，并在策略中检验与原动量因子的组合增益。', 'Suggest: admit for research use and test combined gain with the momentum factor in strategies.']],
  limits: [['预期数据源单一，发布时间戳按日对齐。', 'Single consensus source; release timestamps aligned daily.']] };

const LIB = [
  { n: ['5日反转', '5-day reversal'], src: 'builtin', cat: ['量价', 'Price-volume'], ic: .031, t: 4.8, to: .44, tr: 'ok', st: 'use' },
  { n: ['换手率异动', 'Abnormal turnover'], src: 'builtin', cat: ['量价', 'Price-volume'], ic: .028, t: 4.1, to: .35, tr: 'ok', st: 'use' },
  { n: ['一致预期调整动量', 'Consensus revision momentum'], src: 'human', cat: ['预期', 'Expectations'], ic: .024, t: 3.6, to: .12, tr: 'ok', st: 'use' },
  { n: ['盈余公告漂移 PEAD', 'Post-earnings drift (PEAD)'], src: 'builtin', cat: ['基本面', 'Fundamental'], ic: .022, t: 3.3, to: .08, tr: 'ok', st: 'use' },
  { n: ['低波动', 'Low volatility'], src: 'builtin', cat: ['风险', 'Risk'], ic: .019, t: 2.7, to: .15, tr: 'weak', st: 'watch' },
  { n: ['账面市值比', 'Book-to-market'], src: 'builtin', cat: ['价值', 'Value'], ic: .015, t: 1.9, to: .03, tr: 'weak', st: 'watch' },
  { n: ['20日动量', '20-day momentum'], src: 'builtin', cat: ['量价', 'Price-volume'], ic: .006, t: .9, to: .21, tr: 'weak', st: 'watch' },
  { n: ['小市值', 'Small size'], src: 'builtin', cat: ['风险', 'Risk'], ic: .020, t: 2.1, to: .02, tr: 'off', st: 'off' }
];

const CAPS = [
  { f: 'F0', n: ['研究决策', 'Research decision'], m: 'agent', tools: ['选择下一步、修订/分支/放弃、申请验证、停止', 'Choose next step, revise/branch/drop, request validation, stop'], ev: ['30 个历史课题回放：下一步与专家一致率 / 无效试验占比', '30 replayed topics: next-step agreement / wasted-trial share'], s: '0.69 / 22%', b: '—', v: 'v2' },
  { f: 'F1', n: ['起点检索', 'Starting-point search'], m: 'unit', tools: ['因子库检索、历史试验、数据目录', 'Library search, past trials, data catalogue'], ev: ['80 例：相似因子召回率', '80 cases: similar-factor recall'], s: '0.86', b: '0.78', v: 'v3' },
  { f: 'F2', n: ['假设研究', 'Hypothesis research'], m: 'sub', tools: ['文献检索、机制模板、可证伪检查；可并行提出多个假设', 'Literature search, mechanism templates, falsifiability check; can propose several in parallel'], ev: ['120 例：专家评为“可证伪且不重复”的比例', '120 cases: share rated falsifiable and non-duplicate by experts'], s: '0.72', b: '0.61', v: 'v5' },
  { f: 'F3', n: ['因子实现', 'Factor implementation'], m: 'sub', tools: ['表达式编译、未来函数检查、受限执行；自行“编译-报错-修改”', 'Compiler, look-ahead check, sandboxed run; runs its own compile-fix loop'], ev: ['150 例：一次编译通过率 / 未来函数检出率', '150 cases: first-pass compile rate / look-ahead detection'], s: '0.93 / 1.00', b: '0.88 / 0.97', v: 'v4' },
  { f: 'F4', n: ['检验诊断', 'Testing & diagnosis'], m: 'unit', tools: ['因子计算、IC/分层/衰减、查重；解读结果', 'Factor compute, IC/quantiles/decay, dedup; interprets results'], ev: ['90 例：失败原因判断与专家一致率', '90 cases: agreement with experts on failure causes'], s: '0.77', b: '0.70', v: 'v2' },
  { f: 'F5', n: ['独立复核', 'Independent review'], m: 'indep', tools: ['封存样本、完整性检查；不共享研究上下文', 'Sealed sample, integrity checks; no shared research context'], ev: ['60 例：识别植入问题（泄漏、过拟合、口径错误）', '60 cases: catches planted issues (leakage, overfitting, definition errors)'], s: '0.88', b: '—', v: 'v1' },
  { f: 'F6', n: ['因子卡与入库', 'Factor card & admission'], m: 'unit', tools: ['因子卡模板、衰减跟踪；入库由人决定', 'Card template, decay tracking; admission decided by people'], ev: ['40 例：证据包完整率', '40 cases: evidence-pack completeness'], s: '0.95', b: '0.90', v: 'v2' }
];
const FORM = { agent: ['Agent · 决策', 'Agent · decides', 'purple'], sub: ['子 Agent · 自有循环', 'Sub-agent · own loop', 'blue'], unit: ['能力单元 · 单次调用', 'Unit · single call', 'gray'], indep: ['独立 Agent', 'Independent Agent', 'amber'] };
const formBadge = m => { const x = FORM[m]; return `<span class="badge ${x[2]}">${tx(x)}</span>`; };

/* ---------- state ---------- */
const S = {
  page: 'ops', role: 'researcher', notes: false, demoOpen: false,
  sel: 'T2', node: null, follow: true, unit: null, sysOn: true,
  sim: { on: true, i: 0 }, wb: { topic: 'T1', branch: 'H2c', tool: 'start', busy: false, checks: null, chat: null },
  rv: { sel: 'C1', ack: false }, lib: 'all', events: []
};
const topic = id => TOPICS.find(x => x.id === id);
const nodeOf = (tp, id) => tp.nodes.find(x => x.id === id);
const trials = tp => tp.nodes.reduce((a, n) => a + n.steps.filter(s => s.k === 'E').length, 0);
const holds = tp => tp.nodes.reduce((a, n) => a + n.steps.filter(s => s.k === 'V').length, 0);
const allE = tp => tp.nodes.flatMap(n => n.steps.filter(s => s.k === 'E').map(s => ({ s, n }))).sort((a, b) => a.s.n - b.s.n);
const lastE = n => [...n.steps].reverse().find(s => s.k === 'E');
const lastV = n => [...n.steps].reverse().find(s => s.k === 'V');
const gateOk = (s, K) => s.ic >= GATE.ic && s.t >= needT(K || s.K) && s.corr < GATE.corr;

function ev(tp, txt, kind) { S.events.unshift({ time: clock(), tp, txt, kind: kind || '', fresh: true }); if (S.events.length > 40) S.events.pop(); }
[['T1', ['候选 C1 提交审查', 'Candidate C1 submitted for review']], ['T6', ['课题放弃：三次试验均未达到校正门槛', 'Topic abandoned: three trials below adjusted bar']],
 ['T5', ['申请扩展数据范围：分钟成交', 'Requested data-scope extension: minute trades']], ['T3', ['数据请求 DR-12 已提交到数据资源', 'Data request DR-12 sent to Data Resources']],
 ['T1', ['张新迪 接手 H2 分支，新建 H2c', 'Zhang Xindi took over from H2, created H2c']], ['T4', ['复现完成：与库内 PEAD 相关 0.93', 'Replication complete: 0.93 with library PEAD']]]
  .forEach(([tp, txt], i) => S.events.push({ time: ['10:58:12', '10:41:05', '10:22:47', '09:56:30', '09:31:18', '09:12:02'][i], tp, txt }));

/* ---------- labels ---------- */
const ST = {
  run: ['运行中', 'Running', 'live'], review: ['待复核', 'In review', 'purple'], wait: ['等待数据', 'Waiting for data', 'amber'], auth: ['等待授权', 'Needs approval', 'amber'],
  done: ['已完成', 'Done', 'green'], aband: ['已放弃', 'Abandoned', 'gray'], approved: ['已入库', 'Admitted', 'green'], paused: ['已暂停', 'Paused', 'gray'], queued: ['排队中', 'Queued', 'blue']
};
const BST = {
  run: ['进行中', 'In progress', 'live'], fail: ['未达标', 'Below bar', 'red'], branched: ['已分支', 'Branched', 'gray'], review: ['待复核', 'In review', 'purple'], aband: ['已放弃', 'Abandoned', 'gray'],
  human: ['人工进行中', 'Human, in progress', 'blue'], returned: ['已交回 Agent', 'Returned to Agent', 'gray'], wait: ['等待数据', 'Waiting for data', 'amber'], auth: ['等待授权', 'Needs approval', 'amber'],
  done: ['已完成', 'Done', 'green'], approved: ['已入库', 'Admitted', 'green'], submitted: ['已提交审查', 'Submitted', 'purple'], archived: ['已归档', 'Archived', 'gray']
};
const badge = (m, k) => { const x = m[k] || [k, k, 'gray']; return `<span class="badge ${x[2]}">${tx(x)}</span>`; };
const ROLE = { researcher: ['因子研究员', 'Factor researcher', '研', 'F'], reviewer: ['因子复核人', 'Factor reviewer', '复', 'R'], lead: ['研究负责人', 'Research lead', '负', 'L'] };
const canReview = () => S.role !== 'researcher';
const isLead = () => S.role === 'lead';

/* ---------- shell ---------- */
function sidebar() {
  const pend = CANDS.filter(c => c.status === 'pending').length;
  const it = (ico, z, e, href, sel, cnt) => `<a class="nav-item${sel ? ' selected' : ''}" href="${href}"${sel ? ' aria-current="page"' : ''}><span>${ico}</span>${t(z, e)}${cnt ? `<i class="count">${cnt}</i>` : ''}</a>`;
  return `<a class="brand" href="../prototype.html#overview"><span class="seal">旸</span><span><strong>${t('旸谷资本', 'Sunvalley')}</strong><small>SUNVALLEY CAPITAL</small></span></a>
  <div class="workspace"><b>${t('SVQuant · 机构量化平台', 'SVQuant · Institutional Quant')}</b><span>${t('研究与运行工作区', 'Research & operations')}</span></div>
  <nav><div class="nav-label">${t('工作空间', 'WORKSPACE')}</div>${it('◫', '管理驾驶舱', 'Cockpit', '../prototype.html#overview')}
  <div class="nav-label">${t('业务模块', 'MODULES')}</div>${it('▤', '数据资源', 'Data', '../prototype.html#data')}${it('ƒ', '因子工厂', 'Factor factory', '#', true)}${it('⌁', '策略研究', 'Strategy', '../prototype.html#strategy')}${it('◈', '组合与执行', 'Portfolio', '../prototype.html#portfolio')}${it('◎', '运行与风险', 'Risk', '../prototype.html#monitor')}
  <div class="nav-label">${t('协作与管理', 'COLLABORATION')}</div>${it('▣', '审查中心', 'Review centre', '../prototype.html#review', false, pend)}${it('✧', 'Agent 管理', 'Agents', '../prototype.html#agents')}</nav>
  <footer><span>${t('设计预览 V5', 'Design preview V5')}</span></footer>`;
}
function topbar() {
  const r = ROLE[S.role];
  return `<span class="crumb">${t('机构工作区', 'Workspace')} <i>/</i> ${t('因子工厂', 'Factor factory')}</span>
  <div class="identity"><span class="lang"><button class="${L === 'zh' ? 'on' : ''}" data-a="lang" data-v="zh">中</button><button class="${L === 'en' ? 'on' : ''}" data-a="lang" data-v="en">EN</button></span>
  <span class="avatar">${L === 'en' ? r[3] : r[2]}</span><span>${tx(r)}</span></div>`;
}
function demo() {
  if (!S.demoOpen) return `<button class="demo-fab" data-a="demo">${t('演示控制', 'Demo controls')}</button>`;
  const seg = (k, opts) => `<div class="seg">${opts.map(([v, z, e]) => `<button class="${S[k] === v ? 'on' : ''}" data-a="set" data-k="${k}" data-v="${v}">${t(z, e)}</button>`).join('')}</div>`;
  return `<div class="demo-panel"><h4>${t('演示控制（不属于产品界面）', 'Demo controls (not part of the product)')}<button class="text-btn" data-a="demo">${t('收起', 'Hide')}</button></h4>
  <div class="grp"><span>${t('身份', 'Identity')}</span>${seg('role', [['researcher', '研究员', 'Researcher'], ['reviewer', '复核人', 'Reviewer'], ['lead', '负责人', 'Lead']])}</div>
  <div class="grp"><span>${t('研究系统模拟', 'Research simulation')}</span><div class="row"><button class="btn small" data-a="simtoggle">${S.sim.on ? t('⏸ 暂停模拟', '⏸ Pause') : t('▶ 继续模拟', '▶ Resume')}</button><button class="btn small" data-a="simstep" ${S.sim.i >= SIM.length ? 'disabled' : ''}>${t('推进一步', 'Step')}</button><button class="btn small" data-a="reset">${t('重置', 'Reset')}</button></div></div>
  <div class="grp"><span>${t('设计说明', 'Design notes')}</span>${seg('notes', [[false, '隐藏', 'Hide'], [true, '显示', 'Show']])}</div></div>`;
}
const NOTES = {
  ops: ['<b>设计要点</b>：因子研究由一个持续运行的研究系统完成，页面不驱动研究。人通过“课题 + 授权 + 预算”设定方向，随时观察、给意见、接手任意分支。研究树记录每一次修订、换方向和放弃；所有检验进入课题的试验台账，显著性门槛随试验次数提高（多重检验校正），封存样本每个候选只用一次。',
    '<b>Design</b>: factor research is done by a continuously running research system; pages do not drive it. People steer through topic + authorisation + budget, watch, comment and take over any branch. The tree records every revision, pivot and abandonment; every test enters the topic ledger and the significance bar rises with the number of trials; the sealed sample is used once per candidate.'],
  wb: ['<b>设计要点</b>：人工研究和 Agent 用同一套工具、同一个试验台账。人可以从任意分支接手，也可以交回 Agent；助手调用的也是这些工具。人工检验同样提高课题的显著性门槛，避免“人工多试几次”绕过校正。',
    '<b>Design</b>: human research uses the same tools and the same trial ledger as the Agent. People can take over any branch and hand it back; the assistant calls the same tools. Human tests also raise the topic bar, so retrying by hand cannot bypass the correction.'],
  review: ['<b>设计要点</b>：人只审查通过门槛的候选，但能看到全部试验（包括失败和放弃的），不只看赢家。门槛按课题当前试验总数校正；独立复核 Agent 不共享研究上下文，只给建议，不批准。',
    '<b>Design</b>: people review only candidates that pass the gates, but see every trial including failures — not just the winner. The bar is adjusted for the topic’s current trial count; the independent reviewer Agent shares no research context and only advises.'],
  lib: ['<b>设计要点</b>：因子库每个因子都有统一口径的指标和近期表现，来源区分平台内置、人工和 Agent；入库只授予研究用途，策略和实盘准入另行决定。',
    '<b>Design</b>: every library factor carries metrics on a common definition and recent behaviour; sources are marked built-in, human or Agent. Admission grants research use only; strategy and live use are separate decisions.'],
  caps: ['<b>设计要点</b>：业务流程的每个 AI 功能点都落成一个专职单元，有自己的提示词与工具版本、评测集和得分，可以单独改进，即“拆细、针对性优化”。在此之上补了功能点 F0“研究决策”：根据结果决定下一步、回退、分支或放弃，每个课题一个实例。各单元是独立 Agent、子 Agent 还是一次调用，由评测决定；编排方式用对照实验比较，让效果说话。',
    '<b>Design</b>: every AI point in the business flow becomes a specialist unit with its own prompt/tool versions, eval set and score, optimised independently. On top we add F0 “research decision”: it decides the next step, backtracking, branching or dropping; one instance per topic. Whether a unit is an Agent, sub-agent or single call is set by evals; orchestration options are compared by experiment.']
};
const note = k => S.notes ? `<div class="design-note">${tx(NOTES[k])}</div>` : '';

function render() {
  document.documentElement.lang = L === 'en' ? 'en' : 'zh-CN';
  document.title = t('因子工厂 · 研究系统', 'Factor factory · Research system');
  $('#sidebar').innerHTML = sidebar(); $('#topbar').innerHTML = topbar(); $('#demo').innerHTML = demo();
  const pend = CANDS.filter(c => c.status === 'pending').length;
  const tabs = [['ops', '研究运行', 'Research operations'], ['wb', '人工研究', 'My research'], ['review', '审查', 'Review', pend], ['lib', '因子库', 'Library'], ['caps', '能力与评测', 'Capabilities & evals']];
  const body = { ops: pageOps, wb: pageWB, review: pageReview, lib: pageLib, caps: pageCaps }[S.page]();
  $('#main').innerHTML = `<div class="page-head"><div><span class="eyebrow">FACTOR FACTORY</span><h1>${t('因子工厂', 'Factor factory')}</h1><p>${t('研究系统持续挖掘因子；你可以随时观察、介入，或亲自研究。', 'The research system mines factors continuously; you can watch, step in, or research yourself.')}</p></div>
  <div class="actions"><button class="btn" data-a="auth">${t('研究授权', 'Authorisation')}</button><button class="btn primary" data-a="newtopic">＋ ${t('新建课题', 'New topic')}</button></div></div>
  <div class="preview-bar"><span>${t('交互原型 · 场景数据：不调用模型、计算服务或真实审批，所有数值为演示。', 'Interactive prototype · scenario data: no models, compute or real approvals; all numbers are illustrative.')}</span></div>
  <nav class="tabs">${tabs.map(([k, z, e, c]) => `<button class="${S.page === k ? 'active' : ''}" data-a="page" data-v="${k}">${t(z, e)}${c ? `<span class="count">${c}</span>` : ''}</button>`).join('')}</nav>${body}`;
  S.events.forEach(e => e.fresh = false);
  const ch = $('#chat'); if (ch) ch.scrollTop = ch.scrollHeight;
}

/* ---------- research operations ---------- */
function sysStrip() {
  const n = s => TOPICS.filter(x => x.status === s).length;
  const tr = TOPICS.reduce((a, x) => a + trials(x), 0), hv = TOPICS.reduce((a, x) => a + holds(x), 0), tk = TOPICS.reduce((a, x) => a + x.tokens, 0);
  return `<div class="sys"><div class="sys-state"><span class="ico">✧</span><div><b><span class="live-dot ${S.sysOn ? '' : 'off'}"></span> ${S.sysOn ? t('因子研究系统运行中', 'Factor research system running') : t('因子研究系统已暂停', 'Factor research system paused')}</b><small>${t('授权至 2026-11-30 · 研究负责人 批准', 'Authorised to 2026-11-30 by the research lead')}</small></div></div>
  <div class="kpis"><div class="kpi"><span>${t('课题', 'Topics')}</span><b>${TOPICS.length}</b><small>${t(`运行 ${n('run')} · 待复核 ${n('review')} · 等待 ${n('wait') + n('auth')}`, `${n('run')} running · ${n('review')} in review · ${n('wait') + n('auth')} waiting`)}</small></div>
  <div class="kpi"><span>${t('本月试验台账', 'Trials this month')}</span><b>${tr}</b><small>/ 120</small></div>
  <div class="kpi"><span>${t('封存样本已用', 'Sealed-sample uses')}</span><b>${hv}</b><small>${t('次', '')}</small></div>
  <div class="kpi"><span>${t('待人决定', 'Awaiting people')}</span><b>${CANDS.filter(c => c.status === 'pending').length + n('auth')}</b><small>${t('项', 'items')}</small></div>
  <div class="kpi"><span>Token</span><b>${tk}k</b><small>/ 1,000k</small></div></div>
  <div class="actions"><button class="btn small" data-a="sys">${S.sysOn ? t('暂停全部', 'Pause all') : t('恢复运行', 'Resume')}</button></div></div>`;
}
function topicCard(tp) {
  const K = trials(tp), best = allE(tp).reduce((m, x) => x.s.t > (m ? m.t : -1) ? x.s : m, null);
  const live = tp.status === 'run';
  return `<button class="topic${S.sel === tp.id ? ' sel' : ''}" data-a="topic" data-v="${tp.id}">
  <div class="top"><span class="tid">${tp.id} · ${tp.kind === 'rep' ? t('复现', 'Replication') : t('新发现', 'Discovery')}</span>${badge(ST, tp.status)}</div>
  <h3>${tx(tp.name)}</h3><div class="act">${live ? '<span class="live-dot"></span> ' : ''}${tx(tp.act)}</div>
  <div class="bar"><i style="width:${Math.min(100, K / tp.budget * 100)}%"></i></div>
  <div class="meta"><span>${t('试验', 'Trials')} <b>${K}/${tp.budget}</b></span><span>${t('分支', 'Branches')} <b>${tp.nodes.length}</b></span>${best ? `<span>${t('最佳', 'Best')} t <b>${best.t.toFixed(1)}</b> / ${t('需', 'bar')} ${needT(Math.max(K, 1)).toFixed(2)}</span>` : ''}</div></button>`;
}
function chip(tp, s) {
  if (s.k === 'I') return `<span class="chip ${s.ok ? 'ok' : 'fail'}" title="${esc(tx(s.note) || '')}">${t('实现', 'Impl')} ${s.ok ? '✓' : '✗'}</span>`;
  if (s.k === 'E') { const m = s.res === 'ok' ? '✓' : s.res === 'warn' ? '≈' : '✗'; return `<button class="chip ${s.res}" data-a="report" data-v="${tp.id}|${s.n}">E${s.n} · IC ${s.ic.toFixed(3)} · t ${s.t.toFixed(1)} / ${needT(s.K).toFixed(2)} ${m}${s.res === 'warn' ? ` · ${t('相似', 'sim')} ${s.corr.toFixed(2)}` : ''}</button>`; }
  if (s.k === 'V') return `<span class="chip ${s.res}">${t('封存验证', 'Sealed')} · IC ${s.ic.toFixed(3)} · t ${s.t.toFixed(1)} ${s.res === 'ok' ? '✓' : '✗'}</span>`;
  if (s.k === 'R') return `<span class="chip run">${tx(s.txt)}…</span>`;
  return `<span class="chip dec">${s.k === 'X' ? t('放弃：', 'Abandon: ') : ''}${tx(s.txt)}</span>`;
}
function branch(tp, n) {
  const kids = tp.nodes.filter(x => x.parent === n.id);
  const by = n.by === 'human' ? `${t('人工', 'Human')} · ${tx(n.who)}` : 'Agent';
  return `<div class="branch-wrap"><div class="branch${n.by === 'human' ? ' human' : ''}${['aband', 'returned', 'archived'].includes(n.status) ? ' aband' : ''}${S.node === n.id ? ' sel' : ''}" data-a="node" data-v="${n.id}">
  <div class="bh"><span class="hid">${n.id}</span><span class="bt">${tx(n.title)}</span>${badge(BST, n.status)}<span class="by">${by}</span></div>
  ${n.steps.length ? `<div class="steps">${n.steps.map(s => chip(tp, s)).join('<span class="arrow">›</span>')}</div>` : ''}</div>
  ${kids.length ? `<div class="children">${kids.map(k => branch(tp, k)).join('')}</div>` : ''}</div>`;
}
function topicActions(tp) {
  const b = [];
  if (tp.status === 'run') b.push(`<button class="btn small" data-a="pausetopic">${t('暂停课题', 'Pause topic')}</button>`);
  if (tp.status === 'paused') b.push(`<button class="btn small" data-a="pausetopic">${t('继续课题', 'Resume topic')}</button>`);
  if (tp.status === 'auth') b.push(isLead() ? `<button class="btn small primary" data-a="grant" data-v="yes">${t('批准扩展（另建计划）', 'Approve (new plan)')}</button><button class="btn small" data-a="grant" data-v="no">${t('拒绝，按原范围继续', 'Decline, keep scope')}</button>` : `<span class="subtle">${t('需研究负责人批准', 'Needs the research lead')}</span>`);
  if (tp.status === 'wait') b.push(`<button class="btn small" data-a="toast" data-v="dr">${t('查看数据请求 DR-12', 'View data request DR-12')}</button>`);
  if (tp.status === 'review') b.push(`<button class="btn small primary" data-a="page" data-v="review">${t('去审查', 'Go to review')}</button>`);
  if (!['done', 'aband', 'approved'].includes(tp.status)) b.push(`<button class="btn small ghost" data-a="comment">${t('给研究意见', 'Comment')}</button>`);
  return b.join('');
}
function nodeCard(tp, n) {
  if (!n) return `<div class="card"><div class="empty"><b>${t('选择一个分支查看详情', 'Select a branch to see details')}</b>${t('每个分支是一版假设；可以从任意分支接手。', 'Each branch is one hypothesis version; you can take over any branch.')}</div></div>`;
  const parent = n.parent ? nodeOf(tp, n.parent) : null;
  const rows = n.steps.map(s => {
    if (s.k === 'E') { const pass = gateOk(s); return `<div class="trial-row"><span class="tk">E${s.n}</span><div class="tb"><b>${t('研发检验', 'Development test')}</b> · Rank IC ${s.ic.toFixed(3)} · t ${s.t.toFixed(2)} ${t('需', 'bar')} ${needT(s.K).toFixed(2)}<small>${t(`课题第 ${s.K} 次试验 · 与 ${tx(LIBNAME[s.cw])} 相关 ${s.corr.toFixed(2)}`, `Trial ${s.K} of topic · ${s.corr.toFixed(2)} corr with ${tx(LIBNAME[s.cw])}`)} · <span class="${pass ? 'ok-t' : s.res === 'warn' ? 'warn-t' : 'bad-t'}">${pass ? t('达标', 'passed') : s.res === 'warn' ? t('显著但重复', 'significant but duplicate') : t('未达标', 'below bar')}</span></small></div><button class="text-btn" data-a="report" data-v="${tp.id}|${s.n}">${t('报告', 'Report')}</button></div>`; }
    if (s.k === 'V') return `<div class="trial-row"><span class="tk">V</span><div class="tb"><b>${t('封存验证（独立复核 Agent）', 'Sealed validation (independent reviewer)')}</b> · Rank IC ${s.ic.toFixed(3)} · t ${s.t.toFixed(2)} ${t('需', 'bar')} 1.96<small>${t('2025 全年，仅此一次', 'Full year 2025, used once')}</small></div></div>`;
    if (s.k === 'I') return `<div class="trial-row"><span class="tk">I</span><div class="tb"><b>${t('实现与校验', 'Implementation & checks')}</b> ${s.ok ? '<span class="ok-t">✓</span>' : '<span class="bad-t">✗</span>'}<small>${tx(s.note) || t('语法、字段、未来函数检查通过', 'Syntax, fields and look-ahead checks passed')}</small></div></div>`;
    if (s.k === 'R') return `<div class="trial-row"><span class="tk">…</span><div class="tb">${tx(s.txt)}</div></div>`;
    return `<div class="trial-row"><span class="tk">${s.k === 'X' ? '✕' : '→'}</span><div class="tb"><b>${s.k === 'X' ? t('放弃', 'Abandoned') : t('决定', 'Decision')}</b><small>${tx(s.txt)}</small></div></div>`;
  }).join('');
  const canTake = !['returned', 'archived'].includes(n.status);
  return `<div class="card"><div class="card-head"><div><div class="row-flex"><span class="hid" style="font:600 11px ui-monospace,monospace;color:var(--primary)">${n.id}</span><h2>${tx(n.title)}</h2>${badge(BST, n.status)}</div>
  <p>${n.by === 'human' ? `${t('人工分支', 'Human branch')} · ${tx(n.who)}` : t('Agent 分支', 'Agent branch')}${parent ? ` · ${t('来自', 'from')} ${parent.id}` : ''}</p></div>
  <div class="actions">${canTake ? `<button class="btn small primary" data-a="takeover" data-v="${n.id}">${n.by === 'human' ? t('打开工作台', 'Open workbench') : t('从此分支接手', 'Take over here')}</button>` : ''}</div></div>
  <div class="card-body"><div class="kv"><span>${t('假设', 'Hypothesis')}</span><div>${tx(n.hyp)}</div></div><h3 style="margin:16px 0 4px">${t('试验与决定', 'Trials & decisions')}</h3>${rows || `<p class="subtle">${t('尚无记录', 'No records yet')}</p>`}</div></div>`;
}
function unitsCard() {
  const u = S.unit, live = TOPICS.filter(x => x.status === 'run').map(x => x.id);
  const row = (id, ico, cls, z, e, m, sz, se) => `<div class="unit ${cls}${u && u.u === id ? ' on' : ''}"><span class="ui">${ico}</span><div style="flex:1"><b>${t(z, e)}</b><small>${u && u.u === id ? `${u.tp} · ${t('工作中', 'working')}` : t(sz, se)}</small></div>${m ? formBadge(m) : ''}</div>`;
  return `<div class="card"><div class="card-head"><div><h2>${t('研究系统', 'Research system')}</h2><p>${t('每个课题一个研究决策 Agent，调用专职 Agent 与能力单元', 'One decision Agent per topic, calling specialist agents and units')}</p></div><button class="text-btn" data-a="page" data-v="caps">${t('能力与评测', 'Evals')} ›</button></div><div class="card-body"><div class="units">
  ${row('sched', '⇅', '', '课题调度', 'Topic scheduler', '', '规则：排队、跨课题预算', 'rules: queue, cross-topic budget')}
  ${row('coord', 'F0', 'agent', '研究决策', 'Research decision', 'agent', live.length ? `运行实例：${live.join('、')}` : '暂无运行实例', live.length ? `instances: ${live.join(', ')}` : 'no running instance')}
  ${row('F1', 'F1', '', '起点检索', 'Starting point', 'unit', '因子库 · 历史试验', 'library · past trials')}
  ${row('F2', 'F2', 'agent', '假设研究', 'Hypothesis', 'sub', '机制 · 可证伪条件', 'mechanism · falsifiability')}
  ${row('F3', 'F3', 'agent', '因子实现', 'Implementation', 'sub', '编译 · 未来函数检查', 'compile · look-ahead')}
  ${row('F4', 'F4', '', '检验诊断', 'Test & diagnose', 'unit', 'IC · 分层 · 衰减 · 查重', 'IC · quantiles · decay · dedup')}
  ${row('F5', 'F5', 'indep', '独立复核', 'Independent review', 'indep', '不共享研究上下文', 'no shared research context')}
  </div><div class="svc">${[['数据视图', 'Data view'], ['因子计算', 'Factor compute'], ['封存样本', 'Sealed sample'], ['试验台账', 'Trial ledger'], ['因子库查重', 'Library dedup']].map(x => `<span>${tx(x)}</span>`).join('')}</div></div></div>`;
}
function feedCard() {
  return `<div class="card"><div class="card-head"><h2>${t('实时动态', 'Live activity')}</h2><span class="live-dot ${S.sysOn && S.sim.on ? '' : 'off'}"></span></div><div class="card-body" style="padding-top:6px;padding-bottom:6px"><ul class="feed">
  ${S.events.map(e => `<li class="${e.fresh ? 'new' : ''}"><time>${e.time}</time><span class="tg">${e.tp}</span>${tx(e.txt)}</li>`).join('')}</ul></div></div>`;
}
function pageOps() {
  const tp = topic(S.sel), K = trials(tp);
  if (!S.node || !nodeOf(tp, S.node)) S.node = tp.nodes.length ? (tp.nodes.find(n => ['review', 'human', 'run'].includes(n.status)) || tp.nodes[tp.nodes.length - 1]).id : null;
  const roots = tp.nodes.filter(n => !n.parent);
  return note('ops') + sysStrip() + `<div class="ops-grid"><div><div class="topic-grid">${TOPICS.map(topicCard).join('')}</div>
  <div class="card"><div class="card-head"><div><div class="row-flex"><span class="tid" style="font:10px ui-monospace,monospace;color:#a69caf">${tp.id}</span><h2>${tx(tp.name)}</h2>${badge(ST, tp.status)}</div><p>${tx(SCOPE)}</p></div><div class="actions">${topicActions(tp)}</div></div>
  <div class="card-body"><div class="ledger"><span>${t('试验台账', 'Trial ledger')} <b>${K}</b> / ${tp.budget}</span><span>${t('分支', 'Branches')} <b>${tp.nodes.length}</b></span><span>${t('封存验证', 'Sealed uses')} <b>${holds(tp)}</b></span><span>Token <b>${tp.tokens}k</b></span><span>${t('下一次检验需', 'Next test needs')} t ≥ <b>${needT(K + 1).toFixed(2)}</b></span></div>
  <div class="section-title" style="margin-top:16px"><h3>${t('研究树', 'Research tree')}</h3>${!S.follow && tp.status === 'run' ? `<button class="btn small ghost" data-a="follow">${t('跟随最新进展', 'Follow latest')}</button>` : `<span class="subtle">${t('点击分支查看详情；点击检验查看报告', 'Click a branch for details, a test for its report')}</span>`}</div>
  ${roots.length ? `<div class="tree">${roots.map(r => branch(tp, r)).join('')}</div>` : `<div class="empty"><b>${t('研究决策正在规划', 'The decision Agent is planning')}</b>${tx(tp.act)}</div>`}</div></div>
  ${nodeCard(tp, S.node && nodeOf(tp, S.node))}</div><div class="side">${unitsCard()}${feedCard()}</div></div>`;
}

/* ---------- metrics & charts ---------- */
function metricsOf(s, v) {
  const r = rng(Math.round(s.ic * 1e5) + Math.round(s.t * 100));
  const N = 1455, tn = s.t * 1.15, icirA = tn / Math.sqrt(N) * Math.sqrt(242);
  const slow = s.slow ? 1 : 0;
  const decay = [1, 5, 10, 20].map((h, i) => s.ic * (slow ? [1, .95, .86, .71][i] : [1, .79, .54, .33][i]));
  const q = [-1, -.3, .1, .45, 1].map((w, i) => +(w * s.ic * 190 + (r() - .5) * .6).toFixed(1));
  const to = s.to != null ? s.to : (slow ? .09 : .18);
  const ls = Math.max(-2, s.ic * 420 - to * 242 * 0.002 * 100 * 0.45);
  return { icir: icirA, pos: 50 + s.t * 2.1, decay, q, to, ls, cov: s.cov || .96, v };
}
function lineSVG(s, v) {
  const r = rng(Math.round(s.ic * 1e5) + 7), M = 72, H = v ? 12 : 0;
  const sd = s.ic * Math.sqrt(M) / Math.max(.3, s.t);
  let c = 0; const pts = [0];
  for (let i = 0; i < M; i++) { c += s.ic + sd * gauss(r) * .9; pts.push(c); }
  for (let i = 0; i < H; i++) { c += v.ic + (v.ic * Math.sqrt(H) / Math.max(.3, v.t)) * gauss(r) * .9; pts.push(c); }
  const mx = Math.max(...pts, .001), mn = Math.min(...pts, 0), W = 300, Hh = 140;
  const X = i => 6 + i / (M + H) * (W - 12), Y = y => 8 + (mx - y) / (mx - mn || 1) * (Hh - 16);
  const dev = pts.slice(0, M + 1).map((y, i) => `${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join(' ');
  const hold = H ? pts.slice(M).map((y, i) => `${X(M + i).toFixed(1)},${Y(y).toFixed(1)}`).join(' ') : '';
  return `<svg viewBox="0 0 300 150" preserveAspectRatio="none"><line x1="6" x2="294" y1="${Y(0)}" y2="${Y(0)}" stroke="#e4dfe9"/>
  ${H ? `<rect x="${X(M)}" y="4" width="${X(M + H) - X(M)}" height="136" fill="#eef3fb"/><text x="${X(M) + 3}" y="14" font-size="8" fill="#3b5f9e">${t('封存', 'Sealed')}</text>` : ''}
  <polyline points="${dev}" fill="none" stroke="#76489a" stroke-width="1.6"/>${H ? `<polyline points="${hold}" fill="none" stroke="#3b5f9e" stroke-width="1.8"/>` : ''}
  <text x="6" y="148" font-size="8" fill="#a39aad">2019</text><text x="${H ? X(M) - 10 : 276}" y="148" font-size="8" fill="#a39aad">${H ? '2025' : '2024'}</text></svg>`;
}
function barSVG(vals, labels, fmt) {
  const W = 300, H = 140, mx = Math.max(...vals.map(Math.abs), 1e-9), n = vals.length, bw = (W - 20) / n * .6, zero = vals.some(x => x < 0) ? H / 2 : H - 16;
  const sc = (vals.some(x => x < 0) ? H / 2 - 18 : H - 30) / mx;
  return `<svg viewBox="0 0 300 150"><line x1="8" x2="292" y1="${zero}" y2="${zero}" stroke="#e4dfe9"/>${vals.map((v, i) => {
    const x = 10 + (W - 20) / n * i + (W - 20) / n * .2, h = Math.abs(v) * sc, y = v >= 0 ? zero - h : zero;
    return `<rect x="${x}" y="${y}" width="${bw}" height="${Math.max(1, h)}" rx="2" fill="${v >= 0 ? '#a585c2' : '#d9a5b2'}"/><text x="${x + bw / 2}" y="${v >= 0 ? y - 3 : y + h + 9}" font-size="8" text-anchor="middle" fill="#6d6378">${fmt(v)}</text><text x="${x + bw / 2}" y="148" font-size="8" text-anchor="middle" fill="#a39aad">${labels[i]}</text>`;
  }).join('')}</svg>`;
}
function reportBody(s, v, K) {
  const m = metricsOf(s, v), need = needT(K || s.K);
  return `<div class="metrics"><div class="stat"><span>Rank IC</span><b>${s.ic.toFixed(3)}</b><small>${t('门槛', 'bar')} ≥ ${GATE.ic}</small></div>
  <div class="stat"><span>${t('t 值（NW 调整）', 't-stat (Newey-West)')}</span><b class="${s.t >= need ? 'ok-t' : 'bad-t'}">${s.t.toFixed(2)}</b><small>${t(`需 ≥ ${need.toFixed(2)}（${K || s.K} 次试验校正）`, `needs ≥ ${need.toFixed(2)} (${K || s.K} trials)`)}</small></div>
  <div class="stat"><span>${t('ICIR（年化）', 'ICIR (annualised)')}</span><b>${m.icir.toFixed(2)}</b><small>${t('IC 为正占比', 'IC > 0')} ${m.pos.toFixed(0)}%</small></div>
  <div class="stat"><span>${t('多空年化（扣费）', 'L/S annual (net)')}</span><b>${m.ls.toFixed(1)}%</b><small>${t('日均换手', 'daily turnover')} ${(m.to * 100).toFixed(0)}%</small></div></div>
  <div class="charts"><div class="chart-box"><h4>${t('累计 Rank IC', 'Cumulative Rank IC')}</h4>${lineSVG(s, v)}<div class="cap">${v ? t('紫色为研发区间，蓝色为封存区间', 'Purple: development; blue: sealed period') : t('研发区间 2019–2024', 'Development 2019–2024')}</div></div>
  <div class="chart-box"><h4>${t('IC 衰减（持有期）', 'IC decay (horizon)')}</h4>${barSVG(m.decay, ['1d', '5d', '10d', '20d'], x => x.toFixed(3))}<div class="cap">${t('衰减越慢，换手成本越低', 'Slower decay, lower trading cost')}</div></div>
  <div class="chart-box"><h4>${t('五分组年化超额（%）', 'Quintile annual excess (%)')}</h4>${barSVG(m.q, ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], x => x.toFixed(1))}<div class="cap">${t('Q5 为因子值最高组', 'Q5 = highest factor values')}</div></div></div>`;
}
function gateRows(s, v, K) {
  const need = needT(K), row = (ok, a, b, z) => `<tr><td>${a}</td><td>${b}</td><td class="r ${ok === null ? 'muted' : ok ? 'ok-t' : 'bad-t'}">${ok === null ? z || t('信息', 'info') : ok ? t('✓ 通过', '✓ pass') : t('✗ 未通过', '✗ fail')}</td></tr>`;
  return `<table class="gates">${row(true, t('计算完整、无未来函数', 'Complete computation, no look-ahead'), t('完整性检查通过', 'Integrity checks passed'))}
  ${row((s.cov || .96) >= GATE.cov, t('覆盖率', 'Coverage'), `${((s.cov || .96) * 100).toFixed(0)}% ≥ 90%`)}
  ${row(s.ic >= GATE.ic, 'Rank IC', `${s.ic.toFixed(3)} ≥ ${GATE.ic}`)}
  ${row(s.t >= need, t('显著性（多重检验校正）', 'Significance (multiple-testing adjusted)'), t(`t ${s.t.toFixed(2)} ≥ ${need.toFixed(2)}（课题累计 ${K} 次试验）`, `t ${s.t.toFixed(2)} ≥ ${need.toFixed(2)} (${K} trials in topic)`))}
  ${row(s.corr < GATE.corr, t('新颖性（库内及待审候选）', 'Novelty (library & pending)'), t(`与 ${tx(LIBNAME[s.cw])} 相关 ${s.corr.toFixed(2)} < 0.70`, `${s.corr.toFixed(2)} with ${tx(LIBNAME[s.cw])} < 0.70`))}
  ${v ? row(v.t >= GATE.holdT && v.ic > 0, t('封存验证（一次性）', 'Sealed validation (one-off)'), `IC ${v.ic.toFixed(3)} · t ${v.t.toFixed(2)} ≥ 1.96`) : row(null, t('封存验证（一次性）', 'Sealed validation (one-off)'), t('尚未申请', 'Not requested'), t('待申请', 'pending'))}</table>`;
}

/* ---------- human workbench ---------- */
function evalCode(code) {
  if (code.trim() === CODE.H2c.trim()) return { ic: .022, t: 2.4, corr: .55, cw: 'rev5' };
  if (code.trim() === CODE.H2cS.trim()) return { ic: .023, t: 2.8, corr: .66, cw: 'c1' };
  const h = hash(code); return { ic: +(.014 + (h % 14) / 1000).toFixed(3), t: +(1.8 + (h % 15) / 10).toFixed(1), corr: +(.45 + (h >> 4) % 40 / 100).toFixed(2), cw: ['rev5', 'abto', 'c1'][h % 3] };
}
const SIMILAR = { T1: [['c1', ['研究系统 · T1/H2a', 'Research system · T1/H2a'], '0.69'], ['rev5', ['平台内置', 'Built-in'], '0.55'], ['abto', ['平台内置', 'Built-in'], '0.41']],
  T2: [['crm', ['人工', 'Human'], '0.33'], ['pead', ['平台内置', 'Built-in'], '0.21'], ['rev5', ['平台内置', 'Built-in'], '0.08']], x: [['rev5', ['平台内置', 'Built-in'], '0.30'], ['lowvol', ['平台内置', 'Built-in'], '0.22']] };
function handover(tp, n, K) { const p = n.parent && nodeOf(tp, n.parent); const d = p && [...p.steps].reverse().find(s => s.k === 'D' || s.k === 'X');
  return t(`Agent 交接：你从 ${p ? p.id : '—'} 接手。${d ? '最近决定：' + tx(d.txt) + '。' : ''}课题已用 ${K} 次试验。`, `Agent handover: taken over from ${p ? p.id : '—'}. ${d ? 'Latest decision: ' + tx(d.txt) + '. ' : ''}Topic has used ${K} trials.`); }
function wbNode() { const tp = topic(S.wb.topic); return { tp, n: tp && nodeOf(tp, S.wb.branch) }; }
function pageWB() {
  const { tp, n } = wbNode();
  if (!n) return note('wb') + `<div class="card"><div class="empty"><b>${t('还没有打开的人工分支', 'No human branch open')}</b>${t('在“研究运行”的研究树里选择任意分支“从此分支接手”，或新建课题。', 'Pick any branch in the research tree and choose “Take over here”, or create a topic.')}<div style="margin-top:12px"><button class="btn primary" data-a="page" data-v="ops">${t('去研究运行', 'Go to operations')}</button></div></div></div>`;
  const K = trials(tp), done = ['returned', 'archived', 'submitted'].includes(n.status);
  const e = lastE(n), v = lastV(n);
  const tabs = [['start', '起点', 'Start'], ['hyp', '假设', 'Hypothesis'], ['impl', '实现', 'Implement'], ['test', '检验', 'Test'], ['hold', '封存验证', 'Sealed'], ['submit', '提交', 'Submit']];
  const mark = { impl: n.steps.some(s => s.k === 'I') ? '✓' : '', test: e ? (gateOk(e, K) ? '✓' : '✗') : '', hold: v ? '✓' : '' };
  const parent = n.parent && nodeOf(tp, n.parent);
  return note('wb') + `<div class="card"><div class="card-head"><div><div class="row-flex"><span class="subtle">${tp.id} ${tx(tp.name)} /</span><h2>${n.id} · ${tx(n.title)}</h2>${badge(BST, n.status)}</div>
  <p>${t('人工分支', 'Human branch')} · ${tx(n.who)}${parent ? ` · ${t('接手自', 'taken over from')} ${parent.id}` : ''} · ${t('与 Agent 共用工具和试验台账', 'shares tools and the trial ledger with the Agent')}</p></div>
  <div class="actions">${done ? '' : `<button class="btn small" data-a="handback">${t('交回 Agent', 'Hand back to Agent')}</button><button class="btn small" data-a="archive">${t('归档分支', 'Archive branch')}</button>`}</div></div>
  <div class="card-body" style="padding-top:12px;padding-bottom:12px"><div class="ledger"><span>${t('课题试验台账', 'Topic ledger')} <b>${K}</b> ${t('次', 'trials')}</span><span>${t('下一次检验需', 'Next test needs')} t ≥ <b>${needT(K + 1).toFixed(2)}</b></span><span>${t('预算剩余', 'Budget left')} <b>${tp.budget - K}</b></span><span>${tx(SCOPE)}</span></div></div></div>
  <div class="wb-grid"><div><div class="tool-tabs">${tabs.map(([k, z, en]) => `<button class="${S.wb.tool === k ? 'on' : ''}" data-a="tool" data-v="${k}">${t(z, en)}${mark[k] ? ` <i class="${mark[k] === '✓' ? 'ok-t' : 'bad-t'}">${mark[k]}</i>` : ''}</button>`).join('')}</div>
  ${wbTool(tp, n, K, done)}</div>${assistant(tp, n, K)}</div>`;
}
function wbTool(tp, n, K, done) {
  const e = lastE(n), v = lastV(n), dis = done ? 'disabled' : '';
  switch (S.wb.tool) {
    case 'start': return `<div class="card"><div class="card-head"><div><h2>${t('研究起点', 'Starting point')}</h2><p>${t('接手说明、相似因子与数据可用性', 'Handover note, similar factors and data availability')}</p></div></div><div class="card-body">
      <div class="hint">${n.id !== 'H2c' ? handover(tp, n, K) : t('Agent 交接：H2 整体 t 2.0 未达标，收益集中在小市值；H2a 已用市值和行业中性化形成候选 C1（待审）；H2b 因与“换手率异动”重复放弃。你的方向是行业内排序。课题已用 ' + K + ' 次试验。', 'Agent handover: H2 failed overall (t 2.0) with returns in small caps; H2a formed candidate C1 (pending) via size/industry neutralisation; H2b was dropped as a duplicate of “Abnormal turnover”. Your direction: within-industry ranking. Topic has used ' + K + ' trials.')}</div>
      <div class="section-title"><h3>${t('相似因子（库内与待审）', 'Similar factors (library & pending)')}</h3><button class="btn small" data-a="ask" data-v="similar">${t('重新查重', 'Re-check')}</button></div>
      <table class="table"><thead><tr><th>${t('因子', 'Factor')}</th><th>${t('来源', 'Source')}</th><th>${t('与当前实现相关', 'Corr. with current')}</th></tr></thead><tbody>
      ${(SIMILAR[tp.id] || SIMILAR.x).map(([k, src, c]) => `<tr><td><b>${tx(LIBNAME[k])}</b></td><td>${tx(src)}</td><td>${c}</td></tr>`).join('')}</tbody></table>
      <h3 style="margin:16px 0 6px">${t('数据可用性', 'Data availability')}</h3><ul class="checklist"><li><span class="ok-t">✓</span>${t('日频行情（后复权、原价）· 时点', 'Daily bars (adjusted & raw) · point-in-time')}</li><li><span class="ok-t">✓</span>${t('申万一级行业 · 时点', 'SW level-1 industry · point-in-time')}</li><li><span class="ok-t">✓</span>${t('自由流通市值', 'Free-float market cap')}</li><li><span class="warn-t">!</span>${t('分钟数据不在本课题授权范围', 'Minute data is outside this topic’s scope')}</li></ul></div></div>`;
    case 'hyp': return `<div class="card"><div class="card-head"><div><h2>${t('假设与计划', 'Hypothesis & plan')}</h2><p>${t('保存会形成新的假设版本，已有检验仍绑定旧版本', 'Saving creates a new version; past tests stay bound to the old one')}</p></div></div><div class="card-body"><div class="field-grid">
      <label class="field full">${t('机制', 'Mechanism')}<textarea ${dis}>${esc(tx(n.hyp))}</textarea></label>
      <label class="field">${t('预期方向', 'Expected sign')}<select ${dis}><option>${tp.id === 'T1' ? t('负向：拥挤偏离越大，未来收益越低', 'Negative: larger crowded gap, lower future return') : t('正向', 'Positive')}</option><option>${t('负向', 'Negative')}</option></select></label>
      <label class="field">${t('主要持有期', 'Main horizon')}<select ${dis}><option>5d</option><option>1d</option><option>10d</option></select></label>
      <label class="field full">${t('可证伪条件', 'Falsified if')}<textarea ${dis}>${tp.id === 'T1' ? t('行业内排序后，5 日 Rank IC 的 t 值低于校正门槛，或与候选 C1 相关 ≥ 0.70。', 'After within-industry ranking, 5-day Rank IC t-stat is below the adjusted bar, or correlation with C1 ≥ 0.70.') : t('Rank IC 的 t 值低于校正门槛，或与库内因子相关 ≥ 0.70。', 'Rank IC t-stat below the adjusted bar, or correlation ≥ 0.70 with a library factor.')}</textarea></label></div>
      <div class="actions"><button class="btn primary" data-a="toast" data-v="saved" ${dis}>${t('保存为新版本', 'Save as new version')}</button><button class="btn ghost" data-a="ask" data-v="hyp">${t('请助手检查', 'Ask assistant to check')}</button></div></div></div>`;
    case 'impl': return `<div class="card"><div class="card-head"><div><h2>${t('因子实现', 'Implementation')}</h2><p>${t('平台表达式；校验包括语法、字段口径和未来函数', 'Platform expression; checks cover syntax, field definitions and look-ahead')}</p></div></div><div class="card-body">
      <label class="field full">${t('表达式', 'Expression')}<textarea id="code" class="code" spellcheck="false" ${dis}>${esc(n.code || CODE.tpl)}</textarea></label>
      <div class="actions" style="margin-top:12px"><button class="btn" data-a="check" ${dis}>${t('校验', 'Check')}</button><button class="btn ghost" data-a="ask" data-v="suggest">${t('请助手改进', 'Ask assistant to improve')}</button><button class="btn primary" data-a="tool" data-v="test">${t('去检验', 'Go to test')} ›</button></div>
      ${S.wb.checks ? `<ul class="checklist">${S.wb.checks.map(([ok, z, en]) => `<li><span class="${ok ? 'ok-t' : 'bad-t'}">${ok ? '✓' : '✗'}</span>${t(z, en)}</li>`).join('')}</ul>` : ''}</div></div>`;
    case 'test': return `<div class="card"><div class="card-head"><div><h2>${t('研发检验', 'Development test')}</h2><p>${t('只使用研发区间；每次运行都记入课题试验台账', 'Development period only; every run is recorded in the topic ledger')}</p></div></div><div class="card-body">
      <div class="field-grid"><label class="field">${t('股票池', 'Universe')}<input disabled value="${t('中证800 历史时点成分', 'CSI 800 point-in-time')}"></label><label class="field">${t('区间', 'Period')}<input disabled value="2019-01 — 2024-12"></label>
      <label class="field">${t('持有期', 'Horizons')}<input disabled value="1 / 5 / 10 / 20d"></label><label class="field">${t('成本假设', 'Costs')}<input disabled value="${t('双边 0.2%', '0.2% round-trip')}"></label></div>
      <div class="hint ${needT(K + 1) > 2.5 ? 'warning' : ''}">${t(`这次检验将是课题第 ${K + 1} 次试验，通过需 t ≥ ${needT(K + 1).toFixed(2)}，并且与库内因子和待审候选的相关低于 0.70。`, `This will be trial ${K + 1} of the topic; passing needs t ≥ ${needT(K + 1).toFixed(2)} and correlation below 0.70 with library factors and pending candidates.`)}</div>
      <div class="actions"><button class="btn primary" data-a="runtest" ${dis || (S.wb.busy ? 'disabled' : '')}>${S.wb.busy ? t('计算中…', 'Computing…') : t('运行检验', 'Run test')}</button>${e ? `<span class="subtle">${t('最近一次：', 'Latest: ')}E${e.n}</span>` : ''}</div></div></div>
      ${e ? `<div class="card"><div class="card-head"><div><h2>E${e.n} · ${t('检验报告', 'Test report')}</h2><p>${t('绑定当时的表达式与数据版本', 'Bound to the expression and data version at run time')}</p></div>${gateOk(e, e.K) ? badge(BST, 'done').replace(tx(BST.done), t('达标', 'Passed')) : `<span class="badge red">${t('未达标', 'Below bar')}</span>`}</div><div class="card-body">${reportBody(e, null, e.K)}<h3 style="margin:16px 0 6px">${t('门槛检查', 'Gate checks')}</h3>${gateRows(e, null, e.K)}
      ${!gateOk(e, e.K) ? `<div class="actions" style="margin-top:12px"><button class="btn ghost" data-a="ask" data-v="diagnose">${t('请助手诊断', 'Ask assistant to diagnose')}</button></div>` : `<div class="actions" style="margin-top:12px"><button class="btn primary" data-a="tool" data-v="hold">${t('申请封存验证', 'Request sealed validation')} ›</button></div>`}</div></div>` : ''}`;
    case 'hold': { const ok = e && gateOk(e, e.K);
      return `<div class="card"><div class="card-head"><div><h2>${t('封存验证', 'Sealed validation')}</h2><p>${t('2025 全年数据只对达标候选开放，每个候选仅一次，由独立复核 Agent 执行', '2025 data opens only to passing candidates, once per candidate, run by the independent reviewer Agent')}</p></div></div><div class="card-body">
      ${v ? `${gateRows(e, v, trials(tp))}` : ok ? `<div class="hint">${t('确认后表达式与参数冻结；验证结果不能用来再调参。', 'On confirm the expression and parameters are frozen; results cannot be used for further tuning.')}</div><button class="btn primary" data-a="hold" ${dis}>${t('冻结并申请封存验证', 'Freeze and request')}</button>` : `<div class="empty"><b>${t('研发检验尚未达标', 'Development test not passed yet')}</b>${t('先在“检验”中通过校正后门槛。', 'Pass the adjusted bar under “Test” first.')}</div>`}</div></div>`; }
    case 'submit': { const ready = v && v.res === 'ok';
      return `<div class="card"><div class="card-head"><div><h2>${t('提交审查', 'Submit for review')}</h2><p>${t('提交后进入审查；复核由其他有权限的成员完成', 'Goes to review; another authorised member reviews it')}</p></div></div><div class="card-body">
      <ul class="checklist"><li><span class="${n.steps.some(s => s.k === 'I') ? 'ok-t' : 'bad-t'}">${n.steps.some(s => s.k === 'I') ? '✓' : '✗'}</span>${t('实现与校验', 'Implementation & checks')}</li><li><span class="${e && gateOk(e, e.K) ? 'ok-t' : 'bad-t'}">${e && gateOk(e, e.K) ? '✓' : '✗'}</span>${t('研发检验达标（校正后）', 'Development test passed (adjusted)')}</li><li><span class="${ready ? 'ok-t' : 'bad-t'}">${ready ? '✓' : '✗'}</span>${t('封存验证通过', 'Sealed validation passed')}</li><li><span class="ok-t">✓</span>${t('全部试验自动附在证据包中', 'All trials attached automatically')}</li></ul>
      <div class="actions" style="margin-top:14px"><button class="btn primary" data-a="submit" ${ready && !done ? '' : 'disabled'}>${t('提交审查', 'Submit')}</button>${done ? '' : `<button class="btn" data-a="handback">${t('改为交回 Agent', 'Hand back instead')}</button>`}</div></div></div>`; }
  }
  return '';
}
function assistant(tp, n, K) {
  if (!S.wb.chat) S.wb.chat = [{ ai: true, txt: [`你接手了 ${n.id}。我可以调用本模块的工具：查重、校验、检验、诊断。检验会计入课题台账（当前 ${K} 次）。`, `You took over ${n.id}. I can call this module’s tools: dedup, checks, tests, diagnosis. Tests count toward the topic ledger (now ${K}).`] }];
  return `<div class="card asst"><div class="agent-head"><span class="agent-mark">✧</span><div><strong>${t('因子研究助手', 'Factor research assistant')}</strong><small>${t('调用与 Agent 相同的工具 · 改动先给你确认', 'Same tools as the Agent · changes need your OK')}</small></div></div>
  <div class="chat" id="chat">${S.wb.chat.map(m => `<div class="msg ${m.ai ? 'ai' : 'me'}">${esc(tx(m.txt))}${m.tool ? `<div class="toolcard"><b>${t('调用工具', 'Tool')} · ${tx(m.tool[0])}</b><div class="tm">${m.tool[1].map(x => `<span>${esc(tx(x))}</span>`).join('')}</div></div>` : ''}${m.btn ? `<div style="margin-top:7px"><button class="btn small primary" data-a="${m.btn[0]}">${tx(m.btn[1])}</button></div>` : ''}</div>`).join('')}</div>
  <div class="compose"><div class="qp"><button data-a="ask" data-v="diagnose">${t('诊断最近一次检验', 'Diagnose latest test')}</button><button data-a="ask" data-v="similar">${t('查相似因子', 'Find similar')}</button><button data-a="ask" data-v="suggest">${t('建议改进', 'Suggest a fix')}</button><button data-a="ask" data-v="hand">${t('交回 Agent', 'Hand back')}</button></div>
  <div class="row"><input id="ask" placeholder="${t('问助手，或让它调用工具…', 'Ask, or have it call a tool…')}"><button class="btn small primary" data-a="ask" data-v="free">${t('发送', 'Send')}</button></div></div></div>`;
}
function reply(kind) {
  const { tp, n } = wbNode(); const e = lastE(n), K = trials(tp);
  const me = { diagnose: ['诊断最近一次检验', 'Diagnose the latest test'], similar: ['查相似因子', 'Find similar factors'], suggest: ['建议改进', 'Suggest a fix'], hand: ['交回 Agent', 'Hand back to the Agent'], hyp: ['检查我的假设', 'Check my hypothesis'] }[kind];
  const q = kind === 'free' ? ($('#ask').value.trim() || t('帮我看看这个分支', 'Look at this branch')) : me;
  S.wb.chat.push({ ai: false, txt: q });
  let a;
  if (kind === 'diagnose') a = e ? { txt: gateOk(e, e.K) ? [`E${e.n} 已达标。下一步可以申请封存验证；注意每个候选只能用一次。`, `E${e.n} passed. Next, request sealed validation — once per candidate.`] : [`E${e.n} 未达标，主要是显著性：t ${e.t.toFixed(2)} 低于按 ${e.K} 次试验校正的 ${needT(e.K).toFixed(2)}。分层显示 ${tp.id === 'T1' ? 'Q5 收益主要来自小市值组，行业内排序没有去掉市值暴露（0.38）。建议在行业内排序后再做市值中性化。' : '分层不单调，衰减较快。建议先确认机制，再决定改实现还是修订假设。'}再检验会是第 ${K + 1} 次，门槛 ${needT(K + 1).toFixed(2)}。`, `E${e.n} is below the bar on significance: t ${e.t.toFixed(2)} vs ${needT(e.K).toFixed(2)} adjusted for ${e.K} trials. ${tp.id === 'T1' ? 'Q5 returns come mainly from small caps; within-industry ranking left size exposure (0.38). Neutralise size after ranking.' : 'Quintiles are not monotonic and decay is fast. Confirm the mechanism before choosing between a new implementation and a revised hypothesis.'} A retest would be trial ${K + 1} with bar ${needT(K + 1).toFixed(2)}.`],
    tool: [['读取检验报告', 'Read test report'], [`E${e.n}`, `IC ${e.ic.toFixed(3)}`, `t ${e.t.toFixed(2)}`, [`市值暴露 0.38`, `size exposure 0.38`]]], btn: gateOk(e, e.K) || tp.id !== 'T1' ? null : ['adopt', ['采纳建议到草稿', 'Apply to draft']] }
    : { txt: ['还没有检验结果。我可以先帮你校验实现，或者直接运行检验（会计入台账）。', 'No test yet. I can check the implementation first, or run the test (counts toward the ledger).'] };
  else if (kind === 'similar') a = { txt: ['当前实现与待审候选 C1 相关 0.69，接近 0.70 的重复线；与 5 日反转相关 0.55。行业内排序如果不能带来额外信息，可能被判为 C1 的重复。', 'The current implementation correlates 0.69 with pending C1 — near the 0.70 duplicate line — and 0.55 with 5-day reversal. If within-industry ranking adds nothing, it may be judged a duplicate of C1.'], tool: [['因子库查重', 'Library dedup'], [['C1 0.69', 'C1 0.69'], ['5日反转 0.55', '5-day reversal 0.55'], ['换手率异动 0.41', 'Abnormal turnover 0.41']]] };
  else if (kind === 'suggest') a = { txt: ['建议：行业内排序后，再对对数市值做中性化。改动如下，采纳后进入草稿，不会自动运行检验。\n\nalpha = neutralize(group_rank(-gap * crowd, sw_l1), by=[log_mcap])', 'Suggestion: neutralise log market cap after within-industry ranking. Applying puts it in your draft; no test runs automatically.\n\nalpha = neutralize(group_rank(-gap * crowd, sw_l1), by=[log_mcap])'], btn: ['adopt', ['采纳到草稿', 'Apply to draft']] };
  else if (kind === 'hand') a = { txt: ['交回后，这个分支的代码、试验和你的说明会成为研究决策的输入；它可能继续、合并或放弃该方向，并计入同一台账和预算。', 'After handing back, this branch’s code, trials and notes become input for the decision Agent; it may continue, merge or drop the direction, under the same ledger and budget.'], btn: ['handback', ['确认交回 Agent', 'Confirm hand-back']] };
  else if (kind === 'hyp') a = { txt: ['假设可证伪，方向明确。建议补充：如果与 C1 的相关 ≥ 0.70，就视为 C1 的变体而不是新因子。', 'Falsifiable with a clear sign. Add: if correlation with C1 ≥ 0.70, treat it as a variant of C1, not a new factor.'], tool: [['可证伪检查', 'Falsifiability check'], [['通过', 'pass']]] };
  else a = { txt: ['收到。我会用本模块的工具处理，任何会改动研究内容或花费试验次数的操作都会先请你确认。', 'Got it. I’ll use this module’s tools; anything that changes the research or spends a trial will ask you first.'] };
  S.wb.chat.push({ ai: true, ...a }); render(); const c = $('#chat'); if (c) c.scrollTop = c.scrollHeight;
}

/* ---------- review ---------- */
function candParts(c) { const tp = topic(c.topic), n = nodeOf(tp, c.node); return { tp, n, e: lastE(n), v: lastV(n) }; }
function pageReview() {
  if (!CANDS.find(c => c.id === S.rv.sel)) S.rv.sel = CANDS[0] && CANDS[0].id;
  const c = CANDS.find(x => x.id === S.rv.sel);
  const stc = { pending: ['待复核', 'Pending', 'purple'], approved: ['已入库', 'Admitted', 'green'], returned: ['已退回补证', 'Returned', 'amber'], archived: ['已归档', 'Archived', 'gray'] };
  const q = CANDS.map(x => { const p = candParts(x); return `<button class="qi${x.id === S.rv.sel ? ' sel' : ''}" data-a="cand" data-v="${x.id}"><div class="row-flex"><span class="subtle">${x.id} · ${x.topic}/${x.node}</span>${badge(stc, x.status)}</div><b>${tx(p.n.title)}</b><small>${tx(p.tp.name)}</small><small>${x.by === 'human' ? t('人工提交', 'Submitted by a person') : t('研究系统提交', 'Submitted by the research system')}</small></button>`; }).join('');
  if (!c) return note('review') + `<div class="card"><div class="empty">${t('没有待审候选', 'No candidates')}</div></div>`;
  const { tp, n, e, v } = candParts(c), K = trials(tp);
  const allOk = gateOk(e, K) && v && v.res === 'ok';
  const trialRows = allE(tp).map(({ s, n: b }) => `<tr${b.id === c.node && s === e ? ' style="background:#faf6fd"' : ''}><td><b>E${s.n}</b></td><td>${b.id} · ${tx(b.title)}<small>${b.by === 'human' ? t('人工', 'Human') : 'Agent'}</small></td><td>${s.ic.toFixed(3)}</td><td>${s.t.toFixed(2)}</td><td>${s.corr.toFixed(2)}</td><td>${s.res === 'ok' ? `<span class="ok-t">${t('达标', 'pass')}</span>` : s.res === 'warn' ? `<span class="warn-t">${t('重复', 'dup')}</span>` : `<span class="bad-t">${t('未达标', 'fail')}</span>`}</td></tr>`).join('');
  const dis = canReview() && c.status === 'pending' ? '' : 'disabled';
  return note('review') + `<div class="rv-grid"><div class="queue">${q}</div><div>
  <div class="card"><div class="card-head"><div><div class="row-flex"><span class="subtle">${c.id}</span><h2>${tx(n.title)}</h2>${badge(stc, c.status)}</div><p>${tx(tp.name)} · ${t('分支', 'branch')} ${n.id} · ${c.by === 'human' ? t('人工研究', 'human research') : t('研究系统', 'research system')}</p></div>${allOk ? `<span class="badge green">${t('门槛全部通过', 'All gates passed')}</span>` : `<span class="badge red">${t('有门槛未通过', 'Gate failed')}</span>`}</div>
  <div class="card-body"><div class="kv"><span>${t('假设', 'Hypothesis')}</span><div>${tx(n.hyp)}</div><span>${t('表达式', 'Expression')}</span><div class="expr">${esc(n.code || '').replace(/\n/g, '<br>')}</div><span>${t('数据与口径', 'Data & definitions')}</span><div>${tx(SCOPE)}</div></div></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('门槛检查', 'Gate checks')}</h2><p>${t('显著性按课题当前全部试验次数校正；课题再有新试验，门槛会随之提高', 'Significance is adjusted for all trials in the topic so far; new trials raise the bar')}</p></div></div><div class="card-body">${gateRows(e, v, K)}</div></div>
  <div class="card"><div class="card-head"><div><h2>${t('证据', 'Evidence')}</h2><p>E${e.n} · ${t('研发与封存区间', 'development and sealed periods')}</p></div></div><div class="card-body">${reportBody(e, v, K)}</div></div>
  <div class="card"><div class="card-head"><div><h2>${t('课题的全部试验', 'All trials in this topic')}</h2><p>${t('包括失败、重复和放弃的方向，不只是被提交的这一个', 'Including failed, duplicate and abandoned directions — not just the submitted one')}</p></div><button class="text-btn" data-a="opentree" data-v="${tp.id}">${t('查看研究树', 'View tree')} ›</button></div><div class="table-wrap"><table class="table"><thead><tr><th>${t('试验', 'Trial')}</th><th>${t('分支', 'Branch')}</th><th>Rank IC</th><th>t</th><th>${t('最大相关', 'Max corr')}</th><th>${t('结果', 'Result')}</th></tr></thead><tbody>${trialRows}</tbody></table></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('独立复核意见', 'Independent review opinion')}</h2><p>${t('独立复核 Agent · 不共享研究上下文 · 仅为建议', 'Independent reviewer Agent · no shared research context · advisory only')}</p></div></div><div class="card-body"><ul class="checklist">${c.ai.map(x => `<li><span class="muted">•</span>${tx(x)}</li>`).join('')}</ul>
  <h3 style="margin:14px 0 4px">${t('局限', 'Limitations')}</h3><ul class="checklist">${c.limits.map(x => `<li><span class="warn-t">!</span>${tx(x)}</li>`).join('')}</ul></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('复核决定', 'Decision')}</h2><p>${t('入库只授予研究用途；策略使用和实盘准入另行审批', 'Admission grants research use only; strategy and live use are approved separately')}</p></div></div><div class="card-body">
  ${c.status !== 'pending' ? `<p>${t('已决定：', 'Decided: ')}${tx(stc[c.status])}</p>` : !canReview() ? `<div class="hint warning">${t('复核需由具备因子复核权限的成员完成。', 'Review requires a member with factor-review permission.')}</div>` : `<label class="checks"><span><input type="checkbox" id="ack" ${S.rv.ack ? 'checked' : ''} data-a="ack"> ${t('我已查看全部试验、封存验证结果和局限', 'I have read all trials, the sealed validation and the limitations')}</span></label>`}
  <div class="decision" style="margin-top:12px"><button class="btn primary" data-a="decide" data-v="approved" ${dis} ${S.rv.ack && allOk ? '' : 'disabled'}>${t('入库（研究用途）', 'Admit (research use)')}</button><button class="btn" data-a="decide" data-v="returned" ${dis}>${t('退回补证', 'Return for more evidence')}</button><button class="btn danger" data-a="decide" data-v="archived" ${dis}>${t('归档', 'Archive')}</button></div></div></div>
  </div></div>`;
}

/* ---------- library ---------- */
function pageLib() {
  const src = { builtin: ['平台内置', 'Built-in'], human: ['人工', 'Human'], agent: ['研究系统', 'Research system'] };
  const st = { use: ['研究用途', 'Research use', 'green'], watch: ['观察', 'Watch', 'amber'], off: ['停用', 'Retired', 'gray'] };
  const tr = { ok: ['正常', 'Normal'], weak: ['减弱', 'Weakening'], off: ['失效', 'Decayed'] };
  const rows = LIB.filter(x => S.lib === 'all' || x.st === S.lib || (S.lib === 'agent' && x.src === 'agent'));
  const spark = (k, seed) => { const r = rng(seed); let y = 10; const pts = Array.from({ length: 20 }, (_, i) => { y += (k === 'ok' ? -.25 : k === 'weak' ? .1 : .35) + (r() - .5) * 2; y = Math.max(2, Math.min(18, y)); return `${i * 3.6},${y.toFixed(1)}`; }).join(' '); return `<svg class="spark" viewBox="0 0 70 20"><polyline points="${pts}" fill="none" stroke="${k === 'ok' ? '#76489a' : k === 'weak' ? '#96651f' : '#a0a9b6'}" stroke-width="1.3"/></svg>`; };
  const f = [['all', '全部', 'All'], ['use', '研究用途', 'Research use'], ['watch', '观察', 'Watch'], ['off', '停用', 'Retired'], ['agent', '研究系统产出', 'From research system']];
  return note('lib') + `<div class="filters">${f.map(([k, z, e]) => `<button class="${S.lib === k ? 'on' : ''}" data-a="libf" data-v="${k}">${t(z, e)}</button>`).join('')}</div>
  <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('因子', 'Factor')}</th><th>${t('来源', 'Source')}</th><th>${t('类别', 'Category')}</th><th>Rank IC</th><th>t</th><th>${t('日均换手', 'Daily turnover')}</th><th>${t('近 60 日 IC', 'IC, last 60d')}</th><th>${t('状态', 'Status')}</th></tr></thead><tbody>
  ${rows.map((x, i) => `<tr><td><b>${tx(x.n)}</b>${x.note ? `<small>${tx(x.note)}</small>` : ''}</td><td>${tx(src[x.src])}</td><td>${tx(x.cat)}</td><td>${x.ic.toFixed(3)}</td><td>${x.t.toFixed(1)}</td><td>${(x.to * 100).toFixed(0)}%</td><td>${spark(x.tr, i + 3)} <small style="display:inline">${tx(tr[x.tr])}</small></td><td>${badge(st, x.st)}</td></tr>`).join('')}
  </tbody></table></div><div class="card-footer"><small>${t('统一口径：中证800 历史时点成分，2019–2024，5 日 Rank IC，NW 调整 t 值。平台共 334 个因子，此处为示例。', 'Common definition: CSI 800 point-in-time, 2019–2024, 5-day Rank IC, Newey-West t. 334 factors on the platform; sample shown.')}</small></div></div>`;
}

/* ---------- capabilities & evals ---------- */
function pageCaps() {
  return note('caps') + `<div class="card"><div class="card-head"><div><h2>${t('研究系统组成', 'Research system composition')}</h2><p>${t('当前编排：课题调度分配课题；每个课题一个研究决策 Agent，按结果调用专职 Agent 与能力单元；独立复核与研究隔离', 'Current orchestration: the scheduler assigns topics; each topic has a decision Agent that calls specialist agents and units by results; independent review is isolated')}</p></div><span class="badge purple">${t('编排版本 v2', 'Orchestration v2')}</span></div><div class="card-body"><div class="cap-diagram">
  <div class="cap-col"><h4>${t('人', 'People')}</h4><div class="units">${[['研究负责人', 'Research lead', '课题、授权、预算', 'topics, authorisation, budget'], ['因子研究员', 'Factor researcher', '观察、意见、接手分支', 'watch, comment, take over'], ['因子复核人', 'Factor reviewer', '入库决定', 'admission decisions']].map(x => `<div class="unit"><span class="ui">◎</span><div><b>${t(x[0], x[1])}</b><small>${t(x[2], x[3])}</small></div></div>`).join('')}</div></div>
  <div class="cap-col"><h4>${t('Agent 与能力单元', 'Agents & capability units')}</h4><div class="coord" style="background:#fbfafc;border-color:var(--line)"><b style="color:var(--ink)">${t('课题调度', 'Topic scheduler')}</b><br><small>${t('规则：排队、并发上限、跨课题预算', 'rules: queue, concurrency, cross-topic budget')}</small></div><div style="text-align:center;color:#b9a9c8">↓</div>
  <div class="coord"><b>F0 · ${t('研究决策 Agent', 'Research decision Agent')}</b><br><small>${t('每个课题一个实例 · 下一步 · 修订 · 分支 · 放弃 · 提交', 'one instance per topic · next step · revise · branch · drop · submit')}</small></div><div style="text-align:center;color:#b9a9c8">↓ ${t('按结果调用', 'calls by results')}</div>
  <div class="units">${CAPS.slice(1).map(c => `<div class="unit ${c.m === 'indep' ? 'indep' : c.m === 'sub' ? 'agent' : ''}"><span class="ui">${c.f}</span><div style="flex:1"><b>${tx(c.n)}</b></div>${formBadge(c.m)}</div>`).join('')}</div></div>
  <div class="cap-col"><h4>${t('确定性服务（不由模型决定）', 'Deterministic services')}</h4><div class="units">${[['数据视图', 'Data view', '固定版本、时点口径', 'fixed versions, point-in-time'], ['因子计算', 'Factor compute', 'ResearchEngine', 'ResearchEngine'], ['试验台账', 'Trial ledger', '只追加，不可删', 'append-only'], ['封存样本', 'Sealed sample', '每候选一次', 'once per candidate'], ['因子库查重', 'Library dedup', '含待审候选', 'incl. pending candidates']].map(x => `<div class="unit"><span class="ui">▤</span><div><b>${t(x[0], x[1])}</b><small>${t(x[2], x[3])}</small></div></div>`).join('')}</div></div></div></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('能力单元与评测', 'Capability units & evals')}</h2><p>${t('每个 AI 功能点一个专职单元，各有提示词与工具版本、评测集和得分，可以单独改进和回归；F0 是决定下一步与回退的功能点。形态（Agent / 子 Agent / 能力单元）由评测决定，可调整。', 'One specialist unit per AI point, each with prompt/tool versions, an eval set and a score, improved and regression-tested alone; F0 decides next steps and backtracking. The form (Agent / sub-agent / unit) is set by evals and can change.')}</p></div></div><div class="table-wrap"><table class="table"><thead><tr><th>${t('功能点', 'Point')}</th><th>${t('能力单元', 'Unit')}</th><th>${t('形态', 'Form')}</th><th>${t('主要工具', 'Main tools')}</th><th>${t('评测集', 'Eval set')}</th><th>${t('当前', 'Current')}</th><th>${t('基线', 'Baseline')}</th><th>${t('版本', 'Ver.')}</th></tr></thead><tbody>
  ${CAPS.map(c => `<tr><td><b>${c.f}</b></td><td><b>${tx(c.n)}</b></td><td>${formBadge(c.m)}</td><td>${tx(c.tools)}</td><td>${tx(c.ev)}</td><td><span class="score">${c.s}</span></td><td>${c.b}</td><td>${c.v}</td></tr>`).join('')}</tbody></table></div></div>
  <div class="card"><div class="card-head"><div><h2>${t('编排方案对照实验', 'Orchestration comparison')}</h2><p>${t('同数据视图、同 3 个课题、每组 30 次试验与 300k Token、同门槛与封存样本', 'Same data view, same 3 topics, 30 trials and 300k tokens per arm, same gates and sealed sample')}</p></div><span class="badge amber">${t('计划中 · 未运行', 'Planned · not run')}</span></div><div class="card-body"><div class="arms">
  <div class="arm"><h4>A · ${t('固定顺序流水线', 'Fixed-order pipeline')}</h4><div class="flow">F1 → F2 → F3 → F4 → F5 → F6</div>${t('同一批专职单元按固定顺序交接；失败时按规则回到上一步，没有 F0。', 'The same specialist units hand off in a fixed order; on failure a rule sends it back one step; no F0.')}</div>
  <div class="arm"><h4>B · ${t('研究决策 + 专职单元', 'Decision Agent + specialists')}</h4><div class="flow">F0 ⇄ {F1…F4}; F5 ${t('独立', 'isolated')}</div>${t('F0 按结果选择调用任一单元，可修订、分支、换方向、放弃（当前方案）。', 'F0 picks any unit by results; can revise, branch, pivot, drop (current).')}</div>
  <div class="arm"><h4>C · ${t('人工研究基线', 'Human baseline')}</h4><div class="flow">${t('研究员 + 同一工作台', 'researcher + same workbench')}</div>${t('研究员使用相同工具与台账，不用 Agent。', 'Researchers use the same tools and ledger without Agents.')}</div></div>
  <h3 style="margin:16px 0 6px">${t('比较指标', 'Metrics')}</h3><ul class="checklist"><li>${t('通过校正门槛的候选数；封存验证通过率', 'Candidates passing the adjusted bar; sealed-validation pass rate')}</li><li>${t('每个合格候选的试验次数与 Token 成本', 'Trials and tokens per qualified candidate')}</li><li>${t('失败后选择正确回退方向的比例（专家标注）', 'Share of correct moves after failure (expert-labelled)')}</li><li>${t('人工投入时间；入库后 3 个月 IC 保持率', 'Human time spent; IC retention 3 months after admission')}</li></ul>
  <div class="hint" style="margin-top:12px">${t('调整规则：某个单元改变形态（例如能力单元改为子 Agent）后，其单元评测显著更好、且整体指标不下降，才发布新编排版本；否则回退。', 'Change rule: a unit changes form (e.g. unit → sub-agent) only if its own eval improves clearly and the overall metrics do not drop; otherwise roll back.')}</div>
  <div class="actions"><button class="btn primary" data-a="exp" ${isLead() ? '' : 'disabled'}>${t('提交实验计划', 'Submit experiment plan')}</button>${isLead() ? '' : `<span class="subtle">${t('需研究负责人', 'Research lead only')}</span>`}</div></div></div>`;
}

/* ---------- simulation: topic T2 ---------- */
const T2 = topic('T2');
const add = (p, o) => { T2.nodes.push(Object.assign({ parent: p, by: 'agent', steps: [], code: CODE.T2 }, o)); S.sel === 'T2' && S.follow && (S.node = o.id); };
const SIM = [
  () => { S.unit = { u: 'F1', tp: 'T2' }; T2.act = ['起点检索：读取因子库与相关历史试验', 'Starting point: reading the library and related past trials']; ev('T2', ['读取 334 个库内因子与 2 个相关历史课题', 'Read 334 library factors and 2 related past topics']); },
  () => { S.unit = { u: 'F2', tp: 'T2' }; add(null, { id: 'H1', title: ['一致预期上调后的反应不足', 'Under-reaction to consensus upgrades'], status: 'run', hyp: ['分析师一致预期上调后，股价对新信息反应滞后，未来 5–20 日仍有超额收益。', 'After consensus EPS upgrades, prices under-react and earn excess returns over 5–20 days.'] }); T2.act = ['假设研究：形成 H1', 'Hypothesis research: formed H1']; ev('T2', ['形成假设 H1：一致预期上调后的反应不足', 'Formed H1: under-reaction to consensus upgrades']); },
  () => { S.unit = { u: 'F3', tp: 'T2' }; nodeOf(T2, 'H1').steps.push({ k: 'I', ok: true, note: ['校验发现预期数据需按发布日滞后一日，已修正', 'Check found consensus data must lag release by one day; fixed'] }); T2.act = ['因子实现：H1 通过校验（已修正一处未来函数）', 'Implementation: H1 checked (one look-ahead fixed)']; ev('T2', ['H1 实现：发现并修正预期数据的未来函数', 'H1 implemented: found and fixed a look-ahead in consensus data']); },
  () => { S.unit = { u: 'F4', tp: 'T2' }; const h = nodeOf(T2, 'H1'); h.steps.push({ k: 'E', n: 1, ic: .018, t: 1.7, K: 1, corr: .49, cw: 'crm', res: 'fail', slow: 1, to: .09 }); h.status = 'fail'; T2.act = ['检验诊断：E1 未达标（t 1.7 < 1.96）', 'Test: E1 below bar (t 1.7 < 1.96)']; ev('T2', ['E1 未达标：t 1.7，需 1.96', 'E1 below bar: t 1.7 vs 1.96']); },
  () => { S.unit = { u: 'coord', tp: 'T2' }; nodeOf(T2, 'H1').steps.push({ k: 'D', txt: ['信号集中在分析师覆盖少的股票，噪声大 → 修订为 H2', 'Signal sits in thinly covered stocks and is noisy → revise into H2'] }); add('H1', { id: 'H2', title: ['限定分析师覆盖 ≥ 3 家', 'Require ≥ 3 covering analysts'], status: 'run', hyp: ['覆盖充分时一致预期更可靠，反应不足更明显。', 'With enough coverage the consensus is reliable and under-reaction clearer.'] }); T2.act = ['研究决策：修订假设，开 H2', 'Decision Agent: revised the hypothesis, opened H2']; ev('T2', ['修订假设 → H2（限定覆盖 ≥ 3 家）', 'Revised → H2 (≥ 3 analysts)']); },
  () => { S.unit = { u: 'F4', tp: 'T2' }; const h = nodeOf(T2, 'H2'); h.steps.push({ k: 'I', ok: true }, { k: 'E', n: 2, ic: .029, t: 3.4, K: 2, corr: .78, cw: 'crm', res: 'warn', slow: 1, to: .1 }); T2.act = ['检验诊断：E2 显著，但与库内因子相关 0.78', 'Test: E2 significant but 0.78 corr with a library factor']; ev('T2', ['E2 显著（t 3.4），与“一致预期调整动量”相关 0.78', 'E2 significant (t 3.4) but 0.78 corr with “Consensus revision momentum”']); },
  () => { S.unit = { u: 'coord', tp: 'T2' }; const h = nodeOf(T2, 'H2'); h.steps.push({ k: 'D', txt: ['与库内因子过于相似 → 对其正交化，开 H2a', 'Too close to a library factor → orthogonalise, open H2a'] }); h.status = 'branched'; add('H2', { id: 'H2a', title: ['对已有因子正交化', 'Orthogonalised to existing factor'], status: 'run', hyp: ['剔除一致预期调整动量后，反应不足仍有独立信息。', 'Under-reaction carries information beyond consensus revision momentum.'] }); T2.act = ['研究决策：正交化后开 H2a', 'Decision Agent: orthogonalise, open H2a']; ev('T2', ['决定正交化 → H2a', 'Decided to orthogonalise → H2a']); },
  () => { S.unit = { u: 'F4', tp: 'T2' }; const h = nodeOf(T2, 'H2a'); h.steps.push({ k: 'I', ok: true }, { k: 'E', n: 3, ic: .021, t: 2.9, K: 3, corr: .33, cw: 'crm', res: 'ok', slow: 1, to: .09 }, { k: 'D', txt: ['研发检验达标 → 申请封存验证', 'Development test passed → request sealed validation'] }); T2.act = ['检验诊断：E3 达标，申请封存验证', 'Test: E3 passed, requesting sealed validation']; ev('T2', ['E3 达标：t 2.9 ≥ 2.39，相关 0.33', 'E3 passed: t 2.9 ≥ 2.39, corr 0.33']); },
  () => { S.unit = { u: 'F5', tp: 'T2' }; const h = nodeOf(T2, 'H2a'); h.steps.push({ k: 'V', ic: .016, t: 2.2, res: 'ok' }, { k: 'D', txt: ['独立复核通过 → 提交审查，候选 C2', 'Independent check passed → submitted as candidate C2'] }); h.status = 'review'; T2.status = 'review'; T2.act = ['候选 C2 已提交审查', 'Candidate C2 submitted for review']; CAND_T2.time = clock(); CANDS.push(CAND_T2); ev('T2', ['封存验证通过（t 2.2）→ 候选 C2 提交审查', 'Sealed validation passed (t 2.2) → candidate C2 submitted']); toast(t('研究系统提交了新候选 C2', 'The research system submitted candidate C2')); setTimeout(() => { S.unit = null; refresh(); }, 2500); }
];
let timer = null;
function simStep() { if (S.sim.i >= SIM.length) return; SIM[S.sim.i++](); T2.tokens += 2 + (S.sim.i % 3); refresh(); }
function refresh() { if (!['ops', 'review'].includes(S.page) || ($('#overlay').innerHTML && S.page !== 'ops')) { $('#sidebar').innerHTML = sidebar(); return; } const y = window.scrollY; render(); window.scrollTo(0, y); }
function simLoop() { clearInterval(timer); timer = setInterval(() => { if (S.sim.on && S.sysOn && T2.status === 'run') simStep(); if (S.sim.i >= SIM.length) clearInterval(timer); }, 3200); }

/* ---------- modals & toast ---------- */
function modal(title, sub, body, foot) { $('#overlay').innerHTML = `<div class="modal-backdrop" data-a="closebg"><div class="modal wide" role="dialog" aria-modal="true"><div class="modal-header"><div><h2>${title}</h2>${sub ? `<small>${sub}</small>` : ''}</div><button class="modal-close" data-a="close">×</button></div><div class="modal-body">${body}</div>${foot ? `<div class="modal-footer">${foot}</div>` : ''}</div></div>`; }
const close = () => { $('#overlay').innerHTML = ''; };
let tt; function toast(m) { const el = $('#toast'); el.textContent = m; el.classList.add('show'); clearTimeout(tt); tt = setTimeout(() => el.classList.remove('show'), 2600); }

/* ---------- actions ---------- */
const A = {
  lang: v => { L = v; render(); }, demo: () => { S.demoOpen = !S.demoOpen; $('#demo').innerHTML = demo(); },
  set: (v, el) => { const k = el.dataset.k; S[k] = v === 'true' ? true : v === 'false' ? false : v; S.rv.ack = false; render(); },
  page: v => { S.page = v; close(); render(); window.scrollTo(0, 0); },
  topic: v => { S.sel = v; S.node = null; S.follow = true; render(); }, node: v => { S.node = v; S.follow = false; render(); },
  follow: () => { const tp = topic(S.sel); S.follow = true; S.node = tp.nodes.length ? tp.nodes[tp.nodes.length - 1].id : null; render(); },
  opentree: v => { S.page = 'ops'; S.sel = v; S.node = null; render(); window.scrollTo(0, 0); },
  report: v => { const [tid, n] = v.split('|'); const tp = topic(tid); const x = allE(tp).find(o => o.s.n === +n); const vv = lastV(x.n); const withV = lastE(x.n) === x.s ? vv : null;
    modal(`E${x.s.n} · ${t('检验报告', 'Test report')}`, `${tid} / ${x.n.id} ${tx(x.n.title)} · ${t('课题第', 'trial')} ${x.s.K} ${t('次试验', 'of topic')}`, reportBody(x.s, withV, x.s.K) + `<h3 style="margin:16px 0 6px">${t('门槛检查（按当时试验次数）', 'Gate checks (at that trial count)')}</h3>` + gateRows(x.s, withV, x.s.K), `<button class="btn" data-a="close">${t('关闭', 'Close')}</button>`); },
  takeover: v => { const tp = topic(S.sel); let n = nodeOf(tp, v);
    if (n.by !== 'human') { const id = v + 'm'; if (!nodeOf(tp, id)) { tp.nodes.push({ id, parent: v, by: 'human', who: ['张新迪', 'Zhang Xindi'], title: [`接手自 ${v}`, `Taken over from ${v}`], status: 'human', code: n.code || CODE.tpl, hyp: n.hyp, steps: [] }); ev(tp.id, [`张新迪 接手 ${v}，新建人工分支 ${id}`, `Zhang Xindi took over ${v}, created human branch ${id}`]); } n = nodeOf(tp, id); }
    S.wb = { topic: tp.id, branch: n.id, tool: 'start', busy: false, checks: null, chat: null }; S.page = 'wb'; render(); window.scrollTo(0, 0); },
  tool: v => { const c = $('#code'); if (c) { const { n } = wbNode(); n.code = c.value; } S.wb.tool = v; render(); },
  check: () => { const { n } = wbNode(); n.code = $('#code').value; const bad = !/alpha\s*=\s*\S/.test(n.code); const look = /delay\([^,]+,\s*-/.test(n.code);
    S.wb.checks = [[!bad, '语法与输出变量 alpha', 'Syntax and output variable alpha'], [true, '字段口径：open/close/turnover/sw_l1/log_mcap 均为时点数据', 'Fields: open/close/turnover/sw_l1/log_mcap are point-in-time'], [!look, '未来函数检查', 'Look-ahead check'], [true, '受限执行：抽样 20 日计算成功', 'Sandboxed run: 20 sample days computed']];
    if (!n.steps.some(s => s.k === 'I') && !bad && !look) n.steps.push({ k: 'I', ok: true, note: ['人工实现，校验通过', 'Implemented by hand, checks passed'] }); render(); },
  runtest: () => { const { tp, n } = wbNode(); const c = $('#code'); if (c) n.code = c.value; S.wb.busy = true; render();
    setTimeout(() => { const K = trials(tp) + 1, r = evalCode(n.code || ''); const s = { k: 'E', n: K, K, ...r }; s.res = gateOk(s, K) ? 'ok' : (s.t >= needT(K) && s.ic >= GATE.ic ? 'warn' : 'fail');
      if (!n.steps.some(x => x.k === 'I')) n.steps.push({ k: 'I', ok: true, note: ['人工实现', 'Implemented by hand'] }); n.steps.push(s);
      ev(tp.id, [`人工检验 E${K}（${n.id}）：t ${s.t.toFixed(2)} / 需 ${needT(K).toFixed(2)}`, `Human test E${K} (${n.id}): t ${s.t.toFixed(2)} vs ${needT(K).toFixed(2)}`]); S.wb.busy = false; render(); }, 1100); },
  hold: () => { const { tp, n } = wbNode(); const e = lastE(n); const vt = +(e.t * .76).toFixed(2); n.steps.push({ k: 'V', ic: +(e.ic * .78).toFixed(3), t: vt, res: vt >= GATE.holdT ? 'ok' : 'fail' }); ev(tp.id, [`封存验证（${n.id}）：t ${vt}`, `Sealed validation (${n.id}): t ${vt}`]); render(); },
  submit: () => { const { tp, n } = wbNode(); n.status = 'submitted'; const id = 'C' + (CANDS.length + 1);
    CANDS.push({ id, topic: tp.id, node: n.id, by: 'human', status: 'pending', time: clock(), ai: [['行业内排序后再做市值中性化，市值暴露降至 0.05。', 'Size exposure falls to 0.05 after ranking within industry and neutralising size.'], ['与待审候选 C1 相关 0.66，接近重复线；建议与 C1 合并审查，择一入库。', 'Correlates 0.66 with pending C1, close to the duplicate line; review together with C1 and admit one.']], limits: [['人工分支使用的试验计入同一课题台账。', 'Trials from the human branch count in the same topic ledger.']] });
    n.steps.push({ k: 'D', txt: [`提交审查 → 候选 ${id}`, `Submitted → candidate ${id}`] }); ev(tp.id, [`人工分支 ${n.id} 提交候选 ${id}`, `Human branch ${n.id} submitted candidate ${id}`]); toast(t('已提交审查', 'Submitted for review')); render(); },
  handback: () => { const { tp, n } = wbNode(); n.status = 'returned'; n.steps.push({ k: 'D', txt: ['交回 Agent：作为研究决策的输入', 'Handed back: input for the decision Agent'] }); ev(tp.id, [`${n.id} 交回 Agent`, `${n.id} handed back to the Agent`]);
    setTimeout(() => { ev(tp.id, [`研究决策已接收 ${n.id}：结论并入课题记忆，下一步在预算内重新规划`, `Decision Agent received ${n.id}: findings merged into topic memory; replanning within budget`]); refresh(); }, 1500);
    toast(t('已交回 Agent', 'Handed back to the Agent')); S.page = 'ops'; S.sel = tp.id; S.node = n.id; render(); },
  archive: () => { const { tp, n } = wbNode(); n.status = 'archived'; ev(tp.id, [`${n.id} 已归档，试验记录保留`, `${n.id} archived; trial records kept`]); render(); },
  adopt: () => { const { n } = wbNode(); n.code = CODE.H2cS; S.wb.tool = 'impl'; S.wb.checks = null; S.wb.chat.push({ ai: true, txt: ['已写入草稿。你可以先校验，再决定是否运行检验。', 'Written to your draft. Check it first, then decide whether to run a test.'] }); render(); },
  ask: v => reply(v),
  cand: v => { S.rv.sel = v; S.rv.ack = false; render(); },
  ack: (v, el) => { S.rv.ack = el.checked; render(); },
  decide: v => { const c = CANDS.find(x => x.id === S.rv.sel); c.status = v; const { tp, n, e } = candParts(c);
    if (v === 'approved') { LIB.unshift({ n: n.title, src: c.by === 'human' ? 'human' : 'agent', cat: [c.topic === 'T2' ? '预期' : '量价', c.topic === 'T2' ? 'Expectations' : 'Price-volume'], ic: e.ic, t: e.t, to: c.topic === 'T2' ? .09 : .18, tr: 'ok', st: 'use', note: [`${c.id} · ${tp.id}/${n.id}`, `${c.id} · ${tp.id}/${n.id}`] }); n.status = 'approved'; if (!CANDS.some(x => x.topic === tp.id && x.status === 'pending')) tp.status = 'approved'; }
    ev(tp.id, [`${c.id} ${{ approved: '入库（研究用途）', returned: '退回补证', archived: '归档' }[v]}`, `${c.id} ${{ approved: 'admitted (research use)', returned: 'returned for evidence', archived: 'archived' }[v]}`]); S.rv.ack = false; toast(t('决定已记录', 'Decision recorded')); render(); },
  libf: v => { S.lib = v; render(); },
  sys: () => { S.sysOn = !S.sysOn; TOPICS.forEach(x => { if (!S.sysOn && x.status === 'run') x.status = 'paused'; else if (S.sysOn && x.status === 'paused') x.status = 'run'; }); ev('—', S.sysOn ? ['研究系统恢复运行', 'Research system resumed'] : ['研究系统已暂停：不再调度新动作，进行中的计算完成后停止', 'Research system paused: no new actions; running computations finish then stop']); render(); },
  pausetopic: () => { const tp = topic(S.sel); tp.status = tp.status === 'run' ? 'paused' : 'run'; ev(tp.id, tp.status === 'paused' ? ['课题暂停', 'Topic paused'] : ['课题继续', 'Topic resumed']); render(); },
  simtoggle: () => { S.sim.on = !S.sim.on; render(); }, simstep: () => { if (T2.status === 'paused') T2.status = 'run'; simStep(); },
  reset: () => { location.reload(); },
  grant: v => { const tp = topic(S.sel); if (v === 'yes') { tp.status = 'queued'; tp.act = ['已批准：将另建分钟数据计划，原日频结论不沿用', 'Approved: a new minute-data plan will be created; daily-scope results are not carried over']; } else { tp.status = 'run'; tp.act = ['按原日频范围继续：改用日内收盘集合竞价代理', 'Continuing in daily scope: using closing-auction proxy']; } ev(tp.id, v === 'yes' ? ['研究负责人批准扩展数据范围（新计划）', 'Lead approved scope extension (new plan)'] : ['研究负责人拒绝扩展，按原范围继续', 'Lead declined; continuing in original scope']); render(); },
  comment: () => { const tp = topic(S.sel); modal(t('给研究意见', 'Comment on research'), `${tp.id} · ${tx(tp.name)}`, `<div class="hint">${t('意见会作为研究决策下一步决策的输入并留痕；不会扩大授权、门槛或预算。', 'Comments become logged input to the decision Agent’s next decision; they do not widen authorisation, gates or budget.')}</div><label class="field full">${t('意见', 'Comment')}<textarea id="cmt">${t('优先检验 10 日持有期，换手更低。', 'Prioritise the 10-day horizon; lower turnover.')}</textarea></label>`, `<button class="btn" data-a="close">${t('取消', 'Cancel')}</button><button class="btn primary" data-a="sendcmt">${t('发送', 'Send')}</button>`); },
  sendcmt: () => { const tp = topic(S.sel), txt = $('#cmt').value.trim(); close(); ev(tp.id, [`人工意见：“${txt}”`, `Comment: “${txt}”`]); setTimeout(() => { ev(tp.id, ['研究决策已接收意见，作为下一步决策输入', 'Decision Agent received the comment as input to its next decision']); refresh(); }, 1400); render(); },
  auth: () => { const used = TOPICS.reduce((a, x) => a + trials(x), 0), dis = isLead() ? '' : 'disabled';
    modal(t('研究授权', 'Research authorisation'), t('因子研究系统 · 有效至 2026-11-30', 'Factor research system · valid to 2026-11-30'), `<div class="split" style="grid-template-columns:1fr 1fr 1fr">
    <div class="diff new"><b>${t('可自主执行', 'Autonomous')}</b><p>${t('修改实现；修订假设；开新分支；放弃分支；对达标候选申请一次封存验证；提交审查', 'Edit implementations; revise hypotheses; open or drop branches; one sealed validation per passing candidate; submit for review')}</p></div>
    <div class="diff"><b>${t('需要人确认', 'Needs a person')}</b><p>${t('扩展数据范围；修改门槛或成本假设；增加预算；新建课题', 'Extend data scope; change gates or cost assumptions; add budget; create topics')}</p></div>
    <div class="diff" style="background:var(--red-bg);border-color:#efd3da"><b>${t('不允许', 'Never')}</b><p>${t('批准入库；删除或修改试验记录；重复使用封存样本；用于交易', 'Admit factors; delete or edit trial records; reuse the sealed sample; trade')}</p></div></div>
    <div class="field-grid" style="margin-top:16px"><label class="field">${t('本月试验上限', 'Monthly trial cap')}<input ${dis} value="120"><small>${t('已用', 'Used')} ${used}</small></label><label class="field">${t('Token 预算', 'Token budget')}<input ${dis} value="1,000k"></label>
    <label class="field">${t('显著性校正', 'Significance correction')}<select ${dis}><option>${t('Bonferroni（按课题试验数）', 'Bonferroni (per-topic trials)')}</option><option>Holm</option><option>${t('BHY（错误发现率）', 'BHY (false discovery rate)')}</option></select></label><label class="field">${t('新颖性线', 'Novelty line')}<input ${dis} value="0.70"></label></div>`,
    `${isLead() ? '' : `<span class="subtle" style="margin-right:auto">${t('仅研究负责人可修改', 'Only the research lead can edit')}</span>`}<button class="btn" data-a="close">${t('关闭', 'Close')}</button><button class="btn primary" data-a="saveauth" ${dis}>${t('保存为新授权版本', 'Save as new version')}</button>`); },
  saveauth: () => { close(); ev('—', ['研究授权已更新为新版本', 'Authorisation saved as a new version']); toast(t('已保存，新授权只影响之后的动作', 'Saved; applies to future actions only')); render(); },
  newtopic: () => modal(t('新建研究课题', 'New research topic'), t('研究系统会在授权和预算内自主推进', 'The research system will proceed autonomously within authorisation and budget'), `<div class="field-grid">
    <label class="field full">${t('研究方向', 'Direction')}<input id="ntn" value="${t('机构调研密度与后续收益', 'Institutional site-visit intensity and returns')}"></label>
    <label class="field">${t('类型', 'Type')}<select><option>${t('新发现', 'Discovery')}</option><option>${t('复现', 'Replication')}</option></select></label><label class="field">${t('试验预算', 'Trial budget')}<input value="10"></label>
    <label class="field full">${t('数据范围', 'Data scope')}<input disabled value="${tx(SCOPE)}"></label>
    <label class="field full">${t('补充说明（可选）', 'Notes (optional)')}<textarea>${t('关注中小盘；避免与已有分析师因子重复。', 'Focus on mid/small caps; avoid overlap with existing analyst factors.')}</textarea></label></div>`, `<button class="btn" data-a="close">${t('取消', 'Cancel')}</button><button class="btn primary" data-a="mktopic">${t('创建', 'Create')}</button>`),
  mktopic: () => { const nm = $('#ntn').value.trim() || t('新课题', 'New topic'); const id = 'T' + (TOPICS.length + 1); TOPICS.push({ id, name: [nm, nm], kind: 'new', status: 'queued', budget: 10, tokens: 0, act: ['排队中：等待研究决策分配', 'Queued: awaiting the decision Agent'], nodes: [] }); close(); S.sel = id; S.node = null; S.page = 'ops'; ev(id, ['新建课题', 'Topic created']); render(); },
  exp: () => { ev('—', ['编排对照实验计划已提交，等待排期', 'Orchestration experiment plan submitted for scheduling']); toast(t('实验计划已提交', 'Plan submitted')); render(); },
  toast: v => toast({ dr: t('数据请求 DR-12：北向持股日度时点数据，数据资源模块处理中', 'Data request DR-12: daily PIT northbound holdings, in progress in Data Resources'), saved: t('已保存为新假设版本', 'Saved as a new hypothesis version') }[v] || v),
  close: () => close(), closebg: (v, el, e) => { if (e.target === el) close(); }
};
document.addEventListener('click', e => { const el = e.target.closest('[data-a]'); if (!el) return; const f = A[el.dataset.a]; if (!f) return; if (el.tagName === 'A') e.preventDefault(); if (el.dataset.a !== 'ack') e.stopPropagation(); f(el.dataset.v, el, e); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); if (e.key === 'Enter' && e.target.id === 'ask') reply('free'); });
document.addEventListener('input', e => { if (e.target.id === 'code') { const { n } = wbNode(); if (n) n.code = e.target.value; } });

render(); setTimeout(() => { if (S.sim.on) simStep(); simLoop(); }, 1500);
