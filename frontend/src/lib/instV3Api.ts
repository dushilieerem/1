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

export async function fetchV3Playbook(): Promise<V3Playbook> {
  return instApi<V3Playbook>("/playbook");
}
