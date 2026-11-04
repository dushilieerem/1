import { QuantLayout } from "../src/pages/institutional-workflow/QuantLayout";
import { useConfirm } from "../src/components/ConfirmDialog";
import { listProjects, getProject } from "../src/lib/detectStore";
import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { LoginPage } from "../src/pages/LoginPage";
import { setQuantSession, clearQuantSession, getQuantSession, safeLoginNext, type QuantSession } from "../src/lib/quantAuth";
import { researchFetch, researchIdentity, getStoredUser, researchPagePath } from "../src/lib/researchClient";
Object.defineProperty(globalThis, "sessionStorage", {value: window.sessionStorage, configurable:true});
const originalFetch = globalThis.fetch;
const session: QuantSession = {token:"quant-only-token",product:"quant",user:{id:71,username:"researcher"},org:{id:21,code:"quant-test",name_cn:"测试机构"},permissions:{quant:"write"}};
function quant() { window.history.replaceState({}, "", "/quant/factor"); setQuantSession(session); }
afterEach(()=>{ cleanup(); globalThis.fetch=originalFetch; sessionStorage.clear(); window.history.replaceState({}, "", "/"); });
test("institutional login exposes both products and selects quant from destination",()=>{
 const v=render(<MemoryRouter initialEntries={["/login?mode=inst&next=%2Fquant%2Ffactor"]}><LoginPage/></MemoryRouter>);
 assert.ok(v.getByRole("heading",{name:"机构量化登录"}));
 assert.ok(v.getByRole("button",{name:"进入机构量化平台"}));
 assert.equal(v.queryByText(/开发环境演示账号/),null);
 fireEvent.click(v.getByRole("button",{name:"主观投资"}));
 assert.ok(v.getByRole("heading",{name:"机构主观投资登录"}));
});
test("existing institutional login defaults to subjective, personal login stays personal",()=>{
 let v=render(<MemoryRouter initialEntries={["/login?mode=inst"]}><LoginPage/></MemoryRouter>);
 assert.ok(v.getByRole("heading",{name:"机构主观投资登录"}));cleanup();
 v=render(<MemoryRouter initialEntries={["/login"]}><LoginPage/></MemoryRouter>);
 assert.ok(v.getByRole("heading",{name:"登录"}));
});
test("redirect targets remain within selected product and reject external or lookalike paths",()=>{
 for(const next of ["//evil.test","/\\evil.test","/quantized","/quant/../inst","/inst","/quant\n/evil"]) assert.equal(safeLoginNext(next,"quant"),"/quant");
 assert.equal(safeLoginNext("/quant/factor?runId=1","quant"),"/quant/factor?runId=1");
 assert.equal(safeLoginNext("/quant/factor","subjective"),"/inst");
 assert.equal(safeLoginNext("/inst/ideas","subjective"),"/inst/ideas");
 assert.equal(safeLoginNext("/instx","subjective"),"/inst");
});
test("quant research uses independent token and a scoped API, never personal credentials",async()=>{
 sessionStorage.setItem("svquant_user",JSON.stringify({id:8,username:"personal"}));
 sessionStorage.setItem("svquant_token","personal-token");
 sessionStorage.setItem("svquant_inst_token","subjective-token");quant();
 assert.equal(getStoredUser()?.id,71);
 globalThis.fetch=async(input,init)=>{
 assert.equal(String(input),"/api/inst/quant/detect/projects?_uid=71");
 assert.equal(new Headers(init?.headers).get("Authorization"),"Bearer quant-only-token");
 return Response.json({projects:[]});};
 await researchFetch("/api/detect/projects?_uid=71");
 assert.equal(sessionStorage.getItem("svquant_token"),"personal-token");
 assert.equal(researchPagePath("/factor/detect/abc"),"/quant/factor/abc");
});
test("public catalog reads never carry any account token",async()=>{
 quant();globalThis.fetch=async(input,init)=>{
 assert.equal(String(input),"/api/factor/re-catalog");
 assert.equal(new Headers(init?.headers).get("Authorization"),null);
 return Response.json({});};
 await researchFetch("/api/factor/re-catalog",{headers:{Authorization:"Bearer accidental"}});
});
test("unapproved APIs, external hosts, catalog mutations and read-only writes fail closed",async()=>{
 quant(); let calls=0;globalThis.fetch=async()=>{calls++;return Response.json({});};
 for(const path of ["/api/community/new","https://external.test/api/detect/projects","/api/inst/me","/api/strategy/library/sync"])
 await assert.rejects(researchFetch(path,{method:"POST"}));
 setQuantSession({...session,permissions:{quant:"read"}});
 await assert.rejects(researchFetch("/api/detect/projects",{method:"POST"}));
 assert.equal(calls,0);
});
test("same member in different org changes cache identity; logout invalidates in-flight results",async()=>{
 quant();const key=researchIdentity();
 setQuantSession({...session,org:{...session.org,id:22}});assert.notEqual(researchIdentity(),key);
 let finish:(r:Response)=>void=()=>{};
 globalThis.fetch=async()=>new Promise<Response>(r=>{finish=r;});
 const request=researchFetch("/api/detect/runs");
 clearQuantSession();finish(Response.json({runs:[{id:"old"}]}));
 await assert.rejects(request,/身份已变化/);assert.equal(getQuantSession(),null);
});
test("personal pages preserve the original request without institutional remapping",async()=>{
 quant();window.history.replaceState({},"","/factor/library");
 globalThis.fetch=async(input,init)=>{
 assert.equal(input,"/api/detect/projects");assert.equal((init?.headers as any).Authorization,"Bearer personal");
 return Response.json({});};
 await researchFetch("/api/detect/projects",{headers:{Authorization:"Bearer personal"}});
});

test("institutional shell validates membership and supplies existing tool dialog context",async()=>{
 quant();
 globalThis.fetch=async(input,init)=>{
   assert.equal(String(input),"/api/inst/quant/me");
   assert.equal(new Headers(init?.headers).get("Authorization"),"Bearer quant-only-token");
   return Response.json(session);
 };
 function Tool() { const ask = useConfirm(); return <button onClick={()=>void ask({title:"入库确认",message:"保存到成员私有资产库"})}>工具操作</button>; }
 const v=render(<MemoryRouter initialEntries={["/quant/factor"]}><Routes><Route element={<QuantLayout/>}><Route path="/quant/factor" element={<Tool/>}/></Route></Routes></MemoryRouter>);
 await waitFor(()=>assert.ok(v.getByRole("button",{name:"工具操作"})));
 assert.ok(v.getByText("机构量化平台"));assert.ok(v.getByText(/测试机构/));
 fireEvent.click(v.getByRole("button",{name:"工具操作"}));
 assert.ok(v.getByRole("dialog",{name:"入库确认"}));
});
test("revoked quant access never falls back to a previously cached research project",async()=>{
 quant();let reject=false;
 globalThis.fetch=async()=>reject?Response.json({detail:"机构成员已停用"},{status:401}):Response.json({projects:[{id:"private",config:{},name:"旧私有项目"}]});
 await listProjects();reject=true;
 assert.equal(await getProject("private"),undefined);
 assert.equal(getQuantSession(),null);
});
