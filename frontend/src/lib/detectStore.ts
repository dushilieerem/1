import { researchIdentity, researchPagePath, inQuantWorkspace } from "./researchClient";
import { researchFetch as fetch } from "./researchClient";
import type { YgBacktestRequest, YgBacktestResponse } from "./ygApi";
import type { DetectSource } from "./detectSource";
import { authHeaders, assertAuthConsistency, getStoredUser, subscribeAuth, prepareAuthHandoff } from "./researchClient";
import { renameMethodDef } from "./factorCatalog";

export type WeightMode = "sum" | "product" | "custom";
export type RangeMode = "period" | "custom";
export type AnalysisLevel = "core" | "full";

/** 检测页「新建因子」草稿（未入库；带色展示；报告可入库） */
export type DraftDetectFactor = {
  name: string;
  description: string;
  category: string;
  body: string;
};

export type FactorResearchPlan = {
  researchPurpose?: 'discovery'|'replication';
  noveltyPolicy?: {scope:'all_accessible';maxAbsCorrelation:number;minDays:number;minPairs:number;minCoverage:number};
  candidateExpression?: string;
  improvementScope?: string;
  rules?: {icMetric?:'ic'|'rank_ic'; minSignedIc:number; maxDrawdown:number; minObservations:number; direction:'positive'|'negative'};
  revision: string; hypothesis: string; target: string; frequency: string;
  developmentStart: string; developmentEnd: string;
  validationStart: string; validationEnd: string;
  acceptance: string; maxTrials: number;
};

export type DetectProjectConfig = {
  researchPlan?: FactorResearchPlan;
  researchContext?: {direction:string;question:string;background:string;agentJobId?:string};

  source?: DetectSource;
  factorCodes: string[];
  /**
   * 因子名 → RE/本地 library。选因子时写入，提交时优先于 catalog 解析，
   * 避免目录未就绪或同名多库时漏传 library_name。
   */
  factorLibraries?: Record<string, string>;
  weightMode: WeightMode;
  weights: number[];
  powers: number[];
  customCombine: string;
  portfolioType: string;
  rangeMode: RangeMode;
  backtestPeriod: string;
  startDate: string;
  endDate: string;
  universe: string;
  benchmark: string;
  groups: number;
  rebalanceDays: number;
  filterLimitUp: boolean;
  filterSuspended: boolean;
  filterSt: boolean;
  filterLimitDown: boolean;
  /** core=快速检测 | full=全量检测，对应 RE analysis_level */
  analysisLevel: AnalysisLevel;
  /** 成交时点，对标 RE execution_timing；缺省视为 next_close */
  executionTiming?: ExecutionTiming;
  /** 对标 RE /yg-api：佣金率 / 卖出印花税 / 滑点率 */
  commissionRate: number;
  stampTax: number;
  slippageRate: number;
  /**
   * 新建/社区克隆临时因子（未入库；琥珀色）。
   * 可与库因子并存：factorCodes 含草稿名，检测时把 body 打进 factor_code。
   * 仅当 factorCodes 只有该草稿时，检测页进入「单因子草稿」编辑态。
   */
  draftFactor?: DraftDetectFactor | null;
  /** 多个临时因子（社区混合克隆）；有值时优先于 draftFactor */
  draftFactors?: DraftDetectFactor[];
};

export type DetectProject = {
  id: string;
  name: string;
  factorName: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  runCount: number;
  sample?: boolean;
  config: DetectProjectConfig;
};

export type DetectRunRecord = {
  id: string;
  projectId: string;
  factorName: string;
  description: string;
  /** 用户备注（全局检测报告可编辑） */
  remark?: string;
  /** 用户标记为喜欢/看好 */
  flagged?: boolean;
  request: YgBacktestRequest;
  result: YgBacktestResponse;
  finishedAt: string;
  elapsedSec: number;
  /** 本次为新建自定义因子检测时带上，报告页可入库 */
  draftFactor?: DraftDetectFactor | null;
  /** 多个临时因子（社区克隆）；优先于 draftFactor */
  draftFactors?: DraftDetectFactor[];
};

/** 单次检测落库的 UI 快照（历史还原 / 列表展示） */
export type DetectRunUiSnapshot = {
  source?: DetectSource;
  factorLibraries?: Record<string, string>;
  factorCodes: string[];
  /** code → 中文名 */
  factorLabels?: Record<string, string>;
  weights: number[];
  powers: number[];
  weightMode: WeightMode;
  customCombine: string;
  portfolioType: string;
  rangeMode: RangeMode;
  backtestPeriod: string;
  startDate: string;
  endDate: string;
  universe: string;
  benchmark: string;
  groups: number;
  rebalanceDays: number;
  filterLimitUp: boolean;
  filterSuspended: boolean;
  filterSt: boolean;
  filterLimitDown: boolean;
  analysisLevel: AnalysisLevel;
  executionTiming: ExecutionTiming;
  commissionRate: number;
  stampTax: number;
  slippageRate: number;
};

