import './domSetup.mjs';
import React from 'react';
import test,{afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {render,cleanup,waitFor,fireEvent} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {FactorEvidencePanel} from '../src/pages/institutional-workflow/FactorEvidencePanel';
const originalFetch=globalThis.fetch;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;});
const candidate=(status='development_passed',stale=false)=>({id:'c',status,stale,snapshot_hash:'abc',events:[],evidence:{development:{run_id:'real-run',report_id:'report',gate:{passed:status==='development_passed',checks:[{name:'IC',actual:.05,operator:'>=',threshold:.01,passed:true}]}}}});
function mock(c:any){globalThis.fetch=async(url,init)=>{const p=String(url);if(init?.method==='POST')return Response.json({detail:'服务端拒绝，输入已保留'},{status:409});if(p.endsWith('/libraries'))return Response.json({libraries:[]});return Response.json(p.endsWith('/projects/p/candidates')?{candidates:[c]}:c);};}
function mount(step:'F4'|'F5'|'F6'){return render(<MemoryRouter><FactorEvidencePanel projectId="p" step={step}/></MemoryRouter>);}
test('failed development cannot run validation',async()=>{mock(candidate('development_failed'));const v=mount('F5');await waitFor(()=>assert.equal((v.getByRole('button',{name:'运行冻结候选的样本外复验'}) as HTMLButtonElement).disabled,true));});
test('stale candidate cannot run validation',async()=>{mock(candidate('development_passed',true));const v=mount('F5');await waitFor(()=>assert.equal((v.getByRole('button',{name:'运行冻结候选的样本外复验'}) as HTMLButtonElement).disabled,true));assert.ok(v.getByText(/当前研究输入已变更/));});
test('out-of-sample pass never unlocks formal admission',async()=>{mock(candidate('validation_passed'));const v=mount('F6');await waitFor(()=>assert.equal((v.getByRole('button',{name:'正式准入暂不可用'}) as HTMLButtonElement).disabled,true));});
test('archive error retains researcher conclusions',async()=>{mock(candidate('validation_failed'));const v=mount('F6');await waitFor(()=>assert.ok(v.getByLabelText('研究结论与适用限制')));fireEvent.change(v.getByLabelText('研究结论与适用限制'),{target:{value:'失败实验仍保留结论'}});fireEvent.click(v.getByRole('button',{name:'保存因子卡与研究证据'}));await waitFor(()=>assert.ok(v.getByRole('alert')));assert.equal((v.getByLabelText('研究结论与适用限制') as HTMLTextAreaElement).value,'失败实验仍保留结论');});
