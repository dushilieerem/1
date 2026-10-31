import { useEffect, useMemo, useState, Fragment, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  Clock,
  Layers,
  ListOrdered,
  Share2,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { AiBacktestInterpretDialog } from "@/components/AiBacktestInterpretDialog";
import { StrategyPlazaShareDialog } from "@/components/strategy/StrategyPlazaShareDialog";
import {
  CHART,
  areaGradient,
  axisCategory,
  axisValuePct,
  chartCardClass,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import { getStoredUser, prepareAuthHandoff } from "@/lib/auth";
import { buildStrategyShareDraft } from "@/lib/communityShare";
import {
  STRATEGY_BENCHMARK_OPTIONS,
  STRATEGY_UNIVERSE_OPTIONS,
  getStrategyRun,
  optionLabel,
  type StrategyRunRecord,
} from "@/lib/strategyStore";
import { getLibraryStrategyArchive } from "@/lib/userStrategyLibraries";
import type {
  YgEventFill,
  YgEventPositionSnap,
  YgRebalanceLog,
  YgRebalanceTrade,
} from "@/lib/ygApi";

type ReportTab = "equity" | "overview" | "trades" | "holdings" | "ai";

const NAV: { id: ReportTab; label: string; icon: typeof TrendingDown }[] = [
  { id: "equity", label: "累计收益与回撤", icon: TrendingDown },
  { id: "overview", label: "绩效概览", icon: BarChart3 },
  { id: "trades", label: "交易明细", icon: ListOrdered },
  { id: "holdings", label: "历史持仓", icon: Wallet },
  { id: "ai", label: "AI 解读", icon: Sparkles },
];

const TRADE_PAGE_SIZE = 50;
const HOLDINGS_PAGE_SIZE = 30;

function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}
function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(3);
}
function wgt(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}

/**
 * 净值序列 → 累计收益 %。
 * 向量化多为相对净值（≈1 起）；事件引擎常返回绝对资金（如 1e6）。
 * 若仍按 (v-1)*100，会把 100 万画成约 1 亿%。
 */
function seriesToCumPct(
  values: Array<number | null | undefined>,
): Array<number | null> {
  const first = values.find(
    (v): v is number => typeof v === "number" && Number.isFinite(v) && v !== 0,
  );
  if (first == null) return values.map(() => null);
  const absolute = Math.abs(first) > 10;
  return values.map((v) => {
    if (v == null || !Number.isFinite(v)) return null;
    return absolute ? (v / first - 1) * 100 : (v - 1) * 100;
  });
}

function sideLabel(side: string) {
  const s = side.toLowerCase();
  if (s === "buy") return "买入";
  if (s === "sell") return "卖出";
  return side || "—";
}

function tsToDate(ts?: string | null): string {
  if (!ts) return "—";
  return String(ts).slice(0, 10);
}

function money(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
  });
}

/** 事件日终快照 → 持仓行（仅保留有仓日） */
function holdingsFromEventPositions(snaps: YgEventPositionSnap[]) {
  const rows: Array<{
    date: string;
    cash: number | null;
    totalValue: number | null;
    holdings: Array<{ symbol: string; quantity: number }>;
  }> = [];
  for (const snap of snaps) {
    const pos = snap.positions || {};
    const holdings = Object.entries(pos)
      .map(([symbol, quantity]) => ({
        symbol,
        quantity: Number(quantity) || 0,
      }))
      .filter((h) => Math.abs(h.quantity) > 1e-12)
      .sort((a, b) => a.symbol.localeCompare(b.symbol, "en"));
    if (!holdings.length) continue;
    rows.push({
      date: tsToDate(snap.timestamp),
      cash: typeof snap.cash === "number" ? snap.cash : null,
      totalValue: typeof snap.total_value === "number" ? snap.total_value : null,
      holdings,
    });
  }
  return rows;
}

/** 按调仓日志累积目标权重 → 各调仓日收盘后持仓 */
function holdingsFromRebalanceLogs(logs: YgRebalanceLog[]) {
  const book = new Map<string, { weight: number; name: string }>();
  const rows: Array<{
    date: string;
    holdings: Array<{ symbol: string; name: string; weight: number }>;
  }> = [];
  for (const log of logs) {
    for (const t of log.trades || []) {
      const sym = String(t.symbol || "").trim();
      if (!sym) continue;
      const w = Number(t.target_weight);
      const nm = String(t.name || "").trim();
      if (!Number.isFinite(w) || Math.abs(w) < 1e-12) book.delete(sym);
      else {
        const prev = book.get(sym);
        book.set(sym, { weight: w, name: nm || prev?.name || "" });
      }
    }
    rows.push({
      date: log.date,
      holdings: [...book.entries()]
        .map(([symbol, { weight, name }]) => ({ symbol, name, weight }))
        .sort(
          (a, b) =>
            b.weight - a.weight || a.symbol.localeCompare(b.symbol, "en"),
        ),
    });
  }
  return rows;
}

function flattenTrades(logs: YgRebalanceLog[]) {
  const rows: Array<YgRebalanceTrade & { date: string }> = [];
  for (const log of logs) {
    for (const t of log.trades || []) {
      rows.push({ ...t, date: log.date });
    }
  }
  return rows;
}

function resolveUniverse(rec: StrategyRunRecord | null | undefined): string {
  const req = rec?.request as Record<string, unknown> | undefined;
  const meta = (rec?.result as { meta?: Record<string, unknown> } | undefined)?.meta;
  const raw =
    (typeof req?.universe === "string" && req.universe) ||
    (typeof meta?.universe === "string" && meta.universe) ||
    "";
  return raw;
}

function resolveBenchmark(rec: StrategyRunRecord | null | undefined): string {
  const req = rec?.request as Record<string, unknown> | undefined;
  const meta = (rec?.result as { meta?: Record<string, unknown> } | undefined)?.meta;
  const raw =
    (typeof req?.benchmark === "string" && req.benchmark) ||
    (typeof meta?.benchmark === "string" && meta.benchmark) ||
    "";
  return raw;
}