export function buildDetectRunUiSnapshot(
  cfg: DetectProjectConfig,
  labelOf?: (code: string) => string,
): DetectRunUiSnapshot {
  const factorLabels: Record<string, string> = {};
  for (const c of cfg.factorCodes || []) {
    factorLabels[c] = labelOf?.(c) || c;
  }
  return {
    factorCodes: [...(cfg.factorCodes || [])],
    source: cfg.source,
    factorLibraries: cfg.factorLibraries,
    factorLabels,
    weights: [...(cfg.weights || [])],
    powers: [...(cfg.powers || [])],
    weightMode: cfg.weightMode || "sum",
    customCombine: cfg.customCombine || "",
    portfolioType: cfg.portfolioType || "long_only",
    rangeMode: cfg.rangeMode || "period",
    backtestPeriod: cfg.backtestPeriod || "10y",
    startDate: cfg.startDate || "",
    endDate: cfg.endDate || "",
    universe: cfg.universe || "CSI300",
    benchmark: cfg.benchmark || "CSI300",
    groups: normalizeDetectGroups(cfg.groups),
    rebalanceDays: cfg.rebalanceDays || 1,
    filterLimitUp: Boolean(cfg.filterLimitUp),
    filterSuspended: Boolean(cfg.filterSuspended),
    filterSt: Boolean(cfg.filterSt),
    filterLimitDown: Boolean(cfg.filterLimitDown),
    analysisLevel: cfg.analysisLevel === "full" ? "full" : "core",
    executionTiming: normalizeExecutionTiming(cfg.executionTiming),
    commissionRate: Number(cfg.commissionRate) || 0,
    stampTax: Number(cfg.stampTax) || 0,
    slippageRate: Number(cfg.slippageRate) || 0,
  };
}

export function readDetectRunUiSnapshot(
  req: YgBacktestRequest | Record<string, unknown> | null | undefined,
): DetectRunUiSnapshot | null {
  const raw = (req as { _svquant_ui?: DetectRunUiSnapshot } | null | undefined)
    ?._svquant_ui;
  if (!raw || typeof raw !== "object") return null;
  const codes = Array.isArray(raw.factorCodes)
    ? raw.factorCodes.map(String).filter(Boolean)
    : [];
  if (!codes.length && !(raw.customCombine || "").trim()) return null;
  return {
    factorCodes: codes,
    source: raw.source,
    factorLibraries: raw.factorLibraries,
    factorLabels:
      raw.factorLabels && typeof raw.factorLabels === "object"
        ? Object.fromEntries(
            Object.entries(raw.factorLabels).map(([k, v]) => [k, String(v)]),
          )
        : {},
    weights: Array.isArray(raw.weights) ? raw.weights.map(Number) : equalWeights(codes.length),
    powers: Array.isArray(raw.powers) ? raw.powers.map(Number) : equalPowers(codes.length),
    weightMode:
      raw.weightMode === "product" || raw.weightMode === "custom"
        ? raw.weightMode
        : "sum",
    customCombine: String(raw.customCombine || ""),
    portfolioType: String(raw.portfolioType || "long_only"),
    rangeMode: raw.rangeMode === "custom" ? "custom" : "period",
    backtestPeriod: String(raw.backtestPeriod || "10y"),
    startDate: String(raw.startDate || ""),
    endDate: String(raw.endDate || ""),
    universe: String(raw.universe || "CSI300"),
    benchmark: String(raw.benchmark || "CSI300"),
    groups: normalizeDetectGroups(raw.groups),
    rebalanceDays: Number(raw.rebalanceDays) || 1,
    filterLimitUp: Boolean(raw.filterLimitUp),
    filterSuspended: Boolean(raw.filterSuspended),
    filterSt: Boolean(raw.filterSt),
    filterLimitDown: Boolean(raw.filterLimitDown),
    analysisLevel: raw.analysisLevel === "full" ? "full" : "core",
    // 老快照没有这个字段，回落到 RE 默认值，不能留 undefined。
    executionTiming: normalizeExecutionTiming(raw.executionTiming),
    commissionRate: Number(raw.commissionRate) || 0,
    stampTax: Number(raw.stampTax) || 0,
    slippageRate: Number(raw.slippageRate) || 0,
  };
}

/** 历史列表「因子」列文案 */
export function formatDetectRunFactorsLabel(
  rec: Pick<DetectRunRecord, "description" | "factorName" | "request">,
): string {
  const ui = readDetectRunUiSnapshot(rec.request);
  if (ui?.factorCodes?.length) {
    const labels = ui.factorCodes.map(
      (c) => ui.factorLabels?.[c] || c,
    );
    if (labels.length <= 3) return labels.join(" + ");
    return `${labels.slice(0, 2).join(" + ")} 等${labels.length}个`;
  }
  const desc = (rec.description || "").trim();
  const fname = (rec.factorName || "").trim();
  if (desc && desc !== fname && desc !== "combo_factor" && desc !== "custom_combo") {
    return desc;
  }
  if (fname && fname !== "combo_factor" && fname !== "custom_combo") return fname;
  return desc || fname || "—";
}

/** 历史快照 → 覆盖到项目 config（仅内存展示，是否落库由调用方决定） */
export function applyDetectRunSnapshotToConfig(
  cfg: DetectProjectConfig,
  snap: DetectRunUiSnapshot,
): DetectProjectConfig {
  return {
    ...cfg,
    source: snap.source,
    factorLibraries: snap.factorLibraries || {},
    factorCodes: [...snap.factorCodes],
    weights: snap.weights.length
      ? [...snap.weights]
      : equalWeights(snap.factorCodes.length),
    powers: snap.powers.length
      ? [...snap.powers]
      : equalPowers(snap.factorCodes.length),
    weightMode: snap.weightMode,
    customCombine: snap.customCombine,
    portfolioType: snap.portfolioType,
    rangeMode: snap.rangeMode,
    backtestPeriod: snap.backtestPeriod,
    startDate: snap.startDate,
    endDate: snap.endDate,
    universe: snap.universe,
    benchmark: snap.benchmark,
    groups: normalizeDetectGroups(snap.groups),
    rebalanceDays: snap.rebalanceDays,
    filterLimitUp: snap.filterLimitUp,
    filterSuspended: snap.filterSuspended,
    filterSt: snap.filterSt,
    filterLimitDown: snap.filterLimitDown,
    analysisLevel: snap.analysisLevel,
    executionTiming: normalizeExecutionTiming(snap.executionTiming),
    commissionRate: snap.commissionRate,
    stampTax: snap.stampTax,
    slippageRate: snap.slippageRate,
  };
}

