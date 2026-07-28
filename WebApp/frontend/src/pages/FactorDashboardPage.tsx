import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpDown,
  BarChart3,
  Database,
  Layers,
  Search,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  DYNAMIC_FACTOR_LIBS,
  extractMethod,
  filterTabsFromFactors,
  labelForLibrary,
  libraryKeyFromLabel,
  loadFactors,
  loadLibrarySource,
} from "@/lib/factorCatalog";
import { openOrCreateForFactor, openDetectInNewTab } from "@/lib/detectStore";
import { authHeaders, getStoredUser } from "@/lib/auth";
import {
  buildBuiltinFactorShareStub,
  buildFactorPanelShareDraft,
} from "@/lib/communityShare";
import { PageJump } from "@/components/PageJump";

type PeriodKey = "3m" | "1y" | "3y";
type VerifyStatus = "pending" | "passed" | "failed";
type SortKey =
  | "name_cn"
  | "ic_mean"
  | "rank_ic"
  | "annual_return"
  | "max_drawdown"
  | "q1_turnover"
  | "win_rate"
  | "sharpe"
  | "q1_return"
  | "q5_return"
  | "long_short_spread";

type DashRow = {
  factor_name: string;
  name_cn?: string;
  library?: string;
  ic_mean?: number | null;
  rank_ic?: number | null;
  ir?: number | null;
  q1_return?: number | null;
  q5_return?: number | null;
  long_short_spread?: number | null;
  q1_turnover?: number | null;
  win_rate?: number | null;
  coverage_pool?: number | null;
  sharpe?: number | null;
  annual_return?: number | null;
  max_drawdown?: number | null;
  error?: string | null;
  computed_at?: string;
  verify_status?: VerifyStatus | string;
  verify_note?: string;
};

const VERIFY_OPTIONS: { value: VerifyStatus; label: string; className: string }[] = [
  {
    value: "pending",
    label: "待验证",
    className: "bg-amber-50 text-amber-800 ring-amber-200",
  },
  {
    value: "passed",
    label: "已通过",
    className: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  },
  {
    value: "failed",
    label: "未通过",
    className: "bg-rose-50 text-rose-800 ring-rose-200",
  },
];

function normalizeVerify(v?: string | null): VerifyStatus {
  if (v === "passed" || v === "failed") return v;
  return "pending";
}

function verifyMeta(status?: string | null) {
  const st = normalizeVerify(status);
  return VERIFY_OPTIONS.find((o) => o.value === st) || VERIFY_OPTIONS[0];
}

const UNIVERSES = [
  { value: "CSI300", label: "沪深300" },
  { value: "CSI500", label: "中证500" },
  { value: "CSI1000", label: "中证1000" },
  { value: "SSE50", label: "上证50" },
] as const;

const PERIODS: { key: PeriodKey; label: string }[] = [
  { key: "3m", label: "近3月" },
  { key: "1y", label: "近1年" },
  { key: "3y", label: "近3年" },
];

const PAGE_SIZE = 50;

async function resolvePanelShareCode(
  factorName: string,
  library?: string | null,
): Promise<string> {
  const fname = factorName.trim();
  const lib = (library || "").trim();
  if (!fname) return "";
  if (lib && DYNAMIC_FACTOR_LIBS.has(lib)) {
    return buildBuiltinFactorShareStub(fname, lib);
  }
  try {
    const factors = await loadFactors();
    const meta =
      factors.find((f) => f.name === fname && (!lib || f.library === lib)) ||
      factors.find((f) => f.name === fname);
    if (!meta) {
      return lib ? buildBuiltinFactorShareStub(fname, lib) : "";
    }
    if (DYNAMIC_FACTOR_LIBS.has(meta.library)) {
      return buildBuiltinFactorShareStub(fname, meta.library);
    }
    const src = await loadLibrarySource(meta.libraryFile);
    const method = extractMethod(src, meta.methodName || meta.name).trim();
    return method || buildBuiltinFactorShareStub(fname, meta.library);
  } catch {
    return lib ? buildBuiltinFactorShareStub(fname, lib) : "";
  }
}

