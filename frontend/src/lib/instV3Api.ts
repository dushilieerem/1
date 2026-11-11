import { instApi } from "./instApi";

export type V3Stage = {
  stage_no: number;
  stage_key: string;
  stage_name: string;
  gate: string;
  owner: string;
  count: number;
  total_count?: number;
  truncated?: boolean;
  items: V3PipelineItem[];
};

export type V3PipelineItem = {
  key: string;
  case_id?: number;
  company_id: number;
  symbol?: string;
  company_name?: string;
  industry?: string;
  stage_no: number;
  stage_key: string;
  stage_name: string;
  gate: string;
  source?: string;
  idea?: Record<string, unknown> | null;
  opportunity?: Record<string, unknown> | null;
  version_no?: number | null;
  version_status?: string | null;
  conclusion?: string | null;
  proposal_status?: string | null;
  owner_member_id?: number | null;
  updated_at?: string | null;
  stale?: boolean;
  ref_price?: number | null;
};

export type V3Pipeline = { stages: V3Stage[]; total: number; total_count?: number };

export type V3Stock = {
  id: number;
  symbol: string;
  name: string;
  market?: string;
  industry?: string | null;
  pool_status?: string | null;
  data_status?: string | null;
  ref_price?: number | null;
  last_close?: number | null;
  pe_ttm?: number | null;
  pb_mrq?: number | null;
};

export type V3Bar = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
};

export type V3Bars = {
  symbol: string;
  name: string;
  market?: string;
  period: string;
  available: boolean;
  note?: string;
  items: V3Bar[];
};

export type V3Result = {
  key: string;
  stage_no: number;
  stage_key: string;
  stage_name: string;
  stage_state?: string;
  stage_gate?: Record<string, unknown> | null;
  locks?: Record<string, unknown> | null;
  company?: Record<string, unknown>;
  idea?: Record<string, unknown>;
  opportunity?: Record<string, unknown>;
  latest_decision?: Record<string, unknown> | null;
  case?: Record<string, unknown>;
  latest_version?: Record<string, unknown>;
  latest_debate?: Record<string, unknown>;
  latest_proposal?: Record<string, unknown>;
  authorization?: Record<string, unknown> | null;
  position?: Record<string, unknown> | null;
};

export type V3Playbook = {
  stages: Array<{
    stage_no: number;
    stage_key: string;
    stage_name: string;
    gate: string;
    owner: string;
    steps: string[];
  }>;
  gates: Array<{ key: string; name: string; rule: string; actions: string[] }>;
  hard_constraints: string[];
  evidence_grades: Array<{ grade: string; source: string; rule: string }>;
  rules: string[];
};

export async function fetchV3Pipeline(): Promise<V3Pipeline> {
  return instApi<V3Pipeline>("/pipeline");
}

export async function fetchV3Project(key: string): Promise<V3Result> {
  return instApi<V3Result>(`/projects/${encodeURIComponent(key)}`);
}

export async function deleteV3Case(caseId: number): Promise<{ deleted: boolean; case_id: number }> {
  return instApi<{ deleted: boolean; case_id: number }>(`/cases/${caseId}`, { method: "DELETE" });
}

export async function startV3Research(companyId: number): Promise<{ id: number; created?: boolean }> {
  return instApi<{ id: number; created?: boolean }>(`/companies/${companyId}/research`, {
    method: "POST",
    body: {},
  });
}

export async function fetchV3Stocks(q = "", limit = 200): Promise<{ items: V3Stock[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (q.trim()) params.set("q", q.trim());
  return instApi<{ items: V3Stock[]; total: number }>(`/stocks?${params.toString()}`);
}

export async function fetchV3StockBars(
  companyId: number,
  period = "day",
  limit = 120,
): Promise<V3Bars> {
  return instApi<V3Bars>(`/stocks/${companyId}/bars?period=${encodeURIComponent(period)}&limit=${limit}`);
}

export async function fetchV3Playbook(): Promise<V3Playbook> {
  return instApi<V3Playbook>("/playbook");
}
