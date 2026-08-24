import { Link, useParams, useSearchParams } from "react-router-dom";
import { SymbolOverviewPanel } from "@/components/data/SymbolOverviewPanel";

export function DataSymbolOverviewPage() {
  const { code = "" } = useParams();
  const [params] = useSearchParams();
  const symbol = decodeURIComponent(code).trim();
  const fromWatchlist = params.get("from") === "watchlist";
  const fromNews = params.get("from") === "news";
  const newsId = (params.get("newsId") || "").trim();

  const backTo = fromWatchlist
    ? "/data/watchlist"
    : fromNews && newsId
      ? `/news/${encodeURIComponent(newsId)}`
      : fromNews
        ? "/news"
        : "/data/kline";
  const backLabel = fromWatchlist
    ? "← 返回自选股组合"
    : fromNews
      ? "← 返回资讯"
      : "← 返回 K 线面板";

  return (
    <div className="mx-auto max-w-[1280px] px-3 py-4 sm:px-6 sm:py-6 lg:px-8">
      <Link to={backTo} className="text-sm text-slate-500 hover:text-slate-800">
        {backLabel}
      </Link>
      <div className="mt-3 sm:mt-4">
        <SymbolOverviewPanel
          symbol={symbol || "000001.SZ"}
          chartFrom={
            fromWatchlist
              ? "watchlist"
              : fromNews
                ? newsId
                  ? `news:${newsId}`
                  : "news"
                : undefined
          }
        />
      </div>
    </div>
  );
}
