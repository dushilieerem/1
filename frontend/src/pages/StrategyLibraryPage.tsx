import { quantLoginUrl } from "@/lib/quantAuth";
import { inQuantWorkspace } from "@/lib/researchClient";
import { researchPagePath } from "@/lib/researchClient";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart2,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { PageJump } from "@/components/PageJump";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  getStoredUser,
  prepareAuthHandoff,
  subscribeAuth,
} from "@/lib/researchClient";
import {
  STRATEGY_ARCHIVE_CATEGORIES,
  createEmptyUserStrategy,
  listBuiltinStrategies,
  openBuiltinStrategyDetect,
  openUserLibraryStrategyDetect,
  syncBuiltinStrategies,
  type BuiltinStrategyMeta,
} from "@/lib/strategyLibraryApi";
import {
  createUserStrategyLibrary,
  deleteStrategyFromUserLibrary,
  deleteUserStrategyLibrary,
  listStrategyLibraryItems,
  listUserStrategyLibraries,
  type UserLibraryStrategy,
  type UserStrategyLibrary,
} from "@/lib/userStrategyLibraries";

const PAGE_SIZE = 15;
const BUILTIN_KEY = "__builtin__";

const ROW_BADGE: Record<string, string> = {
  趋势: "bg-blue-50 text-blue-700",
  动量: "bg-violet-50 text-violet-700",
  反转: "bg-amber-50 text-amber-800",
  低波动: "bg-emerald-50 text-emerald-700",
  小市值: "bg-cyan-50 text-cyan-700",
  最小方差: "bg-indigo-50 text-indigo-700",
  统计套利: "bg-fuchsia-50 text-fuchsia-700",
  价值: "bg-orange-50 text-orange-700",
  价值成长: "bg-sky-50 text-sky-700",
  红利: "bg-rose-50 text-rose-700",
  其他: "bg-slate-100 text-slate-600",
};

const COUNT_PILL: Record<string, string> = {
  趋势: "text-blue-600",
  动量: "text-violet-600",
  反转: "text-amber-700",
  低波动: "text-emerald-600",
  小市值: "text-cyan-600",
  最小方差: "text-indigo-600",
  统计套利: "text-fuchsia-600",
  价值: "text-orange-600",
  价值成长: "text-sky-600",
  红利: "text-rose-600",
};

function pageNumbers(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "…")[] = [1];
  if (current > 3) pages.push("…");
  for (let n = Math.max(2, current - 1); n <= Math.min(total - 1, current + 1); n++) {
    pages.push(n);
  }
  if (current < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}

