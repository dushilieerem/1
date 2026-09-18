import { useId, useMemo } from "react";
import { Link } from "react-router-dom";
import { QUANTILE_PALETTE } from "@/components/chartTheme";

/** 浅色弥散光背景 */
export function SoftMeshBackground({ tone = "light" }: { tone?: "light" | "mist" }) {
  const base = tone === "mist" ? "bg-[#f5f8fc]" : "bg-[#f5f8fc]";
  return (
    <div className="absolute inset-0 overflow-hidden" aria-hidden>
      <div className={`absolute inset-0 ${base}`} />
      <div
        className="absolute left-1/2 top-[-10%] h-[70%] w-[90%] -translate-x-1/2"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(255,255,255,0.95) 0%, rgba(245,248,252,0) 70%)",
        }}
      />
      <div className="landing-blob absolute -left-28 -top-24 h-[480px] w-[480px] rounded-full bg-[#fda4af]/28 blur-3xl" />
      <div className="landing-blob-delay absolute right-[-100px] top-10 h-[420px] w-[420px] rounded-full bg-[#7dd3fc]/32 blur-3xl" />
      <div className="landing-blob absolute bottom-[-120px] left-[30%] h-[380px] w-[380px] rounded-full bg-[#bbf7d0]/22 blur-3xl" />
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(100,116,139,0.12) 1px, transparent 0)",
          backgroundSize: "22px 22px",
        }}
      />
    </div>
  );
}

function seriesToPath(values: number[], w: number, h: number, pad = 12) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (w - pad * 2);
      const y = pad + (1 - (v - min) / span) * (h - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function seriesPoints(values: number[], w: number, h: number, pad = 12) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / span) * (h - pad * 2);
    return { x, y };
  });
}

