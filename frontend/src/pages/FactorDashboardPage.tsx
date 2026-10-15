import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpDown,
  BarChart3,
  Database,
  Layers,
  RefreshCw,
  Search,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  DYNAMIC_FACTOR_LIBS,
  builtinCategoryLabelsFromFactors,
  extractMethod,
  labelForLibrary,
  loadFactors,
  loadLibrarySource,
} from "@/lib/factorCatalog";
import { isPlatformFactorLib } from "@/lib/detectComboCode";
import { icUnavailableHint } from "@/lib/factorPanelLabels";
import { openOrCreateForFactor, openDetectPlaceholderTab, navigateDetectTab } from "@/lib/detectStore";
import { authHeaders, getStoredUser } from "@/lib/auth";
import {
  buildBuiltinFactorShareStub,
  buildFactorPanelShareDraft,
} from "@/lib/communityShare";
import { PageJump, PagerBar } from "@/components/PageJump";

type PeriodKey = "3m" | "1y" | "3y";
type VerifyStatus = "pending" | "passed" | "failed";
type SortKey =
  | "name_cn"
  | "ic_mean"
  | "rank_ic"
  | "annual_return"
  | "max_drawdown"
  | "turnover"
  | "q1_turnover"
  | "q5_turnover"
  | "win_rate"
  | "sharpe"
  | "q1_return"
  | "q5_return"
  | "long_short_spread";

/** 面板回测口径（后端 /api/factor/dashboard 透出，见 dashboard_store.PANEL_PORTFOLIO_INFO）。 */
type PanelPortfolio = {
  portfolio_type?: string;
  portfolio_label?: string;
  groups?: number;
  rebalance_days?: number;
  cost?: string;
  execution_timing?: string;
  note?: string;
};

