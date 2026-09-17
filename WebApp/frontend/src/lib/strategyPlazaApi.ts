import { authHeaders } from "@/lib/auth";

export type PlazaCurvePoint = {
  date: string;
  value: number;
  drawdown?: number;
};

export type PlazaSnapshot = {
  metrics?: Record<string, number | null | undefined>;
  excess_return?: number | null;
  equity_curve?: PlazaCurvePoint[];
  benchmark_curve?: PlazaCurvePoint[];
  date_range?: { start?: string; end?: string } | null;
  universe?: string | null;
  benchmark?: string | null;
  universe_label?: string | null;
  benchmark_label?: string | null;
  strategy_code?: string | null;
  range_label?: string | null;
  engine_mode?: "vectorized" | "event" | string | null;
};

export type PlazaItem = {
  id: number;
  title: string;
  body: string;
  source_run_id?: string | null;
  snapshot: PlazaSnapshot;
  view_count: number;
  status: string;
  created_at: string | null;
  updated_at?: string | null;
  author: {
    id?: number | null;
    username?: string;
    display_name?: string;
    avatar_url?: string | null;
  };
};

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: T & { error?: string; detail?: string };
  try {
    data = JSON.parse(text) as T & { error?: string; detail?: string };
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}`);
  }
  if (!res.ok) {
    throw new Error(data.error || data.detail || `HTTP ${res.status}`);
  }
  return data;
}

export async function listStrategyPlaza(opts?: {
  limit?: number;
  offset?: number;
  q?: string;
  sort?: string;
  universe?: string;
}): Promise<{ items: PlazaItem[]; total: number }> {
  const q = new URLSearchParams();
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  if (opts?.q) q.set("q", opts.q);
  if (opts?.sort) q.set("sort", opts.sort);
  if (opts?.universe) q.set("universe", opts.universe);
  const qs = q.toString();
  const res = await fetch(`/api/strategy/plaza${qs ? `?${qs}` : ""}`);
  return parseJson(res);
}

const _viewBumped = new Set<number>();

export async function getStrategyPlazaItem(id: number): Promise<PlazaItem> {
  // 同页 StrictMode 会双挂载；进程内只 bump 一次
  const bump = _viewBumped.has(id) ? 0 : 1;
  _viewBumped.add(id);
  const res = await fetch(`/api/strategy/plaza/${id}?bump=${bump}`);
  const data = await parseJson<{ item: PlazaItem }>(res);
  return data.item;
}

export async function createStrategyPlazaItem(body: {
  title: string;
  body: string;
  snapshot: PlazaSnapshot;
  source_run_id?: string;
}): Promise<PlazaItem> {
  const res = await fetch("/api/strategy/plaza", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await parseJson<{ item: PlazaItem }>(res);
  return data.item;
}

export async function hideStrategyPlazaItem(id: number): Promise<void> {
  const res = await fetch(`/api/strategy/plaza/${id}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  await parseJson(res);
}

/** 净值序列 → 累计收益 %（相对首点）；按日期排序避免横轴乱序 */
export function curveToCumPct(points?: PlazaCurvePoint[] | null): {
  dates: string[];
  values: number[];
} {
  const pts = (points || [])
    .filter(
      (p) => p?.date && typeof p.value === "number" && Number.isFinite(p.value),
    )
    .slice()
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  if (!pts.length) return { dates: [], values: [] };
  const base = pts[0].value || 1;
  return {
    dates: pts.map((p) => p.date),
    values: pts.map((p) => ((p.value / base) - 1) * 100),
  };
}
