import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { createStrategyPlazaItem, type PlazaCurvePoint } from "@/lib/strategyPlazaApi";
import type { YgBacktestResponse, YgCurvePoint, YgStrategyBacktestRequest } from "@/lib/ygApi";

function normalizeCurve(points: YgCurvePoint[] | null | undefined): PlazaCurvePoint[] {
  return (points || []).map((point) => ({
    date: point.date,
    value: point.value,
    ...(point.drawdown == null ? {} : { drawdown: point.drawdown }),
  }));
}

type Props = {
  open: boolean;
  onClose: () => void;
  runId: string;
  defaultTitle: string;
  rangeLabel?: string;
  universeLabel?: string;
  benchmarkLabel?: string;
  request?: YgStrategyBacktestRequest | null;
  result?: YgBacktestResponse | null;
};

export function StrategyPlazaShareDialog({
  open,
  onClose,
  runId,
  defaultTitle,
  rangeLabel,
  universeLabel,
  benchmarkLabel,
  request,
  result,
}: Props) {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle(defaultTitle.slice(0, 120));
    setBody("");
    setErr(null);
    setBusy(false);
  }, [open, defaultTitle]);

  if (!open) return null;

  const submit = async () => {
    const t = title.trim();
    if (!t) {
      setErr("请填写标题");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const item = await createStrategyPlazaItem({
        title: t,
        body: body.trim(),
        source_run_id: runId,
        snapshot: {
          metrics: result?.metrics || {},
          excess_return: result?.excess_return ?? null,
          equity_curve: normalizeCurve(result?.equity_curve),
          benchmark_curve: normalizeCurve(result?.benchmark_curve),
          date_range: result?.date_range || {
            start: request?.start || undefined,
            end: request?.end || undefined,
          },
          universe: request?.universe || null,
          benchmark: request?.benchmark || null,
          universe_label: universeLabel || null,
          benchmark_label: benchmarkLabel || null,
          // 内置策略只按 RE ID 执行，源码快照不进入用户可见的策略广场。
          strategy_code: request?.strategy_id ? null : request?.strategy_code || null,
          range_label: rangeLabel || null,
        },
      });
      onClose();
      navigate(`/strategy/plaza/${item.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "分享失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]"
        aria-label="关闭"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-slate-200">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-base font-semibold text-slate-900">分享到策略广场</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">标题</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value.slice(0, 120))}
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-slate-600">内容</span>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value.slice(0, 4000))}
              rows={5}
              className="mt-1 w-full resize-y rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100"
            />
          </label>
          {err ? <p className="text-sm text-red-600">{err}</p> : null}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
            disabled={busy}
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy}
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {busy ? "发布中…" : "发布"}
          </button>
        </div>
      </div>
    </div>
  );
}
