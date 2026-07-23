import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Layers,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { FactorFormula } from "@/components/FactorFormula";
import { authHeaders, getStoredUser, prepareAuthHandoff, subscribeAuth } from "@/lib/auth";
import {
  DYNAMIC_FACTOR_LIBS,
  FILTER_TABS,
  LABELS,
  clearFactorCache,
  extractMethod,
  formatFactorFormula,
  loadFactors,
  loadLibrarySource,
  type FactorMeta,
} from "@/lib/factorCatalog";
import { openOrCreateForFactor, openDetectInNewTab } from "@/lib/detectStore";

const PAGE_SIZE = 15;

const TAB_ACTIVE: Record<string, string> = {
  全部: "bg-slate-900 text-white shadow-md",
  "动量/趋势": "bg-blue-600 text-white shadow-md shadow-blue-200",
  "价值/估值": "bg-violet-600 text-white shadow-md shadow-violet-200",
  技术指标: "bg-sky-600 text-white shadow-md shadow-sky-200",
  "波动/风险": "bg-amber-600 text-white shadow-md shadow-amber-200",
  "量价/成交": "bg-orange-600 text-white shadow-md shadow-orange-200",
  自定义: "bg-emerald-600 text-white shadow-md shadow-emerald-200",
  聚宽情绪: "bg-rose-600 text-white shadow-md shadow-rose-200",
  聚宽风险: "bg-red-700 text-white shadow-md shadow-red-200",
  聚宽技术: "bg-fuchsia-600 text-white shadow-md shadow-fuchsia-200",
  Qlib特征: "bg-indigo-600 text-white shadow-md shadow-indigo-200",
};

const ROW_ACCENT: Record<string, string> = {
  "动量/趋势": "border-l-blue-500",
  "价值/估值": "border-l-violet-500",
  技术指标: "border-l-sky-500",
  "波动/风险": "border-l-amber-500",
  "量价/成交": "border-l-orange-500",
  自定义: "border-l-emerald-500",
  聚宽情绪: "border-l-rose-500",
  聚宽风险: "border-l-red-600",
  聚宽技术: "border-l-fuchsia-500",
  Qlib特征: "border-l-indigo-500",
};

const ROW_BADGE: Record<string, string> = {
  "动量/趋势": "bg-blue-50 text-blue-700",
  "价值/估值": "bg-violet-50 text-violet-700",
  技术指标: "bg-sky-50 text-sky-700",
  "波动/风险": "bg-amber-50 text-amber-800",
  "量价/成交": "bg-orange-50 text-orange-700",
  自定义: "bg-emerald-50 text-emerald-700",
  聚宽情绪: "bg-rose-50 text-rose-700",
  聚宽风险: "bg-red-50 text-red-800",
  聚宽技术: "bg-fuchsia-50 text-fuchsia-700",
  Qlib特征: "bg-indigo-50 text-indigo-700",
};

const COUNT_PILL: Record<string, string> = {
  "动量/趋势": "text-blue-600",
  "价值/估值": "text-violet-600",
  技术指标: "text-sky-600",
  "波动/风险": "text-amber-700",
  "量价/成交": "text-orange-600",
  自定义: "text-emerald-600",
  聚宽情绪: "text-rose-600",
  聚宽风险: "text-red-700",
  聚宽技术: "text-fuchsia-600",
  Qlib特征: "text-indigo-600",
};

function pageNumbers(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "…")[] = [1];
  if (current > 3) pages.push("…");
  for (let n = Math.max(2, current - 1); n <= Math.min(total - 1, current + 1); n++) pages.push(n);
  if (current < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}

