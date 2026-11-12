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

test('研发失败且仅有研究复盘：不进入审批，独立验证未开始', () => {
  const t = { ...base, dispatch_status: 'stopped', latest_outcome: 'failed', trial_count: 2, pending_feedback: 1 };
  const s = deriveFactorTaskState(t);
  assert.equal(s.key, 'ended');
  assert.match(s.label, /复盘/);
  assert.equal(s.currentStage, 'development');
  assert.equal(stage(t, 'validation'), 'todo');
  assert.equal(stage(t, 'approval'), 'todo');
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


test('已有研发试验后系统异常仍是运行异常，不写未达标结束',()=>{
 const state=deriveFactorTaskState({...base,trial_count:2,dispatch_status:'stopped',dispatch_stop_reason:'Connection timeout',latest_outcome:'failed'});
 assert.equal(state.key,'error');assert.equal(state.currentStage,'development');
});
test('研发达标但未封存不能显示可提交复核',()=>{
 const state=deriveFactorTaskState({...base,trial_count:1,dispatch_status:'stopped',latest_outcome:'passed'});
 assert.equal(state.label,'待独立验证');assert.equal(state.currentStage,'development');
});
test('第一次真实研发动作即进入研发，无需等待首条试验返回',()=>{
 const state=deriveFactorTaskState({...base,dispatch_status:'running',dispatch_action:'run_test'});
 assert.equal(state.key,'running');assert.equal(state.currentStage,'development');
});


test('独立验证真实动作不误标研发运行',()=>{
 const state=deriveFactorTaskState({...base,dispatch_status:'running',dispatch_action:'request_seal',trial_count:1});
 assert.equal(state.key,'validating');assert.equal(state.currentStage,'validation');
});
test('预算授权、全局暂停、数据版本等待按真实原因分别表达',()=>{
 assert.equal(deriveFactorTaskState({...base,dispatch_status:'stopped',dispatch_stop_reason:'预算不足，等待负责人授权'}).label,'等待负责人授权');
 assert.equal(deriveFactorTaskState({...base,dispatch_status:'stopped',dispatch_stop_reason:'global_pause'}).label,'等待恢复研究');
 assert.equal(deriveFactorTaskState({...base,dispatch_status:'stopped',dispatch_stop_reason:'locked_view_drift'}).label,'等待数据版本确认');
});


test('试验预算用尽不是等待授权：本任务已结束，续研需新任务',()=>{
 const t={...base,dispatch_status:'stopped',trial_count:5,latest_outcome:'failed',dispatch_stop_reason:'已用满 max_trials=5 且 remaining=0，预算不足，无法开展下一次新增市场检验。'};
 const s=deriveFactorTaskState(t);
 assert.equal(s.key,'ended');assert.equal(s.label,'未达标，已结束');assert.equal(s.currentStage,'development');assert.ok(!s.needsYou.includes('等待负责人授权'));
});

test('持续研究：排队显示等待运行，技术等待不等于市场未达标',()=>{
 assert.equal(deriveFactorTaskState({...base,dispatch_status:'queued'}).label,'等待运行');
 const waiting=deriveFactorTaskState({...base,dispatch_status:'stopped',dispatch_technical_wait:'execution_dependency',dispatch_stop_reason:'AiOutputTruncated',trial_count:1,latest_outcome:'failed'});
 assert.equal(waiting.key,'waiting');assert.equal(waiting.label,'等待处理');assert.equal(waiting.currentStage,'development');assert.ok(!waiting.needsYou.includes('未达标'));
});


test('技术等待按真实原因区分，不再统一写研究暂遇技术条件限制',()=>{
 const baseWait={...base,dispatch_status:'stopped',trial_count:0};
 const method=deriveFactorTaskState({...baseWait,dispatch_technical_wait:'execution_dependency',dispatch_stop_reason:'原运行的研究方法与当前已加载版本不同；不能静默恢复'});
 assert.equal(method.label,'等待新方法运行');assert.ok(!method.needsYou.includes('技术条件限制'));
 const contract=deriveFactorTaskState({...baseWait,dispatch_technical_wait:'execution_dependency',dispatch_stop_reason:'研究契约或所选父E/H已变化，旧提案未执行'});
 assert.equal(contract.label,'等待重新规划');
 const proposal=deriveFactorTaskState({...baseWait,dispatch_technical_wait:'execution_dependency',dispatch_stop_reason:'研究提案结构或引用校验失败：提案引用了非本轮待处理建议'});
 assert.equal(proposal.label,'等待修订提案');
 const paused=deriveFactorTaskState({...baseWait,dispatch_technical_wait:'execution_dependency',dispatch_stop_reason:'研究已暂停或由人工接手，迟到建议保留'});
 assert.equal(paused.label,'已暂停');
 const checkpoint=deriveFactorTaskState({...baseWait,dispatch_technical_wait:'interrupted_checkpoint',dispatch_stop_reason:'原物理调用结果待确认；不会重新发送'});
 assert.equal(checkpoint.label,'等待处理');assert.match(checkpoint.needsYou,/检查点/);
});


test('旧模型调用次数限制显示已停用，而不是笼统技术条件限制',()=>{
 const s=deriveFactorTaskState({...base,dispatch_status:'stopped',dispatch_technical_wait:'execution_dependency',dispatch_stop_reason:'今日账号模型调用次数已达上限，未预留新请求'});
 assert.equal(s.label,'旧调用配额已停用');assert.match(s.needsYou,/重新启动研究/);assert.ok(!s.needsYou.includes('技术条件限制'));
});


test('实现与假设窗口不一致显示实现需修订，而不是运行异常',()=>{
 const s=deriveFactorTaskState({...base,dispatch_status:'stopped',dispatch_stop_reason:'冻结研究假设写的是 5 日，实际实现代码是 1 日；请修订实现或建立新的研究分支'});
 assert.equal(s.label,'实现需修订');assert.match(s.needsYou,/退回修订/);assert.notEqual(s.label,'运行异常');
});
