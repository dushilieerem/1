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
  };
  outputs: {
    title?: string;
    body?: string;
    section?: string;
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
  by_skill?: { skill: string; calls: number; tokens_in: number; tokens_out: number }[];
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

export async function getMyAgentUsage(): Promise<AgentUsageMe> {
  const res = await fetch("/api/agent/usage/me", {
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
