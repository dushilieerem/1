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
  window.history.pushState({}, '', '/quant/factor');
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
    if (method === 'GET' && /\/detect\/projects\/[^/]+$/.test(path)) return Response.json({project:{id:path.split('/').at(-1),name:'任务',config:{}}});
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
  await waitFor(() => assert.ok(view.getAllByText('已有真实任务')[0]));
  for (const label of ['研究准备','因子研发','独立验证','审批入库']) assert.ok(view.getAllByText(label).length > 0, label);
  assert.equal(view.queryByText(/AC-12/), null);
  assert.equal(view.queryByText(/CURRENT STAGE VIEW/), null);
  let posts = 0;
  const originalFetchForPosts = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    if ((init?.method || 'GET').toUpperCase() === 'POST') posts += 1;
    return originalFetchForPosts(input, init);
  };
  fireEvent.click(view.getByRole('button', {name: '查看因子研发'}));
  await waitFor(() => assert.ok(view.getAllByText(/当前第 2 版/).length > 0));
  assert.equal(posts, 0, '查看环节不能发执行请求');

  fireEvent.click(view.getByRole('button', {name: /＋ 启动挖掘/}));
  const launch = await view.findByRole('button', {name: '创建并启动'});
  fireEvent.change(view.getByText('试验预算').closest('label')!.querySelector('input')!,{target:{value:'2'}});
  fireEvent.click(launch);
  await waitFor(() => assert.ok(view.getByText(/启动请求失败/)), {timeout: 4000});
  assert.equal(projectCreates, 1);
  assert.equal(topicCreates, 1);
  assert.equal(f0Calls, 1);

  fireEvent.click(view.getByRole('button', {name: '重试启动'}));
  await waitFor(() => assert.equal(f0Calls, 2), {timeout: 4000});
  await waitFor(() => assert.ok(!view.queryByRole('dialog')));
  assert.equal(projectCreates, 1, '重试不得重复创建项目');
  assert.equal(topicCreates, 1, '重试不得重复创建挖掘任务');
  assert.equal(f0Keys[0], f0Keys[1], '重试必须复用同一 F0 幂等键');
});


