import { Link, useParams, useSearchParams } from "react-router-dom";
import { SymbolOverviewPanel } from "@/components/data/SymbolOverviewPanel";

export function DataSymbolOverviewPage() {
  const { code = "" } = useParams();
  const [params] = useSearchParams();
  const symbol = decodeURIComponent(code).trim();
  const fromWatchlist = params.get("from") === "watchlist";

  return (
    <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8">
      <Link
        to={fromWatchlist ? "/data/watchlist" : "/data/kline"}
        className="text-sm text-slate-500 hover:text-slate-800"
      >
        {fromWatchlist ? "← 返回自选股组合" : "← 返回 K 线面板"}
      </Link>
      <div className="mt-4">
        <SymbolOverviewPanel
          symbol={symbol || "000001.SZ"}
          chartFrom={fromWatchlist ? "watchlist" : undefined}
        />
      </div>
    </div>
  );
}
