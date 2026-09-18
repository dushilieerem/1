/** 用户自选股组合 API（按登录用户隔离） */

import { authHeaders, assertAuthConsistency } from "./auth";

export type Watchlist = {
  id: number;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  symbolCount?: number;
};

export type WatchlistSymbol = {
  id: number;
  watchlistId: number;
  symbol: string;
  name: string;
  createdAt?: string;
};

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  assertAuthConsistency();
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const text = await res.text();
  let data: T & { error?: string };
  try {
    data = JSON.parse(text) as T & { error?: string };
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}`);
  }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export async function listWatchlists(): Promise<Watchlist[]> {
  const data = await apiJson<{ watchlists: Watchlist[] }>("/api/watchlists");
  return data.watchlists || [];
}

export async function createWatchlist(name: string): Promise<Watchlist> {
  const data = await apiJson<{ watchlist: Watchlist }>("/api/watchlists", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  return data.watchlist;
}

export async function renameWatchlist(
  id: number,
  name: string,
): Promise<Watchlist> {
  const data = await apiJson<{ watchlist: Watchlist }>(`/api/watchlists/${id}`, {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
  return data.watchlist;
}

export async function deleteWatchlist(id: number): Promise<void> {
  await apiJson(`/api/watchlists/${id}`, { method: "DELETE" });
}

export async function listWatchlistSymbols(
  watchlistId: number,
): Promise<WatchlistSymbol[]> {
  const data = await apiJson<{ symbols: WatchlistSymbol[] }>(
    `/api/watchlists/${watchlistId}/symbols`,
  );
  return data.symbols || [];
}

export async function addWatchlistSymbol(
  watchlistId: number,
  symbol: string,
  name = "",
): Promise<WatchlistSymbol> {
  const data = await apiJson<{ symbol: WatchlistSymbol }>(
    `/api/watchlists/${watchlistId}/symbols`,
    {
      method: "POST",
      body: JSON.stringify({ symbol, name }),
    },
  );
  return data.symbol;
}

export async function addWatchlistSymbolsBatch(
  watchlistId: number,
  items: { symbol: string; name?: string }[],
): Promise<{ added: number; skipped: number; symbols: WatchlistSymbol[] }> {
  return apiJson(`/api/watchlists/${watchlistId}/symbols/batch`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export async function deleteWatchlistSymbol(
  watchlistId: number,
  symbol: string,
): Promise<void> {
  await apiJson(
    `/api/watchlists/${watchlistId}/symbols/${encodeURIComponent(symbol)}`,
    { method: "DELETE" },
  );
}