type Scenario = {projectLoss?:boolean;topicLoss?:boolean;stopped?:boolean;refreshLoss?:boolean;finishedReplay?:boolean};
function scenario(options:Scenario={}){
 const topics:any[]=[];const projectIds:string[]=[];const topicProjects:string[]=[];const starts:string[]=[];
 const projects=new Map<string,any>();let loseProject=!!options.projectLoss,loseTopic=!!options.topicLoss,loseRefresh=!!options.refreshLoss;
 globalThis.fetch=async(input,init)=>{
  const path=new URL(String(input),'http://localhost').pathname;const method=init?.method||'GET';const body=init?.body?JSON.parse(String(init.body)):{};
  if(path.endsWith('/factor-workflow/topics')){if(loseRefresh&&starts.length){loseRefresh=false;return Response.json({detail:'refresh failed'},{status:503});}return Response.json({topics});}
  if(path.endsWith('/overview'))return Response.json({counts:{sealed_used:0}});
  if(path.endsWith('/pending-review-count'))return Response.json({count:0});
  if(path.endsWith('/controls'))return Response.json({paused:false});
  if(path.endsWith('/imports/svquant-existing/reference'))return Response.json({items:[]});
  if(path.endsWith('/published-view'))return Response.json({view_id:'rv-1',release_ids:{},as_of:'2026-11-09'});
  if(path.endsWith('/detect/projects')&&method==='POST'){
   projectIds.push(body.id);if(!projects.has(body.id))projects.set(body.id,body);
   if(loseProject){loseProject=false;throw Error('创建响应丢失');}
   return Response.json({project:projects.get(body.id)});
  }
  if(/\/detect\/projects\/[^/]+$/.test(path)){
   const id=path.split('/').at(-1)!;if(method==='PUT')projects.set(id,body);
   return Response.json({project:projects.get(id)});
  }
  if(/\/projects\/[^/]+\/topics$/.test(path)){
   const pid=path.split('/').at(-2)!;
   if(method==='POST'){
    topicProjects.push(pid);const id='task-'+topicProjects.length;
    topics.push({...oldTopic,id,project_id:pid,project_name:'草稿任务',max_trials:body.max_trials,trial_count:0,k:0,branch_count:1,dispatch_status:null,dispatch_stop_reason:null,latest_outcome:null});
    if(loseTopic){loseTopic=false;throw Error('任务响应丢失');}
    return Response.json({topic:topics.at(-1)});
   }
   return Response.json({topics:topics.filter(t=>t.project_id===pid)});
  }
  if(path.endsWith('/ledger')){
   const id=path.split('/').at(-2);const topic=topics.find(t=>t.id===id);
   return Response.json({topic,branches:[{id:'branch-'+id,topic_id:id,hypothesis_version:1,implementation_version:1,source:'manual',status:'active',display_title:'初始假设'}],trials:[],k:0,threshold:2,threshold_next_if_counted:2,next_trial_no:1});
  }
  if(path.endsWith('/f0-runs'))return Response.json(null);
  if(path.endsWith('/f0')&&method==='POST'){starts.push(body.idempotency_key);if(options.finishedReplay&&starts.length===1)throw Error('响应丢失');return Response.json({id:'run-scenario',status:options.stopped||options.finishedReplay?'stopped':'queued',rounds:options.finishedReplay?1:0});}
  throw Error('Unexpected '+method+' '+path);
 };
 return {topics,projectIds,topicProjects,starts,projects};
}
async function openNew(view:ReturnType<typeof render>){
 await waitFor(()=>assert.ok(view.getByText('还没有挖掘任务')));
 fireEvent.click(view.getByRole('button',{name:/＋ 启动挖掘/}));
 fireEvent.change(view.getByLabelText('试验预算'),{target:{value:'2'}});
}
test('独立页面草稿路径：只保存一个项目和任务，不启动；范围预算显示已保存限额',async()=>{
 login();const data=scenario();const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await openNew(view);fireEvent.click(view.getByRole('button',{name:'保存草稿'}));

 await waitFor(()=>assert.ok(!view.queryByRole('dialog')));
 assert.equal(data.projectIds.length,1);assert.equal(data.topicProjects.length,1);assert.equal(data.starts.length,0);
 assert.ok(view.getByText('草稿已保存，未启动研究。'));
 assert.equal(view.queryByRole('button',{name:'暂停任务'}),null);
 fireEvent.click(view.getByRole('button',{name:'范围与预算'}));
 assert.ok(view.getByRole('dialog',{name:'范围与预算'}));assert.ok(view.getByText('已计入 0 次 / 上限 2 次'));
 fireEvent.keyDown(view.getByRole('dialog'),{key:'Escape'});assert.ok(!view.queryByRole('dialog'));
});
for(const mode of ['projectLoss','topicLoss'] as const)test('页面创建响应丢失重试保留身份：'+mode,async()=>{
 login();const data=scenario({[mode]:true});const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await openNew(view);fireEvent.click(view.getByRole('button',{name:'创建并启动'}));
 await waitFor(()=>assert.ok(view.getByText(/响应丢失/)));
 fireEvent.click(view.getByRole('button',{name:'创建并启动'}));
 await waitFor(()=>assert.ok(!view.queryByRole('dialog')));
 assert.equal(new Set(data.projectIds).size,1);assert.equal(data.projects.size,1);assert.equal(data.topics.length,1);assert.equal(data.starts.length,1);
});
test('服务端拒绝调度时不把stopped响应声称启动成功',async()=>{
 login();const data=scenario({stopped:true});const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await openNew(view);fireEvent.click(view.getByRole('button',{name:'创建并启动'}));
 await waitFor(()=>assert.ok(view.getByText(/任务尚未运行/)));
 assert.ok(view.getByRole('dialog'));assert.equal(data.starts.length,1);assert.equal(view.queryByText(/已提交，等待排队/),null);
});
test('预算未配置时要求明确填写，不能默认发8次预算',async()=>{
 login();const data=scenario();const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByText('还没有挖掘任务')));fireEvent.click(view.getByRole('button',{name:/＋ 启动挖掘/}));
 assert.equal((view.getByLabelText('试验预算') as HTMLInputElement).value,'');
 fireEvent.click(view.getByRole('button',{name:'创建并启动'}));
 assert.ok(view.getByText('请明确填写本任务的试验预算。'));assert.equal(data.projectIds.length,0);
});


