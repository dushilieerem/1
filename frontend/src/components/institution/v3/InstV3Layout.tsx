import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Menu, Search, X } from "lucide-react";
import { clearInstSession, fetchInstMe, getInstToken, type InstSession } from "@/lib/instAuth";
import { instApi } from "@/lib/instApi";
import { visibleV3Nav, v3TitleForPath } from "@/data/instV3Nav";
import { InstSessionContext } from "@/components/institution/instSessionContext";
import "@/pages/institution/v3/v3.css";

function loginUrl(next: string) {
  return `/login?mode=inst&next=${encodeURIComponent(next)}`;
}

function workspaceForPath(path: string): string {
  if (path.startsWith("/inst/research")) return "research";
  if (path.startsWith("/inst/debate")) return "debate";
  if (path.startsWith("/inst/approvals")) return "approvals";
  if (path.startsWith("/inst/execute")) return "execution";
  if (path.startsWith("/inst/manage")) return "monitor";
  if (path.startsWith("/inst/playbook") || path.startsWith("/inst/pipeline")) return "overview";
  return "overview";
}

type SearchItem = {
  company_id: number;
  symbol?: string;
  name?: string;
  market?: string;
  industry?: string;
  data_status?: string;
  pool_status?: string;
  ref_price?: number | null;
  case_id?: number | null;
  stage_no?: number | null;
  stage_name?: string | null;
  version_no?: number | null;
};

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
                end={item.path === "/inst"}
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
  const [searchOpen, setSearchOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<SearchItem[]>([]);
  const [searchActive, setSearchActive] = useState(-1);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const openingRef = useRef<number | null>(null);
  const searchRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const q = search.trim();
    if (!q) {
      setSearchResults([]);
      setSearchActive(-1);
      setSearchError(null);
      setSearching(false);
      return;
    }
    let alive = true;
    setSearching(true);
    setSearchError(null);
    const timer = window.setTimeout(() => {
      instApi<{ items: SearchItem[] }>(`/search?q=${encodeURIComponent(q)}&limit=8`)
        .then((res) => {
          if (!alive) return;
          const items = res.items || [];
          setSearchResults(items);
          setSearchActive(items.length ? 0 : -1);
        })
        .catch((ex: unknown) => {
          if (!alive) return;
          setSearchResults([]);
          setSearchActive(-1);
          setSearchError(ex instanceof Error ? ex.message : String(ex));
        })
        .finally(() => { if (alive) setSearching(false); });
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [search]);

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  useEffect(() => {
    let alive = true;
    if (!getInstToken()) {
      navigate(loginUrl(`${location.pathname}${location.search}`), { replace: true });
      return () => { alive = false; };
    }
    fetchInstMe()
      .then((next) => {
        if (!alive) return;
        if (!next) {
          navigate(loginUrl(`${location.pathname}${location.search}`), { replace: true });
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
      window.location.href = loginUrl("/inst");
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
          <button className="v3-btn primary" style={{ marginTop: 12 }} onClick={() => navigate(loginUrl("/inst"))}>重新登录</button>
        </div>
      </div>
    );
  }

  const currentTitle = v3TitleForPath(location.pathname);
  const canStartResearch = session.role === "manager";

  const openSearchItem = async (item: SearchItem) => {
    if (openingRef.current != null) return;
    setSearchOpen(false);
    setSearchError(null);
    if (item.case_id) {
      const path = item.stage_no != null && item.stage_no <= 2
        ? `/inst/research?key=${encodeURIComponent(`case:${item.case_id}`)}`
        : `/inst/pipeline/result?key=${encodeURIComponent(`case:${item.case_id}`)}`;
      navigate(path);
      return;
    }
    if (!canStartResearch) {
      setSearchError("当前账号没有新建研究的权限");
      setSearchOpen(true);
      return;
    }
    openingRef.current = item.company_id;
    setOpeningId(item.company_id);
    try {
      const created = await instApi<{ id: number }>(`/companies/${item.company_id}/research`, {
        method: "POST",
        body: {},
      });
      navigate(`/inst/research?key=${encodeURIComponent(`case:${created.id}`)}`);
    } catch (ex) {
      setSearchError(ex instanceof Error ? ex.message : String(ex));
      setSearchOpen(true);
    } finally {
      openingRef.current = null;
      setOpeningId(null);
    }
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
                  <button className="rounded-lg p-2 text-[#5f5766] hover:bg-[#f8edf3]" onClick={() => setDrawer(false)} aria-label="关闭菜单">
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
                <button className="rounded-lg p-1.5 text-[#5f5766] hover:bg-[#f8edf3] lg:hidden" onClick={() => setDrawer(true)} aria-label="打开菜单">
                  <Menu className="h-4 w-4" />
                </button>
                <span>{location.pathname.startsWith("/inst/playbook") ? "规则与说明" : location.pathname.startsWith("/inst/approvals") || location.pathname.startsWith("/inst/research") || location.pathname.startsWith("/inst/debate") || location.pathname.startsWith("/inst/execute") || location.pathname.startsWith("/inst/manage") ? "流程工作台" : "投资工作空间"}</span>
                <span>/</span>
                <b>{currentTitle}</b>
              </div>
              <div className="v3-top-actions">
                <div ref={searchRef} className="v3-search-wrap hidden md:block">
                  <label className="flex items-center gap-2 rounded-[10px] border border-[#e8e1ee] bg-white px-3 py-2">
                    <Search className="h-3.5 w-3.5 text-[#6b6370]" />
                    <input
                      value={search}
                      onChange={(e) => { setSearch(e.target.value); setSearchOpen(true); }}
                      onFocus={() => setSearchOpen(true)}
                      role="combobox"
                      aria-expanded={searchOpen && !!search.trim()}
                      aria-controls="v3-search-listbox"
                      aria-autocomplete="list"
                      aria-activedescendant={
                        searchActive >= 0 && searchResults[searchActive]
                          ? `v3-search-opt-${searchResults[searchActive].company_id}`
                          : undefined
                      }
                      onKeyDown={(e) => {
                        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                          if (!searchResults.length) return;
                          e.preventDefault();
                          setSearchOpen(true);
                          const delta = e.key === "ArrowDown" ? 1 : -1;
                          setSearchActive((i) => {
                            const base = i < 0 ? (delta > 0 ? -1 : 0) : i;
                            return (base + delta + searchResults.length) % searchResults.length;
                          });
                        } else if (e.key === "Enter") {
                          const item = searchResults[searchActive] || searchResults[0];
                          if (!item || openingId) return;
                          e.preventDefault();
                          void openSearchItem(item);
                        } else if (e.key === "Escape") {
                          setSearchOpen(false);
                        }
                      }}
                      placeholder="搜索股票代码或名称…"
                      className="w-44 bg-transparent text-[11px] outline-none placeholder:text-[#6b6370]"
                    />
                  </label>
                  {searchOpen && search.trim() ? (
                    <div className="v3-search-pop" role="listbox" id="v3-search-listbox">
                      {searching ? <div className="v3-search-state">搜索中…</div> : null}
                      {!searching && searchError ? <div className="v3-search-state error">{searchError}</div> : null}
                      {!searching && !searchError && !searchResults.length ? <div className="v3-search-state">未找到匹配股票</div> : null}
                      {!searching && !searchError ? searchResults.map((item, index) => (
                        <button
                          key={item.company_id}
                          id={`v3-search-opt-${item.company_id}`}
                          role="option"
                          aria-selected={index === searchActive}
                          className={`v3-search-item${index === searchActive ? " on" : ""}`}
                          disabled={openingId === item.company_id}
                          onMouseEnter={() => setSearchActive(index)}
                          onClick={() => void openSearchItem(item)}
                        >
                          <span className="v3-search-main">
                            <b>{item.name || item.symbol}</b>
                            <span>{item.symbol} · {item.industry || "行业待补充"} · {item.data_status || "数据待补充"}</span>
                          </span>
                          <span className="v3-search-side">
                            {item.case_id ? (
                              <>
                                <span className="v3-chip info">{item.stage_name || "在流程中"}</span>
                                <span className="v3-chip">版本 {item.version_no ?? "—"}</span>
                              </>
                            ) : (
                              <span className="v3-chip gold">{canStartResearch ? (openingId === item.company_id ? "创建中…" : "进入研究") : "无研究权限"}</span>
                            )}
                          </span>
                        </button>
                      )) : null}
                    </div>
                  ) : null}
                </div>
                <span className="v3-role">{session.role_label_cn}</span>
                <div className="v3-user">
                  <b>{session.user.display_name || session.user.username}</b>
                  <span>{session.org.name_cn}</span>
                </div>
                <button className="v3-exit" onClick={logout}>退出</button>
              </div>
            </header>
            <main className="v3-main">
              {(session.permissions?.[workspaceForPath(location.pathname)] || "none") === "none" ? (
                <div className="v3-card">
                  <div className="v3-empty">当前角色无权访问该工作区（{session.role_label_cn}）。</div>
                </div>
              ) : (
                <Outlet />
              )}
            </main>
          </div>
        </div>
      </div>
    </InstSessionContext.Provider>
  );
}