export const DETECT_UNIVERSE_OPTIONS = [
  { code: "CSI300", label: "沪深300" },
  { code: "CSI500", label: "中证500" },
  { code: "CSI800", label: "中证800" },
  { code: "CSI1000", label: "中证1000" },
  { code: "SSE50", label: "上证50" },
  { code: "CSI_ALL", label: "全A" },
] as const;

export const DETECT_BENCHMARK_OPTIONS = [
  { code: "CSI300", label: "沪深300" },
  { code: "SSE50", label: "上证50" },
  { code: "CSI500", label: "中证500" },
  { code: "CSI800", label: "中证800" },
  { code: "CSI1000", label: "中证1000" },
] as const;

export const DETECT_PERIOD_OPTIONS = [
  { code: "10y", label: "近10年" },
  { code: "5y", label: "近5年" },
  { code: "3y", label: "近3年" },
  { code: "1y", label: "近1年" },
  { code: "6m", label: "近6个月" },
  { code: "3m", label: "近3月" },
  { code: "1m", label: "近1个月" },
  { code: "10d", label: "近10日" },
  { code: "5d", label: "近5日" },
  { code: "1d", label: "近1日" },
] as const;

export const DETECT_ANALYSIS_LEVEL_OPTIONS = [
  { code: "core" as const, label: "快速检测" },
  { code: "full" as const, label: "全量检测" },
] as const;

/**
 * 成交时点（对标 RE execution_timing）。信号恒在 T 日收盘产生：
 *   same_close  T 日收盘价成交（旧口径，最乐观）
 *   next_close  T+1 日收盘价成交（RE 默认值）
 *   next_open   T+1 日开盘价成交
 */
export const EXECUTION_TIMING_OPTIONS = [
  { code: "same_close" as const, label: "当日收盘" },
  { code: "next_close" as const, label: "次日收盘" },
  { code: "next_open" as const, label: "次日开盘" },
] as const;

export type ExecutionTiming = (typeof EXECUTION_TIMING_OPTIONS)[number]["code"];

/**
 * 因子分层数。RE 的约束是 2~10，这里只暴露 3 / 5 / 10——原先的选项里含 1，
 * 而 RE 要求 >= 2，选「1 组」必然 422。
 */
export const DETECT_GROUP_OPTIONS = [3, 5, 10] as const;

export const DEFAULT_DETECT_GROUPS = 5;

/** 把任意输入收敛成允许的分层数；不在选项内一律回落默认值。 */
export function normalizeDetectGroups(value: unknown): number {
  const n = Number(value);
  return (DETECT_GROUP_OPTIONS as readonly number[]).includes(n)
    ? n
    : DEFAULT_DETECT_GROUPS;
}

/** 默认成交时点，与 ResearchEngine 的默认值保持一致。 */
export const DEFAULT_EXECUTION_TIMING: ExecutionTiming = "next_close";

/** 把任意输入收敛成合法的成交时点；非法或缺失一律回落默认值。 */
export function normalizeExecutionTiming(value: unknown): ExecutionTiming {
  return value === "same_close" || value === "next_close" || value === "next_open"
    ? value
    : DEFAULT_EXECUTION_TIMING;
}

export const RE_MARKET_END = (() => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
})();

