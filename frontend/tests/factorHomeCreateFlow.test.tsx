import './domSetup.mjs';
import React from 'react';
import assert from 'node:assert/strict';
import test, {afterEach} from 'node:test';
import {render, fireEvent, cleanup, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {QuantFactorHomePage} from '../src/pages/institutional-workflow/QuantFactorHomePage';

Object.defineProperty(globalThis, 'sessionStorage', {value: window.sessionStorage, configurable: true});
window.requestAnimationFrame = (fn) => window.setTimeout(() => fn(0), 0);
window.cancelAnimationFrame = window.clearTimeout;
Object.defineProperty(globalThis, 'cancelAnimationFrame', {value: window.clearTimeout, configurable: true});
Object.defineProperty(globalThis, 'requestAnimationFrame', {value: (fn: FrameRequestCallback) => window.setTimeout(() => fn(0), 0), configurable: true});

const originalFetch = globalThis.fetch;
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  sessionStorage.clear();
  window.history.pushState({}, '', '/');
});

function login() {
  sessionStorage.setItem('svquant_quant_session', JSON.stringify({
    product: 'quant', token: 'test-token',
    user: {id: 7, username: 'quant_test'},
    org: {id: 3, code: 'dev', name_cn: '开发机构'},
    permissions: {quant: 'write'}, can_write: true, can_manage: true,
  }));
}

const oldTopic: any = {
  id: 't-old', project_id: 'p-old', project_name: '已有真实任务', view_id: 'rv-1',
  primary_holding_period: 1, max_trials: 8, max_sealed: 1, sealed_used: 0,
  status: 'active', dispatch_status: 'stopped', dispatch_stop_reason: 'budget_exhausted',
  pending_review: 0, sealed_passed: 0, sealed_running: 0, sealed_failed: 0, approved_count: 0,
  latest_outcome: 'failed', research_purpose: 'discovery', k: 2, branch_count: 1, trial_count: 2,
  development_start: '2022-01-01', development_end: '2024-12-31',
  validation_start: '2025-01-01', validation_end: '2025-12-31', created_at: '2026-11-01T00:00:00Z',
};
const oldLedger: any = {
  topic: oldTopic,
  branches: [{id: 'b-old', topic_id: 't-old', source: 'agent', status: 'active', hypothesis_version: 1, implementation_version: 2, display_label: 'H1', display_title: '旧假设', display_status: '未达标'}],
  trials: [{trial_no: 1, branch_id: 'b-old', kind: 'development', outcome: 'failed', executor: 'agent', created_at: '2026-11-02T00:00:00Z', returned_metrics: true}],
  k: 2, threshold: 2.2, threshold_next_if_counted: 2.4, next_trial_no: 3,
};

