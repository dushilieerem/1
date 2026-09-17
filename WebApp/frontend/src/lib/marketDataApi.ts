/** 行情只读：经本机 /api 转发；日线走本机 BFF 缓存，列表类薄转发。 */

import { authHeaders } from "@/lib/auth";

export type MarketBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type MarketDaily = {
  symbol: string;
  name?: string | null;
  bars: MarketBar[];
  date_range: { start: string; end: string };
};

/** 按 date 去重合并，升序 */
export function mergeMarketBars(...lists: Array<MarketBar[] | undefined | null>): MarketBar[] {
  const map = new Map<string, MarketBar>();
  for (const list of lists) {
    if (!list?.length) continue;
    for (const b of list) {
      const d = String(b?.date || "").trim();
      if (!d) continue;
      map.set(d, b);
    }
  }
  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** 把分段日线并进已有结果（先近后远渐进用） */
export function mergeMarketDaily(
  base: MarketDaily | null | undefined,
  chunk: MarketDaily | null | undefined,
): MarketDaily | null {
  if (!chunk?.bars?.length && !base?.bars?.length) return base || chunk || null;
  if (!chunk?.bars?.length) return base || null;
  if (!base?.bars?.length) return chunk;
  const bars = mergeMarketBars(base.bars, chunk.bars);
  return {
    symbol: chunk.symbol || base.symbol,
    name: chunk.name || base.name,
    bars,
    date_range: {
      start: bars[0]?.date || base.date_range?.start || chunk.date_range?.start || "",
      end:
        bars[bars.length - 1]?.date ||
        base.date_range?.end ||
        chunk.date_range?.end ||
        "",
    },
  };
}

/**
 * 自然年区间：从近到远（含当年）。
 * 与近端窗口重叠无妨，merge 会去重。
 */
/** 按自然年从近往远：RE 日线库底约 2005-01-01，更早年多为空/404 */
export function yearlyRangesBack(opts?: {
  earliestYear?: number;
  from?: Date;
}): Array<{ start: string; end: string }> {
  const earliest = opts?.earliestYear ?? 2005;
  const now = opts?.from ?? new Date();
  const yNow = now.getFullYear();
  const out: Array<{ start: string; end: string }> = [];
  for (let y = yNow; y >= earliest; y--) {
    out.push({ start: `${y}-01-01`, end: `${y}-12-31` });
  }
  return out;
}

/** RE symbols 新结构：带交易所后缀 + 名称 */
export type MarketSymbol = {
  symbol: string;
  name: string;
};

export type SymbolQuote = {
  symbol: string;
  name: string | null;
  last: number | null;
  prev: number | null;
  change: number | null;
  changePct: number | null;
  asOf: string | null;
  rangeStart: string | null;
  rangeEnd: string | null;
};

function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function ymd(d: Date): string {
  return ymdLocal(d);
}

/** 会话内内存缓存：不落库，减少重复打 RE */
const _symbolsCache: { at: number; list: MarketSymbol[] } = { at: 0, list: [] };
const _dailyCache = new Map<string, { at: number; data: MarketDaily }>();
const SYMBOLS_TTL_MS = 30 * 60_000;
/** 会话内短缓存：离开再回同一标的可秒开；?fresh=1 / bypassCache 仍直打 */
const DAILY_CACHE_ENABLED = true;
const DAILY_TTL_MS = 5 * 60_000;
/** 浏览器持久缓存：隔天/关浏览器再进，先秒开再后台刷新 */
const LS_DAILY_PREFIX = "svq.mkt.daily.v1:";
const LS_DAILY_INDEX = "svq.mkt.daily.idx.v1";
/** 超过此时间仍可用来首屏，但会后台刷新 */
const LS_STALE_MS = 7 * 24 * 60 * 60_000;
const LS_MAX_SYMBOLS = 12;
/** RE 已发布日线的末日（本机「今天」可能比数据新） */
let _panelAsOf: string | null = null;

function dailyCacheKey(symbol: string, start?: string, end?: string): string {
  return `${symbol}|${start || ""}|${end || ""}`;
}

type LsDailyEntry = { at: number; data: MarketDaily };

function lsReadIndex(): string[] {
  try {
    const raw = localStorage.getItem(LS_DAILY_INDEX);
    if (!raw) return [];
    const arr = JSON.parse(raw) as unknown;
    return Array.isArray(arr) ? arr.map(String) : [];
  } catch {
    return [];
  }
}

function lsWriteIndex(syms: string[]) {
  try {
    localStorage.setItem(LS_DAILY_INDEX, JSON.stringify(syms.slice(0, LS_MAX_SYMBOLS)));
  } catch {
    /* quota */
  }
}

function persistDaily(symbol: string, data: MarketDaily) {
  if (!data?.bars?.length) return;
  const code = String(symbol || "").trim();
  if (!code) return;
  try {
    const entry: LsDailyEntry = { at: Date.now(), data };
    localStorage.setItem(LS_DAILY_PREFIX + code, JSON.stringify(entry));
    const idx = lsReadIndex().filter((s) => s !== code);
    idx.unshift(code);
    lsWriteIndex(idx);
    // 超限删最旧
    for (const old of idx.slice(LS_MAX_SYMBOLS)) {
      localStorage.removeItem(LS_DAILY_PREFIX + old);
    }
  } catch {
    /* private mode / quota */
  }
}

/** 同步读本地日线（可过期）；用于进页立刻出图 */
export function peekPersistedDaily(symbol: string): MarketDaily | null {
  const code = String(symbol || "").trim();
  if (!code) return null;
  try {
    const raw = localStorage.getItem(LS_DAILY_PREFIX + code);
    if (!raw) return null;
    const entry = JSON.parse(raw) as LsDailyEntry;
    if (!entry?.data?.bars?.length) return null;
    if (Date.now() - Number(entry.at || 0) > LS_STALE_MS) return null;
    return entry.data;
  } catch {
    return null;
  }
}

/** 去掉 .SH/.SZ/.BJ */
export function bareCode(symbol: string): string {
  return String(symbol || "")
    .trim()
    .replace(/\.(SH|SZ|BJ)$/i, "");
}

/** 展示用：优先「名称 代码」 */
export function formatSymbolLabel(
  symbol: string,
  name?: string | null,
): string {
  const code = String(symbol || "").trim();
  const n = (name || "").trim();
  return n ? `${n}` : code;
}

export function symbolMatchesQuery(
  item: MarketSymbol,
  query: string,
): boolean {
  const needle = query.trim().toUpperCase();
  if (!needle) return false;
  const sym = item.symbol.toUpperCase();
  const bare = bareCode(item.symbol).toUpperCase();
  const name = (item.name || "").toUpperCase();
  return (
    sym.includes(needle) ||
    bare.includes(needle) ||
    name.includes(needle)
  );
}

/** 近 N 个自然日（日历今天；仅作兜底，报价窗口请用 panelLookbackStart） */
export function recentStartDate(days = 40): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return ymd(d);
}

