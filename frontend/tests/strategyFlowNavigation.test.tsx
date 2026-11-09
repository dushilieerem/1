import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ConfirmProvider } from "../src/components/ConfirmDialog";
import { StrategyBacktestPage } from "../src/pages/StrategyBacktestPage";
import { StrategyReportPage } from "../src/pages/StrategyReportPage";
import { defaultStrategyConfig } from "../src/lib/strategyStore";
Object.defineProperty(globalThis,"sessionStorage",{value:window.sessionStorage,configurable:true});
Object.defineProperty(globalThis,"Window",{value:window.constructor,configurable:true});
Object.defineProperty(globalThis,"getComputedStyle",{value:window.getComputedStyle.bind(window),configurable:true});
window.requestAnimationFrame=fn=>window.setTimeout(()=>fn(0),0);
window.cancelAnimationFrame=window.clearTimeout;
window.Range.prototype.getClientRects=()=>[] as any;
window.Range.prototype.getBoundingClientRect=()=>({top:0,bottom:0,left:0,right:0,width:0,height:0}) as any;
const originalFetch=globalThis.fetch;
let sequence=0;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;sessionStorage.clear();});
for(const custom of [false,true]) {
  test(custom?"embedded strategy keeps report navigation in quant workspace":"default strategy report navigation remains unchanged",async()=>{
    sessionStorage.setItem("svquant_user",JSON.stringify({id:9900+ ++sequence,username:"strategy_test"}));
    let project:any={id:"q-strategy",name:"test",description:"hypothesis",createdAt:"",updatedAt:"",runCount:0,config:defaultStrategyConfig()};
    let saved:any,backtests=0;
    globalThis.fetch=async(url,init)=>{
      const path=new URL(String(url),"http://localhost").pathname;
      const body=init?.body?JSON.parse(String(init.body)):null;
      if(path==="/api/strategy/projects/q-strategy"){if(body)project={...project,...body};return Response.json({project});}
      if(path==="/api/factor/re-catalog")return Response.json({factors:[]});
      if(path==="/api/factor/index")return new Response("libraries: {}");
      if(path==="/api/factor/libraries/factors")return Response.json({factors:[]});
      if(path==="/api/backtest/strategy"){backtests++;return Response.json({metrics:{sharpe:0.2},meta:{spec_hash:"fixture-spec"}});}
      if(path==="/api/strategy/runs"){saved=body;return Response.json({run:{...body,id:"saved-strategy"},project});}
      throw Error("Unexpected "+path);
    };
    const root=custom?"/quant/strategy":"/strategy/research";
    const view=render(<ConfirmProvider><MemoryRouter initialEntries={[root+"/q-strategy"]}><Routes>
      <Route path={root+"/:projectId"} element={<StrategyBacktestPage navigation={custom?{listPath:root,projectPath:id=>root+"/"+id,reportPath:id=>root+"/report/"+id,historyPath:id=>root+"/"+id+"/reports"}:undefined}/>}/>
      <Route path={root+"/report/:runId"} element={<p>Saved report route</p>}/>
    </Routes></MemoryRouter></ConfirmProvider>);
    await waitFor(()=>assert.ok(view.container.querySelector(".cm-editor")),{timeout:15000});
    const history=view.getByRole("link",{name:/回测报告/});
    assert.equal(history.getAttribute("href"),root+"/q-strategy/"+(custom?"reports":"history"));
    fireEvent.click(view.getByRole("button",{name:"进行回测"}));
    await waitFor(()=>assert.ok(view.getByText("Saved report route")),{timeout:6000});
    assert.equal(backtests,1);
    assert.equal(saved.projectId,"q-strategy");
    assert.equal(saved.result.meta.spec_hash,"fixture-spec");
  });
}
test("missing strategy report returns to injected list",async()=>{
  sessionStorage.setItem("svquant_user",JSON.stringify({id:9900+ ++sequence,username:"strategy_test"}));
  globalThis.fetch=async()=>Response.json({detail:"not found"},{status:404});
  const view=render(<ConfirmProvider><MemoryRouter initialEntries={["/quant/strategy/report/missing"]}><Routes>
    <Route path="/quant/strategy/report/:runId" element={<StrategyReportPage navigation={{listPath:"/quant/strategy/reports"}}/>}/>
  </Routes></MemoryRouter></ConfirmProvider>);
  await waitFor(()=>assert.ok(view.getByText("没有找到回测结果。")));
  assert.equal(view.getByRole("link",{name:"返回策略研究"}).getAttribute("href"),"/quant/strategy/reports");
});
