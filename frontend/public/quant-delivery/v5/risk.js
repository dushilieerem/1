'use strict';
/* 运行与风险（交互原型，场景数据） */
const SEV = { 3: ['严重', 'Severe', 's3'], 2: ['警告', 'Warning', 's2'], 1: ['提示', 'Info', 's1'] };
const EST = { open: ['待确认', 'To acknowledge', 'red'], ack: ['处置中', 'Handling', 'amber'], resolved: ['已恢复', 'Recovered', 'green'], auto: ['已自动解除', 'Auto-cleared', 'gray'] };
const EVENTS = () => [
  { id: 'E-31', sev: 3, obj: ['组合 PF-1（模拟）', 'Portfolio PF-1 (simulated)'], txt: ['单日亏损 -2.3%，越过阈值 -2.0%', 'Daily loss -2.3%, beyond the -2.0% limit'], at: '11-05 15:42', st: SV.e31(),
    ev: [[t('规则', 'Rule'), t('单日亏损 ≤ -2.0% · 风险规则 v3', 'Daily loss ≤ -2.0% · risk rules v3')], [t('观测值', 'Observed'), '-2.31%（PF-1 v2，2026-11-05）'], [t('主要来源', 'Main source'), t('ST-01 贡献 -1.9%：电子行业单日下跌 4.1%', 'ST-01 contributed -1.9%: electronics fell 4.1% that day')], [t('数据视图', 'Data view'), 'r20261105'], [t('自动措施', 'Automatic action'), t('暂停 PF-1 新调仓（只影响模拟）', 'Paused PF-1 rebalancing (simulation only)')]] },
  { id: 'E-30', sev: 2, obj: ['数据视图', 'Data view'], txt: ['r20261105 发布延迟 38 分钟（阈值 30 分钟）', 'r20261105 published 38 min late (limit 30)'], at: '11-05 18:58', st: 'auto', ev: [[t('规则', 'Rule'), t('数据延迟 > 30 分钟', 'Data delay > 30 min')], [t('处理', 'Handling'), t('发布完成后自动解除；当日组合运行使用新视图', 'Cleared on publish; the day’s run used the new view')]] },
  { id: 'E-29', sev: 1, obj: ['因子课题 T2', 'Factor topic T2'], txt: ['回测任务超时，自动重试成功', 'Backtest timed out; retry succeeded'], at: '11-05 11:20', st: 'auto', ev: [[t('规则', 'Rule'), t('任务失败连续 2 次告警；本次 1 次', 'Alert after 2 consecutive failures; this was 1')]] },
  { id: 'E-27', sev: 2, obj: ['组合 PF-1（模拟）', 'Portfolio PF-1 (simulated)'], txt: ['单票权重 3.2%，超过 3%', 'Single name at 3.2%, above 3%'], at: '10-28 15:40', st: 'resolved', ev: [[t('处理', 'Handling'), t('下一次调仓降至 1.8%，复测通过后恢复', 'Cut to 1.8% at the next rebalance; recovered after retest')]] }
];
const RULES = [
  ['单日亏损', 'Daily loss', '≤ -2.0%', 3, ['暂停新调仓', 'Pause rebalancing']], ['最大回撤（自启动）', 'Max drawdown (since start)', '≤ -8.0%', 3, ['暂停新调仓', 'Pause rebalancing']],
  ['单票权重', 'Single-name weight', '> 3%', 2, ['告警', 'Alert']], ['数据视图延迟', 'Data view delay', '> 30 分钟', 2, ['告警', 'Alert']], ['任务失败', 'Task failure', '连续 2 次', 2, ['告警', 'Alert']]
];
const CHECKS = [['组合风险', 'Portfolio risk', '每个交易日 15:40', 'Trading days 15:40', '11-06 15:40', 'ok'], ['数据视图更新', 'Data view update', '每日 18:30', 'Daily 18:30', '11-05 18:30', 'ok'], ['任务健康', 'Task health', '每 10 分钟', 'Every 10 min', '11-06 16:10', 'ok'], ['Agent 用量与失败率', 'Agent usage & failures', '每小时', 'Hourly', '11-06 16:00', 'ok']];
const P = { key: 'risk', title: ['运行与风险', 'Operations & risk'], tab: 'events', tabs: [['events'], ['checks'], ['rules'], ['attrib']], sel: 'E-31', tasks: SV.flag('tasks') || [] };

