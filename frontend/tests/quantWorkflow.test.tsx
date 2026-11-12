import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { FactorDraftAssistant } from "../src/pages/institutional-workflow/FactorDraftAssistant";
import { QuantFactorPage } from "../src/pages/institutional-workflow/QuantFactorPage";
import { QuantFactorReportsPage } from "../src/pages/institutional-workflow/QuantFactorReportsPage";
import { FactorDetectPage } from "../src/pages/FactorDetectPage";
import { defaultConfig } from "../src/lib/detectStore";

Object.defineProperty(globalThis, "sessionStorage", {value: window.sessionStorage, configurable:true});
Object.defineProperty(globalThis, "Window", {value: window.constructor, configurable:true});
Object.defineProperty(globalThis, "getComputedStyle", {value: window.getComputedStyle.bind(window), configurable:true});
window.requestAnimationFrame = fn => window.setTimeout(() => fn(0),0);
window.cancelAnimationFrame = window.clearTimeout;
window.Range.prototype.getClientRects = () => [] as any;
window.Range.prototype.getBoundingClientRect = () => ({top:0,bottom:0,left:0,right:0,width:0,height:0}) as any;
const originalFetch=globalThis.fetch;
let sequence=0;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();});
function identity() {
  sessionStorage.setItem("svquant_user",JSON.stringify({id: ++sequence+900,username:"quant_test"}));
}
const code="def ui_factor(self):\n    return self.close.pct_change(20)";
function mountCreate() {
  return render(<MemoryRouter initialEntries={["/quant/factor"]}><Routes>
    <Route path="/quant/factor" element={<QuantFactorPage/>}/>
    <Route path="/quant/factor/:projectId" element={<p>已进入检验</p>}/>
  </Routes></MemoryRouter>);
}
test("research creation retains hypothesis and source in existing project API",async()=>{
  identity();let persisted:any;const writes:any[]=[];
  globalThis.fetch=async(url,init)=>{
    const path=String(url),method=init?.method||"GET";
    if(method==="GET")return Response.json({projects:[]});
    const body=JSON.parse(String(init?.body));writes.push(body);
    persisted={createdAt:"",updatedAt:"",runCount:0,...body,id:"q-create"};
    assert.ok(path.startsWith("/api/detect/projects"));
    return Response.json({project:persisted});
  };
  const view=mountCreate();
  await waitFor(()=>assert.ok(view.getByText(/尚无研究项目/)));
  fireEvent.change(view.getByLabelText("研究名称"),{target:{value:"研究A"}});
  fireEvent.change(view.getByLabelText("研究假设"),{target:{value:"检验动量假设"}});
  fireEvent.change(view.getByLabelText("因子函数名"),{target:{value:"ui_factor"}});
  fireEvent.change(view.getByLabelText("因子 Python 函数"),{target:{value:code}});
  fireEvent.click(view.getByRole("button",{name:"保存并配置检验"}));
  await waitFor(()=>assert.ok(view.getByText("已进入检验")));
  assert.equal(persisted.description,"检验动量假设");
  assert.equal(persisted.config.draftFactor.body,code);
  assert.ok(writes.length>=2);
});
test("save failure preserves the user's research inputs",async()=>{
  identity();
  globalThis.fetch=async(_url,init)=>init?.method?Response.json({detail:"保存暂时不可用"},{status:503}):Response.json({projects:[]});
  const view=mountCreate();
  fireEvent.change(view.getByLabelText("研究名称"),{target:{value:"不能丢失的名称"}});
  fireEvent.change(view.getByLabelText("研究假设"),{target:{value:"假设"}});
  fireEvent.change(view.getByLabelText("因子函数名"),{target:{value:"ui_factor"}});
  fireEvent.change(view.getByLabelText("因子 Python 函数"),{target:{value:code}});
  fireEvent.click(view.getByRole("button",{name:"保存并配置检验"}));
  await waitFor(()=>assert.match(view.getByRole("alert").textContent!,/平台服务暂时不可用/));
  assert.equal((view.getByLabelText("研究名称") as HTMLInputElement).value,"不能丢失的名称");
  assert.equal((view.getByLabelText("因子 Python 函数") as HTMLTextAreaElement).value,code);
});
test("report API errors are not misrepresented as an empty list; retry works",async()=>{
  identity();let failed=true;
  globalThis.fetch=async()=>failed?Response.json({detail:"读取失败"},{status:503}):Response.json({runs:[]});
  const view=render(<MemoryRouter><QuantFactorReportsPage/></MemoryRouter>);
  await waitFor(()=>assert.ok(view.getByRole("alert")));
  assert.equal(view.queryByText(/当前没有已保存/),null);
  failed=false;fireEvent.click(view.getByText("重新读取"));
  await waitFor(()=>assert.ok(view.getByText(/当前没有已保存/)));
});