export function StrategyLibraryPage() {
  const confirm = useConfirm();
  const [builtin, setBuiltin] = useState<BuiltinStrategyMeta[]>([]);
  const [userLibs, setUserLibs] = useState<UserStrategyLibrary[]>([]);
  const [userLibItems, setUserLibItems] = useState<UserLibraryStrategy[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [activeLib, setActiveLib] = useState<string>(BUILTIN_KEY);
  const [category, setCategory] = useState("全部");
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [user, setUser] = useState(() => getStoredUser());
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [strategyCreateOpen, setStrategyCreateOpen] = useState(false);
  const [strategyName, setStrategyName] = useState("");
  const [strategyDesc, setStrategyDesc] = useState("");
  const [strategyCategory, setStrategyCategory] = useState<string>("其他");
  const [strategyLibId, setStrategyLibId] = useState("");
  const [strategyCreateErr, setStrategyCreateErr] = useState<string | null>(null);
  const [strategyCreateBusy, setStrategyCreateBusy] = useState(false);

  const isAdmin = user?.role === "admin";

  const builtinCategories = useMemo(() => {
    const labels = new Set(builtin.map((b) => b.strategy_type_label));
    return Array.from(labels);
  }, [builtin]);

  const categoryFilters = useMemo(() => {
    if (activeLib === BUILTIN_KEY) {
      return ["全部", ...builtinCategories];
    }
    // 用户库：固定五类 + 其他（与入库可选分类一致）
    return ["全部", ...STRATEGY_ARCHIVE_CATEGORIES];
  }, [activeLib, builtinCategories]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const b of builtin) {
      c[b.strategy_type_label] = (c[b.strategy_type_label] || 0) + 1;
    }
    return c;
  }, [builtin]);

  const reload = () => {
    setErr(null);
    void listBuiltinStrategies()
      .then(setBuiltin)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
    void listUserStrategyLibraries()
      .then(setUserLibs)
      .catch(() => setUserLibs([]));
  };

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    return subscribeAuth(() => {
      setUser(getStoredUser());
      reload();
    });
  }, []);

  useEffect(() => {
    if (!categoryFilters.includes(category)) setCategory("全部");
  }, [categoryFilters, category]);

  useEffect(() => {
    if (activeLib === BUILTIN_KEY) {
      setUserLibItems([]);
      return;
    }
    const libId = Number(activeLib);
    if (!Number.isFinite(libId)) return;
    let cancelled = false;
    void listStrategyLibraryItems(libId)
      .then((rows) => {
        if (!cancelled) setUserLibItems(rows);
      })
      .catch(() => {
        if (!cancelled) setUserLibItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeLib]);

  const filteredBuiltin = useMemo(() => {
    const q = query.trim().toLowerCase();
    return builtin.filter((m) => {
      if (category !== "全部" && m.strategy_type_label !== category) return false;
      if (!q) return true;
      return (
        m.name.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        m.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [builtin, query, category]);

  const filteredUser = useMemo(() => {
    const q = query.trim().toLowerCase();
    return userLibItems.filter((s) => {
      if (category !== "全部" && (s.categoryLabel || "其他") !== category) {
        return false;
      }
      if (!q) return true;
      return (
        s.name.toLowerCase().includes(q) ||
        (s.codeId || "").toLowerCase().includes(q) ||
        (s.description || "").toLowerCase().includes(q)
      );
    });
  }, [userLibItems, query, category]);

  const filtered =
    activeLib === BUILTIN_KEY ? filteredBuiltin : filteredUser;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const slice = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [query, category, activeLib]);

  const onDetect = async (m: BuiltinStrategyMeta) => {
    setBusyId(m.id);
    setErr(null);
    try {
      await openBuiltinStrategyDetect(m);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const onUserDetect = async (s: UserLibraryStrategy) => {
    setBusyId(`user:${s.id}`);
    setErr(null);
    try {
      await openUserLibraryStrategyDetect(s);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const openCreate = () => {
    if (!user) {
      window.location.href = inQuantWorkspace() ? quantLoginUrl("/quant/strategy/library") : "/login?next=/strategy/library";
      return;
    }
    setCreateName("");
    setCreateErr(null);
    setCreateOpen(true);
  };

  const onSyncBuiltin = async () => {
    if (!isAdmin || syncBusy) return;
    const ok = await confirm({
      title: "更新内置策略库",
      message: "是否更新内置策略库",
      confirmLabel: "开始更新",
    });
    if (!ok) return;
    setSyncBusy(true);
    setErr(null);
    try {
      const r = await syncBuiltinStrategies();
      await listBuiltinStrategies().then(setBuiltin);
      await confirm({
        title: "更新完成",
        message: `内置策略库已更新（${r.upserted} 条）`,
        confirmLabel: "确定",
        alert: true,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncBusy(false);
    }
  };

  const openStrategyCreate = () => {
    if (!user) {
      window.location.href = inQuantWorkspace() ? quantLoginUrl("/quant/strategy/library") : "/login?next=/strategy/library";
      return;
    }
    if (!userLibs.length) {
      window.alert("请先「新增策略库」，再新建策略。");
      return;
    }
    const prefer =
      activeLib !== BUILTIN_KEY && userLibs.some((l) => String(l.id) === activeLib)
        ? activeLib
        : String(userLibs[0].id);
    setStrategyLibId(prefer);
    setStrategyName("");
    setStrategyDesc("");
    setStrategyCategory("其他");
    setStrategyCreateErr(null);
    setStrategyCreateOpen(true);
  };

  const confirmStrategyCreate = async () => {
    const title = strategyName.trim();
    if (!title) {
      setStrategyCreateErr("请填写策略名称");
      return;
    }
    const libId = Number(strategyLibId);
    if (!Number.isFinite(libId)) {
      setStrategyCreateErr("请选择策略库");
      return;
    }
    setStrategyCreateBusy(true);
    setStrategyCreateErr(null);
    try {
      await createEmptyUserStrategy({
        libraryId: libId,
        name: title,
        description: strategyDesc,
        categoryLabel: strategyCategory,
      });
      setActiveLib(String(libId));
      const rows = await listStrategyLibraryItems(libId);
      setUserLibItems(rows);
      setUserLibs((prev) =>
        prev.map((l) =>
          l.id === libId
            ? { ...l, strategyCount: (l.strategyCount || 0) + 1 }
            : l,
        ),
      );
      setStrategyCreateOpen(false);
    } catch (e) {
      setStrategyCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setStrategyCreateBusy(false);
    }
  };

  const confirmCreate = async () => {
    const title = createName.trim();
    if (!title) {
      setCreateErr("请填写策略库名称");
      return;
    }
    if (title.length > 64) {
      setCreateErr("策略库名称最长 64 个字符");
      return;
    }
    setCreateBusy(true);
    setCreateErr(null);
    try {
      const lib = await createUserStrategyLibrary(title);
      setUserLibs((prev) => [lib, ...prev.filter((x) => x.id !== lib.id)]);
      setActiveLib(String(lib.id));
      setCreateOpen(false);
    } catch (e) {
      setCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreateBusy(false);
    }
  };

  const onDeleteLib = async (lib: UserStrategyLibrary) => {
    const ok = await confirm({
      title: "删除策略库",
      message: `确认删除「${lib.name}」？库内策略（若有）将一并移除。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteUserStrategyLibrary(lib.id);
      setUserLibs((prev) => prev.filter((x) => x.id !== lib.id));
      if (activeLib === String(lib.id)) setActiveLib(BUILTIN_KEY);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  const onDeleteStrategy = async (s: UserLibraryStrategy) => {
    const ok = await confirm({
      title: "删除策略",
      message: `确认从库中删除「${s.name}」？`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteStrategyFromUserLibrary(s.libraryId, s.id);
      setUserLibItems((prev) => prev.filter((x) => x.id !== s.id));
      setUserLibs((prev) =>
        prev.map((l) =>
          l.id === s.libraryId
            ? {
                ...l,
                strategyCount: Math.max(0, (l.strategyCount || 1) - 1),
              }
            : l,
        ),
      );
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  const activeLibTitle =
    activeLib === BUILTIN_KEY
      ? "内置策略库"
      : userLibs.find((l) => String(l.id) === activeLib)?.name || "策略库";

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1440px] px-4 py-6 lg:px-6 lg:py-8">
        <div className="relative mb-6 overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm lg:p-6">
          <div className="bg-grid pointer-events-none absolute inset-0 opacity-40" />
          <div className="relative flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-500 text-white shadow">
                  <Layers className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-slate-900">策略库</h1>
                  {err ? <p className="text-sm text-red-500">{err}</p> : null}
                </div>
              </div>
              <div className="mt-3 text-xs text-slate-500">
                <span className="mb-1.5 block font-semibold text-slate-700 lg:mb-0 lg:inline">
                  内置策略分类及数量：
                </span>
                <span className="flex flex-wrap gap-x-3 gap-y-1.5 font-semibold lg:ml-2 lg:inline-flex lg:gap-3">
                  {builtinCategories.map((label) => (
                    <span
                      key={label}
                      className={COUNT_PILL[label] || "text-slate-500"}
                    >
                      {label} {counts[label] || 0}
                    </span>
                  ))}
                </span>
              </div>
            </div>
            <div className="relative flex w-full flex-col gap-2 sm:ml-auto sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
              <div className="flex w-full min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 sm:w-auto sm:flex-none">
                <Search className="h-4 w-4 shrink-0 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索名称、代码…"
                  className="w-full min-w-0 bg-transparent text-sm outline-none sm:w-56"
                />
                {query ? (
                  <button type="button" onClick={() => setQuery("")}>
                    <X className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2 sm:justify-end">
              {isAdmin ? (
                <button
                  type="button"
                  onClick={() => void onSyncBuiltin()}
                  disabled={syncBusy}
                  title="管理员：从 ResearchEngine 全量同步内置策略到数据库（全站共享，不动用户库）"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                >
                  <RefreshCw
                    className={`h-4 w-4 ${syncBusy ? "animate-spin" : ""}`}
                  />
                  {syncBusy ? "更新中…" : "更新内置策略库"}
                </button>
              ) : null}
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
              >
                <Plus className="h-4 w-4" />
                新增策略库
              </button>
              <button
                type="button"
                onClick={openStrategyCreate}
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-100"
              >
                <Plus className="h-4 w-4" />
                新建策略
              </button>
              <Link
                to="/strategy/joinquant"
                className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-200 bg-indigo-50 px-3.5 py-2 text-sm font-semibold text-indigo-900 hover:bg-indigo-100"
              >
                <Upload className="h-4 w-4" />
                聚宽策略
              </Link>
              <Link
                to={researchPagePath("/strategy/research")}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => prepareAuthHandoff()}
                className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              >
                <BarChart2 className="h-4 w-4" />
                检测报告
              </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-5 lg:flex-row">
          <aside className="w-full shrink-0 lg:w-52">
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:sticky lg:top-20">
              <div className="border-b border-slate-100 px-3 py-2.5 text-xs font-semibold text-slate-500">
                策略库
              </div>
              <nav className="max-h-[calc(100vh-14rem)] space-y-0.5 overflow-y-auto p-2">
                <button
                  type="button"
                  onClick={() => setActiveLib(BUILTIN_KEY)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm font-medium transition ${
                    activeLib === BUILTIN_KEY
                      ? "bg-slate-900 text-white"
                      : "text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <FolderOpen className="h-4 w-4 shrink-0 opacity-80" />
                  <span className="truncate">内置策略库</span>
                </button>
                {userLibs.map((lib) => (
                  <div
                    key={lib.id}
                    className={`group flex items-center gap-0.5 rounded-lg ${
                      activeLib === String(lib.id) ? "bg-slate-900" : ""
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setActiveLib(String(lib.id))}
                      className={`flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm font-medium transition ${
                        activeLib === String(lib.id)
                          ? "text-white"
                          : "text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <FolderOpen className="h-4 w-4 shrink-0 opacity-80" />
                      <span className="truncate">{lib.name}</span>
                    </button>
                    <button
                      type="button"
                      title="删除"
                      onClick={() => void onDeleteLib(lib)}
                      className={`mr-1 rounded-md p-1.5 opacity-0 transition group-hover:opacity-100 ${
                        activeLib === String(lib.id)
                          ? "text-white/70 hover:bg-white/10 hover:text-white"
                          : "text-slate-400 hover:bg-red-50 hover:text-red-500"
                      }`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </nav>
            </div>
          </aside>

          <div className="min-w-0 flex-1">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <span className="text-xs font-medium text-slate-500">分类筛选</span>
              <div className="flex flex-wrap gap-1.5">
                {categoryFilters.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setCategory(c)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                      category === c
                        ? "bg-slate-800 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
              <span>
                {activeLibTitle} · 当前 {filtered.length} 个
              </span>
              <span>
                {(pageSafe - 1) * PAGE_SIZE + 1}-
                {Math.min(pageSafe * PAGE_SIZE, filtered.length)} /{" "}
                {filtered.length}
              </span>
            </div>

            <div className="space-y-2">
              {activeLib === BUILTIN_KEY
                ? (slice as BuiltinStrategyMeta[]).map((m) => {
                    const badge =
                      ROW_BADGE[m.strategy_type_label] ??
                      "bg-slate-100 text-slate-600";
                    return (
                      <div
                        key={m.id}
                        className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm lg:flex-row lg:items-center lg:justify-between"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">
                            {m.name}
                          </p>
                          <p className="truncate font-mono text-xs text-slate-400">
                            {m.id}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 lg:shrink-0">
                          {m.execution_mode === "event" ? (
                            <span className="rounded-md bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-800">
                              事件
                            </span>
                          ) : null}
                          <span
                            className={`rounded-md px-2 py-0.5 text-xs font-medium ${badge}`}
                          >
                            {m.strategy_type_label}
                          </span>
                          <button
                            type="button"
                            disabled={busyId === m.id}
                            onClick={() => void onDetect(m)}
                            className="inline-flex h-7 min-w-[3.25rem] items-center justify-center rounded-lg bg-red-50 px-2.5 text-xs font-semibold text-red-600 transition hover:bg-red-100 disabled:opacity-40"
                          >
                            {busyId === m.id ? "…" : "检测"}
                          </button>
                        </div>
                      </div>
                    );
                  })
                : (slice as UserLibraryStrategy[]).map((s) => {
                    const pending =
                      s.pendingDetect === true ||
                      (s.pendingDetect !== false &&
                        !s.detectedAt &&
                        !s.hasArchiveReport);
                    const badge =
                      ROW_BADGE[s.categoryLabel] ?? "bg-slate-100 text-slate-600";
                    const busy = busyId === `user:${s.id}`;
                    const rawDesc = (s.description || "").trim();
                    const subtitle =
                      rawDesc && rawDesc !== s.name.trim()
                        ? rawDesc
                        : "暂无说明";
                    return (
                      <div
                        key={s.id}
                        className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm lg:flex-row lg:items-center lg:justify-between"
                      >
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <p className="truncate font-medium text-slate-900">
                              {s.name}
                            </p>
                            {pending ? (
                              <span className="shrink-0 rounded bg-yellow-300 px-1.5 py-0.5 text-[10px] font-semibold text-yellow-950">
                                待检测
                              </span>
                            ) : null}
                          </div>
                          <p
                            className="truncate text-xs text-slate-400"
                            title={subtitle === "暂无说明" ? undefined : subtitle}
                          >
                            {subtitle}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 lg:shrink-0">
                          <span
                            className={`rounded-md px-2 py-0.5 text-xs font-medium ${badge}`}
                          >
                            {s.categoryLabel || "其他"}
                          </span>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void onUserDetect(s)}
                            className="inline-flex h-7 min-w-[3.25rem] items-center justify-center rounded-lg bg-red-50 px-2.5 text-xs font-semibold text-red-600 transition hover:bg-red-100 disabled:opacity-40"
                          >
                            {busy ? "…" : "检测"}
                          </button>
                          <button
                            type="button"
                            title="删除"
                            onClick={() => void onDeleteStrategy(s)}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition hover:bg-red-50 hover:text-red-500"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
              {!slice.length ? (
                <p className="rounded-xl border border-dashed border-slate-200 bg-white py-16 text-center text-sm text-slate-400">
                  {activeLib === BUILTIN_KEY
                    ? "无匹配策略"
                    : "该策略库暂无策略，可点右上角「新建策略」添加"}
                </p>
              ) : null}
            </div>

            {totalPages > 1 ? (
              <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                <button
                  type="button"
                  disabled={pageSafe <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded-lg border border-slate-200 bg-white p-2 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                {pageNumbers(pageSafe, totalPages).map((n, i) =>
                  n === "…" ? (
                    <span key={`e${i}`} className="px-1 text-slate-400">
                      …
                    </span>
                  ) : (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setPage(n)}
                      className={`min-w-8 rounded-lg px-2 py-1.5 text-sm ${
                        n === pageSafe
                          ? "bg-slate-900 text-white"
                          : "border border-slate-200 bg-white text-slate-700"
                      }`}
                    >
                      {n}
                    </button>
                  ),
                )}
                <button
                  type="button"
                  disabled={pageSafe >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="rounded-lg border border-slate-200 bg-white p-2 disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
                <PageJump page={pageSafe} totalPages={totalPages} onJump={setPage} />
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-900">新增策略库</h3>
            <label className="mt-4 block text-xs font-medium text-slate-600">
              策略库名称
              <input
                autoFocus
                value={createName}
                maxLength={64}
                onChange={(e) => {
                  setCreateName(e.target.value);
                  setCreateErr(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void confirmCreate();
                  }
                }}
                placeholder="例如 A / 我的研究库"
                className="mt-1.5 h-9 w-full rounded-lg border border-slate-200 px-2.5 text-sm outline-none focus:border-slate-400"
              />
            </label>
            <p className="mt-1.5 text-xs text-slate-400">
              <span className={createName.length >= 64 ? "text-red-500" : undefined}>
                {createName.length}/64
              </span>
              {" · 支持中英文、数字、下划线与短横线"}
            </p>
            {createErr ? (
              <p className="mt-2 text-xs text-red-500">{createErr}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600"
              >
                取消
              </button>
              <button
                type="button"
                disabled={createBusy}
                onClick={() => void confirmCreate()}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {strategyCreateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">新建策略</h3>
              <button
                type="button"
                onClick={() => setStrategyCreateOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <label className="block text-xs text-slate-500">
                策略名称
                <input
                  autoFocus
                  value={strategyName}
                  onChange={(e) => {
                    setStrategyName(e.target.value);
                    setStrategyCreateErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                说明
                <input
                  value={strategyDesc}
                  onChange={(e) => setStrategyDesc(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                分类
                <select
                  value={strategyCategory}
                  onChange={(e) => setStrategyCategory(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                >
                  {STRATEGY_ARCHIVE_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-slate-500">
                所属策略库
                <select
                  value={strategyLibId}
                  onChange={(e) => setStrategyLibId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                >
                  {userLibs.map((l) => (
                    <option key={l.id} value={String(l.id)}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {strategyCreateErr ? (
              <p className="mt-2 text-xs text-red-500">{strategyCreateErr}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStrategyCreateOpen(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600"
              >
                取消
              </button>
              <button
                type="button"
                disabled={strategyCreateBusy}
                onClick={() => void confirmStrategyCreate()}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