/** 预设周期 end：日历今天（RE 无数据日会自动裁到行情末日，不报错） */
export function reMarketEndToday(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseYmd(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function fmtDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 预设周期 → start/end（end 为当天，随日历滚动） */
export function resolveBacktestRange(cfg: DetectProjectConfig): { start: string; end: string } {
  if (cfg.rangeMode === "custom") {
    return { start: cfg.startDate, end: cfg.endDate };
  }
  return periodToStartEnd(cfg.backtestPeriod || "10y");
}

/** 自定义因子试算等：仅用 period 字符串 */
export function periodToStartEnd(period: string): { start: string; end: string } {
  const end = parseYmd(reMarketEndToday());
  const start = new Date(end);
  const p = period || "10y";
  if (p === "1d") start.setDate(start.getDate() - 1);
  else if (p === "5d") start.setDate(start.getDate() - 5);
  else if (p === "10d") start.setDate(start.getDate() - 10);
  else if (p === "1m") start.setMonth(start.getMonth() - 1);
  else if (p === "6m") start.setMonth(start.getMonth() - 6);
  else if (p === "3m") start.setMonth(start.getMonth() - 3);
  else if (p === "1y") start.setFullYear(start.getFullYear() - 1);
  else if (p === "3y") start.setFullYear(start.getFullYear() - 3);
  else if (p === "5y") start.setFullYear(start.getFullYear() - 5);
  else start.setFullYear(start.getFullYear() - 10); // 10y 默认
  return { start: fmtDate(start), end: fmtDate(end) };
}

/** 切入自定义区间时的默认起止（空值才填充） */
export function defaultCustomRangeDates(period = "10y"): { startDate: string; endDate: string } {
  const r = periodToStartEnd(period);
  return { startDate: r.start, endDate: r.end };
}

/** 保证 end >= start；返回修正后的一对日期 */
export function clampDateRange(
  startDate: string,
  endDate: string,
  changed: "start" | "end",
): { startDate: string; endDate: string } {
  if (!startDate || !endDate) return { startDate, endDate };
  if (endDate >= startDate) return { startDate, endDate };
  if (changed === "start") return { startDate, endDate: startDate };
  return { startDate: endDate, endDate };
}

export const PORTFOLIO_TYPE_OPTIONS = [
  {
    code: "long_short",
    label: "多空",
    hint: "做多最高分组、做空最低分组，衡量因子多空收益。",
  },
  {
    code: "long_only",
    label: "纯多",
    hint: "只做多最高分组，不进行空头对冲。",
  },
] as const;

export function equalWeights(n: number): number[] {
  if (n <= 0) return [];
  const base = Math.floor((100 / n) * 100) / 100;
  const weights = Array.from({ length: n }, () => base);
  const sum = weights.reduce((a, b) => a + b, 0);
  if (weights.length) {
    weights[weights.length - 1] =
      Math.round((weights[weights.length - 1] + (100 - sum)) * 100) / 100;
  }
  return weights;
}

export function equalPowers(n: number): number[] {
  return Array.from({ length: n }, () => 1);
}

export function defaultConfig(factorCodes: string[] = []): DetectProjectConfig {
  const codes = [...factorCodes];
  return {
    factorCodes: codes,
    factorLibraries: {},
    weightMode: "sum",
    weights: equalWeights(codes.length),
    powers: equalPowers(codes.length),
    customCombine: codes.length
      ? `def combo_factor(self):\n    """自定义组合"""\n    return self.${codes[0]}()`
      : `def combo_factor(self):\n    """自定义组合"""\n    return self.close.pct_change(5)`,
    portfolioType: "long_only",
    rangeMode: "period",
    backtestPeriod: "10y",
    startDate: periodToStartEnd("10y").start,
    endDate: periodToStartEnd("10y").end,
    universe: "CSI300",
    benchmark: "CSI300",
    groups: 5,
    rebalanceDays: 1,
    filterLimitUp: false,
    filterSuspended: false,
    filterSt: false,
    filterLimitDown: false,
    analysisLevel: "core",
    executionTiming: DEFAULT_EXECUTION_TIMING,
    commissionRate: 0,
    stampTax: 0,
    slippageRate: 0,
  };
}

function normalizeProject(
  raw: DetectProject & { config?: Partial<DetectProjectConfig> },
): DetectProject {
  const base = defaultConfig(
    raw.factorName && raw.factorName !== "custom_combo" ? [raw.factorName] : [],
  );
  const cfg: DetectProjectConfig = { ...base, ...(raw.config || {}) };
  if (!cfg.rangeMode) {
    cfg.rangeMode =
      cfg.startDate && cfg.endDate && !cfg.backtestPeriod ? "custom" : "period";
  }
  if (!cfg.backtestPeriod) cfg.backtestPeriod = "10y";
  if (cfg.analysisLevel !== "core" && cfg.analysisLevel !== "full") {
    cfg.analysisLevel = "core";
  }
  cfg.groups = normalizeDetectGroups(cfg.groups);
  cfg.executionTiming = normalizeExecutionTiming(cfg.executionTiming);
  if (!cfg.factorLibraries || typeof cfg.factorLibraries !== "object") {
    cfg.factorLibraries = {};
  }
  if (typeof cfg.commissionRate !== "number" || Number.isNaN(cfg.commissionRate)) {
    cfg.commissionRate = base.commissionRate;
  }
  if (typeof cfg.stampTax !== "number" || Number.isNaN(cfg.stampTax)) {
    cfg.stampTax = base.stampTax;
  }
  if (typeof cfg.slippageRate !== "number" || Number.isNaN(cfg.slippageRate)) {
    cfg.slippageRate = base.slippageRate;
  }
  return { ...raw, config: cfg };
}

const memoryRuns = new Map<string, DetectRunRecord>();
let cacheUserId: string | null = null;
let projectCache: DetectProject[] = [];

function currentUserId(): number | null {
  const u = getStoredUser();
  return u?.id != null && u.id > 0 ? u.id : null;
}

function purgeLegacyBrowserDetectKeys() {
  try {
    const drop: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k) continue;
      if (
        k === "svquant_detect_projects_v2" ||
        k === "svquant_detect_runs_v2" ||
        k === "svquant_detect_result_v2" ||
        k.startsWith("svquant_detect_projects_v2_") ||
        k.startsWith("svquant_detect_result_v2_")
      ) {
        drop.push(k);
      }
    }
    drop.forEach((k) => localStorage.removeItem(k));
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith("svquant_detect_")) sessionStorage.removeItem(k);
    }
  } catch {
    /* ignore */
  }
}

export function clearDetectClientCache() {
  projectCache = [];
  memoryRuns.clear();
  cacheUserId = researchIdentity();
}

function ensureCacheOwner() {
  const uid = researchIdentity();
  if (cacheUserId !== uid) {
    projectCache = [];
    memoryRuns.clear();
    cacheUserId = uid;
  }
}

