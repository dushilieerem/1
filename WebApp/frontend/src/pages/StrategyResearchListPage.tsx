import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FileText, Search, Trash2, X } from "lucide-react";
import {
  clearStrategyClientCache,
  deleteStrategyRun,
  listAllStrategyRuns,
  updateStrategyRunFlagged,
  updateStrategyRunRemark,
  type StrategyRunRecord,
} from "@/lib/strategyStore";
import { getStoredUser, prepareAuthHandoff, subscribeAuth } from "@/lib/auth";
import { PagerBar } from "@/components/PageJump";
import { useConfirm } from "@/components/ConfirmDialog";

const PAGE_SIZE = 20;

function fmtTime(iso: string) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  } catch {
    return iso;
  }
}

function runLabel(r: StrategyRunRecord): string {
  const name = (r.name || "").trim();
  if (name) return name;
  const desc = (r.description || "").trim();
  if (desc) return desc;
  return r.id.slice(0, 8);
}

export function StrategyResearchListPage() {
  const confirm = useConfirm();
  const [searchParams] = useSearchParams();
  const filterProjectId = searchParams.get("projectId")?.trim() || "";
  const [runs, setRuns] = useState<StrategyRunRecord[]>([]);
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [editingRemarkId, setEditingRemarkId] = useState<string | null>(null);
  const [remarkDraft, setRemarkDraft] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    setErr(null);
    void listAllStrategyRuns()
      .then(setRuns)
      .catch((e) => {
        setRuns([]);
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    let lastUid = getStoredUser()?.id ?? null;
    return subscribeAuth(() => {
      const uid = getStoredUser()?.id ?? null;
      if (uid === lastUid) return;
      lastUid = uid;
      clearStrategyClientCache();
      setPage(1);
      refresh();
    });
  }, []);

  const filtered = useMemo(() => {
    let list = runs;
    if (filterProjectId) {
      list = list.filter((r) => r.projectId === filterProjectId);
    }
    if (flaggedOnly) {
      list = list.filter((r) => Boolean(r.flagged));
    }
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((r) => {
      const label = runLabel(r).toLowerCase();
      const remark = (r.remark || "").toLowerCase();
      return label.includes(q) || remark.includes(q);
    });
  }, [runs, query, filterProjectId, flaggedOnly]);

  useEffect(() => {
    setPage(1);
  }, [query, flaggedOnly]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE) || 1);
  const pageSafe = Math.min(Math.max(1, page), totalPages);
  const pageRows = useMemo(() => {
    const start = (pageSafe - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, pageSafe]);

  const saveRemark = async (runId: string) => {
    setBusyId(runId);
    try {
      const updated = await updateStrategyRunRemark(runId, remarkDraft);
      setRuns((prev) =>
        prev.map((r) =>
          r.id === runId ? { ...r, remark: updated.remark ?? remarkDraft } : r,
        ),
      );
      setEditingRemarkId(null);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const toggleFlag = async (run: StrategyRunRecord) => {
    const next = !run.flagged;
    setBusyId(run.id);
    try {
      const updated = await updateStrategyRunFlagged(run.id, next);
      setRuns((prev) =>
        prev.map((r) =>
          r.id === run.id ? { ...r, flagged: updated.flagged ?? next } : r,
        ),
      );
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (run: StrategyRunRecord) => {
    const label = runLabel(run);
    const ok = await confirm({
      title: "删除检测报告",
      message: `确定删除「${label}」这次回测记录？此操作不可恢复。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    setBusyId(run.id);
    try {
      await deleteStrategyRun(run.id);
      setRuns((prev) => prev.filter((r) => r.id !== run.id));
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-50 via-white to-blue-50/30">
      <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">检测报告</h1>
            {err ? <p className="mt-2 text-sm text-red-500">{err}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex min-w-[14rem] flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 sm:flex-none">
              <Search className="h-4 w-4 shrink-0 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索策略名、备注…"
                className="w-full min-w-0 bg-transparent text-sm outline-none sm:w-52"
              />
              {query ? (
                <button type="button" onClick={() => setQuery("")}>
                  <X className="h-3.5 w-3.5 text-slate-400" />
                </button>
              ) : null}
            </div>
            <Link
              to="/strategy/library"
              onClick={() => prepareAuthHandoff()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
            >
              <FileText className="h-4 w-4" />
              查看策略库
            </Link>
            <button
              type="button"
              onClick={() => setFlaggedOnly((v) => !v)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3.5 py-2 text-sm font-semibold transition ${
                flaggedOnly
                  ? "border-amber-300 bg-amber-50 text-amber-900"
                  : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
              }`}
            >
              <span aria-hidden>🚩</span>
              查看标记策略
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full table-fixed text-left text-sm">
              <colgroup>
                <col className="w-[22%]" />
                <col className="w-[18%]" />
                <col className="w-[28%]" />
                <col className="w-[32%]" />
              </colgroup>
              <thead className="border-b border-slate-100 bg-slate-50/80 text-xs font-semibold text-slate-500">
                <tr>
                  <th className="px-4 py-3">策略名</th>
                  <th className="px-4 py-3 whitespace-nowrap">测试时间</th>
                  <th className="px-4 py-3">备注</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-16 text-center text-slate-400"
                    >
                      加载中…
                    </td>
                  </tr>
                ) : pageRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-16 text-center text-slate-400"
                    >
                      {flaggedOnly
                        ? "暂无标记的检测报告。可在操作列点旗帜标记。"
                        : "暂无检测报告。可在策略库选择策略后点「检测」并完成回测。"}
                    </td>
                  </tr>
                ) : (
                  pageRows.map((r) => {
                    const label = runLabel(r);
                    const editing = editingRemarkId === r.id;
                    return (
                      <tr
                        key={r.id}
                        className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60"
                      >
                        <td className="px-4 py-3 align-middle">
                          <code className="break-all rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-800">
                            {label}
                          </code>
                        </td>
                        <td className="px-4 py-3 align-middle whitespace-nowrap text-slate-600">
                          {fmtTime(r.finishedAt)}
                        </td>
                        <td className="px-4 py-3 align-middle">
                          <div className="flex h-8 w-full min-w-0 items-center gap-1.5">
                            {editing ? (
                              <>
                                <input
                                  autoFocus
                                  value={remarkDraft}
                                  onChange={(e) => setRemarkDraft(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      e.preventDefault();
                                      void saveRemark(r.id);
                                    }
                                    if (e.key === "Escape") {
                                      setEditingRemarkId(null);
                                    }
                                  }}
                                  className="h-8 min-w-0 flex-1 rounded-lg border border-blue-300 bg-white px-2 text-xs outline-none"
                                  placeholder="备注"
                                />
                                <button
                                  type="button"
                                  disabled={busyId === r.id}
                                  onClick={() => void saveRemark(r.id)}
                                  className="w-8 shrink-0 text-xs font-medium text-blue-600 hover:underline disabled:opacity-40"
                                >
                                  保存
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  title="点击编辑备注"
                                  onClick={() => {
                                    setEditingRemarkId(r.id);
                                    setRemarkDraft(r.remark || "");
                                  }}
                                  className="h-8 min-w-0 flex-1 truncate rounded-lg border border-transparent px-2 text-left text-slate-600 hover:border-slate-200 hover:bg-white"
                                >
                                  {r.remark?.trim() ? (
                                    r.remark
                                  ) : (
                                    <span className="invisible select-none">备注</span>
                                  )}
                                </button>
                                <span className="w-8 shrink-0" aria-hidden />
                              </>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-middle">
                          <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-xs font-medium">
                            <button
                              type="button"
                              title={r.flagged ? "取消标记" : "标记为喜欢"}
                              disabled={busyId === r.id}
                              onClick={() => void toggleFlag(r)}
                              className={`inline-flex h-7 w-7 items-center justify-center rounded-lg text-sm transition disabled:opacity-40 ${
                                r.flagged
                                  ? "bg-amber-50 hover:bg-amber-100"
                                  : "opacity-40 grayscale hover:bg-slate-100 hover:opacity-100 hover:grayscale-0"
                              }`}
                            >
                              🚩
                            </button>
                            <Link
                              to={`/strategy/research/report/${r.id}`}
                              className="text-blue-600 hover:underline"
                            >
                              查看报告
                            </Link>
                            <Link
                              to={`/strategy/research/${r.projectId}?runId=${encodeURIComponent(r.id)}`}
                              className="text-blue-600 hover:underline"
                            >
                              查看配置
                            </Link>
                            <button
                              type="button"
                              disabled={busyId === r.id}
                              onClick={() => void onDelete(r)}
                              className="inline-flex items-center gap-0.5 text-red-500 hover:underline disabled:opacity-40"
                            >
                              <Trash2 className="h-3 w-3" />
                              删除
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          {totalPages > 1 ? (
            <div className="border-t border-slate-100 px-4 py-3">
              <PagerBar
                page={pageSafe}
                totalPages={totalPages}
                onJump={setPage}
              />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