/** 相对 RE 数据末日往前 lookback，避免 start 落在无 bar 区间导致 404 */
export function panelLookbackStart(asOf: string, lookbackDays = 45): string {
  const d = new Date(asOf + "T12:00:00");
  if (Number.isNaN(d.getTime())) return recentStartDate(lookbackDays);
  d.setDate(d.getDate() - Math.max(5, lookbackDays));
  return ymdLocal(d);
}

async function resolvePanelAsOf(sampleSymbol: string): Promise<string> {
  if (_panelAsOf) return _panelAsOf;
  const daily = await fetchMarketDaily(sampleSymbol, { start: "2024-01-01" });
  const end =
    daily.date_range?.end ||
    (daily.bars.length ? daily.bars[daily.bars.length - 1].date : null);
  if (!end) throw new Error("无法解析市场数据末日");
  _panelAsOf = end;
  return end;
}

async function formatApiError(data: unknown, res: Response): Promise<string> {
  if (data && typeof data === "object") {
    const d = data as { detail?: unknown; error?: unknown; message?: unknown };
    if (d.detail != null) {
      if (typeof d.detail === "string") return d.detail;
      if (Array.isArray(d.detail)) {
        return d.detail
          .map((x) =>
            x && typeof x === "object" && "msg" in x
              ? String((x as { msg: unknown }).msg)
              : JSON.stringify(x),
          )
          .join("; ");
      }
      try {
        return JSON.stringify(d.detail);
      } catch {
        /* fall through */
      }
    }
    if (d.error != null) return String(d.error);
    if (d.message != null) return String(d.message);
  }
  const st = res.statusText?.trim();
  if (st && st.toLowerCase() !== "ok") return `${st}（HTTP ${res.status}）`;
  return `HTTP ${res.status}`;
}

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text ? { error: text.slice(0, 500) } : null;
  }
  if (!res.ok) {
    let msg = await formatApiError(data, res);
    if (res.status === 503 && /证券主数据|代码列|name/i.test(msg)) {
      msg = `ResearchEngine 行情暂不可用：证券主数据缺代码/名称列（请同事检查 RE 主数据）。原始：${msg}`;
    }
    throw new Error(msg);
  }
  return data as T;
}

