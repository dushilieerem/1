import { StrategyDraftAssistant } from "./StrategyDraftAssistant";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createStrategyProject, createStrategyProjectFromCode, listStrategyProjects, type StrategyProject } from "@/lib/strategyStore";
import { subscribeAuth } from "@/lib/auth";
import { StrategyBacktestPage } from "@/pages/StrategyBacktestPage";
import { Card } from "@/pages/institution/instUi";
import { QuantStrategyShell, strategyProjectPath, strategyReportPath, strategyReportsPath } from "./QuantStrategyShell";

export function QuantStrategyPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [projects,setProjects]=useState<StrategyProject[]>([]);
  const [name,setName]=useState("");
  const [description,setDescription]=useState("");
  const [source,setSource]=useState<"library"|"code">("library");
  const [code,setCode]=useState("");
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    let live=true,generation=0;
    const load=()=>{
      const current=++generation;
      setLoading(true);setProjects([]);setError("");
      listStrategyProjects().then(rows=>{if(live&&current===generation)setProjects(rows.filter(p=>!p.sample));})
        .catch(e=>{if(live&&current===generation)setError(e instanceof Error?e.message:String(e));})
        .finally(()=>{if(live&&current===generation)setLoading(false);});
    };
    load();
    const unsub=subscribeAuth(()=>{setName("");setDescription("");setCode("");load();});
    return()=>{live=false;++generation;unsub();};
  },[retry,projectId]);
  async function create() {
    if(busy)return;
    setBusy(true);setError("");
    try {
      if(!name.trim()||!description.trim())throw new Error("请填写研究名称与研究目标");
      if(source==="code"&&!code.trim())throw new Error("请填写策略代码或因子函数");
      const project=source==="code"
        ? await createStrategyProjectFromCode({name:name.trim(),description:description.trim(),strategyCode:code})
        : await createStrategyProject(name.trim(),description.trim());
      setName("");setDescription("");setCode("");
      navigate(strategyProjectPath(project.id));
    } catch(e) {setError(e instanceof Error?e.message:String(e));}
    finally {setBusy(false);}
  }
  const input="w-full rounded-lg border border-[#dde5f2] bg-white p-3 text-sm text-[#171923]";
  return <QuantStrategyShell stage={projectId?"test":"research"} projectId={projectId}>
    {projectId?<StrategyBacktestPage key={projectId} navigation={{listPath:"/quant/strategy",projectPath:strategyProjectPath,reportPath:strategyReportPath,historyPath:strategyReportsPath}}/>:<>
      {error&&<div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}<button className="ml-3 underline" onClick={()=>setRetry(n=>n+1)}>重新读取项目</button></div>}
      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="新建策略研究" desc="先定义研究目标，再进入工作台选用因子、编辑代码和配置交易规则。">
          <form className="space-y-4" onSubmit={e=>{e.preventDefault();void create();}}>
            <label className="block text-sm">研究名称<input required maxLength={100} className={input} value={name} onChange={e=>setName(e.target.value)} disabled={busy}/></label>
            <label className="block text-sm">研究目标<textarea required maxLength={3000} rows={3} className={input} value={description} onChange={e=>setDescription(e.target.value)} disabled={busy}/></label>
            <label className="block text-sm">构建方式<select className={input} value={source} onChange={e=>setSource(e.target.value as "library"|"code")} disabled={busy}><option value="library">在工作台选用已有因子</option><option value="code">使用已有策略代码或因子函数</option></select></label>
            <StrategyDraftAssistant hypothesis={description} name="" draftVersion={JSON.stringify([name,description,source,code])} onApply={draft=>{setSource("code");setCode(draft.strategy_code);}}/>
            {source==="code"?<label className="block text-sm">策略代码或因子函数<textarea required rows={10} className={input+" font-mono"} value={code} onChange={e=>setCode(e.target.value)} disabled={busy} spellCheck={false}/></label>:<p className="text-sm text-slate-500">下一步使用平台因子选择器配置因子和权重；初始空模板尚无有效选股信号，请配置后再回测。</p>}
            <div className="flex flex-wrap items-center gap-4"><button disabled={busy} className="rounded-lg bg-[#65358D] px-5 py-2.5 text-sm text-white disabled:opacity-50">{busy?"正在保存…":"保存并构建策略"}</button><Link to="/strategy/ai" className="text-sm text-[#65358D] underline">使用平台 AI 策略助手</Link></div>
          </form>
        </Card>
        <Card title="已有研究项目" desc="直接继续已有策略研究，或复用平台策略库。">
          {loading?<p role="status">正在读取项目…</p>:projects.length?<ul className="divide-y divide-[#dde5f2]">{projects.map(p=><li key={p.id} className="py-3"><Link className="font-medium text-[#65358D]" to={strategyProjectPath(p.id)}>{p.name}</Link><p className="mt-1 line-clamp-2 text-xs text-slate-500">{p.description}</p><Link className="mt-2 inline-block text-xs text-[#65358D] underline" to={strategyReportsPath(p.id)}>查看报告（{p.runCount||0}）</Link></li>)}</ul>:!error&&<p className="text-sm text-slate-500">当前账户尚无策略研究项目，可以从左侧创建。</p>}
        </Card>
      </div>
    </>}
  </QuantStrategyShell>;
}
