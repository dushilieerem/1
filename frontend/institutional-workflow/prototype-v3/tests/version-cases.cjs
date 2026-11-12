'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../src/config.js'),M=require('../src/model.js'),B=JSON.parse(fs.readFileSync(path.join(__dirname,'../../docs/2026-11-04-business-fishbones/design.json'),'utf8'));
test('提交时证据与输入快照不随任务编辑或重算改变',()=>{
 const s=M.makeState(C,B),t=M.selected(s,'factor');for(const id of ['F4','F5','F6'])M.execute(s,t,id,C);
 const r=s.reviews.find(r=>r.taskId===t.id&&r.type==='研究准入'),frozen=JSON.stringify(r.evidence),old=M.artifact(t,'F4').id;
 M.edit(s,t,'experimentNote','修订检验说明','F4',C);M.execute(s,t,'F4',C);
 assert.equal(JSON.stringify(r.evidence),frozen);assert.notEqual(r.snapshot.values.experimentNote,t.values.experimentNote);assert.equal(r.status,'expired');assert.equal(t.current,'F4');assert.equal(M.artifact(t,'F4',old).id,old);assert.notEqual(M.artifact(t,'F4').id,old);assert.throws(()=>M.artifact(t,'F4','missing'),/不存在/);
});
test('输入未改但上游重算，也会使旧资金授权不能再部署',()=>{
 const s=M.makeState(C,B),t=M.selected(s,'portfolio');M.execute(s,t,'P3',C);M.execute(s,t,'P4',C);
 let r=s.reviews.find(r=>r.taskId===t.id);s.persona='投资负责人';M.decide(s,r.id,'approved','原型授权');M.execute(s,t,'P5',C);
 M.execute(s,t,'P3',C);assert.equal(t.outputs.P4.stale,true);assert.throws(()=>M.execute(s,t,'P5',C),/审批/);
 M.execute(s,t,'P4',C);r=s.reviews.find(r=>r.taskId===t.id);assert.equal(r.status,'pending');assert.throws(()=>M.execute(s,t,'P5',C),/审批/);
 M.decide(s,r.id,'approved','新证据通过');assert.ok(M.execute(s,t,'P5',C));
});
test('重新生成同输入版本的资产也保留旧准入资产与报告',()=>{
 const s=M.makeState(C,B),t=M.selected(s,'factor');for(const id of ['F4','F5','F6'])M.execute(s,t,id,C);
 const r=s.reviews.find(r=>r.taskId===t.id),a=s.assets.factor.find(a=>a.id===r.assetId);M.decide(s,r.id,'approved','允许共享');const before=JSON.stringify(a);
 M.execute(s,t,'F6',C);assert.equal(JSON.stringify(a),before);assert.equal(s.assets.factor.filter(a=>a.taskId===t.id).length,2);
});
