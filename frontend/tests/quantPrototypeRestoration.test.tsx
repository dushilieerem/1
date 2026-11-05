import './domSetup.mjs';
import React from 'react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {FactorWorkflowPage} from '../src/pages/institutional-workflow/FactorWorkflowPage';
import {setQuantSession} from '../src/lib/quantAuth';
import {FactorResearchParameters} from '../src/pages/institutional-workflow/FactorResearchParameters';
import test,{afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
import {cleanup,render,waitFor,fireEvent} from '@testing-library/react';
import {FactorStageAgent} from '../src/pages/institutional-workflow/FactorStageAgent';
import {formatResearchNumber} from '../src/pages/institutional-workflow/QuantFactorReportPage';
const root=new URL('../',import.meta.url),originalFetch=globalThis.fetch;
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
function login(){window.history.replaceState({},'', '/quant/factor');setQuantSession({token:'test-double',product:'quant',user:{id:71,username:'test'},org:{id:21,code:'test',name_cn:'测试'},permissions:{quant:'write'}});}
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();window.history.replaceState({},'', '/');});
function prototype(file:string){return new JSDOM(readFileSync(new URL(file,root),'utf8'),{url:'http://localhost/quant-delivery/prototype-module.html',runScripts:'dangerously',beforeParse(w){w.scrollTo=()=>{};w.requestAnimationFrame=fn=>w.setTimeout(()=>fn(0),0);w.ResizeObserver=class{observe(){}disconnect(){}} as any;}});}
test('all undeveloped module stages retain the accepted prototype forms, tools and Agent panel',()=>{
 const baseline=prototype('../docs/模块设计/量化机构端/index.html'),embedded=prototype('public/quant-delivery/prototype-module.html');
 try{for(const [module,prefix] of [['data','D'],['strategy','S'],['portfolio','P'],['monitor','T']])for(let i=1;i<=6;i++){
  const snapshots=[baseline,embedded].map(dom=>{dom.window.location.hash=module+'/'+prefix+i;dom.window.dispatchEvent(new dom.window.HashChangeEvent('hashchange'));const main=dom.window.document.querySelector('#main-content')!;return {heading:main.querySelector('h1')?.textContent,fields:[...main.querySelectorAll('#stage-form input,#stage-form textarea,#stage-form select')].map(n=>n.id),buttons:[...main.querySelectorAll('#stage-form button')].map(n=>n.textContent),agent:main.querySelector('#agent-panel')?.textContent};});
  assert.deepEqual(snapshots[1],snapshots[0],module+'/'+prefix+i);assert.ok(snapshots[1].fields.length>0,module+'/'+prefix+i+' has working form');assert.match(snapshots[1].agent||'',/AI/);
 }}finally{baseline.window.close();embedded.window.close();}
});
test('review and Agent configuration preserve full interaction content and preview identity',()=>{
 const dom=prototype('public/quant-delivery/prototype-module.html');try{for(const page of ['review','agents']){dom.window.location.hash=page;dom.window.dispatchEvent(new dom.window.HashChangeEvent('hashchange'));const main=dom.window.document.querySelector('#main-content')!;assert.ok(main.querySelectorAll('button').length>8,page);assert.match(main.textContent||'',/场景/);}assert.ok(dom.window.document.getElementById('quant-embedded-style'));assert.ok(dom.window.document.getElementById('quant-embedded-bridge'));assert.match(dom.serialize(),/sunvalley.workflow.prototype.v3.20261104.embedded/);}finally{dom.window.close();}
});
test('active factor screens do not embed personal SVQuant page components',()=>{
 for(const file of ['FactorWorkflowPage.tsx','QuantFactorLibraryPage.tsx','QuantFactorReportPage.tsx','QuantFactorReportsPage.tsx']){const source=readFileSync(new URL('src/pages/institutional-workflow/'+file,root),'utf8');assert.doesNotMatch(source,/import[^\n]*(?:FactorDetectPage|FactorDetectReportPage|FactorLibraryPage).*from\s+['"]@\/pages\//);}
 const app=readFileSync(new URL('src/App.tsx',root),'utf8');assert.match(app,/path="\/quant\/strategy" element={<QuantPrototypeModulePage/);assert.doesNotMatch(app,/QuantModulePendingPage/);
});
const draft={title:'',direction:'量价特征',question:'',background:''};
const ready={id:'job1',stage:'F1',status:'ready',input:{draft},output:{fields:{title:'研究任务',direction:'量价',question:'可验证的研究问题',background:'限制'},model:'test-double'},events:[{at:'2026-11-04T00:00:00Z',action:'fields_ready',message:'字段校验通过'}]};
test('completed Agent task restores fields without another model request',async()=>{
 let calls=0,applied:any;globalThis.fetch=async(_u,i)=>{calls++;assert.equal(i?.method,undefined);return Response.json({job:ready});};const v=render(<FactorStageAgent stage="F1" draft={draft} autoStart onApply={x=>applied=x}/>);await waitFor(()=>assert.deepEqual(applied,ready.output.fields));assert.ok(v.getByText('Agent 已填写左侧表单，可检查、编辑并保存。'));assert.equal(calls,1);
});
test('human edits take precedence over resumed Agent output',async()=>{
 let applied:any;globalThis.fetch=async()=>Response.json({job:ready});const v=render(<FactorStageAgent stage="F1" draft={{...draft,title:'人工任务'}} onApply={x=>applied=x}/>);await waitFor(()=>assert.ok(v.getByRole('button',{name:'采用 Agent 结果'})));assert.equal(applied,undefined);fireEvent.click(v.getByRole('button',{name:'采用 Agent 结果'}));assert.deepEqual(applied,ready.output.fields);
});
test('first empty F1 form starts one background job and reports real queued state',async()=>{
 const posts:any[]=[];globalThis.fetch=async(_u,i)=>{if(i?.method==='POST'){posts.push(JSON.parse(String(i.body)));return Response.json({...ready,status:'queued',output:null,events:[{at:'2026-11-04T00:00:00Z',action:'queued',message:'已排队'}]});}return Response.json({job:null});};const v=render(<FactorStageAgent stage="F1" draft={draft} autoStart onApply={()=>assert.fail('no result yet')}/>);await waitFor(()=>assert.ok(v.getByText('等待执行')));assert.equal(posts.length,1);assert.deepEqual(posts[0].draft,draft);assert.ok(v.getByRole('button',{name:'人工接管'}));
});
test('missing and invalid report metrics are never rendered as zero',()=>{assert.equal(formatResearchNumber(null),'未返回');assert.equal(formatResearchNumber(undefined),'未返回');assert.equal(formatResearchNumber(NaN),'未返回');assert.equal(formatResearchNumber(0),'0');assert.equal(formatResearchNumber(.1,true),'10.00%');});

test('restored saved Agent fields are recognised without overwriting them or reporting a conflict',async()=>{
 let calls=0;globalThis.fetch=async()=>Response.json(ready);const v=render(<FactorStageAgent stage="F1" draft={ready.output.fields} resumeJobId="job1" onApply={()=>calls++}/>);
 await waitFor(()=>assert.ok(v.getByText('Agent 已填写左侧表单，可检查、编辑并保存。')));assert.equal(calls,0);assert.equal(v.queryByRole('button',{name:'采用 Agent 结果'}),null);
});
const projectFixture=()=>({id:'form-project',name:'test research',factorName:'custom_combo',description:'hypothesis',createdAt:'2026-11-04',updatedAt:'2026-11-04',config:{universe:'CSI300',benchmark:'CSI300',portfolioType:'long_only',groups:5,rebalanceDays:5,executionTiming:'next_open',commissionRate:.0003,stampTax:.0005,slippageRate:.0001,filterSt:true,filterSuspended:true,filterLimitUp:true,filterLimitDown:true,factorCodes:[],weights:[],powers:[],researchPlan:{researchPurpose:'replication',revision:'r',hypothesis:'hypothesis',candidateExpression:'',target:'next day',frequency:'1d',developmentStart:'2024-01-02',developmentEnd:'2024-06-30',validationStart:'2024-07-01',validationEnd:'2024-12-31',acceptance:'predeclared',maxTrials:12,rules:{icMetric:'rank_ic',minSignedIc:.02,maxDrawdown:.3,minObservations:60,direction:'positive'}}}});
test('native date input is persisted and saved plan does not falsely remain dirty',async()=>{
 login();let project=projectFixture(),sent:any;globalThis.fetch=async(url,init)=>{if(String(url).includes('/agent-jobs'))return Response.json({job:null});if(init?.method==='PUT'){sent=JSON.parse(String(init.body));project=sent;return Response.json({project:{...sent,config:{...sent.config,researchPlan:Object.fromEntries(Object.entries(sent.config.researchPlan).reverse())}}});}return Response.json({projects:[project],project});};
 const v=render(<MemoryRouter initialEntries={['/quant/factor/workflow/form-project/F2']}><Routes><Route path="/quant/factor/workflow/:projectId/:step" element={<FactorWorkflowPage/>}/></Routes></MemoryRouter>);
 await waitFor(()=>assert.ok(v.getByLabelText('研发开始')));fireEvent.input(v.getByLabelText('研发开始'),{target:{value:'2024-02-01'}});fireEvent.click(v.getByRole('button',{name:'保存假设与验证计划'}));await waitFor(()=>assert.ok(v.getByText('研究假设与计划已保存。')));assert.equal(sent.config.researchPlan.developmentStart,'2024-02-01');assert.equal(v.queryByText('有未保存修改'),null);
});
test('manual research parameters use platform API and preserve the latest saved plan and implementation',async()=>{
 login();let saved:any;const original=projectFixture(),latest={...original,config:{...original.config,researchPlan:{...original.config.researchPlan,revision:'concurrent-plan'},draftFactor:{name:'kept',body:'def kept(): pass'}}};globalThis.fetch=async(_url,init)=>{if(init?.method==='PUT'){saved=JSON.parse(String(init.body));return Response.json({project:saved});}return Response.json({project:latest});};const v=render(<FactorResearchParameters project={original as any} onSaved={()=>{}} onDirty={()=>{}}/>);
 fireEvent.change(v.getByLabelText('单边佣金率（%）'),{target:{value:'0.06'}});fireEvent.click(v.getByRole('button',{name:'保存研发参数'}));await waitFor(()=>assert.ok(saved));assert.equal(saved.config.commissionRate,.0006);assert.equal(saved.config.researchPlan.revision,'concurrent-plan');assert.equal(saved.config.draftFactor.name,'kept');
});
