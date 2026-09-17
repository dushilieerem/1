import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Code2,
  Eye,
  LayoutDashboard,
  Loader2,
  Trash2,
  Zap,
} from "lucide-react";
import { AuthorAvatar } from "@/components/community/communityUi";
import { PlazaEquityChart } from "@/components/strategy/PlazaEquityChart";
import { getStoredUser, prepareAuthHandoff } from "@/lib/auth";
import { highlightSource } from "@/lib/codeHighlight";
import {
  getStrategyPlazaItem,
  hideStrategyPlazaItem,
  type PlazaCurvePoint,
  type PlazaItem,
} from "@/lib/strategyPlazaApi";
import { ygBacktestStrategy, type YgBacktestResponse } from "@/lib/ygApi";

type Tab = "overview" | "code" | "run";

function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}
function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(2);
}
/** 红涨绿跌 */
function tone(x?: number | null, invert = false) {
  if (x == null || Number.isNaN(x)) return "text-slate-700";
  const pos = invert ? x < 0 : x > 0;
  const neg = invert ? x > 0 : x < 0;
  if (pos) return "text-red-500";
  if (neg) return "text-emerald-600";
  return "text-slate-700";
}

function Kpi({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="rounded-2xl bg-white/90 p-4 ring-1 ring-orange-100/80">
      <div className={`text-xl font-bold tabular-nums ${className || ""}`}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-slate-400">{label}</div>
    </div>
  );
}

