import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { SymbolPreviewCard } from "@/components/data/SymbolPreviewCard";
import { PageJump } from "@/components/PageJump";
import {
  fetchMarketSymbols,
  fetchQuotesBatch,
  symbolMatchesQuery,
  type MarketSymbol,
  type SymbolQuote,
} from "@/lib/marketDataApi";

/** 每页最多 6 张预览卡，避免同时渲染过多图表卡死 */
const PAGE_SIZE = 6;

export function DataSearchResultsPage() {
  const [params, setParams] = useSearchParams();
  const qFromUrl = (params.get("q") || "").trim();
  const pageFromUrl = Math.max(1, Number(params.get("page") || "1") || 1);
  const [draftQ, setDraftQ] = useState(qFromUrl);
  const [symbols, setSymbols] = useState<MarketSymbol[]>([]);
  const [symErr, setSymErr] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Record<string, SymbolQuote>>({});
  const [loadingSym, setLoadingSym] = useState(true);

  useEffect(() => {
    setDraftQ(qFromUrl);
  }, [qFromUrl]);

  useEffect(() => {
    let cancelled = false;
    setLoadingSym(true);
    void fetchMarketSymbols()
      .then((list) => {
        if (!cancelled) setSymbols(list);
      })
      .catch((ex) => {
        if (!cancelled) setSymErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (!cancelled) setLoadingSym(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const allMatches = useMemo(() => {
    if (!qFromUrl) return [];
    return symbols.filter((s) => symbolMatchesQuery(s, qFromUrl));
  }, [symbols, qFromUrl]);

  const totalPages = Math.max(1, Math.ceil(allMatches.length / PAGE_SIZE));
  const page = Math.min(pageFromUrl, totalPages);

  const pageItems = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return allMatches.slice(start, start + PAGE_SIZE);
  }, [allMatches, page]);

  const pageCodes = useMemo(
    () => pageItems.map((m) => m.symbol),
    [pageItems],
  );

  // 超页时纠正 URL
  useEffect(() => {
    if (!qFromUrl || loadingSym) return;
    if (pageFromUrl !== page) {
      setParams({ q: qFromUrl, page: String(page) }, { replace: true });
    }
  }, [qFromUrl, loadingSym, page, pageFromUrl, setParams]);

  useEffect(() => {
    if (!pageCodes.length) {
      setQuotes({});
      return;
    }
    let cancelled = false;
    void fetchQuotesBatch(pageCodes, { concurrency: 4, lookbackDays: 45 }).then(
      (map) => {
        if (!cancelled) setQuotes(map);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [pageCodes]);

  const goPage = (p: number) => {
    const next = Math.min(totalPages, Math.max(1, p));
    setParams({ q: qFromUrl, page: String(next) });
  };

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const next = draftQ.trim();
    if (!next) return;
    setParams({ q: next, page: "1" });
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#f7f8fa]">
      <div className="border-b-2 border-slate-200 bg-white shadow-[0_1px_0_0_rgba(15,23,42,0.04)]">
        <div className="mx-auto max-w-[1280px] px-4 py-5 sm:px-6 lg:px-8">
          <Link
            to="/data/kline"
            className="text-sm text-slate-500 hover:text-slate-800"
          >
            ← 返回 K 线面板
          </Link>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
            搜索结果
          </h1>

          <form onSubmit={onSearch} className="mt-4 flex max-w-lg gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={draftQ}
                onChange={(e) => setDraftQ(e.target.value)}
                placeholder="搜索代码或名称"
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm outline-none ring-red-200 focus:border-red-300 focus:ring-2"
              />
            </div>
            <button
              type="submit"
              className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              搜索
            </button>
          </form>
        </div>
      </div>

      <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8">
        {symErr ? (
          <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {symErr}
          </p>
        ) : null}

        {!qFromUrl ? (
          <p className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-16 text-center text-sm text-slate-400">
            在上方输入代码后搜索
          </p>
        ) : loadingSym ? (
          <p className="py-16 text-center text-sm text-slate-400">加载中…</p>
        ) : allMatches.length === 0 && !symErr ? (
          <p className="rounded-2xl border border-slate-200 bg-white px-4 py-16 text-center text-sm text-slate-400">
            未找到匹配代码
          </p>
        ) : pageItems.length > 0 ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {pageItems.map((item) => (
                <SymbolPreviewCard
                  key={item.symbol}
                  symbol={item.symbol}
                  name={item.name}
                  quote={quotes[item.symbol] || null}
                />
              ))}
            </div>

            {totalPages > 1 ? (
              <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-slate-500">
                  共 {allMatches.length} 条 · 第 {page}/{totalPages} 页 · 每页{" "}
                  {PAGE_SIZE} 条
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => goPage(page - 1)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一页
                  </button>
                  <PageJump page={page} totalPages={totalPages} onJump={goPage} />
                  <button
                    type="button"
                    disabled={page >= totalPages}
                    onClick={() => goPage(page + 1)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    下一页
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
