import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Eye, Search, Trash2, Zap } from "lucide-react";
import { AuthorAvatar } from "@/components/community/communityUi";
import { PageJump } from "@/components/PageJump";
import { PlazaEquityChart } from "@/components/strategy/PlazaEquityChart";
import { getStoredUser } from "@/lib/auth";
import {
  hideStrategyPlazaItem,
  listStrategyPlaza,
  type PlazaItem,
} from "@/lib/strategyPlazaApi";

const PAGE_SIZE = 5;

const SORT_OPTIONS = [
  { value: "newest", label: "最新发布" },
  { value: "annual", label: "年化收益" },
  { value: "sharpe", label: "夏普比率" },
  { value: "mdd", label: "回撤更小" },
  { value: "excess", label: "超额收益" },
  { value: "views", label: "浏览最多" },
] as const;

const UNIVERSE_OPTIONS = [
  { value: "", label: "全部股票池" },
  { value: "CSI300", label: "沪深300" },
  { value: "CSI500", label: "中证500" },
  { value: "CSI1000", label: "中证1000" },
] as const;

function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}

function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(2);
}

/** 红涨绿跌 */
function toneClass(x?: number | null, invert = false) {
  if (x == null || Number.isNaN(x)) return "text-slate-500";
  const pos = invert ? x < 0 : x > 0;
  const neg = invert ? x > 0 : x < 0;
  if (pos) return "text-red-500";
  if (neg) return "text-emerald-600";
  return "text-slate-600";
}

function MetricCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <div
        className={`truncate text-base font-semibold tabular-nums sm:text-lg ${tone || "text-slate-800"}`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[11px] text-slate-400">{label}</div>
    </div>
  );
}