purgeLegacyBrowserDetectKeys();
subscribeAuth(() => {
  purgeLegacyBrowserDetectKeys();
  clearDetectClientCache();
});

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const user = getStoredUser();
  if (!user?.id) throw new Error("未登录");
  assertAuthConsistency();
  ensureCacheOwner();
  const uid = user.id;
  // URL 带 uid，避免浏览器把不同账号的 GET 列表当成同一缓存
  const join = url.includes("?") ? "&" : "?";
  const urlWithUid = `${url}${join}_uid=${uid}&_ts=${Date.now()}`;
  const res = await fetch(urlWithUid, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const data = (await res.json().catch(() => ({}))) as T & {
    error?: string;
    user_id?: number;
  };
  if (!res.ok) {
    const detail = String((data as { error?: string }).error || "").trim();
    // Vite 代理到 :8766 失败时常只有状态码、无 JSON error（与检测台直打 RE 的失败不同）
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new Error(
        detail ||
          `本机 API 暂不可达（HTTP ${res.status}）。红色「检测」只创建/打开检测项目，不跑回测；请确认后端 :8766 在运行后重试。`,
      );
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (typeof data.user_id === "number" && data.user_id !== uid) {
    clearDetectClientCache();
    throw new Error(`账号不一致：当前 ${uid}，接口 ${data.user_id}，请重新登录`);
  }
  return data;
}

export async function listProjects(): Promise<DetectProject[]> {
  ensureCacheOwner();
  const data = await apiJson<{ projects: DetectProject[]; user_id?: number }>(
    "/api/detect/projects",
  );
  projectCache = (data.projects || []).map((p) => normalizeProject(p));
  return [...projectCache];
}

export async function listVisibleProjects(): Promise<DetectProject[]> {
  ensureCacheOwner();
  // 与策略研究一致：展示全部项目（含社区克隆后尚未检测的）
  const data = await apiJson<{
    projects: DetectProject[];
    user_id?: number;
    username?: string;
  }>("/api/detect/projects");
  const me = getStoredUser();
  if (
    me &&
    ((typeof data.user_id === "number" && data.user_id !== me.id) ||
      (data.username && data.username !== me.username))
  ) {
    clearDetectClientCache();
    throw new Error(
      `账号不一致：界面 ${me.username}，接口 ${data.username || data.user_id}，请重新登录`,
    );
  }
  projectCache = (data.projects || []).map((p) => normalizeProject(p));
  return [...projectCache];
}

export async function ensureSampleProject(): Promise<DetectProject> {
  const list = await listProjects();
  const sample = list.find((p) => p.sample);
  if (!sample) throw new Error("样例项目创建失败");
  return sample;
}

export async function getProject(id: string): Promise<DetectProject | undefined> {
  ensureCacheOwner();
  const hit = projectCache.find((p) => p.id === id);
  try {
    const data = await apiJson<{ project: DetectProject }>(
      `/api/detect/projects/${encodeURIComponent(id)}`,
    );
    const p = normalizeProject(data.project);
    const idx = projectCache.findIndex((x) => x.id === p.id);
    if (idx >= 0) projectCache[idx] = p;
    else projectCache.unshift(p);
    return p;
  } catch {
    return inQuantWorkspace() ? undefined : hit;
  }
}

/** 同步读缓存，避免新建/跳转时先闪「不存在」 */
export function peekProject(id: string): DetectProject | undefined {
  ensureCacheOwner();
  return projectCache.find((p) => p.id === id);
}

export async function saveProject(project: DetectProject): Promise<DetectProject> {
  ensureCacheOwner();
  const next = { ...normalizeProject(project), updatedAt: new Date().toISOString() };
  const data = await apiJson<{ project: DetectProject }>(
    `/api/detect/projects/${encodeURIComponent(next.id)}`,
    { method: "PUT", body: JSON.stringify(next) },
  );
  const saved = normalizeProject(data.project);
  const idx = projectCache.findIndex((p) => p.id === saved.id);
  if (idx >= 0) projectCache[idx] = saved;
  else projectCache.unshift(saved);
  return saved;
}

export async function createProject(
  factorName: string,
  description: string,
  displayName?: string,
): Promise<DetectProject> {
  ensureCacheOwner();
  const codes =
    factorName && factorName !== "custom_combo" ? [factorName] : [];
  const data = await apiJson<{ project: DetectProject }>("/api/detect/projects", {
    method: "POST",
    body: JSON.stringify({
      factorName,
      description,
      name: displayName || description || factorName,
      config: defaultConfig(codes),
    }),
  });
  const p = normalizeProject(data.project);
  projectCache = [p, ...projectCache.filter((x) => x.id !== p.id)];
  return p;
}

export async function deleteProject(id: string) {
  ensureCacheOwner();
  const p = projectCache.find((x) => x.id === id);
  if (p?.sample) return;
  await apiJson(`/api/detect/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  projectCache = projectCache.filter((x) => x.id !== id);
}

export async function listRuns(projectId: string): Promise<DetectRunRecord[]> {
  ensureCacheOwner();
  const data = await apiJson<{ runs: DetectRunRecord[] }>(
    `/api/detect/projects/${encodeURIComponent(projectId)}/runs`,
  );
  // 列表接口是摘要，不要覆盖内存里的完整报告
  return data.runs || [];
}

/** 当前用户全部检测运行（全局检测报告） */
export async function listAllDetectRuns(): Promise<DetectRunRecord[]> {
  ensureCacheOwner();
  const data = await apiJson<{ runs: DetectRunRecord[] }>("/api/detect/runs");
  return data.runs || [];
}

export async function updateDetectRunRemark(
  runId: string,
  remark: string,
): Promise<DetectRunRecord> {
  ensureCacheOwner();
  const data = await apiJson<{ run: DetectRunRecord }>(
    `/api/detect/runs/${encodeURIComponent(runId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ remark }),
    },
  );
  const full = data.run;
  const prev = memoryRuns.get(runId);
  if (prev) memoryRuns.set(runId, { ...prev, remark: full.remark ?? remark });
  else memoryRuns.set(runId, full);
  return full;
}

