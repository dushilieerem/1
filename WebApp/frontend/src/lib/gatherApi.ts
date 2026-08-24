import { authHeaders } from "@/lib/auth";

export type GatherSources = {
  news?: boolean;
  report?: boolean;
  paper?: boolean;
  post?: boolean;
  sv_news?: boolean;
  web_public?: boolean;
};

export type GatherRequestBody = {
  topic: string;
  themes?: string[];
  symbols?: string[];
  time_window?: { preset?: string; start?: string; end?: string };
  sources?: GatherSources;
  max_items?: number;
  prefer_flash?: boolean;
  use_llm?: boolean;
};

export type EvidenceItem = {
  id: string;
  source_type: string;
  title: string;
  snippet: string;
  published_at: string;
  url?: string | null;
  sv_news_id?: number | null;
  source_label?: string;
  category?: string;
  themes?: string[];
  symbols?: string[];
  relevance?: number;
};

export type EvidencePack = {
  ok: boolean;
  pack_id: string;
  query?: Record<string, unknown>;
  items: EvidenceItem[];
  digest: string;
  digest_bullets: { text: string; item_ids: string[] }[];
  citations: { id: string; label: string; url?: string | null }[];
  gaps: string[];
  warnings?: string[];
  stats?: {
    retrieved?: number;
    after_dedupe?: number;
    returned?: number;
    elapsed_ms?: number;
    digest_mode?: string;
    tokens_in?: number;
    tokens_out?: number;
    llm_model?: string;
    run_id?: string;
    source_counts?: Record<string, number>;
  };
  error?: string;
};

export async function runGather(
  body: GatherRequestBody,
  signal?: AbortSignal,
): Promise<EvidencePack> {
  const res = await fetch("/api/agent/gather", {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(body),
    signal,
  });
  const data = (await res.json().catch(() => ({}))) as EvidencePack & {
    error?: string;
  };
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `搜集失败 HTTP ${res.status}`);
  }
  return data;
}
