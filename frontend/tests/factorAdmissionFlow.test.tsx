import './domSetup.mjs';
import React from 'react';
import assert from 'node:assert/strict';
import test,{afterEach} from 'node:test';
import {render,fireEvent,cleanup,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {FactorReviewPage} from '../src/pages/institutional-workflow/FactorReviewPage';
import {QuantFactorLibraryPage} from '../src/pages/institutional-workflow/QuantFactorLibraryPage';
import {reuseResearchAsset,type ResearchAsset} from '../src/lib/factorResearchAssets';
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
const originalFetch=globalThis.fetch;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();window.history.pushState({},'','/');});
function login(permission='review'){
 window.history.pushState({},'','/quant/reviews/factors');sessionStorage.setItem('svquant_quant_session',JSON.stringify({product:'quant',token:'isolated-token',user:{id:9,username:'review-test'},org:{id:2,code:'dev'},permissions:{quant:permission},can_write:permission==='write',can_review:permission==='review'}));
}
const asset:any={id:'qfa_candidate',kind:'novel_factor',display_name:'已批准定义',version:1,category:'反转因子',tags:['日频'],hypothesis:'固定研究假设',snapshot_hash:'fixed-hash',purpose:'research_only',source_factor:{factor_name:'fixed_factor'},approval:{at:'2026-11-09T00:00:00Z'},definition:{factor_name:'fixed_factor',factor_code:'def fixed_factor(self): return self.close.shift(1)'},source_hash:'code',method:{},policy_version:'policy',k:1,threshold:1.96,data:{},development_report:{report_id:'development-fixed',metrics:{rank_ic:.03},gate:{passed:true,checks:[]}},sealed_report:{report_id:'sealed-fixed',passed:true,gate:{passed:true,checks:[]}},novelty_report:{gate:{expected_count:2,compared_count:2}}};
function reviewFixture(purpose='research_admission',author=false){
 let current:any={id:'candidate',status:'development_passed',snapshot_hash:'fixed-hash',snapshot:{name:'候选测试',plan:{hypothesis:'冻结研究假设',researchPurpose:'discovery'},request:{factor_name:'fixed_factor',factor_code:asset.definition.factor_code}},archive:{review:{status:'requested',purpose,question:'请核验'}},evidence:{development:{gate:{passed:true,checks:[]},novelty:{gate:{complete:true,passed:true}}}},sealed:{status:'passed'},trials:[],is_author:author,review_actions:{can_claim:!author,can_decide:false},admission:{allowed:!author,reason:author?'作者只读':''}};
 const decisions:any[]=[];let opinions=0;
 globalThis.fetch=async(input,init)=>{
  const path=new URL(String(input),'http://localhost').pathname;const method=init?.method||'GET';const body=init?.body?JSON.parse(String(init.body)):{};
  if(path.endsWith('/strategy-research/reviews'))return Response.json({branches:[]});
  if(path.endsWith('/factor-workflow/reviews')&&method==='GET')return Response.json({candidates:[{...current,name:'候选测试'}]});
  if(path.endsWith('/reviews/candidate/claim')){current.review_actions={can_claim:false,can_decide:true};return Response.json(current);}
  if(path.endsWith('/reviews/candidate/independent-opinion')){opinions++;const opinion={verdict:'support',rationale:'基于冻结证据的独立意见',limitations:[],generated_at:'2026-11-09'};current.archive.review.independent_opinion=opinion;return Response.json(opinion);}
  if(path.endsWith('/reviews/candidate')&&method==='GET')return Response.json(current);
  if(path.endsWith('/reviews/candidate')&&method==='POST'){decisions.push(body);current.archive.review={...current.archive.review,status:'reviewed',decision:body.decision,note:body.note};current.review_actions={can_claim:false,can_decide:false};if(body.decision==='approve_research_and_register')current.archive.research_asset={...asset,display_name:body.display_name};return Response.json(asset);}
  throw Error('Unexpected '+method+' '+path);
 };
 return {decisions,get opinions(){return opinions;}};
}
test('审查真实组件路径：先领取，意见响应不替换候选，批准弹窗确认后显示登记入口',async()=>{
 login();const data=reviewFixture();const view=render(<MemoryRouter><FactorReviewPage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByRole('button',{name:'领取复核'})));
 assert.equal((view.getByRole('button',{name:'批准研究用途并入库'}) as HTMLButtonElement).disabled,true);
 fireEvent.click(view.getByRole('button',{name:'领取复核'}));await waitFor(()=>assert.ok(view.getByText('我在复核')));
 fireEvent.click(view.getByRole('button',{name:'独立分析意见'}));fireEvent.click(view.getByRole('button',{name:'生成独立分析意见'}));
 await waitFor(()=>assert.ok(view.getByText('基于冻结证据的独立意见')));assert.ok(view.getByRole('heading',{name:'候选测试',level:2}));assert.equal(data.opinions,1);
 const approve=view.getByRole('button',{name:'批准研究用途并入库'});approve.focus();fireEvent.click(approve);
 const dialog=view.getByRole('dialog',{name:'批准研究用途并入库'});const modal=within(dialog);
 fireEvent.change(modal.getByLabelText('因子名称'),{target:{value:'正式业务名称'}});fireEvent.change(modal.getByLabelText('业务分类'),{target:{value:'反转因子'}});fireEvent.change(modal.getByLabelText('复核依据'),{target:{value:'已核验冻结的全部研究证据'}});
 assert.equal((modal.getByRole('button',{name:'批准研究用途并入库'}) as HTMLButtonElement).disabled,true);
 fireEvent.click(modal.getByRole('checkbox'));fireEvent.click(modal.getByRole('button',{name:'批准研究用途并入库'}));
 await waitFor(()=>assert.ok(!view.queryByRole('dialog')));assert.equal(data.decisions.length,1);assert.equal(data.decisions[0].decision,'approve_research_and_register');assert.equal(data.decisions[0].acknowledged,true);
 assert.ok(view.getAllByText('复核已完成')[0]);assert.ok(view.getByRole('link',{name:'在因子库查看登记与报告'}));
});
test('旧反馈和作者只读不会出现新批准入口；取消弹窗回到触发按钮',async()=>{
 login();reviewFixture('research_feedback_only');const view=render(<MemoryRouter><FactorReviewPage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByRole('button',{name:'领取复核'})));assert.equal(view.queryByRole('button',{name:'批准研究用途并入库'}),null);
 fireEvent.click(view.getByRole('button',{name:'领取复核'}));await waitFor(()=>assert.ok(view.getByText('我在复核')));
 const button=view.getByRole('button',{name:'复核不通过'});button.focus();fireEvent.click(button);fireEvent.click(within(view.getByRole('dialog')).getByRole('button',{name:'取消'}));assert.equal(document.activeElement,button);
});
test('作者只读材料没有批准、领取或决定按钮',async()=>{
 login('write');reviewFixture('research_admission',true);const view=render(<MemoryRouter><FactorReviewPage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByRole('heading',{name:'候选测试',level:2})));assert.equal(view.queryByRole('button',{name:'批准研究用途并入库'}),null);assert.equal(view.queryByRole('button',{name:'领取复核'}),null);assert.equal(view.queryByRole('button',{name:'复核不通过'}),null);
});
test('冻结资产复用保存来源和原定义，不复制旧验证状态或自动运行',async()=>{
 login('write');let saved:any;const posts:string[]=[];
 globalThis.fetch=async(input,init)=>{const path=new URL(String(input),'http://localhost').pathname;const body=init?.body?JSON.parse(String(init.body)):{};posts.push((init?.method||'GET')+' '+path);if(path.endsWith('/detect/projects'))return Response.json({project:{...body,id:'new-project'}});if(path.endsWith('/detect/projects/new-project')){saved=body;return Response.json({project:body});}throw Error(path);};
 const project=await reuseResearchAsset(asset as ResearchAsset);assert.equal(project.id,'new-project');assert.equal(saved.config.draftFactor.body,asset.definition.factor_code);assert.equal(saved.config.sourceResearchAsset.id,asset.id);assert.equal(saved.config.sourceResearchAsset.version,1);assert.equal(saved.config.researchPlan,undefined);assert.equal(saved.archive,undefined);assert.equal(posts.length,2);assert.ok(posts.every(p=>!p.includes('/f0')));
});
test('普通研究员从机构资产入口查看授权报告摘要与固定代码，无作者私有报告请求',async()=>{
 login('write');window.history.pushState({},'','/quant/factor/library');const requested:string[]=[];
 globalThis.fetch=async(input)=>{const url=new URL(String(input),'http://localhost');requested.push(url.pathname);if(url.pathname.endsWith('/assets/qfa_candidate'))return Response.json(asset);if(url.pathname.endsWith('/assets'))return Response.json({assets:[asset]});if(url.pathname.includes('reference'))return Response.json({items:[]});if(url.pathname.includes('re-catalog'))return Response.json({factors:[],ok:true});if(url.pathname.includes('/factor/index'))return Response.json({factors:[],libraries:[]});return Response.json({factors:[],libraries:[],items:[]});};
 const view=render(<MemoryRouter initialEntries={['/quant/factor/library?asset=qfa_candidate']}><QuantFactorLibraryPage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByRole('button',{name:'用此固定定义建立研究'})));
 assert.ok(view.getByText('查看研发报告摘要'));assert.ok(view.getByText('查看独立验证报告摘要'));assert.ok(view.getByText(asset.definition.factor_code));assert.ok(!requested.some(path=>path.includes('/detect/runs/')||path.includes('/projects/')));
});