function tone(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "text-slate-400";
  if (Math.abs(v) < 0.01) return "text-slate-500";
  return v > 0 ? "text-red-600 font-semibold" : "text-emerald-600 font-semibold";
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

/** IC / RankIC：库内按百分数存（22.87 → 0.2287），界面用小数 */
function fmtIc(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const d = v / 100;
  const sign = d > 0 ? "+" : "";
  return `${sign}${d.toFixed(4)}`;
}

function fmtNum(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  accent,
}: {
  icon: typeof BarChart3;
  label: string;
  value: string;
  hint: string;
  accent: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="mt-1 text-2xl font-bold tracking-tight text-slate-900">{value}</p>
          <p className="mt-1 text-xs text-slate-400">{hint}</p>
        </div>
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${accent}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

export function FactorDashboardPage() {
  const navigate = useNavigate();
  const user = getStoredUser();
  const isAdmin = user?.role === "admin";
  const [universe, setUniverse] = useState("CSI300");
  const [period, setPeriod] = useState<PeriodKey>("3y");
  const [filterUp, setFilterUp] = useState(true);
  const [library, setLibrary] = useState<string>("全部");
  const [query, setQuery] = useState("");
  const [verifyFilter, setVerifyFilter] = useState<"all" | VerifyStatus>("all");
  const [rows, setRows] = useState<DashRow[]>([]);
  const [verifySummary, setVerifySummary] = useState({
    pending: 0,
    passed: 0,
    failed: 0,
  });
  const [job, setJob] = useState<{ status?: string; done?: number; total?: number; current?: string }>({});
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("ic_mean");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [err, setErr] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState<string | null>(null);
  const [verifyBusy, setVerifyBusy] = useState<string | null>(null);

  const [hideErrors, setHideErrors] = useState(true);
  const [page, setPage] = useState(1);
  /** 分类 Tab 跟当前 index.yaml 实际库走（面板不含自定义） */
  const [categoryTabs, setCategoryTabs] = useState<string[]>(["全部"]);

  useEffect(() => {
    void loadFactors(true)
      .then((fs) => {
        const tabs = filterTabsFromFactors(fs.filter((f) => f.library !== "custom_lib"));
        setCategoryTabs(tabs);
        setLibrary((cur) => (tabs.includes(cur) ? cur : "全部"));
      })
      .catch(() => setCategoryTabs(["全部"]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const qs = new URLSearchParams({
        universe,
        period,
        filter_limit_up: filterUp ? "1" : "0",
        filter_suspended: "1",
      });
      if (library !== "全部") {
        const key = libraryKeyFromLabel(library);
        if (key) qs.set("library", key);
      }
      const res = await fetch(`/api/factor/dashboard?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setRows(data.rows || []);
      setJob(data.job || {});
      const vs = data.verify_summary || {};
      setVerifySummary({
        pending: Number(vs.pending) || 0,
        passed: Number(vs.passed) || 0,
        failed: Number(vs.failed) || 0,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [universe, period, filterUp, library]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (job.status !== "running") return;
    const t = window.setInterval(async () => {
      try {
        const r = await fetch("/api/factor/dashboard/status");
        const j = await r.json();
        setJob(j);
        if (j.status === "done" || j.status === "failed") void load();
      } catch {
        /* ignore */
      }
    }, 2000);
    return () => window.clearInterval(t);
  }, [job.status, load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = rows;
    if (hideErrors) {
      list = list.filter((r) => !r.error);
    }
    if (verifyFilter !== "all") {
      list = list.filter((r) => normalizeVerify(r.verify_status) === verifyFilter);
    }
    if (q) {
      list = list.filter(
        (r) =>
          (r.factor_name || "").toLowerCase().includes(q) ||
          (r.name_cn || "").toLowerCase().includes(q),
      );
    }
    const dir = sortDir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      if (sortKey === "name_cn") {
        return dir * String(a.name_cn || a.factor_name).localeCompare(String(b.name_cn || b.factor_name), "zh");
      }
      const av = a[sortKey];
      const bv = b[sortKey];
      const an = typeof av === "number" ? av : -Infinity;
      const bn = typeof bv === "number" ? bv : -Infinity;
      return dir * (an - bn);
    });
  }, [rows, query, sortKey, sortDir, hideErrors, verifyFilter]);

  useEffect(() => {
    setPage(1);
  }, [universe, period, filterUp, library, query, hideErrors, sortKey, sortDir, verifyFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, pageCount);
  const paged = useMemo(() => {
    const start = (pageSafe - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, pageSafe]);

  const errCount = useMemo(() => rows.filter((r) => !!r.error).length, [rows]);
  const okRows = useMemo(() => filtered.filter((r) => !r.error && r.ic_mean != null), [filtered]);
  const avgIc = useMemo(() => {
    if (!okRows.length) return null;
    return okRows.reduce((s, r) => s + (r.ic_mean || 0), 0) / okRows.length;
  }, [okRows]);
  const strongIc = useMemo(() => okRows.filter((r) => Math.abs(r.ic_mean || 0) >= 2).length, [okRows]);

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir("desc");
    }
  };

  const SortTh = ({
    k,
    label,
    align = "left",
  }: {
    k: SortKey;
    label: string;
    align?: "left" | "right";
  }) => (
    <th
      className={`cursor-pointer whitespace-nowrap px-4 py-3 ${
        align === "right" ? "text-right" : "text-left"
      }`}
      onClick={() => toggleSort(k)}
    >
      <span
        className={`inline-flex items-center gap-1 text-xs font-semibold tracking-wide ${
          align === "right" ? "ml-auto" : ""
        } ${sortKey === k ? "text-red-600" : "text-slate-500"}`}
      >
        {label}
        <ArrowUpDown className={`h-3.5 w-3.5 shrink-0 ${sortKey === k ? "opacity-100" : "opacity-40"}`} />
      </span>
    </th>
  );

  const uniLabel = UNIVERSES.find((u) => u.value === universe)?.label || universe;
  const periodLabel = PERIODS.find((p) => p.key === period)?.label || period;

  const shareRowToCommunity = async (r: DashRow) => {
    const next = `/community/new?section=factor`;
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    if (r.error) {
      window.alert("该因子面板指标失败，无法分享。请先刷新或换组合。");
      return;
    }
    setShareBusy(r.factor_name);
    try {
      const factorCode = await resolvePanelShareCode(r.factor_name, r.library);
      const libKey = r.library || "";
      const draft = buildFactorPanelShareDraft({
        name: r.name_cn || r.factor_name,
        factorName: r.factor_name,
        libraryName: libKey || null,
        libraryLabel: libKey ? labelForLibrary(libKey) : null,
        universeLabel: uniLabel,
        periodLabel,
        universeCode: universe,
        periodCode: period,
        filterLimitUp: filterUp,
        filterLabel: filterUp ? "过滤涨停" : "不过滤涨停",
        metrics: {
          ic_mean: r.ic_mean,
          rank_ic: r.rank_ic,
          ir: r.ir,
          annual_return: r.annual_return,
          max_drawdown: r.max_drawdown,
          sharpe: r.sharpe,
          win_rate: r.win_rate ?? r.coverage_pool,
          q1_return: r.q1_return,
          q5_return: r.q5_return,
          long_short_spread: r.long_short_spread,
          q1_turnover: r.q1_turnover,
        },
        factorCode,
        returnTo: "/factor/dashboard",
        returnLabel: "返回因子面板",
      });
      navigate(next, { state: draft });
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setShareBusy(null);
    }
  };

  const onChangeVerify = async (factorName: string, status: VerifyStatus) => {
    const u = getStoredUser();
    if (!u) {
      navigate(`/login?next=${encodeURIComponent("/factor/dashboard")}`);
      return;
    }
    if (u.role !== "admin") {
      window.alert("仅管理员可修改校验状态");
      return;
    }
    setVerifyBusy(factorName);
    try {
      const res = await fetch("/api/factor/dashboard/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ factor_name: factorName, status }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setRows((prev) =>
        prev.map((r) =>
          r.factor_name === factorName
            ? {
                ...r,
                verify_status: data.verify_status || status,
                verify_note: data.verify_note || "",
              }
            : r,
        ),
      );
      setVerifySummary((prev) => {
        const old = normalizeVerify(
          rows.find((r) => r.factor_name === factorName)?.verify_status,
        );
        const next = { ...prev };
        if (old !== status) {
          next[old] = Math.max(0, (next[old] || 0) - 1);
          next[status] = (next[status] || 0) + 1;
        }
        return next;
      });
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setVerifyBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-red-50/50 via-white to-slate-50">
      <div className="mx-auto max-w-[1440px] px-6 py-8">
        <section className="relative mb-6 overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-white to-red-50/60 p-8 shadow-sm">
          <div
            className="pointer-events-none absolute inset-0 opacity-30"
            style={{
              backgroundImage:
                "radial-gradient(circle at 1px 1px, rgb(148 163 184 / 0.35) 1px, transparent 0)",
              backgroundSize: "22px 22px",
            }}
          />
          <div className="relative flex flex-wrap items-start justify-between gap-6">
            <div className="max-w-2xl">
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">因子面板</h1>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                批量看全因子表现（YGQuant RE 回测聚合）。单因子可调参深度检测请用
                <Link to="/factor/detect" className="mx-1 font-medium text-red-600 hover:underline">
                  因子检测
                </Link>
                。
              </p>
              <p className="mt-3 text-xs text-slate-400">
                {uniLabel} · {periodLabel} · {filterUp ? "过滤涨停" : "不过滤涨停"} · 已算{" "}
                {okRows.length}/{filtered.length}
                {" · "}
                <span className="text-amber-700">待验证 {verifySummary.pending}</span>
                {" · "}
                <span className="text-emerald-700">已通过 {verifySummary.passed}</span>
                {" · "}
                <span className="text-rose-700">未通过 {verifySummary.failed}</span>
                {loading ? " · 加载中…" : ""}
                {job.status === "running"
                  ? ` · 后台计算中 ${job.done ?? 0}/${job.total ?? "?"} ${job.current || ""}`
                  : ""}
              </p>
            </div>
          </div>
        </section>

        <section className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            icon={Layers}
            label="缓存因子"
            value={`${filtered.length}`}
            hint={`成功 ${okRows.length} · 失败 ${filtered.length - okRows.length}`}
            accent="bg-blue-50 text-blue-600"
          />
          <StatCard
            icon={TrendingUp}
            label="平均 IC"
            value={avgIc == null ? "—" : fmtIc(avgIc)}
            hint="当前筛选下 IC 均值"
            accent="bg-rose-50 text-rose-600"
          />
          <StatCard
            icon={Zap}
            label="|IC| ≥ 0.02"
            value={`${strongIc}`}
            hint="相对较强预测力"
            accent="bg-amber-50 text-amber-600"
          />
          <StatCard
            icon={Database}
            label="已计算"
            value={`${okRows.length}`}
            hint={filterUp ? "过滤涨停口径" : "不过滤涨停口径"}
            accent="bg-violet-50 text-violet-600"
          />
        </section>

        <div className="mb-4 space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-16 shrink-0 text-xs text-slate-400">分类</span>
            {categoryTabs.map((lab) => (
              <button
                key={lab}
                type="button"
                onClick={() => setLibrary(lab)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  library === lab ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {lab}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-16 shrink-0 text-xs text-slate-400">股票池</span>
            {UNIVERSES.map((u) => (
              <button
                key={u.value}
                type="button"
                onClick={() => setUniverse(u.value)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  universe === u.value ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {u.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-16 shrink-0 text-xs text-slate-400">涨跌停</span>
            <button
              type="button"
              onClick={() => setFilterUp(false)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                !filterUp ? "bg-red-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              不过滤
            </button>
            <button
              type="button"
              onClick={() => setFilterUp(true)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                filterUp ? "bg-red-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              过滤涨停
            </button>
            {!filterUp && filtered.length === 0 && (
              <span className="text-[11px] text-amber-600">
                该口径暂无缓存数据
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-16 shrink-0 text-xs text-slate-400">周期</span>
            {PERIODS.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setPeriod(p.key)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  period === p.key
                    ? "bg-red-50 text-red-600 ring-1 ring-red-200"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-16 shrink-0 text-xs text-slate-400">校验</span>
            {(
              [
                { value: "all" as const, label: "全部" },
                ...VERIFY_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
              ] as { value: "all" | VerifyStatus; label: string }[]
            ).map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setVerifyFilter(o.value)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  verifyFilter === o.value
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {o.label}
                {o.value === "pending"
                  ? ` ${verifySummary.pending}`
                  : o.value === "passed"
                    ? ` ${verifySummary.passed}`
                    : o.value === "failed"
                      ? ` ${verifySummary.failed}`
                      : ""}
              </button>
            ))}
          </div>
        </div>

        {err && <p className="mb-3 text-sm text-red-600">{err}</p>}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900">因子表现总览</h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {errCount > 0 && (
                <label className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-1.5 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={hideErrors}
                    onChange={(e) => setHideErrors(e.target.checked)}
                  />
                  隐藏不可用/失败
                </label>
              )}
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5">
                <Search className="h-3.5 w-3.5 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索因子名称、代码…"
                  className="w-48 bg-transparent text-sm outline-none"
                />
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[1200px] text-left text-sm">
              <thead className="bg-slate-50/80">
                <tr className="border-b border-slate-100">
                  <SortTh k="name_cn" label="因子" />
                  <th className="whitespace-nowrap px-3 py-3 text-xs font-semibold tracking-wide text-slate-500">
                    校验
                  </th>
                  <th className="whitespace-nowrap px-4 py-3 text-xs font-semibold tracking-wide text-slate-500">
                    子类
                  </th>
                  <SortTh k="ic_mean" label="IC均值" align="right" />
                  <SortTh k="rank_ic" label="RankIC" align="right" />
                  <SortTh k="annual_return" label="年化" align="right" />
                  <SortTh k="max_drawdown" label="最大回撤" align="right" />
                  <SortTh k="q1_turnover" label="换手" align="right" />
                  <SortTh k="win_rate" label="胜率" align="right" />
                  <SortTh k="sharpe" label="Sharpe" align="right" />
                  <SortTh k="q1_return" label="Q1分层" align="right" />
                  <SortTh k="q5_return" label="Q5分层" align="right" />
                  <SortTh k="long_short_spread" label="多空差" align="right" />
                  <th className="sticky right-0 z-10 whitespace-nowrap bg-slate-50/95 px-3 py-3 text-center text-xs font-semibold tracking-wide text-slate-500 shadow-[-6px_0_8px_-6px_rgba(15,23,42,0.12)]">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {paged.map((r) => {
                  const win = r.win_rate ?? r.coverage_pool;
                  const lib = labelForLibrary(r.library || "", r.library || "—");
                  const vm = verifyMeta(r.verify_status);
                  return (
                    <tr
                      key={r.factor_name}
                      className="group border-b border-slate-100 transition hover:bg-slate-50/80"
                    >
                      <td className="px-4 py-3.5">
                        <div className="min-w-[12rem]">
                          <p className="font-medium text-slate-900 group-hover:text-red-600">
                            {r.name_cn || r.factor_name}
                          </p>
                          <code className="mt-0.5 block font-mono text-[11px] text-slate-400">
                            {r.factor_name}
                          </code>
                          {r.error ? (
                            <p
                              className={`mt-1 max-w-xs truncate text-[10px] ${
                                r.error.includes("数据不可用")
                                  ? "font-medium text-amber-600"
                                  : "text-red-500"
                              }`}
                              title={r.error}
                            >
                              {r.error.includes("数据不可用")
                                ? r.error.length > 48
                                  ? `${r.error.slice(0, 48)}…`
                                  : r.error
                                : r.error.includes("422")
                                  ? "旧缓存失效，等待重算或点刷新"
                                  : r.error.length > 48
                                    ? `${r.error.slice(0, 48)}…`
                                    : r.error}
                            </p>
                          ) : null}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-3.5">
                        {isAdmin ? (
                          <select
                            value={normalizeVerify(r.verify_status)}
                            disabled={verifyBusy === r.factor_name}
                            onChange={(e) =>
                              void onChangeVerify(
                                r.factor_name,
                                e.target.value as VerifyStatus,
                              )
                            }
                            className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ring-1 ring-inset outline-none disabled:opacity-60 ${vm.className}`}
                            title="跨平台对比校验状态（仅管理员可改）"
                          >
                            {VERIFY_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-semibold ring-1 ring-inset ${vm.className}`}
                            title="仅管理员可修改校验状态"
                          >
                            {vm.label}
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3.5">
                        <span className="inline-flex whitespace-nowrap rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700 ring-1 ring-inset ring-violet-500/20">
                          {lib}
                        </span>
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.ic_mean)}`}>
                        {fmtIc(r.ic_mean)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.rank_ic)}`}>
                        {fmtIc(r.rank_ic)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.annual_return)}`}>
                        {fmtPct(r.annual_return)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.max_drawdown)}`}>
                        {fmtPct(r.max_drawdown)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.q1_turnover)}`}>
                        {fmtPct(r.q1_turnover)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(win)}`}>
                        {fmtPct(win)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.sharpe)}`}>
                        {fmtNum(r.sharpe)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.q1_return)}`}>
                        {fmtPct(r.q1_return)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.q5_return)}`}>
                        {fmtPct(r.q5_return)}
                      </td>
                      <td
                        className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.long_short_spread)}`}
                      >
                        {fmtPct(r.long_short_spread)}
                      </td>
                      <td className="sticky right-0 z-10 whitespace-nowrap bg-white px-3 py-3.5 text-center shadow-[-6px_0_8px_-6px_rgba(15,23,42,0.12)] group-hover:bg-slate-50/95">
                        <div className="inline-flex min-w-[7.5rem] items-center justify-center gap-1">
                          <button
                            type="button"
                            disabled={shareBusy === r.factor_name || !!r.error}
                            onClick={() => void shareRowToCommunity(r)}
                            className="rounded-md px-2 py-1 text-xs font-semibold text-red-600 transition hover:bg-red-50 hover:text-red-700 disabled:opacity-40"
                            title="分享到社区"
                          >
                            {shareBusy === r.factor_name ? "…" : "分享"}
                          </button>
                          <span className="text-slate-300" aria-hidden>
                            |
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              void openOrCreateForFactor(
                                r.factor_name,
                                r.name_cn || r.factor_name,
                              ).then((p) => openDetectInNewTab(p.id));
                            }}
                            className="rounded-md px-2 py-1 text-xs font-semibold text-red-600 transition hover:bg-red-50 hover:text-red-700"
                          >
                            检测
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!filtered.length && (
                  <tr>
                    <td colSpan={14} className="px-4 py-16 text-center text-sm text-slate-400">
                      暂无缓存数据
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {filtered.length > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
              <span>
                共 {filtered.length} 条 · 每页 {PAGE_SIZE} · 第 {pageSafe}/{pageCount} 页
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={pageSafe <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  上一页
                </button>
                <button
                  type="button"
                  disabled={pageSafe >= pageCount}
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  下一页
                </button>
                <PageJump
                  page={pageSafe}
                  totalPages={pageCount}
                  onJump={setPage}
                />
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