/** Hero：净值折线（红/蓝） */
export function AnimatedEquityChart({
  title = "策略净值对比",
  className = "",
}: {
  title?: string;
  className?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const strat = useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => {
        const t = i / 35;
        return 1 + t * 0.42 + Math.sin(i * 0.45) * 0.03 + (i > 20 ? 0.08 : 0);
      }),
    [],
  );
  const bench = useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => {
        const t = i / 35;
        return 1 + t * 0.18 + Math.sin(i * 0.35 + 1) * 0.02;
      }),
    [],
  );
  const w = 420;
  const h = 140;
  const stratPath = seriesToPath(strat, w, h, 10);
  const benchPath = seriesToPath(bench, w, h, 10);

  return (
    <div
      className={`flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white/90 shadow-[0_18px_40px_-28px_rgba(15,23,42,0.28)] backdrop-blur-sm ${className}`}
    >
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-2">
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        <div className="flex items-center gap-3 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <i className="h-1.5 w-3 rounded-full bg-red-500" />
            策略
          </span>
          <span className="inline-flex items-center gap-1">
            <i className="h-1.5 w-3 rounded-full bg-sky-500" />
            基准
          </span>
        </div>
      </div>
      <div className="min-h-0 flex-1 px-2 pb-2 pt-1">
        <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" preserveAspectRatio="none" fill="none" aria-hidden>
          <defs>
            <linearGradient id={`eqFill-${uid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[35, 70, 105].map((y) => (
            <line key={y} x1="8" x2={w - 8} y1={y} y2={y} stroke="#e2e8f0" strokeWidth="1" />
          ))}
          <path
            d={`${stratPath} L${w - 10} ${h - 10} L10 ${h - 10} Z`}
            fill={`url(#eqFill-${uid})`}
            className="landing-eq-fill"
          />
          <path
            d={benchPath}
            stroke="#0ea5e9"
            strokeWidth="2"
            strokeLinecap="round"
            className="landing-eq-line-bench"
          />
          <path
            d={stratPath}
            stroke="#ef4444"
            strokeWidth="2.5"
            strokeLinecap="round"
            className="landing-eq-line-strat"
          />
        </svg>
      </div>
    </div>
  );
}

/** Hero：分层柱，使用平台 QUANTILE_PALETTE 五色 */
export function AnimatedLayerChart({
  title = "因子分层累计收益",
  className = "",
}: {
  title?: string;
  className?: string;
}) {
  const heights = [38, 52, 48, 72, 100];
  const colors = QUANTILE_PALETTE.slice(0, 5);
  return (
    <div
      className={`flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white/90 shadow-[0_18px_40px_-28px_rgba(15,23,42,0.28)] backdrop-blur-sm ${className}`}
    >
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-2">
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        <p className="font-mono text-[11px] text-emerald-600">Rank IC 0.068</p>
      </div>
      <div className="flex min-h-0 flex-1 items-end gap-3 px-5 pb-2 pt-3">
        {heights.map((h, i) => (
          <div key={i} className="flex h-full min-h-0 flex-1 flex-col justify-end gap-1">
            <div
              className="landing-layer-breath w-full rounded-t-md"
              style={{
                height: `${h}%`,
                background: colors[i],
                animationDelay: `${i * 0.18}s`,
              }}
            />
            <span className="shrink-0 text-center font-mono text-[10px] text-slate-400">Q{i + 1}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 社区：循环描边面积图 */
export function CommunityAreaSpark({
  title,
  ret,
  ctaTo,
  onGate,
  className = "",
}: {
  title: string;
  ret: string;
  ctaTo: string;
  onGate: (path: string) => string;
  className?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const vals = useMemo(
    () =>
      Array.from({ length: 28 }, (_, i) => {
        const t = i / 27;
        return 1 + t * 0.38 + Math.sin(i * 0.62) * 0.05 + Math.cos(i * 0.22) * 0.025;
      }),
    [],
  );
  const w = 360;
  const h = 110;
  const path = seriesToPath(vals, w, h, 8);
  const pts = seriesPoints(vals, w, h, 8);
  const last = pts[pts.length - 1];

  return (
    <div
      className={`landing-card-hover flex min-h-0 flex-1 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_36px_-28px_rgba(15,23,42,0.28)] ${className}`}
    >
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <p className="font-medium text-slate-900">{title}</p>
        <p className="font-mono text-sm font-semibold text-red-600">{ret}</p>
      </div>
      <div className="min-h-0 flex-1">
        <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" preserveAspectRatio="none" fill="none" aria-hidden>
          <defs>
            <linearGradient id={`area-${uid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.38" />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <path
            d={`${path} L${w - 8} ${h - 8} L8 ${h - 8} Z`}
            fill={`url(#area-${uid})`}
            className="landing-comm-area-fill"
          />
          <path
            d={path}
            stroke="#e11d48"
            strokeWidth="2.4"
            strokeLinecap="round"
            className="landing-comm-area-line"
          />
          <circle
            cx={last.x}
            cy={last.y}
            r="4.5"
            fill="#e11d48"
            className="landing-comm-dot"
          />
        </svg>
      </div>
      <div className="mt-2 flex shrink-0 justify-end">
        <Link
          to={onGate(ctaTo)}
          className="landing-wiggle-hover inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500"
        >
          去验证 →
        </Link>
      </div>
    </div>
  );
}

/** 社区：循环生长的五色横向条 */
export function CommunityHBarSpark({
  title,
  ret,
  ctaTo,
  onGate,
  className = "",
}: {
  title: string;
  ret: string;
  ctaTo: string;
  onGate: (path: string) => string;
  className?: string;
}) {
  const rows = [
    { q: "Q1", w: 28 },
    { q: "Q2", w: 42 },
    { q: "Q3", w: 55 },
    { q: "Q4", w: 70 },
    { q: "Q5", w: 92 },
  ];
  const colors = QUANTILE_PALETTE.slice(0, 5);
  return (
    <div
      className={`landing-card-hover flex min-h-0 flex-1 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_36px_-28px_rgba(15,23,42,0.28)] ${className}`}
    >
      <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
        <p className="font-medium text-slate-900">{title}</p>
        <p className="font-mono text-sm font-semibold text-red-600">{ret}</p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col justify-center gap-2.5">
        {rows.map((r, i) => (
          <div key={r.q} className="flex items-center gap-2">
            <span className="w-6 font-mono text-[10px] text-slate-400">{r.q}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="landing-hbar-loop h-full rounded-full"
                style={{
                  width: `${r.w}%`,
                  background: colors[i],
                  animationDelay: `${i * 0.14}s`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex shrink-0 justify-end">
        <Link
          to={onGate(ctaTo)}
          className="landing-wiggle-hover inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500"
        >
          去验证 →
        </Link>
      </div>
    </div>
  );
}
