import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  deleteStrategyRun,
  getStrategyProject,
  listStrategyRuns,
  optionLabel,
  STRATEGY_UNIVERSE_OPTIONS,
  type StrategyProject,
  type StrategyRunRecord,
} from "@/lib/strategyStore";
import { useConfirm } from "@/components/ConfirmDialog";

function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}
function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(2);
}

function runUniverse(r: StrategyRunRecord): string {
  const req = r.request as Record<string, unknown> | undefined;
  const meta = (r.result as { meta?: Record<string, unknown> } | undefined)?.meta;
  const code =
    (typeof req?.universe === "string" && req.universe) ||
    (typeof meta?.universe === "string" && meta.universe) ||
    "";
  return optionLabel(code, STRATEGY_UNIVERSE_OPTIONS);
}

export function StrategyHistoryPage() {
  const { projectId = "" } = useParams();
  const confirm = useConfirm();
  const [project, setProject] = useState<StrategyProject | null>(null);
  const [runs, setRuns] = useState<StrategyRunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    setErr(null);
    void (async () => {
      try {
        const [p, list] = await Promise.all([
          getStrategyProject(projectId),
          listStrategyRuns(projectId),
        ]);
        setProject(p);
        setRuns(list);
      } catch (e) {
        setProject(null);
        setRuns([]);
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  };

  useEffect(() => {
    refresh();
  }, [projectId]);

  if (loading && !project) {
    return <div className="p-10 text-center text-slate-400">加载中…</div>;
  }

  if (!project && !loading) {
    return (
      <div className="p-10 text-center text-slate-500">
        {err || "项目不存在"} ·{" "}
        <Link to="/strategy/research" className="text-blue-600">
          返回
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1100px] px-4 py-6 lg:px-6 lg:py-8">
        <p className="text-xs text-slate-400">
          <Link to="/strategy/research" className="hover:text-slate-600">
            策略研究
          </Link>
          {" / "}
          <Link
            to={`/strategy/research/${projectId}`}
            className="hover:text-slate-600"
          >
            {project?.name || "…"}
          </Link>
          {" / 历史记录"}
        </p>
        <h1 className="mt-2 text-xl font-bold text-slate-900 lg:text-2xl">
          {project?.name || "…"} · 回测历史
        </h1>

        <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-3 py-3 sm:px-4">回测时间</th>
                <th className="px-3 py-3 sm:px-4">股票池</th>
                <th className="px-3 py-3 sm:px-4">年化</th>
                <th className="hidden px-4 py-3 lg:table-cell">夏普</th>
                <th className="hidden px-4 py-3 lg:table-cell">最大回撤</th>
                <th className="hidden px-4 py-3 lg:table-cell">耗时</th>
                <th className="px-3 py-3 text-right sm:px-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-16 text-center text-slate-400">
                    加载中…
                  </td>
                </tr>
              ) : (
                <>
                  {runs.map((r) => {
                    const m = r.result.metrics || {};
                    return (
                      <tr key={r.id} className="border-t border-slate-100">
                        <td className="px-3 py-3 font-mono text-xs text-slate-600 sm:px-4">
                          {String(r.finishedAt || "")
                            .replace("T", " ")
                            .slice(0, 19)}
                        </td>
                        <td className="px-3 py-3 text-slate-700 sm:px-4">
                          {runUniverse(r)}
                        </td>
                        <td className="px-3 py-3 tabular-nums sm:px-4">
                          {pct(m.annual_return)}
                        </td>
                        <td className="hidden px-4 py-3 tabular-nums lg:table-cell">
                          {num(m.sharpe)}
                        </td>
                        <td className="hidden px-4 py-3 tabular-nums text-red-600 lg:table-cell">
                          {pct(m.max_drawdown)}
                        </td>
                        <td className="hidden px-4 py-3 tabular-nums text-slate-600 lg:table-cell">
                          {r.elapsedSec}s
                        </td>
                        <td className="px-3 py-3 text-right text-xs sm:px-4">
                          <Link
                            to={`/strategy/research/report/${r.id}`}
                            className="mr-2 font-medium text-blue-600 hover:underline sm:mr-3"
                          >
                            报告
                          </Link>
                          <button
                            type="button"
                            onClick={() => {
                              void (async () => {
                                const ok = await confirm({
                                  title: "删除记录",
                                  message: "删除这条回测记录？",
                                  confirmLabel: "删除",
                                  danger: true,
                                });
                                if (ok) void deleteStrategyRun(r.id).then(refresh);
                              })();
                            }}
                            className="font-medium text-red-600 hover:underline"
                          >
                            删除
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {!runs.length && (
                    <tr>
                      <td
                        colSpan={7}
                        className="px-4 py-16 text-center text-slate-400"
                      >
                        暂无历史 ·{" "}
                        <Link
                          to={`/strategy/research/${projectId}`}
                          className="text-blue-600"
                        >
                          去回测
                        </Link>
                      </td>
                    </tr>
                  )}
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