function timeline(st) {
  const s = ['open', 'ack', 'resolved'].indexOf(st);
  const items = [['11-05 15:42', t('触发：组合风险巡检发现越线', 'Triggered by the portfolio risk check'), 0], ['11-05 15:42', t('自动暂停 PF-1 新调仓', 'PF-1 rebalancing auto-paused'), 0], [SV.flag('E31ack') || '—', t('确认收到（风控负责人）', 'Acknowledged (risk owner)'), 1], [SV.flag('E31res') || '—', t('提交复测证据并恢复调仓', 'Retest evidence submitted, rebalancing resumed'), 2]];
  return `<ul class="timeline">${items.map(([tm, x, k]) => `<li class="${k < s || (k === 0) || (k === s && st === 'resolved') ? 'done' : k === s ? 'now' : 'todo-s'}"><time>${tm}</time>${x}</li>`).join('')}</ul>`;
}
function pageEvents() {
  const es = EVENTS(), e = es.find(x => x.id === P.sel), lead = SV.role === 'lead';
  let act = '';
  if (e.id === 'E-31') {
    if (e.st === 'open') act = `<button class="btn primary" data-a="ack" ${lead ? '' : 'disabled'}>${t('确认收到', 'Acknowledge')}</button>${lead ? '' : `<span class="subtle">${t('由风控负责人处理（本期由投资负责人担任）', 'Handled by the risk owner (the investment lead this release)')}</span>`}`;
    else if (e.st === 'ack') act = `<div style="flex:1"><label class="field">${t('复测证据（必填）', 'Retest evidence (required)')}<textarea id="evd" placeholder="${t('例如：已将 ST-01 权重降至 40%（PF-1 v3 已批准）；按新权重重算 11-05 单日亏损为 -1.6%，低于阈值。', 'e.g. ST-01 cut to 40% (PF-1 v3 approved); recomputed 11-05 loss is -1.6%, inside the limit.')}"></textarea></label>
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center"><button class="btn primary" data-a="resolve" ${lead ? '' : 'disabled'}>${t('提交证据并恢复调仓', 'Submit evidence and resume')}</button><small>${SV.pfv3() === 'approved' ? t('PF-1 v3 已批准，可引用为处置措施', 'PF-1 v3 is approved and can be cited') : t('提示：PF-1 v3（降低 ST-01 权重）仍待审批', 'Note: PF-1 v3 (lower ST-01) still awaits approval')}</small></div></div>`;
    else act = `<span class="ok-t">${t('已恢复：下一交易日恢复生成订单意图', 'Recovered: order intents resume next trading day')}</span>`;
  }
  return SV.note(['<b>设计要点</b>：巡检在服务端定时运行，越线产生带证据的事件；严重事件按规则自动暂停相关模拟组合。“确认收到”和“解除风险”是两步：恢复必须附复测证据，全程留痕。', '<b>Design</b>: checks run on the server; breaches create events with evidence and severe ones auto-pause the simulated portfolio. Acknowledging and recovering are separate steps; recovery needs retest evidence and everything is logged.'])
    + `<div class="rv-grid" style="grid-template-columns:330px minmax(0,1fr)"><div class="queue">${es.map(x => `<button class="qi ${x.id === P.sel ? 'sel' : ''}" data-a="sel" data-v="${x.id}"><span class="mono">${x.id} · ${x.at}</span> <span class="sev ${SEV[x.sev][2]}">${tx(SEV[x.sev])}</span><b>${tx(x.txt)}</b><small>${tx(x.obj)} · ${tx(EST[x.st])}</small></button>`).join('')}</div>
    <div class="card"><div class="card-head"><div><h2>${e.id} · ${tx(e.txt)}</h2><p>${tx(e.obj)} · ${e.at}</p></div>${SV.badge(EST[e.st])}</div><div class="card-body"><div class="grid2"><div><h3 style="margin-bottom:8px">${t('证据', 'Evidence')}</h3><div class="kv">${e.ev.map(([a, b]) => `<span>${a}</span><b style="font-weight:500">${b}</b>`).join('')}</div></div>
    <div>${e.id === 'E-31' ? `<h3 style="margin-bottom:8px">${t('处置过程', 'Handling')}</h3>${timeline(e.st)}` : ''}</div></div></div>
    <div class="card-footer" style="align-items:flex-start">${act || '<span></span>'}<button class="btn small" data-a="task" data-v="${e.id}">${t('创建改进任务', 'Create improvement task')}</button></div></div></div>`;
}
function pageChecks() {
  return `<div class="hint">${t('巡检由服务端定时任务执行，关闭页面不影响运行；每次运行写入记录，越线时生成事件。', 'Checks are server-side scheduled jobs and run with every page closed; each run is logged and breaches create events.')}</div>
  <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('巡检', 'Check')}</th><th>${t('频率', 'Schedule')}</th><th>${t('上次运行', 'Last run')}</th><th>${t('结果', 'Result')}</th><th>${t('本月运行 / 产生事件', 'Runs / events this month')}</th></tr></thead><tbody>
  ${CHECKS.map((c, i) => `<tr><td><b>${t(c[0], c[1])}</b></td><td>${t(c[2], c[3])}</td><td class="mono">${c[4]}</td><td>${SV.badge(i === 0 && SV.pfPaused() ? ['有未解除事件', 'Open event', 'amber'] : ['正常', 'OK', 'green'])}</td><td>${[[4, 2], [6, 1], [870, 1], [146, 0]][i].join(' / ')}</td></tr>`).join('')}</tbody></table></div></div>`;
}
function pageRules() {
  const lead = SV.role === 'lead';
  return `<div class="card"><div class="card-head"><div><h2>${t('风险规则 v3', 'Risk rules v3')}</h2><p>${t('生效于 10-20 · 由投资负责人维护 · 修改即生成新版本，只影响之后的巡检', 'Effective 10-20 · maintained by the investment lead · edits create a new version for future checks only')}</p></div><span class="badge amber">${t('演示默认值，需按机构政策校准', 'Demo defaults — calibrate to policy')}</span></div>
  <div class="table-wrap"><table class="table"><thead><tr><th>${t('规则', 'Rule')}</th><th>${t('阈值', 'Threshold')}</th><th>${t('等级', 'Severity')}</th><th>${t('越线后', 'On breach')}</th><th>${t('适用', 'Applies to')}</th></tr></thead><tbody>
  ${RULES.map((r, i) => `<tr><td><b>${t(r[0], r[1])}</b></td><td>${lead ? `<input class="wt" style="width:96px;border:1px solid #e4deea;border-radius:5px;padding:4px 6px" value="${r[2]}" data-rule="${i}">` : r[2]}</td><td><span class="sev ${SEV[r[3]][2]}">${tx(SEV[r[3]])}</span></td><td>${tx(r[4])}</td><td>${i < 3 ? t('模拟组合', 'Simulated portfolios') : t('数据与任务', 'Data and jobs')}</td></tr>`).join('')}</tbody></table></div>
  <div class="card-footer"><small>${t('历史版本：v1（08-12）、v2（09-15）、v3（10-20）', 'History: v1 (08-12), v2 (09-15), v3 (10-20)')}</small><button class="btn primary small" data-a="saverules" ${lead ? '' : 'disabled'}>${t('保存为 v4', 'Save as v4')}</button></div></div>`;
}
function pageAttrib() {
  const rows = [['ST-01 量价反转增强', 'ST-01 reversal', -0.6, '#c98a97'], ['ST-02 盈余漂移低换手', 'ST-02 earnings drift', 1.3, '#8e6bb0'], [t('交易成本（模拟）', 'Trading cost (sim)'), 'Trading cost (sim)', -0.2, '#c98a97'], [t('残差（权重漂移、现金）', 'Residual (drift, cash)'), 'Residual', 0.1, '#b9b0c2']];
  const tot = rows.reduce((a, r) => a + r[2], 0), m = 1.6;
  return SV.note(['<b>设计要点</b>：本期归因按策略拆分组合超额，加上成本和残差，合计必须等于组合超额。发现问题可以直接创建改进任务，回到因子或策略课题。', '<b>Design</b>: attribution splits portfolio excess by strategy plus cost and residual, which must add up. Problems become improvement tasks routed back to factor or strategy topics.'])
    + `<div class="grid-side"><div class="card"><div class="card-head"><div><h2>${t('PF-1 近 20 个交易日超额归因', 'PF-1 excess attribution, last 20 trading days')}</h2><p>${t('组合超额', 'Portfolio excess')} ${tot >= 0 ? '+' : ''}${tot.toFixed(1)}% = ${t('各项合计', 'sum of parts')}</p></div></div><div class="card-body"><div class="contrib">
    ${rows.map(r => `<div class="cr"><span>${L === 'en' ? r[1] : r[0]}</span><div class="track"><i style="left:${r[2] >= 0 ? 50 : 50 + r[2] / m * 50}%;width:${Math.abs(r[2]) / m * 50}%;background:${r[3]}"></i><i style="left:50%;width:1px;background:#bbb"></i></div><b style="text-align:right">${r[2] >= 0 ? '+' : ''}${r[2].toFixed(1)}%</b></div>`).join('')}
    <div class="cr" style="border-top:1px solid var(--line);padding-top:8px"><b>${t('合计', 'Total')}</b><span></span><b style="text-align:right">${tot >= 0 ? '+' : ''}${tot.toFixed(1)}%</b></div></div>
    <div class="hint" style="margin:14px 0 0">${t('ST-01 的负贡献集中在 11-05（电子行业下跌）。反转策略在行业单边行情中容易集中暴露。', 'ST-01’s loss is concentrated on 11-05 (electronics sell-off): reversal strategies concentrate exposure in one-way sector moves.')}</div></div>
    <div class="card-footer"><small>${t('复杂归因（Brinson、风险模型）在完善期提供', 'Brinson / risk-model attribution comes later')}</small><button class="btn small primary" data-a="task" data-v="ATTR">${t('创建改进任务', 'Create improvement task')}</button></div></div>
    <div class="card"><div class="card-head"><h2>${t('改进任务', 'Improvement tasks')}</h2></div><div class="card-body">${P.tasks.length ? P.tasks.map(x => `<div class="rowi"><span class="mono">${x.id}</span><div class="grow">${x.txt}<small>${x.to} · ${x.own}</small></div><a class="text-btn" href="${x.href}">${t('打开', 'Open')} →</a></div>`).join('') : `<div class="empty">${t('暂无。可从事件或归因创建。', 'None yet. Create one from an event or attribution.')}</div>`}</div></div></div>`;
}
P.render = () => SV.head('OPERATIONS & RISK', '运行与风险', 'Operations & risk', '服务端巡检数据、任务和模拟组合；越线时自动处理并通知负责人。', 'Server-side checks on data, jobs and simulated portfolios; breaches are handled automatically and routed to owners.')
  + (SV.openSevere() ? `<div class="status-strip warning"><span class="status-icon">!</span><div class="status-main"><b>${t('1 个严重事件未解除', '1 severe event open')}</b><p>${t('E-31 · PF-1 新调仓已暂停', 'E-31 · PF-1 rebalancing paused')}</p></div></div>` : '')
  + SV.tabs([['events', '事件', 'Events', EVENTS().filter(e => e.st === 'open' || e.st === 'ack').length], ['checks', '巡检', 'Checks'], ['rules', '风险规则', 'Risk rules'], ['attrib', '归因与复盘', 'Attribution']], P.tab)
  + { events: pageEvents, checks: pageChecks, rules: pageRules, attrib: pageAttrib }[P.tab]();
