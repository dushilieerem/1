import './domSetup.mjs';import React from 'react';import test,{afterEach} from 'node:test';import assert from 'node:assert/strict';import {render,cleanup,waitFor} from '@testing-library/react';import {ResearchGateSummary,QuantFactorReportPage} from '../src/pages/institutional-workflow/QuantFactorReportPage';
test('报告门槛实际组件：结论与逐项值可读，四位显示保留原精度且null不转0',()=>{const view=render(<ResearchGateSummary gate={{passed:false,checks:[{name:'方向 NW t',actual:-.339123987,operator:'>=',threshold:1.9599639845400536,passed:false},{name:'有效IC观测数',actual:null,operator:'>=',threshold:60,passed:false,reason:'日度数据不足'}]}}/>);assert.ok(view.getByRole('heading',{name:'研发检验未通过'}));assert.ok(view.getByText('-0.3391'));assert.ok(view.getByText('门槛 >= 1.96'));assert.ok(view.getByTitle('1.9599639845400536'));assert.ok(view.getByText('无法计算 / 缺数据'));assert.ok(view.getByText('日度数据不足'));cleanup();});

import {MemoryRouter,Routes,Route} from 'react-router-dom';
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});const originalFetch=globalThis.fetch;afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();window.history.pushState({},'','/');});
test('报告返回研究页保留精确candidate及H分支，不默认另一候选',async()=>{
 const id='22222222-2222-4222-8222-222222222222',report='qf_'+id+'_development';window.history.pushState({},'','/quant/factor/report/'+report);sessionStorage.setItem('svquant_quant_session',JSON.stringify({product:'quant',token:'isolated',user:{id:5},org:{id:2},permissions:{quant:'write'}}));
 globalThis.fetch=async(input)=>{const path=new URL(String(input),'http://localhost').pathname;if(path.endsWith('/detect/runs/'+report))return Response.json({run:{id:report,projectId:'p',factorName:'f',description:'研究报告',request:{},result:{metrics:{},meta:{}}}});if(path.endsWith('/candidates/'+id))return Response.json({id,status:'development_failed',presentation:{branch_id:'h2',branch_label:'H2',trial_no:2},evidence:{development:{gate:{passed:false,checks:[]}}}});throw Error(path);};
 const view=render(<MemoryRouter initialEntries={['/quant/factor/report/'+report]}><Routes><Route path="/quant/factor/report/:runId" element={<QuantFactorReportPage/>}/></Routes></MemoryRouter>);await waitFor(()=>{const link=view.getByRole('link',{name:'返回研究任务 →'});assert.equal(link.getAttribute('href'),'/quant/factor/workflow/p/F4?candidate='+id+'&branch=h2');});
});

import {formatGateNumber} from '../src/lib/factorPresentation';
import {FactorNoveltyEvidence} from '../src/pages/institutional-workflow/FactorNoveltyEvidence';
test('因子门槛四有效位不改数值，缺值不转0；来源哈希默认折叠',()=>{
 assert.equal(formatGateNumber(.011636148341631875),'0.01164');assert.equal(formatGateNumber(2.2414027276049464),'2.241');assert.equal(formatGateNumber(0),'0');assert.equal(formatGateNumber(null),'无法计算 / 缺数据');const view=render(<FactorNoveltyEvidence evidence={{status:'deferred',reference_hash:'long-frozen-reference-hash',run_id:'original-run'}}/>);const fold=view.getByText('对照来源追溯').closest('details')!;assert.equal(fold.open,false);assert.ok(fold.textContent?.includes('long-frozen-reference-hash'));cleanup();
});
