import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowUpRight,
  Building2,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Flame,
  Newspaper,
  Search,
  Sparkles,
  Tag,
  Zap,
} from "lucide-react";
import { NEWS_CATEGORIES, NEWS_SOURCES } from "@/data/nav";
import {
  formatNewsDate,
  formatNewsWhen,
  fetchNewsDict,
  listNews,
  type NewsItem,
} from "@/lib/newsApi";
import { PageJump } from "@/components/PageJump";

type ViewMode = "feed" | "flash" | "announce";

const PAGE_SIZE = 20;
const NEWS_UI_KEY = "svquant.news.ui.v3";

type NewsUiState = {
  cat: string;
  source: string;
  q: string;
  mode: ViewMode;
  page: number;
  themes: string[];
  symbols: string[];
  industries: string[];
};

function asTagList(v: unknown): string[] {
  if (Array.isArray(v)) {
    return v.map(String).map((s) => s.trim()).filter(Boolean).slice(0, 8);
  }
  if (typeof v === "string" && v.trim()) return [v.trim()];
  return [];
}

function loadNewsUi(): Partial<NewsUiState> {
  try {
    const raw = sessionStorage.getItem(NEWS_UI_KEY);
    if (!raw) {
      // 兼容 v2 单选
      const legacy = sessionStorage.getItem("svquant.news.ui.v2");
      if (!legacy) return {};
      const old = JSON.parse(legacy) as Record<string, unknown>;
      return {
        cat: typeof old.cat === "string" ? old.cat : undefined,
        source: typeof old.source === "string" ? old.source : undefined,
        q: typeof old.q === "string" ? old.q : undefined,
        mode: old.mode as ViewMode | undefined,
        page: typeof old.page === "number" ? old.page : undefined,
        themes: asTagList(old.theme),
        symbols: asTagList(old.symbol),
        industries: asTagList(old.industry),
      };
    }
    const parsed = JSON.parse(raw) as Partial<NewsUiState> & {
      theme?: string;
      symbol?: string;
      industry?: string;
    };
    return {
      ...parsed,
      themes: asTagList(parsed.themes ?? parsed.theme),
      symbols: asTagList(parsed.symbols ?? parsed.symbol),
      industries: asTagList(parsed.industries ?? parsed.industry),
    };
  } catch {
    return {};
  }
}

function toggleTag(list: string[], name: string, max = 8): string[] {
  if (list.includes(name)) return list.filter((x) => x !== name);
  return [...list, name].slice(0, max);
}

const INDICES = [
  { name: "上证", value: "3,412.6", chg: "+0.86%", up: true },
  { name: "深成", value: "10,892.1", chg: "+1.42%", up: true },
  { name: "创业板", value: "2,268.4", chg: "+4.92%", up: true },
  { name: "科创50", value: "1,615.2", chg: "+3.80%", up: true },
  { name: "沪深300", value: "3,892.1", chg: "+1.15%", up: true },
  { name: "中证1000", value: "5,640.8", chg: "+2.05%", up: true },
  { name: "恒生", value: "20,148.0", chg: "-0.35%", up: false },
  { name: "纳指", value: "21,420.3", chg: "+2.10%", up: true },
];

const HOT_THEMES = [
  { name: "CPO", chg: "+6.8%", reason: "光模块量产叙事升温" },
  { name: "CRO", chg: "+4.2%", reason: "龙头上调业绩指引" },
  { name: "AI应用", chg: "+3.1%", reason: "美股映射 + 国产降本" },
  { name: "电子特气", chg: "+4.4%", reason: "存储耗材预期" },
  { name: "人形机器人", chg: "+1.6%", reason: "订单兑现预期" },
];

/** 投资日历：目前为页面静态样例，未接真源日历接口 */
const CALENDAR = [
  { when: "今日", title: "FMS 闪存峰会召开（至 6 日）" },
  { when: "明日", title: "宇树科技科创板初步询价" },
  { when: "08-07", title: "Grok 4.6 预计发布" },
  { when: "08-13", title: "中芯国际披露二季报" },
];

const SOURCE_DOT: Record<string, string> = {
  cls: "bg-rose-500",
  eastmoney: "bg-orange-500",
  cninfo: "bg-sky-600",
  "10jqka": "bg-red-600",
  wallstreetcn: "bg-amber-500",
  bloomberg: "bg-slate-800",
};