P.A = {
  sel: v => { P.sel = v; SV.render(); },
  ack: () => { SV.flag('E31', 'ack'); SV.flag('E31ack', '11-06 ' + clock().slice(0, 5)); SV.log('risk', ['E-31 已确认收到', 'E-31 acknowledged']); SV.toast(t('已确认收到；组合仍保持暂停，直到提交复测证据', 'Acknowledged; the portfolio stays paused until retest evidence is submitted')); SV.render(); },
  resolve: () => { const x = ($('#evd') || {}).value || ''; if (x.trim().length < 10) { SV.toast(t('请填写复测证据（至少 10 个字）', 'Please enter retest evidence (at least 10 characters)')); return; } SV.flag('E31', 'resolved'); SV.flag('E31res', '11-06 ' + clock().slice(0, 5)); SV.log('risk', ['E-31 已恢复，附复测证据', 'E-31 recovered with retest evidence']); SV.toast(t('已恢复：PF-1 下一交易日恢复调仓', 'Recovered: PF-1 resumes next trading day')); SV.render(); },
  saverules: () => { SV.log('risk', ['风险规则保存为 v4', 'Risk rules saved as v4']); SV.toast(t('已保存为 v4：只影响之后的巡检', 'Saved as v4: applies to future checks only')); },
  task: v => SV.modal(t('创建改进任务', 'Create improvement task'), v === 'ATTR' ? t('来源：PF-1 归因', 'Source: PF-1 attribution') : t(`来源：事件 ${v}`, `Source: event ${v}`), `<div class="field-grid"><label class="field full">${t('任务', 'Task')}<input id="tk" value="${t('ST-01 加行业上限，降低单边行业行情下的集中暴露', 'Add an industry cap to ST-01 to limit one-way sector exposure')}"></label><label class="field">${t('指派到', 'Route to')}<select id="tkto"><option value="strategy.html#ops">${t('策略研究 · ST-01 来源课题', 'Strategy · ST-01 source topic')}</option><option value="factor.html#ops">${t('因子工厂 · 5 日反转', 'Factor factory · 5-day reversal')}</option></select></label><label class="field">${t('负责人', 'Owner')}<select id="tkown"><option>${t('张新迪', 'Zhang Xindi')}</option></select></label><label class="field full">${t('验收标准', 'Acceptance')}<textarea>${t('在相同成本下，加行业上限后的版本信息比率不低于原版本，最大行业暴露 ≤ 20%；走完封存与复核。', 'At the same cost, the capped version keeps IR at least as high and max industry exposure ≤ 20%; passes sealed validation and review.')}</textarea></label></div>`, `<button class="btn" data-a="close">${t('取消', 'Cancel')}</button><button class="btn primary" data-a="mktask">${t('创建', 'Create')}</button>`),
  mktask: () => { const sel = $('#tkto'); P.tasks.unshift({ id: 'IT-' + (P.tasks.length + 7), txt: esc($('#tk').value), to: sel.options[sel.selectedIndex].text, own: $('#tkown').value, href: sel.value }); SV.flag('tasks', P.tasks); SV.close(); SV.log('risk', ['创建改进任务，已指派到研究模块', 'Improvement task created and routed']); P.tab = 'attrib'; SV.toast(t('任务已创建，会出现在对应模块的待办里', 'Task created; it appears in the module’s to-do list')); SV.render(); }
};
SV.boot(P);
