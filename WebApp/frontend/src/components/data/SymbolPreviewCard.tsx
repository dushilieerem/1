import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { SymbolMiniChart } from "@/components/data/SymbolMiniChart";
import {
  changeToneClass,
  fmtPct,
  fmtPrice,
  type SymbolQuote,
} from "@/lib/marketDataApi";

type Props = {
  symbol: string;
  name?: string | null;
  quote?: SymbolQuote | null;
};

export function SymbolPreviewCard({ symbol, name, quote }: Props) {
  const tone = changeToneClass(quote?.changePct);
  const up =
    quote?.changePct == null
      ? null
      : quote.changePct > 0
        ? true
        : quote.changePct < 0
          ? false
          : null;
  const title = (quote?.name || name || "").trim();

  return (
    <Link
      to={`/data/symbol/${encodeURIComponent(symbol)}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3 px-4 pt-4">
        <div className="min-w-0">
          <p className="truncate text-lg font-bold tracking-tight text-slate-900">
            {title || symbol}
          </p>
          <p className="mt-0.5 text-xs font-medium text-slate-500">{symbol}</p>
        </div>
        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition group-hover:bg-slate-900 group-hover:text-white">
          <ArrowUpRight className="h-3.5 w-3.5" />
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-baseline gap-2 px-4">
        {quote?.last == null ? (
          <span className="text-sm font-medium text-slate-400">暂无行情</span>
        ) : (
          <>
            <span className={`text-2xl font-bold tabular-nums ${tone}`}>
              {fmtPrice(quote.last)}
            </span>
            <span className={`text-sm font-semibold tabular-nums ${tone}`}>
              {quote.change == null
                ? ""
                : `${quote.change > 0 ? "+" : ""}${fmtPrice(quote.change)}`}{" "}
              {fmtPct(quote.changePct)}
            </span>
          </>
        )}
      </div>

      <div className="mt-3 border-t border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-3 pb-3 pt-3">
        <SymbolMiniChart
          symbol={symbol}
          up={up}
          asOf={quote?.asOf || quote?.rangeEnd || null}
          height={112}
        />
      </div>
    </Link>
  );
}
