import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { listAllDetectRuns, listRuns, type DetectRunRecord } from "@/lib/detectStore";
import { subscribeAuth } from "@/lib/researchClient";
import { Card } from "@/pages/institution/instUi";
import { QuantFactorShell, quantProjectPath, quantReportPath } from "./QuantFactorShell";

export function QuantFactorReportsPage() {
  const { projectId } = useParams();
  const [runs, setRuns] = useState<DetectRunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let generation = 0;
    let active = true;
    function load() {
      const current = ++generation;
      setRuns([]); setLoading(true); setError("");
      (projectId ? listRuns(projectId) : listAllDetectRuns())
        .then(rows => { if (active && current === generation) setRuns(rows); })
        .catch(e => { if (active && current === generation) setError(e instanceof Error ? e.message : String(e)); })
        .finally(() => { if (active && current === generation) setLoading(false); });
    }
    load();
    const unsubscribe = subscribeAuth(load);
    return () => { active = false; ++generation; unsubscribe(); };
  }, [projectId, retry]);
  return <QuantFactorShell stage="reports" projectId={projectId}>
    <Card title={projectId ? "当前研究的检测报告" : "我的检测报告"} desc="每份报告保留当次代码、参数与计算结果。打开报告进行诊断、复核或将草稿因子加入个人因子库。">
      {loading ? <p role="status">正在读取报告…</p> : error ? <div role="alert" className="text-sm text-red-700">{error}<button className="ml-3 underline" onClick={() => setRetry(n => n + 1)}>重新读取</button></div> : !runs.length ? <div className="space-y-3 py-4 text-sm text-slate-500"><p>当前没有已保存的检测报告。完成一次检测后，报告会出现在这里。</p><Link className="text-[#65358D] underline" to={projectId ? quantProjectPath(projectId) : "/quant/factor"}>{projectId ? "返回配置与检验" : "选择研究项目"}</Link></div> :
      <ul className="divide-y divide-slate-200">{runs.map(run => <li key={run.id} className="flex flex-wrap items-start justify-between gap-3 py-4">
        <div className="min-w-0"><Link className="break-all font-medium text-[#65358D]" to={quantReportPath(run.id)}>{run.factorName || run.description || "检测报告"}</Link><p className="mt-1 text-xs text-slate-500">{run.finishedAt ? new Date(run.finishedAt).toLocaleString("zh-CN") : "时间未记录"} · {Number.isFinite(run.elapsedSec) ? run.elapsedSec + " 秒" : "耗时未记录"}</p>{run.remark && <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-600">{run.remark}</p>}</div>
        <Link className="text-sm text-[#65358D] underline" to={quantReportPath(run.id)}>打开报告</Link>
      </li>)}</ul>}
    </Card>
  </QuantFactorShell>;
}