test('切换任务后丢弃前一任务的迟到台账及运行响应',async()=>{
 login();let resolveA!:(value:Response)=>void;
 const a={...oldTopic,id:'race-a',project_id:'p-a',project_name:'任务A',trial_count:0,dispatch_status:null};
 const b={...a,id:'race-b',project_id:'p-b',project_name:'任务B'};
 const ledger=(t:any)=>({topic:t,branches:[{id:'branch-'+t.id,hypothesis_version:1,implementation_version:1,source:'agent',hypothesis_text:t.id==='race-a'?'A的迟到假设':'B的当前假设'}],trials:[],k:0,threshold:2});
 globalThis.fetch=async(input)=>{
  const path=new URL(String(input),'http://localhost').pathname;
  if(path.endsWith('/topics'))return Response.json({topics:[a,b]});
  if(path.endsWith('/overview'))return Response.json({counts:{}});
  if(path.endsWith('/pending-review-count'))return Response.json({count:0});
  if(path.endsWith('/controls'))return Response.json({paused:false});
  if(path.endsWith('/race-a/ledger'))return new Promise<Response>(resolve=>{resolveA=resolve;});
  if(path.endsWith('/race-b/ledger'))return Response.json(ledger(b));
  if(path.endsWith('/race-a/f0-runs'))return Response.json({id:'old-a',status:'running',decision:{current_action:'request_seal'}});
  if(path.endsWith('/race-b/f0-runs'))return Response.json(null);
  if(path.includes('/detect/projects/'))return Response.json({project:{id:'p',config:{}}});
  throw Error(path);
 };
 const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await waitFor(()=>assert.ok(resolveA));fireEvent.click(view.getByRole('button',{name:/任务B/}));
 await waitFor(()=>assert.ok(view.getAllByText('B的当前假设')[0]));
 resolveA(Response.json(ledger(a)));await new Promise(resolve=>setTimeout(resolve,20));
 assert.equal(view.queryByText('A的迟到假设'),null);
 assert.ok(view.getAllByText('B的当前假设')[0]);
 assert.equal(view.getByRole('button',{name:/任务B/}).getAttribute('aria-current'),'true');
});


test('研发主区显示最新试验绑定的冻结定义，不随历史节点切换混用版本',async()=>{
 login();const data=scenario();data.topics.push({...oldTopic,id:'frozen-task',project_id:'frozen-project'});
 const baseFetch=globalThis.fetch;
 globalThis.fetch=async(input,init)=>{
  const path=new URL(String(input),'http://localhost').pathname;
  if(path.endsWith('/frozen-task/ledger'))return Response.json({topic:data.topics[0],branches:[
   {id:'older',display_title:'旧分支',hypothesis_version:1,implementation_version:1,source:'agent'},
   {id:'newer',display_title:'当前短标题',hypothesis_version:2,implementation_version:3,source:'agent'}
  ],trials:[{trial_no:2,branch_id:'newer',report_id:'qf_fixed-candidate_development',kind:'research',outcome:'failed'}],k:2,threshold:2});
  if(path.endsWith('/candidates/fixed-candidate'))return Response.json({snapshot:{name:'固定候选',plan:{hypothesis:'冻结假设正文'},request:{factor_name:'fixed_factor',factor_code:'def fixed_factor(data): return data.close'}}});
  return baseFetch(input,init);
 };
 const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByText('冻结假设正文')));
 assert.ok(view.getByText('def fixed_factor(data): return data.close'));
 assert.ok(view.getByText('当前短标题',{selector:'h3'}));
 fireEvent.click(view.container.querySelector('[data-bid=older]')!);
 assert.ok(view.getByText('冻结假设正文'));assert.ok(view.getByText('当前短标题',{selector:'h3'}));
});


test('启动已确认而列表刷新失败时，重试只读列表，不再启动',async()=>{
 login();const data=scenario({refreshLoss:true});const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await openNew(view);fireEvent.click(view.getByRole('button',{name:'创建并启动'}));
 await waitFor(()=>assert.ok(view.getByText(/列表更新失败/)));
 assert.equal(data.starts.length,1);fireEvent.click(view.getByRole('button',{name:'重试启动'}));
 await waitFor(()=>assert.ok(!view.queryByRole('dialog')));
 assert.equal(data.starts.length,1);assert.equal(data.topics.length,1);
});
test('启动响应丢失后重试返回已结束的原run，复用身份并显示结束结果',async()=>{
 login();const data=scenario({finishedReplay:true});const view=render(<MemoryRouter><QuantFactorHomePage/></MemoryRouter>);
 await openNew(view);fireEvent.click(view.getByRole('button',{name:'创建并启动'}));
 await waitFor(()=>assert.ok(view.getByText(/启动请求失败/)));
 fireEvent.click(view.getByRole('button',{name:'重试启动'}));
 await waitFor(()=>assert.ok(!view.queryByRole('dialog')));
 assert.equal(data.starts.length,2);assert.equal(data.starts[0],data.starts[1]);assert.ok(view.getByText('任务运行已结束，结果已保留。'));
});
