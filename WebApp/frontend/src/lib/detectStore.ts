import type { YgBacktestRequest, YgBacktestResponse } from "./ygApi";
import { authHeaders, assertAuthConsistency, getStoredUser, subscribeAuth } from "./auth";

export type WeightMode = "sum" | "product" | "custom";
export type RangeMode = "period" | "custom";
export type AnalysisLevel = "core" | "full";

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
  /** core=核心检测 | full=全量检测，对应 RE analysis_level */
  analysisLevel: AnalysisLevel;
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
};

export const DETECT_UNIVERSE_OPTIONS = [
  { code: "CSI300", label: "沪深300" },
  { code: "CSI500", label: "中证500" },
  { code: "CSI1000", label: "中证1000" },
  { code: "SSE50", label: "上证50" },
  { code: "CSI_ALL", label: "中证全指" },
] as const;

export const DETECT_BENCHMARK_OPTIONS = [
  { code: "CSI300", label: "沪深300" },
  { code: "SSE50", label: "上证50" },
  { code: "CSI500", label: "中证500" },
  { code: "CSI1000", label: "中证1000" },
] as const;

export const DETECT_PERIOD_OPTIONS = [
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
  { code: "core" as const, label: "核心检测" },
  { code: "full" as const, label: "全量检测" },
] as const;

export const RE_MARKET_END = "2026-01-01";

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

/** 预设周期 → start/end（end 固定为 RE 行情截止日） */
export function resolveBacktestRange(cfg: DetectProjectConfig): { start: string; end: string } {
  if (cfg.rangeMode === "custom") {
    return { start: cfg.startDate, end: cfg.endDate };
  }
  return periodToStartEnd(cfg.backtestPeriod || "3y");
}

/** 自定义因子试算等：仅用 period 字符串 */
export function periodToStartEnd(period: string): { start: string; end: string } {
  const end = parseYmd(RE_MARKET_END);
  const start = new Date(end);
  const p = period || "3y";
  if (p === "1d") start.setDate(start.getDate() - 1);
  else if (p === "5d") start.setDate(start.getDate() - 5);
  else if (p === "10d") start.setDate(start.getDate() - 10);
  else if (p === "1m") start.setMonth(start.getMonth() - 1);
  else if (p === "6m") start.setMonth(start.getMonth() - 6);
  else if (p === "3m") start.setMonth(start.getMonth() - 3);
  else if (p === "1y") start.setFullYear(start.getFullYear() - 1);
  else start.setFullYear(start.getFullYear() - 3);
  return { start: fmtDate(start), end: fmtDate(end) };
}

export const PORTFOLIO_TYPE_OPTIONS = [
  {
    code: "long_short",
    label: "多空 long_short",
    hint: "做多最高分组、做空最低分组，衡量因子多空收益。",
  },
  {
    code: "long_only",
    label: "纯多 long_only",
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
    portfolioType: "long_short",
    rangeMode: "period",
    backtestPeriod: "3y",
    startDate: "2022-01-01",
    endDate: "2024-12-31",
    universe: "CSI300",
    benchmark: "CSI300",
    groups: 5,
    rebalanceDays: 20,
    filterLimitUp: true,
    filterSuspended: true,
    analysisLevel: "core",
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
  if (!cfg.backtestPeriod) cfg.backtestPeriod = "3y";
  if (cfg.analysisLevel !== "core" && cfg.analysisLevel !== "full") {
    cfg.analysisLevel = "core";
  }
  cfg.groups = Math.min(5, Math.max(1, Number(cfg.groups) || 5));
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
  const data = await apiJson<{
    projects: DetectProject[];
    user_id?: number;
    username?: string;
  }>("/api/detect/projects?visible=1");
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
  const data = await apiJson<{ project: DetectProject }>("/api/detect/projects", {
    method: "POST",
    body: JSON.stringify({
      factorName,
      description,
      name: displayName || description || factorName,
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

export async function openOrCreateForFactor(
  factorName: string,
  description: string,
): Promise<DetectProject> {
  ensureCacheOwner();
  const list = await listProjects();
  const existing = list.find((p) => p.factorName === factorName && !p.sample);
  if (existing) return existing;
  return createProject(factorName, description);
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
