import { authHeaders } from "@/lib/auth";

export type AiAgent = {
  task_id: string;
  agent_key: string;
  name: string;
  group: string;
  description: string;
  auto_run: boolean;
  editable: boolean;
  source: "institution" | "platform" | "skill" | string;
  prompt_version: string;
  override: boolean;
  prompt: string | null;
  default_prompt: string | null;
};

export type AiAgentList = {
  items: AiAgent[];
  count: number;
  editable_count: number;
  can_edit: boolean;
};

export type AiAgentPromptHistory = {
  id: number;
  version_no: number;
  action: string;
  prompt: string;
  status: string;
  note?: string | null;
  updated_by?: number | null;
  created_at?: string;
};

async function readJson<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(String((data as { detail?: string })?.detail || `HTTP ${res.status}`));
  }
  return data as T;
}

export async function listAiAgents(): Promise<AiAgentList> {
  const res = await fetch("/api/agent/agents", { headers: authHeaders() });
  return readJson<AiAgentList>(res);
}

export async function getAiAgent(taskId: string): Promise<AiAgent> {
  const res = await fetch(`/api/agent/agents/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(),
  });
  return readJson<AiAgent>(res);
}

export async function saveAiAgentPrompt(
  taskId: string,
  prompt: string,
  note?: string,
): Promise<{ version: number; agent: AiAgent }> {
  const res = await fetch(`/api/agent/agents/${encodeURIComponent(taskId)}/prompt`, {
    method: "PUT",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, note: note || null }),
  });
  return readJson<{ version: number; agent: AiAgent }>(res);
}

export async function resetAiAgentPrompt(taskId: string): Promise<{ version: number; agent: AiAgent }> {
  const res = await fetch(`/api/agent/agents/${encodeURIComponent(taskId)}/prompt/reset`, {
    method: "POST",
    headers: authHeaders(),
  });
  return readJson<{ version: number; agent: AiAgent }>(res);
}

export async function getAiAgentPromptHistory(taskId: string): Promise<AiAgentPromptHistory[]> {
  const res = await fetch(`/api/agent/agents/${encodeURIComponent(taskId)}/prompt/history`, {
    headers: authHeaders(),
  });
  const data = await readJson<{ items: AiAgentPromptHistory[] }>(res);
  return data.items || [];
}
