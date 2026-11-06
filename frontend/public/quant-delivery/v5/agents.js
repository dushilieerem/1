'use strict';
/* Agent 管理：只读 + 暂停开关（评测与发布在完善期） */
const U = [
  ['F0', '研究决策（因子）', 'Research decision (factor)', 'agent', 'factor', 'v2', 186, 412, 1.6, '16:08'], ['F1', '起点检索', 'Starting-point search', 'unit', 'factor', 'v3', 58, 61, 0, '15:51'],
  ['F2', '假设研究', 'Hypothesis research', 'sub', 'factor', 'v5', 41, 233, 2.4, '15:52'], ['F3', '因子实现', 'Factor implementation', 'sub', 'factor', 'v4', 77, 198, 3.9, '16:02'],
  ['F4', '检验诊断', 'Testing & diagnosis', 'unit', 'factor', 'v2', 64, 122, 0, '16:05'], ['F5', '独立复核', 'Independent review', 'indep', 'factor', 'v1', 9, 54, 0, '10:41'], ['F6', '因子卡与入库', 'Factor card', 'unit', 'factor', 'v2', 6, 12, 0, '10:42'],
  ['S0', '研究决策（策略）', 'Research decision (strategy)', 'agent', 'strategy', 'v1', 14, 61, 0, '16:09'], ['S1', '因子选择', 'Factor selection', 'unit', 'strategy', 'v1', 9, 14, 0, '15:30'], ['S2', '配方构造', 'Recipe builder', 'unit', 'strategy', 'v1', 12, 18, 0, '16:09'],
  ['S3', '回测与诊断', 'Backtest & diagnosis', 'unit', 'strategy', 'v1', 11, 40, 9.1, '16:09'], ['S4', '稳健性检验', 'Robustness', 'unit', 'strategy', 'v1', 6, 9, 0, '15:12'], ['S5', '独立复核', 'Independent review', 'indep', 'strategy', 'v1', 2, 15, 0, '06:12'],
  ['R1', '事件说明', 'Event explainer', 'unit', 'risk', 'v1', 7, 6, 0, '15:43'], ['A1', '研究助手', 'Research assistant', 'unit', 'all', 'v3', 133, 157, .8, '16:11']
];
const FORM = { agent: ['Agent · 决策', 'Agent · decides', 'purple'], sub: ['子 Agent', 'Sub-agent', 'blue'], unit: ['单次调用', 'Single call', 'gray'], indep: ['独立 Agent', 'Independent', 'amber'] };
const MOD = { factor: ['因子工厂', 'Factor factory', 'factor.html'], strategy: ['策略研究', 'Strategy research', 'strategy.html'], risk: ['运行与风险', 'Operations & risk', 'risk.html'], all: ['各模块', 'All modules', 'index.html'] };
const P = { key: 'agents', title: ['Agent 管理', 'Agents'], tab: 'list', tabs: [['list']], sel: null };
const paused = id => !!SV.flag('pause_' + id);
P.render = () => {
  const lead = SV.role === 'lead', tok = U.reduce((a, u) => a + u[7], 0), calls = U.reduce((a, u) => a + u[6], 0), sel = U.find(u => u[0] === P.sel);
  return SV.head('AGENTS', 'Agent 管理', 'Agents', '查看各 Agent 的方法版本、调用、用量与失败率；必要时暂停。', 'Method versions, calls, usage and failure rates of every agent; pause one when needed.')
    + SV.note(['<b>设计要点</b>：本期只读加暂停开关。暂停研究决策 Agent（F0 / S0）后，对应课题不再自动推进，人工工具和研究助手仍可用。评测集、方法发布与回退放到完善期。', '<b>Design</b>: read-only plus a pause switch. Pausing a decision agent (F0/S0) stops automatic progress on its topics; manual tools and the assistant keep working. Evals and method releases come later.'])
    + `<div class="metrics">${[[t('Agent / 能力单元', 'Agents / units'), U.length], [t('本月调用', 'Calls this month'), calls], [t('本月 Token', 'Tokens this month'), tok + 'k'], [t('已暂停', 'Paused'), U.filter(u => paused(u[0])).length]].map(([a, b]) => `<div class="stat"><span>${a}</span><b>${b}</b></div>`).join('')}</div>
    <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('单元', 'Unit')}</th><th>${t('形态', 'Form')}</th><th>${t('模块', 'Module')}</th><th>${t('方法版本', 'Method version')}</th><th>${t('本月调用', 'Calls')}</th><th>Token</th><th>${t('失败率', 'Failure rate')}</th><th>${t('最近运行', 'Last run')}</th><th>${t('运行', 'Enabled')}</th></tr></thead><tbody>
    ${U.map(u => `<tr data-a="sel" data-v="${u[0]}" style="cursor:pointer"><td><b>${u[0]} · ${t(u[1], u[2])}</b>${paused(u[0]) ? `<small class="warn-t">${t('已暂停', 'Paused')}</small>` : ''}</td><td>${SV.badge(FORM[u[3]])}</td><td><a href="${MOD[u[4]][2]}">${t(MOD[u[4]][0], MOD[u[4]][1])}</a></td><td class="mono">${t('提示词', 'prompt')} ${u[5]}</td><td>${u[6]}</td><td>${u[7]}k</td><td class="${u[8] > 5 ? 'warn-t' : ''}">${u[8]}%</td><td class="mono">${u[9]}</td>
    <td><button class="toggle ${paused(u[0]) ? '' : 'on'}" data-a="pause" data-v="${u[0]}" ${lead ? '' : 'disabled'} aria-label="${t('运行开关', 'Enabled')}"></button></td></tr>`).join('')}</tbody></table></div>
    <div class="card-footer"><small>${lead ? t('暂停只影响之后的自动动作；进行中的计算完成后停止', 'Pausing affects future automatic actions; running computations finish first') : t('仅投资负责人可暂停', 'Only the investment lead can pause')}</small></div></div>
    ${sel ? `<div class="drawer"><h3>${sel[0]} · ${t(sel[1], sel[2])}</h3><div class="kv" style="margin-top:8px"><span>${t('方法版本', 'Method version')}</span><b>${t('提示词', 'Prompt')} ${sel[5]} · ${t('机构默认模型', 'Institution default model')} · ${t('工具清单', 'Tool list')} ${sel[5]}</b><span>${t('输入 / 输出', 'Input / output')}</span><b>${t('结构化 JSON，程序校验后执行', 'Structured JSON, validated by code before execution')}</b><span>${t('失败说明', 'Failures')}</span><b>${sel[8] > 5 ? t('主要为 RE 回测超时，已自动重试', 'Mostly RE backtest timeouts, retried automatically') : t('无异常', 'Normal')}</b><span>${t('评测', 'Evaluation')}</span><b>${t('完善期提供：评测集、得分、版本发布与回退', 'Later: eval sets, scores, releases and rollback')}</b></div></div>` : ''}`;
};
P.A = { sel: v => { P.sel = P.sel === v ? null : v; SV.render(); }, pause: v => { const now = !paused(v); SV.flag('pause_' + v, now); SV.log('agents', [`${v} ${now ? '已暂停' : '已恢复'}`, `${v} ${now ? 'paused' : 'resumed'}`]); SV.toast(now ? t(`${v} 已暂停：相关课题不再自动推进`, `${v} paused: its topics stop advancing automatically`) : t(`${v} 已恢复`, `${v} resumed`)); SV.render(); } };
SV.boot(P);
