import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { StrategyDraftAssistant } from "../src/pages/institutional-workflow/StrategyDraftAssistant";
import { QuantStrategyPage } from "../src/pages/institutional-workflow/QuantStrategyPage";
import { QuantStrategyReportPage } from "../src/pages/institutional-workflow/QuantStrategyReportPage";
import { defaultStrategyConfig } from "../src/lib/strategyStore";
Object.defineProperty(globalThis,"sessionStorage",{value:window.sessionStorage,configurable:true});
const originalFetch=globalThis.fetch;
let sequence=0;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();});
function identity(){sessionStorage.setItem("svquant_user",JSON.stringify({id:8800+ ++sequence,username:"quant_strategy_test"}));}
function mount(){return render(<MemoryRouter initialEntries={["/quant/strategy"]}><Routes>
  <Route path="/quant/strategy" element={<QuantStrategyPage/>}/>
  <Route path="/quant/strategy/:projectId" element={<p>进入策略工作台</p>}/>
</Routes></MemoryRouter>);}
test("library research creates a project through existing API without running a backtest",async()=>{
  identity();const writes:any[]=[];
  globalThis.fetch=async(url,init)=>{
    assert.equal(String(url),"/api/strategy/projects");
    if(!init?.method)return Response.json({projects:[]});
    const body=JSON.parse(String(init.body));writes.push(body);
    return Response.json({project:{...body,id:"p1",config:defaultStrategyConfig()}});
  };
  const view=mount();
  await waitFor(()=>assert.ok(view.getByText(/当前账户尚无策略研究项目/)));
  fireEvent.change(view.getByLabelText("研究名称"),{target:{value:"组合动量"}});
  fireEvent.change(view.getByLabelText("研究目标"),{target:{value:"验证动量假设"}});
  fireEvent.click(view.getByRole("button",{name:"保存并构建策略"}));
  await waitFor(()=>assert.ok(view.getByText("进入策略工作台")));
  assert.deepEqual(writes,[{name:"组合动量",description:"验证动量假设"}]);
});
test("code import preserves actual factor source in strategy project; does not call the engine",async()=>{
  identity();let project:any;const calls:string[]=[];
  globalThis.fetch=async(url,init)=>{
    const path=new URL(String(url),"http://localhost").pathname;calls.push(path);
    if(path==="/api/strategy/projects"){
      if(!init?.method)return Response.json({projects:[]});
      project={...JSON.parse(String(init.body)),id:"p2",config:defaultStrategyConfig()};
      return Response.json({project});
    }
    if(path==="/api/strategy/projects/p2"){project={...project,...JSON.parse(String(init?.body))};return Response.json({project});}
    if(path==="/api/factor/re-catalog")return Response.json({factors:[]});
    if(path==="/api/factor/index")return new Response("libraries: {}");
    throw Error("Unexpected "+path);
  };
  const view=mount();
  await waitFor(()=>assert.ok(view.getByText(/当前账户尚无策略研究项目/)));
  fireEvent.change(view.getByLabelText("研究名称"),{target:{value:"手写动量"}});
  fireEvent.change(view.getByLabelText("研究目标"),{target:{value:"验证20日动量"}});
  fireEvent.change(view.getByLabelText("构建方式"),{target:{value:"code"}});
  fireEvent.change(view.getByLabelText("策略代码或因子函数"),{target:{value:"def actual_momentum(self):\n    return self.close.pct_change(20)"}});
  fireEvent.click(view.getByRole("button",{name:"保存并构建策略"}));
  await waitFor(()=>assert.ok(view.getByText("进入策略工作台")));
  assert.match(project.config.strategy_code,/def actual_momentum/);
  assert.match(project.config.strategy_code,/return self.close.pct_change\(20\)/);
  assert.equal(project.description,"验证20日动量");
  assert.ok(!calls.some(path=>path.includes("/backtest/")));
});
test("failed save retains strategy inputs",async()=>{
  identity();
  globalThis.fetch=async(_url,init)=>init?.method?Response.json({detail:"保存失败"},{status:503}):Response.json({projects:[]});
  const view=mount();
  await waitFor(()=>assert.ok(view.getByText(/当前账户尚无策略研究项目/)));
  fireEvent.change(view.getByLabelText("研究名称"),{target:{value:"保留研究"}});
  fireEvent.change(view.getByLabelText("研究目标"),{target:{value:"保留目标"}});
  fireEvent.click(view.getByRole("button",{name:"保存并构建策略"}));
  await waitFor(()=>assert.ok(view.getByRole("alert")));
  assert.equal((view.getByLabelText("研究目标") as HTMLTextAreaElement).value,"保留目标");
});
test("report request failure is visible instead of an unhandled rejection",async()=>{
  identity();globalThis.fetch=async()=>Response.json({detail:"forbidden"},{status:403});
  const view=render(<MemoryRouter initialEntries={["/quant/strategy/report/denied"]}><Routes><Route path="/quant/strategy/report/:runId" element={<QuantStrategyReportPage/>}/></Routes></MemoryRouter>);
  await waitFor(()=>assert.match(view.getByRole("alert").textContent!,/无法读取报告/));
});

