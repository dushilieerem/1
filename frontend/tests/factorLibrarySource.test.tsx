import './domSetup.mjs';
import React from 'react';
import assert from 'node:assert/strict';
import test,{afterEach} from 'node:test';
import {render,fireEvent,cleanup,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {QuantFactorLibraryPage} from '../src/pages/institutional-workflow/QuantFactorLibraryPage';
import {clearFactorCache} from '../src/lib/factorCatalog';
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
const originalFetch=globalThis.fetch;const clipboard=Object.getOwnPropertyDescriptor(navigator,'clipboard');const execCommand=Object.getOwnPropertyDescriptor(document,'execCommand');
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;clearFactorCache();sessionStorage.clear();window.history.pushState({},'','/');if(clipboard)Object.defineProperty(navigator,'clipboard',clipboard);else delete (navigator as any).clipboard;if(execCommand)Object.defineProperty(document,'execCommand',execCommand);else delete (document as any).execCommand;});
const CODE='# exact original\n\ndef alpha(self):\n    return self.close  # original\n';
const catalog=[{name:'SV01_0001',library:'主因子库',display_name:'原库动量',description:'动量定义',category_label:'动量因子',category_id:'SV01'},{name:'SV02_0001',library:'主因子库',display_name:'原库反转',description:'反转定义',category_label:'反转因子',category_id:'SV02'}];
function source(id='one',factor='SV01_0001',code=CODE){return {imported_id:id,library_id:1,library_name:'主因子库',factor_id:factor,function_name:'alpha',source_code:code,source_sha256:'a'.repeat(64),source_hash:'b'.repeat(64),source_hash_scope:'factor_id+adapter_version+original_source+tool_module',source_kind:'current_library_definition',execution_validated:false};}
function fixture(handler?:(id:string)=>Promise<Response>|Response,permission='write'){
 window.history.pushState({},'','/quant/factor/library');
 sessionStorage.setItem('svquant_quant_session',JSON.stringify({product:'quant',token:'isolated',user:{id:7,username:'isolated'},org:{id:9,code:'test'},permissions:{quant:permission},can_write:permission==='write'}));
 const calls:string[]=[],writes:any[]=[];
 globalThis.fetch=async(input,init)=>{const path=new URL(String(input),'http://localhost').pathname;calls.push((init?.method||'GET')+' '+path);
  if(path.endsWith('/reference'))return Response.json({items:catalog.map((f,i)=>({id:i?'two':'one',source_library:f.library,source_factor_id:f.name,factor_name:f.name,display_name:f.display_name,definition:f.description,category:f.category_label,status:'imported_unreviewed',metrics_status:'pending',reference:null}))});
  if(path.endsWith('/assets'))return Response.json({assets:[]});if(path.endsWith('/re-catalog'))return Response.json({ok:true,factors:catalog});if(path.endsWith('/factor/index'))return Response.json({libraries:{}});
  if(path.endsWith('/source')){const id=path.split('/').at(-2)!;return handler?handler(id):Response.json(source(id,id==='one'?'SV01_0001':'SV02_0001'));}
  if(path.includes('/detect/projects')){const data=JSON.parse(String(init?.body));writes.push(data);return Response.json({project:{...data,id:'new-project'}});}
  throw Error('unexpected '+path);
 };return {calls,writes};
}
async function open(view:ReturnType<typeof render>,name='原库动量'){
 const button=await view.findByRole('button',{name});button.focus();fireEvent.click(button);return view.getByRole('dialog',{name});
}
test('真实列表详情按需读源码、保留原文/两类指纹；复制后关闭保留筛选并回焦',async()=>{
 const data=fixture();let copied='';Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text:string)=>{copied=text;}}});
 const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);await view.findByRole('button',{name:'全部 2'});
 fireEvent.click(view.getByRole('button',{name:'动量因子 1'}));fireEvent.change(view.getByRole('textbox',{name:'搜索因子'}),{target:{value:'SV01'}});
 const trigger=view.getByRole('button',{name:'原库动量'});const dialog=await open(view);assert.equal(data.calls.filter(x=>x.endsWith('/source')).length,0);
 fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await waitFor(()=>assert.equal(within(dialog).getByLabelText('因子源码').textContent,CODE));
 assert.ok(within(dialog).getByText('原始源码 SHA-256'));assert.ok(within(dialog).getByText('含适配器和公共工具的执行指纹'));
 fireEvent.click(within(dialog).getByRole('button',{name:'复制代码'}));await within(dialog).findByText('已复制源码');assert.equal(copied,CODE);
 fireEvent(dialog,new window.Event('cancel',{bubbles:true,cancelable:true}));assert.equal(view.queryByRole('dialog'),null);assert.equal(document.activeElement,trigger);assert.equal((view.getByRole('textbox',{name:'搜索因子'}) as HTMLInputElement).value,'SV01');assert.equal(view.getByRole('button',{name:'动量因子 1'}).getAttribute('aria-pressed'),'true');assert.equal(data.writes.length,0);
});
test('关闭后旧源码响应迟到不能覆盖下一因子，切换时先清旧代码',async()=>{
 let old!:(r:Response)=>void;const data=fixture(id=>id==='one'?new Promise(r=>{old=r;}):Response.json(source('two','SV02_0001','def alpha(self):\n    return self.open\n')));
 const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);let dialog=await open(view);fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await waitFor(()=>assert.ok(old));fireEvent.click(within(dialog).getByRole('button',{name:'关闭详情'}));
 dialog=await open(view,'原库反转');assert.equal(within(dialog).queryByLabelText('因子源码'),null);fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await waitFor(()=>assert.ok(within(dialog).getByLabelText('因子源码').textContent?.includes('self.open')));old(Response.json(source()));await new Promise(r=>setTimeout(r,0));assert.ok(within(dialog).getByLabelText('因子源码').textContent?.includes('self.open'));assert.equal(data.writes.length,0);
});
test('空源码与暂时失败分别显示，失败重试取得实际回执',async()=>{
 let attempts=0;fixture(()=>{attempts++;return attempts===1?Response.json({error:'源码服务暂不可用，请稍后重试',code:'source_unavailable'},{status:503}):Response.json(source());});
 const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);let dialog=await open(view);fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await within(dialog).findByRole('alert');fireEvent.click(within(dialog).getByRole('button',{name:'重试读取'}));await within(dialog).findByLabelText('因子源码');assert.equal(attempts,2);cleanup();
 fixture(()=>Response.json({code:'source_empty',error:'该因子暂未提供源码'},{status:409}));const second=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);dialog=await open(second);fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await within(dialog).findByText('该因子暂未提供源码');assert.equal(within(dialog).queryByRole('button',{name:'重试读取'}),null);assert.equal(within(dialog).queryByLabelText('因子源码'),null);
});
test('看过与复制源码后建立研究仍用原库稳定ID，不提交自定义factor_code或自动计算',async()=>{
 const data=fixture();const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);const dialog=await open(view);fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await within(dialog).findByLabelText('因子源码');fireEvent.click(within(dialog).getByRole('button',{name:'基于此因子建立研究'}));await waitFor(()=>assert.equal(data.writes.length,2));
 const config=data.writes[1].config;assert.deepEqual(config.factorCodes,['SV01_0001']);assert.deepEqual(config.factorLibraries,{'SV01_0001':'主因子库'});assert.equal(config.draftFactor,undefined);assert.ok(!JSON.stringify(data.writes).includes(CODE));assert.ok(!data.calls.some(x=>/f0|backtest|source-check/.test(x)));
});
test('只读身份可看源码和空验证记录，不能建立研究',async()=>{
 fixture(undefined,'read');const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);const dialog=await open(view);assert.equal((within(dialog).getByRole('button',{name:'基于此因子建立研究'}) as HTMLButtonElement).disabled,true);fireEvent.click(within(dialog).getByRole('tab',{name:'验证记录'}));assert.ok(within(dialog).getByText('暂无本机构已登记的复现验证记录。'));assert.ok(within(dialog).getByText('暂无历史参考报告。'));fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await within(dialog).findByLabelText('因子源码');
});