test('已决定复盘：结果摘要可见，缺项去重，因子路由不读取或拼接空策略区',async()=>{
 login();reviewFixture('research_feedback_only');const original=globalThis.fetch;let strategyReads=0;
 globalThis.fetch=async(input,init)=>{
  const path=new URL(String(input),'http://localhost').pathname;if(path.includes('/strategy-research/'))strategyReads++;
  const response=await original(input,init);if(path.endsWith('/reviews/candidate')){const current=await response.json();current.archive.review={...current.archive.review,status:'reviewed',decision:'rejected',note:'真实研发证据尚不支持该结论'};current.feedback_materials={missing:['完整库对照未完成','完整库对照未完成'],allowed_decisions:['needs_revision','rejected'],grants_admission:false};return Response.json(current);}return response;
 };
 const view=render(<MemoryRouter initialEntries={['/quant/reviews/factors']}><FactorReviewPage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByRole('heading',{name:'复核已完成'})));assert.ok(view.getByLabelText('复核结果'));assert.equal(view.getAllByText('完整库对照未完成').length,1);assert.ok(view.queryByRole('heading',{name:'策略候选'})===null,'因子页不得拼接策略区');assert.equal(strategyReads,0);
});
test('策略复核路由保留原有策略入口，不顺带请求因子复核',async()=>{
 login();let factorReads=0;globalThis.fetch=async(input)=>{const path=new URL(String(input),'http://localhost').pathname;if(path.includes('/factor-workflow/'))factorReads++;return Response.json({branches:[]});};
 const view=render(<MemoryRouter initialEntries={['/quant/reviews/strategies']}><FactorReviewPage/></MemoryRouter>);await waitFor(()=>assert.ok(view.getByText('没有待审策略候选')));assert.equal(factorReads,0);
});
