import { useState, type FormEvent } from "react";
import {
  ArrowRight,
  CandlestickChart,
  LineChart,
  Search,
  Sparkles,
} from "lucide-react";
import { SymbolOverviewPanel } from "@/components/data/SymbolOverviewPanel";
import { openAuthedTab } from "@/components/RequireAuth";

/** 文档推荐交易所后缀；默认平安银行 */
const DEFAULT_SYMBOL = "000001.SZ";

const FEATURES = [
  { icon: Search, title: "代码搜索" },
  { icon: LineChart, title: "个股概览" },
  { icon: CandlestickChart, title: "日线 K 线" },
] as const;

export function DataKlinePanelPage() {
  const [draftQ, setDraftQ] = useState("");

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const q = draftQ.trim();
    if (!q) return;
    openAuthedTab(`/data/kline/search?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#f7f8fa]">
      {/* 顶区到内容区用渐变过渡，避免硬分界线 */}
      <div className="relative bg-gradient-to-b from-white via-white to-[#f7f8fa]">
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -left-24 -top-10 h-[380px] w-[380px] rounded-full bg-red-500/5 blur-3xl" />
          <div className="absolute -right-16 top-0 h-[320px] w-[320px] rounded-full bg-sky-400/10 blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-[1280px] px-4 pt-10 sm:px-6 lg:px-8 lg:pt-12">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-red-100 bg-red-50 px-3 py-1 text-xs font-semibold text-red-600">
            <Sparkles className="h-3 w-3" />
            数据 · K 线面板
          </span>

          <div className="mt-5 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
            <h1 className="max-w-xl text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
              看行情，从一只股开始
            </h1>

            <form
              onSubmit={onSearch}
              className="flex w-full max-w-md shrink-0 gap-2 sm:ml-auto"
            >
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={draftQ}
                  onChange={(e) => setDraftQ(e.target.value)}
                  placeholder="搜索代码或名称"
                  className="w-full rounded-xl border border-slate-200 bg-white/90 py-3 pl-9 pr-3 text-sm shadow-sm outline-none ring-red-200 backdrop-blur focus:border-red-300 focus:ring-2"
                />
              </div>
              <button
                type="submit"
                className="inline-flex items-center gap-1.5 rounded-xl bg-red-600 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-red-700"
              >
                搜索
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          </div>

          <div className="mt-6 flex flex-wrap gap-2">
            {FEATURES.map(({ icon: Icon, title }) => (
              <span
                key={title}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200/90 bg-white/80 px-3.5 py-1.5 text-sm font-medium text-slate-700 shadow-sm backdrop-blur"
              >
                <Icon className="h-3.5 w-3.5 text-red-500" />
                {title}
              </span>
            ))}
          </div>

          {/* 顶区与「今日聚焦」分割 */}
          <div className="mt-10 flex items-center gap-3" aria-hidden>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-slate-300 to-slate-300" />
            <div className="h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
            <div className="h-px flex-1 bg-gradient-to-l from-transparent via-slate-300 to-slate-300" />
          </div>
        </div>
      </div>

      <section className="relative mx-auto max-w-[1280px] px-4 pb-10 pt-6 sm:px-6 lg:px-8">
        <h2 className="mb-4 text-lg font-bold text-slate-900">今日聚焦</h2>
        <SymbolOverviewPanel symbol={DEFAULT_SYMBOL} />
      </section>
    </div>
  );
}
