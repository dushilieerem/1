import type { YgBacktestRequest, YgBacktestResponse } from "./ygApi";
import { authHeaders, assertAuthConsistency, getStoredUser, subscribeAuth, prepareAuthHandoff } from "./auth";
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

export type DetectProjectConfig = {
  factorCodes: string[];
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
  /** core=快速检测 | full=全量检测，对应 RE analysis_level */
  analysisLevel: AnalysisLevel;
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
  analysisLevel: AnalysisLevel;
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
    groups: cfg.groups || 5,
    rebalanceDays: cfg.rebalanceDays || 1,
    filterLimitUp: Boolean(cfg.filterLimitUp),
    filterSuspended: Boolean(cfg.filterSuspended),
    analysisLevel: cfg.analysisLevel === "full" ? "full" : "core",
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
    groups: Number(raw.groups) || 5,
    rebalanceDays: Number(raw.rebalanceDays) || 1,
    filterLimitUp: Boolean(raw.filterLimitUp),
    filterSuspended: Boolean(raw.filterSuspended),
    analysisLevel: raw.analysisLevel === "full" ? "full" : "core",
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
    groups: snap.groups,
    rebalanceDays: snap.rebalanceDays,
    filterLimitUp: snap.filterLimitUp,
    filterSuspended: snap.filterSuspended,
    analysisLevel: snap.analysisLevel,
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
    analysisLevel: "core",
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
  cfg.groups = Math.min(5, Math.max(1, Number(cfg.groups) || 5));
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
let cacheUserId: number | null = null;
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
  cacheUserId = currentUserId();
}

function ensureCacheOwner() {
  const uid = currentUserId();
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
    throw new Error((data as { error?: string }).error || `HTTP ${res.status}`);
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
    return hit;
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
    return hit;
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
  cfg.customCombine = `def combo_factor(self):\n    """单因子"""\n    return self.${factorName}()`;
  return cfg;
}

export async function openOrCreateForFactor(
  factorName: string,
  description: string,
): Promise<DetectProject> {
  ensureCacheOwner();
  const name = (factorName || "").trim();
  if (!name) throw new Error("因子名为空");
  const list = await listProjects();
  const existing = list.find((p) => p.factorName === name && !p.sample);
  if (existing) {
    // 修好旧「社区克隆→自定义组合、未选因子」的脏项目
    existing.config = singleFactorDetectConfig(name, existing.config);
    existing.description = description || existing.description;
    return saveProject(existing);
  }
  const created = await createProject(name, description);
  created.config = singleFactorDetectConfig(name, created.config);
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

/** 打开检测配置页：窄屏同页跳转（手机常拦弹窗）；桌面优先新标签 */
export function openDetectInNewTab(projectId: string) {
  const path = `/factor/detect/${encodeURIComponent(projectId)}`;
  prepareAuthHandoff();
  const narrow =
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 1023px)").matches;
  if (narrow) {
    window.location.assign(path);
    return;
  }
  const win = window.open(path, "_blank");
  if (!win) {
    window.location.assign(path);
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