function parseSymbolsPayload(raw: unknown): MarketSymbol[] {
  if (!Array.isArray(raw)) return [];
  const out: MarketSymbol[] = [];
  for (const item of raw) {
    if (typeof item === "string") {
      const s = item.trim();
      if (s) out.push({ symbol: s, name: "" });
      continue;
    }
    if (item && typeof item === "object") {
      const o = item as { symbol?: unknown; name?: unknown };
      const symbol = String(o.symbol ?? "").trim();
      if (!symbol) continue;
      out.push({ symbol, name: String(o.name ?? "").trim() });
    }
  }
  return out;
}

export async function fetchMarketSymbols(): Promise<MarketSymbol[]> {
  const now = Date.now();
  if (_symbolsCache.list.length && now - _symbolsCache.at < SYMBOLS_TTL_MS) {
    return _symbolsCache.list;
  }
  const res = await fetch("/api/market-data/symbols", {
    headers: { ...authHeaders() },
  });
  const data = await parseJson<{ symbols?: unknown; unmapped_count?: number }>(
    res,
  );
  const list = parseSymbolsPayload(data.symbols);
  _symbolsCache.at = now;
  _symbolsCache.list = list;
  return list;
}

export type MarketIndex = {
  code: string;
  name: string;
};

const _indicesCache: { at: number; list: MarketIndex[] } = { at: 0, list: [] };
const _constituentsCache = new Map<
  string,
  { at: number; list: MarketSymbol[] }
>();
const INDICES_TTL_MS = 30 * 60_000;
const CONSTITUENTS_TTL_MS = 30 * 60_000;

function parseIndicesPayload(raw: unknown): MarketIndex[] {
  if (!Array.isArray(raw)) return [];
  const out: MarketIndex[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as { code?: unknown; name?: unknown };
    const code = String(o.code ?? "").trim();
    if (!code) continue;
    out.push({ code, name: String(o.name ?? "").trim() || code });
  }
  return out;
}

/** 内置股指列表（RE docs: GET /api/market-data/indices） */
export async function fetchMarketIndices(): Promise<MarketIndex[]> {
  const now = Date.now();
  if (_indicesCache.list.length && now - _indicesCache.at < INDICES_TTL_MS) {
    return _indicesCache.list;
  }
  const res = await fetch("/api/market-data/indices", {
    headers: { ...authHeaders() },
  });
  const data = await parseJson<{ indices?: unknown }>(res);
  const list = parseIndicesPayload(data.indices);
  _indicesCache.at = now;
  _indicesCache.list = list;
  return list;
}

/** 股指最新一期成分（兼容 000300.SH / CSI300） */
export async function fetchIndexConstituents(
  code: string,
): Promise<MarketSymbol[]> {
  const key = String(code || "").trim();
  if (!key) throw new Error("缺少股指代码");
  const now = Date.now();
  const hit = _constituentsCache.get(key);
  if (hit && now - hit.at < CONSTITUENTS_TTL_MS) return hit.list;

  const res = await fetch(
    `/api/market-data/indices/${encodeURIComponent(key)}/constituents`,
    { headers: { ...authHeaders() } },
  );
  const data = await parseJson<{
    index?: { code?: string; name?: string };
    constituents?: unknown;
  }>(res);
  const list = parseSymbolsPayload(data.constituents);
  _constituentsCache.set(key, { at: now, list });
  return list;
}

/**
 * 拉取日线。文档推荐交易所后缀（如 000001.SZ）；六位裸码仍兼容。
 */
