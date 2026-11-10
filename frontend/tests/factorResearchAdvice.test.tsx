import './domSetup.mjs';
import React from 'react';
import assert from 'node:assert/strict';
import test,{afterEach} from 'node:test';
import {render,cleanup,fireEvent,waitFor} from '@testing-library/react';
import {FactorResearchAdvice} from '../src/pages/institutional-workflow/FactorResearchAdvice';
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
const originalFetch=globalThis.fetch;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();});
function login(id=7,org=3){window.history.pushState({},'','/quant/factor');sessionStorage.setItem('svquant_quant_session',JSON.stringify({product:'quant',token:'test',user:{id},org:{id:org},permissions:{quant:'write'},can_write:true}));}
const props={topicId:'topic',projectId:'project',canSubmit:true,branches:[{id:'h1',display_label:'H1',implementation_version:1},{id:'h1a',display_label:'H1a',implementation_version:2}]};
function receipt(body:any,status='pending'){const {request_key,run_id,...input}=body;return {id:'stored-advice',request_key,run_id,input,status,reason:status==='not_adopted'?'未采用：研究已结束':''};}
function setup(post:(body:any)=>Promise<Response>|Response){
 let branch='h1',epoch='epoch1',run='run1',status='running';const posts:any[]=[];
 globalThis.fetch=async(input,init)=>{
  const path=new URL(String(input),'http://localhost').pathname;
  if(init?.method==='POST'){const body=JSON.parse(String(init.body));posts.push(body);return post(body);}
  if(path.endsWith('/f0-runs'))return Response.json({id:run,status});
  if(path.endsWith('/detect/projects/project'))return Response.json({project:{id:'project',name:'研究任务',config:{v5ActiveBranch:branch,v5ControlEpoch:epoch}}});
  throw Error('Unexpected '+path);
 };
 return {posts,change:()=>{branch='h1a';epoch='epoch2';},end:()=>{status='stopped';},newRun:()=>{run='run2';}};
}
async function type(view:any,text='只比较向后窗口，不扩大范围'){
 fireEvent.click(view.getByRole('button',{name:'给研究建议'}));const input=await view.findByLabelText('给当前研究的建议');
 await waitFor(()=>assert.equal((input as HTMLTextAreaElement).disabled,false));fireEvent.change(input,{target:{value:text}});
}

test('409 error正文明确拒绝，保留文字；用户确认新目标后才使用新key提交',async()=>{
 login();let count=0;const state=setup(body=>++count===1?Response.json({error:'当前研究版本已变化，这笔建议未保存。',code:'advice_target_changed',saved:false},{status:409}):Response.json(receipt(body)));
 const view=render(<FactorResearchAdvice {...props}/>);await type(view);state.change();fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));
 await waitFor(()=>assert.ok(view.getByText('当前研究版本已变化，这笔建议未保存。')));
 assert.equal((view.getByLabelText('给当前研究的建议') as HTMLTextAreaElement).value,'只比较向后窗口，不扩大范围');assert.equal(view.queryByRole('button',{name:'确认原提交'}),null);
 fireEvent.click(view.getByRole('button',{name:'选择当前研究版本'}));await waitFor(()=>assert.ok(view.getByText(/改为向 H1a · 第2版/)));assert.equal(state.posts.length,1);
 fireEvent.click(view.getByRole('button',{name:'确认使用当前研究版本'}));assert.equal(state.posts.length,1);
 fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));await waitFor(()=>assert.ok(view.getByText(/研究建议已保存，等待系统处理；尚不代表已采用/)));
 assert.equal(state.posts[1].branch_id,'h1a');assert.notEqual(state.posts[0].request_key,state.posts[1].request_key);assert.equal(state.posts[0].message,state.posts[1].message);
});

test('实际保存后响应丢失，结束或新运行后仍按原key原正文确认，刷新不新建身份',async()=>{
 login();let saved:any;const state=setup(body=>{if(!saved){saved=body;throw Error('response lost after commit');}return Response.json(receipt(saved,'not_adopted'));});
 let view=render(<FactorResearchAdvice {...props}/>);await type(view);fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));
 await waitFor(()=>assert.ok(view.getByRole('button',{name:'确认原提交'})));view.unmount();state.end();state.newRun();
 view=render(<FactorResearchAdvice {...props} canSubmit={false}/>);
 assert.equal((view.getByLabelText('给当前研究的建议') as HTMLTextAreaElement).readOnly,true);
 fireEvent.click(view.getByRole('button',{name:'确认原提交'}));await waitFor(()=>assert.ok(view.getByText(/原研究建议已保存，系统记录为未采用/)));
 assert.deepEqual(state.posts[0],state.posts[1]);assert.equal(state.posts[1].run_id,'run1');assert.equal(view.queryByRole('button',{name:'选择当前研究版本'}),null);
});

