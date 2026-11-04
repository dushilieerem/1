import { NavLink } from "react-router-dom";

export function QuantModuleNav() {
  return <nav aria-label="量化研究模块" className="flex flex-wrap gap-2 text-sm">
    {[["/quant/factor", "因子工厂"], ["/quant/strategy", "策略研究"]].map(([to, label]) =>
      <NavLink key={to} to={to} className={({isActive}) => "rounded-lg border px-4 py-2 " + (isActive ? "border-[#65358D] bg-[#65358D] text-white" : "border-[#dde5f2] bg-white text-slate-600")}>{label}</NavLink>)}
  </nav>;
}
