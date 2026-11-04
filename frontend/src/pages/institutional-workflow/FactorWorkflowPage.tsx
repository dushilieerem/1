import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createProject, getProject, listProjects, saveProject, type DetectProject, type FactorResearchPlan } from '@/lib/detectStore';
import { subscribeAuth } from '@/lib/researchClient';
import { factorStages } from './factorWorkflow';
import { FactorDraftAssistant } from './FactorDraftAssistant';
import { FactorDetectPage } from '@/pages/FactorDetectPage';
import { quantReportsPath, quantReportPath } from './QuantFactorShell';
import { Card, PageHeader } from '@/pages/institution/instUi';
const input = 'mt-2 w-full rounded-lg border border-[#e0d9ef] bg-white p-3 text-sm';
const button = 'rounded-lg bg-[#65358D] px-4 py-2 text-sm text-white disabled:opacity-50';
const route = (id:string, step:string) => `/quant/factor/workflow/${encodeURIComponent(id)}/${step}`;
const emptyPlan = (): FactorResearchPlan => ({revision:'',hypothesis:'',target:'未来5个交易日收益',frequency:'1d',developmentStart:'',developmentEnd:'',validationStart:'',validationEnd:'',acceptance:'',maxTrials:10});
export function FactorWorkflowPage() {
 const {projectId,step='F1'}=useParams(); const navigate=useNavigate();
 const [projects,setProjects]=useState<DetectProject[]>([]),[project,setProject]=useState<DetectProject>();
 const [title,setTitle]=useState(''),[plan,setPlan]=useState(emptyPlan),[name,setName]=useState(''),[code,setCode]=useState('');
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{let live=true, seq=0; const load=async()=>{const n=++seq;setLoading(true);setProject(undefined);setError('');setNotice('');setPlan(emptyPlan());setName('');setCode('');try{
 const [items,p]=await Promise.all([listProjects(),projectId?getProject(projectId):Promise.resolve(undefined)]);
 if(!live||n!==seq)return;setProjects(items.filter(x=>!x.sample));
 if(projectId&&!p)throw Error('研究不存在、无权访问或服务暂不可用，请重试。');
 setProject(p);if(p){setPlan(p.config.researchPlan||{...emptyPlan(),hypothesis:p.description});setName(p.config.draftFactor?.name||'');setCode(p.config.draftFactor?.body||'');}
 }catch(e){if(live&&n===seq)setError(e instanceof Error?e.message:String(e));}finally{if(live&&n===seq)setLoading(false);}};
 void load();const off=subscribeAuth(()=>{setTitle('');void load();});return()=>{live=false;++seq;off();};},[projectId,step]);
 async function perform(work:()=>Promise<void>){if(busy)return;setBusy(true);setError('');setNotice('');try{await work();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 async function create(){if(!title.trim())throw Error('请填写研究名称');const p=await createProject('custom_combo','',title.trim());navigate(route(p.id,'F2'));}
 async function persistPlan(){if(!project)return;
 if(!plan.hypothesis.trim()||!plan.acceptance.trim())throw Error('请填写研究假设及预先约定的筛选条件');
 if(!plan.developmentStart||!plan.developmentEnd||!plan.validationStart||!plan.validationEnd)throw Error('请填写研发及验证日期范围');
 if(!(plan.developmentStart<=plan.developmentEnd&&plan.developmentEnd<plan.validationStart&&plan.validationStart<=plan.validationEnd))throw Error('研发区间须早于验证区间，且不能重叠');
 if(!Number.isInteger(plan.maxTrials)||plan.maxTrials<1||plan.maxTrials>1000)throw Error('尝试预算须为1—1000的整数');
 const next={...plan,revision:crypto.randomUUID()};const saved=await saveProject({...project,description:next.hypothesis,config:{...project.config,researchPlan:next,rangeMode:'custom',startDate:next.developmentStart,endDate:next.developmentEnd}});setProject(saved);setPlan(next);setNotice('研究计划已保存至平台。验证区间登记不代表已建立封存权限。');}
 async function persistCode(){if(!project)return;if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)||!code.trim())throw Error('请填写合法函数名和完整代码');
 if(!new RegExp('def\\s+'+name+'\\s*\\(').test(code))throw Error('函数定义必须与函数名一致');
 const saved=await saveProject({...project,factorName:name,config:{...project.config,factorCodes:[name],weights:[1],powers:[1],draftFactors:undefined,draftFactor:{name,body:code,description:plan.hypothesis,category:'机构因子研究'}}});setProject(saved);setNotice('代码已保存，尚未执行计算。');}
 const dirty=!!project && (step==='F2' ? JSON.stringify(plan)!==JSON.stringify(project.config.researchPlan||{...emptyPlan(),hypothesis:project.description}) : step==='F3' && (name!==(project.config.draftFactor?.name||'')||code!==(project.config.draftFactor?.body||'')));
 useEffect(()=>{const guard=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[dirty]);
 const active=factorStages.find(x=>x.id===step)||factorStages[0];
 return <section className="mx-auto max-w-[1500px] space-y-5 p-5" onClickCapture={e=>{if(dirty&&(e.target as HTMLElement).closest('a')&&!window.confirm('当前修改尚未保存，离开后将丢失。确认离开？')){e.preventDefault();e.stopPropagation();}}}>
 <PageHeader eyebrow="量化投研" title="因子工厂" desc={project?.name||'从已有资产或新假设开始，形成有证据的因子资产。'}/>
 <nav aria-label="因子工厂六步骤" className="grid grid-cols-2 gap-2 rounded-xl border bg-white p-3 xl:grid-cols-6">{factorStages.map(s=>!projectId&&s.id!=='F1'?<span key={s.id} aria-disabled="true" title="先建立或选择研究任务" className="rounded-lg p-3 text-sm text-slate-400">{s.id} {s.title}</span>:<Link key={s.id} to={projectId?route(projectId,s.id):'/quant/factor'} aria-current={active.id===s.id?'step':undefined} className={'rounded-lg p-3 text-sm '+(active.id===s.id?'bg-[#f3eaf8] font-semibold text-[#65358D]':'text-slate-600')}><span className="mr-2 text-xs">{s.id}</span>{s.title}</Link>)}</nav>
 {error&&<p role="alert" className="rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}{notice&&<p role="status" className="rounded-lg bg-green-50 p-3 text-green-800">{notice}</p>}
 {loading?<p role="status">正在读取研究…</p>:<>
 {(step==='F1'||!projectId)&&<div className="grid gap-5 lg:grid-cols-2"><Card title="研究起点" desc="创建任务不要求先写代码，也不依赖上游产生新因子。"><form onSubmit={e=>{e.preventDefault();void perform(create);}}><label>研究名称<input required maxLength={100} className={input} value={title} onChange={e=>setTitle(e.target.value)}/></label><button disabled={busy} className={button+' mt-4'}>建立研究任务</button></form><Link className="mt-5 block text-sm text-[#65358D]" to="/quant/factor/library">检索已有因子与研究资产 →</Link><Link className="mt-3 block text-sm text-[#65358D]" to="/quant/factor/reports">查看历史实验报告 →</Link></Card><Card title="继续已有研究">{projects.map(p=><Link className="block border-b py-3 text-sm" key={p.id} to={route(p.id,'F2')}><strong>{p.name}</strong><p className="mt-1 text-xs text-slate-500">{p.description||'尚未填写假设'} · {p.runCount}份报告</p></Link>)}</Card></div>}
 {project&&step==='F2'&&<Card title="假设与验证计划" desc="在计算前明确研究目标、样本范围与筛选条件。"><form className="grid gap-4 md:grid-cols-2" onSubmit={e=>{e.preventDefault();void perform(persistPlan);}}>
 <label className="md:col-span-2">经济或行为假设<textarea required rows={3} className={input} value={plan.hypothesis} onChange={e=>setPlan({...plan,hypothesis:e.target.value})}/></label>
 <label>预测目标<input className={input} value={plan.target} onChange={e=>setPlan({...plan,target:e.target.value})}/></label><label>最大尝试次数<input type="number" min={1} max={1000} className={input} value={plan.maxTrials} onChange={e=>setPlan({...plan,maxTrials:Number(e.target.value)})}/></label>
 {([['developmentStart','研发开始'],['developmentEnd','研发结束'],['validationStart','验证开始'],['validationEnd','验证结束']] as const).map(([key,label])=><label key={key}>{label}<input required type="date" className={input} value={plan[key]} onChange={e=>setPlan({...plan,[key]:e.target.value})}/></label>)}
 <label className="md:col-span-2">预先约定的筛选条件<textarea required rows={3} className={input} placeholder="填写指标、成本、稳定性要求与不通过时的处理原则" value={plan.acceptance} onChange={e=>setPlan({...plan,acceptance:e.target.value})}/></label>
 <div className="flex items-center gap-4 md:col-span-2"><button disabled={busy} className={button}>保存计划</button><Link to={route(project.id,'F3')}>进入工程计算 →</Link></div></form></Card>}
 {project&&step==='F3'&&<Card title="因子实现" desc="人工编辑或采纳 AI 代码，保存到同一研究任务。"><div className="space-y-4"><label className="block">因子函数名<input className={input} value={name} onChange={e=>setName(e.target.value)}/></label><FactorDraftAssistant hypothesis={plan.hypothesis} name={name} draftVersion={JSON.stringify([plan,name,code])} onApply={f=>{setName(f.factor_name);setCode(f.factor_code);}}/><label className="block">Python 实现<textarea rows={15} spellCheck={false} className={input+' font-mono'} value={code} onChange={e=>setCode(e.target.value)}/></label><button disabled={busy} className={button} onClick={()=>void perform(persistCode)}>保存实现</button><Link className="ml-4 text-sm" to={route(project.id,'F4')}>进入研发检验 →</Link></div></Card>}
 {project&&step==='F4'&&<div className="space-y-4"><Card title="研发检验" desc="以下操作直接调用平台现有 ResearchEngine；全部检测结果保存到当前研究任务。"><Link className="text-sm text-[#65358D]" to={quantReportsPath(project.id)}>查看全部实验报告 →</Link></Card><FactorDetectPage key={project.id} navigation={{listPath:route(project.id,'F4'),reportPath:quantReportPath}}/></div>}
 {project&&(step==='F5'||step==='F6')&&<Card title={active.title} desc="此步骤正在接入服务端证据与权限校验。"><p className="text-sm text-slate-600">{step==='F5'?'当前普通回测不能作为独立验证。冻结、受控验证及报告绑定完成前，不允许标记通过。':'已有研究报告可以留档和登记研究资产；独立验证与审批接入完成前，不开放正式准入。'}</p><Link className="mt-4 inline-block text-sm text-[#65358D]" to={'/quant/factor/'+encodeURIComponent(project.id)+'/reports'}>查看真实研究报告</Link></Card>}
 </>}
 </section>;
}