function resolvePlazaRunCode(raw: string): {
  code: string;
  engineMode: "vectorized" | "event";
} {
  let code = raw;
  const newImport = `from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)`;
  code = code.replace(
    /from\s+quantcore\s+import\s*\([\s\S]*?\)/,
    newImport,
  );
  code = code.replace(
    /from\s+app\.quantcore\s+import\s*\([\s\S]*?\)/,
    newImport,
  );
  const eventish =
    /execution_mode\s*=\s*["']event["']/.test(code) ||
    /class\s+\w+EventStrategy\b/.test(code) ||
    /def\s+initialize\s*\(\s*self\s*,\s*context/.test(code);
  return { code, engineMode: eventish ? "event" : "vectorized" };
}

function HeroPulseStats({
  annual,
  cum,
  mdd,
}: {
  annual?: number | null;
  cum?: number | null;
  mdd?: number | null;
}) {
  const items = [
    { label: "年化", value: pct(annual), tone: tone(annual) },
    { label: "累计", value: pct(cum), tone: tone(cum) },
    { label: "回撤", value: pct(mdd), tone: tone(mdd) },
  ];
  return (
    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-white via-orange-50/80 to-rose-50/70 px-4 py-3 shadow-sm ring-1 ring-orange-100/90 sm:px-5 sm:py-4">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-rose-300/30 blur-2xl animate-pulse"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-8 -left-4 h-20 w-20 rounded-full bg-amber-300/25 blur-2xl animate-pulse"
        style={{ animationDelay: "0.6s" }}
      />
      <div className="relative flex items-center justify-center gap-3 sm:gap-5">
        {items.map((it, i) => (
          <div
            key={it.label}
            className="relative flex h-[4.75rem] w-[4.75rem] flex-col items-center justify-center rounded-full bg-white shadow-md ring-1 ring-orange-100 sm:h-[5.5rem] sm:w-[5.5rem]"
          >
            <div
              aria-hidden
              className="absolute inset-[-3px] rounded-full opacity-90"
              style={{
                background:
                  "conic-gradient(from 0deg, #ef4444, #f59e0b, #3b82f6, #ec4899, #ef4444)",
                mask: "radial-gradient(farthest-side, transparent calc(100% - 4px), #000 calc(100% - 3px))",
                WebkitMask:
                  "radial-gradient(farthest-side, transparent calc(100% - 4px), #000 calc(100% - 3px))",
                animation: "plaza-spin 3.5s linear infinite",
                animationDelay: `${i * 0.25}s`,
              }}
            />
            <div
              aria-hidden
              className="absolute inset-0 rounded-full bg-rose-400/10 animate-ping"
              style={{ animationDuration: "2.2s", animationDelay: `${i * 0.3}s` }}
            />
            <div
              className={`relative text-sm font-bold tabular-nums sm:text-base ${it.tone}`}
            >
              {it.value}
            </div>
            <div className="relative text-[10px] text-slate-400">{it.label}</div>
          </div>
        ))}
      </div>
      <style>{`
        @keyframes plaza-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

export function StrategyPlazaDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const user = getStoredUser();
  const isAdmin = (user?.role || "").toLowerCase() === "admin";
  const [item, setItem] = useState<PlazaItem | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");

  const [runBusy, setRunBusy] = useState(false);
  const [runErr, setRunErr] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<YgBacktestResponse | null>(null);

  useEffect(() => {
    const nid = Number(id);
    if (!Number.isFinite(nid)) {
      setErr("无效链接");
      return;
    }
    let cancelled = false;
    setErr(null);
    setRunResult(null);
    setRunErr(null);
    void getStrategyPlazaItem(nid)
      .then((it) => {
        if (!cancelled) setItem(it);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message || "加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const m = item?.snapshot?.metrics || {};
  const author =
    item?.author?.display_name || item?.author?.username || "匿名";
  const username = item?.author?.username;
  const bodyText = useMemo(() => {
    const raw = item?.body || "";
    if (!raw.includes("<")) return raw;
    return raw.replace(/<[^>]+>/g, "\n").replace(/\n+/g, "\n").trim();
  }, [item?.body]);

  const codeHtml = useMemo(() => {
    const code = item?.snapshot?.strategy_code || "";
    if (!code) return "";
    return highlightSource(code, "python").html;
  }, [item?.snapshot?.strategy_code]);

  const runFast = async () => {
    if (!item) return;
    if (!getStoredUser()) {
      prepareAuthHandoff();
      navigate(`/login?next=${encodeURIComponent(`/strategy/plaza/${item.id}`)}`);
      return;
    }
    const rawCode = item.snapshot.strategy_code?.trim();
    if (!rawCode) {
      setRunErr("该分享未附带策略源码，无法极速运行");
      return;
    }
    setRunBusy(true);
    setRunErr(null);
    try {
      const start =
        item.snapshot.date_range?.start ||
        (item.snapshot.range_label || "").split("~")[0]?.trim() ||
        null;
      const end =
        item.snapshot.date_range?.end ||
        (item.snapshot.range_label || "").split("~")[1]?.trim() ||
        null;
      const resolved = resolvePlazaRunCode(rawCode);
      const engineMode =
        item.snapshot.engine_mode === "event" ||
        item.snapshot.engine_mode === "vectorized"
          ? item.snapshot.engine_mode
          : resolved.engineMode;
      const res = await ygBacktestStrategy({
        strategy_code: resolved.code,
        universe: item.snapshot.universe || "CSI300",
        benchmark: item.snapshot.benchmark || "CSI300",
        start,
        end,
        commission_rate: 0.0003,
        stamp_tax: 0.001,
        slippage_rate: 0.001,
        initial_capital: 1_000_000,
        engine_mode: engineMode,
        include_rebalance_logs: false,
      });
      if (res.error) {
        const raw = String(res.error);
        setRunErr(
          /No module named/i.test(raw)
            ? "计算服务未能加载策略依赖库。请确认 ResearchEngine 已用当前可运行导入路径启动后再试。"
            : raw,
        );
        setRunResult(null);
        return;
      }
      setRunResult(res);
    } catch (e) {
      const raw = e instanceof Error ? e.message : "运行失败";
      setRunErr(
        /No module named/i.test(raw)
          ? "计算服务未能加载策略依赖库。请确认 ResearchEngine 已正常启动后再试。"
          : raw,
      );
      setRunResult(null);
    } finally {
      setRunBusy(false);
    }
  };

  const liveEquity = (runResult?.equity_curve || null) as PlazaCurvePoint[] | null;
  const liveBench = (runResult?.benchmark_curve || null) as PlazaCurvePoint[] | null;
  const liveM = runResult?.metrics || {};

  if (err) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-16 text-center">
        <p className="text-sm text-red-600">{err}</p>
        <button
          type="button"
          className="mt-4 text-sm text-slate-700 hover:underline"
          onClick={() => navigate("/strategy/plaza")}
        >
          返回策略广场
        </button>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">
        加载中…
      </div>
    );
  }

  const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
    { id: "overview", label: "概览", icon: LayoutDashboard },
    { id: "code", label: "源码", icon: Code2 },
    { id: "run", label: "极速运行", icon: Zap },
  ];

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-white to-slate-100">
      <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            to="/strategy/plaza"
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
          >
            <ArrowLeft className="h-4 w-4" />
            策略广场
          </Link>
          {isAdmin ? (
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
              onClick={() => {
                if (!window.confirm(`删除「${item.title}」？`)) return;
                void hideStrategyPlazaItem(item.id)
                  .then(() => navigate("/strategy/plaza"))
                  .catch((e: Error) => window.alert(e.message));
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除
            </button>
          ) : null}
        </div>

        <div className="mt-4 overflow-hidden rounded-2xl bg-white/95 shadow-sm ring-1 ring-orange-100/90">
          <div className="grid gap-0 lg:grid-cols-[minmax(0,1.35fr)_auto]">
            <div className="relative min-w-0 border-b border-orange-50 p-5 sm:p-6 lg:border-b-0 lg:border-r">
              <div
                aria-hidden
                className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-orange-50/60 to-transparent"
              />
              <h1 className="relative text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                {item.title}
              </h1>
              <div className="relative mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-500">
                {username ? (
                  <Link
                    to={`/u/${encodeURIComponent(username)}`}
                    className="inline-flex items-center gap-2 rounded-full bg-slate-50 py-1 pl-1 pr-2.5 font-medium text-slate-700 ring-1 ring-slate-200/80 hover:text-rose-600"
                  >
                    <AuthorAvatar
                      name={author}
                      src={item.author?.avatar_url}
                      size="sm"
                    />
                    {author}
                  </Link>
                ) : (
                  <span className="inline-flex items-center gap-2 rounded-full bg-slate-50 py-1 pl-1 pr-2.5 font-medium text-slate-700 ring-1 ring-slate-200/80">
                    <AuthorAvatar name={author} src={item.author?.avatar_url} size="sm" />
                    {author}
                  </span>
                )}
                <span className="rounded-full bg-slate-50 px-2.5 py-1 text-xs ring-1 ring-slate-200/70">
                  {item.created_at?.slice(0, 16).replace("T", " ") || "—"}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-2.5 py-1 text-xs ring-1 ring-slate-200/70">
                  <Eye className="h-3.5 w-3.5" />
                  {item.view_count}
                </span>
                {item.snapshot?.universe_label ? (
                  <span className="rounded-full bg-orange-50 px-2.5 py-1 text-xs text-orange-900/80 ring-1 ring-orange-100">
                    {item.snapshot.universe_label}
                  </span>
                ) : null}
                {item.snapshot?.range_label ? (
                  <span className="rounded-full bg-slate-50 px-2.5 py-1 text-xs ring-1 ring-slate-200/70">
                    {item.snapshot.range_label}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="flex items-center justify-center bg-gradient-to-br from-orange-50/40 to-rose-50/30 p-4 sm:p-5">
              <HeroPulseStats
                annual={m.annual_return}
                cum={m.cumulative_return ?? m.total_return}
                mdd={m.max_drawdown}
              />
            </div>
          </div>
        </div>

        <div className="mt-6 flex gap-1 rounded-xl bg-white/90 p-1 ring-1 ring-orange-100 sm:w-fit">
          {tabs.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-slate-900 text-white shadow-sm"
                    : "text-slate-600 hover:bg-orange-50"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="mt-6">
          {tab === "overview" ? (
            <div className="space-y-5">
              {bodyText ? (
                <div className="rounded-2xl bg-white/90 p-5 text-sm leading-relaxed text-slate-600 ring-1 ring-orange-100 whitespace-pre-wrap">
                  {bodyText}
                </div>
              ) : null}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <Kpi label="年化收益" value={pct(m.annual_return)} className={tone(m.annual_return)} />
                <Kpi
                  label="累计收益"
                  value={pct(m.cumulative_return ?? m.total_return)}
                  className={tone(m.cumulative_return ?? m.total_return)}
                />
                <Kpi
                  label="最大回撤"
                  value={pct(m.max_drawdown)}
                  className={tone(m.max_drawdown)}
                />
                <Kpi label="夏普" value={num(m.sharpe)} className="text-slate-800" />
                <Kpi
                  label="超额"
                  value={pct(item.snapshot.excess_return)}
                  className={tone(item.snapshot.excess_return)}
                />
              </div>
              <div className="flex min-h-[380px] items-center rounded-2xl bg-white/90 p-4 ring-1 ring-orange-100 sm:p-6">
                <div className="w-full">
                  <PlazaEquityChart
                    equity={item.snapshot.equity_curve}
                    benchmark={item.snapshot.benchmark_curve}
                    height={340}
                    showExcess
                  />
                </div>
              </div>
            </div>
          ) : null}

          {tab === "code" ? (
            item.snapshot.strategy_code ? (
              <pre className="community-code-block max-h-[70vh] overflow-auto rounded-2xl bg-slate-950 p-4 text-[13px] leading-relaxed text-slate-100 ring-1 ring-slate-800">
                <code
                  className="hljs language-python"
                  dangerouslySetInnerHTML={{ __html: codeHtml }}
                />
              </pre>
            ) : (
              <div className="rounded-2xl bg-white/90 px-4 py-16 text-center text-sm text-slate-500 ring-1 ring-orange-100">
                未附带源码
              </div>
            )
          ) : null}

          {tab === "run" ? (
            <div className="space-y-5">
              <div className="rounded-2xl bg-gradient-to-br from-white via-slate-50 to-slate-100/80 px-5 py-10 ring-1 ring-slate-200/70 sm:px-6">
                <div className="flex flex-col items-center gap-3 text-center">
                  <button
                    type="button"
                    disabled={runBusy}
                    onClick={() => void runFast()}
                    className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-red-500 to-amber-500 px-8 py-3.5 text-sm font-semibold text-white shadow-lg shadow-rose-200/60 transition hover:brightness-105 disabled:opacity-60"
                  >
                    {runBusy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Zap className="h-4 w-4" />
                    )}
                    {runBusy ? "运行中…" : "极速运行"}
                  </button>
                  {runErr ? (
                    <p className="text-sm text-red-600">{runErr}</p>
                  ) : null}
                </div>
              </div>

              {runResult ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                    <Kpi
                      label="年化收益"
                      value={pct(liveM.annual_return as number | null)}
                      className={tone(liveM.annual_return as number | null)}
                    />
                    <Kpi
                      label="累计收益"
                      value={pct(
                        (liveM.cumulative_return ?? liveM.total_return) as
                          | number
                          | null,
                      )}
                      className={tone(
                        (liveM.cumulative_return ?? liveM.total_return) as
                          | number
                          | null,
                      )}
                    />
                    <Kpi
                      label="最大回撤"
                      value={pct(liveM.max_drawdown as number | null)}
                      className={tone(liveM.max_drawdown as number | null)}
                    />
                    <Kpi
                      label="夏普"
                      value={num(liveM.sharpe as number | null)}
                      className="text-slate-800"
                    />
                    <Kpi
                      label="超额"
                      value={pct(runResult.excess_return)}
                      className={tone(runResult.excess_return)}
                    />
                  </div>
                  <div className="flex min-h-[400px] items-center rounded-2xl bg-white p-4 ring-1 ring-slate-200/70 sm:p-6">
                    <div className="w-full">
                      <PlazaEquityChart
                        equity={liveEquity}
                        benchmark={liveBench}
                        height={360}
                        showExcess
                      />
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
