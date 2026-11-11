import { researchFetch as fetch } from "./researchClient";
import { authHeaders, assertAuthConsistency } from "./researchClient";

/** 聚宽策略直跑：预检、异步提交、状态查询、能力清单。 */

export type JoinquantIssue = {
  code: string;
  severity: "blocker" | "degraded" | "info" | string;
  impact?: string;
  line?: number | null;
  title: string;
  why?: string;
  effect?: string;
  evidence?: string;
};

export type JoinquantPrecheck = {
  ok: boolean;
  dialect: "joinquant";
  engine: string | null;
  code_hash: string;
  chars: number;
  issues: JoinquantIssue[];
  blocker_count: number;
  can_run_directly: boolean;
  verdict: string;
  capabilities_version?: string | null;
};

export type JoinquantRunStatus = {
  run_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  cancel_requested?: boolean;
  error?: string | null;
  error_code?: string | null;
  unsupported_api?: string | null;
  result?: {
    meta?: { run_id?: string; code_hash?: string; data_release_id?: string; engine_mode?: string };
    assumptions?: Record<string, unknown> | null;
    error?: string | null;
    error_code?: string | null;
    unsupported_api?: string | null;
    [key: string]: unknown;
  } | null;
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
  let data: (T & { error?: string }) | null = null;
  try {
    data = JSON.parse(text) as T & { error?: string };
  } catch {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    throw new Error("响应不是 JSON");
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const message =
      (data && data.error) ||
      (typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${res.status}`);
    throw new Error(message);
  }
  return data as T;
}

export async function precheckJoinquant(code: string): Promise<JoinquantPrecheck> {
  return apiJson<JoinquantPrecheck>("/api/strategy/precheck", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export type JoinquantRunPayload = {
  code: string;
  start: string;
  end: string;
  universe?: string;
  benchmark?: string;
  initial_capital?: number;
  commission_rate?: number;
  stamp_tax?: number;
  min_commission?: number;
  slippage_rate?: number;
  extra_symbols?: string[];
};

export async function submitJoinquantRun(
  payload: JoinquantRunPayload,
): Promise<{ run_id: string; status: string; code_hash: string; poll_url?: string | null }> {
  return apiJson("/api/strategy/joinquant/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getJoinquantRun(runId: string): Promise<JoinquantRunStatus> {
  return apiJson<JoinquantRunStatus>(
    `/api/strategy/joinquant/runs/${encodeURIComponent(runId)}`,
  );
}

export async function cancelJoinquantRun(runId: string): Promise<JoinquantRunStatus> {
  return apiJson<JoinquantRunStatus>(
    `/api/strategy/joinquant/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  );
}

export async function getStrategyCapabilities(): Promise<Record<string, unknown> | null> {
  const data = await apiJson<{ capabilities: Record<string, unknown> | null }>(
    "/api/strategy/capabilities",
  ).catch(() => ({ capabilities: null }));
  return data.capabilities;
}
