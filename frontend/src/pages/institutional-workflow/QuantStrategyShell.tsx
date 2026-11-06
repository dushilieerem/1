import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/pages/institution/instUi";
import { QuantModuleNav } from "./QuantModuleNav";

export const strategyProjectPath = (id: string) => "/quant/strategy/" + encodeURIComponent(id);
export const strategyReportPath = (id: string) => "/quant/strategy/report/" + encodeURIComponent(id);
export const strategyReportsPath = (id?: string) => id ? strategyProjectPath(id) + "/reports" : "/quant/strategy/reports";
export function QuantStrategyShell({stage,projectId,children}: {
  stage: "research" | "test" | "reports"; projectId?: string; children: ReactNode;
}) {
  const cls = (active: boolean) => active ? "font-semibold text-[#65358D]" : "text-slate-600 hover:text-[#65358D]";
  return <section className="mx-auto min-w-0 max-w-[1600px] space-y-5 bg-[#f7f8fc] p-3 sm:p-5">
    <QuantModuleNav/>
    <PageHeader eyebrow="SUNVALLEY · 量化机构端" title="策略研究" desc="从已有因子或策略代码开始，配置交易规则、运行回测并复核报告。" actions={<Link to="/quant/strategy/library" className="text-sm text-[#65358D] underline">打开平台策略库</Link>}/>
    <nav aria-label="策略研究步骤" className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-[#dde5f2] bg-white p-4 text-sm">
      <Link aria-current={stage==="research"?"step":undefined} className={cls(stage==="research")} to="/quant/strategy">研究项目与目标</Link><span aria-hidden="true">→</span>
      {projectId?<Link aria-current={stage==="test"?"step":undefined} className={cls(stage==="test")} to={strategyProjectPath(projectId)}>因子选用、交易规则与回测</Link>:<span className="text-slate-500">因子选用、交易规则与回测</span>}<span aria-hidden="true">→</span>
      <Link aria-current={stage==="reports"?"step":undefined} className={cls(stage==="reports")} to={strategyReportsPath(projectId)}>回测报告与复核</Link><span aria-hidden="true">→</span>
      <Link className={cls(false)} to="/quant/strategy/library">策略库与复用</Link>
      {projectId&&<Link className="ml-auto text-xs text-[#65358D] underline" to="/quant/strategy">切换 / 新建研究</Link>}
    </nav>
    {children}
  </section>;
}