export async function updateDetectRunFlagged(
  runId: string,
  flagged: boolean,
): Promise<DetectRunRecord> {
  ensureCacheOwner();
  const data = await apiJson<{ run: DetectRunRecord }>(
    `/api/detect/runs/${encodeURIComponent(runId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ flagged }),
    },
  );
  const full = data.run;
  const prev = memoryRuns.get(runId);
  if (prev) memoryRuns.set(runId, { ...prev, flagged: full.flagged ?? flagged });
  else memoryRuns.set(runId, full);
  return full;
}

export async function deleteRun(runId: string) {
  ensureCacheOwner();
  await apiJson(`/api/detect/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  memoryRuns.delete(runId);
  await listProjects();
}

export async function saveDetectRun(
  rec: Omit<DetectRunRecord, "id"> & { id?: string },
): Promise<DetectRunRecord> {
  ensureCacheOwner();
  const data = await apiJson<{ run: DetectRunRecord; project?: DetectProject }>(
    "/api/detect/runs",
    { method: "POST", body: JSON.stringify(rec) },
  );
  const full = data.run;
  memoryRuns.set(full.id, full);
  if (data.project) {
    const p = normalizeProject(data.project);
    const idx = projectCache.findIndex((x) => x.id === p.id);
    if (idx >= 0) projectCache[idx] = p;
    else projectCache.unshift(p);
  }
  try {
    const uid = currentUserId();
    sessionStorage.setItem(
      `svquant_detect_last_run_u${uid}`,
      JSON.stringify({ id: full.id }),
    );
  } catch {
    /* ignore */
  }
  return full;
}

export async function getRun(runId: string): Promise<DetectRunRecord | undefined> {
  ensureCacheOwner();
  const hit = memoryRuns.get(runId);
  try {
    const data = await apiJson<{ run: DetectRunRecord }>(
      `/api/detect/runs/${encodeURIComponent(runId)}`,
    );
    memoryRuns.set(runId, data.run);
    return data.run;
  } catch {
    return inQuantWorkspace() ? undefined : hit;
  }
}

export function peekRun(runId: string): DetectRunRecord | undefined {
  ensureCacheOwner();
  return memoryRuns.get(runId);
}

export async function loadLastResult(): Promise<DetectRunRecord | null> {
  ensureCacheOwner();
  try {
    const uid = currentUserId();
    const raw = sessionStorage.getItem(`svquant_detect_last_run_u${uid}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { id?: string };
    if (parsed?.id) return (await getRun(parsed.id)) || null;
  } catch {
    /* ignore */
  }
  return null;
}

/** 单因子检测配置：预选该因子 + 赋权相加（不用「自定义组合」塞整段代码） */
function singleFactorDetectConfig(
  factorName: string,
  base?: Partial<DetectProjectConfig>,
): DetectProjectConfig {
  const codes = [factorName];
  const cfg = { ...defaultConfig(codes), ...(base || {}) };
  cfg.factorCodes = codes;
  cfg.weightMode = "sum";
  cfg.weights = equalWeights(1);
  cfg.powers = equalPowers(1);
  cfg.customCombine = `def ${factorName}(self):\n    """单因子"""\n    return self.${factorName}()`;
  return cfg;
}

/**
 * 面板进检测时清洗显示名：只去掉末尾「口语括注」，保留公式里的（快-慢）等。
 */
export function cleanDetectDisplayName(raw: string, fallback = ""): string {
  let s = (raw || "").trim();
  const m = s.match(/^(.*?)[（(]([^）)]*)[）)]\s*$/u);
  if (m) {
    const head = m[1].trim();
    const inner = m[2].trim();
    const casual =
      /有点|厉害|哈哈|测试|test|TODO|xxx|随便|备注|啊|呢|吧|嘛|哦|啦|嘿/i.test(
        inner,
      ) || (inner.length <= 8 && /[啊呢吧嘛哦啦嘿]/.test(inner));
    if (casual && head) s = head;
  }
  return s || (fallback || "").trim() || "未命名检测";
}

export async function openOrCreateForFactor(
  factorName: string,
  description: string,
): Promise<DetectProject> {
  ensureCacheOwner();
  const name = (factorName || "").trim();
  if (!name) throw new Error("因子名为空");
  const title = cleanDetectDisplayName(description, name);
  // 有内存列表则不再全量 GET，缩短红「检测」占位等待
  const list =
    projectCache.length > 0 ? [...projectCache] : await listProjects();
  const existing = list.find((p) => p.factorName === name && !p.sample);
  if (existing) {
    // 复用已有项目：保留已选因子/权重，不要 reset 成单因子
    existing.name = title;
    existing.description = title;
    let cfg = { ...(existing.config || defaultConfig([name])) };
    let codes = [...(cfg.factorCodes || [])];
    // 若配置被洗成只剩主因子，尝试从最近一次检测快照恢复成分因子
    const onlyPrimary =
      !codes.length ||
      (codes.length === 1 && codes[0] === name) ||
      (codes.length > 0 && codes.every((c) => c === name));
    if (onlyPrimary) {
      try {
        const runs = await listRuns(existing.id);
        const snap = runs[0]
          ? readDetectRunUiSnapshot(runs[0].request)
          : null;
        if (snap?.factorCodes && snap.factorCodes.length > 1) {
          cfg = applyDetectRunSnapshotToConfig(cfg, snap);
          codes = [...(cfg.factorCodes || [])];
        }
      } catch {
        /* 无历史则保持现状 */
      }
    }
    if (name && !codes.includes(name)) {
      codes.push(name);
      cfg.factorCodes = codes;
      if (cfg.weightMode === "sum") {
        const ingredients = codes.filter((c) => c !== name);
        const ew = equalWeights(ingredients.length || 1);
        cfg.weights = codes.map((c) => {
          if (c === name) return 0;
          const ii = ingredients.indexOf(c);
          return ii >= 0 ? ew[ii] : 0;
        });
      } else if ((cfg.weights || []).length !== codes.length) {
        cfg.weights = equalWeights(codes.length);
      }
      if ((cfg.powers || []).length !== codes.length) {
        cfg.powers = equalPowers(codes.length);
      }
    }
    existing.config = cfg;
    return saveProject(existing);
  }
  const created = await createProject(name, title, title);
  created.config = singleFactorDetectConfig(name, created.config);
  created.config.customCombine = `def ${name}(self):\n    """${title}"""\n    return self.${name}()`;
  return saveProject(created);
}

/** 社区克隆：始终新建检测项目（不复用已有同名项目） */
export async function createDetectProjectForClone(
  factorCode: string,
  displayName: string,
): Promise<DetectProject> {
  ensureCacheOwner();
  const code = (factorCode || "").trim();
  if (!code) throw new Error("因子名为空");
  const title = (displayName || code).trim() || code;
  const created = await createProject(code, title, title);
  created.config = singleFactorDetectConfig(code, created.config);
  return saveProject(created);
}

/**
 * 社区克隆 → 因子检测：新建检测项目，以「新建因子」草稿模式承载源码（琥珀色单因子，报告可入库）。
 */
export async function createDetectProjectFromSnippet(opts: {
  /** 检测项目显示名 */
  title: string;
  code: string;
  /** 因子代码名（须与函数 def 一致；会改写源码 def 名） */
  name: string;
  description: string;
  category: string;
}): Promise<DetectProject> {
  ensureCacheOwner();
  const code = (opts.code || "").trim();
  if (!code) throw new Error("该帖没有代码片段");
  const name = (opts.name || "").trim();
  if (!name) throw new Error("请填写因子代码名");
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    throw new Error("因子代码名须为字母开头的标识符（字母/数字/下划线）");
  }
  const description = (opts.description || "").trim() || name;
  const category = (opts.category || "").trim() || "其他";
  const title = (opts.title || description).trim() || name;

  let body = renameMethodDef(code, name);
  if (!/^\s*def\s+/m.test(body)) {
    const doc = description.replace(/\\/g, "\\\\").replace(/"""/g, "'''");
    const indented = body
      .split("\n")
      .map((ln) => (ln.trim() ? `    ${ln}` : ln))
      .join("\n");
    body = `def ${name}(self):\n    """${doc}"""\n${indented}\n`;
  }

  const created = await createProject(name, title, title);
  created.config = {
    ...defaultConfig([name]),
    factorCodes: [name],
    weightMode: "sum",
    weights: equalWeights(1),
    powers: equalPowers(1),
    // AI/社区草稿：默认 1 年 + 5 日调仓，避免日频×自定义源码首次试跑过久
    backtestPeriod: "1y",
    startDate: periodToStartEnd("1y").start,
    endDate: periodToStartEnd("1y").end,
    rebalanceDays: 5,
    draftFactor: {
      name,
      description,
      category,
      body,
    },
  };
  return saveProject(created);
}

/** 配置里的临时草稿列表（兼容旧单一 draftFactor） */
export function listDraftFactors(
  cfg: Pick<DetectProjectConfig, "draftFactor" | "draftFactors"> | null | undefined,
): DraftDetectFactor[] {
  if (!cfg) return [];
  if (cfg.draftFactors?.length) return cfg.draftFactors;
  if (cfg.draftFactor?.name) return [cfg.draftFactor];
  return [];
}

/** 社区克隆 → 选用平台公用因子（不展开源码）；可选附带临时自定义草稿 */
export async function createDetectProjectFromLibraryFactors(opts: {
  title: string;
  factorIds: string[];
  comboFn?: string;
  weightMode?: WeightMode;
  /** 帖内自定义因子：临时带入，不入库 */
  draftFactors?: DraftDetectFactor[];
}): Promise<DetectProject> {
  ensureCacheOwner();
  const drafts = (opts.draftFactors || []).filter((d) => d?.name && d?.body);
  const ids = (opts.factorIds || []).map(String).filter(Boolean);
  for (const d of drafts) {
    if (!ids.includes(d.name)) ids.push(d.name);
  }
  if (!ids.length) throw new Error("未指定公用因子");
  const title = (opts.title || ids.join("+")).trim() || "社区克隆";
  const created = await createProject(ids[0], title, title);
  const mode = opts.weightMode || (ids.length > 1 ? "custom" : "sum");
  const combo =
    (opts.comboFn || "").trim() ||
    (ids.length === 1
      ? `def combo_factor(self):\n    """直通"""\n    return self.${ids[0]}()`
      : `def combo_factor(self):\n    """自定义组合"""\n    return ${ids.map((c) => `self.${c}()`).join(" + ")}`);
  created.config = {
    ...defaultConfig(ids),
    factorCodes: ids,
    weightMode: mode,
    weights: equalWeights(ids.length),
    powers: equalPowers(ids.length),
    customCombine: combo,
    draftFactor: drafts[0] || null,
    draftFactors: drafts.length ? drafts : undefined,
  };
  return saveProject(created);
}

function detectPath(projectId: string) {
  return researchPagePath(`/factor/detect/${encodeURIComponent(projectId)}`);
}

function isNarrowViewport() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 1023px)").matches
  );
}

const DETECT_OPENING_HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>正在加载检测项目…</title>
  <style>
    html, body { margin: 0; height: 100%; background: #f0f2f5;
      font-family: system-ui, "Segoe UI", "Microsoft YaHei", sans-serif; }
    body { display: flex; align-items: center; justify-content: center; color: #475569; }
    .c { text-align: center; }
    .s { width: 28px; height: 28px; margin: 0 auto 12px; border-radius: 50%;
      border: 3px solid #e2e8f0; border-top-color: #e11d48;
      animation: r .8s linear infinite; }
    @keyframes r { to { transform: rotate(360deg); } }
    p { margin: 0; font-size: 14px; }
  </style>
</head>
<body>
  <div class="c"><div class="s"></div><p>正在加载检测项目…</p></div>
</body>
</html>`;

/**
 * 必须在 click 同步阶段调用（await 之前），否则浏览器会丢「用户手势」，
 * window.open 被拦后旧逻辑会 location.assign，表现为「不新开页、当前页跳走」。
 * 立刻写入加载页，避免 about:blank 在等建项目时长时间白屏。
 * 返回占位标签；窄屏返回 null（稍后同页跳转）。
 */
export function openDetectPlaceholderTab(): Window | null {
  prepareAuthHandoff();
  if (isNarrowViewport()) return null;
  try {
    const win = window.open("about:blank", "_blank");
    if (win) {
      try {
        win.document.open();
        win.document.write(DETECT_OPENING_HTML);
        win.document.close();
      } catch {
        /* 跨域或已导航则忽略 */
      }
    }
    return win;
  } catch {
    return null;
  }
}

/** 新标签打开检测页时的项目快照（localStorage，跨标签；用完即删） */
const DETECT_PROJECT_SEED_PREFIX = "svquant_detect_project_seed_";
const DETECT_PROJECT_SEED_TTL_MS = 60_000;

export function seedDetectProjectForNewTab(project: DetectProject): void {
  if (inQuantWorkspace()) return;
  try {
    localStorage.setItem(
      `${DETECT_PROJECT_SEED_PREFIX}${project.id}`,
      JSON.stringify({ at: Date.now(), project }),
    );
  } catch {
    /* quota */
  }
}

export function consumeDetectProjectSeed(id: string): DetectProject | undefined {
  if (inQuantWorkspace()) return undefined;
  const key = `${DETECT_PROJECT_SEED_PREFIX}${id}`;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return undefined;
    localStorage.removeItem(key);
    const parsed = JSON.parse(raw) as { at?: number; project?: DetectProject };
    if (
      typeof parsed.at !== "number" ||
      Date.now() - parsed.at > DETECT_PROJECT_SEED_TTL_MS ||
      !parsed.project
    ) {
      return undefined;
    }
    const p = normalizeProject(parsed.project);
    const idx = projectCache.findIndex((x) => x.id === p.id);
    if (idx >= 0) projectCache[idx] = p;
    else projectCache.unshift(p);
    return p;
  } catch {
    try {
      localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
    return undefined;
  }
}

/** 把占位标签导航到检测配置页；无占位时窄屏同页跳，桌面则提示弹窗被拦 */
export function navigateDetectTab(
  win: Window | null,
  projectId: string,
  project?: DetectProject,
) {
  if (project && project.id === projectId) {
    seedDetectProjectForNewTab(project);
  }
  const path = detectPath(projectId);
  prepareAuthHandoff();
  if (win && !win.closed) {
    try {
      win.location.replace(path);
      win.focus();
      return;
    } catch {
      try {
        win.close();
      } catch {
        /* ignore */
      }
    }
  }
  if (isNarrowViewport()) {
    window.location.assign(path);
    return;
  }
  // 桌面：勿静默劫持当前因子库页（多开回测时尤其容易误伤）
  const abs = `${window.location.origin}${path}`;
  window.alert(
    `浏览器拦截了新标签页。请允许本站弹窗后重试，或复制打开：\n${abs}`,
  );
}

/** 打开检测配置页：窄屏同页跳转；桌面新标签（仅适合仍在用户手势内的同步调用） */
export function openDetectInNewTab(projectId: string) {
  const path = detectPath(projectId);
  prepareAuthHandoff();
  if (isNarrowViewport()) {
    window.location.assign(path);
    return;
  }
  const win = window.open(path, "_blank");
  if (!win) {
    const abs = `${window.location.origin}${path}`;
    window.alert(
      `浏览器拦截了新标签页。请允许本站弹窗后重试，或复制打开：\n${abs}`,
    );
  }
}

export function optionLabel(
  code: string,
  options: readonly { code: string; label: string }[],
): string {
  return options.find((o) => o.code === code)?.label ?? code;
}

export function migrateLegacyRunsOnBoot() {
  purgeLegacyBrowserDetectKeys();
}
