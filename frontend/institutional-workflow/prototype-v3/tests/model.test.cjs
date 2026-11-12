'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../src/config.js'),M=require('../src/model.js');
const B={modules:JSON.parse(fs.readFileSync(path.join(__dirname,'../../docs/2026-11-04-business-fishbones/design.json'),'utf8'))};
if(!Array.isArray(B.modules))Object.assign(B,B.modules);
if(!B.roles){B.roles={};for(const m of B.modules)Object.assign(B.roles,m.roles||{});}
function fresh(){return M.makeState(C,B);}
function task(s,id){return M.selected(s,id);}
function run(s,t,...stages){for(const id of stages)M.execute(s,t,id,C);return t;}
function funding(s){const t=task(s,'portfolio');run(s,t,'P3','P4');return [t,s.reviews.find(r=>r.taskId===t.id&&r.type==='资金方案')];}

test('所有业务步骤有人工字段、操作、工具与产物契约，职责可映射',()=>{
 assert.equal(B.modules.length,5);assert.equal(Object.keys(C.stages).length,30);assert.equal(Object.keys(B.roles).length,18);
 for(const m of B.modules){assert.equal(m.stages.length,6);for(const stage of m.stages){const c=C.stages[stage.id];assert.ok(c);assert.ok(c.fields.length>=4);assert.equal(c.tools.length,3);assert.ok(c.result);for(const role of stage.roles)assert.ok(B.roles[role],role);}}
});
test('已有因子可立即建立下游策略；探索用途不需要新上游任务完成',()=>{
 const s=fresh();const count=s.tasks.length,t=M.selectAsset(s,'factor','F-003',C);
 assert.equal(s.tasks.length,count+1);assert.equal(t.module,'strategy');assert.deepEqual(t.values.factors,['F-003']);assert.equal(t.upstream.version,'draft-2');assert.equal(M.validation(s,t,'S1',C).length,0);
});
test('隔离数据与未准入策略不能跨越用途门槛',()=>{
 const s=fresh();assert.throws(()=>M.selectAsset(s,'dataset','D-003',C),/隔离/);
 s.assets.strategy[0].status='research';assert.throws(()=>M.selectAsset(s,'strategy','S-001',C),/准入/);
 const t=M.selectAsset(s,'dataset','D-001',C);assert.equal(t.values.dataset,'D-001');
});
test('输入约束覆盖空数字、错误区间、表达式和缺少前置证据',()=>{
 const s=fresh(),d=task(s,'data'),f=M.newTask(s,'factor',C,'无上游');
 d.values.start='2026-11-04';d.values.end='2026-11-01';assert.ok(M.validation(s,d,'D2',C).some(x=>x.includes('开始日期')));
 f.values.expression='close / (';assert.ok(M.validation(s,f,'F3',C).some(x=>x.includes('表达式')));
 f.values.expression='eval(close)';assert.ok(M.validation(s,f,'F3',C).some(x=>x.includes('表达式')));
 const numeric=C.stages.F4.fields.find(x=>x.type==='number');f.values[numeric.key]='';assert.ok(M.validation(s,f,'F4',C).some(x=>x.includes(numeric.label)));
 assert.throws(()=>M.execute(s,f,'F5',C),/F4/);
});
test('低质量因子自动留档，不进入人工待审；阻止后续正式验证',()=>{
 const s=fresh(),t=task(s,'factor');t.values.minIC=0.2;const pending=s.reviews.filter(r=>r.status==='pending').length;
 const out=M.execute(s,t,'F4',C);assert.equal(out.passed,false);assert.equal(s.reviews[0].status,'archived');assert.equal(s.reviews.filter(r=>r.status==='pending').length,pending);assert.throws(()=>M.execute(s,t,'F5',C),/F4/);
});
test('普通实验可留档；正式候选必须有独立验证及确认材料',()=>{
 const s=fresh(),t=M.newTask(s,'factor',C,'普通实验');
 t.values.usage='仅研究留档';t.values.selection='仅留档，不送审';M.execute(s,t,'F6',C);assert.ok(s.assets.factor.some(a=>a.taskId===t.id&&a.status==='research'));assert.ok(!s.reviews.some(r=>r.taskId===t.id));
 t.values.usage='共享研究准入';t.values.selection='符合条件后送审';assert.throws(()=>M.execute(s,t,'F6',C),/独立验证/);
 const candidate=M.getTask(s,'factor-2');candidate.values.evidence=false;assert.throws(()=>M.execute(s,candidate,'F6',C),/确认/);
});
test('独立验证拒绝缺少尝试记录或隔离约定',()=>{
 const s=fresh(),t=task(s,'factor');run(s,t,'F4');t.values.isolate=false;assert.throws(()=>M.execute(s,t,'F5',C),/隔离/);t.values.isolate=true;t.values.attempts=false;assert.throws(()=>M.execute(s,t,'F5',C),/尝试/);
});
test('因子准入经过证据、送审、人工批准，可保留旧资产版本',()=>{
 const s=fresh(),t=task(s,'factor');run(s,t,'F4','F5','F6');const r=s.reviews.find(r=>r.taskId===t.id&&r.type==='研究准入');assert.equal(r.status,'pending');
 M.decide(s,r.id,'approved','证据齐备，允许共享研究');const old=s.assets.factor.find(a=>a.id===r.assetId);assert.equal(old.status,'approved');
 M.edit(s,t,'assetSummary','补充用途说明','F6',C);M.execute(s,t,'F6',C);const versions=s.assets.factor.filter(a=>a.taskId===t.id);assert.equal(versions.length,2);assert.equal(old.status,'approved');assert.notEqual(versions[0].version,versions[1].version);
});
test('审查要求正确身份、理由、硬条件且只处理待审事项',()=>{
 const s=fresh();s.persona='研究员';assert.throws(()=>M.decide(s,'RV-001','approved','通过'),/研究负责人/);
 s.persona='研究负责人';assert.throws(()=>M.decide(s,'RV-001','approved',''),/理由/);
 s.reviews[0].hardPass=false;assert.throws(()=>M.decide(s,'RV-001','approved','想通过'),/硬条件/);
 s.reviews[0].hardPass=true;M.decide(s,'RV-001','returned','需要补充成本比较');assert.equal(s.reviews[0].status,'returned');assert.throws(()=>M.decide(s,'RV-001','approved','再次操作'),/待审/);
});
test('修改上游输入保留旧报告但标记失效，并使待审申请失效',()=>{
 const s=fresh(),t=M.getTask(s,'factor-2'),id=t.outputs.F5.id;M.edit(s,t,'expression','close / delay(close, 10)','F3',C);
 assert.equal(t.outputs.F2.stale,true);assert.equal(t.outputs.F3.stale,true);assert.equal(t.outputs.F5.id,id);assert.equal(s.reviews[0].status,'expired');assert.equal(M.stageStatus(t,'F5'),'stale');assert.throws(()=>M.decide(s,'RV-001','approved','过期'),/待审/);
});
test('共享字段变更使所有使用该字段的步骤及后续证据失效',()=>{
 const s=fresh(),t=M.getTask(s,'factor-2');M.edit(s,t,'expression','close','F3',C);
 assert.equal(t.outputs.F1.stale,false);assert.equal(t.outputs.F2.stale,true);assert.equal(t.outputs.F3.stale,true);assert.equal(M.stageStatus(t,'F2'),'stale');
 const d=fresh(),u=M.getTask(d,'factor-2');M.edit(d,u,'dataset','D-002','F3',C);assert.equal(u.outputs.F1.stale,true);assert.equal(M.stageStatus(u,'F1'),'stale');
 const m=fresh(),v=M.getTask(m,'factor-2');M.edit(m,v,'minIC',0.03,'F4',C);assert.equal(v.outputs.F2.stale,true);assert.equal(M.stageStatus(v,'F2'),'stale');
});
test('取消 AI 执行不产生新产物且留停止记录',()=>{
 const s=fresh(),t=task(s,'factor'),j=M.startJob(t,'F4','execute',C);M.advanceJob(j);M.cancelJob(j);
 assert.equal(M.executeJob(s,t,j,C),null);assert.equal(t.outputs.F4,undefined);assert.equal(j.status,'cancelled');assert.equal(M.advanceJob(j),false);assert.ok(j.events.some(e=>e.status==='cancelled'));
});
test('AI 填写使用启动时快照；人修改后需显式应用，不自动覆盖',()=>{
 const s=fresh(),t=task(s,'factor'),original=t.values.expression,j=M.startJob(t,'F2','fill',C);
 M.edit(s,t,'expression','人工新表达式','F2',C);const result=M.completeFill(s,t,j,C);
 assert.equal(result.conflict,true);assert.equal(t.values.expression,'人工新表达式');assert.equal(t.patch.values.expression,original);
 M.applyPatch(s,t,t.patch,C);assert.equal(t.values.expression,original);assert.equal(t.patch,null);
});
test('AI 执行互斥、错误与刷新中断都不会伪造成功',()=>{
 const s=fresh(),t=task(s,'factor'),j=M.startJob(t,'F4','execute',C,'failure');
 assert.throws(()=>M.startJob(t,'F4','fill',C),/运行/);assert.throws(()=>M.edit(s,t,'minIC',0.031,'F4',C),/停止/);M.executeJob(s,t,j,C);assert.equal(j.status,'failed');assert.equal(t.outputs.F4,undefined);
 const next=M.startJob(t,'F4','execute',C);M.recover(s);assert.equal(next.status,'interrupted');assert.equal(M.executeJob(s,t,next,C),null);
});
test('策略观察时间不足只留档，不形成合格待审候选',()=>{
 const s=fresh(),t=task(s,'strategy');run(s,t,'S3','S4','S5');t.values.observedDays=5;
 const out=M.execute(s,t,'S6',C);assert.equal(out.passed,false);assert.ok(s.reviews.some(r=>r.taskId===t.id&&r.status==='archived'));assert.ok(!s.reviews.some(r=>r.taskId===t.id&&r.status==='pending'));
});
test('数据发布需要质量通过、合适身份和不可变版本约定',()=>{
 const s=fresh(),t=task(s,'data');run(s,t,'D3','D4');assert.throws(()=>M.execute(s,t,'D5',C),/数据负责人/);
 s.persona='数据负责人';t.values.immutable=false;assert.throws(()=>M.execute(s,t,'D5',C),/历史版本/);t.values.immutable=true;M.execute(s,t,'D5',C);assert.ok(s.assets.dataset.some(a=>a.taskId===t.id&&a.status==='published'));
 M.edit(s,t,'coverage',100,'D4',C);M.execute(s,t,'D4',C);assert.throws(()=>M.execute(s,t,'D5',C),/D4/);
});
test('资金配置检查权重合计、集中度与独立风险材料',()=>{
 const s=fresh(),t=task(s,'portfolio');t.values.weight1=60;t.values.weight2=60;assert.throws(()=>M.execute(s,t,'P3',C),/100%/);t.values.weight1=70;t.values.weight2=20;assert.throws(()=>M.execute(s,t,'P3',C),/上限/);
 t.values.weight1=50;t.values.weight2=40;M.execute(s,t,'P3',C);t.values.riskEvidence=false;assert.throws(()=>M.execute(s,t,'P4',C),/独立风险/);
});
test('部署必须绑定已批版本，实盘禁止，重复模拟部署幂等',()=>{
 const s=fresh(),[t,r]=funding(s);assert.throws(()=>M.execute(s,t,'P5',C),/审批/);
 s.persona='投资负责人';M.decide(s,r.id,'approved','按固定方案进行模拟');const first=M.execute(s,t,'P5',C),second=M.execute(s,t,'P5',C);assert.equal(first.id,second.id);
 M.edit(s,t,'deployVersion','portfolio-v2','P5',C);assert.throws(()=>M.execute(s,t,'P5',C),/审批/);
 t.values.environment='实盘环境（本原型不接入）';assert.throws(()=>M.execute(s,t,'P5',C),/不接入实盘/);
});
test('硬风险不能只观察；恢复需复测回执与风控决定',()=>{
 const s=fresh(),t=task(s,'monitor');run(s,t,'T2');s.persona='风控负责人';t.values.measure='继续观察';assert.throws(()=>M.execute(s,t,'T3',C),/硬限制/);
 t.values.measure='暂停新增风险';M.execute(s,t,'T3',C);t.values.retested=false;assert.throws(()=>M.execute(s,t,'T4',C),/复测/);t.values.retested=true;M.execute(s,t,'T4',C);
 assert.equal(s.incidents[0].status,'open');const r=s.reviews.find(x=>x.type==='风险恢复');M.decide(s,r.id,'approved','措施和复测证据齐全');assert.equal(s.incidents[0].status,'resolved');
});
test('方法发布要求当前版本评测及管理员，修改后旧评测失效',()=>{
 const s=fresh(),id='F-A1';M.evaluateMethod(s,id);assert.throws(()=>M.publishMethod(s,id),/管理员/);
 s.persona='平台管理员';M.publishMethod(s,id);const prior=s.methods[id].published;
 M.saveMethod(s,id,{prompt:'这是经过修订的因子研究方法，要求使用受控工具并保留数据版本、实验记录与失败证据。',skills:'factor-query\nfactor-calc',knowledge:'研究规范'});
 assert.equal(s.methods[id].published,prior);assert.throws(()=>M.publishMethod(s,id),/评测/);M.evaluateMethod(s,id);M.publishMethod(s,id);assert.equal(s.methods[id].published,s.methods[id].version);
});
test('运行计划拒绝非法额度和任务数；保存不启动真实作业',()=>{
 const s=fresh(),count=s.tasks.length;assert.throws(()=>M.savePlan(s,'factor',{budget:0,maxTasks:5}),/额度/);assert.throws(()=>M.savePlan(s,'factor',{budget:200000,maxTasks:'abc'}),/上限/);
 assert.throws(()=>M.savePlan(s,'factor',{budget:200000,maxTasks:1.5}),/上限/);M.savePlan(s,'factor',{enabled:true,budget:200000,maxTasks:5,trigger:'每日盘后',scope:'量价因子'});assert.equal(s.tasks.length,count);assert.equal(s.plans.factor.enabled,true);
});
