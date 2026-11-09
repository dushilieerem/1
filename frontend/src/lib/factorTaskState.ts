/**
 * 挖掘任务真实业务状态与四环节映射。
 *
 * 只消费后端已持久化的事实（F0 运行状态/停止原因、研发试验、封存记录、
 * 复核请求、审批/登记标记），不用试验次数或当前页签冒充“阶段”。
 * 人工查看某环节只改 viewing，不改变这里返回的 currentStage。
 */

export type FactorTaskFacts = {
  status: string;
  dispatch_status?: string | null;
  dispatch_stop_reason?: string | null;
  latest_outcome?: string | null;
  trial_count: number;
  sealed_used?: number;
  sealed_passed?: number;
  sealed_running?: number;
  sealed_failed?: number;
  pending_review?: number;
  approved_count?: number;
  /** 仅当资产登记成功后端返回；没有契约前保持 undefined，不伪造已入库。 */
  registered_count?: number;
};

export type FactorTaskStateKey =
  | 'draft'
  | 'preparing'
  | 'running'
  | 'validating'
  | 'review'
  | 'review_ready'
  | 'approved_unregistered'
  | 'admitted'
  | 'ended'
  | 'error'
  | 'waiting'
  | 'paused';

export type StageId = 'prepare' | 'development' | 'validation' | 'approval';
export type StageStatus = 'done' | 'current' | 'todo';

export type StageView = { id: StageId; label: string; role: string; status: StageStatus };

export type FactorTaskState = {
  key: FactorTaskStateKey;
  label: string;
  tone: 'live' | 'warn' | 'bad' | 'ok' | 'gray';
  /** 真实当前环节；与用户正在查看的 stageView 无关。 */
  currentStage: StageId;
  stages: StageView[];
  /** 用户真正需要处理的事项；没有则明确说无需人工。 */
  needsYou: string;
};

const STAGES: Array<{ id: StageId; label: string; role: string }> = [
  { id: 'prepare', label: '研究准备', role: '研究准备 Agent' },
  { id: 'development', label: '因子研发', role: '因子研发 Agent' },
  { id: 'validation', label: '独立验证', role: '独立复核 Agent' },
  { id: 'approval', label: '审批入库', role: '成果管理 Agent · 人工审批' },
];

const STOP_WAIT = ['global_pause', 'locked_view_drift', 'service_unavailable', 'resource', 'waiting', '暂停全部', '负责人已暂停', '视图不一致', '服务不可用', '资源不足'];
const STOP_INTERRUPT = ['中断', '异常', '重启', 'failed', 'error', 'not json serializable', 'traceback', '崩溃'];
const STOP_BUDGET = ['budget_exhausted', '预算', 'budget'];

function stopReason(t: FactorTaskFacts): string {
  return String(t.dispatch_stop_reason || '').toLowerCase();
}

function inferArtifactStage(t: FactorTaskFacts): number {
  if ((t.approved_count || 0) > 0 || (t.pending_review || 0) > 0) return 3;
  if ((t.sealed_running || 0) > 0 || (t.sealed_passed || 0) > 0 || (t.sealed_failed || 0) > 0 || (t.sealed_used || 0) > 0) return 2;
  if ((t.trial_count || 0) > 0) return 1;
  return 0;
}

function stateStage(key: FactorTaskStateKey): number {
  switch (key) {
    case 'draft':
    case 'preparing':
      return 0;
    case 'running':
      return 1;
    case 'validating':
    case 'review_ready':
      return 2;
    case 'review':
    case 'approved_unregistered':
    case 'admitted':
      return 3;
    default:
      return 0;
  }
}

function buildStages(current: number, admitted: boolean): StageView[] {
  return STAGES.map((s, i) => ({
    ...s,
    status: i < current ? 'done' : i === current ? (admitted && s.id === 'approval' ? 'done' : 'current') : 'todo',
  }));
}