test('页面按钮路径：F0 响应丢失后重试复用任务与幂等键，不重复建项目/任务', async () => {
  login();
  window.history.pushState({}, '', '/quant/factor');
  const projectTopics = new Map<string, any[]>();
  const allTopics = [oldTopic];
  const f0Keys: string[] = [];
  let projectCreates = 0, topicCreates = 0, f0Calls = 0;

  globalThis.fetch = async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname;
    const method = (init?.method || 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    if (path.endsWith('/factor-workflow/topics') && method === 'GET') return Response.json({topics: allTopics});
    if (path.endsWith('/factor-workflow/overview')) return Response.json({counts: {sealed_used: 0}});
    if (path.endsWith('/factor-workflow/pending-review-count')) return Response.json({count: 0});
    if (path.endsWith('/factor-workflow/controls')) return Response.json({paused: false});
    if (path.endsWith('/factor-workflow/imports/svquant-existing/reference')) return Response.json({items: []});
    if (path.endsWith('/factor-workflow/topics/t-old/ledger')) return Response.json(oldLedger);
    if (path.endsWith('/factor-workflow/topics/t-old/f0-runs')) return Response.json({status: 'stopped', stop_reason: 'budget_exhausted'});
    if (path.endsWith('/detect/projects') && method === 'POST') {
      projectCreates += 1;
      assert.ok(body.id, '客户端必须先生成 projectId');
      return Response.json({project: {...body, id: body.id, config: body.config || {}}});
    }
    if (/\/detect\/projects\/[^/]+$/.test(path) && method === 'PUT') {
      return Response.json({project: body});
    }
    if (path.endsWith('/factor-workflow/published-view')) return Response.json({view_id: 'rv-1', release_ids: {}, view_manifest_sha256: 'm', contract_revision: 'c', as_of: '2026-11-09'});
    if (path.match(/\/factor-workflow\/projects\/[^/]+\/topics$/) && method === 'GET') {
      const pid = decodeURIComponent(path.split('/')[4]);
      return Response.json({topics: projectTopics.get(pid) || []});
    }
    if (path.match(/\/factor-workflow\/projects\/[^/]+\/topics$/) && method === 'POST') {
      const pid = decodeURIComponent(path.split('/')[4]);
      topicCreates += 1;
      const topic = {...oldTopic, id: 't-new', project_id: pid, project_name: '新挖掘任务', trial_count: 0, k: 0, dispatch_status: null, dispatch_stop_reason: null, latest_outcome: null};
      projectTopics.set(pid, [{id: 't-new', branch_id: 'b-new'}]);
      allTopics.push(topic);
      return Response.json({topic});
    }
    if (path.endsWith('/factor-workflow/topics/t-new/f0-runs')) return Response.json(null);
    if (path.endsWith('/factor-workflow/topics/t-new/ledger')) {
      const t = allTopics.find(x => x.id === 't-new');
      return Response.json({topic: t, branches: [{id: 'b-new', topic_id: 't-new', source: 'agent', status: 'active', hypothesis_version: 1, implementation_version: 1}], trials: [], k: 0, threshold: 2, threshold_next_if_counted: 2.2, next_trial_no: 1});
    }
    if (path.endsWith('/factor-workflow/topics/t-new/branches/b-new/f0') && method === 'POST') {
      f0Calls += 1;
      f0Keys.push(String(body.idempotency_key));
      if (f0Calls === 1) throw new Error('响应丢失');
      return Response.json({id: 'run-1', status: 'queued'});
    }
    throw Error('Unexpected ' + method + ' ' + path);
  };

  const view = render(<MemoryRouter initialEntries={['/quant/factor']}><QuantFactorHomePage/></MemoryRouter>);
  await waitFor(() => assert.ok(view.getByText('已有真实任务')));
  for (const label of ['研究准备','因子研发','独立验证','审批入库']) assert.ok(view.getAllByText(label).length > 0, label);
  assert.equal(view.queryByText(/AC-12/), null);
  assert.equal(view.queryByText(/CURRENT STAGE VIEW/), null);
  let posts = 0;
  const originalFetchForPosts = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    if ((init?.method || 'GET').toUpperCase() === 'POST') posts += 1;
    return originalFetchForPosts(input, init);
  };
  fireEvent.click(view.getByRole('button', {name: /因子研发/}));
  await waitFor(() => assert.ok(view.getAllByText(/当前第 2 版/).length > 0));
  assert.equal(posts, 0, '查看环节不能发执行请求');

  fireEvent.click(view.getByRole('button', {name: /＋ 启动挖掘/}));
  const launch = await view.findByRole('button', {name: '创建并启动'});
  fireEvent.click(launch);
  await waitFor(() => assert.ok(view.getByText(/启动请求失败/)), {timeout: 4000});
  assert.equal(projectCreates, 1);
  assert.equal(topicCreates, 1);
  assert.equal(f0Calls, 1);

  fireEvent.click(view.getByRole('button', {name: '创建并启动'}));
  await waitFor(() => assert.equal(f0Calls, 2), {timeout: 4000});
  await waitFor(() => assert.equal(view.queryByRole('dialog'), null));
  assert.equal(projectCreates, 1, '重试不得重复创建项目');
  assert.equal(topicCreates, 1, '重试不得重复创建挖掘任务');
  assert.equal(f0Keys[0], f0Keys[1], '重试必须复用同一 F0 幂等键');
});
