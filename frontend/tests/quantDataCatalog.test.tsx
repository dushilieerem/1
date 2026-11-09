import './domSetup.mjs';
import React from 'react';import test,{afterEach} from 'node:test';import assert from 'node:assert/strict';
import {render,fireEvent,waitFor,cleanup,within} from '@testing-library/react';
import {QuantDataCatalog} from '../src/pages/institutional-workflow/QuantDataCatalog';
import type {DataCatalog,DataSet} from '../src/pages/institutional-workflow/quantDataModel';
const originalFetch=globalThis.fetch;Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();window.history.pushState({},'','/');});
function login(){window.history.pushState({},'','/quant/data');sessionStorage.setItem('svquant_quant_session',JSON.stringify({product:'quant',token:'isolated-token',user:{id:9,username:'fixture'},org:{id:2,code:'fixture'},permissions:{quant:'write'},can_write:true}));}
const items:DataSet[]=Array.from({length:45},(_,i)=>({name:'dataset_'+i,label:'数据'+i,topic:i%2?'财务':'行情',frequency:i%2?'公告日':'日频',published:i<40,quality_status:i===0?'error':'unchecked',applicability:{status:i%2?'restricted':'unknown',summary:i%2?'按公告时点核对':'适用性待确认'},field_index:[{name:'metric_'+i,label:'中文字段'+i}]}));
const catalog:DataCatalog={view_id:'fixture-v1',summary:{datasets:40},datasets:items};
function props(){return {catalog,loading:false,onRetry:()=>{},onVersions:()=>{},onRequest:()=>{}};}
function detail(name:string){return {...items.find(d=>d.name===name),view_id:'fixture-v1',fields:[{name:'sw_l2_code',label:'申万二级代码',availability_status:'conflict',availability_rule:'当前分类快照；字段覆盖状态待确认',availability_note:'历史日期套用当前映射',catalog_note:'目录旧说明',source_ref:'fixture-v1/data_contract',catalog_source_ref:'fixture-v1/monitor'}],quality_checks:[]};}
test('真实目录组件搜索字段名和中文字段，多筛选并分页；清除保留可用控件',()=>{
 login();const view=render(<QuantDataCatalog {...props()}/>);assert.equal(view.container.querySelectorAll('tbody tr').length,20);assert.ok(view.getByText('40'));fireEvent.click(view.getByRole('button',{name:'下一页'}));assert.ok(view.getByText('数据20'));
 const search=view.getByRole('searchbox');search.focus();fireEvent.change(search,{target:{value:'metric_44'}});assert.ok(view.getByText('数据44'));assert.match(view.container.textContent!,/第 1 \/ 1 页/);assert.equal(document.activeElement,search);
 fireEvent.change(search,{target:{value:'中文字段3'}});fireEvent.change(view.getByLabelText('分类'),{target:{value:'财务'}});fireEvent.change(view.getByLabelText('频率'),{target:{value:'公告日'}});fireEvent.change(view.getByLabelText('使用说明'),{target:{value:'restricted'}});assert.ok(view.getByText('数据3'));assert.equal(view.queryByText('数据30'),null);
 fireEvent.click(view.getByRole('button',{name:'重置'}));assert.equal((search as HTMLInputElement).value,'');assert.equal(view.container.querySelectorAll('tbody tr').length,20);
});
test('零结果可清除筛选或提交需求；未知发布和读取失败不冒充未检查',()=>{
 login();let requested=0;const view=render(<QuantDataCatalog {...props()} onRequest={()=>requested++}/>);assert.ok(view.getByText('检查结果读取失败'));fireEvent.change(view.getByRole('searchbox'),{target:{value:'no_match'}});assert.ok(view.getByText('没有符合条件的数据'));fireEvent.click(view.getByRole('button',{name:'提交数据需求'}));assert.equal(requested,1);fireEvent.click(view.getByRole('button',{name:'清除筛选'}));assert.ok(view.getByText('数据0'));
});
test('目录失败有独立重试，旧成功目录更新失败保留时点提示',()=>{
 let retried=0;const view=render(<QuantDataCatalog {...props()} catalog={undefined} error="目录失败" onRetry={()=>retried++}/>);fireEvent.click(view.getByRole('button',{name:'重新加载'}));assert.equal(retried,1);view.rerender(<QuantDataCatalog {...props()} error="网络异常"/>);assert.match(view.getByRole('alert').textContent!,/此前读取/);assert.ok(view.getByText('数据0'));
});
test('详情固定版本、保留两个口径来源；关闭回焦且不改变当前筛选',async()=>{
 login();const calls:string[]=[];globalThis.fetch=async input=>{calls.push(String(input));return Response.json(detail('dataset_3'));};const view=render(<QuantDataCatalog {...props()}/>);fireEvent.change(view.getByRole('searchbox'),{target:{value:'dataset_3'}});const trigger=view.getByRole('button',{name:'查看 数据3 详情'});trigger.focus();fireEvent.click(trigger);const modal=within(view.getByRole('dialog'));await waitFor(()=>assert.ok(modal.getByText('申万二级代码')));assert.ok(modal.getByText(/目录原文：目录旧说明/));assert.equal(modal.getAllByText(/字段覆盖状态待确认/).length,2);assert.ok(calls[0].includes('view_id=fixture-v1'));fireEvent.click(modal.getByRole('button',{name:'完成'}));assert.equal(document.activeElement,trigger);assert.equal((view.getByRole('searchbox') as HTMLInputElement).value,'dataset_3');
});
test('A详情慢返回，关闭后切B只展示B；请求失败不残留旧字段',async()=>{
 login();let resolveA:(value:Response)=>void=()=>{};globalThis.fetch=async input=>String(input).includes('dataset_0?')?new Promise< Response>(resolve=>{resolveA=resolve;}):Response.json(detail('dataset_1'));
 const view=render(<QuantDataCatalog {...props()}/>);fireEvent.click(view.getByRole('button',{name:'查看 数据0 详情'}));fireEvent.click(view.getByRole('button',{name:'完成'}));fireEvent.click(view.getByRole('button',{name:'查看 数据1 详情'}));await waitFor(()=>assert.ok(within(view.getByRole('dialog')).getByText('申万二级代码')));resolveA(Response.json(detail('dataset_0')));await new Promise(r=>setTimeout(r,10));assert.equal(view.getByRole('dialog').getAttribute('aria-label'),'数据1');fireEvent.click(within(view.getByRole('dialog')).getByRole('button',{name:'完成'}));globalThis.fetch=async()=>new Response('{}',{status:500});fireEvent.click(view.getByRole('button',{name:'查看 数据2 详情'}));await waitFor(()=>assert.ok(within(view.getByRole('dialog')).getByRole('alert')));assert.equal(within(view.getByRole('dialog')).queryByText('申万二级代码'),null);
});
test('返回不同发布版本明确拒绝，不拼接旧目录和新字段',async()=>{
 login();globalThis.fetch=async()=>Response.json({...detail('dataset_0'),view_id:'different'});const view=render(<QuantDataCatalog {...props()}/>);fireEvent.click(view.getByRole('button',{name:'查看 数据0 详情'}));await waitFor(()=>assert.match(within(view.getByRole('dialog')).getByRole('alert').textContent!,/不一致/));assert.equal(within(view.getByRole('dialog')).queryByText('申万二级代码'),null);
});

test('只读目录的零结果和详情均无需求或反馈写入口',async()=>{
 login();globalThis.fetch=async()=>Response.json(detail('dataset_0'));const view=render(<QuantDataCatalog {...props()} canWrite={false}/>);fireEvent.change(view.getByRole('searchbox'),{target:{value:'absent'}});assert.equal(view.queryByRole('button',{name:'提交数据需求'}),null);assert.ok(view.getByText('当前身份仅可查看数据说明。'));fireEvent.click(view.getByRole('button',{name:'清除筛选'}));fireEvent.click(view.getByRole('button',{name:'查看 数据0 详情'}));await waitFor(()=>assert.ok(within(view.getByRole('dialog')).getByText('申万二级代码')));assert.equal(within(view.getByRole('dialog')).queryByRole('button',{name:'反馈数据问题'}),null);
});
