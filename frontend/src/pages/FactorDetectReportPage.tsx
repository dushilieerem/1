import { researchPagePath, inQuantWorkspace } from "@/lib/researchClient";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import {
  Activity,
  BarChart3,
  Building2,
  Clock,
  Layers,
  LineChart,
  Share2,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Archive,
} from "lucide-react";
import { AiBacktestInterpretDialog } from "@/components/AiBacktestInterpretDialog";
import { getStoredUser } from "@/lib/researchClient";
import { buildFactorDetectShareDraft } from "@/lib/communityShare";
import {
  CHART,
  QUANTILE_PALETTE,
  areaGradient,
  axisCategory,
  axisValuePct,
  chartCardClass,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import { ICDetectPanel } from "@/components/factor/ICDetectPanel";
import { IndustryDetectPanel } from "@/components/factor/IndustryDetectPanel";
import {
  RE_Q1_DIRECTION_HINT,
  clampGroups,
  groupLayerKeys,
  portfolioConvention,
  quantileLabel,
} from "@/lib/factorPanelLabels";
import {
  DETECT_BENCHMARK_OPTIONS,
  DETECT_UNIVERSE_OPTIONS,
  PORTFOLIO_TYPE_OPTIONS,
  formatDetectRunFactorsLabel,
  getProject,
  getRun,
  listDraftFactors,
  loadLastResult,
  optionLabel,
  peekRun,
  readDetectRunUiSnapshot,
  saveProject,
  type DetectRunRecord,
  type DraftDetectFactor,
} from "@/lib/detectStore";
import {
  addFactorToUserLibrary,
  listAllUserLibraryFactors,
  listUserFactorLibraries,
  type UserFactorLibrary,
} from "@/lib/userFactorLibraries";
import {
  builtinCategoryLabelsFromFactors,
  loadFactors,
} from "@/lib/factorCatalog";

const DESC_MAX = 40;

function draftsFromRun(rec: DetectRunRecord | null | undefined): DraftDetectFactor[] {
  if (!rec) return [];
  const req = rec.request as {
    _svquantDraftFactors?: DraftDetectFactor[];
    _svquantDraftFactor?: DraftDetectFactor;
  };
  const fromReq = req?._svquantDraftFactors;
  if (Array.isArray(fromReq) && fromReq.length) {
    return fromReq.filter((d) => d?.name && d?.body);
  }
  if (Array.isArray(rec.draftFactors) && rec.draftFactors.length) {
    return rec.draftFactors.filter((d) => d?.name && d?.body);
  }
  if (rec.draftFactor?.name && rec.draftFactor?.body) return [rec.draftFactor];
  if (req?._svquantDraftFactor?.name && req._svquantDraftFactor.body) {
    return [req._svquantDraftFactor];
  }
  return [];
}

type ReportTab = "equity" | "groups" | "ic" | "industry" | "overview" | "ai";

const NAV: { id: ReportTab; label: string; icon: typeof LineChart }[] = [
  { id: "equity", label: "累计收益与回撤", icon: TrendingDown },
  { id: "groups", label: "分组累计收益", icon: LineChart },
  { id: "ic", label: "IC", icon: Activity },
  { id: "industry", label: "行业", icon: Building2 },
  { id: "overview", label: "绩效概览", icon: BarChart3 },
  { id: "ai", label: "AI 解读", icon: Sparkles },
];

const CORE_TABS: ReportTab[] = ["equity", "groups", "overview", "ai"];

function hasIcData(rec: DetectRunRecord | null | undefined): boolean {
  const fa = rec?.result?.factor_analysis;
  if (!fa) return false;
  return Boolean(
    (fa.ic_series && fa.ic_series.length) ||
      (fa.cumulative_ic_series && fa.cumulative_ic_series.length) ||
      (fa.rolling_ir_series && fa.rolling_ir_series.length) ||
      fa.ic_mean != null ||
      fa.rank_ic_mean != null,
  );
}

function hasIndustryData(rec: DetectRunRecord | null | undefined): boolean {
  const fa = rec?.result?.factor_analysis;
  if (!fa) return false;
  return Boolean(
    (fa.industry_equity_curves && fa.industry_equity_curves.length) ||
      (fa.industry_group_equity_curves && fa.industry_group_equity_curves.length),
  );
}

function visibleNavFor(rec: DetectRunRecord | null | undefined) {
  const level = rec?.request?.analysis_level;
  if (level === "core") {
    return NAV.filter((n) => CORE_TABS.includes(n.id));
  }
  // full 或旧数据未带 analysis_level：按结果字段显隐 IC / 行业
  return NAV.filter((n) => {
    if (n.id === "ic") return hasIcData(rec);
    if (n.id === "industry") return hasIndustryData(rec);
    return true;
  });
}
function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}
function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(3);
}
function toCumPct(nav: number) {
  return (nav - 1) * 100;
}

function layeredEntries(lr: Record<string, number | null> | undefined | null) {
  if (!lr || typeof lr !== "object") return [] as { key: string; label: string; value: number }[];
  const out: { key: string; label: string; value: number }[] = [];
  for (const [k, v] of Object.entries(lr)) {
    if (!/^layer\d+$/i.test(k)) continue;
    if (typeof v !== "number" || Number.isNaN(v)) continue;
    const n = k.replace(/layer/i, "");
    out.push({ key: k, label: `Q${n}`, value: v });
  }
  out.sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
  return out;
}

