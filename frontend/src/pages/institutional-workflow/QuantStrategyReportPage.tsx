import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getStrategyRun, type StrategyRunRecord } from "@/lib/strategyStore";
import { subscribeAuth } from "@/lib/auth";
import { StrategyReportPage } from "@/pages/StrategyReportPage";
import { QuantStrategyShell, strategyProjectPath, strategyReportPath, strategyReportsPath } from "./QuantStrategyShell";

export function QuantStrategyReportPage() {
  const { runId = "" } = useParams();
  const [run, setRun] = useState<StrategyRunRecord>();
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    let generation = 0;
    function load() {
      const current = ++generation;
      setRun(undefined); setLoading(true);
      getStrategyRun(runId).then(row => { if (active && current === generation) setRun(row); })
        .catch(() => { if (active && current === generation) setRun(undefined); })
        .finally(() => { if (active && current === generation) setLoading(false); });
    }
    load(); const unsubscribe = subscribeAuth(load);
    return () => { active = false; ++generation; unsubscribe(); };
  }, [runId]);
  const meta = (run?.result as unknown as { meta?: Record<string, unknown> } | undefined)?.meta || {};
  const request = run?.request as unknown as Record<string, unknown> | undefined;
  const verified = (run as (StrategyRunRecord & { verified?: boolean }) | undefined)?.verified === true;
  return <QuantStrategyShell stage="reports" projectId={run?.projectId}>
    {loading ? <p role="status">正在读取报告…</p> : !run ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">无法读取报告，请检查访问权限或稍后重试。<Link className="ml-3 underline" to={strategyReportsPath()}>返回报告列表</Link></div> : <>
      <details className="rounded-xl border border-[#dde5f2] bg-white p-4 text-sm">
        <summary className="cursor-pointer font-medium">计算来源 · {verified ? "平台签名校验通过" : "未验证签名"}</summary>
        <p className="mt-3 text-xs text-slate-500">签名校验仅验证结果来源和完整性，不代表策略质量合格或已通过投资审批。</p>
        <dl className="mt-3 grid gap-2 sm:grid-cols-[130px_minmax(0,1fr)]">
          <dt>报告编号</dt><dd className="break-all font-mono text-xs">{run.id}</dd>
          <dt>计算任务</dt><dd className="break-all font-mono text-xs">{String(request?._re_run_id || "接口未返回任务编号")}</dd>
          <dt>数据发布标识</dt><dd className="break-all font-mono text-xs">{String(meta.data_release_id || "引擎未返回")}</dd>
          <dt>计算规格摘要</dt><dd className="break-all font-mono text-xs">{String(meta.spec_hash || "引擎未返回")}</dd>
        </dl>
      </details>
      <StrategyReportPage key={runId} navigation={{ listPath: strategyReportsPath(run.projectId), projectPath: strategyProjectPath, reportPath: strategyReportPath, historyPath: strategyReportsPath }} />
    </>}
  </QuantStrategyShell>;
}