export async function fetchMarketDaily(
  symbol: string,
  opts?: { start?: string; end?: string; bypassCache?: boolean },
): Promise<MarketDaily> {
  const code = String(symbol || "").trim();
  if (!code) throw new Error("缺少股票代码");
  const key = dailyCacheKey(code, opts?.start, opts?.end);
  const now = Date.now();
  if (DAILY_CACHE_ENABLED && !opts?.bypassCache) {
    const hit = _dailyCache.get(key);
    if (hit && now - hit.at < DAILY_TTL_MS) return hit.data;
  }

  const q = new URLSearchParams();
  if (opts?.start) q.set("start", opts.start);
  if (opts?.end) q.set("end", opts.end);
  const qs = q.toString();
  const res = await fetch(
    `/api/market-data/daily/${encodeURIComponent(code)}${qs ? `?${qs}` : ""}`,
    { headers: { ...authHeaders() } },
  );
  const data = await parseJson<MarketDaily>(res);
  if (DAILY_CACHE_ENABLED) {
    _dailyCache.set(key, { at: now, data });
  }
  // 只把「更完整」的结果写入持久缓存（全历史优先；近端也能救急）
  const prev = peekPersistedDaily(code);
  if (!prev || (data.bars?.length || 0) >= (prev.bars?.length || 0)) {
    persistDaily(code, data);
  }
  return data;
}

/** 清日线内存缓存（调试首屏渐进加载用） */
export function clearMarketDailyCache() {
  _dailyCache.clear();
}

/** 清浏览器持久日线（?fresh=1） */
export function clearPersistedDailyCache(symbol?: string) {
  try {
    if (symbol) {
      const code = String(symbol).trim();
      localStorage.removeItem(LS_DAILY_PREFIX + code);
      lsWriteIndex(lsReadIndex().filter((s) => s !== code));
      return;
    }
    for (const s of lsReadIndex()) {
      localStorage.removeItem(LS_DAILY_PREFIX + s);
    }
    localStorage.removeItem(LS_DAILY_INDEX);
  } catch {
    /* ignore */
  }
}

export function quoteFromBars(
  symbol: string,
  daily: MarketDaily | null,
): SymbolQuote {
  const bars = daily?.bars || [];
  const name = (daily?.name || "").trim() || null;
  if (!bars.length) {
    return {
      symbol,
      name,
      last: null,
      prev: null,
      change: null,
      changePct: null,
      asOf: null,
      rangeStart: daily?.date_range?.start || null,
      rangeEnd: daily?.date_range?.end || null,
    };
  }
  const lastBar = bars[bars.length - 1];
  const prevBar = bars.length >= 2 ? bars[bars.length - 2] : null;
  const last = Number(lastBar.close);
  const prev = prevBar != null ? Number(prevBar.close) : null;
  const change = prev != null && Number.isFinite(prev) ? last - prev : null;
  const changePct =
    change != null && prev != null && Math.abs(prev) > 1e-12
      ? (change / prev) * 100
      : null;
  return {
    symbol: daily?.symbol || symbol,
    name,
    last: Number.isFinite(last) ? last : null,
    prev: prev != null && Number.isFinite(prev) ? prev : null,
    change: change != null && Number.isFinite(change) ? change : null,
    changePct:
      changePct != null && Number.isFinite(changePct) ? changePct : null,
    asOf: lastBar.date || null,
    rangeStart: daily?.date_range?.start || bars[0]?.date || null,
    rangeEnd: daily?.date_range?.end || lastBar.date || null,
  };
}