type DashRow = {
  factor_name: string;
  name_cn?: string;
  library?: string;
  /** 分类（来自 RE 目录，后端在行上补齐）：如「动量因子」 */
  category_id?: string;
  category_label?: string;
  ic_mean?: number | null;
  rank_ic?: number | null;
  /**
   * IC 不可用的原因（RE `factor_analysis.definition.ic_unavailable_reason`）。
   * 与「计算失败」不同：这一行算成功了，只是因子/数据本身让 IC 无定义。
   * 老响应或计算失败时为 null。
   */
  ic_unavailable_reason?: string | null;
  ir?: number | null;
  q1_return?: number | null;
  q5_return?: number | null;
  long_short_spread?: number | null;
  /** 组合（主组合）换手 */
  turnover?: number | null;
  /** 逐分位换手：最高分位 Q1 / 最低分位 Q5 */
  q1_turnover?: number | null;
  q5_turnover?: number | null;
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

/**
 * 只列出 RE 实际支持的股票池：其余池 RE 直接 422
 * （`不支持的股票池 'CSI1000'，可用: ['ALL_A','A_SHARE','CSI300','CSI500','CSI_ALL']`）。
 * 列出后点开必然空表，不如不展示；后端日更也只跑这两个池。
 */
const UNIVERSES = [
  { value: "CSI300", label: "沪深300" },
  { value: "CSI500", label: "中证500" },
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
  if (lib && (DYNAMIC_FACTOR_LIBS.has(lib) || isPlatformFactorLib(lib))) {
    return buildBuiltinFactorShareStub(fname, lib, fname);
  }
  try {
    const factors = await loadFactors();
    const meta =
      factors.find((f) => f.name === fname && (!lib || f.library === lib)) ||
      factors.find((f) => f.name === fname);
    if (!meta) {
      return lib ? buildBuiltinFactorShareStub(fname, lib, fname) : "";
    }
    if (
      isPlatformFactorLib(meta.library) ||
      DYNAMIC_FACTOR_LIBS.has(meta.library)
    ) {
      const label =
        (meta.description || "").trim() ||
        (meta.explain || "").trim() ||
        fname;
      return buildBuiltinFactorShareStub(fname, meta.library, label);
    }
    // 用户自建库等：仍可贴实现
    const src = await loadLibrarySource(meta.libraryFile);
    const method = extractMethod(src, meta.methodName || meta.name).trim();
    const label =
      (meta.description || "").trim() ||
      (meta.explain || "").trim() ||
      fname;
    return method || buildBuiltinFactorShareStub(fname, meta.library, label);
  } catch {
    return lib ? buildBuiltinFactorShareStub(fname, lib, fname) : "";
  }
}

/** 行的分类：优先 RE 目录补的 category_label，回退库名映射（单库时即「主因子库」） */
function rowCategory(r: DashRow): string {
  return r.category_label || labelForLibrary(r.library || "");
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
  /** 分类筛选：RE 目录的分类名（如「动量因子」），不是库名 */
  const [category, setCategory] = useState<string>("全部");
  const [query, setQuery] = useState("");
  const [verifyFilter, setVerifyFilter] = useState<"all" | VerifyStatus>("all");
  const [rows, setRows] = useState<DashRow[]>([]);
  const [portfolio, setPortfolio] = useState<PanelPortfolio | null>(null);
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
  /** 分类 Tab 跟 RE 目录的分类走（面板不含自定义 / 用户库） */
  const [categoryTabs, setCategoryTabs] = useState<string[]>(["全部"]);
  const [refreshBusy, setRefreshBusy] = useState(false);

  useEffect(() => {
    void loadFactors(true)
      .then((fs) => {
        const tabs = [
          "全部",
          ...builtinCategoryLabelsFromFactors(
            fs.filter((f) => f.library !== "custom_lib"),
          ),
        ];
        setCategoryTabs(tabs);
        setCategory((cur) => (tabs.includes(cur) ? cur : "全部"));
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
      // 分类不做服务端过滤：单库（主因子库）下 library 已无区分度，
      // 改由前端按行的 category_label 过滤（本页本就整批取回后本地搜索/排序/分页）。
      const res = await fetch(`/api/factor/dashboard?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setRows(data.rows || []);
      setPortfolio(data.portfolio || null);
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
  }, [universe, period, filterUp]);

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
    if (category !== "全部") {
      list = list.filter((r) => rowCategory(r) === category);
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
  }, [rows, query, sortKey, sortDir, hideErrors, verifyFilter, category]);

  useEffect(() => {
    setPage(1);
  }, [universe, period, filterUp, category, query, hideErrors, sortKey, sortDir, verifyFilter]);

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
    title,
  }: {
    k: SortKey;
    label: string;
    align?: "left" | "right";
    /** 口径说明：分位列必须讲清哪一端是「因子值最大」 */
    title?: string;
  }) => (
    <th
      className={`cursor-pointer whitespace-nowrap px-4 py-3 ${
        align === "right" ? "text-right" : "text-left"
      }`}
      onClick={() => toggleSort(k)}
      title={title}
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
      const draft = await buildFactorPanelShareDraft({
        name: r.name_cn || r.factor_name,
        factorName: r.factor_name,
        libraryName: libKey || null,
        // 单库下面板以分类区分因子，分享稿展示分类更有信息量
        libraryLabel: rowCategory(r) || null,
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
          turnover: r.turnover,
          q1_turnover: r.q1_turnover,
          q5_turnover: r.q5_turnover,
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

  const onChangeVerify = async (
    libraryName: string,
    factorName: string,
    status: VerifyStatus,
  ) => {
    const u = getStoredUser();
    if (!u) {
      navigate(`/login?next=${encodeURIComponent("/factor/dashboard")}`);
      return;
    }
    if (u.role !== "admin") {
      window.alert("仅管理员可修改校验状态");
      return;
    }
    const verifyKey = `${libraryName}::${factorName}`;
    setVerifyBusy(verifyKey);
    try {
      const res = await fetch("/api/factor/dashboard/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          library_name: libraryName,
          factor_name: factorName,
          status,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setRows((prev) =>
        prev.map((r) =>
          r.factor_name === factorName && (r.library || "") === libraryName
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
          rows.find(
            (r) => r.factor_name === factorName && (r.library || "") === libraryName,
          )?.verify_status,
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

  /** 重算当前视图的整批 RE 回测（仅管理员；后端同样限管理员） */
  const onRefresh = async () => {
    if (!isAdmin || job.status === "running") return;
    if (
      !window.confirm(
        `将重新经 RE 回测 ${uniLabel} · ${periodLabel} · ${
          filterUp ? "过滤涨停" : "不过滤涨停"
        } 的全部因子（约 ${filtered.length || "数百"} 个）。\n` +
          `单个因子约 6–12 秒，整轮可能数十分钟；期间会持续占用 RE 回测资源。\n\n确认开始？`,
      )
    ) {
      return;
    }
    setRefreshBusy(true);
    try {
      const res = await fetch("/api/factor/dashboard/refresh", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          universe,
          period,
          filter_limit_up: filterUp,
          filter_suspended: true,
          // false = 重新计算（不跳过已算过的），否则行情更新后指标永远不变
          skip_ok: false,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || data.detail || `HTTP ${res.status}`);
      }
      if (data.ok === false) throw new Error(data.error || "刷新任务未启动");
      // 置为 running 触发既有的进度轮询 effect
      setJob(data.job || { status: "running" });
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setRefreshBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-red-50/50 via-white to-slate-50">
      <div className="mx-auto max-w-[1440px] px-3 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
        <section className="relative mb-6 overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-white to-red-50/60 p-4 shadow-sm sm:p-6 lg:p-8">
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
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 lg:text-3xl">因子面板</h1>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                批量看全因子表现（YGQuant RE 回测聚合）。单因子可调参深度检测请用
                <Link to="/factor/detect" className="mx-1 font-medium text-red-600 hover:underline">
                  检测报告
                </Link>
                。
              </p>
              <p className="mt-3 text-[11px] leading-relaxed text-slate-400 sm:text-xs">
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
              {portfolio ? (
                <p className="mt-2 rounded-lg border border-slate-200/80 bg-white/70 px-2.5 py-1.5 text-[11px] leading-relaxed text-slate-500">
                  组合口径：
                  <span className="font-medium text-slate-700">
                    {portfolio.portfolio_label || portfolio.portfolio_type}
                  </span>
                  {portfolio.rebalance_days ? ` · ${portfolio.rebalance_days} 交易日调仓` : ""}
                  {portfolio.groups ? ` · ${portfolio.groups} 组` : ""}
                  {portfolio.cost ? ` · ${portfolio.cost}` : ""}
                  {portfolio.note ? `　${portfolio.note}` : ""}
                </p>
              ) : null}
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
                onClick={() => setCategory(lab)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  category === lab ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
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
            {!filterUp && !loading && !err && rows.length === 0 && (
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
            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
              {isAdmin && (
                <button
                  type="button"
                  disabled={refreshBusy || job.status === "running"}
                  onClick={() => void onRefresh()}
                  title="重新经 RE 计算当前股票池/周期/过滤口径的全部因子指标"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${job.status === "running" || refreshBusy ? "animate-spin" : ""}`}
                  />
                  {job.status === "running"
                    ? `计算中 ${job.done ?? 0}/${job.total ?? "?"}`
                    : refreshBusy
                      ? "提交中…"
                      : "刷新指标"}
                </button>
              )}
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
              <div className="flex min-w-0 w-full items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5 sm:w-auto">
                <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索因子名称、代码…"
                  className="min-w-0 w-full bg-transparent text-sm outline-none sm:w-48"
                />
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[1500px] text-left text-sm">
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
                  <SortTh
                    k="turnover"
                    label="组合换手"
                    align="right"
                    title="整条多空主组合的平均单边换手（逐日 Σ|Δw|/2 后取均值），不是分位换手"
                  />
                  <SortTh
                    k="q1_turnover"
                    label="最高分位 Q1 换手"
                    align="right"
                    title="因子值最大那一组的换手。分组是等权诊断桶（不是可交易组合），换手全部来自排名进出，量级通常明显高于组合"
                  />
                  <SortTh
                    k="q5_turnover"
                    label="最低分位 Q5 换手"
                    align="right"
                    title="因子值最小那一组的换手，口径同 Q1 列"
                  />
                  <SortTh k="win_rate" label="胜率" align="right" />
                  <SortTh k="sharpe" label="Sharpe" align="right" />
                  <SortTh
                    k="q1_return"
                    label="最高分位 Q1"
                    align="right"
                    title="因子值最大的一组，纯做多的参考收益（RE 口径：Q1 = 最高组、Q5 = 最低组）"
                  />
                  <SortTh
                    k="q5_return"
                    label="最低分位 Q5"
                    align="right"
                    title="因子值最小的一组（RE 口径：Q1 = 最高组、Q5 = 最低组）"
                  />
                  <SortTh
                    k="long_short_spread"
                    label="多空差"
                    align="right"
                    title="最高分位 Q1 − 最低分位 Q5（做多最高组、做空最低组）"
                  />
                  <th className="sticky right-0 z-10 whitespace-nowrap bg-slate-50/95 px-3 py-3 text-center text-xs font-semibold tracking-wide text-slate-500 shadow-[-6px_0_8px_-6px_rgba(15,23,42,0.12)]">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {paged.map((r) => {
                  const win = r.win_rate ?? r.coverage_pool;
                  const lib = rowCategory(r) || "—";
                  const verifyKey = `${r.library || ""}::${r.factor_name}`;
                  const vm = verifyMeta(r.verify_status);
                  return (
                    <tr
                      key={verifyKey}
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
                            disabled={verifyBusy === verifyKey}
                            onChange={(e) =>
                              void onChangeVerify(
                                r.library || "",
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
                      <td
                        className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.ic_mean)}`}
                        title={icUnavailableHint(r.ic_unavailable_reason) ?? undefined}
                      >
                        {fmtIc(r.ic_mean)}
                        {r.ic_mean == null && r.ic_unavailable_reason ? (
                          <span
                            className="ml-1 align-super text-[10px] text-amber-500"
                            aria-label="IC 不可用"
                          >
                            *
                          </span>
                        ) : null}
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
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.turnover)}`}>
                        {fmtPct(r.turnover)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.q1_turnover)}`}>
                        {fmtPct(r.q1_turnover)}
                      </td>
                      <td className={`px-4 py-3.5 text-right font-mono text-sm ${tone(r.q5_turnover)}`}>
                        {fmtPct(r.q5_turnover)}
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
                              const tab = openDetectPlaceholderTab();
                              void openOrCreateForFactor(
                                r.factor_name,
                                r.factor_name,
                              )
                                .then((p) => navigateDetectTab(tab, p.id, p))
                                .catch((err) => {
                                  try {
                                    tab?.close();
                                  } catch {
                                    /* ignore */
                                  }
                                  window.alert(
                                    err instanceof Error ? err.message : String(err),
                                  );
                                });
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
                    <td colSpan={16} className="px-4 py-16 text-center text-sm text-slate-400">
                      {loading
                        ? "正在加载因子数据…"
                        : err
                          ? "因子数据加载失败，请稍后重试"
                          : rows.length === 0
                            ? "该口径暂无缓存数据"
                            : "没有符合条件的因子，请调整搜索或筛选条件"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {filtered.length > 0 ? (
            <>
              <div className="hidden flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 text-xs text-slate-500 lg:flex">
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
              <div className="flex items-center gap-2 border-t border-slate-100 px-3 py-2 lg:hidden">
                <span className="shrink-0 text-[11px] tabular-nums text-slate-400">
                  {filtered.length}条 · {pageSafe}/{pageCount}
                </span>
                <PagerBar
                  page={pageSafe}
                  totalPages={pageCount}
                  onJump={setPage}
                  className="min-w-0 flex-1 justify-end py-1"
                />
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
