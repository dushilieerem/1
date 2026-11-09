import assert from 'node:assert/strict';
import test from 'node:test';
import { deriveFactorTaskState, type FactorTaskFacts } from '../src/lib/factorTaskState.ts';

const base: FactorTaskFacts = {
  status: 'active',
  dispatch_status: null,
  latest_outcome: null,
  trial_count: 0,
  sealed_used: 0,
  sealed_passed: 0,
  sealed_running: 0,
  sealed_failed: 0,
  pending_review: 0,
  approved_count: 0,
};

const stage = (t: FactorTaskFacts, id: string) => deriveFactorTaskState(t).stages.find((s) => s.id === id)?.status;

test('草稿：未启动，研究准备当前，不被写成已进入研发', () => {
  const s = deriveFactorTaskState({ ...base });
  assert.equal(s.key, 'draft');
  assert.equal(s.currentStage, 'prepare');
  assert.equal(stage(base, 'prepare'), 'current');
  assert.equal(stage(base, 'development'), 'todo');
});

test('准备中：F0 已排队但还没有试验', () => {
  const t = { ...base, dispatch_status: 'queued' };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'preparing');
  assert.equal(s.currentStage, 'prepare');
  assert.equal(stage(t, 'development'), 'todo');
});

test('研发运行：已有试验且 F0 正在运行', () => {
  const t = { ...base, dispatch_status: 'running', trial_count: 2 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'running');
  assert.equal(s.currentStage, 'development');
  assert.equal(stage(t, 'prepare'), 'done');
  assert.equal(stage(t, 'development'), 'current');
});

test('独立验证中：封存任务在途', () => {
  const t = { ...base, dispatch_status: 'stopped', trial_count: 3, sealed_used: 1, sealed_running: 1 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'validating');
  assert.equal(s.currentStage, 'validation');
  assert.equal(stage(t, 'development'), 'done');
  assert.equal(stage(t, 'validation'), 'current');
});

test('待人工审批：pending_review 进入审批入库，独立验证已完成', () => {
  const t = { ...base, dispatch_status: 'stopped', trial_count: 3, sealed_used: 1, sealed_passed: 1, pending_review: 1 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'review');
  assert.equal(s.currentStage, 'approval');
  assert.equal(stage(t, 'validation'), 'done');
  assert.equal(stage(t, 'approval'), 'current');
});

test('已入库：必须同时有登记成功事实，仅有审批通过不算', () => {
  const approved = { ...base, status: 'archived', trial_count: 3, sealed_used: 1, sealed_passed: 1, approved_count: 1 };
  const pendingRegistration = deriveFactorTaskState(approved);
  assert.equal(pendingRegistration.key, 'approved_unregistered');
  assert.notEqual(pendingRegistration.label, '已入库');
  assert.equal(stage(approved, 'approval'), 'current');

  const registered = deriveFactorTaskState({ ...approved, registered_count: 1 });
  assert.equal(registered.key, 'admitted');
  assert.equal(registered.label, '已入库');
  assert.equal(stage({ ...approved, registered_count: 1 }, 'approval'), 'done');
});

test('未达标结束：预算耗尽且最终试验未通过', () => {
  const t = { ...base, dispatch_status: 'stopped', dispatch_stop_reason: 'budget_exhausted', trial_count: 8, latest_outcome: 'failed' };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'ended');
  assert.equal(s.label, '未达标，已结束');
  assert.equal(s.currentStage, 'development');
});

test('服务异常：F0 失败时给出异常状态和重试入口依据', () => {
  const t = { ...base, dispatch_status: 'error', dispatch_stop_reason: '模型服务异常' };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'error');
  assert.equal(s.label, '服务异常');
  assert.match(s.needsYou, /重试/);
});

test('等待：全局暂停/视图漂移不等于研究失败', () => {
  const t = { ...base, dispatch_status: 'stopped', dispatch_stop_reason: 'global_pause', trial_count: 2 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'waiting');
  assert.match(s.label, /等待/);
});

test('真实中文全局暂停原因映射为等待，不误报未达标', () => {
  const t = { ...base, dispatch_status: 'stopped', dispatch_stop_reason: '研究负责人已暂停全部：不启动新的自动研究动作', trial_count: 1 };
  assert.equal(deriveFactorTaskState(t).key, 'waiting');
});

test('真实序列化异常映射为服务异常，不误报未达标结束', () => {
  const t = { ...base, dispatch_status: 'stopped', dispatch_stop_reason: 'Object of type datetime is not JSON serializable' };
  assert.equal(deriveFactorTaskState(t).key, 'error');
});

test('暂停：人工暂停有独立状态，不冒充运行', () => {
  const t = { ...base, status: 'paused', dispatch_status: 'running', trial_count: 2 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'paused');
  assert.equal(s.label, '已暂停');
});

test('封存通过但未提交复核：验证环节当前，不是已进入审批', () => {
  const t = { ...base, dispatch_status: 'stopped', trial_count: 2, sealed_used: 1, sealed_passed: 1 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'review_ready');
  assert.equal(s.currentStage, 'validation');
  assert.equal(stage(t, 'approval'), 'todo');
});
