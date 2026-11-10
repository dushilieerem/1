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
  dispatch_technical_wait?: string | null;
  latest_outcome?: string | null;
  dispatch_action?: string | null;
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
const STOP_INTERRUPT = ['中断', '异常', '重启', 'failed', 'error', 'not json serializable', 'traceback', '崩溃', 'timeout', 'connection', 'unavailable'];
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
  } else if ((t.sealed_running || 0) > 0 || (dispatch === 'running' && t.dispatch_action === 'request_seal')) {
    key = 'validating'; label = '独立验证中'; tone = 'live';
    needsYou = '封存验证正在执行；结果返回前不能送审或继续调参。';
  } else if (t.status === 'paused') {
    key = 'paused'; label = '已暂停'; tone = 'gray';
    needsYou = '完成人工操作后恢复研究；恢复不会补发已暂停的计算。';
  } else if (t.dispatch_technical_wait && dispatch !== 'running' && dispatch !== 'queued') {
    key='waiting';label='等待处理';tone='warn';
    needsYou='研究暂遇技术条件限制，已有数据范围、结果和次数保留；核对后继续，不代表研究结论不成立。';
  } else if (dispatch === 'error' || dispatch === 'failed') {
    key = 'error'; label = '服务异常'; tone = 'bad';
    needsYou = '可重试启动并保留原任务；连续异常请联系维护人员，技术原文见诊断详情。';
  } else if (dispatch === 'stopped') {
    if (['authorization','授权','额度不足','预算不足'].some(s=>reason.includes(s))) {
      key = 'waiting'; label = '等待负责人授权'; tone = 'warn';
      needsYou = '当前范围或预算不足；由负责人处理授权后再继续，已有记录保留。';
    } else if (STOP_WAIT.some((s) => reason.includes(s))) {
      key = 'waiting'; label = '等待计算服务'; tone = 'warn';
      needsYou = '所需数据或计算条件尚未恢复；已有记录保留，恢复后从原任务继续。';
      if(['global_pause','暂停全部','负责人已暂停'].some(s=>reason.includes(s))){label='等待恢复研究';needsYou='负责人已暂停自动研究；恢复前不启动新动作，在途证据保留。';}
      if(['locked_view_drift','视图不一致'].some(s=>reason.includes(s))){label='等待数据版本确认';needsYou='任务数据版本与当前发布版本不一致；请由负责人核对，不能自动替换固定数据。';}
    } else if (STOP_INTERRUPT.some((s) => reason.includes(s))) {
      key = 'error'; label = '运行异常'; tone = 'bad';
      needsYou = '本次运行因服务异常中断；已有试验保留，可重试或人工接手，诊断详情保留技术原因。';
    } else if (STOP_BUDGET.some((s) => reason.includes(s))) {
      key = 'ended'; label = '未达标，已结束'; tone = 'gray';
      needsYou = '预算已用尽，全部试验与报告保留；需要新预算须走新的授权计划。';
    } else if ((t.sealed_passed || 0) > 0) {
      key = 'review_ready'; label = '待提交独立复核'; tone = 'warn';
      needsYou = '研发或封存已通过；请提交独立复核，不能由研究员自行批准。';
    } else if (t.latest_outcome === 'passed') {
      key = 'waiting'; label = '待独立验证'; tone = 'warn';
      needsYou = '研发检验已通过，尚无通过的封存验证；请查看验证要求，不能直接审批。';
    } else if (t.latest_outcome === 'failed') {
      key = 'ended'; label = '未达标，已结束'; tone = 'gray';
      needsYou = '本轮未达标，证据已归档；可查看研究历程或经授权开启新计划。';
    } else {
      key = 'ended'; label = '已结束'; tone = 'gray';
      needsYou = '研究已停止，证据与报告保留；需要继续时由人工决定。';
    }
  } else if (dispatch === 'queued' || dispatch === 'running') {
    if (dispatch === 'queued') {
      key = 'preparing'; label = '等待运行'; tone = 'live';
      needsYou = '启动请求已接受，等待执行；可查看范围与预算。';
    } else if (!t.dispatch_action && (t.trial_count || 0) === 0) {
      key = 'preparing'; label = '研究准备中'; tone = 'live';
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

  const actionStage = t.dispatch_action === 'request_seal' ? 2 : ['run_test','revise','pivot'].includes(t.dispatch_action || '') ? 1 : 0;
  const current = Math.max(inferArtifactStage(t), stateStage(key), actionStage);
  const currentStage = STAGES[current].id;
  return { key, label, tone, currentStage, stages: buildStages(current, key === 'admitted'), needsYou };
}