export function deriveFactorTaskState(t: FactorTaskFacts): FactorTaskState {
  const reason = stopReason(t);
  const dispatch = String(t.dispatch_status || '');
  let key: FactorTaskStateKey;
  let label: string;
  let tone: FactorTaskState['tone'] = 'gray';
  let needsYou = '当前无需人工处理，可继续观察。';

  if ((t.registered_count || 0) > 0) {
    key = 'admitted'; label = '已入库'; tone = 'ok';
    needsYou = '已完成审批并登记，可在因子库查看。';
  } else if ((t.approved_count || 0) > 0) {
    key = 'approved_unregistered'; label = '已批准 · 待登记'; tone = 'warn';
    needsYou = '审批已通过但尚未登记资产；登记成功前不显示已入库。';
  } else if ((t.pending_review || 0) > 0) {
    key = 'review'; label = '待人工审批'; tone = 'warn';
    needsYou = '等待独立复核人查看冻结证据并决定，研究员不能批准自己的成果。';
  } else if ((t.sealed_running || 0) > 0) {
    key = 'validating'; label = '独立验证中'; tone = 'live';
    needsYou = '封存验证正在执行；结果返回前不能送审或继续调参。';
  } else if (t.status === 'paused') {
    key = 'paused'; label = '已暂停'; tone = 'gray';
    needsYou = '完成人工操作后恢复研究；恢复不会补发已暂停的计算。';
  } else if (dispatch === 'error' || dispatch === 'failed') {
    key = 'error'; label = '服务异常'; tone = 'bad';
    needsYou = '可重试启动并保留原任务；连续异常请联系维护人员，技术原文见诊断详情。';
  } else if (dispatch === 'stopped') {
    if (STOP_WAIT.some((s) => reason.includes(s))) {
      key = 'waiting'; label = '等待计算服务'; tone = 'warn';
      needsYou = '已记录服务/授权缺口，暂不能继续验证；恢复后从原任务重试。';
    } else if (STOP_INTERRUPT.some((s) => reason.includes(s)) && (t.trial_count || 0) === 0) {
      key = 'error'; label = '启动未完成'; tone = 'bad';
      needsYou = '任务已创建但没有产生试验；可重试启动，身份与证据保留。';
    } else if (STOP_BUDGET.some((s) => reason.includes(s))) {
      key = 'ended'; label = '未达标，已结束'; tone = 'gray';
      needsYou = '预算已用尽，全部试验与报告保留；需要新预算须走新的授权计划。';
    } else if (t.latest_outcome === 'passed' || (t.sealed_passed || 0) > 0) {
      key = 'review_ready'; label = '待提交独立复核'; tone = 'warn';
      needsYou = '研发或封存已通过；请提交独立复核，不能由研究员自行批准。';
    } else if (t.latest_outcome === 'failed') {
      key = 'ended'; label = '未达标，已结束'; tone = 'gray';
      needsYou = '本轮未达标，证据已归档；可查看研究历程或经授权开启新计划。';
    } else {
      key = 'ended'; label = '已结束'; tone = 'gray';
      needsYou = '研究已停止，证据与报告保留；需要继续时由人工决定。';
    }
  } else if (dispatch === 'queued' || dispatch === 'running') {
    if ((t.trial_count || 0) === 0) {
      key = 'preparing'; label = '准备中'; tone = 'live';
      needsYou = '研究准备 Agent 正在建立首个可检验假设；页面不强制推进。';
    } else {
      key = 'running'; label = '研发运行中'; tone = 'live';
      needsYou = '因子研发 Agent 正在检验与迭代；可观察或到人工工作台接手。';
    }
  } else if ((t.sealed_passed || 0) > 0) {
    key = 'review_ready'; label = '待提交独立复核'; tone = 'warn';
    needsYou = '封存已通过；请提交独立复核，不能自行批准。';
  } else if ((t.trial_count || 0) > 0) {
    key = 'waiting'; label = '待人工处理'; tone = 'warn';
    needsYou = '当前没有自动运行；可查看研究历程、重试启动或到人工工作台接手。';
  } else {
    key = 'draft'; label = '待启动'; tone = 'gray';
    needsYou = '任务已保存但尚未启动；可启动挖掘，草稿不会自动产生计算。';
  }

  const current = Math.max(inferArtifactStage(t), stateStage(key));
  const currentStage = STAGES[current].id;
  return { key, label, tone, currentStage, stages: buildStages(current, key === 'admitted'), needsYou };
}
