import { factorStages } from "./factorWorkflow";
import { QuantModuleNav } from "./QuantModuleNav";
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
    <QuantModuleNav/>
    {projectId && <Link className="text-sm text-[#65358D]" to={"/quant/factor/workflow/"+encodeURIComponent(projectId)+"/F4"}>返回该研究的六步工作区</Link>}
    <PageHeader eyebrow="SUNVALLEY · 量化机构端" title="因子工厂"
      desc="研究定义、计算检验和检测报告共用平台工具；已有因子可以直接复用。"
      actions={<Link className="text-sm text-[#65358D] underline" to="/quant/factor/library">打开平台因子库</Link>} />
    <nav aria-label="因子研究步骤" className="grid grid-cols-2 gap-2 rounded-xl border border-[#dde5f2] bg-white p-3 text-sm xl:grid-cols-6">
      {factorStages.map(s => <Link key={s.id} className={linkClass((stage === "research" ? "F2" : "F4") === s.id)+" rounded-lg p-2"} to={projectId ? "/quant/factor/workflow/"+encodeURIComponent(projectId)+"/"+s.id : "/quant/factor"}>{s.id} {s.title}</Link>)}
    </nav>
    {children}
  </section>;
}
