import type { YgBacktestResponse, YgStrategyBacktestRequest } from "./ygApi";
import {
  authHeaders,
  assertAuthConsistency,
  getStoredUser,
  prepareAuthHandoff,
  subscribeAuth,
} from "./auth";
import {
  DETECT_BENCHMARK_OPTIONS,
  DETECT_PERIOD_OPTIONS,
  DETECT_UNIVERSE_OPTIONS,
  RE_MARKET_END,
  clampDateRange,
  defaultCustomRangeDates,
  periodToStartEnd,
  type RangeMode,
} from "./detectStore";
import { DEFAULT_STRATEGY_CODE, wrapFactorCodeAsStrategy } from "./strategyCodeSync";

export type StrategyProjectConfig = {
  universe: string;
  benchmark: string;
  rangeMode: RangeMode;
  backtestPeriod: string;
  startDate: string;
  endDate: string;
  commission_rate: number;
  stamp_tax: number;
  slippage_rate: number;
  initial_capital: number;
  top_n: number;
  rebalance_days: number;
  /** 回测请求：是否拉取 rebalance_logs */
  include_rebalance_logs: boolean;
  strategy_code: string;
};

export type StrategyProject = {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  runCount: number;
  config: StrategyProjectConfig;
};

export type StrategyRunRecord = {
  id: string;
  projectId: string;
  name: string;
  description: string;
  request: YgStrategyBacktestRequest;
  result: YgBacktestResponse;
  finishedAt: string;
  elapsedSec: number;
};

export const STRATEGY_UNIVERSE_OPTIONS = DETECT_UNIVERSE_OPTIONS;
export const STRATEGY_BENCHMARK_OPTIONS = DETECT_BENCHMARK_OPTIONS;
export const STRATEGY_PERIOD_OPTIONS = DETECT_PERIOD_OPTIONS;
export { RE_MARKET_END, periodToStartEnd, clampDateRange, defaultCustomRangeDates };

export function optionLabel(
  code: string,
  options: readonly { code: string; label: string }[],
): string {
  return options.find((o) => o.code === code)?.label || code || "—";
}

export function defaultStrategyConfig(): StrategyProjectConfig {
  const custom = defaultCustomRangeDates("10y");
  return {
    universe: "CSI500",
    benchmark: "CSI300",
    rangeMode: "period",
    backtestPeriod: "10y",
    startDate: custom.startDate,
    endDate: custom.endDate,
    commission_rate: 0.0003,
    stamp_tax: 0.001,
    slippage_rate: 0.001,
    initial_capital: 1_000_000,
    top_n: 30,
    rebalance_days: 20,
    include_rebalance_logs: true,
    strategy_code: DEFAULT_STRATEGY_CODE,
  };
}

/** 兼容旧项目缺字段 */
export function normalizeStrategyConfig(
  raw?: Partial<StrategyProjectConfig> | null,
): StrategyProjectConfig {
  const d = defaultStrategyConfig();
  const c = raw || {};
  return {
    universe: c.universe || d.universe,
    benchmark: c.benchmark || d.benchmark,
    rangeMode: c.rangeMode === "custom" ? "custom" : "period",
    backtestPeriod: c.backtestPeriod || d.backtestPeriod,
    startDate: c.startDate || d.startDate,
    endDate: c.endDate || d.endDate,
    commission_rate:
      typeof c.commission_rate === "number" ? c.commission_rate : d.commission_rate,
    stamp_tax: typeof c.stamp_tax === "number" ? c.stamp_tax : d.stamp_tax,
    slippage_rate:
      typeof c.slippage_rate === "number" ? c.slippage_rate : d.slippage_rate,
    initial_capital:
      typeof c.initial_capital === "number" ? c.initial_capital : d.initial_capital,
    top_n: typeof c.top_n === "number" && c.top_n > 0 ? c.top_n : d.top_n,
    rebalance_days:
      typeof c.rebalance_days === "number" && c.rebalance_days > 0
        ? c.rebalance_days
        : d.rebalance_days,
    include_rebalance_logs:
      typeof c.include_rebalance_logs === "boolean"
        ? c.include_rebalance_logs
        : d.include_rebalance_logs,
    strategy_code: (c.strategy_code || "").trim()
      ? String(c.strategy_code)
      : d.strategy_code,
  };
}

export function resolveStrategyRange(cfg: StrategyProjectConfig): {
  start: string | null;
  end: string | null;
} {
  if (cfg.rangeMode === "custom") {
    return {
      start: cfg.startDate || null,
      end: cfg.endDate || null,
    };
  }
  const r = periodToStartEnd(cfg.backtestPeriod || "10y");
  return { start: r.start, end: r.end };
}

let projectCache: StrategyProject[] | null = null;

export function clearStrategyClientCache() {
  projectCache = null;
}

