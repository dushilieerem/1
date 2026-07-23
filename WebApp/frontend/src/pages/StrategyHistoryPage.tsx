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
      <div className="mx-auto max-w-[1100px] px-6 py-8">
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
        <h1 className="mt-2 text-2xl font-bold text-slate-900">
          {project?.name || "…"} · 回测历史
        </h1>

        <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">回测时间</th>
                <th className="px-4 py-3">股票池</th>
                <th className="px-4 py-3">年化</th>
                <th className="px-4 py-3">夏普</th>
                <th className="px-4 py-3">最大回撤</th>
                <th className="px-4 py-3">耗时</th>
                <th className="px-4 py-3 text-right">操作</th>
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
                        <td className="px-4 py-3 font-mono text-xs text-slate-600">
                          {String(r.finishedAt || "")
                            .replace("T", " ")
                            .slice(0, 19)}
                        </td>
                        <td className="px-4 py-3 text-slate-700">
                          {runUniverse(r)}
                        </td>
                        <td className="px-4 py-3 tabular-nums">
                          {pct(m.annual_return)}
                        </td>
                        <td className="px-4 py-3 tabular-nums">{num(m.sharpe)}</td>
                        <td className="px-4 py-3 tabular-nums text-red-600">
                          {pct(m.max_drawdown)}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-slate-600">
                          {r.elapsedSec}s
                        </td>
                        <td className="px-4 py-3 text-right text-xs">
                          <Link
                            to={`/strategy/research/report/${r.id}`}
                            className="mr-3 font-medium text-blue-600 hover:underline"
                          >
                            查看报告
                          </Link>
                          <button
                            type="button"
                            onClick={() => {
                              if (window.confirm("删除这条回测记录？")) {
                                void deleteStrategyRun(r.id).then(refresh);
                              }
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
