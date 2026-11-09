import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
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
test("embedded detector retains RE run id and follows the injected report route",async()=>{
  identity();let saved:any;
  let project:any={id:"q-run",name:"研究",factorName:"ui_factor",description:"研究假设",createdAt:"",updatedAt:"",runCount:0,
    config:{...defaultConfig(["ui_factor"]),source:{name:"ui_factor",code},draftFactor:{name:"ui_factor",description:"研究假设",category:"test",body:code}}};
  globalThis.fetch=async(url,init)=>{
    const path=new URL(String(url),"http://localhost").pathname;
    const body=init?.body?JSON.parse(String(init.body)):null;
    if(path==="/api/detect/projects/q-run"){if(body)project=body;return Response.json({project});}
    if(path.endsWith("/q-run/runs"))return Response.json({runs:[]});
    if(path==="/api/factor/re-catalog")return Response.json({factors:[]});
    if(path==="/api/factor/index")return new Response("libraries: {}");
    if(path==="/api/factor/libraries/factors")return Response.json({factors:[]});
    if(path==="/api/backtest/factor")return Response.json({run_id:"engine-123",status:"queued"},{status:202});
    if(path==="/api/backtest/factor/engine-123")return Response.json({run_id:"engine-123",status:"succeeded",result:{metrics:{ic:0.03},meta:{data_release_id:"fixture-release",spec_hash:"fixture-spec"}}});
    if(path==="/api/detect/runs"){saved=body;return Response.json({run:{...body,id:"saved-report"},project});}
    throw Error("Unexpected "+path);
  };
  const view=render(<MemoryRouter initialEntries={["/quant/factor/q-run"]}><Routes>
    <Route path="/quant/factor/:projectId" element={<FactorDetectPage navigation={{listPath:"/quant/factor/reports",reportPath:id=>"/quant/factor/report/"+id}}/>}/>
    <Route path="/quant/factor/report/:runId" element={<p>机构端报告</p>}/>
  </Routes></MemoryRouter>);
  await waitFor(()=>assert.ok(view.container.querySelector(".cm-editor")),{timeout:15000});
  fireEvent.click(view.getByRole("button",{name:"进行检测"}));
  await waitFor(()=>assert.ok(view.getByText("机构端报告")),{timeout:6000});
  assert.equal(saved.request._re_run_id,"engine-123");
  assert.equal(saved.result.meta.data_release_id,"fixture-release");
  assert.equal(saved.request.factor_code,code);
});