function zoomSlider() {
  return [
    { type: "inside" as const, zoomOnMouseWheel: true, moveOnMouseMove: true },
    {
      type: "slider" as const,
      height: 22,
      bottom: 6,
      borderColor: CHART.grid,
      fillerColor: "rgba(13,148,136,0.18)",
      backgroundColor: "rgba(148,163,184,0.12)",
      handleStyle: { color: CHART.ink, borderColor: CHART.ink },
      showDetail: false,
      brushSelect: false,
    },
  ];
}

/** 长区间也保留从左到右绘制动画（默认阈值 2000 点会关掉） */
function chartAnim() {
  return {
    animation: true as const,
    animationThreshold: 200000,
    animationDuration: 900,
    animationEasing: "cubicOut" as const,
  };
}

/** 图例右上；grid.top 留空，MDD 横标在竖线顶端（低于图例） */
function legendTopRight(data: string[]) {
  return {
    ...legendBase({ top: 4, right: 8, left: "auto" }),
    data,
  };
}

/** MDD：竖线居中横写「MDD」，贴在图区顶部（在右上图例下方） */
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

export type FactorReportNavigation = {
  listPath?: string;
  projectPath?: (projectId: string) => string;
  reportPath?: (runId: string) => string;
};

export function FactorDetectReportPage({ navigation }: { navigation?: FactorReportNavigation } = {}) {
  const listPath = navigation?.listPath ?? "/factor/detect";
  const projectPath = navigation?.projectPath ?? ((id: string) => `/factor/detect/${id}`);
  const reportPath = navigation?.reportPath ?? ((id: string) => `/factor/detect/report/${id}`);
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const [rec, setRec] = useState<DetectRunRecord | null | undefined>(() =>
    runId ? peekRun(runId) ?? undefined : undefined,
  );
  const [projectName, setProjectName] = useState("");
  const [tab, setTab] = useState<ReportTab>("equity");
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [userLibs, setUserLibs] = useState<UserFactorLibrary[]>([]);
  const [archiveLibId, setArchiveLibId] = useState<number | "">("");
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [archiveErr, setArchiveErr] = useState<string | null>(null);
  const [archiveOk, setArchiveOk] = useState<string | null>(null);
  const [alreadyArchivedTip, setAlreadyArchivedTip] = useState<string | null>(null);
  const [archivedNames, setArchivedNames] = useState<Set<string>>(() => new Set());
  const [projectDrafts, setProjectDrafts] = useState<DraftDetectFactor[]>([]);
  /** 本报告相关临时因子：入库后仍保留，供「入库」按钮常驻 */
  const [archiveDrafts, setArchiveDrafts] = useState<DraftDetectFactor[]>([]);
  const [archiveTarget, setArchiveTarget] = useState<DraftDetectFactor | null>(null);
  const [archiveDesc, setArchiveDesc] = useState("");
  const [archiveCategory, setArchiveCategory] = useState("其他");
  const [categoryOptions, setCategoryOptions] = useState<string[]>(["其他"]);

  const runDrafts = useMemo(() => draftsFromRun(rec ?? null), [rec]);

  useEffect(() => {
    setArchiveDrafts([]);
  }, [runId]);

  useEffect(() => {
    setArchiveDrafts((prev) => {
      const byName = new Map(prev.map((d) => [d.name, d]));
      for (const d of [...runDrafts, ...projectDrafts]) {
        if (!d?.name || !d?.body) continue;
        byName.set(d.name, d);
      }
      return [...byName.values()];
    });
  }, [runDrafts, projectDrafts]);

  useEffect(() => {
    let cancelled = false;
    void listAllUserLibraryFactors()
      .then((rows) => {
        if (cancelled) return;
        setArchivedNames(new Set(rows.map((r) => r.name)));
      })
      .catch(() => {
        /* ignore */
      });
    return () => {
      cancelled = true;
    };
  }, [rec?.id]);

  useEffect(() => {
    let cancelled = false;
    const cached = peekRun(runId);
    if (cached) setRec(cached);
    else setRec(undefined);
    (async () => {
      const byId = await getRun(runId);
      if (cancelled) return;
      if (byId) {
        setRec(byId);
        return;
      }
      const last = await loadLastResult();
      if (cancelled) return;
      if (last && (last.id === runId || last.factorName === runId)) setRec(last);
      else setRec(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    const pid = rec?.projectId;
    if (!pid) {
      setProjectName("");
      setProjectDrafts([]);
      return;
    }
    let cancelled = false;
    void getProject(pid)
      .then((p) => {
        if (cancelled) return;
        setProjectName((p?.name || p?.description || "").trim());
        setProjectDrafts(listDraftFactors(p?.config));
      })
      .catch(() => {
        if (!cancelled) {
          setProjectName("");
          setProjectDrafts([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [rec?.projectId, rec?.id]);

  const fillArchiveForm = (draft: DraftDetectFactor) => {
    setArchiveTarget(draft);
    setArchiveDesc((draft.description || "").slice(0, DESC_MAX));
    setArchiveCategory(draft.category?.trim() || "其他");
    setArchiveErr(null);
    setCategoryOptions((prev) => {
      const cur = (draft.category || "").trim();
      if (!cur || prev.includes(cur)) return prev;
      const next = prev.filter((c) => c !== "其他");
      next.push(cur);
      if (!next.includes("其他")) next.push("其他");
      return next;
    });
  };

  const openArchive = () => {
    if (!archiveDrafts.length) return;
    const first =
      archiveDrafts.find((d) => !archivedNames.has(d.name)) || archiveDrafts[0];
    setArchiveOk(null);
    setArchiveLibId("");
    fillArchiveForm(first);
    setArchiveOpen(true);
    void Promise.all([
      listUserFactorLibraries().catch(() => [] as UserFactorLibrary[]),
      loadFactors(true).catch(() => []),
    ]).then(([libs, fs]) => {
      setUserLibs(libs);
      const cats = builtinCategoryLabelsFromFactors(
        fs.filter((f) => f.library !== "custom_lib"),
      );
      const cur = (first.category || "").trim();
      const opts = [...cats];
      if (cur && !opts.includes(cur)) opts.push(cur);
      if (!opts.includes("其他")) opts.push("其他");
      setCategoryOptions(opts);
    });
  };

  const selectArchiveFactor = (name: string) => {
    const draft = archiveDrafts.find((d) => d.name === name);
    if (!draft) return;
    fillArchiveForm(draft);
  };

  const confirmArchive = async () => {
    if (!archiveTarget) return;
    if (archivedNames.has(archiveTarget.name)) {
      setAlreadyArchivedTip(archiveTarget.name);
      return;
    }
    if (archiveLibId === "" || archiveLibId == null) {
      setArchiveErr("请选择要放入的因子库");
      return;
    }
    const description = archiveDesc.trim();
    if (!description) {
      setArchiveErr("请填写中文解释");
      return;
    }
    const category = archiveCategory.trim() || "其他";
    setArchiveBusy(true);
    setArchiveErr(null);
    try {
      await addFactorToUserLibrary(Number(archiveLibId), {
        name: archiveTarget.name,
        body: archiveTarget.body,
        description,
        categoryLabel: category,
      });
      const libName =
        userLibs.find((l) => l.id === Number(archiveLibId))?.name || "因子库";
      setArchiveOk(`「${archiveTarget.name}」已入库到「${libName}」`);
      setArchiveOpen(false);
      setArchivedNames((prev) => new Set([...prev, archiveTarget.name]));
      // 检测项目去掉琥珀色草稿标记（列表仍保留在本报告入库下拉中）
      if (rec?.projectId) {
        const proj = await getProject(rec.projectId);
        if (proj?.config) {
          const remain = listDraftFactors(proj.config).filter(
            (d) => d.name !== archiveTarget.name,
          );
          setProjectDrafts(remain);
          await saveProject({
            ...proj,
            config: {
              ...proj.config,
              draftFactor: remain[0] || null,
              draftFactors: remain.length ? remain : undefined,
              factorCodes: proj.config.factorCodes.length
                ? proj.config.factorCodes
                : [archiveTarget.name],
            },
          });
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/已存在|重名|duplicate|already/i.test(msg)) {
        setArchivedNames((prev) => new Set([...prev, archiveTarget.name]));
        setAlreadyArchivedTip(archiveTarget.name);
      } else {
        setArchiveErr(msg);
      }
    } finally {
      setArchiveBusy(false);
    }
  };

  const visibleNav = useMemo(() => visibleNavFor(rec).filter(item => !inQuantWorkspace() || item.id !== "ai"), [rec]);

  useEffect(() => {
    if (!visibleNav.some((n) => n.id === tab)) {
      setTab(visibleNav[0]?.id || "equity");
    }
  }, [visibleNav, tab]);

  const result = rec?.result;
  const m = result?.metrics;
  const req = rec?.request;
  const groups = clampGroups(
    Number(result?.factor_analysis?.layered_returns?.groups) || Number(req?.groups) || 5,
  );
  /** 主组合口径：纯多 = 做多 Q1；多空 = Q1 − QN，N 使用本次报告组数。 */
  const portfolioType = String(
    req?.portfolio_type ||
      readDetectRunUiSnapshot(rec?.request)?.portfolioType ||
      "long_only",
  );
  const portfolioLabel = optionLabel(portfolioType, PORTFOLIO_TYPE_OPTIONS);
  const convention = portfolioConvention(portfolioType, groups);

  const curveDates = useMemo(() => result?.equity_curve?.map((p) => p.date) || [], [result]);
  const stratPct = useMemo(
    () => (result?.equity_curve || []).map((p) => toCumPct(p.value)),
    [result],
  );
  const benchPct = useMemo(() => {
    const c = result?.equity_curve;
    if (!c?.length) return [] as (number | null)[];
    const benchMap = new Map((result?.benchmark_curve || []).map((p) => [p.date, p.value]));
    return c.map((p) => {
      const bv = benchMap.get(p.date);
      return bv == null ? null : toCumPct(bv);
    });
  }, [result]);
  const ddPct = useMemo(
    () => (result?.equity_curve || []).map((p) => (p.drawdown ?? 0) * 100),
    [result],
  );
  const hasBench = benchPct.some((v) => v != null);

  const mddMeta = useMemo(() => {
    const curve = result?.equity_curve || [];
    const fromMetric = result?.metrics?.max_drawdown;
    const mddPct =
      typeof fromMetric === "number" && !Number.isNaN(fromMetric)
        ? fromMetric * 100
        : ddPct.length
          ? Math.min(...ddPct)
          : 0;

    // 两图统一：标在「回撤最深」那天（谷底），与红横线一致
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

  /** 上行：策略 vs 基准；橙虚线 MDD = 最大回撤谷底日（与下图对齐） */
  const equityOnlyOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      ...chartAnim(),
      color: [CHART.ink, CHART.bench],
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string; marker: string }>) => {
          const head = params[0]?.axisValue ?? "";
          const rows = params
            .filter((p) => p.value != null && !Number.isNaN(Number(p.value)))
            .map((p) => `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}%`)
            .join("<br/>");
          return `<b>${head}</b><br/>${rows}`;
        },
      },
      legend: legendTopRight(hasBench ? ["策略", "基准"] : ["策略"]),
      grid: { left: 52, right: 20, top: 48, bottom: 58 },
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

  /** 下行：水平线 = MDD 深度；橙色竖线 = 谷底日 */
  const drawdownOnlyOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      ...chartAnim(),
      color: [CHART.amber],
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ value: number; axisValue: string; marker: string }>) => {
          const p = params[0];
          if (!p) return "";
          return `<b>${p.axisValue}</b><br/>${p.marker} 回撤: ${Number(p.value).toFixed(2)}%`;
        },
      },
      legend: legendTopRight(["回撤"]),
      grid: { left: 52, right: 28, top: 48, bottom: 58 },
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

  const groupCumOpt = useMemo(() => {
    const seriesPts = result?.factor_analysis?.cumulative_series;
    if (!seriesPts?.length) return null;
    const groupKeys = groupLayerKeys(groups);
    const benchMap = new Map(
      (result?.benchmark_curve || []).map((p) => [String(p.date), p.value]),
    );
    const tradeDates = seriesPts.map((p) => String(p.date));

    /** 只放交易日点；时间轴用时间戳，周末空隙自然拉开，中间无点 */
    const toTimePairs = (vals: Array<number | null>): Array<[number, number]> => {
      const out: Array<[number, number]> = [];
      for (let i = 0; i < tradeDates.length; i++) {
        const v = vals[i];
        if (v == null || Number.isNaN(Number(v))) continue;
        const ts = Date.parse(`${tradeDates[i]}T00:00:00`);
        if (Number.isNaN(ts)) continue;
        out.push([ts, Number(v)]);
      }
      return out;
    };

    const benchPairs = toTimePairs(
      tradeDates.map((d) => {
        const v = benchMap.get(d);
        return v == null ? null : toCumPct(v);
      }),
    );
    const groupPairs = groupKeys.map((k) =>
      toTimePairs(
        seriesPts.map((p) => {
          const v = p[k];
          return typeof v === "number" ? toCumPct(v) : null;
        }),
      ),
    );
    const showBench = benchPairs.length > 0;
    const groupLabels = groupKeys.map((k, i) => quantileLabel(k, i));
    const seriesNames = showBench ? ["基准", ...groupLabels] : groupLabels;
    const seriesColors = showBench
      ? [CHART.bench, ...QUANTILE_PALETTE.slice(0, groupKeys.length)]
      : [...QUANTILE_PALETTE.slice(0, groupKeys.length)];

    /** 悬停时各线出实心圆点（白边）；平时不铺满，避免抄空心圆也避免密点糊成线 */
    const pointMark = (color: string) => ({
      symbol: "circle" as const,
      symbolSize: 7,
      showSymbol: false,
      itemStyle: {
        color,
        borderColor: "#fff",
        borderWidth: 1.5,
      },
      emphasis: {
        scale: 1.15,
        itemStyle: {
          color,
          borderColor: "#fff",
          borderWidth: 2,
          shadowBlur: 5,
          shadowColor: "rgba(15,23,42,0.28)",
        },
      },
    });

    return {
      ...chartAnim(),
      color: seriesColors,
      grid: { left: 52, right: 20, top: 40, bottom: 56 },
      tooltip: {
        ...darkTooltip(),
        trigger: "axis" as const,
        transitionDuration: 0,
        showDelay: 0,
        hideDelay: 0,
        axisPointer: {
          type: "line" as const,
          snap: true,
          lineStyle: { color: "#94a3b8", type: "dashed" as const, width: 1 },
        },
        formatter: (
          params: Array<{
            seriesName: string;
            value: [number | string, number] | number;
            axisValueLabel?: string;
            axisValue?: string | number;
            marker: string;
            color?: string;
          }>,
        ) => {
          const list = Array.isArray(params) ? params : [params];
          if (!list.length) return "";
          const raw = list[0]?.value;
          let head = String(list[0]?.axisValueLabel ?? list[0]?.axisValue ?? "");
          if (Array.isArray(raw) && raw[0] != null) {
            const t = typeof raw[0] === "number" ? raw[0] : Date.parse(String(raw[0]));
            if (!Number.isNaN(t)) {
              const d = new Date(t);
              head = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
            } else {
              head = String(raw[0]);
            }
          }
          const rows = list
            .map((p) => {
              const v = Array.isArray(p.value) ? p.value[1] : p.value;
              if (v == null || Number.isNaN(Number(v))) return null;
              return `${p.marker} ${p.seriesName}: ${Number(v).toFixed(2)}%`;
            })
            .filter(Boolean);
          if (!rows.length) return "";
          return `<b>${head}</b><br/>${rows.join("<br/>")}`;
        },
      },
      // 组数多时图例改可滚动：10 组 + 基准共 11 项，铺开会压住曲线。
      // 滚动图例必须给定宽度（left/right 夹住），否则 ECharts 按内容撑宽、不出现翻页箭头。
      legend: {
        ...legendTopRight(seriesNames),
        ...(groupKeys.length > 5 ? { type: "scroll" as const, left: 0, right: 8 } : {}),
      },
      xAxis: {
        type: "time" as const,
        boundaryGap: false,
        // 少抽刻度，避免「周刻度 + 月初」叠在一起
        splitNumber: 7,
        axisLine: { lineStyle: { color: CHART.grid } },
        axisLabel: {
          color: CHART.axis,
          fontSize: 11,
          hideOverlap: true,
          showMinLabel: true,
          showMaxLabel: true,
          margin: 12,
          formatter: (val: number) => {
            const d = new Date(val);
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            return `${y}-${m}-${day}`;
          },
        },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      yAxis: axisValuePct(),
      dataZoom: zoomSlider(),
      series: [
        ...(showBench
          ? [
              {
                name: "基准",
                type: "line" as const,
                smooth: false,
                ...pointMark(CHART.bench),
                z: 1,
                lineStyle: { width: 2.5, color: CHART.bench },
                areaStyle: { color: areaGradient("#334155", 0.1) },
                data: benchPairs,
              },
            ]
          : []),
        ...groupKeys.map((k, i) => {
          const color = QUANTILE_PALETTE[i % QUANTILE_PALETTE.length];
          return {
            name: quantileLabel(k, i),
            type: "line" as const,
            smooth: true,
            ...pointMark(color),
            z: 2 + i,
            lineStyle: { width: 2.2, color },
            data: groupPairs[i] || [],
          };
        }),
      ],
    };
  }, [result, groups]);

  const annualOpt = useMemo(() => {
    const rows = result?.annual_returns;
    if (!rows?.length) return null;
    const vals = rows.map((r) => (r.return_value ?? 0) * 100);
    return {
      ...chartAnim(),
      tooltip: {
        ...darkTooltip(),
        trigger: "item",
        formatter: (p: { dataIndex: number; value: number | { value: number }; marker: string }) => {
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

  const layers = useMemo(() => layeredEntries(result?.factor_analysis?.layered_returns), [result]);
  const quantileMetrics = useMemo(() => {
    const rows = result?.factor_analysis?.quantile_metrics ?? [];
    // Q1..Qn 在前，benchmark 固定最后
    const groups = rows.filter((r) => !/^benchmark$/i.test(String(r.quantile || "")));
    const bench = rows.filter((r) => /^benchmark$/i.test(String(r.quantile || "")));
    return [...groups, ...bench];
  }, [result]);
  const layerOpt = useMemo(() => {
    if (!layers.length) return null;
    const vals = layers.map((x) => x.value * 100);
    return {
      ...chartAnim(),
      tooltip: {
        ...darkTooltip(),
        trigger: "item",
        formatter: (p: { dataIndex: number; value: number | { value: number }; marker: string }) => {
          const layer = layers[p.dataIndex];
          if (!layer) return "";
          const raw = typeof p.value === "number" ? p.value : p.value?.value;
          return `<b>${layer.label}</b><br/>${p.marker} 分层收益: ${Number(raw).toFixed(2)}%`;
        },
      },
      grid: { left: 16, right: 16, top: 28, bottom: 28, containLabel: true },
      xAxis: {
        type: "category",
        data: layers.map((x) => x.label),
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
          barMaxWidth: 40,
          data: vals.map((v, i) => ({
            value: v,
            itemStyle: {
              color: QUANTILE_PALETTE[i % QUANTILE_PALETTE.length],
              borderRadius: [4, 4, 0, 0],
            },
          })),
        },
      ],
    };
  }, [layers]);

  if (rec === undefined) {
    return <div className="mx-auto max-w-lg px-6 py-20 text-center text-slate-400">加载中…</div>;
  }

  if (!rec) {
    return (
      <div className="mx-auto max-w-lg px-6 py-20 text-center">
        <p className="text-slate-600">没有找到检测结果，请先运行检测。</p>
        <Link to={listPath} className="mt-4 inline-block text-sm font-medium text-blue-600 underline">
          返回检测报告
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

  const factorLabel = formatDetectRunFactorsLabel(rec);

  const shareToCommunity = () => {
    const next = `/community/new?section=factor`;
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    void (async () => {
      const draft = await buildFactorDetectShareDraft({
        name: factorLabel || rec.description || "因子检测",
        rangeLabel,
        universeLabel: optionLabel(req?.universe || "", DETECT_UNIVERSE_OPTIONS),
        benchmarkLabel: optionLabel(req?.benchmark || "", DETECT_BENCHMARK_OPTIONS),
        metrics: result?.metrics,
        excessReturn: result?.excess_return,
        factorCode: req?.factor_code,
        libraryName: req?.library_name,
        factorName: req?.factor_name,
        runId: rec.id || runId,
        returnTo: reportPath(rec.id || runId),
        returnLabel: "返回因子检测报告",
      });
      navigate(next, { state: draft });
    })();
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-slate-50 to-white">
      {/* 顶栏：标题 + 元信息卡片（对齐 NBQuant） */}
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-3 px-3 py-3 sm:flex-row sm:items-start sm:justify-between sm:px-6">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-slate-500">
              <Link to={listPath} className="hover:text-blue-600">
                检测报告
              </Link>
              {" / "}
              <Link to={projectPath(rec.projectId)} className="hover:text-blue-600">
                {projectName || "检测项目"}
              </Link>
              {" / 检测报告"}
            </p>
            <h1 className="mt-0.5 text-lg font-bold text-slate-900">{factorLabel}</h1>
            {rec.factorName &&
            rec.factorName !== "combo_factor" &&
            rec.factorName !== "custom_combo" &&
            rec.factorName !== factorLabel ? (
              <p className="font-mono text-xs text-slate-500">{rec.factorName}</p>
            ) : null}
          </div>
          <div className="grid w-full grid-cols-2 gap-2 sm:ml-auto sm:flex sm:w-auto sm:flex-wrap sm:justify-end">
            {archiveDrafts.length > 0 ? (
              <button
                type="button"
                onClick={openArchive}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-900 hover:bg-amber-100"
              >
                <Archive className="h-3.5 w-3.5 shrink-0" />
                入库
              </button>
            ) : null}
            {!inQuantWorkspace() && (<button
              type="button"
              onClick={shareToCommunity}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <Share2 className="h-3.5 w-3.5 shrink-0" />
              <span className="sm:hidden">分享</span>
              <span className="hidden sm:inline">分享到社区</span>
            </button>)}
            <Link
              to={`${projectPath(rec.projectId)}?runId=${encodeURIComponent(rec.id || runId)}`}
              className="inline-flex items-center justify-center rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <span className="sm:hidden">配置</span>
              <span className="hidden sm:inline">返回配置</span>
            </Link>
            <Link
              to={listPath}
              className="inline-flex items-center justify-center rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <span className="sm:hidden">报告</span>
              <span className="hidden sm:inline">全部报告</span>
            </Link>
          </div>
        </div>

        {archiveOk ? (
          <div className="mx-auto max-w-[1400px] px-3 pb-2 sm:px-6">
            <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
              {archiveOk}
            </p>
          </div>
        ) : null}

        <div className="mx-auto grid max-w-[1400px] grid-cols-2 gap-2 px-3 pb-3 sm:grid-cols-3 sm:px-6 lg:grid-cols-6">
          <MetaChip icon={<Clock className="h-3.5 w-3.5 text-blue-500" />} label="区间" value={rangeLabel} />
          <MetaChip
            icon={<Layers className="h-3.5 w-3.5 text-amber-500" />}
            label="股票池"
            value={optionLabel(req?.universe || "", DETECT_UNIVERSE_OPTIONS)}
          />
          <MetaChip
            icon={<TrendingUp className="h-3.5 w-3.5 text-teal-500" />}
            label="基准"
            value={optionLabel(req?.benchmark || "", DETECT_BENCHMARK_OPTIONS)}
          />
          {/* 组合类型决定「累计收益/回撤/绩效概览」的口径：纯多 = Q1，多空 = Q1 − QN */}
          <MetaChip
            icon={<Activity className="h-3.5 w-3.5 text-rose-500" />}
            label="组合类型"
            value={portfolioLabel ? `${portfolioLabel}${convention ? ` · ${convention}` : ""}` : "—"}
          />
          <MetaChip
            icon={
              <div className="flex h-3.5 w-3.5 items-center justify-center rounded bg-blue-100 text-[9px] font-bold text-blue-600">
                {groups}
              </div>
            }
            label="分组 · 调仓"
            value={`${groups} 组 · ${req?.rebalance_days ?? "—"} 日`}
          />
          <MetaChip
            icon={<BarChart3 className="h-3.5 w-3.5 text-slate-500" />}
            label="运行耗时"
            value={`${rec.elapsedSec}s`}
          />
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] px-3 py-4 sm:px-6 sm:py-5">
        {/* 移动端顶栏导航：可横滑，末项留边距避免裁切 */}
        <nav className="sticky top-0 z-10 -mx-3 mb-4 flex gap-1.5 overflow-x-auto border-b border-slate-200 bg-white/95 px-3 pb-2 backdrop-blur [scrollbar-width:thin] lg:mx-0 lg:hidden lg:px-0">
          {visibleNav.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs whitespace-nowrap ${
                tab === item.id ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              {item.label}
            </button>
          ))}
          {/* 右侧呼吸边距，防止最后一枚贴边看起来像被切掉 */}
          <span className="w-2 shrink-0" aria-hidden />
        </nav>

        <div className="flex gap-6">
          {/* 左侧导航（两行以上菜单项） */}
          <aside className="hidden w-44 shrink-0 lg:block">
            <nav className="sticky top-20 space-y-0.5">
              {visibleNav.map((item) => (
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
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">累计收益</h2>
                  <ConventionNote>
                    {[
                      convention ? `组合口径：${convention}。` : "",
                      "本页净值与回撤取自这一条主组合净值，已扣本配置的佣金/印花/滑点（默认 0）。",
                      portfolioType === "long_short"
                        ? "多空组合为市场中性口径，与下方基准指数不可直接比超额。"
                        : "",
                    ].join("")}
                  </ConventionNote>
                  {equityOnlyOpt ? (
                    <ReactECharts option={equityOnlyOpt} style={{ height: 340, width: "100%" }} notMerge opts={{ renderer: "canvas" }} />
                  ) : (
                    <p className="py-16 text-center text-sm text-slate-400">暂无净值数据</p>
                  )}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">动态回撤</h2>
                  {drawdownOnlyOpt ? (
                    <ReactECharts option={drawdownOnlyOpt} style={{ height: 260, width: "100%" }} notMerge opts={{ renderer: "canvas" }} />
                  ) : (
                    <p className="py-12 text-center text-sm text-slate-400">暂无回撤数据</p>
                  )}
                </section>
              </div>
            )}

            {tab === "groups" && (
              <div className="space-y-5">
                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">分组累计收益</h2>
                  <ConventionNote>
                    {[
                      RE_Q1_DIRECTION_HINT,
                      `；本页共 ${groups} 组。`,
                      "分组曲线是各组毛收益（交易成本只作用于主组合），与「累计收益」页的净口径不同。",
                    ].join("")}
                  </ConventionNote>
                  {groupCumOpt ? (
                    <ReactECharts option={groupCumOpt} style={{ height: 420 }} notMerge opts={{ renderer: "canvas" }} />
                  ) : (
                    <p className="py-20 text-center text-sm text-slate-400">暂无分组累计序列</p>
                  )}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-3 text-lg font-bold tracking-tight text-slate-900">分组绩效分析</h2>
                  {quantileMetrics.length ? (
                    <div className="overflow-x-auto">
                      <table className="min-w-full border-collapse text-left text-xs sm:text-sm">
                        <thead>
                          <tr className="bg-sky-50 text-slate-700">
                            {[
                              "分组",
                              "年化收益率",
                              "年化波动率",
                              "夏普比率",
                              "最大回撤",
                              "年化超额收益率",
                              "超额收益年化波动率",
                              "信息比率",
                              "相对基准胜率",
                            ].map((h) => (
                              <th
                                key={h}
                                className="whitespace-nowrap border border-slate-200 px-2.5 py-2 font-semibold"
                              >
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {quantileMetrics.map((row) => {
                            const q = String(row.quantile || "");
                            const isBench = /^benchmark$/i.test(q);
                            // 保留 Q 前缀：方向口径（Q1 = 因子值最大组）要靠它读
                            const label = isBench ? "基准" : q || "—";
                            const ar = row.annual_return;
                            return (
                              <tr
                                key={row.quantile}
                                className={`odd:bg-white even:bg-slate-50/60 ${
                                  isBench ? "bg-slate-50 font-medium" : ""
                                }`}
                              >
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {label}
                                </td>
                                <td
                                  className={`border border-slate-200 px-2.5 py-2 tabular-nums ${
                                    ar != null && ar > 0 ? "text-red-600" : "text-slate-800"
                                  }`}
                                >
                                  {pct(ar)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {pct(row.volatility)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {num(row.sharpe)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {pct(row.max_drawdown)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {isBench ? "—" : pct(row.annual_excess_return)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {isBench ? "—" : pct(row.excess_volatility)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {isBench ? "—" : num(row.information_ratio)}
                                </td>
                                <td className="border border-slate-200 px-2.5 py-2 tabular-nums text-slate-800">
                                  {isBench ? "—" : pct(row.benchmark_win_rate)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="py-10 text-center text-sm text-slate-400">
                      暂无分组绩效（需 ResearchEngine 返回 factor_analysis.quantile_metrics；请用新版接口重跑）
                    </p>
                  )}
                </section>
              </div>
            )}

            {tab === "ic" && <ICDetectPanel fa={result?.factor_analysis} />}

            {tab === "industry" && (
              <IndustryDetectPanel fa={result?.factor_analysis} groups={groups} />
            )}

            {tab === "overview" && (
              <div className="space-y-5">
                <ConventionNote>
                  {[
                    "下列指标全部是主组合口径",
                    convention ? `（${convention}）` : "",
                    "，不是某一个分组；「分层区间收益」才是逐组结果（Q1 = 因子值最大组，毛收益、区间累计、非年化）。",
                  ].join("")}
                </ConventionNote>
                {m && (
                  <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      ["Sharpe", num(m.sharpe)],
                      ["年化", pct(m.annual_return)],
                      ["最大回撤", pct(m.max_drawdown)],
                      ["Rank IC", num(m.rank_ic ?? result?.factor_analysis?.rank_ic_mean ?? m.ic)],
                      ["胜率", pct(m.win_rate)],
                      ["超额", pct(result?.excess_return)],
                    ].map(([k, v]) => (
                      <div key={k} className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm">
                        <p className="text-xs text-slate-500">{k}</p>
                        <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">{v}</p>
                      </div>
                    ))}
                  </section>
                )}

                <div className="grid gap-5 lg:grid-cols-2">
                  <section className={chartCardClass()}>
                    <h2 className="mb-2 text-sm font-semibold text-slate-800">分年收益</h2>
                    {annualOpt ? (
                      <ReactECharts option={annualOpt} style={{ height: 280 }} notMerge opts={{ renderer: "canvas" }} />
                    ) : (
                      <p className="py-16 text-center text-sm text-slate-400">暂无分年收益</p>
                    )}
                  </section>
                  <section className={chartCardClass()}>
                    <h2 className="mb-2 text-sm font-semibold text-slate-800">
                      分层区间收益
                    </h2>
                    {layerOpt ? (
                      <ReactECharts option={layerOpt} style={{ height: 280 }} notMerge opts={{ renderer: "canvas" }} />
                    ) : (
                      <p className="py-16 text-center text-sm text-slate-400">暂无分层汇总</p>
                    )}
                  </section>
                </div>

                {dds.length > 0 && (
                  <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                    <div className="border-b border-slate-100 px-4 py-3">
                      <h2 className="text-sm font-semibold text-slate-800">回撤区间标注</h2>
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        每一行是一次从高点回落到谷底的过程。「回到前高」为净值再次涨回该次回撤起点峰值的日期；若显示「尚未修复」，表示到回测结束仍未回到前高。
                      </p>
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
                              <td className="px-4 py-2 font-mono text-xs">{d.start}</td>
                              <td className="px-4 py-2 font-mono text-xs">{d.end}</td>
                              <td className="px-4 py-2 tabular-nums text-red-600">{pct(d.depth)}</td>
                              <td className="px-4 py-2 tabular-nums">{d.days ?? "—"}</td>
                              <td className="px-4 py-2 font-mono text-xs">{d.recovery ?? "尚未修复"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
              </div>
            )}

            {tab === "ai" ? (
              <AiBacktestInterpretDialog
                variant="panel"
                backtestType="factor"
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

      {archiveOpen && archiveTarget ? (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
            <h3 className="text-base font-bold text-slate-900">因子入库</h3>
            <div className="mt-4 space-y-3">
              <label className="block text-xs text-slate-500">
                要入库的因子
                <select
                  value={archiveTarget.name}
                  onChange={(e) => selectArchiveFactor(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-amber-400"
                >
                  {archiveDrafts.map((d) => (
                    <option key={d.name} value={d.name}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-slate-500">
                <span className="flex items-center justify-between gap-2">
                  <span>中文解释</span>
                  <span className="tabular-nums text-slate-400">
                    {archiveDesc.length}/{DESC_MAX}
                  </span>
                </span>
                <input
                  value={archiveDesc}
                  maxLength={DESC_MAX}
                  onChange={(e) => {
                    setArchiveDesc(e.target.value.slice(0, DESC_MAX));
                    setArchiveErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                分类
                <select
                  value={archiveCategory}
                  onChange={(e) => {
                    setArchiveCategory(e.target.value);
                    setArchiveErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-400"
                >
                  {categoryOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-slate-500">
                目标因子库
                <select
                  value={archiveLibId === "" ? "" : String(archiveLibId)}
                  onChange={(e) =>
                    setArchiveLibId(e.target.value ? Number(e.target.value) : "")
                  }
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
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
            {archiveErr ? (
              <p className="mt-2 text-xs text-red-600">{archiveErr}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setArchiveOpen(false)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={archiveBusy || userLibs.length === 0}
                onClick={() => void confirmArchive()}
                className="rounded-lg bg-amber-600 px-5 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {archiveBusy ? "入库中…" : "确定入库"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {alreadyArchivedTip ? (
        <div className="fixed inset-0 z-[140] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-2xl">
            <p className="text-base font-semibold text-slate-900">
              「{alreadyArchivedTip}」已入库
            </p>
            <button
              type="button"
              onClick={() => setAlreadyArchivedTip(null)}
              className="mt-5 rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
            >
              知道了
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** 口径说明行：讲清这一屏的数字属于哪个组合 / 哪个分位。 */
function ConventionNote({ children }: { children: ReactNode }) {
  return (
    <p className="mb-3 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
      {children}
    </p>
  );
}

function MetaChip({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-start gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-2.5 py-1.5">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] text-slate-400">{label}</p>
        <p className="break-words text-xs font-semibold leading-snug text-slate-800">{value}</p>
      </div>
    </div>
  );
}