function FactorRow({
  factor,
  expanded,
  onToggle,
  onDeleted,
}: {
  factor: FactorMeta;
  expanded: boolean;
  onToggle: () => void;
  onDeleted?: () => void;
}) {
  const isCustom = factor.library === "custom_lib";
  const accent = ROW_ACCENT[factor.libraryLabel] ?? "border-l-slate-300";
  const badge = ROW_BADGE[factor.libraryLabel] ?? "bg-slate-100 text-slate-600";
  const [formula, setFormula] = useState(factor.formula);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    if (DYNAMIC_FACTOR_LIBS.has(factor.library)) {
      setFormula(
        `# ${factor.description}\n# 动态注册特征（${factor.libraryFile}）；检测时由 RE library_name=qlib_alpha 加载`,
      );
      return;
    }
    void loadLibrarySource(factor.libraryFile)
      .then((src) => {
        if (cancelled) return;
        const method = extractMethod(src, factor.methodName || factor.name);
        // 展示完整 def … 方法（含函数名），与 RE 写法一致
        const fromSrc = formatFactorFormula(method, factor.params);
        setFormula(fromSrc || method || factor.formula || "");
      })
      .catch(() => {
        if (!cancelled) setFormula(factor.formula || factor.description || "");
      });
    return () => {
      cancelled = true;
    };
  }, [expanded, factor]);

  const onDetect = (e: React.MouseEvent) => {
    e.stopPropagation();
    void openOrCreateForFactor(factor.name, factor.description).then((p) => {
      openDetectInNewTab(p.id);
    });
  };

  const onDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`从列表下线「${factor.description}」？`)) return;
    setBusy(true);
    try {
      const r = await fetch(`/api/factor/custom/${encodeURIComponent(factor.name)}`, {
        method: "DELETE",
        headers: { ...authHeaders() },
      });
      const j = (await r.json()) as { error?: string };
      if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
      clearFactorCache();
      onDeleted?.();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={`group overflow-hidden rounded-xl border border-slate-200/90 border-l-[3px] bg-white shadow-sm transition hover:shadow-md ${accent} ${
        expanded ? "ring-1 ring-slate-200" : ""
      }`}
    >
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3.5 text-left">
        <div
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition ${
            expanded ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500 group-hover:bg-slate-200"
          }`}
        >
          <ChevronDown className={`h-4 w-4 transition ${expanded ? "rotate-180" : ""}`} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
              {factor.name}
            </code>
          </div>
          <p className="mt-0.5 line-clamp-1 text-sm text-slate-700">{factor.explain || "暂无简介"}</p>
        </div>
        {/* 右侧固定槽位：分类徽章 | 编辑/删除(占位) | 检测 — 保证各行对齐 */}
        <div
          className="flex shrink-0 items-center gap-2"
          onClick={(e) => e.stopPropagation()}
        >
          <span
            className={`inline-flex h-7 min-w-[4.75rem] items-center justify-center rounded-md px-2 text-[10px] font-semibold ${badge}`}
          >
            {isCustom ? "自定义" : factor.libraryLabel}
          </span>
          <div className="flex h-7 w-[4.25rem] items-center justify-end gap-0.5">
            {isCustom ? (
              <>
                <Link
                  to={`/factor/library/custom/${encodeURIComponent(factor.name)}`}
                  className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                  title="编辑"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Link>
                <button
                  type="button"
                  disabled={busy}
                  onClick={(e) => void onDelete(e)}
                  className="rounded-lg p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onDetect}
            className="inline-flex h-7 min-w-[3.25rem] items-center justify-center rounded-lg bg-red-50 px-2.5 text-xs font-semibold text-red-600 transition hover:bg-red-100"
          >
            检测
          </button>
        </div>
      </button>
      {expanded && (
        <div className="border-t border-slate-100 bg-gradient-to-b from-slate-50/90 to-white px-4 py-3 pl-14">
          <FactorFormula formula={formula} />
        </div>
      )}
    </div>
  );
}

export function FactorLibraryPage() {
  const [factors, setFactors] = useState<FactorMeta[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<string>("全部");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [user, setUser] = useState(() => getStoredUser());

  const reload = () =>
    void loadFactors(true)
      .then(setFactors)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));

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

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of factors) c[f.libraryLabel] = (c[f.libraryLabel] || 0) + 1;
    return c;
  }, [factors]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return factors.filter((f) => {
      if (tab !== "全部" && f.libraryLabel !== tab) return false;
      if (!q) return true;
      return (
        f.name.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.explain.toLowerCase().includes(q)
      );
    });
  }, [factors, query, tab]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const slice = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [query, tab]);

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1440px] px-6 py-8">
        <div className="relative mb-6 overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
          <div className="bg-grid pointer-events-none absolute inset-0 opacity-40" />
          <div className="relative flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-500 text-white shadow">
                  <Layers className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-slate-900">因子库</h1>
                  <p className="text-sm text-slate-500">
                    点击行展开公式 · 共 {factors.length} 个
                    {err ? ` · ${err}` : ""}
                  </p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-3 text-xs font-semibold">
                {Object.values(LABELS).map((label) => (
                  <span key={label} className={COUNT_PILL[label] || "text-slate-500"}>
                    {label.split("/")[0]} {counts[label] || 0}
                  </span>
                ))}
              </div>
            </div>
            <div className="relative flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2">
                <Search className="h-4 w-4 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索名称、代码…"
                  className="w-48 bg-transparent text-sm outline-none sm:w-56"
                />
                {query && (
                  <button type="button" onClick={() => setQuery("")}>
                    <X className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                )}
              </div>
              <Link
                to="/factor/library/custom/new"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
              >
                <Plus className="h-4 w-4" />
                新增因子
              </Link>
              <Link
                to="/factor/detect"
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => prepareAuthHandoff()}
                className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              >
                <BarChart2 className="h-4 w-4" />
                检测
              </Link>
            </div>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          {FILTER_TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                tab === t ? TAB_ACTIVE[t] || "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {t === "全部" ? t : `${t}因子`.replace("因子因子", "因子")}
            </button>
          ))}
        </div>

        {!user && tab === "自定义" ? (
          <p className="mb-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            自定义因子按账号隔离，请先{" "}
            <Link to="/login?next=/factor/library" className="font-semibold underline">
              登录
            </Link>{" "}
            后查看与新增。
          </p>
        ) : null}

        <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
          <span>当前 {filtered.length} 个</span>
          <span>
            {(pageSafe - 1) * PAGE_SIZE + 1}-{Math.min(pageSafe * PAGE_SIZE, filtered.length)} / {filtered.length}
          </span>
        </div>

        <div className="space-y-2">
          {slice.map((f) => (
            <FactorRow
              key={`${f.library}:${f.name}`}
              factor={f}
              expanded={expanded === f.name}
              onToggle={() => setExpanded((v) => (v === f.name ? null : f.name))}
              onDeleted={reload}
            />
          ))}
          {!slice.length && <p className="py-16 text-center text-sm text-slate-400">无匹配因子</p>}
        </div>

        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-center gap-1">
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
                <span key={`e${i}`} className="px-2 text-slate-400">
                  …
                </span>
              ) : (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPage(n)}
                  className={`min-w-9 rounded-lg px-2 py-1.5 text-sm font-medium ${
                    n === pageSafe ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-100"
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
        )}
      </div>
    </div>
  );
}