test("AI draft calls the existing API and changes the form only after explicit adoption",async()=>{
  identity();let adopted:any;let request:any;
  globalThis.fetch=async(url,init)=>{
    assert.equal(String(url),"/api/ai/factor-generations");
    request=JSON.parse(String(init?.body));
    return Response.json({generation_id:"fixture-ai",status:"ready",factor:{factor_name:"ui_factor",factor_code:code,description:"20日动量",used_fields:["close"],used_library_methods:[],assumptions:[],warnings:[]},validation:{status:"passed",errors:[],warnings:[]},meta:{model_alias:"test-model",prompt_version:"test-v1",latency_ms:12}});
  };
  const view=render(<FactorDraftAssistant hypothesis="计算过去20个交易日的收盘价收益率" name="ui_factor" draftVersion="v1" onApply={v=>{adopted=v;}}/>);
  fireEvent.click(view.getByRole("button",{name:"根据研究假设生成代码"}));
  await waitFor(()=>assert.ok(view.getByText("静态校验通过，等待采纳")));
  assert.equal(adopted,undefined);
  assert.equal(request.context.preferred_factor_name,"ui_factor");
  fireEvent.click(view.getByRole("button",{name:"采纳到代码表单"}));
  assert.equal(adopted.factor_code,code);
});
test("AI suggestion cannot overwrite a draft edited while it was generating",async()=>{
  identity();let respond:(value:Response)=>void=()=>{};let adopted=false;
  globalThis.fetch=async()=>await new Promise<Response>(r=>{respond=r;});
  const props={hypothesis:"计算过去20个交易日的收盘价收益率",name:"ui_factor",onApply:()=>{adopted=true;}};
  const view=render(<FactorDraftAssistant {...props} draftVersion="v1"/>);
  fireEvent.click(view.getByRole("button",{name:"根据研究假设生成代码"}));
  view.rerender(<FactorDraftAssistant {...props} draftVersion="v2"/>);
  respond(Response.json({generation_id:"late",status:"ready",factor:{factor_name:"ui_factor",factor_code:code,description:"动量",used_fields:[],used_library_methods:[],assumptions:[],warnings:[]},validation:{status:"passed",errors:[],warnings:[]}}));
  await waitFor(()=>assert.ok(view.getByText(/当前研究内容已修改/)));
  assert.equal((view.getByRole("button",{name:"采纳到代码表单"}) as HTMLButtonElement).disabled,true);
  assert.equal(adopted,false);
});
test("unconfigured AI fails visibly without supplying fabricated code",async()=>{
  identity();
  globalThis.fetch=async()=>Response.json({detail:"AI 因子生成服务尚未配置"},{status:503});
  const view=render(<FactorDraftAssistant hypothesis="计算过去20个交易日的收盘价收益率" name="ui_factor" draftVersion="v1" onApply={()=>assert.fail()}/>);
  fireEvent.click(view.getByRole("button",{name:"根据研究假设生成代码"}));
  await waitFor(()=>assert.match(view.getByRole("alert").textContent!,/AI 服务暂不可用/));
  assert.equal(view.queryByRole("button",{name:"采纳到代码表单"}),null);
});