test("strategy provenance uses the backend report verification flag, not a factor-only field",async()=>{
  identity();
  const record={id:"signed",projectId:"p",name:"测试报告",description:"测试",verified:true,request:{start:"2025-01-01",end:"2025-06-30"},result:{metrics:{},meta:{run_id:"actual-engine-run"}},finishedAt:"2025-07-01",elapsedSec:1};
  globalThis.fetch=async()=>Response.json({run:record,project:{id:"p",config:defaultStrategyConfig()}});
  const view=render(<MemoryRouter initialEntries={["/quant/strategy/report/signed"]}><Routes><Route path="/quant/strategy/report/:runId" element={<QuantStrategyReportPage/>}/></Routes></MemoryRouter>);
  await waitFor(()=>assert.ok(view.getByText("计算来源 · 平台签名校验通过")));
  assert.ok(view.getAllByText("引擎未返回").length>=1);
  assert.ok(view.getByText("actual-engine-run"));
});

test("strategy AI uses the shared generation endpoint and requires adoption",async()=>{
  identity();let adopted:any;let request:any;
  globalThis.fetch=async(url,init)=>{
    assert.equal(String(url),"/api/ai/strategy-generations");request=JSON.parse(String(init?.body));
    return Response.json({generation_id:"strategy-fixture",status:"ready",strategy:{strategy_name:"Momentum",strategy_code:"class Momentum: pass",description:"测试草稿",used_fields:["close"],assumptions:[],warnings:[]},validation:{status:"passed",errors:[],warnings:[]},meta:{model_alias:"test-provider"}});
  };
  const view=render(<StrategyDraftAssistant hypothesis="构建20日动量策略，每5个交易日等权调整30个持仓" name="" draftVersion="v1" onApply={v=>{adopted=v;}}/>);
  fireEvent.click(view.getByRole("button",{name:"根据研究假设生成代码"}));
  await waitFor(()=>assert.ok(view.getByText("静态校验通过，等待采纳")));
  assert.equal(adopted,undefined);assert.equal(request.context.frequency,"1d");
  fireEvent.click(view.getByRole("button",{name:"采纳到代码表单"}));
  assert.equal(adopted.strategy_name,"Momentum");
});
test("edited strategy objectives invalidate a pending AI proposal",async()=>{
  identity();let respond:(r:Response)=>void=()=>{};
  globalThis.fetch=async()=>await new Promise<Response>(r=>{respond=r;});
  const props={hypothesis:"构建20日动量策略，每5个交易日等权调整30个持仓",name:"",onApply:()=>{throw Error("must not apply stale draft");}};
  const view=render(<StrategyDraftAssistant {...props} draftVersion="v1"/>);
  fireEvent.click(view.getByRole("button",{name:"根据研究假设生成代码"}));
  view.rerender(<StrategyDraftAssistant {...props} draftVersion="v2"/>);
  respond(Response.json({generation_id:"late",status:"ready",strategy:{strategy_name:"Momentum",strategy_code:"class Momentum: pass",description:"测试",used_fields:[],assumptions:[],warnings:[]},validation:{status:"passed",errors:[],warnings:[]}}));
  await waitFor(()=>assert.ok(view.getByText(/当前研究内容已修改/)));
  assert.equal((view.getByRole("button",{name:"采纳到代码表单"}) as HTMLButtonElement).disabled,true);
});