subscribeAuth(() => {
  clearStrategyClientCache();
});

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  assertAuthConsistency();
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const text = await res.text();
  let data: T & { error?: string };
  try {
    data = JSON.parse(text) as T & { error?: string };
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}`);
  }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export async function listStrategyProjects(opts?: {
  visible?: boolean;
}): Promise<StrategyProject[]> {
  const q = opts?.visible ? "?visible=1" : "";
  const data = await apiJson<{ projects: StrategyProject[] }>(
    `/api/strategy/projects${q}`,
  );
  projectCache = data.projects || [];
  return projectCache;
}

export async function listVisibleStrategyProjects(): Promise<StrategyProject[]> {
  // 恢复：列表展示全部项目（含尚未回测的新建 / 社区克隆）
  return listStrategyProjects();
}

export async function getStrategyProject(id: string): Promise<StrategyProject> {
  const data = await apiJson<{ project: StrategyProject }>(
    `/api/strategy/projects/${encodeURIComponent(id)}`,
  );
  return data.project;
}

export async function createStrategyProject(
  name: string,
  description?: string,
): Promise<StrategyProject> {
  const data = await apiJson<{ project: StrategyProject }>("/api/strategy/projects", {
    method: "POST",
    body: JSON.stringify({ name, description: description || name }),
  });
  clearStrategyClientCache();
  return data.project;
}

/** 从社区帖代码新建策略项目并写入可回测 strategy_code */
export async function createStrategyProjectFromCode(opts: {
  name: string;
  description?: string;
  strategyCode: string;
}): Promise<StrategyProject> {
  const { resolveStrategyCloneSource } = await import("./communityClone");
  const raw = await resolveStrategyCloneSource(opts.strategyCode || "");
  const code = wrapFactorCodeAsStrategy(raw);
  const project = await createStrategyProject(
    opts.name,
    opts.description || opts.name,
  );
  return saveStrategyProject({
    ...project,
    config: {
      ...project.config,
      strategy_code: code,
    },
  });
}

/** 社区克隆草稿：未回测前不落库 */
export const STRATEGY_DRAFT_ID = "draft";
const STRATEGY_CLONE_DRAFT_KEY = "svquant_strategy_clone_draft";

export type StrategyCloneDraft = {
  name: string;
  description?: string;
  strategy_code: string;
};

export function stashStrategyCloneDraft(draft: StrategyCloneDraft) {
  sessionStorage.setItem(STRATEGY_CLONE_DRAFT_KEY, JSON.stringify(draft));
}

export function peekStrategyCloneDraft(): StrategyCloneDraft | null {
  try {
    const raw = sessionStorage.getItem(STRATEGY_CLONE_DRAFT_KEY);
    if (!raw) return null;
    const d = JSON.parse(raw) as StrategyCloneDraft;
    if (!d?.strategy_code?.trim() || !d?.name?.trim()) return null;
    return d;
  } catch {
    return null;
  }
}

export function clearStrategyCloneDraft() {
  sessionStorage.removeItem(STRATEGY_CLONE_DRAFT_KEY);
}

/** 打开策略配置草稿页（新标签）；首次回测/保存时才创建项目 */
export function openStrategyDraftInNewTab(draft: StrategyCloneDraft) {
  stashStrategyCloneDraft(draft);
  prepareAuthHandoff();
  const win = window.open(`/strategy/research/${STRATEGY_DRAFT_ID}`, "_blank");
  if (!win) {
    window.alert(
      "浏览器拦截了新标签页。请允许本站弹出窗口后再试。当前页面不会跳转。",
    );
  }
}

export async function saveStrategyProject(
  project: StrategyProject,
): Promise<StrategyProject> {
  const data = await apiJson<{ project: StrategyProject }>(
    `/api/strategy/projects/${encodeURIComponent(project.id)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        id: project.id,
        name: project.name,
        description: project.description,
        config: project.config,
      }),
    },
  );
  clearStrategyClientCache();
  return data.project;
}

export async function deleteStrategyProject(id: string): Promise<void> {
  await apiJson(`/api/strategy/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  clearStrategyClientCache();
}

export async function listStrategyRuns(
  projectId: string,
): Promise<StrategyRunRecord[]> {
  const data = await apiJson<{ runs: StrategyRunRecord[] }>(
    `/api/strategy/projects/${encodeURIComponent(projectId)}/runs`,
  );
  return data.runs || [];
}

export async function getStrategyRun(runId: string): Promise<StrategyRunRecord> {
  const data = await apiJson<{ run: StrategyRunRecord }>(
    `/api/strategy/runs/${encodeURIComponent(runId)}`,
  );
  return data.run;
}

export async function saveStrategyRun(payload: {
  projectId: string;
  name?: string;
  description?: string;
  request: YgStrategyBacktestRequest;
  result: YgBacktestResponse;
  elapsedSec: number;
}): Promise<StrategyRunRecord> {
  const data = await apiJson<{ run: StrategyRunRecord }>("/api/strategy/runs", {
    method: "POST",
    body: JSON.stringify({
      projectId: payload.projectId,
      name: payload.name,
      description: payload.description,
      request: payload.request,
      result: payload.result,
      elapsedSec: payload.elapsedSec,
    }),
  });
  clearStrategyClientCache();
  return data.run;
}

export async function deleteStrategyRun(runId: string): Promise<void> {
  await apiJson(`/api/strategy/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}

export function openStrategyInNewTab(projectId: string) {
  const path = `/strategy/research/${encodeURIComponent(projectId)}`;
  prepareAuthHandoff();
  const win = window.open(path, "_blank");
  if (!win) {
    window.alert(
      "浏览器拦截了新标签页。请允许本站弹出窗口后再试。当前页面不会跳转。",
    );
  }
}

export function requireStrategyUser() {
  if (!getStoredUser()) throw new Error("未登录");
}
