'use strict';
/* 审查中心：五类待办统一入口，详情复用各模块页面 */
const P = { key: 'review', title: ['审查中心', 'Review centre'], tab: 'all', tabs: [['all'], ['factor'], ['strategy'], ['portfolio'], ['risk'], ['auth']], scope: 'mine' };
const WHO = { reviewer: ['复核人', 'Reviewer'], lead: ['投资负责人', 'Investment lead'] };
const STX = { pending: ['待处理', 'Pending', 'purple'], done: ['已处理', 'Done', 'green'], approved: ['已批准', 'Approved', 'green'], returned: ['已退回', 'Returned', 'amber'], archived: ['已归档', 'Archived', 'gray'] };
P.render = () => {
  const all = SV.reviews(), mine = all.filter(x => x.mine);
  const list = all.filter(x => (P.tab === 'all' || x.type === P.tab) && (P.scope === 'all' || x.mine));
  const cnt = k => all.filter(x => x.type === k && x.st === 'pending').length;
  return SV.head('REVIEW CENTRE', '审查中心', 'Review centre', '所有需要人决定的事项：候选复核、组合审批、风险恢复和授权申请。', 'Everything that needs a human decision: candidate reviews, portfolio approvals, risk recovery and authorisation requests.')
    + SV.tabs([['all', '全部', 'All', all.filter(x => x.st === 'pending').length], ['factor', '因子候选', 'Factors', cnt('factor')], ['strategy', '策略候选', 'Strategies', cnt('strategy')], ['portfolio', '组合审批', 'Portfolios', cnt('portfolio')], ['risk', '风险恢复', 'Risk recovery', cnt('risk')], ['auth', '授权申请', 'Authorisations', cnt('auth')]], P.tab)
    + SV.note(['<b>设计要点</b>：审查中心只做汇总和分派，决定在各模块的详情页里做，避免两套审批逻辑。谁能处理、能否自审由后端按身份判断；页面只显示结果。', '<b>Design</b>: the centre aggregates and routes; decisions happen on each module’s detail page so there is one approval logic. Who may act and the no-self-approval rule are enforced by the backend.'])
    + `<div class="filters"><button class="${P.scope === 'mine' ? 'on' : ''}" data-a="scope" data-v="mine">${t('待我处理', 'Assigned to me')} ${mine.length}</button><button class="${P.scope === 'all' ? 'on' : ''}" data-a="scope" data-v="all">${t('全部事项', 'All items')}</button></div>
    <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t('类型', 'Type')}</th><th>${t('事项', 'Item')}</th><th>${t('提交方', 'From')}</th><th>${t('等待', 'Waiting')}</th><th>${t('处理人', 'Handled by')}</th><th>${t('状态', 'Status')}</th><th></th></tr></thead><tbody>
    ${list.length ? list.map(x => `<tr><td>${SV.badge(SV.TYPES[x.type])}</td><td><b>${tx(x.obj)}</b></td><td>${tx(x.by)}</td><td>${x.st === 'pending' ? tx(x.wait) : '—'}</td><td>${tx(WHO[x.who])}</td><td>${SV.badge(STX[x.st] || STX.done)}</td><td><a class="btn small ${x.mine ? 'primary' : ''}" href="${x.href}">${x.mine ? t('去处理', 'Handle') : t('查看', 'View')} →</a></td></tr>`).join('')
      : `<tr><td colspan="7"><div class="empty"><b>${t('没有待你处理的事项', 'Nothing assigned to you')}</b>${SV.role === 'researcher' ? t('研究员不审批候选；切换到“全部事项”查看进度。', 'Researchers do not approve candidates; switch to All items to follow progress.') : ''}</div></td></tr>`}</tbody></table></div>
    <div class="card-footer"><small>${t('规则：提交人不能审批自己的事项；研究员不能复核候选；风险恢复需附复测证据', 'Rules: no self-approval; researchers cannot review candidates; risk recovery needs retest evidence')}</small></div></div>`;
};
P.A = { scope: v => { P.scope = v; SV.render(); } };
SV.boot(P);
