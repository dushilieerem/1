import { ConfirmProvider } from "@/components/ConfirmDialog";
import { ScrollToTop } from "@/components/ScrollToTop";
import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearQuantSession, fetchQuantMe, getQuantSession, quantLoginUrl, subscribeQuantAuth, type QuantSession } from "@/lib/quantAuth";

export function QuantLayout() {
 const location = useLocation(), navigate = useNavigate();
 const [menuOpen,setMenuOpen]=useState(false);
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
 const reviewer = session.permissions.quant === "review";
 if (reviewer && location.pathname !== "/quant/reviews/factors") return <Navigate to="/quant/reviews/factors" replace />;
 const sections=[{label:'工作空间',items:[['/quant','管理驾驶舱','◫']]},{label:'业务模块',items:[['/quant/data','数据资源','▤'],['/quant/factor','因子工厂','ƒ'],['/quant/strategy','策略研究','⌁'],['/quant/portfolio','组合与执行','▦'],['/quant/monitor','运行与风险','◉']]},{label:'协作与管理',items:[['/quant/reviews','审查中心','✓'],['/quant/agents','Agent 管理','✦']]}];
 const current=sections.flatMap(g=>g.items).find(([to])=>to==='/quant'?location.pathname==='/quant':location.pathname===to||location.pathname.startsWith(to+'/'));
 return <div className={'quant-shell'+(menuOpen?' menu-open':'')}><div className="app-shell">
   <aside className="sidebar"><button className="close mobile-close" aria-label="关闭导航" onClick={()=>setMenuOpen(false)}>×</button>
     <NavLink to="/quant" className="brand"><span className="seal">旸</span><span><strong>旸谷资本</strong><small>SUNVALLEY CAPITAL</small></span></NavLink>
     <div className="workspace-name"><b>SVQuant · 机构量化平台</b>研究与运行工作区</div>
     <nav aria-label="机构量化导航">{sections.map(g=><div key={g.label}><div className="nav-label">{g.label}</div>{g.items.map(([to,label,icon])=>reviewer&&to!=='/quant/reviews'?<span key={to} className="nav-item" aria-disabled="true" title="当前身份为独立研究复核员"><span className="nav-icon" aria-hidden="true">{icon}</span>{label}</span>:<NavLink key={to} to={reviewer?"/quant/reviews/factors":to} end={to==='/quant'} className="nav-item" onClick={()=>setMenuOpen(false)}><span className="nav-icon" aria-hidden="true">{icon}</span>{label}</NavLink>)}</div>)}</nav>
     <div className="side-footer"><span className="version">INSTITUTIONAL QUANT · 开发环境</span></div>
   </aside>
   <div className="stage-area"><header className="topbar"><button className="btn small menu-toggle" aria-label="打开导航" onClick={()=>setMenuOpen(true)}>☰ 导航</button><div className="crumb">机构工作区 / <b>{current?.[1]||'量化投研'}</b></div><div className="top-actions"><span className="preview-label">研究环境</span><span className="identity"><span className="avatar" aria-hidden="true">{(session.user.display_name||session.user.username).slice(0,1)}</span><span className="fine">{session.org.name_cn} · {session.user.display_name||session.user.username} · {reviewer?'独立研究复核员':'量化研究员'}</span></span><button className="btn small" onClick={()=>{clearQuantSession();navigate(quantLoginUrl(),{replace:true});}}>退出</button></div></header>
   <main className="main"><ConfirmProvider><ScrollToTop/><Outlet/></ConfirmProvider></main></div>
 </div></div>;
}
