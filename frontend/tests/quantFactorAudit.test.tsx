import './domSetup.mjs';
import React from 'react';
import test,{afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {render,cleanup,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {FactorWorkflowPage} from '../src/pages/institutional-workflow/FactorWorkflowPage';
import {FactorEvidencePanel} from '../src/pages/institutional-workflow/FactorEvidencePanel';
import {FactorIterationPanel} from '../src/pages/institutional-workflow/FactorIterationPanel';
import {setQuantSession} from '../src/lib/quantAuth';
import {alignedCurves,relativeCurve,periodReturns,groupSeries,icStats,formatResearchNumber} from '../src/pages/institutional-workflow/factorReportData';
const originalFetch=globalThis.fetch;
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();window.history.replaceState({},'','/');});
function login(){window.history.replaceState({},'','/quant/factor');setQuantSession({token:'test-double',product:'quant',user:{id:71,username:'test'},org:{id:21,code:'test',name_cn:'测试'},permissions:{quant:'write'}});}
const plan={revision:'fixed',hypothesis:'h',candidateExpression:'',target:'1d',frequency:'1d',developmentStart:'2025-01-01',developmentEnd:'2025-06-30',validationStart:'2025-07-01',validationEnd:'2025-12-31',acceptance:'predefined',maxTrials:3,rules:{icMetric:'rank_ic',minSignedIc:.02,maxDrawdown:.3,minObservations:60,direction:'positive'}};
const project={id:'p',name:'test',factorName:'f',description:'h',config:{factorCodes:['f'],researchPlan:plan}};
const candidate={id:'c1',status:'development_failed',snapshot_hash:'sha',events:[],evidence:{development:{run_id:'r',gate:{passed:false,checks:[{name:'Rank IC',actual:.01,operator:'>=',threshold:.02,passed:false}]}}}};
test('saving an unchanged research plan preserves revision and existing evidence',async()=>{
 login();let writes=0;globalThis.fetch=async(url,init)=>{if(init?.method==='PUT'){writes++;return Response.json({project});}if(String(url).includes('agent-jobs'))return Response.json({job:null});if(String(url).endsWith('/candidates'))return Response.json({candidates:[candidate]});if(String(url).endsWith('/candidates/c1'))return Response.json(candidate);return Response.json({project,projects:[project]});};
 const v=render(<MemoryRouter initialEntries={['/quant/factor/workflow/p/F2']}><Routes><Route path="/quant/factor/workflow/:projectId/:step" element={<FactorWorkflowPage/>}/></Routes></MemoryRouter>);await waitFor(()=>assert.ok(v.getByRole('button',{name:'保存假设与验证计划'})));fireEvent.click(v.getByRole('button',{name:'保存假设与验证计划'}));await waitFor(()=>assert.ok(v.getByText('计划没有变化，保留原版本与已有证据。')));assert.equal(writes,0);assert.ok(v.getByText('条件未通过'));
});
test('F6 unsaved notes recover after navigating away and report dirty status',async()=>{
 login();globalThis.fetch=async url=>Response.json(String(url).endsWith('/libraries')?{libraries:[]}:String(url).endsWith('/candidates')?{candidates:[candidate]}:candidate);let dirty=false;
 const mount=()=>render(<MemoryRouter><FactorEvidencePanel projectId="p" step="F6" onDirty={v=>dirty=v}/></MemoryRouter>);const a=mount();await waitFor(()=>assert.ok(a.getByLabelText('研究结论与适用限制')));fireEvent.change(a.getByLabelText('研究结论与适用限制'),{target:{value:'my unsaved research note'}});await waitFor(()=>assert.equal(dirty,true));a.unmount();const b=mount();await waitFor(()=>assert.equal((b.getByLabelText('研究结论与适用限制') as HTMLTextAreaElement).value,'my unsaved research note'));
});
test('F5 explains why failed candidates cannot validate',async()=>{
 globalThis.fetch=async url=>Response.json(String(url).endsWith('/candidates')?{candidates:[candidate]}:candidate);const v=render(<MemoryRouter><FactorEvidencePanel projectId="p" step="F5"/></MemoryRouter>);await waitFor(()=>assert.ok(v.getByText(/研发硬门槛未通过/)));assert.equal((v.getByRole('button',{name:'运行冻结候选的样本外复验'}) as HTMLButtonElement).disabled,true);
});
test('benchmark series align by date with missing values preserved, never by index',()=>{
 const p=alignedCurves([{name:'portfolio',points:[{date:'2025-01-01',value:1},{date:'2025-01-03',value:1.1}]},{name:'baseline',points:[{date:'2025-01-02',value:1.05},{date:'2025-01-03',value:1.02}]}],true);
 assert.deepEqual(p.dates,['2025-01-01','2025-01-02','2025-01-03']);assert.equal(p.series[0].values[1],null);assert.equal(p.series[1].values[0],null);assert.equal(p.series[0].values[0],0);
});
test('relative performance uses matching-date NAV ratio, missing or zero benchmark stays missing',()=>{
 const p=relativeCurve([{date:'a',value:1.1},{date:'b',value:1.2},{date:'c',value:1.3}],[{date:'a',value:1.05},{date:'c',value:0}]);assert.equal(p[0].value,1.1/1.05);assert.equal(p[1].value,null);assert.equal(p[2].value,null);
});
test('monthly returns compound from previous month and retain data gaps',()=>{
 const r=periodReturns([{date:'2025-01-01',value:1},{date:'2025-01-31',value:1.1},{date:'2025-02-28',value:1.21},{date:'2025-03-31',value:null as any}]);assert.ok(Math.abs(r[1].value!-.1)<1e-9);assert.equal(r[2].value,null);
});
test('unused factor layers are omitted; groups and IC are never rendered as percentages',()=>{
 const p=groupSeries({factor_analysis:{cumulative_series:[{date:'d',layer1:1,layer2:1.1,layer3:null}] }},'baseline');assert.deepEqual(p.series.map(s=>s.name),['Q1','Q2','baseline']);assert.equal(formatResearchNumber(5),'5');assert.equal(formatResearchNumber(null),'未返回');assert.equal(icStats({factor_analysis:{ic_mean:.04,ic_std:.2,ic_series:[{date:'a',value:0},{date:'b',value:.1},{date:'c',value:null as any}]}}).positive,.5);
});
test('iteration starts with chosen bound and can be paused without automatic approval',async()=>{
 login();const calls:any[]=[];const run={id:'loop',status:'running',max_rounds:2,rounds:[],events:[{at:'2026-11-04',message:'真实计算中'}],stop_reason:''};globalThis.fetch=async(url,init)=>{if(init?.method==='POST'){calls.push({url:String(url),body:JSON.parse(String(init.body))});return Response.json(String(url).endsWith('/pause')?{...run,status:'paused',stop_reason:'人工暂停'}:run);}return Response.json({iteration:null});};let active=false;
 const v=render(<MemoryRouter><FactorIterationPanel projectId="p" maxTrials={3} onActive={v=>active=v}/></MemoryRouter>);await waitFor(()=>assert.equal((v.getByRole('button',{name:'开始自动迭代'}) as HTMLButtonElement).disabled,false));fireEvent.change(v.getByLabelText('本次最多迭代轮数'),{target:{value:'2'}});fireEvent.click(v.getByRole('button',{name:'开始自动迭代'}));await waitFor(()=>assert.equal(active,true));assert.deepEqual(calls[0].body,{max_rounds:2});fireEvent.click(v.getByRole('button',{name:'暂停并人工接管'}));await waitFor(()=>assert.ok(v.getByText('人工暂停')));assert.equal(active,false);assert.ok(calls[1].url.endsWith('/pause'));assert.equal(calls.length,2);
});
test('refresh restores the running iteration limit instead of showing a new default',async()=>{
 login();const run={id:'loop',status:'running',max_rounds:2,rounds:[],events:[],stop_reason:''};globalThis.fetch=async()=>Response.json({iteration:run});const v=render(<MemoryRouter><FactorIterationPanel projectId="p" maxTrials={12}/></MemoryRouter>);await waitFor(()=>assert.equal((v.getByLabelText('本次最多迭代轮数') as HTMLInputElement).value,'2'));assert.ok(v.getByText(/本任务固定上限 2 轮/));
});

test('a changed input is marked stale on earlier workflow steps, not shown as current passing evidence',async()=>{
 login();globalThis.fetch=async url=>{const u=String(url);return Response.json(u.includes('agent-jobs')?{job:null}:u.endsWith('/candidates')?{candidates:[candidate]}:u.endsWith('/candidates/c1')?{...candidate,stale:true}:{project,projects:[project]});};
 const v=render(<MemoryRouter initialEntries={['/quant/factor/workflow/p/F2']}><Routes><Route path="/quant/factor/workflow/:projectId/:step" element={<FactorWorkflowPage/>}/></Routes></MemoryRouter>);await waitFor(()=>assert.equal(v.getAllByText('输入已变更').length,2));assert.equal(v.queryByText('条件通过'),null);
});
