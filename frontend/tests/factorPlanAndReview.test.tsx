import './domSetup.mjs';
import React from 'react';
import test,{afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {render,cleanup,waitFor,fireEvent} from '@testing-library/react';
import {FactorPlanAssistant} from '../src/pages/institutional-workflow/FactorPlanAssistant';
import {FactorReviewPage} from '../src/pages/institutional-workflow/FactorReviewPage';
const originalFetch=globalThis.fetch;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;});
const draft={hypothesis:'old',target:'target',acceptance:'predeclared'};
const proposal={suggestion:{hypothesis:'new hypothesis',target:'new target',acceptance:'method',summary:'suggestion only',limitations:['not tested']},run_id:'ai-real-shaped',model:'test-double',prompt_version:'v1',latency_ms:1,actions:['read','model','schema']};
test('AI suggestion changes no form until explicit adoption',async()=>{
 let applied:unknown;globalThis.fetch=async()=>Response.json(proposal);
 const v=render(<FactorPlanAssistant projectId="p" draft={draft} onApply={x=>applied=x}/>);
 fireEvent.click(v.getByRole('button',{name:'AI完善研究计划'}));await waitFor(()=>assert.ok(v.getByText('suggestion only')));assert.equal(applied,undefined);
 fireEvent.click(v.getByRole('button',{name:'采纳到计划表单'}));assert.deepEqual(applied,{hypothesis:'new hypothesis',target:'new target',acceptance:'method'});
});
test('edited draft blocks old suggestion and project switch clears it',async()=>{
 globalThis.fetch=async()=>Response.json(proposal);const apply=()=>assert.fail('stale adoption');
 const v=render(<FactorPlanAssistant projectId="p" draft={draft} onApply={apply}/>);fireEvent.click(v.getByRole('button',{name:'AI完善研究计划'}));await waitFor(()=>assert.ok(v.getByText('suggestion only')));
 v.rerender(<FactorPlanAssistant projectId="p" draft={{...draft,hypothesis:'edited'}} onApply={apply}/>);assert.equal((v.getByRole('button',{name:'采纳到计划表单'}) as HTMLButtonElement).disabled,true);
 v.rerender(<FactorPlanAssistant projectId="other" draft={draft} onApply={apply}/>);assert.equal(v.queryByText('suggestion only'),null);
});
test('AI network failure exposes no fabricated suggestion',async()=>{
 globalThis.fetch=async()=>{throw Error('offline');};const v=render(<FactorPlanAssistant projectId="p" draft={draft} onApply={()=>assert.fail('no output')}/>);fireEvent.click(v.getByRole('button',{name:'AI完善研究计划'}));await waitFor(()=>assert.ok(v.getByRole('alert')));assert.equal(v.queryByRole('button',{name:'采纳到计划表单'}),null);
});
const item={id:'c',name:'fixed study',snapshot_hash:'abc',status:'development_failed',archive:{note:'failure retained',review:{status:'requested',question:'check method'}},snapshot:{name:'fixed study',plan:{hypothesis:'frozen'},request:{factor_code:'read only'}},evidence:{development:{run_id:'r',gate:{passed:false,checks:[{name:'IC',actual:-.1,operator:'>=',threshold:.01,passed:false}]}}}};
test('review UI shows failed evidence, sends only feedback, and locks recorded decision',async()=>{
 let sent:any;globalThis.fetch=async(url,init)=>{if(init?.method==='POST'){sent=JSON.parse(String(init.body));return Response.json({...item,archive:{...item.archive,review:{...item.archive.review,status:'reviewed',...sent}}});}return Response.json(String(url).endsWith('/reviews')?{candidates:[item]}:item);};
 const v=render(<FactorReviewPage/>);await waitFor(()=>assert.ok(v.getByRole('button',{name:/fixed study/})));fireEvent.click(v.getByRole('button',{name:/fixed study/}));await waitFor(()=>assert.ok(v.getByText(/预设条件未通过/)));
 fireEvent.change(v.getByLabelText('复核依据与改进要求'),{target:{value:'rework the hypothesis'}});fireEvent.click(v.getByRole('button',{name:'保存复核意见'}));await waitFor(()=>assert.ok(v.getByText('本版本复核记录已保存，不可覆盖。')));
 assert.deepEqual(sent,{decision:'needs_revision',note:'rework the hypothesis'});assert.equal(v.queryByRole('button',{name:'保存复核意见'}),null);
});
test('review service failure preserves unsent feedback',async()=>{
 globalThis.fetch=async(url,init)=>init?.method==='POST'?Response.json({detail:'try later'},{status:503}):Response.json(String(url).endsWith('/reviews')?{candidates:[item]}:item);
 const v=render(<FactorReviewPage/>);await waitFor(()=>assert.ok(v.getByRole('button',{name:/fixed study/})));fireEvent.click(v.getByRole('button',{name:/fixed study/}));await waitFor(()=>assert.ok(v.getByLabelText('复核依据与改进要求')));fireEvent.change(v.getByLabelText('复核依据与改进要求'),{target:{value:'keep this note'}});fireEvent.click(v.getByRole('button',{name:'保存复核意见'}));await waitFor(()=>assert.ok(v.getByRole('alert')));assert.equal((v.getByLabelText('复核依据与改进要求') as HTMLTextAreaElement).value,'keep this note');
});
