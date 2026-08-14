import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  deleteRun,
  formatDetectRunFactorsLabel,
  getProject,
  listRuns,
  peekProject,
  type DetectProject,
  type DetectRunRecord,
} from "@/lib/detectStore";
import { useConfirm } from "@/components/ConfirmDialog";

function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}
function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(2);
}

export function FactorDetectHistoryPage() {
  const { projectId = "" } = useParams();
  const confirm = useConfirm();
  const [project, setProject] = useState<DetectProject | null | undefined>(() =>
    projectId ? peekProject(projectId) ?? undefined : undefined,
  );
  const [runs, setRuns] = useState<DetectRunRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    const cached = peekProject(projectId);
    if (cached) setProject(cached);
    void (async () => {
      const [p, list] = await Promise.all([getProject(projectId), listRuns(projectId)]);
      setProject(p ?? null);
      setRuns(list);
      setLoading(false);
    })();
  };

  useEffect(() => {
    refresh();
  }, [projectId]);

  if (project === undefined && loading) {
    return <div className="p-10 text-center text-slate-400">加载中…</div>;
  }

  if (!project && !loading) {
    return (
      <div className="p-10 text-center text-slate-500">
        项目不存在 ·{" "}
        <Link to="/factor/detect" className="text-blue-600">
          返回
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1100px] px-4 py-6 lg:px-6 lg:py-8">
        <p className="text-xs text-slate-400">
          <Link to="/factor/detect" className="hover:text-slate-600">
            因子检测
          </Link>
          {" / "}
          <Link to={`/factor/detect/${projectId}`} className="hover:text-slate-600">
            {project?.name || "…"}
          </Link>
          {" / 检测列表"}
        </p>
        <h1 className="mt-2 text-xl font-bold text-slate-900 lg:text-2xl">
          {project?.name || "…"} · 检测历史
        </h1>

        <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">检测时间</th>
                <th className="px-4 py-3">因子</th>
                <th className="hidden px-4 py-3 lg:table-cell">IC均值</th>
                <th className="hidden px-4 py-3 lg:table-cell">IR / Sharpe</th>
                <th className="hidden px-4 py-3 lg:table-cell">耗时</th>
                <th className="px-4 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center text-slate-400">
                    加载中…
                  </td>
                </tr>
              ) : (
                <>
                  {runs.map((r) => {
                    const m = r.result.metrics || {};
                    const ic = m.ic ?? m.rank_ic ?? r.result.factor_analysis?.ic_mean;
                    return (
                      <tr key={r.id} className="border-t border-slate-100">
                        <td className="px-4 py-3 font-mono text-xs text-slate-600">
                          {String(r.finishedAt || "").replace("T", " ").slice(0, 19)}
                        </td>
                        <td className="px-4 py-3">
                          <p
                            className="max-w-[240px] truncate font-semibold text-slate-900"
                            title={formatDetectRunFactorsLabel(r)}
                          >
                            {formatDetectRunFactorsLabel(r)}
                          </p>
                        </td>
                        <td className="hidden px-4 py-3 tabular-nums lg:table-cell">
                          {pct(typeof ic === "number" ? ic : null)}
                        </td>
                        <td className="hidden px-4 py-3 tabular-nums lg:table-cell">{num(m.sharpe)}</td>
                        <td className="hidden px-4 py-3 tabular-nums text-slate-600 lg:table-cell">
                          {Math.round((r.elapsedSec || 0) * 1000)}ms
                        </td>
                        <td className="px-4 py-3 text-right text-xs">
                          <div className="flex flex-col items-end gap-1 sm:flex-row sm:flex-wrap sm:justify-end sm:gap-x-3 sm:gap-y-1">
                            <Link
                              to={`/factor/detect/report/${r.id}`}
                              className="py-1 font-medium text-blue-600 hover:underline"
                            >
                              查看报告
                            </Link>
                            <Link
                              to={`/factor/detect/${projectId}?runId=${encodeURIComponent(r.id)}`}
                              className="py-1 font-medium text-blue-600 hover:underline"
                            >
                              打开配置
                            </Link>
                            <button
                              type="button"
                              onClick={() => {
                                void (async () => {
                                  const ok = await confirm({
                                    title: "删除记录",
                                    message: "删除这条检测记录？",
                                    confirmLabel: "删除",
                                    danger: true,
                                  });
                                  if (ok) void deleteRun(r.id).then(refresh);
                                })();
                              }}
                              className="py-1 font-medium text-red-600 hover:underline"
                            >
                              删除
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {!runs.length && (
                    <tr>
                      <td colSpan={6} className="px-4 py-16 text-center text-slate-400">
                        暂无历史 ·{" "}
                        <Link to={`/factor/detect/${projectId}`} className="text-blue-600">
                          去检测
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