function catLabel(id: string) {
  return NEWS_CATEGORIES.find((c) => c.id === id)?.label || id;
}

/**
 * 资讯 Hub：列表来自 GET /api/news（Postgres news_items）。
 */
export function NewsPage() {
  const [searchParams] = useSearchParams();
  const qFromUrl = (searchParams.get("q") || "").trim();
  const saved = loadNewsUi();
  const [cat, setCat] = useState(saved.cat || "all");
  const [source, setSource] = useState(saved.source || "all");
  const [q, setQ] = useState(qFromUrl || saved.q || "");
  const [qDebounced, setQDebounced] = useState((qFromUrl || saved.q || "").trim());
  const [themes, setThemes] = useState<string[]>(() => asTagList(saved.themes));
  const [symbols, setSymbols] = useState<string[]>(() => asTagList(saved.symbols));
  const [industries, setIndustries] = useState<string[]>(() =>
    asTagList(saved.industries),
  );
  const [dictThemes, setDictThemes] = useState<string[]>([]);
  const [dictIndustries, setDictIndustries] = useState<string[]>([]);
  const [mode, setMode] = useState<ViewMode>(
    saved.mode === "flash" || saved.mode === "announce" || saved.mode === "feed"
      ? saved.mode
      : "feed",
  );
  const [items, setItems] = useState<NewsItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [page, setPage] = useState(
    typeof saved.page === "number" && saved.page > 0 ? saved.page : 1,
  );

  useEffect(() => {
    let cancelled = false;
    void fetchNewsDict()
      .then((d) => {
        if (cancelled) return;
        setDictThemes(d.themes);
        setDictIndustries(d.industries);
      })
      .catch(() => {
        /* 字典可选 */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 全局搜索「在资讯查看全部」带入 ?q=
  useEffect(() => {
    if (!qFromUrl) return;
    setQ(qFromUrl);
    setQDebounced(qFromUrl);
    setPage(1);
  }, [qFromUrl]);

  useEffect(() => {
    const t = window.setTimeout(() => setQDebounced(q.trim()), 280);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    try {
      const payload: NewsUiState = {
        cat,
        source,
        q,
        mode,
        page,
        themes,
        symbols,
        industries,
      };
      sessionStorage.setItem(NEWS_UI_KEY, JSON.stringify(payload));
    } catch {
      /* ignore */
    }
  }, [cat, source, q, mode, page, themes, symbols, industries]);

  // 筛选变化回到第一页（跳过首次挂载，避免冲掉 session 页码）
  const skipPageReset = useRef(true);
  useEffect(() => {
    if (skipPageReset.current) {
      skipPageReset.current = false;
      return;
    }
    setPage(1);
  }, [cat, source, qDebounced, mode, themes, symbols, industries]);

  useEffect(() => {
    if (mode === "announce" && cat !== "all" && cat !== "announce") {
      setCat("announce");
    } else if (
      mode === "flash" &&
      (cat === "announce" || cat === "research" || cat === "policy")
    ) {
      setCat("all");
    }
  }, [mode, cat]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void listNews({
      category: cat,
      source,
      q: qDebounced,
      mode,
      theme: themes.length ? themes : undefined,
      symbol: symbols.length ? symbols : undefined,
      industry: industries.length ? industries : undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cat, source, qDebounced, mode, themes, symbols, industries, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const featured = useMemo(() => {
    const f = items.filter((x) => x.isFeatured).slice(0, 2);
    if (f.length >= 2) return f;
    return items.slice(0, 2);
  }, [items]);

  /** 本页题材词云：来自当前列表，点击按题材筛 */
  const themeCloud = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      for (const t of it.themes || []) {
        const name = t.trim();
        if (!name || name.length > 16) continue;
        counts.set(name, (counts.get(name) || 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([name, n]) => ({ name, n }));
  }, [items]);

  const industryCloud = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      for (const t of it.industries || []) {
        const name = t.trim();
        if (!name || name.length > 16) continue;
        counts.set(name, (counts.get(name) || 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, n]) => ({ name, n }));
  }, [items]);

  const hotSymbols = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      for (const s of it.symbols || []) {
        counts.set(s, (counts.get(s) || 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([sym]) => sym);
  }, [items]);

  const hasTagFilter =
    themes.length > 0 || symbols.length > 0 || industries.length > 0;

  const toggleTheme = (name: string) => {
    setThemes((prev) => toggleTag(prev, name));
  };
  const toggleSymbol = (code: string) => {
    setSymbols((prev) => toggleTag(prev, code));
  };
  const toggleIndustry = (name: string) => {
    setIndustries((prev) => toggleTag(prev, name));
  };
  const clearTagFilters = () => {
    setThemes([]);
    setSymbols([]);
    setIndustries([]);
  };

  return (
    <div className="relative min-h-[calc(100vh-4rem)] overflow-x-hidden bg-[#f6f4f1]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-[radial-gradient(ellipse_at_top,_rgba(185,28,28,0.08),_transparent_55%),linear-gradient(180deg,#fff_0%,#f6f4f1_70%)]"
      />

      <div className="relative border-b border-slate-200/80 bg-slate-950 text-white">
        <div className="mx-auto flex max-w-[1440px] items-center gap-4 overflow-x-auto px-4 py-2.5 text-[12px] sm:px-6 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <span className="shrink-0 text-[10px] font-medium tracking-wide text-slate-500">
            指数 · 演示
          </span>
          {INDICES.map((ix) => (
            <div key={ix.name} className="flex shrink-0 items-baseline gap-2">
              <span className="text-slate-400">{ix.name}</span>
              <span className="font-semibold tabular-nums tracking-tight">{ix.value}</span>
              <span className={`tabular-nums ${ix.up ? "text-rose-400" : "text-emerald-400"}`}>
                {ix.chg}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="relative mx-auto max-w-[1560px] px-4 pb-10 pt-5 sm:px-6 sm:pb-12 sm:pt-6">
        <div className="mb-3 sm:mb-4">
          <div className="mb-1 inline-flex items-center gap-2 rounded-full border border-rose-200/80 bg-white/80 px-3 py-1 text-[11px] font-semibold tracking-wide text-rose-700 shadow-sm backdrop-blur">
            <Newspaper className="h-3.5 w-3.5" />
            NEWS HUB
          </div>
          <h1 className="font-news text-2xl font-semibold tracking-tight text-slate-900 lg:text-3xl xl:text-4xl">
            资讯
          </h1>
        </div>

        {hasTagFilter ? (
          <div className="mb-4 flex flex-wrap items-center gap-2 text-[12px]">
            <span className="text-slate-500">标签筛选（可多选）</span>
            {themes.map((t) => (
              <button
                key={`t-${t}`}
                type="button"
                onClick={() => toggleTheme(t)}
                className="rounded-full bg-rose-100 px-2.5 py-1 font-medium text-rose-800 ring-1 ring-rose-200"
              >
                题材 · {t} ×
              </button>
            ))}
            {industries.map((ind) => (
              <button
                key={`i-${ind}`}
                type="button"
                onClick={() => toggleIndustry(ind)}
                className="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-900 ring-1 ring-amber-200"
              >
                行业 · {ind} ×
              </button>
            ))}
            {symbols.map((sym) => (
              <button
                key={`s-${sym}`}
                type="button"
                onClick={() => toggleSymbol(sym)}
                className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-800 ring-1 ring-slate-200"
              >
                代码 · {sym} ×
              </button>
            ))}
            <button
              type="button"
              onClick={clearTagFilters}
              className="text-slate-400 underline-offset-2 hover:text-rose-600 hover:underline"
            >
              清除
            </button>
          </div>
        ) : null}

        {featured.length > 0 ? (
          <div className="mb-3 grid gap-3 lg:mb-4 lg:grid-cols-2 lg:gap-4">
            {featured.map((it, i) => (
              <Link
                key={it.id}
                to={`/news/${it.id}`}
                className={`group relative overflow-hidden rounded-3xl border p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
                  i === 0
                    ? "border-rose-200/80 bg-gradient-to-br from-rose-50 via-white to-amber-50"
                    : "border-slate-200/80 bg-white"
                }`}
              >
                <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px]">
                  <span
                    className={`rounded-full px-2 py-0.5 font-semibold ${
                      i === 0 ? "bg-rose-100 text-rose-800" : "bg-rose-50 text-rose-700"
                    }`}
                  >
                    {it.sourceLabel}
                  </span>
                  <span className="text-slate-500">{formatNewsWhen(it.publishedAt)}</span>
                  <span className="text-slate-300">·</span>
                  <span className="text-slate-500">{catLabel(it.category)}</span>
                </div>
                <h2 className="font-news text-lg font-semibold leading-snug tracking-tight text-slate-900">
                  {it.title}
                </h2>
                <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-slate-600">
                  {it.summary}
                </p>
                <div className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-rose-700 opacity-80 group-hover:opacity-100">
                  阅读全文 <ArrowUpRight className="h-3.5 w-3.5" />
                </div>
              </Link>
            ))}
          </div>
        ) : null}

        <div className="mb-3 flex w-full items-center gap-2 rounded-2xl border border-slate-200/90 bg-white px-3.5 py-2 shadow-sm sm:mb-4 sm:max-w-md sm:px-4 sm:py-2.5">
          <Search className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜标题、代码、题材、摘要…"
            className="w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-slate-400"
          />
        </div>

        <div className="mb-3 flex flex-col gap-2 sm:mb-4 lg:flex-row lg:items-center lg:justify-between lg:gap-3">
          <div className="inline-flex max-w-full gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1 shadow-sm [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden lg:overflow-visible">
            {(
              [
                { id: "feed", label: "要闻流", icon: Sparkles },
                { id: "flash", label: "电报快讯", icon: Zap },
                { id: "announce", label: "公告表", icon: Building2 },
              ] as const
            ).map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setMode(m.id)}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition sm:px-3.5 ${
                  mode === m.id
                    ? "bg-slate-900 text-white shadow"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <m.icon className="h-3.5 w-3.5" />
                {m.label}
              </button>
            ))}
          </div>
          <div className="flex gap-1 overflow-x-auto pb-1 lg:pb-0 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {(mode === "announce"
              ? NEWS_CATEGORIES.filter((c) => c.id === "all" || c.id === "announce")
              : mode === "flash"
                ? NEWS_CATEGORIES.filter(
                    (c) =>
                      c.id === "all" ||
                      c.id === "flash" ||
                      c.id === "market" ||
                      c.id === "global",
                  )
                : NEWS_CATEGORIES
            ).map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCat(c.id)}
                className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                  cat === c.id
                    ? "bg-rose-600 text-white shadow-sm shadow-rose-200"
                    : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-rose-200"
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {/* 窄屏：来源横滑（桌面仍用左侧栏） */}
        <div className="mb-3 flex gap-1.5 overflow-x-auto pb-0.5 lg:hidden [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <button
            type="button"
            onClick={() => setSource("all")}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${
              source === "all"
                ? "bg-rose-600 text-white"
                : "bg-white text-slate-600 ring-1 ring-slate-200"
            }`}
          >
            全部来源
          </button>
          {NEWS_SOURCES.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSource(s.id)}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition ${
                source === s.id
                  ? "bg-rose-600 text-white"
                  : "bg-white text-slate-600 ring-1 ring-slate-200"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${SOURCE_DOT[s.id]}`} />
              {s.label}
            </button>
          ))}
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-[240px_minmax(0,1fr)_300px]">
          <aside className="hidden space-y-4 lg:sticky lg:top-24 lg:block lg:self-start">
            <div className="rounded-3xl border border-slate-200/90 bg-white/90 p-4 shadow-sm backdrop-blur">
              <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                Sources
              </div>
              <button
                type="button"
                onClick={() => setSource("all")}
                className={`mb-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm transition ${
                  source === "all"
                    ? "bg-rose-50 font-semibold text-rose-700"
                    : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                <span className="h-2 w-2 rounded-full bg-slate-300" />
                全部来源
              </button>
              {NEWS_SOURCES.map((s) => (
                <div key={s.id} className="group mb-0.5 flex items-center gap-0.5">
                  <button
                    type="button"
                    onClick={() => setSource(s.id)}
                    className={`flex min-w-0 flex-1 items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm transition ${
                      source === s.id
                        ? "bg-rose-50 font-semibold text-rose-700"
                        : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <span className={`h-2 w-2 shrink-0 rounded-full ${SOURCE_DOT[s.id]}`} />
                    <span className="min-w-0 truncate">
                      {s.label}
                      <span className="mt-0.5 block truncate text-[10px] font-normal text-slate-400">
                        {s.role}
                      </span>
                    </span>
                  </button>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    title="打开官网"
                    className="rounded-lg p-1.5 text-slate-300 opacity-0 transition hover:bg-slate-100 hover:text-slate-600 group-hover:opacity-100"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </div>
              ))}
            </div>
          </aside>

          <main className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <div>
                共 <strong className="text-slate-800">{total}</strong> 条
                {total > 0 ? (
                  <span className="ml-2">
                    · 第 {page}/{totalPages} 页
                  </span>
                ) : null}
                {loading ? " · 加载中…" : null}
                {err ? <span className="ml-2 text-rose-600">{err}</span> : null}
              </div>
              <PageJump page={page} totalPages={totalPages} onJump={setPage} />
            </div>

            {mode === "announce" ? (
              <div className="overflow-x-auto rounded-3xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full min-w-[36rem] text-left text-sm">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3 font-semibold">日期</th>
                      <th className="px-4 py-3 font-semibold">代码</th>
                      <th className="px-4 py-3 font-semibold">标题</th>
                      <th className="px-4 py-3 font-semibold">来源</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.id} className="border-t border-slate-100 hover:bg-rose-50/40">
                        <td className="whitespace-nowrap px-4 py-3 tabular-nums text-slate-500">
                          {formatNewsDate(it.publishedAt)}
                        </td>
                        <td className="px-4 py-3">
                          {it.symbols[0] ? (
                            <Link
                              to={`/data/symbol/${encodeURIComponent(it.symbols[0])}`}
                              className="font-medium text-rose-700 hover:underline"
                            >
                              {it.symbols[0]}
                            </Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-4 py-3 font-medium text-slate-900">
                          <Link to={`/news/${it.id}`} className="hover:text-rose-700">
                            {it.title}
                          </Link>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                          {it.sourceLabel}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!loading && items.length === 0 ? (
                  <div className="py-16 text-center text-sm text-slate-400">当前筛选无公告</div>
                ) : null}
              </div>
            ) : mode === "flash" ? (
              <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-100 bg-slate-950 px-4 py-3 text-sm font-semibold text-white">
                  <span className="inline-flex items-center gap-2">
                    <Zap className="h-4 w-4 text-rose-400" />
                    7×24 电报
                  </span>
                </div>
                <ul className="divide-y divide-slate-100">
                  {items.map((it) => (
                    <li key={it.id} className="flex gap-4 px-4 py-3.5 hover:bg-slate-50/80">
                      <div className="w-[4.5rem] shrink-0 pt-0.5 text-right text-[11px] font-semibold tabular-nums leading-snug text-rose-600">
                        {formatNewsWhen(it.publishedAt)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                          <span className={`h-1.5 w-1.5 rounded-full ${SOURCE_DOT[it.source] || "bg-slate-400"}`} />
                          {it.sourceLabel}
                          {it.themes.slice(0, 2).map((t) => (
                            <span key={t} className="rounded bg-slate-100 px-1.5 py-0.5">
                              {t}
                            </span>
                          ))}
                        </div>
                        <Link
                          to={`/news/${it.id}`}
                          className="font-news font-semibold leading-snug text-slate-900 hover:text-rose-700"
                        >
                          {it.title}
                        </Link>
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">
                          {it.summary}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
                {!loading && items.length === 0 ? (
                  <div className="py-16 text-center text-sm text-slate-400">当前筛选无快讯</div>
                ) : null}
              </div>
            ) : (
              <div className="space-y-3">
                {items.map((it) => (
                  <article
                    key={it.id}
                    className="group rounded-3xl border border-slate-200/90 bg-white/95 p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-rose-200 hover:shadow-md"
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span className={`h-1.5 w-1.5 rounded-full ${SOURCE_DOT[it.source] || "bg-slate-400"}`} />
                      <span className="font-semibold text-slate-700">{it.sourceLabel}</span>
                      <span>{formatNewsWhen(it.publishedAt)}</span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5">
                        {catLabel(it.category)}
                      </span>
                      {it.isFlash ? (
                        <span className="inline-flex items-center gap-0.5 rounded-full bg-rose-50 px-2 py-0.5 font-medium text-rose-600">
                          <Zap className="h-3 w-3" />
                          快讯
                        </span>
                      ) : null}
                    </div>
                    <h2 className="font-news text-[16px] font-semibold leading-snug tracking-tight text-slate-900 group-hover:text-rose-800">
                      <Link to={`/news/${it.id}`}>{it.title}</Link>
                    </h2>
                    <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-slate-600">
                      {it.summary}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {it.themes.map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => toggleTheme(t)}
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 transition ${
                            themes.includes(t)
                              ? "bg-rose-600 text-white ring-rose-600"
                              : "bg-[#faf6f3] text-rose-800 ring-rose-100 hover:bg-rose-50"
                          }`}
                        >
                          <Tag className="h-3 w-3" />
                          {t}
                        </button>
                      ))}
                      {(it.industries || []).slice(0, 2).map((ind) => (
                        <button
                          key={ind}
                          type="button"
                          onClick={() => toggleIndustry(ind)}
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 transition ${
                            industries.includes(ind)
                              ? "bg-amber-700 text-white ring-amber-700"
                              : "bg-amber-50/80 text-amber-900 ring-amber-100 hover:bg-amber-50"
                          }`}
                        >
                          {ind}
                        </button>
                      ))}
                      {it.symbols.map((sym) => (
                        <button
                          key={sym}
                          type="button"
                          onClick={() => toggleSymbol(sym)}
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition ${
                            symbols.includes(sym)
                              ? "border-slate-900 bg-slate-900 text-white"
                              : "border-slate-200 bg-white text-slate-700 hover:border-rose-300 hover:text-rose-700"
                          }`}
                        >
                          <Building2 className="h-3 w-3" />
                          {sym}
                        </button>
                      ))}
                      {it.url ? (
                        <a
                          href={it.url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-auto inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 hover:text-rose-600"
                        >
                          原文 <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : null}
                    </div>
                  </article>
                ))}
                {!loading && items.length === 0 ? (
                  <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 py-16 text-center text-sm text-slate-400">
                    {cat === "research" || cat === "policy" ? (
                      <>
                        <p className="font-medium text-slate-600">
                          「{catLabel(cat)}」本期尚未接入真源
                        </p>
                        <p className="mt-2 text-xs leading-relaxed">
                          当前拉取覆盖快讯 / 市场 / 公告 / 海外；研报与政策需另接栏目（如东财研报、政策频道）。
                        </p>
                      </>
                    ) : (
                      "当前筛选无条目"
                    )}
                  </div>
                ) : null}
              </div>
            )}

            {totalPages > 1 ? (
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                <button
                  type="button"
                  disabled={page <= 1 || loading}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                  上一页
                </button>
                <span className="px-2 text-sm tabular-nums text-slate-600">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages || loading}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  下一页
                  <ChevronRight className="h-4 w-4" />
                </button>
                <PageJump page={page} totalPages={totalPages} onJump={setPage} />
              </div>
            ) : null}
          </main>

          <aside className="hidden space-y-4 lg:sticky lg:top-24 lg:block lg:self-start">
            <div className="rounded-3xl border border-slate-200/90 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900">
                <Tag className="h-4 w-4 text-rose-600" />
                本页题材
              </div>
              {themeCloud.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {themeCloud.map((t) => (
                    <button
                      key={t.name}
                      type="button"
                      onClick={() => toggleTheme(t.name)}
                      className={`rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 transition ${
                        themes.includes(t.name)
                          ? "bg-rose-600 text-white ring-rose-600"
                          : "bg-[#faf6f3] text-rose-800 ring-rose-100 hover:bg-rose-50"
                      }`}
                      title={`出现 ${t.n} 次 · 点此筛选`}
                    >
                      {t.name}
                      <span
                        className={`ml-1 tabular-nums ${
                          themes.includes(t.name) ? "text-rose-100" : "text-rose-400"
                        }`}
                      >
                        {t.n}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">当前页暂无题材标签</p>
              )}
              {dictThemes.length > 0 ? (
                <div className="mt-3 border-t border-slate-100 pt-3">
                  <div className="mb-2 text-[11px] font-semibold text-slate-500">字典题材</div>
                  <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto">
                    {dictThemes.slice(0, 16).map((name) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => toggleTheme(name)}
                        className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                          themes.includes(name)
                            ? "bg-rose-600 text-white"
                            : "bg-slate-50 text-slate-600 hover:bg-rose-50 hover:text-rose-700"
                        }`}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            {industryCloud.length > 0 || dictIndustries.length > 0 ? (
              <div className="rounded-3xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900">
                  <Flame className="h-4 w-4 text-amber-600" />
                  行业
                </div>
                {industryCloud.length > 0 ? (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {industryCloud.map((t) => (
                      <button
                        key={t.name}
                        type="button"
                        onClick={() => toggleIndustry(t.name)}
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 transition ${
                          industries.includes(t.name)
                            ? "bg-amber-700 text-white ring-amber-700"
                            : "bg-amber-50 text-amber-900 ring-amber-100 hover:bg-amber-100"
                        }`}
                      >
                        {t.name}
                        <span
                          className={`ml-1 tabular-nums ${
                            industries.includes(t.name) ? "text-amber-100" : "text-amber-500"
                          }`}
                        >
                          {t.n}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
                {dictIndustries.length > 0 ? (
                  <div className="flex max-h-24 flex-wrap gap-1 overflow-y-auto">
                    {dictIndustries.slice(0, 14).map((name) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => toggleIndustry(name)}
                        className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                          industries.includes(name)
                            ? "bg-amber-700 text-white"
                            : "bg-slate-50 text-slate-600 hover:bg-amber-50"
                        }`}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {hotSymbols.length > 0 ? (
              <div className="rounded-3xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900">
                  <Building2 className="h-4 w-4 text-slate-700" />
                  关联标的
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {hotSymbols.map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => toggleSymbol(sym)}
                      className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold transition ${
                        symbols.includes(sym)
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-200 bg-white text-slate-700 hover:border-rose-300 hover:text-rose-700"
                      }`}
                      title="点此按代码筛选"
                    >
                      {sym}
                    </button>
                  ))}
                </div>
                {symbols.length === 1 ? (
                  <Link
                    to={`/data/symbol/${encodeURIComponent(symbols[0])}`}
                    className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-rose-700 hover:underline"
                  >
                    打开个股 {symbols[0]} <ArrowUpRight className="h-3 w-3" />
                  </Link>
                ) : null}
              </div>
            ) : null}

            <div className="rounded-3xl border border-slate-200/90 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900">
                <Flame className="h-4 w-4 text-rose-600" />
                今日风口
                <span className="ml-auto text-[10px] font-medium text-slate-400">静态样例</span>
              </div>
              <ul className="space-y-3">
                {HOT_THEMES.map((t, i) => (
                  <li key={t.name} className="flex gap-3">
                    <span
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[11px] font-bold ${
                        i < 3 ? "bg-rose-600 text-white" : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-baseline gap-2">
                        <button
                          type="button"
                          onClick={() => toggleTheme(t.name)}
                          className={`font-semibold hover:text-rose-700 ${
                            themes.includes(t.name) ? "text-rose-700" : "text-slate-900"
                          }`}
                        >
                          {t.name}
                        </button>
                        <span className="text-xs font-semibold tabular-nums text-rose-600">
                          {t.chg}
                        </span>
                      </div>
                      <p className="text-[11px] leading-relaxed text-slate-500">{t.reason}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-3xl border border-slate-200/90 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900">
                <CalendarDays className="h-4 w-4 text-slate-700" />
                投资日历
                <span className="ml-auto text-[10px] font-medium text-slate-400">静态样例</span>
              </div>
              <ul className="space-y-2.5">
                {CALENDAR.map((c) => (
                  <li key={c.title} className="flex gap-3 text-sm">
                    <span className="w-12 shrink-0 text-[11px] font-semibold text-rose-700">
                      {c.when}
                    </span>
                    <span className="leading-snug text-slate-700">{c.title}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-3xl border border-dashed border-slate-200 bg-white/80 p-4 text-xs leading-relaxed text-slate-500">
              <div className="mb-1 font-semibold text-slate-700">研究联动（规划）</div>
              自选股相关资讯、研报/政策源、真行情指数条与风口，将接到自选与数据页。
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
