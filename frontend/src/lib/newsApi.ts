export type NewsItem = {
  id: number;
  title: string;
  summary: string;
  body?: string;
  publishedAt: string;
  source: string;
  sourceLabel: string;
  category: string;
  url: string;
  symbols: string[];
  themes: string[];
  industries?: string[];
  isFlash: boolean;
  isFeatured: boolean;
};

export type ListNewsParams = {
  category?: string;
  source?: string;
  q?: string;
  mode?: "feed" | "flash" | "announce" | string;
  theme?: string | string[];
  symbol?: string | string[];
  industry?: string | string[];
  limit?: number;
  offset?: number;
};

function appendTags(sp: URLSearchParams, key: string, raw?: string | string[]) {
  if (!raw) return;
  const arr = Array.isArray(raw) ? raw : [raw];
  for (const t of arr) {
    const s = t.trim();
    if (s) sp.append(key, s);
  }
}

export async function listNews(params: ListNewsParams = {}) {
  const sp = new URLSearchParams();
  if (params.category && params.category !== "all") sp.set("category", params.category);
  if (params.source && params.source !== "all") sp.set("source", params.source);
  if (params.q?.trim()) sp.set("q", params.q.trim());
  if (params.mode && params.mode !== "feed") sp.set("mode", params.mode);
  appendTags(sp, "theme", params.theme);
  appendTags(sp, "symbol", params.symbol);
  appendTags(sp, "industry", params.industry);
  if (params.limit != null) sp.set("limit", String(params.limit));
  if (params.offset != null) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const res = await fetch(`/api/news${qs ? `?${qs}` : ""}`);
  const data = (await res.json()) as {
    ok?: boolean;
    total?: number;
    items?: NewsItem[];
    error?: string;
  };
  if (!res.ok) {
    throw new Error(data.error || `资讯列表失败 (${res.status})`);
  }
  return {
    total: data.total || 0,
    items: data.items || [],
  };
}

export type NewsDict = {
  themes: string[];
  industries: string[];
};

export async function fetchNewsDict(): Promise<NewsDict> {
  const res = await fetch("/api/news/dict");
  const data = (await res.json()) as {
    ok?: boolean;
    themes?: string[];
    industries?: string[];
    error?: string;
  };
  if (!res.ok) {
    throw new Error(data.error || `资讯字典失败 (${res.status})`);
  }
  return {
    themes: data.themes || [],
    industries: data.industries || [],
  };
}

export async function getNews(id: number | string) {
  const res = await fetch(`/api/news/${encodeURIComponent(String(id))}`);
  const data = (await res.json()) as { ok?: boolean; item?: NewsItem; error?: string };
  if (!res.ok) {
    throw new Error(data.error || `资讯详情失败 (${res.status})`);
  }
  if (!data.item) throw new Error("资讯不存在");
  return data.item;
}

export type NewsIngestResult = {
  ok: boolean;
  fetched: number;
  upserted: number;
  sources?: Record<
    string,
    { ok: boolean; count: number; label?: string; error?: string }
  >;
  errors?: Record<string, string> | null;
  note?: string;
  error?: string;
};

/** 拉取真源入库（东财 / 华尔街见闻 / 同花顺 / 财联社 / 巨潮） */
export async function ingestNews(params: {
  sources?: string[];
  limit?: number;
} = {}) {
  const res = await fetch("/api/news/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sources: params.sources,
      limit: params.limit ?? 12,
    }),
  });
  const data = (await res.json()) as NewsIngestResult;
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `资讯拉取失败 (${res.status})`);
  }
  return data;
}

/** 详情页补抓正文（东财等） */
export async function enrichNewsBody(id: number | string) {
  const res = await fetch(`/api/news/${encodeURIComponent(String(id))}/enrich`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  const data = (await res.json()) as {
    ok?: boolean;
    enriched?: boolean;
    message?: string;
    error?: string;
  };
  if (!res.ok) {
    throw new Error(data.error || `正文补抓失败 (${res.status})`);
  }
  return data;
}

/** 展示用时分（本地） */
export function formatNewsTime(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

/** 列表用：今天只显示 HH:mm；跨天显示 MM-DD HH:mm；仅日期（00:00）显示 MM-DD */
export function formatNewsWhen(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const timeOnly =
    d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0;
  if (timeOnly) return `${m}-${day}`;

  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const hm = formatNewsTime(iso);
  return sameDay ? hm : `${m}-${day} ${hm}`;
}

/** 公告表等：完整日期 + 可选时分 */
export function formatNewsDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  if (d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0) {
    return `${y}-${m}-${day}`;
  }
  return `${y}-${m}-${day} ${formatNewsTime(iso)}`;
}