function PlazaCard({
  item,
  isAdmin,
  onDeleted,
}: {
  item: PlazaItem;
  isAdmin: boolean;
  onDeleted: (id: number) => void;
}) {
  const m = item.snapshot?.metrics || {};
  const annual = m.annual_return;
  const cum = m.cumulative_return ?? m.total_return ?? null;
  const mdd = m.max_drawdown;
  const sharpe = m.sharpe;
  const author =
    item.author?.display_name || item.author?.username || "匿名";
  const username = item.author?.username;
  const bodyPreview = (item.body || "").replace(/<[^>]+>/g, "").trim();

  return (
    <div className="group relative rounded-2xl bg-white/95 shadow-sm ring-1 ring-orange-100/80 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-rose-200">
      <Link to={`/strategy/plaza/${item.id}`} className="absolute inset-0 z-0" />
      <div className="relative z-10 grid pointer-events-none gap-0 lg:grid-cols-[minmax(0,1.05fr)_minmax(300px,1.2fr)_250px]">
        <div className="flex min-h-[220px] min-w-0 flex-col border-b border-slate-100 p-5 lg:border-b-0 lg:border-r">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {username ? (
              <Link
                to={`/u/${encodeURIComponent(username)}`}
                className="pointer-events-auto inline-flex items-center gap-2 hover:opacity-90"
                onClick={(e) => e.stopPropagation()}
              >
                <AuthorAvatar
                  name={author}
                  src={item.author?.avatar_url}
                  size="sm"
                />
                <span className="font-medium text-slate-700">{author}</span>
              </Link>
            ) : (
              <span className="inline-flex items-center gap-2">
                <AuthorAvatar name={author} src={item.author?.avatar_url} size="sm" />
                <span className="font-medium text-slate-700">{author}</span>
              </span>
            )}
            <span className="text-slate-300">·</span>
            <span>{item.created_at?.slice(0, 10) || "—"}</span>
            {item.snapshot?.universe_label ? (
              <span className="rounded-full bg-orange-50 px-2 py-0.5 text-orange-800/80 ring-1 ring-orange-100">
                {item.snapshot.universe_label}
              </span>
            ) : null}
          </div>
          <h2 className="mt-3 line-clamp-2 text-lg font-bold tracking-tight text-slate-900 group-hover:text-rose-600">
            {item.title}
          </h2>
          {bodyPreview ? (
            <p className="mt-3 line-clamp-5 overflow-hidden text-sm leading-6 text-slate-500">
              {bodyPreview}
            </p>
          ) : null}
          <div className="mt-auto flex items-center gap-3 pt-3 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1">
              <Eye className="h-3.5 w-3.5" />
              {item.view_count}
            </span>
            {item.snapshot?.range_label ? (
              <span>{item.snapshot.range_label}</span>
            ) : null}
          </div>
        </div>

        {/* 图表单独接收鼠标，否则 tooltip 被整卡 pointer-events-none 挡住 */}
        <div className="pointer-events-auto relative z-20 flex min-h-[220px] min-w-0 items-center border-b border-orange-50 p-3 lg:border-b-0 lg:border-r lg:p-4">
          <div className="w-full">
            <PlazaEquityChart
              equity={item.snapshot?.equity_curve}
              benchmark={item.snapshot?.benchmark_curve}
              height={176}
              compact
              showExcess
            />
          </div>
        </div>

        <div className="flex min-h-[220px] flex-col justify-center gap-4 bg-slate-50/60 p-5">
          <div>
            <div
              className={`text-3xl font-bold tabular-nums ${toneClass(annual)}`}
            >
              {pct(annual)}
            </div>
            <div className="mt-1 text-[11px] text-slate-400">年化收益</div>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <MetricCell label="累计收益" value={pct(cum)} tone={toneClass(cum)} />
            <MetricCell
              label="超额"
              value={pct(item.snapshot?.excess_return)}
              tone={toneClass(item.snapshot?.excess_return)}
            />
            <MetricCell
              label="最大回撤"
              value={pct(mdd)}
              tone={toneClass(mdd)}
            />
            <MetricCell label="夏普" value={num(sharpe)} tone="text-slate-800" />
          </div>
          <div className="pointer-events-auto flex items-center justify-end gap-2">
            {isAdmin ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (!window.confirm(`删除「${item.title}」？`)) return;
                  void hideStrategyPlazaItem(item.id)
                    .then(() => onDeleted(item.id))
                    .catch((err: Error) => window.alert(err.message));
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除
              </button>
            ) : null}
            <Link
              to={`/strategy/plaza/${item.id}`}
              className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-600"
            >
              <Zap className="h-3.5 w-3.5" />
              查看
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export function StrategyPlazaPage() {
  const navigate = useNavigate();
  const user = getStoredUser();
  const isAdmin = (user?.role || "").toLowerCase() === "admin";
  const [items, setItems] = useState<PlazaItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [qDraft, setQDraft] = useState("");
  const [sort, setSort] = useState<string>("newest");
  const [universe, setUniverse] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageSafe = Math.min(Math.max(1, page), totalPages);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void listStrategyPlaza({
      limit: PAGE_SIZE,
      offset: (pageSafe - 1) * PAGE_SIZE,
      q: q || undefined,
      sort,
      universe: universe || undefined,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items || []);
        setTotal(res.total || 0);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message || "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [q, pageSafe, sort, universe]);

  const emptyHint = useMemo(() => {
    if (q || universe) return "没有匹配的策略";
    return "暂无分享";
  }, [q, universe]);

  const rangeStart = total === 0 ? 0 : (pageSafe - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(pageSafe * PAGE_SIZE, total);

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-white to-slate-100">
      <div className="mx-auto max-w-[1440px] px-4 py-7 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-white via-slate-50 to-slate-100/90 px-5 py-6 ring-1 ring-slate-200/70 sm:px-7 sm:py-7">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-slate-200/40 blur-3xl"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-20 left-1/3 h-40 w-40 rounded-full bg-slate-300/25 blur-3xl"
          />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0 max-w-2xl">
              <p className="text-xs font-medium tracking-wide text-slate-400">
                策略分享 · 回测快照
              </p>
              <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                策略广场
              </h1>
            </div>
            <form
              className="flex w-full max-w-md gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setPage(1);
                setQ(qDraft.trim());
              }}
            >
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={qDraft}
                  onChange={(e) => setQDraft(e.target.value)}
                  placeholder="搜索标题或介绍"
                  className="w-full rounded-xl border-0 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-800 shadow-sm ring-1 ring-slate-200/80 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300"
                />
              </div>
              <button
                type="submit"
                className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-rose-600"
              >
                搜索
              </button>
            </form>
          </div>
        </div>

        <div className="mt-4 rounded-2xl bg-white/95 px-4 py-3 shadow-sm ring-1 ring-orange-100/80 sm:px-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="shrink-0 text-xs font-medium text-slate-500">
                股票池
              </span>
              <div className="flex flex-wrap gap-1.5">
                {UNIVERSE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value || "all"}
                    type="button"
                    onClick={() => {
                      setUniverse(opt.value);
                      setPage(1);
                    }}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                      universe === opt.value
                        ? "bg-slate-900 text-white"
                        : "bg-slate-50 text-slate-600 ring-1 ring-slate-200/80 hover:bg-slate-100"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="shrink-0 text-xs font-medium text-slate-500">
                排序
              </span>
              <div className="flex flex-wrap gap-1.5">
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => {
                      setSort(opt.value);
                      setPage(1);
                    }}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                      sort === opt.value
                        ? "bg-rose-500 text-white"
                        : "bg-slate-50 text-slate-600 ring-1 ring-slate-200/80 hover:bg-slate-100"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 space-y-4">
          {loading ? (
            <div className="rounded-2xl bg-white/80 px-6 py-16 text-center text-sm text-slate-500 ring-1 ring-orange-100">
              加载中…
            </div>
          ) : err ? (
            <div className="rounded-2xl bg-rose-50 px-6 py-10 text-center text-sm text-rose-600 ring-1 ring-rose-100">
              {err}
            </div>
          ) : !items.length ? (
            <div className="rounded-2xl bg-white/80 px-6 py-16 text-center text-sm text-slate-500 ring-1 ring-orange-100">
              {emptyHint}
              <button
                type="button"
                onClick={() => navigate("/strategy/research")}
                className="mt-3 block w-full text-rose-600 hover:underline"
              >
                去做回测
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  {universe
                    ? UNIVERSE_OPTIONS.find((o) => o.value === universe)?.label
                    : "全部股票池"}
                  ·{" "}
                  {SORT_OPTIONS.find((o) => o.value === sort)?.label || "最新发布"}
                </span>
                <span>
                  {rangeStart}-{rangeEnd} / {total}
                </span>
              </div>
              {items.map((it) => (
                <PlazaCard
                  key={it.id}
                  item={it}
                  isAdmin={isAdmin}
                  onDeleted={(id) => {
                    setItems((prev) => prev.filter((x) => x.id !== id));
                    setTotal((t) => Math.max(0, t - 1));
                  }}
                />
              ))}
              {totalPages > 1 ? (
                <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
                  <button
                    type="button"
                    disabled={pageSafe <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-slate-200 bg-white p-2 disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter((n) => {
                      if (totalPages <= 7) return true;
                      if (n === 1 || n === totalPages) return true;
                      return Math.abs(n - pageSafe) <= 1;
                    })
                    .map((n, idx, arr) => {
                      const prev = arr[idx - 1];
                      const gap = prev != null && n - prev > 1;
                      return (
                        <span key={n} className="inline-flex items-center gap-2">
                          {gap ? (
                            <span className="px-1 text-slate-400">…</span>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => setPage(n)}
                            className={`min-w-8 rounded-lg px-2 py-1.5 text-sm ${
                              n === pageSafe
                                ? "bg-slate-900 text-white"
                                : "border border-slate-200 bg-white text-slate-700"
                            }`}
                          >
                            {n}
                          </button>
                        </span>
                      );
                    })}
                  <button
                    type="button"
                    disabled={pageSafe >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-lg border border-slate-200 bg-white p-2 disabled:opacity-40"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                  <PageJump
                    page={pageSafe}
                    totalPages={totalPages}
                    onJump={setPage}
                  />
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
