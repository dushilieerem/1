import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/pages/institution/instUi";

export function quantProjectPath(projectId: string) {
  return "/quant/factor/" + encodeURIComponent(projectId);
}
export function quantReportPath(runId: string) {
  return "/quant/factor/report/" + encodeURIComponent(runId);
}
export function quantReportsPath(projectId?: string) {
  return projectId ? quantProjectPath(projectId) + "/reports" : "/quant/factor/reports";
}
export function QuantFactorShell({ stage, projectId, children }: {
  stage: "research" | "test" | "reports"; projectId?: string; children: ReactNode;
}) {
  const linkClass = (active: boolean) => active ? "font-semibold text-[#65358D]" : "text-slate-600 hover:text-[#65358D]";
  return <section className="mx-auto min-w-0 max-w-[1600px] space-y-5 bg-[#f7f8fc] p-3 sm:p-5">
    <PageHeader eyebrow="SUNVALLEY · 量化机构端" title="因子工厂"
      desc="研究定义、计算检验和检测报告共用平台工具；已有因子可以直接复用。"
      actions={<Link className="text-sm text-[#65358D] underline" to="/factor/library">打开平台因子库</Link>} />
    <nav aria-label="因子研究步骤" className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-[#dde5f2] bg-white p-4 text-sm">
      <Link aria-current={stage === "research" ? "step" : undefined} className={linkClass(stage === "research")} to="/quant/factor">研究项目与定义</Link>
      <span aria-hidden="true">→</span>
      {projectId ? <Link aria-current={stage === "test" ? "step" : undefined} className={linkClass(stage === "test")} to={quantProjectPath(projectId)}>参数配置与检验</Link> : <span className="text-slate-500">参数配置与检验</span>}
      <span aria-hidden="true">→</span>
      <Link aria-current={stage === "reports" ? "step" : undefined} className={linkClass(stage === "reports")} to={quantReportsPath(projectId)}>检测报告与复核</Link>
      <span aria-hidden="true">→</span>
      <Link className={linkClass(false)} to="/factor/library">因子库与复用</Link>
      {projectId && <Link className="ml-auto text-xs text-[#65358D] underline" to="/quant/factor">切换 / 新建研究</Link>}
    </nav>
    {children}
  </section>;
}
