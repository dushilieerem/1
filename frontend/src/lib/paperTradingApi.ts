/** 模拟盘账户与日终结算 API（按登录用户隔离）。 */

import { authHeaders, assertAuthConsistency } from "./auth";

export type PaperAccountStatus = "active" | "paused" | "closed" | "blocked";
export type PaperEngineMode = "event" | "vectorized";

export type PaperAccount = {
  id: number;
  userId: number;
  name: string;
  projectId: string;
  projectName: string;
  engineMode: PaperEngineMode;
  strategyId?: string | null;
  codeHash: string;
  configRevision: number;
  universe: string;
  benchmark: string;
  commissionRate: number;
  minCommission: number;
  stampTax: number;
  slippageRate: number;
  lotSize: number;
  filterSt: boolean;
  initialCash: number;
  cash: number;
  totalEquity: number;
  positionsValue: number;
  firstSettlementDate: string;
  nextSettlementDate: string;
  lastSettledDate: string | null;
  status: PaperAccountStatus;
  lastErrorCode?: string | null;
  lastErrorMessage?: string | null;
  retryCount: number;
  nextRetryAt?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type PaperPosition = {
  symbol: string;
  quantity: number;
  availableQuantity: number;
  averageCost: number;
  markPrice?: number | null;
  marketValue?: number | null;
  updatedAt?: string;
};

export type PaperOrder = {
  orderId: string;
  settlementDate: string;
  symbol: string;
  side?: string | null;
  quantity?: number | null;
  targetValue?: number | null;
  status: string;
  reasonCode?: string | null;
  submittedAt?: string | null;
};

export type PaperFill = {
  orderId: string;
  settlementDate: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  commission: number;
  stampTax: number;
  filledAt?: string | null;
};

export type PaperEquityPoint = {
  date: string;
  cash: number;
  positionsValue: number;
  totalEquity: number;
  dailyReturn?: number | null;
};

export type PaperSettlementPosition = {
  symbol: string;
  quantity: number;
  availableQuantity: number;
  averageCost: number;
  markPrice?: number | null;
  marketValue?: number | null;
};

export type PaperSettlement = {
  id: number;
  settlementDate: string;
  signalDate: string;
  status: "applied" | "rolled_back";
  engineMode: PaperEngineMode;
  configRevision: number;
  dataReleaseId?: string | null;
  dataReleaseSignature?: string | null;
  codeHash: string;
  stateHash?: string | null;
  cashBefore: number;
  cashAfter: number;
  positionsValue: number;
  totalEquity: number;
  commission: number;
  stampTax: number;
  warnings: string[];
  nextAccount?: {
    cash: number;
    positionsValue: number;
    totalEquity: number;
    positions: PaperSettlementPosition[];
  } | null;
  createdAt: string;
  rolledBackAt?: string | null;
};

export type PaperAttempt = {
  id: number;
  settlementDate: string;
  attemptNo: number;
  trigger: string;
  httpStatus?: number | null;
  errorCode?: string | null;
  errorMessage?: string | null;
  dataReleaseId?: string | null;
  status: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationMs?: number | null;
};

export type PaperReStatus = {
  status?: string;
  settlement_date?: string | null;
  latest_ready_trading_day?: string | null;
  signal_date?: string | null;
  next_trading_day?: string | null;
  data_release_id?: string | null;
  data_version?: string | null;
  release_stale?: boolean;
  error?: string;
  message?: string;
};

export type PaperSchedulerState = {
  enabled: boolean;
  activeAccounts: number;
  maxCatchupDays: number;
  settleTimeoutSec: number;
  retryBackoffSec: number;
};

export type PaperStatus = {
  ok: boolean;
  scheduler: PaperSchedulerState;
  schedulerLastResult?: Record<string, unknown> | null;
  re: PaperReStatus;
};

export type PaperSettleResult = {
  ok: boolean;
  settled: boolean;
  idempotent?: boolean;
  skipped?: string;
  settlement?: PaperSettlement;
  account?: PaperAccount;
  results?: PaperSettleResult[];
  latestReadyDate?: string;
  status?: PaperReStatus;
};

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
  let data: T & {
    error?: string;
    detail?: string | { message?: string; code?: string };
    code?: string;
  };
  try {
    data = JSON.parse(text) as typeof data;
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}`);
  }
  if (!res.ok) {
    const detail =
      typeof data.detail === "string" ? data.detail : data.detail?.message;
    const code =
      data.code ||
      (typeof data.detail === "object" ? data.detail?.code : undefined);
    const message = data.error || detail || `HTTP ${res.status}`;
    throw new Error(code ? `${code}: ${message}` : message);
  }
  return data;
}

export async function listPaperAccounts(): Promise<PaperAccount[]> {
  const data = await apiJson<{ accounts: PaperAccount[] }>("/api/paper/accounts");
  return data.accounts || [];
}

export async function createPaperAccount(input: {
  name: string;
  strategy_project_id: string;
  initial_cash: number;
  first_settlement_date?: string;
}): Promise<PaperAccount> {
  const data = await apiJson<{ account: PaperAccount }>("/api/paper/accounts", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data.account;
}

export async function getPaperAccount(
  id: number,
): Promise<{ account: PaperAccount; positions: PaperPosition[] }> {
  return apiJson<{ account: PaperAccount; positions: PaperPosition[] }>(
    `/api/paper/accounts/${id}`,
  );
}

export async function updatePaperAccount(
  id: number,
  patch: { name?: string; status?: PaperAccountStatus },
): Promise<PaperAccount> {
  const data = await apiJson<{ account: PaperAccount }>(
    `/api/paper/accounts/${id}/status`,
    { method: "POST", body: JSON.stringify(patch) },
  );
  return data.account;
}

export async function listPaperPositions(id: number): Promise<PaperPosition[]> {
  const data = await apiJson<{ positions: PaperPosition[] }>(
    `/api/paper/accounts/${id}/positions`,
  );
  return data.positions || [];
}

export async function listPaperOrders(
  id: number,
  opts: { limit?: number; offset?: number; start?: string; end?: string } = {},
): Promise<{ orders: PaperOrder[]; total: number }> {
  const qs = new URLSearchParams();
  if (opts.limit != null) qs.set("limit", String(opts.limit));
  if (opts.offset != null) qs.set("offset", String(opts.offset));
  if (opts.start) qs.set("start", opts.start);
  if (opts.end) qs.set("end", opts.end);
  const suffix = qs.toString() ? `?${qs}` : "";
  const data = await apiJson<{ orders: PaperOrder[]; total: number }>(
    `/api/paper/accounts/${id}/orders${suffix}`,
  );
  return { orders: data.orders || [], total: data.total || 0 };
}

export async function listPaperFills(
  id: number,
  opts: { limit?: number; offset?: number; start?: string; end?: string } = {},
): Promise<{ fills: PaperFill[]; total: number }> {
  const qs = new URLSearchParams();
  if (opts.limit != null) qs.set("limit", String(opts.limit));
  if (opts.offset != null) qs.set("offset", String(opts.offset));
  if (opts.start) qs.set("start", opts.start);
  if (opts.end) qs.set("end", opts.end);
  const suffix = qs.toString() ? `?${qs}` : "";
  const data = await apiJson<{ fills: PaperFill[]; total: number }>(
    `/api/paper/accounts/${id}/fills${suffix}`,
  );
  return { fills: data.fills || [], total: data.total || 0 };
}

export async function listPaperEquity(
  id: number,
  opts: { start?: string; end?: string } = {},
): Promise<PaperEquityPoint[]> {
  const qs = new URLSearchParams();
  if (opts.start) qs.set("start", opts.start);
  if (opts.end) qs.set("end", opts.end);
  const suffix = qs.toString() ? `?${qs}` : "";
  const data = await apiJson<{ equity: PaperEquityPoint[] }>(
    `/api/paper/accounts/${id}/equity${suffix}`,
  );
  return data.equity || [];
}

export async function listPaperSettlements(
  id: number,
  opts: { limit?: number; offset?: number } = {},
): Promise<{ settlements: PaperSettlement[]; total: number }> {
  const qs = new URLSearchParams();
  if (opts.limit != null) qs.set("limit", String(opts.limit));
  if (opts.offset != null) qs.set("offset", String(opts.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  const data = await apiJson<{ settlements: PaperSettlement[]; total: number }>(
    `/api/paper/accounts/${id}/settlements${suffix}`,
  );
  return { settlements: data.settlements || [], total: data.total || 0 };
}

export async function listPaperAttempts(id: number): Promise<PaperAttempt[]> {
  const data = await apiJson<{ attempts: PaperAttempt[] }>(
    `/api/paper/accounts/${id}/settlement-attempts`,
  );
  return data.attempts || [];
}

export async function getPaperStatus(): Promise<PaperStatus> {
  return apiJson<PaperStatus>("/api/paper/status");
}

export async function settlePaperAccount(
  id: number,
  date?: string,
): Promise<PaperSettleResult> {
  return apiJson<PaperSettleResult>(`/api/paper/accounts/${id}/settle`, {
    method: "POST",
    body: JSON.stringify(date ? { date } : {}),
  });
}

export async function replayPaperAccount(id: number): Promise<unknown> {
  return apiJson(`/api/paper/accounts/${id}/replay`, { method: "POST", body: "{}" });
}

export async function syncPaperStrategy(id: number): Promise<unknown> {
  return apiJson(`/api/paper/accounts/${id}/sync-strategy`, {
    method: "POST",
    body: "{}",
  });
}
