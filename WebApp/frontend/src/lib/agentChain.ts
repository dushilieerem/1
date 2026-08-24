import { authHeaders } from "@/lib/auth";
import type { IdeaItem } from "./ideaApi";
import { getStoredUser } from "./auth";

export type FactorDraft = {
  factor_name: string;
  factor_code: string;
  description: string;
  formula_nl?: string;
  used_fields: string[];
  assumptions?: string[];
  warnings?: string[];
};

export type BacktestHint = {
  factor_name: string;
  factor_code: string;
  universe: string;
  start: string;
  end: string;
  oos_split?: string;
  portfolio_type?: string;
  rebalance_days?: number;
  groups?: number;
  benchmark?: string;
  analysis_level?: string;
};

export type FactorDraftBundle = {
  ok: boolean;
  draft_id: string;
  idea_id?: string;
  pack_id?: string;
  bundle_id?: string;
  factor: FactorDraft;
  backtest_hint: BacktestHint;
  warnings?: string[];
  stats?: Record<string, unknown>;
  error?: string;
};

export type BacktestReport = {
  ok: boolean;
  report_id: string;
  draft_id?: string;
  request?: BacktestHint;
  metrics?: Record<string, unknown>;
  error?: string | null;
  date_range?: unknown;
  warnings?: string[];
  stats?: Record<string, unknown>;
};

export type EvalResult = {
  ok: boolean;
  eval_id: string;
  verdict: string;
  admit: boolean;
  note: string;
  reasons: string[];
  warnings?: string[];
};

function uid(): string {
  const u = getStoredUser();
  return u?.id != null ? String(u.id) : "anon";
}

const ideaKey = () => `svquant.chain.idea.v1.u${uid()}`;
const draftKey = () => `svquant.chain.draft.v1.u${uid()}`;
const reportKey = () => `svquant.chain.report.v1.u${uid()}`;

export function saveChainIdea(idea: IdeaItem, meta?: { pack_id?: string; bundle_id?: string }) {
  sessionStorage.setItem(ideaKey(), JSON.stringify({ idea, ...meta }));
}

export function loadChainIdea(): {
  idea: IdeaItem;
  pack_id?: string;
  bundle_id?: string;
} | null {
  try {
    const raw = sessionStorage.getItem(ideaKey());
    if (!raw) return null;
    const o = JSON.parse(raw);
    return o?.idea ? o : null;
  } catch {
    return null;
  }
}

export function saveChainDraft(draft: FactorDraftBundle) {
  sessionStorage.setItem(draftKey(), JSON.stringify(draft));
}

export function loadChainDraft(): FactorDraftBundle | null {
  try {
    const raw = sessionStorage.getItem(draftKey());
    if (!raw) return null;
    return JSON.parse(raw) as FactorDraftBundle;
  } catch {
    return null;
  }
}

export function saveChainReport(report: BacktestReport) {
  sessionStorage.setItem(reportKey(), JSON.stringify(report));
}

export function loadChainReport(): BacktestReport | null {
  try {
    const raw = sessionStorage.getItem(reportKey());
    if (!raw) return null;
    return JSON.parse(raw) as BacktestReport;
  } catch {
    return null;
  }
}

async function postJson<T extends { ok?: boolean; error?: string }>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  const data = (await res.json().catch(() => ({}))) as T;
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `请求失败 HTTP ${res.status}`);
  }
  return data;
}

export function runFactorDraft(
  body: {
    idea: IdeaItem;
    pack_id?: string;
    bundle_id?: string;
    prompt?: string;
  },
  signal?: AbortSignal,
) {
  return postJson<FactorDraftBundle>("/api/agent/factor", body, signal);
}

export function runFactorBacktest(
  body: { backtest_hint: BacktestHint; factor?: FactorDraft; draft_id?: string },
  signal?: AbortSignal,
) {
  return postJson<BacktestReport>("/api/agent/factor-backtest", body, signal);
}

export function runFactorEval(body: { report: BacktestReport }, signal?: AbortSignal) {
  return postJson<EvalResult>("/api/agent/factor-eval", body, signal);
}
