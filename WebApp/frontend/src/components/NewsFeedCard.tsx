import { Link } from "react-router-dom";
import { Building2, ExternalLink, Tag, Zap } from "lucide-react";
import { NEWS_CATEGORIES } from "@/data/nav";
import { formatNewsWhen, type NewsItem } from "@/lib/newsApi";

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

/** 资讯要闻流卡片（列表页 / 浏览历史共用） */
export function NewsFeedCard({
  item,
  onThemeClick,
  onIndustryClick,
  onSymbolClick,
}: {
  item: NewsItem;
  onThemeClick?: (name: string) => void;
  onIndustryClick?: (name: string) => void;
  onSymbolClick?: (code: string) => void;
}) {
  return (
    <article className="group rounded-3xl border border-slate-200/90 bg-white/95 p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-rose-200 hover:shadow-md">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span
          className={`h-1.5 w-1.5 rounded-full ${SOURCE_DOT[item.source] || "bg-slate-400"}`}
        />
        <span className="font-semibold text-slate-700">{item.sourceLabel}</span>
        <span>{formatNewsWhen(item.publishedAt)}</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5">
          {catLabel(item.category)}
        </span>
        {item.isFlash ? (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-rose-50 px-2 py-0.5 font-medium text-rose-600">
            <Zap className="h-3 w-3" />
            快讯
          </span>
        ) : null}
      </div>
      <h2 className="font-news text-[16px] font-semibold leading-snug tracking-tight text-slate-900 group-hover:text-rose-800">
        <Link to={`/news/${item.id}`}>{item.title}</Link>
      </h2>
      <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-slate-600">
        {item.summary}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {item.themes.map((t) =>
          onThemeClick ? (
            <button
              key={t}
              type="button"
              onClick={() => onThemeClick(t)}
              className="inline-flex items-center gap-1 rounded-full bg-[#faf6f3] px-2 py-0.5 text-[11px] font-medium text-rose-800 ring-1 ring-rose-100 hover:bg-rose-50"
            >
              <Tag className="h-3 w-3" />
              {t}
            </button>
          ) : (
            <span
              key={t}
              className="inline-flex items-center gap-1 rounded-full bg-[#faf6f3] px-2 py-0.5 text-[11px] font-medium text-rose-800 ring-1 ring-rose-100"
            >
              <Tag className="h-3 w-3" />
              {t}
            </span>
          ),
        )}
        {(item.industries || []).slice(0, 2).map((ind) =>
          onIndustryClick ? (
            <button
              key={ind}
              type="button"
              onClick={() => onIndustryClick(ind)}
              className="inline-flex items-center gap-1 rounded-full bg-amber-50/80 px-2 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-amber-100 hover:bg-amber-50"
            >
              {ind}
            </button>
          ) : (
            <span
              key={ind}
              className="inline-flex items-center gap-1 rounded-full bg-amber-50/80 px-2 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-amber-100"
            >
              {ind}
            </span>
          ),
        )}
        {item.symbols.map((sym) =>
          onSymbolClick ? (
            <button
              key={sym}
              type="button"
              onClick={() => onSymbolClick(sym)}
              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700 hover:border-rose-300 hover:text-rose-700"
            >
              <Building2 className="h-3 w-3" />
              {sym}
            </button>
          ) : (
            <Link
              key={sym}
              to={`/data/symbol/${encodeURIComponent(sym)}`}
              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700 hover:border-rose-300 hover:text-rose-700"
            >
              <Building2 className="h-3 w-3" />
              {sym}
            </Link>
          ),
        )}
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 hover:text-rose-600"
          >
            原文 <ExternalLink className="h-3 w-3" />
          </a>
        ) : null}
      </div>
    </article>
  );
}