function zoomSlider() {
  return [
    { type: "inside" as const },
    {
      type: "slider" as const,
      height: 18,
      bottom: 8,
      borderColor: CHART.grid,
      fillerColor: "rgba(13,148,136,0.12)",
      handleStyle: { color: CHART.ink },
    },
  ];
}

function chartAnim() {
  return {
    animation: true as const,
    animationThreshold: 200000,
    animationDuration: 900,
    animationEasing: "cubicOut" as const,
  };
}

function legendTopRight(data: string[]) {
  return {
    ...legendBase({ top: 4, right: 8, left: "auto" }),
    data,
  };
}

function mddMarkLine(troughDate: string) {
  return {
    symbol: "none" as const,
    silent: true,
    data: [
      {
        xAxis: troughDate,
        lineStyle: { color: CHART.amber, type: "dashed" as const, width: 1.5 },
        label: {
          show: true,
          formatter: "MDD",
          position: "end" as const,
          rotate: 0,
          distance: 10,
          color: CHART.amber,
          fontSize: 12,
          fontWeight: 700 as const,
          backgroundColor: "rgba(255,255,255,0.92)",
          padding: [2, 6] as [number, number],
          borderRadius: 3,
        },
      },
    ],
  };
}

export function StrategyReportPage() {
  const { runId = "", archiveStrategyId = "" } = useParams();
  const navigate = useNavigate();
  const isArchiveSnap = Boolean(archiveStrategyId.trim());
  const [rec, setRec] = useState<StrategyRunRecord | null | undefined>(undefined);
  const [tab, setTab] = useState<ReportTab>("equity");
  const [tradePage, setTradePage] = useState(1);
  const [holdingsPage, setHoldingsPage] = useState(1);
  const [expandedDates, setExpandedDates] = useState<Set<string>>(() => new Set());
  const [plazaShareOpen, setPlazaShareOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRec(undefined);
    const archId = Number(archiveStrategyId);
    void (isArchiveSnap
      ? getLibraryStrategyArchive(archId)
      : getStrategyRun(runId)
    )
      .then((r) => {
        if (!cancelled) setRec(r);
      })
      .catch(() => {
        if (!cancelled) setRec(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, archiveStrategyId, isArchiveSnap]);

  const result = rec?.result;
  const m = result?.metrics;
  const req = rec?.request;
  const isEventRun = useMemo(() => {
    if (req?.engine_mode === "event") return true;
    const r = result as Record<string, unknown> | undefined;
    if (!r) return false;
    return (
      Array.isArray(r.fills) ||
      Array.isArray(r.orders) ||
      Array.isArray(r.event_positions)
    );
  }, [req, result]);

  const rebalanceLogs = useMemo(
    () => (result?.rebalance_logs || []) as YgRebalanceLog[],
    [result],
  );
  const eventFills = useMemo(
    () => (Array.isArray(result?.fills) ? result!.fills! : []) as YgEventFill[],
    [result],
  );
  const flatTrades = useMemo(
    () => flattenTrades(rebalanceLogs),
    [rebalanceLogs],
  );
  const holdingRows = useMemo(
    () => holdingsFromRebalanceLogs(rebalanceLogs),
    [rebalanceLogs],
  );
  const eventHoldingRows = useMemo(
    () =>
      holdingsFromEventPositions(
        (Array.isArray(result?.event_positions)
          ? result!.event_positions!
          : []) as YgEventPositionSnap[],
      ),
    [result],
  );
  const rebSummary = useMemo(() => {
    let buys = 0;
    let sells = 0;
    for (const t of flatTrades) {
      const s = String(t.side || "").toLowerCase();
      if (s === "buy") buys += 1;
      else if (s === "sell") sells += 1;
    }
    return {
      days: rebalanceLogs.length,
      tradeRows: flatTrades.length,
      buys,
      sells,
    };
  }, [flatTrades, rebalanceLogs.length]);

  const fillSummary = useMemo(() => {
    let buys = 0;
    let sells = 0;
    const days = new Set<string>();
    for (const f of eventFills) {
      const s = String(f.side || "").toLowerCase();
      if (s === "buy") buys += 1;
      else if (s === "sell") sells += 1;
      days.add(tsToDate(f.timestamp));
    }
    days.delete("—");
    return {
      days: days.size,
      tradeRows: eventFills.length,
      buys,
      sells,
    };
  }, [eventFills]);

  useEffect(() => {
    setTradePage(1);
    setHoldingsPage(1);
    setExpandedDates(new Set());
  }, [runId]);

  const tradeSourceLen = isEventRun ? eventFills.length : flatTrades.length;
  const tradePageCount = Math.max(
    1,
    Math.ceil(tradeSourceLen / TRADE_PAGE_SIZE) || 1,
  );
  const tradeSlice = useMemo(() => {
    const page = Math.min(Math.max(1, tradePage), tradePageCount);
    const start = (page - 1) * TRADE_PAGE_SIZE;
    return flatTrades.slice(start, start + TRADE_PAGE_SIZE);
  }, [flatTrades, tradePage, tradePageCount]);
  const fillSlice = useMemo(() => {
    const page = Math.min(Math.max(1, tradePage), tradePageCount);
    const start = (page - 1) * TRADE_PAGE_SIZE;
    return eventFills.slice(start, start + TRADE_PAGE_SIZE);
  }, [eventFills, tradePage, tradePageCount]);

  const holdingsSourceLen = isEventRun
    ? eventHoldingRows.length
    : holdingRows.length;
  const holdingsPageCount = Math.max(
    1,
    Math.ceil(holdingsSourceLen / HOLDINGS_PAGE_SIZE) || 1,
  );
  const holdingsSlice = useMemo(() => {
    const page = Math.min(Math.max(1, holdingsPage), holdingsPageCount);
    const start = (page - 1) * HOLDINGS_PAGE_SIZE;
    return holdingRows.slice(start, start + HOLDINGS_PAGE_SIZE);
  }, [holdingRows, holdingsPage, holdingsPageCount]);
  const eventHoldingsSlice = useMemo(() => {
    const page = Math.min(Math.max(1, holdingsPage), holdingsPageCount);
    const start = (page - 1) * HOLDINGS_PAGE_SIZE;
    return eventHoldingRows.slice(start, start + HOLDINGS_PAGE_SIZE);
  }, [eventHoldingRows, holdingsPage, holdingsPageCount]);

  const toggleExpand = (date: string) => {
    setExpandedDates((prev) => {
      const next = new Set(prev);
      if (next.has(date)) next.delete(date);
      else next.add(date);
      return next;
    });
  };

  const expandAllHoldings = () => {
    const rows = isEventRun ? eventHoldingsSlice : holdingsSlice;
    setExpandedDates(new Set(rows.map((r) => r.date)));
  };
  const collapseAllHoldings = () => {
    setExpandedDates(new Set());
  };

  const emptyRebHint = (() => {
    const flags = result as Record<string, unknown> | undefined;
    if (flags?._rebalance_logs_dropped) {
      return `该次回测曾返回 ${flags._rebalance_logs_total ?? "若干"} 条调仓日志，但旧版入库时被裁掉。请勾选「返回调仓日志」后重新回测（现已改存完整明细）。`;
    }
    if (isEventRun) {
      if (eventFills.length === 0 && eventHoldingRows.length === 0) {
        return "事件回测无成交 / 持仓快照（可能整段空仓，或旧记录未保存事件明细）。";
      }
      return "暂无数据";
    }
    if (req?.include_rebalance_logs) {
      return "本次回测未返回调仓记录（可能无权重变化）";
    }
    return "本次回测未请求调仓日志。请在参数设置勾选「返回调仓日志」后重新回测。";
  })();

  const curveDates = useMemo(
    () => result?.equity_curve?.map((p) => p.date) || [],
    [result],
  );
  const stratPct = useMemo(
    () => seriesToCumPct((result?.equity_curve || []).map((p) => p.value)),
    [result],
  );
  const benchPct = useMemo(() => {
    const c = result?.equity_curve;
    if (!c?.length) return [] as (number | null)[];
    const benchMap = new Map(
      (result?.benchmark_curve || []).map((p) => [p.date, p.value]),
    );
    return seriesToCumPct(c.map((p) => benchMap.get(p.date)));
  }, [result]);
  const hasBench = benchPct.some((v) => v != null);
  const ddPct = useMemo(
    () => (result?.equity_curve || []).map((p) => (p.drawdown ?? 0) * 100),
    [result],
  );

  const mddMeta = useMemo(() => {
    const curve = result?.equity_curve || [];
    const fromMetric = result?.metrics?.max_drawdown;
    const mddPct =
      typeof fromMetric === "number" && !Number.isNaN(fromMetric)
        ? fromMetric * 100
        : ddPct.length
          ? Math.min(...ddPct)
          : 0;
    let troughDate: string | null = null;
    if (curve.length) {
      let best = 0;
      let idx = -1;
      curve.forEach((p, i) => {
        const d = p.drawdown ?? 0;
        if (d < best) {
          best = d;
          idx = i;
        }
      });
      if (idx >= 0) troughDate = curve[idx].date;
    }
    if (!troughDate) {
      const dds = result?.drawdowns || [];
      const worst = [...dds].sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0))[0];
      troughDate = worst?.end || null;
    }
    return { mddPct, troughDate };
  }, [result, ddPct]);

  const equityOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      ...chartAnim(),
      color: [CHART.ink, CHART.bench],
      tooltip: {
        ...darkTooltip(),
        formatter: (
          params: Array<{
            seriesName: string;
            value: number | null;
            axisValue: string;
            marker: string;
          }>,
        ) => {
          const head = params[0]?.axisValue ?? "";
          const rows = params
            .filter((p) => p.value != null && !Number.isNaN(Number(p.value)))
            .map((p) => `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}%`)
            .join("<br/>");
          return `<b>${head}</b><br/>${rows}`;
        },
      },
      legend: legendTopRight(hasBench ? ["策略", "基准"] : ["策略"]),
      grid: { left: 52, right: 20, top: 48, bottom: 52 },
      dataZoom: zoomSlider(),
      xAxis: axisCategory({
        data: curveDates,
        boundaryGap: false,
        axisLabel: { color: CHART.axis, fontSize: 11, hideOverlap: true },
      }),
      yAxis: { ...axisValuePct(), scale: true },
      series: [
        {
          name: "策略",
          type: "line",
          smooth: 0.25,
          showSymbol: false,
          data: stratPct,
          lineStyle: { width: 2.2, color: CHART.ink },
          areaStyle: { color: areaGradient(CHART.ink, 0.14) },
          itemStyle: { color: CHART.ink },
          markLine: mddMeta.troughDate ? mddMarkLine(mddMeta.troughDate) : undefined,
        },
        ...(hasBench
          ? [
              {
                name: "基准",
                type: "line" as const,
                smooth: 0.25,
                showSymbol: false,
                data: benchPct,
                lineStyle: { width: 2, color: CHART.bench },
                itemStyle: { color: CHART.bench },
              },
            ]
          : []),
      ],
    };
  }, [curveDates, stratPct, benchPct, hasBench, mddMeta.troughDate]);

  const drawdownOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      ...chartAnim(),
      color: [CHART.amber],
      tooltip: {
        ...darkTooltip(),
        formatter: (
          params: Array<{ value: number; axisValue: string; marker: string }>,
        ) => {
          const p = params[0];
          if (!p) return "";
          return `<b>${p.axisValue}</b><br/>${p.marker} 回撤: ${Number(p.value).toFixed(2)}%`;
        },
      },
      legend: legendTopRight(["回撤"]),
      grid: { left: 52, right: 28, top: 48, bottom: 52 },
      dataZoom: zoomSlider(),
      xAxis: axisCategory({
        data: curveDates,
        boundaryGap: false,
        axisLabel: { color: CHART.axis, fontSize: 11, hideOverlap: true },
      }),
      yAxis: {
        ...axisValuePct(),
        max: 0,
        scale: true,
      },
      series: [
        {
          name: "回撤",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: ddPct,
          lineStyle: { width: 1.2, color: CHART.amber },
          areaStyle: { color: areaGradient(CHART.amber, 0.4) },
          itemStyle: { color: CHART.amber },
          markLine: {
            symbol: "none",
            silent: true,
            data: [
              {
                yAxis: mddMeta.mddPct,
                lineStyle: { color: "#e11d48", type: "solid", width: 1.8 },
                label: { show: false },
              },
              ...(mddMeta.troughDate ? mddMarkLine(mddMeta.troughDate).data : []),
            ],
          },
        },
      ],
    };
  }, [curveDates, ddPct, mddMeta]);

  const annualOpt = useMemo(() => {
    const rows = result?.annual_returns;
    if (!rows?.length) return null;
    const vals = rows.map((r) => (r.return_value ?? 0) * 100);
    return {
      ...chartAnim(),
      tooltip: {
        ...darkTooltip(),
        trigger: "item",
        formatter: (p: {
          dataIndex: number;
          value: number | { value: number };
          marker: string;
        }) => {
          const row = rows[p.dataIndex];
          if (!row) return "";
          const raw = typeof p.value === "number" ? p.value : p.value?.value;
          return `<b>${row.year}</b><br/>${p.marker} 年化收益: ${Number(raw).toFixed(2)}%`;
        },
      },
      grid: { left: 16, right: 16, top: 28, bottom: 28, containLabel: true },
      xAxis: {
        type: "category",
        data: rows.map((r) => String(r.year)),
        axisLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.axis, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: "{value}%", color: CHART.axis, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART.grid, type: "dashed" } },
        axisLine: { show: false },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 36,
          data: vals.map((v) => ({
            value: v,
            itemStyle: {
              color: v >= 0 ? "#ef4444" : "#16a34a",
              borderRadius: v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
            },
          })),
        },
      ],
    };
  }, [result]);

  if (rec === undefined) {
    return (
      <div className="mx-auto max-w-lg px-6 py-20 text-center text-slate-400">
        加载中…
      </div>
    );
  }

  if (!rec) {
    return (
      <div className="mx-auto max-w-lg px-6 py-20 text-center">
        <p className="text-slate-600">
          {isArchiveSnap
            ? "没有找到入库报告（可能是旧数据仅保存了代码）。"
            : "没有找到回测结果。"}
        </p>
        <Link
          to={isArchiveSnap ? "/strategy/library" : "/strategy/research"}
          className="mt-4 inline-block text-sm font-medium text-blue-600 underline"
        >
          {isArchiveSnap ? "返回策略库" : "返回策略研究"}
        </Link>
      </div>
    );
  }

  const dds = result?.drawdowns || [];
  const rangeLabel =
    req?.start && req?.end
      ? `${req.start} ~ ${req.end}`
      : result?.date_range?.start && result?.date_range?.end
        ? `${result.date_range.start} ~ ${result.date_range.end}`
        : "—";
  const uniCode = resolveUniverse(rec);
  const bmCode = resolveBenchmark(rec);

  const shareToCommunity = () => {
    const next = `/community/new?section=strategy`;
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    void (async () => {
      const draft = await buildStrategyShareDraft({
        name: rec.name || rec.description || "策略回测",
        rangeLabel,
        universeLabel: optionLabel(uniCode, STRATEGY_UNIVERSE_OPTIONS),
        benchmarkLabel: optionLabel(bmCode, STRATEGY_BENCHMARK_OPTIONS),
        metrics: m,
        excessReturn: result?.excess_return,
        // 内置策略源码是历史快照，但过渡期不在用户分享/展示链路中暴露。
        strategyCode: req?.strategy_id ? undefined : req?.strategy_code,
        runId: rec.id || runId,
        returnTo: `/strategy/research/report/${rec.id || runId}`,
        returnLabel: "返回策略回测报告",
      });
      navigate(next, { state: draft });
    })();
  };

  const shareToPlaza = () => {
    if (!getStoredUser()) {
      prepareAuthHandoff();
      navigate(
        `/login?next=${encodeURIComponent(`/strategy/research/report/${runId}`)}`,
      );
      return;
    }
    setPlazaShareOpen(true);
  };

  const highlightMetrics: Array<{
    key: string;
    label: string;
    value: string;
    valueClass: string;
  }> = [
    {
      key: "annual",
      label: "年化",
      value: m?.annual_return != null ? pct(m.annual_return) : "—",
      valueClass: "text-sky-700",
    },
    {
      key: "mdd",
      label: "最大回撤",
      value: m?.max_drawdown != null ? pct(m.max_drawdown) : "—",
      valueClass: "text-rose-700",
    },
    {
      key: "sharpe",
      label: "Sharpe",
      value: m?.sharpe != null ? num(m.sharpe) : "—",
      valueClass: "text-violet-700",
    },
  ];

  const candidates: Array<[string, string | null]> = [
    [
      "波动",
      m?.volatility != null || m?.annual_vol != null
        ? pct(m?.volatility ?? m?.annual_vol)
        : null,
    ],
    ["Calmar", m?.calmar != null ? num(m.calmar) : null],
    ["胜率", m?.win_rate != null ? pct(m.win_rate) : null],
    [
      "累计收益",
      m?.total_return != null || m?.cumulative_return != null
        ? pct(m?.total_return ?? m?.cumulative_return)
        : null,
    ],
    [
      "换手",
      m?.turnover != null || m?.avg_turnover != null
        ? num(m?.turnover ?? m?.avg_turnover)
        : null,
    ],
    ["超额", result?.excess_return != null ? pct(result.excess_return) : null],
  ];
  const metricCards: Array<[string, string]> = candidates.filter(
    (c): c is [string, string] => c[1] != null,
  );
  const shownCards: Array<[string, string]> =
    metricCards.length > 0
      ? metricCards
      : [
          ["累计收益", "—"],
          ["波动", "—"],
          ["胜率", "—"],
          ["超额", "—"],
        ];

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-slate-50 to-white">
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-3 px-3 py-3 sm:px-6 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs text-slate-500 sm:text-sm">
              {isArchiveSnap || rec.immutable ? (
                <>
                  <Link to="/strategy/library" className="hover:text-blue-600">
                    策略库
                  </Link>
                  {rec.libraryName ? (
                    <>
                      {" / "}
                      <span>{rec.libraryName}</span>
                    </>
                  ) : null}
                  {" / 入库报告"}
                </>
              ) : (
                <>
                  <Link to="/strategy/research" className="hover:text-blue-600">
                    策略研究
                  </Link>
                  {" / "}
                  <Link
                    to={`/strategy/research/${rec.projectId}`}
                    className="hover:text-blue-600"
                  >
                    {rec.name || rec.description}
                  </Link>
                  {" / 回测报告"}
                </>
              )}
            </p>
            <h1 className="mt-0.5 text-base font-bold text-slate-900 sm:text-lg">
              {rec.name || rec.description}
              {isArchiveSnap || rec.immutable ? (
                <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-600">
                  入库快照 · 只读
                </span>
              ) : null}
            </h1>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {isArchiveSnap || rec.immutable ? (
              <Link
                to="/strategy/library"
                className="col-span-2 inline-flex items-center justify-center rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 sm:col-span-1"
              >
                返回策略库
              </Link>
            ) : (
              <>
                <button
                  type="button"
                  onClick={shareToPlaza}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-cyan-300 bg-cyan-50 px-3 py-1.5 text-sm font-medium text-cyan-950 hover:bg-cyan-100"
                >
                  <Share2 className="h-3.5 w-3.5" />
                  <span className="sm:hidden">广场</span>
                  <span className="hidden sm:inline">分享到策略广场</span>
                </button>
                <button
                  type="button"
                  onClick={shareToCommunity}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
                >
                  <Share2 className="h-3.5 w-3.5" />
                  <span className="sm:hidden">社区</span>
                  <span className="hidden sm:inline">分享到社区</span>
                </button>
                <Link
                  to={`/strategy/research/${rec.projectId}/history`}
                  className="inline-flex items-center justify-center rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
                >
                  <span className="sm:hidden">历史</span>
                  <span className="hidden sm:inline">历史记录</span>
                </Link>
                <Link
                  to={`/strategy/research/${rec.projectId}?runId=${encodeURIComponent(rec.id)}`}
                  className="inline-flex items-center justify-center rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
                >
                  返回配置
                </Link>
              </>
            )}
          </div>
        </div>

        <div className="mx-auto w-full max-w-[1400px] space-y-2 px-3 pb-4 sm:px-6">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <ReportStatCard
              label="区间"
              value={rangeLabel}
              icon={<Clock className="h-3.5 w-3.5 text-blue-500" />}
            />
            <ReportStatCard
              label="股票池"
              value={optionLabel(uniCode, STRATEGY_UNIVERSE_OPTIONS)}
              icon={<Layers className="h-3.5 w-3.5 text-amber-500" />}
            />
            <ReportStatCard
              label="基准"
              value={optionLabel(bmCode, STRATEGY_BENCHMARK_OPTIONS)}
              icon={<TrendingUp className="h-3.5 w-3.5 text-teal-500" />}
            />
            <ReportStatCard
              label="运行耗时"
              value={`${rec.elapsedSec}s`}
              icon={<BarChart3 className="h-3.5 w-3.5 text-slate-500" />}
            />
            <ReportStatCard
              label="起始资金"
              value={
                req?.initial_capital != null
                  ? req.initial_capital.toLocaleString("zh-CN")
                  : "—"
              }
              icon={<TrendingDown className="h-3.5 w-3.5 text-rose-500" />}
            />
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {highlightMetrics.map((item) => (
              <ReportStatCard
                key={item.key}
                label={item.label}
                value={item.value}
                valueClassName={item.valueClass}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] px-3 py-4 sm:px-6 sm:py-5">
        <nav className="sticky top-0 z-10 mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 bg-white/95 pb-2 backdrop-blur [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden lg:hidden">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs ${
                tab === item.id ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex gap-6">
          <aside className="hidden w-44 shrink-0 lg:block">
            <nav className="sticky top-20 space-y-0.5">
              {NAV.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
                    tab === item.id
                      ? "bg-blue-50 font-medium text-blue-700 ring-1 ring-blue-100"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </button>
              ))}
            </nav>
          </aside>

          <main className="min-w-0 flex-1">
            {tab === "equity" && (
              <div className="space-y-5">
                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">
                    累计收益
                  </h2>
                  {equityOpt ? (
                    <ReactECharts
                      option={equityOpt}
                      style={{ height: 320 }}
                      notMerge
                      opts={{ renderer: "canvas" }}
                    />
                  ) : (
                    <p className="py-16 text-center text-sm text-slate-400">
                      暂无净值数据
                    </p>
                  )}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">
                    动态回撤
                  </h2>
                  {drawdownOpt ? (
                    <ReactECharts
                      option={drawdownOpt}
                      style={{ height: 240 }}
                      notMerge
                      opts={{ renderer: "canvas" }}
                    />
                  ) : (
                    <p className="py-12 text-center text-sm text-slate-400">
                      暂无回撤数据
                    </p>
                  )}
                </section>
              </div>
            )}

            {tab === "overview" && (
              <div className="space-y-5">
                <section
                  className="grid gap-2"
                  style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}
                >
                  {shownCards.map(([k, v]) => (
                    <ReportStatCard key={k} label={k} value={v} />
                  ))}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-sm font-semibold text-slate-800">
                    分年收益
                  </h2>
                  {annualOpt ? (
                    <ReactECharts
                      option={annualOpt}
                      style={{ height: 280 }}
                      notMerge
                      opts={{ renderer: "canvas" }}
                    />
                  ) : (
                    <p className="py-16 text-center text-sm text-slate-400">
                      暂无分年收益
                    </p>
                  )}
                </section>

                {dds.length > 0 && (
                  <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                    <div className="border-b border-slate-100 px-4 py-3">
                      <h2 className="text-sm font-semibold text-slate-800">
                        回撤区间
                      </h2>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-slate-50 text-xs text-slate-500">
                          <tr>
                            <th className="px-4 py-2">开始</th>
                            <th className="px-4 py-2">谷底</th>
                            <th className="px-4 py-2">深度</th>
                            <th className="px-4 py-2">天数</th>
                            <th className="px-4 py-2">回到前高</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dds.map((d, i) => (
                            <tr key={i} className="border-t border-slate-100">
                              <td className="px-4 py-2 font-mono text-xs">
                                {d.start}
                              </td>
                              <td className="px-4 py-2 font-mono text-xs">
                                {d.end}
                              </td>
                              <td className="px-4 py-2 tabular-nums text-red-600">
                                {pct(d.depth)}
                              </td>
                              <td className="px-4 py-2 tabular-nums">
                                {d.days ?? "—"}
                              </td>
                              <td className="px-4 py-2 font-mono text-xs">
                                {d.recovery ?? "尚未修复"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
              </div>
            )}

            {tab === "trades" && (
              <div className="space-y-4">
                {isEventRun ? (
                  eventFills.length === 0 ? (
                    <section className={chartCardClass()}>
                      <p className="py-16 text-center text-sm text-slate-400">
                        {emptyRebHint}
                      </p>
                    </section>
                  ) : (
                    <>
                      <section className="grid gap-3 sm:grid-cols-4">
                        {(
                          [
                            ["成交日", String(fillSummary.days)],
                            ["成交笔数", String(fillSummary.tradeRows)],
                            ["买入", String(fillSummary.buys)],
                            ["卖出", String(fillSummary.sells)],
                          ] as const
                        ).map(([k, v]) => (
                          <div
                            key={k}
                            className="rounded-xl border border-slate-200/90 bg-white p-3 shadow-sm"
                          >
                            <p className="text-xs text-slate-500">{k}</p>
                            <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                              {v}
                            </p>
                          </div>
                        ))}
                      </section>
                      <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 text-xs text-slate-500">
                              <tr>
                                <th className="px-4 py-2.5 font-medium">日期</th>
                                <th className="px-4 py-2.5 font-medium">标的</th>
                                <th className="px-4 py-2.5 font-medium">方向</th>
                                <th className="px-4 py-2.5 text-right font-medium">
                                  数量
                                </th>
                                <th className="px-4 py-2.5 text-right font-medium">
                                  价格
                                </th>
                                <th className="px-4 py-2.5 text-right font-medium">
                                  佣金
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {fillSlice.map((f, i) => {
                                const side = String(f.side || "").toLowerCase();
                                const buy = side === "buy";
                                const sell = side === "sell";
                                return (
                                  <tr
                                    key={`${f.order_id || i}-${f.symbol}-${i}`}
                                    className="border-t border-slate-100 hover:bg-slate-50/80"
                                  >
                                    <td className="px-4 py-2.5 font-mono text-xs text-slate-600">
                                      {tsToDate(f.timestamp)}
                                    </td>
                                    <td className="px-4 py-2.5 font-mono text-xs text-slate-800">
                                      {f.symbol || "—"}
                                    </td>
                                    <td
                                      className={`px-4 py-2.5 text-sm font-medium ${
                                        buy
                                          ? "text-red-600"
                                          : sell
                                            ? "text-emerald-600"
                                            : "text-slate-600"
                                      }`}
                                    >
                                      {sideLabel(String(f.side || ""))}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-700">
                                      {f.quantity ?? "—"}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-700">
                                      {f.price != null
                                        ? Number(f.price).toFixed(2)
                                        : "—"}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-500">
                                      {money(f.commission)}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        {tradePageCount > 1 && (
                          <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-4 py-2.5 text-xs text-slate-500">
                            <span>
                              第 {Math.min(tradePage, tradePageCount)} /{" "}
                              {tradePageCount} 页 · 共 {eventFills.length} 笔
                            </span>
                            <button
                              type="button"
                              disabled={tradePage <= 1}
                              onClick={() =>
                                setTradePage((p) => Math.max(1, p - 1))
                              }
                              className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                            >
                              上一页
                            </button>
                            <button
                              type="button"
                              disabled={tradePage >= tradePageCount}
                              onClick={() =>
                                setTradePage((p) =>
                                  Math.min(tradePageCount, p + 1),
                                )
                              }
                              className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                            >
                              下一页
                            </button>
                          </div>
                        )}
                      </section>
                    </>
                  )
                ) : flatTrades.length === 0 ? (
                  <section className={chartCardClass()}>
                    <p className="py-16 text-center text-sm text-slate-400">
                      {emptyRebHint}
                    </p>
                  </section>
                ) : (
                  <>
                    <section className="grid gap-3 sm:grid-cols-4">
                      {(
                        [
                          ["调仓日", String(rebSummary.days)],
                          ["变动笔数", String(rebSummary.tradeRows)],
                          ["买入", String(rebSummary.buys)],
                          ["卖出", String(rebSummary.sells)],
                        ] as const
                      ).map(([k, v]) => (
                        <div
                          key={k}
                          className="rounded-xl border border-slate-200/90 bg-white p-3 shadow-sm"
                        >
                          <p className="text-xs text-slate-500">{k}</p>
                          <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                            {v}
                          </p>
                        </div>
                      ))}
                    </section>

                    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                          <thead className="bg-slate-50 text-xs text-slate-500">
                            <tr>
                              <th className="px-4 py-2.5 font-medium">日期</th>
                              <th className="px-4 py-2.5 font-medium">标的</th>
                              <th className="px-4 py-2.5 font-medium">买卖操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tradeSlice.map((t, i) => {
                              const side = String(t.side || "").toLowerCase();
                              const buy = side === "buy";
                              const sell = side === "sell";
                              return (
                                <tr
                                  key={`${t.date}-${t.symbol}-${i}`}
                                  className="border-t border-slate-100 hover:bg-slate-50/80"
                                >
                                  <td className="px-4 py-2.5 font-mono text-xs text-slate-600">
                                    {t.date}
                                  </td>
                                  <td className="px-4 py-2.5 text-xs text-slate-800">
                                    <span className="font-mono">
                                      {t.symbol || "—"}
                                    </span>
                                    {t.name ? (
                                      <span className="ml-1.5 text-slate-500">
                                        {t.name}
                                      </span>
                                    ) : null}
                                  </td>
                                  <td
                                    className={`px-4 py-2.5 text-sm font-medium ${
                                      buy
                                        ? "text-red-600"
                                        : sell
                                          ? "text-emerald-600"
                                          : "text-slate-600"
                                    }`}
                                  >
                                    {sideLabel(t.side)}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      {tradePageCount > 1 && (
                        <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-4 py-2.5 text-xs text-slate-500">
                          <span>
                            第 {Math.min(tradePage, tradePageCount)} /{" "}
                            {tradePageCount} 页 · 共 {flatTrades.length} 笔
                          </span>
                          <button
                            type="button"
                            disabled={tradePage <= 1}
                            onClick={() =>
                              setTradePage((p) => Math.max(1, p - 1))
                            }
                            className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                          >
                            上一页
                          </button>
                          <button
                            type="button"
                            disabled={tradePage >= tradePageCount}
                            onClick={() =>
                              setTradePage((p) =>
                                Math.min(tradePageCount, p + 1),
                              )
                            }
                            className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                          >
                            下一页
                          </button>
                        </div>
                      )}
                    </section>
                  </>
                )}
              </div>
            )}

            {tab === "holdings" && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div />
                  {(isEventRun
                    ? eventHoldingRows.length > 0
                    : holdingRows.length > 0) && (
                    <div className="flex gap-2 text-xs">
                      <button
                        type="button"
                        onClick={expandAllHoldings}
                        className="rounded border border-slate-200 px-2 py-1 text-slate-600 hover:bg-slate-50"
                      >
                        全部展开
                      </button>
                      <button
                        type="button"
                        onClick={collapseAllHoldings}
                        className="rounded border border-slate-200 px-2 py-1 text-slate-600 hover:bg-slate-50"
                      >
                        全部收起
                      </button>
                    </div>
                  )}
                </div>

                {isEventRun ? (
                  eventHoldingRows.length === 0 ? (
                    <section className={chartCardClass()}>
                      <p className="py-16 text-center text-sm text-slate-400">
                        {emptyRebHint}
                      </p>
                    </section>
                  ) : (
                    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-slate-50 text-xs text-slate-500">
                          <tr>
                            <th className="w-10 px-3 py-2.5" />
                            <th className="px-3 py-2.5 font-medium">日期</th>
                            <th className="px-3 py-2.5 font-medium">持仓</th>
                            <th className="px-3 py-2.5 text-right font-medium">
                              总权益
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {eventHoldingsSlice.map((row) => {
                            const open = expandedDates.has(row.date);
                            const n = row.holdings.length;
                            return (
                              <Fragment key={row.date}>
                                <tr
                                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50/80"
                                  onClick={() => toggleExpand(row.date)}
                                >
                                  <td className="px-3 py-2.5 text-blue-600">
                                    {open ? (
                                      <ChevronDown className="h-4 w-4" />
                                    ) : (
                                      <ChevronRight className="h-4 w-4" />
                                    )}
                                  </td>
                                  <td className="px-3 py-2.5 font-mono text-xs text-slate-700">
                                    {row.date}
                                  </td>
                                  <td className="px-3 py-2.5 text-slate-600">
                                    持有 {n} 只 · 现金 {money(row.cash)}
                                  </td>
                                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-700">
                                    {money(row.totalValue)}
                                  </td>
                                </tr>
                                {open &&
                                  row.holdings.map((h) => (
                                    <tr
                                      key={`${row.date}-${h.symbol}`}
                                      className="border-t border-slate-50 bg-slate-50/40"
                                    >
                                      <td />
                                      <td className="px-3 py-1.5 font-mono text-[11px] text-slate-400">
                                        {row.date}
                                      </td>
                                      <td className="px-3 py-1.5 font-mono text-xs text-slate-800">
                                        {h.symbol}
                                      </td>
                                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-700">
                                        {h.quantity} 股
                                      </td>
                                    </tr>
                                  ))}
                              </Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                      {holdingsPageCount > 1 && (
                        <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-4 py-2.5 text-xs text-slate-500">
                          <span>
                            第 {Math.min(holdingsPage, holdingsPageCount)} /{" "}
                            {holdingsPageCount} 页 · 共{" "}
                            {eventHoldingRows.length} 日
                          </span>
                          <button
                            type="button"
                            disabled={holdingsPage <= 1}
                            onClick={() => {
                              setHoldingsPage((p) => Math.max(1, p - 1));
                              setExpandedDates(new Set());
                            }}
                            className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                          >
                            上一页
                          </button>
                          <button
                            type="button"
                            disabled={holdingsPage >= holdingsPageCount}
                            onClick={() => {
                              setHoldingsPage((p) =>
                                Math.min(holdingsPageCount, p + 1),
                              );
                              setExpandedDates(new Set());
                            }}
                            className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                          >
                            下一页
                          </button>
                        </div>
                      )}
                    </section>
                  )
                ) : holdingRows.length === 0 ? (
                  <section className={chartCardClass()}>
                    <p className="py-16 text-center text-sm text-slate-400">
                      {emptyRebHint}
                    </p>
                  </section>
                ) : (
                  <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-slate-50 text-xs text-slate-500">
                        <tr>
                          <th className="w-10 px-3 py-2.5" />
                          <th className="px-3 py-2.5 font-medium">日期</th>
                          <th className="px-3 py-2.5 font-medium">持仓表</th>
                          <th className="px-3 py-2.5 text-right font-medium">权重</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holdingsSlice.map((row) => {
                          const open = expandedDates.has(row.date);
                          const n = row.holdings.length;
                          return (
                            <Fragment key={row.date}>
                              <tr
                                className="cursor-pointer border-t border-slate-100 hover:bg-slate-50/80"
                                onClick={() => toggleExpand(row.date)}
                              >
                                <td className="px-3 py-2.5 text-blue-600">
                                  {open ? (
                                    <ChevronDown className="h-4 w-4" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4" />
                                  )}
                                </td>
                                <td className="px-3 py-2.5 font-mono text-xs text-slate-700">
                                  {row.date}
                                </td>
                                <td className="px-3 py-2.5 text-slate-600">
                                  持有 {n} 只证券
                                </td>
                                <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">
                                  —
                                </td>
                              </tr>
                              {open &&
                                (n === 0 ? (
                                  <tr className="border-t border-slate-50 bg-slate-50/40">
                                    <td />
                                    <td
                                      colSpan={3}
                                      className="px-3 py-3 text-xs text-slate-400"
                                    >
                                      该日无持仓
                                    </td>
                                  </tr>
                                ) : (
                                  row.holdings.map((h) => (
                                    <tr
                                      key={`${row.date}-${h.symbol}`}
                                      className="border-t border-slate-50 bg-slate-50/40"
                                    >
                                      <td />
                                      <td className="px-3 py-1.5 font-mono text-[11px] text-slate-400">
                                        {row.date}
                                      </td>
                                      <td className="px-3 py-1.5 text-xs text-slate-800">
                                        <span className="font-mono">{h.symbol}</span>
                                        {h.name ? (
                                          <span className="ml-1.5 text-slate-500">
                                            {h.name}
                                          </span>
                                        ) : null}
                                      </td>
                                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-700">
                                        {wgt(h.weight)}
                                      </td>
                                    </tr>
                                  ))
                                ))}
                            </Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                    {holdingsPageCount > 1 && (
                      <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-4 py-2.5 text-xs text-slate-500">
                        <span>
                          第 {Math.min(holdingsPage, holdingsPageCount)} /{" "}
                          {holdingsPageCount} 页 · 共 {holdingRows.length} 个调仓日
                        </span>
                        <button
                          type="button"
                          disabled={holdingsPage <= 1}
                          onClick={() => {
                            setHoldingsPage((p) => Math.max(1, p - 1));
                            setExpandedDates(new Set());
                          }}
                          className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                        >
                          上一页
                        </button>
                        <button
                          type="button"
                          disabled={holdingsPage >= holdingsPageCount}
                          onClick={() => {
                            setHoldingsPage((p) =>
                              Math.min(holdingsPageCount, p + 1),
                            );
                            setExpandedDates(new Set());
                          }}
                          className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                        >
                          下一页
                        </button>
                      </div>
                    )}
                  </section>
                )}
              </div>
            )}

            {tab === "ai" ? (
              <AiBacktestInterpretDialog
                variant="panel"
                backtestType="strategy"
                result={
                  result && typeof result === "object"
                    ? (result as unknown as Record<string, unknown>)
                    : null
                }
                runContext={{
                  validation_scheme: "in_sample",
                  commission_rate:
                    req &&
                    typeof (req as { commission_rate?: number }).commission_rate ===
                      "number"
                      ? (req as { commission_rate: number }).commission_rate
                      : undefined,
                  stamp_tax:
                    req && typeof (req as { stamp_tax?: number }).stamp_tax === "number"
                      ? (req as { stamp_tax: number }).stamp_tax
                      : undefined,
                  slippage_rate:
                    req &&
                    typeof (req as { slippage_rate?: number }).slippage_rate ===
                      "number"
                      ? (req as { slippage_rate: number }).slippage_rate
                      : undefined,
                }}
              />
            ) : null}
          </main>
        </div>
      </div>

      <StrategyPlazaShareDialog
        open={plazaShareOpen}
        onClose={() => setPlazaShareOpen(false)}
        runId={String(rec.id || runId)}
        defaultTitle={(rec.name || rec.description || "策略分享").slice(0, 120)}
        rangeLabel={rangeLabel}
        universeLabel={optionLabel(uniCode, STRATEGY_UNIVERSE_OPTIONS)}
        benchmarkLabel={optionLabel(bmCode, STRATEGY_BENCHMARK_OPTIONS)}
        request={req}
        result={result}
      />
    </div>
  );
}

function ReportStatCard({
  label,
  value,
  icon,
  valueClassName = "text-slate-900",
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  valueClassName?: string;
}) {
  return (
    <div className="flex min-h-[58px] min-w-0 w-full items-center gap-2 rounded-lg border border-slate-200/90 bg-white px-3 py-2 shadow-sm">
      {icon ? <span className="shrink-0">{icon}</span> : null}
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-slate-500">{label}</p>
        <p
          className={`truncate text-sm font-semibold tabular-nums leading-snug ${valueClassName}`}
        >
          {value}
        </p>
      </div>
    </div>
  );
}
