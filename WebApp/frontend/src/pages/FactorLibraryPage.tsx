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
  X,
} from "lucide-react";
import { PageJump } from "@/components/PageJump";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  getStoredUser,
  prepareAuthHandoff,
  subscribeAuth,
} from "@/lib/auth";
import {
  builtinCategoryLabelsFromFactors,
  clearFactorCache,
  loadFactors,
  syncOfficialFactorCatalog,
  type FactorMeta,
} from "@/lib/factorCatalog";
import {
  createEmptyUserFactor,
  isFormulaPending,
  openDetectForLibraryFactor,
} from "@/lib/factorLifecycle";
import {
  createUserFactorLibrary,
  deleteFactorFromUserLibrary,
  deleteUserFactorLibrary,
  listLibraryFactors,
  listUserFactorLibraries,
  userLibraryFactorToMeta,
  type UserFactorLibrary,
} from "@/lib/userFactorLibraries";

const PAGE_SIZE = 15;
const BUILTIN_KEY = "__builtin__";

const ROW_ACCENT: Record<string, string> = {
  "动量/趋势": "border-l-blue-500",
  "价值/估值": "border-l-violet-500",
  技术指标: "border-l-sky-500",
  "波动/风险": "border-l-amber-500",
  "量价/成交": "border-l-orange-500",
  情绪因子: "border-l-rose-500",
  风险因子: "border-l-red-600",
  技术指标库: "border-l-fuchsia-500",
  "Alpha158/360": "border-l-indigo-500",
  Alpha库: "border-l-violet-400",
  "WorldQuant/Alpha101": "border-l-emerald-500",
  其他: "border-l-slate-400",
};

const ROW_BADGE: Record<string, string> = {
  "动量/趋势": "bg-blue-50 text-blue-700",
  "价值/估值": "bg-violet-50 text-violet-700",
  技术指标: "bg-sky-50 text-sky-700",
  "波动/风险": "bg-amber-50 text-amber-800",
  "量价/成交": "bg-orange-50 text-orange-700",
  情绪因子: "bg-rose-50 text-rose-700",
  风险因子: "bg-red-50 text-red-800",
  技术指标库: "bg-fuchsia-50 text-fuchsia-700",
  "Alpha158/360": "bg-indigo-50 text-indigo-700",
  Alpha库: "bg-violet-50 text-violet-700",
  "WorldQuant/Alpha101": "bg-emerald-50 text-emerald-700",
  其他: "bg-slate-100 text-slate-600",
};

