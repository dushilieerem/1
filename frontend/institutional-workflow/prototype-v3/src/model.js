(function(root,factory){const value=factory();if(typeof module==='object')module.exports=value;else root.ProtoModel=value;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const clone=v=>JSON.parse(JSON.stringify(v));
let serial=0;
const uid=p=>p+'-'+Date.now().toString(36)+'-'+(++serial);
const stamp=()=>new Date().toISOString();
const levels={data:'D',factor:'F',strategy:'S',portfolio:'P',monitor:'T'};
function defaults(module,config){const v={};for(let i=1;i<=6;i++)for(const f of config.stages[levels[module]+i].fields)if(!(f.key in v))v[f.key]=clone(f.value);return v;}
function task(module,config,name){return {id:uid(module),module,name:name||defaults(module,config).name||'新的'+({monitor:'运行检查',data:'数据任务',factor:'因子研究',strategy:'策略研究',portfolio:'组合研究'}[module]),revision:1,values:defaults(module,config),outputs:{},history:[],jobs:[],messages:[],patch:null,current:levels[module]+'1',updated:stamp()};}
function makeState(config,blueprint){
 const state={schema:3,persona:'研究负责人',tasks:[],selected:{},reviews:[],events:[],methods:{},plans:{},assets:{
 dataset:[{id:'D-001',name:'A股日频研究快照',version:'v20261103',status:'published',detail:'场景数据 · 行情、交易状态、复权事件',expr:'2024-01-02 → 2026-11-03',use:'研究可用'},{id:'D-002',name:'公司财务与公告',version:'v20261031',status:'published',detail:'场景数据 · 报表、公告、历史可用时间',expr:'按公告时点发布',use:'研究可用'},{id:'D-003',name:'新闻事件加工批次',version:'draft-3',status:'isolated',detail:'场景数据 · 实体匹配待复核',expr:'质量问题：部分来源时间缺失',use:'隔离中'}],
 factor:[{id:'F-001',name:'20日低波动',version:'v1.2',status:'approved',detail:'已完成研究准入 · 场景资产',expr:'-1 * ts_std(close / delay(close, 1) - 1, 20)',use:'共享研究'},{id:'F-002',name:'5日价格反转',version:'v1.0',status:'pending',detail:'独立证据齐备 · 待研究负责人审查',expr:'-1 * (close / delay(close, 5) - 1)',use:'仅研究'},{id:'F-003',name:'成交量偏离',version:'draft-2',status:'research',detail:'探索资产 · 尚未完成独立验证',expr:'volume / ts_mean(volume, 20) - 1',use:'仅研究'}],
 strategy:[{id:'S-001',name:'低波均衡策略',version:'v2.1',status:'approved',detail:'场景资产 · 每周调仓 / 稳健选股',expr:'低波动排序 + 集中度约束',use:'可申请配置'},{id:'S-002',name:'质量动量策略',version:'v1.3',status:'approved',detail:'场景资产 · 月度调仓 / 多因子融合',expr:'质量与动量融合 + 风险约束',use:'可申请配置'}],
 portfolio:[{id:'P-001',name:'稳健模拟组合',version:'v1.0',status:'approved',detail:'仅为模拟场景 · 无真实资金',expr:'低波均衡 50% + 质量动量 40% + 现金 10%',use:'模拟'}]},
 incidents:[{id:'E-001',name:'日频行情更新延迟',level:'高',status:'open',object:'行情快照 / 低波均衡策略',hard:true,note:'场景预设：新风险暴露已限制，等待补采复验。'},{id:'E-002',name:'模拟交易成本偏离预期',level:'中',status:'open',object:'质量动量策略',hard:false,note:'场景预设：需核对成本与成交假设。'}]};
 for(const m of blueprint.modules){const t=task(m.id,config);t.id=m.id+'-1';t.current=m.code+({data:3,factor:4,strategy:3,portfolio:3,monitor:2}[m.id]);if(!t.values.name)t.values.name=t.name;t.name=t.values.name;
 for(let i=1;i<Number(t.current.slice(1));i++)t.outputs[m.code+i]={id:uid('sample'),stage:m.code+i,revision:1,passed:true,sample:true,stale:false,title:config.stages[m.code+i].result,summary:'场景预置的上游产物，可继续操作。',snapshot:clone(t.values),metrics:[],rows:[['来源','预置研究场景']],created:'2026-11-04T01:30:00Z'};
 state.tasks.push(t);state.selected[m.id]=t.id;state.plans[m.id]={enabled:false,trigger:'每日盘后',budget:200000,maxTasks:5,scope:m.purpose};}
 const candidate=task('factor',config,'5日反转 · 准入材料');candidate.id='factor-2';candidate.current='F6';candidate.values.assetName='5日价格反转';candidate.values.name=candidate.name;for(let i=1;i<=5;i++)candidate.outputs['F'+i]={id:'sample-factor-'+i,stage:'F'+i,revision:1,passed:true,sample:true,stale:false,title:config.stages['F'+i].result,summary:'场景预置证据包，报告与冻结版本匹配。',snapshot:clone(candidate.values),metrics:[],rows:[['版本','factor-candidate-v1']],created:'2026-11-04T01:32:00Z'};state.tasks.push(candidate);
 state.reviews=[{id:'RV-001',taskId:candidate.id,module:'factor',type:'研究准入',name:'5日价格反转',version:'v1.0',revision:1,assetId:'F-002',hardPass:true,riskPass:true,status:'pending',summary:'样例：覆盖、独立验证与重复检查满足预设政策；需确认共享研究用途。',checks:[['定义与数据版本','通过'],['独立验证证据','通过'],['重复与增量检查','通过']],created:'2026-11-04T01:40:00Z',audit:[]},
 {id:'RV-002',taskId:null,module:'factor',type:'研究筛选',name:'高换手短周期候选',version:'draft-1',revision:1,hardPass:false,riskPass:false,status:'archived',summary:'样例：成本敏感性不满足预设门槛，自动留档。',checks:[['成本敏感性','不通过'],['送审门槛','未达到']],created:'2026-11-04T01:20:00Z',audit:[]}];
 state.reviews[0].snapshot=snapshot(candidate);state.reviews[0].evidence=clone(Object.values(candidate.outputs));
 for(const [id,r] of Object.entries(blueprint.roles))state.methods[id]={version:1,published:1,prompt:'目标：'+r.mission+'\n交付：'+r.output+'\n边界：'+r.boundary,skills:r.tools.split('、').slice(0,4).join('\n'),knowledge:'公司研究规范 / 已授权知识与历史失败案例',evalStatus:'未评测',evalVersion:null};
 return state;
}
function getTask(state,id){const t=state.tasks.find(x=>x.id===id);if(!t)throw Error('研究任务不存在');return t;}
function selected(state,module){return getTask(state,state.selected[module]);}
function addEvent(state,text,kind='研究'){state.events.unshift({id:uid('event'),time:stamp(),text,kind});state.events=state.events.slice(0,100);}
function newTask(state,module,config,name){const t=task(module,config,name);if(name)t.values.name=name;state.tasks.unshift(t);state.selected[module]=t.id;addEvent(state,'建立'+t.name);return t;}
function selectAsset(state,assetType,id,config){const asset=state.assets[assetType].find(x=>x.id===id);if(!asset)throw Error('资产不存在');
 const next={dataset:'factor',factor:'strategy',strategy:'portfolio'}[assetType];if(!next)throw Error('该资产没有下游研究入口');
 if(assetType==='dataset'&&asset.status!=='published')throw Error('隔离数据不可用于研究，请先处理质量问题。');
 if(assetType==='strategy'&&asset.status!=='approved')throw Error('策略尚未准入，不能申请资金配置。');
 const t=newTask(state,next,config,asset.name+' · 新研究');if(assetType==='dataset')t.values.dataset=asset.id;
 if(assetType==='factor')t.values.factors=[asset.id];if(assetType==='strategy'){t.values.strategies=[asset.id];t.values.weight1=Math.min(90,Number(t.values.singleStrategy));t.values.weight2=0;t.values.cash=100-t.values.weight1;}
 t.upstream={type:assetType,id:asset.id,version:asset.version,status:asset.status};return t;
}
function resumeFactor(state,id,config){const asset=state.assets.factor.find(x=>x.id===id);if(!asset)throw Error('因子不存在');const t=newTask(state,'factor',config,asset.name+' · 复现研究');t.values.expression=asset.expr;t.values.reference=id;t.current='F3';t.upstream={type:'factor',id,version:asset.version,status:asset.status};return t;}
function edit(state,t,key,value,stage,config){if(JSON.stringify(t.values[key])===JSON.stringify(value))return;
 const active=t.jobs.find(j=>j.status==='running'&&j.mode==='execute');if(active)throw Error('本任务正在执行，请先停止后续调用再修改参数。');
 t.values[key]=value;t.revision++;t.current=stage;t.updated=stamp();if(key==='name')t.name=value||'未命名研究';
 const index=id=>Number(String(id).slice(1));let from=index(stage);
 // 同一字段可能被多个步骤共用（如 F2/F3 的表达式）：任一使用该字段的步骤及其后续产物都必须失效。
 if(config?.stages)for(const [id,schema] of Object.entries(config.stages))if(id.startsWith(levels[t.module])&&schema.fields.some(f=>f.key===key))from=Math.min(from,index(id));
 for(const [id,out] of Object.entries(t.outputs))if(index(id)>=from)out.stale=true;
 for(const r of state.reviews)if(r.taskId===t.id&&r.status==='pending'){r.status='expired';r.audit.push({decision:'版本变更失效',note:'参数已变更，请重新形成证据并送审。',time:stamp()});}
}
function permission(persona,stage){
 if(stage==='D5'&&!['数据负责人','平台管理员'].includes(persona))return '发布数据需要切换到「数据负责人」预览身份。';
 if(stage==='P5'&&persona!=='投资负责人')return '部署操作由「投资负责人」预览身份执行。';
 if(['T3','T4'].includes(stage)&&persona!=='风控负责人')return '风险处置由「风控负责人」预览身份执行。';
 return '';
}
function outputValid(t,id){const x=t.outputs[id];return x&&!x.stale&&x.passed;}
function validation(state,t,stage,config){
 const errors=[];const v=t.values;const schema=config.stages[stage];if(!schema)return ['未知业务步骤'];
 const perm=permission(state.persona,stage);if(perm)errors.push(perm);
 for(const f of schema.fields){const value=v[f.key];if(['text','textarea','code','date','select'].includes(f.type)&&!String(value??'').trim())errors.push('请填写'+f.label);if(f.type==='number'&&(value===''||value===null||value===undefined||!Number.isFinite(Number(value))||Number(value)<f.min||Number(value)>f.max))errors.push(f.label+'需要在 '+f.min+'～'+f.max+' 之间');if(f.type==='multi'&&(!Array.isArray(value)||!value.length))errors.push('请至少选择一项'+f.label);}
 if(['D2','S3'].includes(stage)&&v.start>v.end)errors.push('开始日期不能晚于结束日期。');
 if(['F2','F3'].includes(stage)){let balance=0;for(const char of v.expression||''){if(char==='(')balance++;if(char===')')balance--;if(balance<0)break;}if(balance!==0||/(__|import|eval|fetch|;)/i.test(v.expression||''))errors.push('表达式包含不匹配括号或不支持的内容。');}
 const dependencies={D3:'D2',D4:'D3',D5:'D4',F4:'F3',F5:'F4',S3:'S2',S4:'S3',S5:'S4',S6:'S5',P2:'P1',P3:'P2',P4:'P3',T3:'T2',T4:'T3'};
 const dep=dependencies[stage];if(dep&&!outputValid(t,dep))errors.push('需要本任务有效的 '+dep+' 产物；可返回该步执行，或选择已有任务。');
 if(stage==='F6'&&v.usage!=='仅研究留档'&&!outputValid(t,'F5'))errors.push('正式候选需要冻结版本及独立验证证据；普通实验可选择仅留档。');
 if(stage==='F6'&&v.usage!=='仅研究留档'&&v.selection!=='仅留档，不送审'&&!v.evidence)errors.push('正式送审需要确认报告、数据版本与独立验证材料齐备。');
 if(['F5','S5'].includes(stage)&&(!v.attempts||!v.isolate))errors.push('独立验证需要完整尝试记录与隔离环境约定。');
 if(stage==='D5'&&(!v.immutable))errors.push('发布不能覆盖历史版本。');
 if(stage==='P2'){for(const id of v.strategies||[])if(!state.assets.strategy.some(a=>a.id===id&&a.status==='approved'))errors.push('只能将已准入策略纳入资金配置。');}
 if(stage==='P3'){
 const total=Number(v.weight1)+Number(v.weight2)+Number(v.cash);if(Math.abs(total-100)>0.001)errors.push('策略权重与现金比例合计必须为100%。');
 if(Math.max(Number(v.weight1),Number(v.weight2))>Number(v.singleStrategy))errors.push('策略权重超过本组合单策略上限。');
 if((v.strategies||[]).length===1&&Number(v.weight2)!==0)errors.push('只选择了一项策略，策略二权重必须为0。');
 }
 if(stage==='P4'&&!v.riskEvidence)errors.push('缺少独立风险检查材料。');
 if(stage==='P5'){
 if(v.environment!=='模拟环境')errors.push('本原型不接入实盘；请选择模拟环境查看交互。');
 if(!state.reviews.some(r=>r.taskId===t.id&&r.revision===t.revision&&r.status==='approved'&&r.type==='资金方案'&&r.artifactId===t.outputs.P4?.id&&!t.outputs.P4.stale))errors.push('当前方案版本尚未获得资金方案审批。');
 if(!v.pretrade||!v.reconcile)errors.push('执行前检查和对账必须启用。');
 }
 if(stage==='T3'&&v.measure==='继续观察'&&state.incidents.find(i=>i.id===v.event)?.hard)errors.push('此事件有硬限制，不能仅选择继续观察来解除保护。');
 if(stage==='T4'&&(!v.retested||!v.receipts))errors.push('缺少风险复测或措施回执，不能申请恢复。');
 return errors;
}
function snapshot(t){return {taskId:t.id,revision:t.revision,values:clone(t.values)};}
function summarize(t,stage,caseName){
 const v=t.values;let passed=true;let metrics=[],rows=[],summary='';
 if(t.module==='data'){metrics=[['字段完整率','99.4%'],['异常记录','6条'],['来源版本','场景快照']];rows=[['数据源',v.source],['批次','RAW-SAMPLE-1104'],['质量规则','固定规则集 v1'],['处理方式',v.missing||'按已登记规则']];summary='已生成场景中的数据处理产物；原始、加工、质量和发布版本可追踪。';if(stage==='D4')passed=Number(v.coverage)<=99.4;if(stage==='D5')summary='版本发布交互已完成预览；没有修改真实数据目录。';}
 if(t.module==='factor'){metrics=[['Rank IC（样例）','0.041'],['有效交易日（样例）','658'],['换手诊断','需关注'],['近似相关性（样例）','0.42']];rows=[['因子表达式',v.expression],['数据版本',v.dataset],['预处理',v.preprocess],['检验范围',stage==='F5'?'独立验证场景':'研发区间场景']];summary='场景指标用于展示报告结构，不是当前参数的实际计算结果。';if(stage==='F4')passed=Number(v.minIC)<=0.041&&Number(v.minDays)<=658&&Number(v.maxCorrelation)>=0.42;if(stage==='F5')summary='已预览冻结候选、独立工具权限和验证证据；真实封存验证服务待接入。';}
 if(t.module==='strategy'){metrics=[['年化收益（样例）','12.8%'],['最大回撤（样例）','8.6%'],['成本假设',v.cost+' bps'],['观察进度',v.observedDays+'/'+v.requiredDays+'日']];rows=[['引用因子',(v.factors||[]).join('、')],['信号方法',v.signal],['调仓周期',v.rebalance],['持仓数量',v.topN]];summary='此处展示策略报告与证据交接结构，未进行真实回测或训练。';if(stage==='S6'){passed=Number(v.observedDays)>=Number(v.requiredDays);summary=passed?'场景观察期满足约定，可整理候选材料。':'观察期尚未满足约定，保持模拟跟踪，不送审。';}}
 if(t.module==='portfolio'){metrics=[['策略一配置',v.weight1+'%'],['策略二配置',v.weight2+'%'],['现金比例',v.cash+'%'],['场景预算',v.capital+'万元']];rows=[['合计权重',Number(v.weight1)+Number(v.weight2)+Number(v.cash)+'%'],['场景策略一金额',(Number(v.capital)*Number(v.weight1)/100).toFixed(2)+'万元'],['场景策略二金额',(Number(v.capital)*Number(v.weight2)/100).toFixed(2)+'万元'],['账户',v.account]];summary='权重和金额由页面实际计算；风险、成交与回执均为场景预览。';if(stage==='P5')summary='模拟部署回执已生成。未连接交易账户、未提交真实订单。';}
 if(t.module==='monitor'){metrics=[['影响对象',v.affected||'研究工作区'],['建议等级',v.severity||'高'],['事件状态','待闭环'],['评价对象',v.basis||'模拟运行']];rows=[['事件',v.event||'E-001'],['措施',v.measure||'待研判'],['证据',v.evidenceNote||v.attributionNote||'查看来源记录'],['责任人',v.riskOwner||'风控负责人']];summary='根据场景记录预览运行检查、处置与反馈。';if(stage==='T4')summary='已整理恢复复核申请；知悉和提交申请不代表风险已解除。';if(stage==='T5')rows=[['策略贡献（样例）','+1.42%'],['成本影响（样例）','-0.12%'],['未解释残差（样例）','+0.03%'],['合计（样例）','+1.33%']];}
 if(caseName==='evidence'){passed=false;summary='证据不足场景：关键来源或核验材料缺失，需要补证，不能正式放行。';}
 return {passed,metrics,rows,summary};
}
function ensureAsset(state,module,t,status){
 const kind=module==='data'?'dataset':module;const collection=state.assets[kind];if(!collection)return null;
 const sourceArtifact=t.outputs[t.current]?.id;let a=collection.find(x=>x.taskId===t.id&&x.revision===t.revision&&x.sourceArtifact===sourceArtifact);if(!a){a={id:uid(levels[module]),taskId:t.id,sourceArtifact,assetVersion:'v'+t.revision+'.'+(collection.filter(x=>x.taskId===t.id).length+1)};collection.unshift(a);}
 Object.assign(a,{name:t.values.assetName||t.name,version:a.assetVersion,status,detail:'交互原型中的任务产物',expr:t.values.expression||t.values.signal||t.values.version||'查看场景报告',use:status==='approved'?'已获研究准入':'仅研究',revision:t.revision});return a;
}
function submitReview(state,t,out,type,hardPass=true){
 const same=state.reviews.find(r=>r.taskId===t.id&&r.revision===t.revision&&r.type===type&&r.artifactId===out.id&&['pending','approved','archived'].includes(r.status));if(same)return same;
 const r={id:uid('RV'),taskId:t.id,module:t.module,type,name:t.values.assetName||t.name,version:'v'+t.revision,revision:t.revision,hardPass,riskPass:hardPass,status:hardPass?'pending':'archived',summary:out.summary,checks:[['版本与证据',hardPass?'通过':'需补证'],['硬条件',hardPass?'通过':'不通过'],['用途',type]],snapshot:snapshot(t),artifactId:out.id,evidence:clone(Object.values(t.outputs)),created:stamp(),audit:[]};
 if(['factor','strategy'].includes(t.module)){const a=ensureAsset(state,t.module,t,hardPass?'pending':'research');r.assetId=a.id;}
 state.reviews.unshift(r);addEvent(state,(hardPass?'送审：':'自动留档：')+r.name,'审查');return r;
}
function execute(state,t,stage,config,caseName='normal'){
 const errors=validation(state,t,stage,config);if(errors.length)throw Error(errors.join('\n'));
 if(caseName==='failure')throw Error('模拟工具超时：未产生新产物，可重试或人工接续。');
 if(stage==='P5'&&t.outputs.P5&&!t.outputs.P5.stale&&t.outputs.P5.revision===t.revision)return t.outputs.P5;
 const result=summarize(t,stage,caseName);
 const out={id:uid('ART'),title:config.stages[stage].result,stage,revision:t.revision,created:stamp(),snapshot:clone(t.values),sample:true,stale:false,...result};
 if(t.outputs[stage]){
 t.history.unshift(clone(t.outputs[stage]));
 for(const [id,previous] of Object.entries(t.outputs))if(Number(id.slice(1))>Number(stage.slice(1)))previous.stale=true;
 for(const r of state.reviews)if(r.taskId===t.id&&r.status==='pending'){r.status='expired';r.audit.push({decision:'证据更新失效',note:'上游产物重新生成，需要按新的证据送审。',time:stamp()});}
 }t.outputs[stage]=out;t.current=stage;t.updated=stamp();
 if(stage==='F4'&&!out.passed)submitReview(state,t,out,'研究筛选',false);
 if(stage==='F6'){if(t.values.usage==='仅研究留档'||t.values.selection==='仅留档，不送审')ensureAsset(state,'factor',t,'research');else submitReview(state,t,out,'研究准入',out.passed&&outputValid(t,'F5'));}
 if(stage==='S6'&&t.values.selection!=='继续观察')submitReview(state,t,out,'研究准入',out.passed&&outputValid(t,'S5'));
 if(stage==='P4')submitReview(state,t,out,'资金方案',out.passed);
 if(stage==='T4'&&t.values.resolution==='申请恢复')submitReview(state,t,out,'风险恢复',out.passed);
 if(stage==='D5'&&out.passed)ensureAsset(state,'data',t,'published');
 if(stage==='T6'){state.improvements=state.improvements||[];state.improvements.unshift({id:uid('IMP'),module:t.values.targetModule,name:t.values.finding,owner:t.values.improvementOwner,criteria:t.values.acceptance,status:'待安排'});}
 addEvent(state,t.name+' · '+config.stages[stage].result+(out.passed?'已生成':'需补证'),'工具预览');return out;
}
function reviewer(type){return type==='资金方案'?'投资负责人':type==='风险恢复'?'风控负责人':'研究负责人';}
function decide(state,id,decision,note){
 const r=state.reviews.find(r=>r.id===id);if(!r)throw Error('审查事项不存在');if(r.status!=='pending')throw Error('仅可处理待审事项。');
 if(state.persona!==reviewer(r.type))throw Error('此事项需要「'+reviewer(r.type)+'」预览身份。');
 if(!String(note||'').trim())throw Error('请填写决定理由，保留可追溯依据。');
 if(!['approved','returned','rejected'].includes(decision))throw Error('未知审查决定。');
 if(decision==='approved'&&(!r.hardPass||(r.type==='资金方案'&&!r.riskPass)))throw Error('硬条件未满足，不能通过审批。');
 const t=r.taskId?getTask(state,r.taskId):null;if(t&&t.revision!==r.revision)throw Error('申请版本已失效，请重新送审。');
 r.status=decision;r.audit.push({decision,note,by:state.persona,time:stamp()});
 if(r.assetId){const a=(state.assets[r.module]||[]).find(a=>a.id===r.assetId);if(a){a.status=decision==='approved'?'approved':'research';a.use=decision==='approved'?'共享研究':'仅研究';a.detail=decision==='approved'?'研究准入已通过 · 场景资产':'研究用途待补证 · 场景资产';}}
 if(decision==='approved'&&r.type==='风险恢复'){const e=state.incidents.find(x=>x.id===t.values.event);if(e)e.status='resolved';}
 addEvent(state,r.name+' · '+({approved:'通过',returned:'退回',rejected:'不采纳'}[decision]),'人工预览');return r;
}
function startJob(t,stage,mode,config,caseName='normal',instruction=''){
 if(t.jobs.some(j=>j.status==='running'))throw Error('本任务已有运行中的预览任务，请等待或停止。');
 const job={id:uid('JOB'),taskId:t.id,stage,mode,caseName,instruction,revision:t.revision,snapshot:clone(t.values),status:'running',started:stamp(),events:[],phase:0,tools:config.stages[stage].tools,model:'交互预览 · 无模型调用'};
 t.jobs.unshift(job);return job;
}
function advanceJob(job){if(job.status!=='running')return false;const label=job.tools[job.phase];if(!label)return false;
 job.events.push({id:uid('CALL'),tool:label,status:'completed',input:{taskId:job.taskId,revision:job.revision,parameters:job.snapshot},output:{preview:true,summary:'预览工具返回：'+label,source:'场景数据'},time:stamp()});job.phase++;return true;
}
function cancelJob(job){if(job.status!=='running')return;job.status='cancelled';job.finished=stamp();job.events.push({id:uid('CALL'),tool:'停止后续调用',status:'cancelled',input:{},output:{summary:'本次预览停止，未执行尚未开始的步骤。'},time:stamp()});}
function makePatch(t,stage,config){const patch={};for(const f of config.stages[stage].fields){let value=clone(t.values[f.key]??f.value);if(['textarea','code'].includes(f.type)&&!String(value).trim())value=clone(f.value);patch[f.key]=value;}if('hypothesis' in patch)patch.hypothesis='基于短期过度反应假设，检验反转特征在不同波动阶段与成本条件下的稳定性。';if('question'in patch)patch.question='复用已有因子与失败记录，比较短期反转的稳定性和交易成本敏感性。';return patch;}
function completeFill(state,t,job,config){
 if(job.status!=='running')return {cancelled:true};job.status='completed';job.finished=stamp();const patch=makePatch({values:job.snapshot},job.stage,config);
 if(t.revision!==job.revision){t.patch={values:patch,stage:job.stage,baseRevision:job.revision};return {conflict:true};}
 applyPatch(state,t,{values:patch,stage:job.stage},config);return {applied:true};
}
function applyPatch(state,t,patch,config){for(const [k,v] of Object.entries(patch.values))edit(state,t,k,v,patch.stage,config);t.patch=null;}
function executeJob(state,t,job,config){
 if(job.status!=='running')return null;
 if(t.revision!==job.revision){job.status='failed';job.error='输入版本发生变化，请重新运行。';job.finished=stamp();return null;}
 try{const out=execute(state,t,job.stage,config,job.caseName);job.status='completed';job.artifactId=out.id;job.finished=stamp();return out;}catch(e){job.status='failed';job.error=e.message;job.finished=stamp();const last=job.events[job.events.length-1];if(last){last.status='failed';last.output={preview:true,summary:e.message};}return null;}
}
function artifact(t,stage,id){const result=id?[...Object.values(t.outputs),...t.history].find(o=>o.id===id):t.outputs[stage];if(!result)throw Error('对应产物快照不存在');return result;}
function stageStatus(t,id){if(t.jobs.some(j=>j.stage===id&&j.status==='running'))return 'running';const out=t.outputs[id];return !out?'todo':out.stale?'stale':out.passed?'completed':'needs_evidence';}
function recover(state){for(const t of state.tasks||[])for(const j of t.jobs||[])if(j.status==='running'){j.status='interrupted';j.error='页面刷新后，本次交互预览中断。可重新委托，不会自动重复执行。';}return state;}
function saveMethod(state,id,data){const m=state.methods[id];if(!m)throw Error('角色不存在');if(!data.prompt.trim()||!data.skills.trim())throw Error('Prompt和Skill配置不能为空。');m.version++;Object.assign(m,data,{evalStatus:'待评测',evalVersion:null});return m;}
function evaluateMethod(state,id){const m=state.methods[id];m.evalStatus=m.prompt.length>=30&&m.skills.length>=4?'通过（场景）':'需改进';m.evalVersion=m.version;return m;}
function publishMethod(state,id){const m=state.methods[id];if(state.persona!=='平台管理员')throw Error('发布方法版本需要「平台管理员」预览身份。');if(m.evalVersion!==m.version||m.evalStatus!=='通过（场景）')throw Error('当前草案版本尚未通过评测。');m.published=m.version;addEvent(state,id+' 方法版本已发布（预览）','方法');return m;}
function savePlan(state,module,data){if(!Number.isFinite(Number(data.budget))||Number(data.budget)<1000||Number(data.budget)>1000000)throw Error('原型额度请设在1,000～1,000,000 Tokens。');if(!Number.isInteger(Number(data.maxTasks))||Number(data.maxTasks)<1||Number(data.maxTasks)>20)throw Error('单日任务上限请设在1～20之间。');state.plans[module]={...data,budget:Number(data.budget),maxTasks:Number(data.maxTasks)};return state.plans[module];}
return {clone,uid,stamp,makeState,defaults,getTask,selected,newTask,selectAsset,resumeFactor,edit,permission,validation,execute,reviewer,decide,startJob,advanceJob,cancelJob,completeFill,applyPatch,executeJob,artifact,stageStatus,recover,saveMethod,evaluateMethod,publishMethod,savePlan,addEvent};
});
