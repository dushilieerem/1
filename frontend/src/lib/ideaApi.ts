import { authHeaders } from "@/lib/auth";
import type { EvidencePack } from "./gatherApi";

export type IdeaPreference = {
  focus?: "theme" | "factor" | "risk" | "mixed";
  horizon?: "short" | "medium";
  note?: string;
};

export type IdeaItem = {
  id: string;
  title: string;
  thesis: string;
  citation_ids: string[];
  suggested_next: string;
  risk_notes: string[];
  confidence: "low" | "mid" | "high";
  convertible?: boolean;
  factor_prompt?: string;
  factor_spec?: {
    universe?: string;
    frequency?: string;
    used_fields?: string[];
    preferred_factor_name?: string;
    direction?: string;
  };
  validity?: {
    regime?: string;
    suggested_start?: string;
    suggested_end?: string;
    why_window?: string;
    oos_split?: string;
    decay_notes?: string;
  };
};

export type IdeaBundle = {
  ok: boolean;
  bundle_id: string;
  pack_id: string;
  ideas: IdeaItem[];
  gaps: string[];
  warnings?: string[];
  stats?: {
    elapsed_ms?: number;
    tokens_in?: number;
    tokens_out?: number;
    llm_model?: string;
    idea_mode?: string;
    returned?: number;
    max_ideas?: number;
    run_id?: string;
    preference?: IdeaPreference;
  };
  error?: string;
};

export type IdeaRequestBody = {
  pack: EvidencePack;
  preference?: IdeaPreference;
  max_ideas?: number;
};

export async function runIdea(
  body: IdeaRequestBody,
  signal?: AbortSignal,
): Promise<IdeaBundle> {
  const res = await fetch("/api/agent/idea", {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(body),
    signal,
  });
  const data = (await res.json().catch(() => ({}))) as IdeaBundle & {
    error?: string;
  };
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `研究假设生成失败 HTTP ${res.status}`);
  }
  return data;
}