const COUNT_PILL: Record<string, string> = {
  "动量/趋势": "text-blue-600",
  "价值/估值": "text-violet-600",
  技术指标: "text-sky-600",
  "波动/风险": "text-amber-700",
  "量价/成交": "text-orange-600",
  情绪因子: "text-rose-600",
  风险因子: "text-red-700",
  技术指标库: "text-fuchsia-600",
  "Alpha158/360": "text-indigo-600",
  Alpha库: "text-violet-600",
  "WorldQuant/Alpha101": "text-emerald-700",
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

function FactorRow({
  factor,
  onDelete,
}: {
  factor: FactorMeta;
  onDelete?: () => void;
}) {
  const pending = isFormulaPending(factor);
  // 待写态用亮黄，与「波动/风险」的 amber 明显区分；检测写回后恢复分类色
  const accent = pending
    ? "border-l-yellow-400"
    : ROW_ACCENT[factor.libraryLabel] ?? "border-l-slate-300";
  const badge = pending
    ? "bg-yellow-300 text-yellow-950"
    : ROW_BADGE[factor.libraryLabel] ?? "bg-slate-100 text-slate-600";
  const [busy, setBusy] = useState(false);

  const onDetect = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await openDetectForLibraryFactor(factor);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={`overflow-hidden rounded-xl border border-slate-200 border-l-4 bg-white shadow-sm ${accent} ${
        pending ? "bg-yellow-50/50" : ""
      }`}
    >
      <div className="flex flex-col gap-2.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <code className="inline-block max-w-full break-all rounded bg-slate-100 px-1.5 py-0.5 text-xs leading-snug text-slate-700">
              {factor.name}
            </code>
            {pending ? (
              <span className="rounded bg-yellow-300 px-1.5 py-0.5 text-[10px] font-semibold text-yellow-950">
                待写代码
              </span>
            ) : null}
          </div>
          <div className="mt-1 truncate text-sm font-medium text-slate-800">
            {factor.explain || factor.description}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 self-end sm:self-auto">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badge}`}
          >
            {factor.libraryLabel}
          </span>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onDetect()}
            className="inline-flex h-7 min-w-[3.25rem] items-center justify-center rounded-lg bg-red-50 px-2.5 text-xs font-semibold text-red-600 transition hover:bg-red-100 disabled:opacity-40"
          >
            检测
          </button>
          {onDelete ? (
            <button
              type="button"
              title="删除"
              onClick={() => void onDelete()}
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition hover:bg-red-50 hover:text-red-500"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function FactorLibraryPage() {
  const confirm = useConfirm();
  const [factors, setFactors] = useState<FactorMeta[]>([]);
  const [userLibs, setUserLibs] = useState<UserFactorLibrary[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [activeLib, setActiveLib] = useState<string>(BUILTIN_KEY);
  const [category, setCategory] = useState<string>("全部");
  const [page, setPage] = useState(1);
  const [user, setUser] = useState(() => getStoredUser());
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [factorCreateOpen, setFactorCreateOpen] = useState(false);
  const [factorName, setFactorName] = useState("");
  const [factorDesc, setFactorDesc] = useState("");
  const [factorCategory, setFactorCategory] = useState("");
  const [factorLibId, setFactorLibId] = useState<number | "">("");
  const [factorCreateErr, setFactorCreateErr] = useState<string | null>(null);
  const [factorCreateBusy, setFactorCreateBusy] = useState(false);
  const [userLibFactors, setUserLibFactors] = useState<FactorMeta[]>([]);
  const [syncBusy, setSyncBusy] = useState(false);
  const isAdmin = user?.role === "admin";

  const builtinFactors = useMemo(
    () => factors.filter((f) => f.library !== "custom_lib"),
    [factors],
  );

  const builtinCategories = useMemo(
    () => builtinCategoryLabelsFromFactors(builtinFactors),
    [builtinFactors],
  );

  const categoryFilters = useMemo(() => {
    if (activeLib === BUILTIN_KEY) {
      return ["全部", ...builtinCategories];
    }
    const present = new Set(userLibFactors.map((f) => f.libraryLabel));
    const ordered = [
      ...builtinCategories.filter((c) => present.has(c)),
      ...(present.has("其他") ? ["其他"] : []),
    ];
    for (const lab of present) {
      if (!ordered.includes(lab)) ordered.push(lab);
    }
    return ["全部", ...ordered];
  }, [activeLib, builtinCategories, userLibFactors]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of builtinFactors) {
      c[f.libraryLabel] = (c[f.libraryLabel] || 0) + 1;
    }
    return c;
  }, [builtinFactors]);

  const reload = () => {
    setLoading(true);
    setErr(null);
    void loadFactors(true)
      .then((fs) => {
        setFactors(fs);
        setErr(null);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
    void listUserFactorLibraries()
      .then(setUserLibs)
      .catch(() => setUserLibs([]));
  };

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    return subscribeAuth(() => {
      setUser(getStoredUser());
      clearFactorCache();
      reload();
    });
  }, []);

  useEffect(() => {
    if (!categoryFilters.includes(category)) setCategory("全部");
  }, [categoryFilters, category]);

  useEffect(() => {
    if (activeLib === BUILTIN_KEY) {
      setUserLibFactors([]);
      return;
    }
    const libId = Number(activeLib);
    if (!Number.isFinite(libId)) return;
    let cancelled = false;
    void listLibraryFactors(libId)
      .then((rows) => {
        if (!cancelled) setUserLibFactors(rows.map(userLibraryFactorToMeta));
      })
      .catch(() => {
        if (!cancelled) setUserLibFactors([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeLib]);

  const filtered = useMemo(() => {
    const source = activeLib === BUILTIN_KEY ? builtinFactors : userLibFactors;
    const q = query.trim().toLowerCase();
    return source.filter((f) => {
      if (category !== "全部" && f.libraryLabel !== category) return false;
      if (!q) return true;
      return (
        f.name.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.explain.toLowerCase().includes(q)
      );
    });
  }, [activeLib, builtinFactors, userLibFactors, query, category]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE) || 1);
  const pageNum = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1;
  const pageSafe = Math.min(pageNum, totalPages);
  const slice =
    filtered.length === 0
      ? []
      : filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [query, category, activeLib]);

  const onSyncBuiltin = async () => {
    if (!isAdmin || syncBusy) return;
    const ok = await confirm({
      title: "更新内置因子库",
      message:
        "将从同事 ResearchEngine 拉取全量官方目录并写入共享缓存。所有账户的「内置因子库」会一起更新；各用户自建库不受影响。同步可能需要十几秒。",
      confirmLabel: "开始更新",
    });
    if (!ok) return;
    setSyncBusy(true);
    try {
      const result = await syncOfficialFactorCatalog();
      setFactors(result.factors);
      setErr(null);
      const wq = result.libraryCounts?.worldquant_alpha101;
      window.alert(
        `${result.message}\n当前内置 ${result.factorCount} 个` +
          (wq != null ? `\nWorldQuant ${wq}` : "") +
          (result.changed ? "" : "\n（与上次一致）"),
      );
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncBusy(false);
    }
  };

  const openCreate = () => {
    if (!user) {
      window.location.href = "/login?next=/factor/library";
      return;
    }
    setCreateName("");
    setCreateErr(null);
    setCreateOpen(true);
  };

  const openFactorCreate = () => {
    if (!user) {
      window.location.href = "/login?next=/factor/library";
      return;
    }
    if (!userLibs.length) {
      window.alert("请先「新增因子库」，再新建因子。");
      return;
    }
    const prefer =
      activeLib !== BUILTIN_KEY && userLibs.some((l) => String(l.id) === activeLib)
        ? Number(activeLib)
        : userLibs[0].id;
    setFactorName("");
    setFactorDesc("");
    setFactorCategory("");
    setFactorLibId(prefer);
    setFactorCreateErr(null);
    setFactorCreateOpen(true);
  };

  const confirmFactorCreate = async () => {
    if (factorLibId === "") {
      setFactorCreateErr("请选择所属因子库");
      return;
    }
    if (!factorCategory.trim()) {
      setFactorCreateErr("请选择分类");
      return;
    }
    setFactorCreateBusy(true);
    setFactorCreateErr(null);
    try {
      const created = await createEmptyUserFactor({
        libraryId: Number(factorLibId),
        name: factorName,
        description: factorDesc,
        categoryLabel: factorCategory,
      });
      const meta = userLibraryFactorToMeta(created);
      setActiveLib(String(created.libraryId));
      setUserLibFactors((prev) => [
        meta,
        ...prev.filter((x) => x.name !== meta.name),
      ]);
      setUserLibs((prev) =>
        prev.map((l) =>
          l.id === created.libraryId
            ? { ...l, factorCount: (l.factorCount || 0) + 1 }
            : l,
        ),
      );
      setFactorCreateOpen(false);
    } catch (e) {
      setFactorCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setFactorCreateBusy(false);
    }
  };

  const confirmCreate = async () => {
    const title = createName.trim();
    if (!title) {
      setCreateErr("请填写因子库名称");
      return;
    }
    setCreateBusy(true);
    setCreateErr(null);
    try {
      const lib = await createUserFactorLibrary(title);
      setUserLibs((prev) => [lib, ...prev.filter((x) => x.id !== lib.id)]);
      setActiveLib(String(lib.id));
      setCreateOpen(false);
    } catch (e) {
      setCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreateBusy(false);
    }
  };

  const onDeleteLib = async (lib: UserFactorLibrary) => {
    const ok = await confirm({
      title: "删除因子库",
      message: `确认删除「${lib.name}」？库内因子（若有）将一并移除。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteUserFactorLibrary(lib.id);
      setUserLibs((prev) => prev.filter((x) => x.id !== lib.id));
      if (activeLib === String(lib.id)) setActiveLib(BUILTIN_KEY);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  const onDeleteFactor = async (f: FactorMeta) => {
    const libId = f.userLibraryId;
    const factorId = f.userLibraryFactorId;
    if (libId == null || factorId == null) return;
    const ok = await confirm({
      title: "删除因子",
      message: `确认从库中删除「${f.name}」？`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteFactorFromUserLibrary(libId, factorId);
      setUserLibFactors((prev) =>
        prev.filter((x) => x.userLibraryFactorId !== factorId),
      );
      setUserLibs((prev) =>
        prev.map((l) =>
          l.id === libId
            ? {
                ...l,
                factorCount: Math.max(0, (l.factorCount || 1) - 1),
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
      ? "内置因子库"
      : userLibs.find((l) => String(l.id) === activeLib)?.name || "因子库";

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
                  <h1 className="text-2xl font-bold text-slate-900">因子库</h1>
                  {err ? (
                    <p className="text-sm text-red-500">{err}</p>
                  ) : null}
                </div>
              </div>
              <div className="mt-3 text-xs text-slate-500">
                <span className="mb-1.5 block font-semibold text-slate-700 lg:mb-0 lg:inline">
                  内置因子分类及数量：
                </span>
                <span className="flex flex-wrap gap-x-3 gap-y-1.5 font-semibold lg:ml-2 lg:inline-flex lg:gap-3">
                  {builtinCategories.map((label) => (
                    <span
                      key={label}
                      className={COUNT_PILL[label] || "text-slate-500"}
                    >
                      {label.split("/")[0]} {counts[label] || 0}
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
                {query && (
                  <button type="button" onClick={() => setQuery("")}>
                    <X className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-2 sm:justify-end">
              {isAdmin ? (
                <button
                  type="button"
                  onClick={() => void onSyncBuiltin()}
                  disabled={syncBusy}
                  title="管理员：手动同步 RE 全量内置目录（所有账户共享）"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                >
                  <RefreshCw
                    className={`h-4 w-4 ${syncBusy ? "animate-spin" : ""}`}
                  />
                  {syncBusy ? "更新中…" : "更新内置因子库"}
                </button>
              ) : null}
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
              >
                <Plus className="h-4 w-4" />
                新增因子库
              </button>
              <button
                type="button"
                onClick={openFactorCreate}
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-100"
              >
                <Plus className="h-4 w-4" />
                新建因子
              </button>
              <Link
                to="/factor/detect"
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

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[13rem_minmax(0,1fr)]">
          {/* 左侧栏：内置 + 用户因子库 */}
          <aside className="w-full lg:w-auto order-1">
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:sticky lg:top-20">
              <div className="border-b border-slate-100 px-3 py-2.5 text-xs font-semibold text-slate-500">
                因子库
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
                  <span className="truncate">内置因子库</span>
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

          {/* 主区：分类筛选 + 因子列表 */}
          <div className="min-w-0 order-2">
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
                {activeLibTitle} ·{" "}
                {loading && activeLib === BUILTIN_KEY
                  ? "加载中…"
                  : `当前 ${filtered.length} 个`}
              </span>
              <span>
                {loading && activeLib === BUILTIN_KEY
                  ? "…"
                  : filtered.length === 0
                    ? `0 / 0`
                    : `${(pageSafe - 1) * PAGE_SIZE + 1}-${Math.min(
                        pageSafe * PAGE_SIZE,
                        filtered.length,
                      )} / ${filtered.length}`}
              </span>
            </div>

            <div className="space-y-2">
              {loading && activeLib === BUILTIN_KEY ? (
                <p className="py-16 text-center text-sm text-slate-400">
                  正在加载内置因子目录…
                </p>
              ) : (
                <>
              {slice.map((f) => (
                <FactorRow
                  key={`${f.library}:${f.name}:${f.userLibraryFactorId ?? ""}`}
                  factor={f}
                  onDelete={
                    activeLib !== BUILTIN_KEY &&
                    f.userLibraryFactorId != null &&
                    f.userLibraryId != null
                      ? () => void onDeleteFactor(f)
                      : undefined
                  }
                />
              ))}
              {!slice.length && (
                <p className="py-16 text-center text-sm text-slate-400">
                  {activeLib === BUILTIN_KEY
                    ? "无匹配因子"
                    : "该因子库暂无因子，可点右上角「新建因子」添加"}
                </p>
              )}
                </>
              )}
            </div>

            {totalPages > 1 && (
              <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                <div className="flex items-center gap-1">
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
                        className={`min-w-[2rem] rounded-lg px-2 py-1.5 text-sm ${
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
                </div>
                <PageJump page={pageSafe} totalPages={totalPages} onJump={setPage} />
              </div>
            )}
          </div>
        </div>
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-900">新增因子库</h3>
            <label className="mt-4 block text-xs font-medium text-slate-600">
              因子库名称
              <input
                autoFocus
                value={createName}
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

      {factorCreateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">新建因子</h3>
              <button
                type="button"
                onClick={() => setFactorCreateOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <label className="block text-xs text-slate-500">
                因子代码名
                <input
                  autoFocus
                  value={factorName}
                  onChange={(e) => {
                    setFactorName(e.target.value);
                    setFactorCreateErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                中文解释
                <input
                  value={factorDesc}
                  onChange={(e) => {
                    setFactorDesc(e.target.value);
                    setFactorCreateErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                分类
                <select
                  value={factorCategory}
                  onChange={(e) => {
                    setFactorCategory(e.target.value);
                    setFactorCreateErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                >
                  <option value="">请选择</option>
                  {[...builtinCategories, "其他"].map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-slate-500">
                所属用户因子库
                <select
                  value={factorLibId === "" ? "" : String(factorLibId)}
                  onChange={(e) => {
                    setFactorLibId(
                      e.target.value ? Number(e.target.value) : "",
                    );
                    setFactorCreateErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                >
                  <option value="">请选择</option>
                  {userLibs.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {factorCreateErr ? (
              <p className="mt-2 text-xs text-red-500">{factorCreateErr}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setFactorCreateOpen(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600"
              >
                取消
              </button>
              <button
                type="button"
                disabled={factorCreateBusy}
                onClick={() => void confirmFactorCreate()}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
              >
                {factorCreateBusy ? "创建中…" : "确定"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