/** 有限并发拉取多只近端行情；近端无数据时回退全量末日收盘价 */
export async function fetchQuotesBatch(
  symbols: string[],
  opts?: { concurrency?: number; lookbackDays?: number },
): Promise<Record<string, SymbolQuote>> {
  const concurrency = Math.max(1, Math.min(12, opts?.concurrency ?? 8));
  const lookbackDays = opts?.lookbackDays ?? 45;
  const out: Record<string, SymbolQuote> = {};
  if (!symbols.length) return out;

  let start: string;
  let end: string | undefined;
  try {
    const asOf = await resolvePanelAsOf(symbols[0] || "000001.SZ");
    end = asOf;
    start = panelLookbackStart(asOf, lookbackDays);
  } catch {
    start = "2025-01-01";
    end = undefined;
  }

  async function quoteOne(sym: string): Promise<SymbolQuote> {
    try {
      const near = await fetchMarketDaily(sym, { start, end });
      if (near.bars?.length) {
        const tip =
          near.date_range?.end || near.bars[near.bars.length - 1]?.date || null;
        if (tip && (!_panelAsOf || tip > _panelAsOf)) _panelAsOf = tip;
        return quoteFromBars(sym, near);
      }
      // 近端明确无 bars（退市/无行情）：勿再打全历史
      return quoteFromBars(sym, near);
    } catch {
      // 近端请求失败才尝试全量末日
    }
    try {
      const full = await fetchMarketDaily(sym);
      return quoteFromBars(sym, full);
    } catch {
      return quoteFromBars(sym, null);
    }
  }

  let i = 0;
  async function worker() {
    while (i < symbols.length) {
      const idx = i++;
      const sym = symbols[idx];
      out[sym] = await quoteOne(sym);
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(concurrency, symbols.length) }, () =>
      worker(),
    ),
  );
  return out;
}

export function fmtPrice(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

/** A 股习惯：红涨绿跌 */
export function changeToneClass(changePct: number | null | undefined): string {
  if (changePct == null || !Number.isFinite(changePct) || changePct === 0) {
    return "text-slate-600";
  }
  return changePct > 0 ? "text-red-600" : "text-emerald-600";
}

export type OverviewStats = {
  last: number | null;
  change: number | null;
  changePct: number | null;
  asOf: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prevClose: number | null;
  rangeStart: string | null;
  rangeEnd: string | null;
  barCount: number;
  high52: number | null;
  low52: number | null;
  perf: Record<string, number | null>;
};

function closeOnOrBefore(bars: MarketBar[], target: string): number | null {
  for (let i = bars.length - 1; i >= 0; i--) {
    if (bars[i].date <= target) return Number(bars[i].close);
  }
  return null;
}

function shiftYmd(end: string, days: number): string {
  const d = new Date(end + "T12:00:00");
  d.setDate(d.getDate() + days);
  return ymdLocal(d);
}

export function computeOverviewStats(daily: MarketDaily): OverviewStats {
  const bars = daily.bars || [];
  const q = quoteFromBars(daily.symbol, daily);
  const lastBar = bars.length ? bars[bars.length - 1] : null;
  const end = q.asOf || daily.date_range?.end || null;

  let high52: number | null = null;
  let low52: number | null = null;
  if (end && bars.length) {
    const from = shiftYmd(end, -370);
    for (const b of bars) {
      if (b.date < from) continue;
      const h = Number(b.high);
      const l = Number(b.low);
      if (Number.isFinite(h)) high52 = high52 == null ? h : Math.max(high52, h);
      if (Number.isFinite(l)) low52 = low52 == null ? l : Math.min(low52, l);
    }
  }

  const windows: Record<string, number> = {
    "1D": 1,
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "1Y": 365,
  };
  const perf: Record<string, number | null> = {};
  if (end && q.last != null) {
    for (const [k, days] of Object.entries(windows)) {
      const base = closeOnOrBefore(bars, shiftYmd(end, -days));
      perf[k] =
        base != null && Math.abs(base) > 1e-12
          ? ((q.last - base) / base) * 100
          : null;
    }
    const y = end.slice(0, 4);
    const ytdBase = closeOnOrBefore(bars, `${y}-01-01`);
    let firstInYear: number | null = null;
    for (const b of bars) {
      if (b.date.startsWith(`${y}-`)) {
        firstInYear = Number(b.close);
        break;
      }
    }
    const y0 = firstInYear ?? ytdBase;
    perf.YTD =
      y0 != null && Math.abs(y0) > 1e-12 ? ((q.last - y0) / y0) * 100 : null;
  }

  return {
    last: q.last,
    change: q.change,
    changePct: q.changePct,
    asOf: q.asOf,
    open: lastBar ? Number(lastBar.open) : null,
    high: lastBar ? Number(lastBar.high) : null,
    low: lastBar ? Number(lastBar.low) : null,
    prevClose: q.prev,
    rangeStart: daily.date_range?.start || bars[0]?.date || null,
    rangeEnd: daily.date_range?.end || q.asOf,
    barCount: bars.length,
    high52,
    low52,
    perf,
  };
}