test('网络结果未知时403只能说明无权确认，不能宣称未保存或静默换目标',async()=>{
 login();let count=0;const state=setup(()=>++count===1?Promise.reject(Error('network timeout')):Response.json({error:'没有权限'},{status:403}));
 const view=render(<FactorResearchAdvice {...props}/>);await type(view);fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));await waitFor(()=>assert.ok(view.getByRole('button',{name:'确认原提交'})));
 fireEvent.click(view.getByRole('button',{name:'确认原提交'}));await waitFor(()=>assert.ok(view.getByText(/当前无权确认这笔建议的保存结果/)));
 assert.deepEqual(state.posts[0],state.posts[1]);assert.equal(view.queryByRole('button',{name:'选择当前研究版本'}),null);assert.equal((view.getByLabelText('给当前研究的建议') as HTMLTextAreaElement).readOnly,true);
});

test('首次403确定拒绝准确显示，200无匹配回执也不虚报成功',async()=>{
 login();let count=0;setup(()=>++count===1?Response.json({error:'当前没有提交研究建议的权限'},{status:403}):Response.json({id:'wrong',status:'pending'}));
 const view=render(<FactorResearchAdvice {...props}/>);await type(view);fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));await waitFor(()=>assert.ok(view.getByText('当前没有提交研究建议的权限')));
 fireEvent.click(view.getByRole('button',{name:'选择当前研究版本'}));fireEvent.click(await view.findByRole('button',{name:'确认使用当前研究版本'}));fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));
 await waitFor(()=>assert.ok(view.getByText(/返回的保存记录与这笔建议尚未对应/)));assert.equal(view.queryByText(/研究建议已保存/),null);
});

test('确定研究已结束保留文本，不显示永久重试或伪装采用',async()=>{
 login();setup(()=>Response.json({error:'本次研究已结束，这笔建议未保存。',code:'advice_ended',saved:false},{status:409}));
 const view=render(<FactorResearchAdvice {...props}/>);await type(view);fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));await waitFor(()=>assert.ok(view.getByText('本次研究已结束，这笔建议未保存。')));
 view.rerender(<FactorResearchAdvice {...props} canSubmit={false}/>);assert.equal(view.queryByRole('button',{name:'确认原提交'}),null);assert.equal(view.queryByRole('button',{name:'选择当前研究版本'}),null);
 assert.equal((view.getByLabelText('给当前研究的建议') as HTMLTextAreaElement).value,'只比较向后窗口，不扩大范围');
});

test('任务和账号切换隔离草稿，迟到响应不覆盖当前任务；轮询不折叠输入',async()=>{
 login();let resolve!:(value:Response)=>void;const state=setup(()=>new Promise<Response>(r=>{resolve=r;}));
 const view=render(<FactorResearchAdvice {...props}/>);await type(view,'仅针对原任务的建议');view.rerender(<FactorResearchAdvice {...props} branches={[...props.branches]}/>);assert.ok(view.getByLabelText('给当前研究的建议'));
 fireEvent.click(view.getByRole('button',{name:'提交研究建议'}));await waitFor(()=>assert.equal(state.posts.length,1));
 view.rerender(<FactorResearchAdvice {...props} topicId="different-topic"/>);assert.equal(view.queryByLabelText('给当前研究的建议'),null);
 resolve(Response.json(receipt(state.posts[0])));await new Promise(r=>setTimeout(r,0));assert.equal(view.queryByText(/研究建议已保存/),null);
 login(8);view.rerender(<FactorResearchAdvice {...props}/>);assert.equal(view.queryByLabelText('给当前研究的建议'),null);
 login();view.rerender(<FactorResearchAdvice {...props}/>);assert.equal((view.getByLabelText('给当前研究的建议') as HTMLTextAreaElement).value,'仅针对原任务的建议');assert.ok(view.getByRole('button',{name:'确认原提交'}));
});
