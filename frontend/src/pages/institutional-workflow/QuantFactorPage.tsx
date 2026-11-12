import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createDetectProjectFromSnippet, listProjects, saveProject, type DetectProject } from "@/lib/detectStore";
import { subscribeAuth } from "@/lib/researchClient";
import { FactorDetectPage } from "@/pages/FactorDetectPage";
import { Card } from "@/pages/institution/instUi";
import { QuantFactorShell, quantReportsPath, quantReportPath } from "./QuantFactorShell";

import { FactorDraftAssistant } from "./FactorDraftAssistant";

export function QuantFactorPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<DetectProject[]>([]);
  const [title, setTitle] = useState("");
  const [name, setName] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    let generation = 0;
    const load = () => {
      const current = ++generation;
      setLoading(true); setProjects([]); setError("");
      listProjects().then(p => { if (live && current === generation) setProjects(p.filter(x => !x.sample)); })
        .catch(e => { if (live && current === generation) setError(String(e.message || e)); })
        .finally(() => { if (live && current === generation) setLoading(false); });
    };
    load();
    const unsubscribe = subscribeAuth(() => { setCode(""); setHypothesis(""); setName(""); setTitle(""); load(); });
    return () => { live = false; ++generation; unsubscribe(); };
  }, [projectId]);
  async function create() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (!title.trim() || !hypothesis.trim() || !code.trim()) throw new Error("请填写研究名称、假设和因子代码");
      const project = await createDetectProjectFromSnippet({
        title: title.trim(), name: name.trim(), description: hypothesis.trim(),
        code, category: "量化机构研究",
      });
      if (project.description !== hypothesis.trim()) await saveProject({ ...project, description: hypothesis.trim() });
      setTitle(""); setHypothesis(""); setName(""); setCode("");
      navigate("/quant/factor/" + encodeURIComponent(project.id));
    } catch (e) { setError(/HTTP 50[234]/.test(String(e)) ? "平台服务暂时不可用，请稍后重试；当前填写内容已保留。" : e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const input = "w-full rounded-lg border border-[#dde5f2] bg-white p-3 text-sm text-[#171923]";
  return <QuantFactorShell stage={projectId ? "test" : "research"} projectId={projectId}>
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {projectId ? <FactorDetectPage key={projectId} navigation={{ listPath: quantReportsPath(projectId), reportPath: quantReportPath }} /> : <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Card title="新建因子研究" desc="保存研究定义后进入配置与检验；检验调用平台现有 ResearchEngine 服务。">
        <form className="space-y-4" onSubmit={e => { e.preventDefault(); void create(); }}>
          <label className="block text-sm">研究名称<input required maxLength={100} className={input} value={title} onChange={e=>setTitle(e.target.value)} disabled={busy}/></label>
          <label className="block text-sm">研究假设<textarea required maxLength={3000} rows={3} className={input} value={hypothesis} onChange={e=>setHypothesis(e.target.value)} disabled={busy}/></label>
          <label className="block text-sm">因子函数名<input required pattern="[A-Za-z_][A-Za-z0-9_]*" maxLength={80} className={input} value={name} onChange={e=>setName(e.target.value)} disabled={busy}/></label>
          <FactorDraftAssistant hypothesis={hypothesis} name={name} draftVersion={JSON.stringify([title, hypothesis, name, code])} onApply={factor => { setName(factor.factor_name); setCode(factor.factor_code); }} />
          <label className="block text-sm">因子 Python 函数<textarea required rows={9} className={input+" font-mono"} value={code} onChange={e=>setCode(e.target.value)} disabled={busy} spellCheck={false}/></label>
          <div className="flex flex-wrap items-center gap-4">
            <button disabled={busy} className="rounded-lg bg-[#65358D] px-5 py-2.5 text-sm text-white disabled:opacity-50">{busy ? "正在保存…" : "保存并配置检验"}</button>

          </div>
        </form>
      </Card>
      <Card title="已有研究项目" desc="可以继续已有研究；无需等待前序人员交付新因子。">
        {loading ? <p role="status">正在读取项目…</p> : projects.length ? <ul className="divide-y divide-[#dde5f2]">{projects.map(p=><li key={p.id} className="py-3"><Link className="font-medium text-[#65358D]" to={"/quant/factor/"+encodeURIComponent(p.id)}>{p.name || p.factorName}</Link><p className="mt-1 line-clamp-2 text-xs text-slate-500">{p.description}</p><Link className="mt-2 inline-block text-xs text-[#65358D] underline" to={quantReportsPath(p.id)}>查看报告（{p.runCount || 0}）</Link></li>)}</ul> : !error && <p className="text-sm text-slate-500">当前账户尚无研究项目，可以从左侧创建。</p>}
      </Card>
    </div>}
  </QuantFactorShell>;
}
