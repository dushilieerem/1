import { ConfirmProvider } from "@/components/ConfirmDialog";
import { ScrollToTop } from "@/components/ScrollToTop";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearQuantSession, fetchQuantMe, getQuantSession, quantLoginUrl, subscribeQuantAuth, type QuantSession } from "@/lib/quantAuth";

export function QuantLayout() {
 const location = useLocation(), navigate = useNavigate();
 const [session, setSession] = useState<QuantSession | null>(null);
 const [error, setError] = useState("");
 const [retry, setRetry] = useState(0);
 useEffect(() => {
   let alive = true;
   function verify() {
     if (!getQuantSession()) { setSession(null); navigate(quantLoginUrl(location.pathname + location.search), { replace: true }); return; }
     fetchQuantMe().then(s => { if (alive) { setSession(s); setError(""); } })
       .catch(e => { if (alive) { setSession(null); setError(e.message); if (!getQuantSession()) navigate(quantLoginUrl(location.pathname + location.search), { replace: true }); } });
   }
   document.title = "SVQuant · 机构量化平台";
   verify();
   const off = subscribeQuantAuth(verify);
   // Validate membership again when returning to the tab, without polling.
   window.addEventListener("focus", verify);
   return () => { alive = false; off(); window.removeEventListener("focus", verify); };
 }, [location.pathname, location.search, navigate, retry]);
 if (!session) return <main className="min-h-screen bg-[#f7f8fc] p-8 text-sm">
   {error ? <div role="alert">{error}<button className="ml-4 underline" onClick={() => { setError(""); setRetry(n => n + 1); }}>重试</button></div> : <p role="status">正在验证机构量化身份…</p>}
 </main>;
 const nav = [["/quant/factor", "因子工厂"], ["/quant/strategy", "策略研究"], ["/quant/factor/library", "因子库"], ["/quant/strategy/library", "策略库"]];
 return <div className="min-h-screen bg-[#f7f8fc] text-[#171923]">
   <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-3 border-b border-[#e0d9ef] bg-white px-5 py-4">
     <div><p className="font-display text-lg font-semibold tracking-wider">旸谷资本 <span className="ml-3 text-sm font-normal tracking-normal text-[#65358D]">机构量化平台</span></p>
       <p className="mt-1 text-xs text-slate-500">{session.org.name_cn} · {session.user.display_name || session.user.username} · 量化研究员</p></div>
     <div className="flex items-center gap-4 text-xs text-slate-500"><span>开发环境 · 不连接实盘交易</span>
       <button className="text-[#65358D] hover:underline" onClick={() => { clearQuantSession(); navigate(quantLoginUrl(), { replace: true }); }}>退出量化工作区</button></div>
   </header>
   <div className="mx-auto flex max-w-[1900px] flex-col lg:flex-row">
     <aside className="shrink-0 border-b border-[#e0d9ef] bg-white p-4 lg:min-h-[calc(100vh-81px)] lg:w-52 lg:border-r lg:border-b-0">
       <p className="mb-3 px-3 text-[11px] tracking-widest text-slate-400">量化投研</p>
       <nav aria-label="机构量化导航" className="flex flex-wrap gap-1 lg:flex-col">{nav.map(([to,label]) => <NavLink key={to} to={to}
         className={() => "rounded-lg px-3 py-2.5 text-sm " + ((location.pathname === to || (to === "/quant/factor" || to === "/quant/strategy") && location.pathname.startsWith(to + "/") && !location.pathname.includes("/library")) ? "bg-[#f3eaf8] font-medium text-[#65358D]" : "text-slate-600 hover:bg-slate-50")}>{label}</NavLink>)}</nav>
       <p className="mt-6 hidden px-3 text-xs leading-6 text-slate-500 lg:block">当前研究资产按成员私有管理。机构共享与投资审批尚未开放。</p>
     </aside>
     <main className="min-w-0 flex-1"><ConfirmProvider><ScrollToTop /><Outlet /></ConfirmProvider></main>
   </div>
 </div>;
}
