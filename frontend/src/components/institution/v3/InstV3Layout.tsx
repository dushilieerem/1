import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Menu, Search, X } from "lucide-react";
import { clearInstSession, fetchInstMe, getInstToken, type InstSession } from "@/lib/instAuth";
import { visibleV3Nav, v3TitleForPath } from "@/data/instV3Nav";
import { InstSessionContext } from "@/components/institution/instSessionContext";
import "@/pages/institution/v3/v3.css";

function loginUrl(next: string) {
  return `/login?mode=inst&next=${encodeURIComponent(next)}`;
}

function Sidebar({ session, onNavigate }: { session: InstSession; onNavigate?: () => void }) {
  const groups = useMemo(() => visibleV3Nav(session.role, session.permissions), [session]);
  const counts: Record<string, string> = {};
  return (
    <aside className="v3-side">
      <div className="v3-brand">
        <span className="v3-seal">旸</span>
        <div>
          <b>旸谷资本</b>
          <span>SUBJECTIVE INVESTMENT OFFICE</span>
        </div>
      </div>
      {groups.map((group) => (
        <div key={group.label}>
          <div className="v3-nav-label">
            <span>{group.label}</span>
            {group.hint ? <span className="v3-nav-hint">{group.hint}</span> : null}
          </div>
          <nav className="v3-nav">
            {group.items.map((item) => (
              <NavLink
                key={item.key}
                to={item.path}
                end={item.path === "/inst-v3"}
                onClick={onNavigate}
                className={({ isActive }) => `v3-nav-item${isActive ? " on" : ""}`}
              >
                <span className="v3-nav-no">{item.no || "·"}</span>
                <span>{item.label}</span>
                {counts[item.key] ? <span className="v3-nav-count">{counts[item.key]}</span> : null}
              </NavLink>
            ))}
          </nav>
        </div>
      ))}
      <div className="v3-side-note">
        <div><span className="live" />演示环境 · 无真实交易</div>
        <div className="row"><span>全流程环节</span><b>6 个</b></div>
        <div className="row"><span>Agent 工作台</span><b>5 个</b></div>
        <div className="row"><span>人工拍板点</span><b>5 个</b></div>
        <div className="row"><span>自动环节</span><b>1 个</b></div>
      </div>
      <div className="v3-side-foot">
        v3 预览 · 数据来自 svquant_test
        <br />
        页面按登录角色裁剪，不提供角色切换
      </div>
    </aside>
  );
}

export function InstV3Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [session, setSession] = useState<InstSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let alive = true;
    if (!getInstToken()) {
      navigate(loginUrl(location.pathname), { replace: true });
      return () => { alive = false; };
    }
    fetchInstMe()
      .then((next) => {
        if (!alive) return;
        if (!next) {
          navigate(loginUrl(location.pathname), { replace: true });
          return;
        }
        setSession(next);
      })
      .catch((ex: unknown) => {
        if (alive) setError(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onExpired = () => {
      clearInstSession();
      window.location.href = loginUrl("/inst-v3");
    };
    window.addEventListener("svq:inst-auth-expired", onExpired);
    return () => window.removeEventListener("svq:inst-auth-expired", onExpired);
  }, []);

  const logout = () => {
    clearInstSession();
    navigate("/login?mode=inst", { replace: true });
  };

  if (loading) {
    return <div className="inst-v3"><div className="v3-loading">正在校验机构会话…</div></div>;
  }
  if (!session) {
    return (
      <div className="inst-v3">
        <div className="v3-loading">
          机构会话不可用：{error || "请重新登录"}<br />
          <button className="v3-btn primary" style={{ marginTop: 12 }} onClick={() => navigate(loginUrl("/inst-v3"))}>重新登录</button>
        </div>
      </div>
    );
  }

  const currentTitle = v3TitleForPath(location.pathname);
  const submitSearch = () => {
    const q = search.trim();
    navigate(q ? `/inst-v3/pipeline?q=${encodeURIComponent(q)}` : "/inst-v3/pipeline");
  };

  return (
    <InstSessionContext.Provider value={session}>
      <div className="inst-v3">
        <div className="v3-shell">
          <div className="hidden lg:block"><Sidebar session={session} /></div>
          {drawer ? (
            <div className="fixed inset-0 z-50 flex lg:hidden">
              <div className="flex w-72 max-w-[86vw] flex-col bg-[#fbf8fd]">
                <div className="flex items-center justify-end p-2">
                  <button className="rounded-lg p-2 text-[#746b7c] hover:bg-[#f8edf3]" onClick={() => setDrawer(false)} aria-label="关闭菜单">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <Sidebar session={session} onNavigate={() => setDrawer(false)} />
              </div>
              <button className="flex-1 bg-[#2b2533]/35" onClick={() => setDrawer(false)} aria-label="关闭菜单遮罩" />
            </div>
          ) : null}
          <div className="v3-workspace">
            <header className="v3-topbar">
              <div className="v3-crumb">
                <button className="rounded-lg p-1.5 text-[#746b7c] hover:bg-[#f8edf3] lg:hidden" onClick={() => setDrawer(true)} aria-label="打开菜单">
                  <Menu className="h-4 w-4" />
                </button>
                <span>{location.pathname.startsWith("/inst-v3/playbook") ? "规则与说明" : location.pathname.startsWith("/inst-v3/approvals") || location.pathname.startsWith("/inst-v3/research") || location.pathname.startsWith("/inst-v3/debate") || location.pathname.startsWith("/inst-v3/execute") || location.pathname.startsWith("/inst-v3/manage") ? "流程工作台" : "投资工作空间"}</span>
                <span>/</span>
                <b>{currentTitle}</b>
              </div>
              <div className="v3-top-actions">
                <label className="hidden items-center gap-1.5 rounded-lg border border-[#e8e1ee] bg-white px-2.5 py-1.5 md:flex">
                  <Search className="h-3.5 w-3.5 text-[#9b92a1]" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") submitSearch(); }}
                    placeholder="搜索项目、代码、负责人…"
                    className="w-44 bg-transparent text-[11px] outline-none placeholder:text-[#b7afbc]"
                  />
                </label>
                <span className="v3-preview">v3 预览</span>
                <span className="v3-role">{session.role_label_cn}</span>
                <div className="v3-user">
                  <b>{session.user.display_name || session.user.username}</b>
                  <span>{session.org.name_cn}</span>
                </div>
                <button className="v3-exit" onClick={logout}>退出</button>
              </div>
            </header>
            <main className="v3-main"><Outlet /></main>
          </div>
        </div>
      </div>
    </InstSessionContext.Provider>
  );
}