test('原生对话框复制回退仅选择内部textarea，失败时保留代码选区和手动提示',async()=>{
 for(const succeeds of [true,false]){
  fixture();Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});let selected='';let inside=false;
  Object.defineProperty(document,'execCommand',{configurable:true,value:(command:string)=>{assert.equal(command,'copy');const area=document.activeElement as HTMLTextAreaElement;inside=area.tagName==='TEXTAREA'&&Boolean(area.closest('dialog'));selected=area.value;return succeeds;}});
  const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);const dialog=await open(view);fireEvent.click(within(dialog).getByRole('tab',{name:'实现代码'}));await within(dialog).findByLabelText('因子源码');const copyButton=within(dialog).getByRole('button',{name:'复制代码'});copyButton.focus();fireEvent.click(copyButton);
  await within(dialog).findByText(succeeds?'已复制源码':'已选中代码，请使用系统复制命令。');assert.equal(inside,true);assert.equal(selected,CODE);assert.equal(dialog.querySelector('textarea'),null);
  if(succeeds)assert.ok(document.activeElement===copyButton,'successful copy returns focus to its trigger');else{assert.ok(document.activeElement===within(dialog).getByLabelText('因子源码'),'manual fallback focuses the code selection');assert.equal(window.getSelection()?.toString(),CODE);}
  cleanup();
 }
});
