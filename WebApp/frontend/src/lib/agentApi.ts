import { authHeaders } from "@/lib/auth";

export type AgentStep = {
  status: string;
  tool: string;
  detail?: string;
  agent?: string;
  skill?: string | null;
  board_revision?: number;
};

export type AgentFlag = {
  code?: string;
  severity?: string;
  message?: string;
};

export type AgentRunResult = {
  ok: boolean;
  run_id: string;
  goal: string;
  mode?: string;
  crew?: string;
  status: string;
  steps: AgentStep[];
  agents_trace?: {
    agent: string;
    phase?: string;
    decision?: string;
    flags?: AgentFlag[];
    section?: string;
    ok?: boolean;
    revision?: number;
    suggestion?: { section?: string; label?: string; reason?: string };
  }[];
  board?: {
    revision?: number;
    flags?: AgentFlag[];
    votes?: { agent?: string; decision?: string; reason?: string }[];
    artifacts?: Record<string, unknown>;
    section?: string;
    summary_md?: string;
    source_post_id?: number | null;
    truncated?: boolean;
  };
  outputs: {
    title?: string;
    body?: string;
    section?: string;
    summary_md?: string;
    flags?: AgentFlag[];
  };
  usage: {
    tokens_in: number;
    tokens_out: number;
    skills: string[];
    provider?: string;
    quota_daily: number;
    used_today: number;
    remaining: number;
  };
  error?: string | null;
  ai_assisted?: boolean;
};

export type AgentUsageMe = {
  quota_daily: number;
  used_today: number;
  remaining: number;
  day: string;
  days?: number;
  totals?: {
    calls: number;
    runs: number;
    tokens_in: number;
    tokens_out: number;
  };
  by_day?: {
    day: string;
    calls: number;
    tokens_in: number;
    tokens_out: number;
  }[];
  by_skill?: { skill: string; calls: number; tokens_in: number; tokens_out: number }[];
  by_skill_today?: { skill: string; calls: number; tokens_in: number; tokens_out: number }[];
};

export type AgentUsageAdmin = {
  days: number;
  totals: {
    calls: number;
    tokens_in: number;
    tokens_out: number;
    users: number;
  };
  by_user: {
    user_id: number;
    username: string;
    display_name?: string | null;
    role?: string;
    quota_daily: number;
    used_today: number;
    remaining?: number;
    calls: number;
    tokens_in: number;
    tokens_out: number;
  }[];
  by_skill: {
    skill: string;
    calls: number;
    tokens_in: number;
    tokens_out: number;
  }[];
};

async function readJson<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new Error((data as { error?: string }).error || `HTTP ${res.status}`);
  }
  return data;
}

export async function runAgent(payload: {
  goal?: string;
  skills?: string[];
  mode?: "single" | "multi";
  crew?: string;
  context: {
    title?: string;
    body?: string;
    section?: string;
    code_snippet?: string;
    post_id?: number;
    with_risks?: boolean;
    platform_ref?: {
      source?: string;
      label?: string;
      factor_name?: string;
      universe?: string;
      period?: string;
      metrics_display?: Record<string, string>;
      metrics?: Record<string, number | null | undefined>;
    };
  };
}): Promise<AgentRunResult> {
  const res = await fetch("/api/agent/runs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  return readJson<AgentRunResult>(res);
}

export async function getMyAgentUsage(days = 7): Promise<AgentUsageMe> {
  const res = await fetch(`/api/agent/usage/me?days=${days}`, {
    headers: { ...authHeaders() },
  });
  return readJson<AgentUsageMe>(res);
}

export async function getAdminAgentUsage(days = 7): Promise<AgentUsageAdmin> {
  const res = await fetch(`/api/agent/usage?days=${days}`, {
    headers: { ...authHeaders() },
  });
  return readJson<AgentUsageAdmin>(res);
}

export async function setUserAgentQuota(userId: number, quotaDaily: number) {
  const res = await fetch("/api/agent/usage/quota", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ user_id: userId, quota_daily: quotaDaily }),
  });
  return readJson<{
    ok: boolean;
    user: {
      user_id: number;
      username: string;
      display_name?: string;
      quota_daily: number;
      used_today: number;
      remaining: number;
    };
  }>(res);
}
