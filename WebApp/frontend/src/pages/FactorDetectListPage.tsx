import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Pencil, Plus, Trash2 } from "lucide-react";
import {
  clearDetectClientCache,
  createProject,
  deleteProject,
  listVisibleProjects,
  openDetectPlaceholderTab,
  navigateDetectTab,
  saveProject,
  type DetectProject,
} from "@/lib/detectStore";
import { getStoredUser, subscribeAuth } from "@/lib/auth";
import { PagerBar } from "@/components/PageJump";

const PAGE_SIZE = 20;

export function FactorDetectListPage() {
  const [projects, setProjects] = useState<DetectProject[]>([]);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [nameModal, setNameModal] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [renameTarget, setRenameTarget] = useState<DetectProject | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameErr, setRenameErr] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DetectProject | null>(null);
  const [batchDeleteIds, setBatchDeleteIds] = useState<string[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [deleting, setDeleting] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    setErr(null);
    void listVisibleProjects()
      .then((list) => {
        setProjects(list);
        setSelectedIds((prev) => {
          const next = new Set<string>();
          for (const id of prev) {
            if (list.some((p) => p.id === id && !p.sample)) next.add(id);
          }
          return next;
        });
      })
      .catch((e) => {
        setProjects([]);
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
      clearDetectClientCache();
      setSelectedIds(new Set());
      setPage(1);
      refresh();
    });
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.factorName.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q),
    );
  }, [projects, query]);

  useEffect(() => {
    setPage(1);
  }, [query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE) || 1);
  const pageSafe = Math.min(Math.max(1, page), totalPages);
  const pageRows = useMemo(() => {
    const start = (pageSafe - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, pageSafe]);

  const deletableFiltered = useMemo(
    () => pageRows.filter((p) => !p.sample),
    [pageRows],
  );

  const allDeletableSelected =
    deletableFiltered.length > 0 &&
    deletableFiltered.every((p) => selectedIds.has(p.id));

  const toggleOne = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleAll = (checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const p of deletableFiltered) {
        if (checked) next.add(p.id);
        else next.delete(p.id);
      }
      return next;
    });
  };

  const openCreate = () => {
    setProjectName("");
    setCreateErr(null);
    setNameModal(true);
  };

  const confirmCreate = () => {
    const title = projectName.trim();
    if (!title) {
      setCreateErr("请填写检测名称");
      return;
    }
    const tab = openDetectPlaceholderTab();
    void createProject("custom_combo", title, title)
      .then((p) => {
        setNameModal(false);
        setProjectName("");
        setCreateErr(null);
        navigateDetectTab(tab, p.id);
        refresh();
      })
      .catch((e) => {
        try {
          tab?.close();
        } catch {
          /* ignore */
        }
        setCreateErr(e instanceof Error ? e.message : String(e));
      });
  };

  const openRename = (p: DetectProject) => {
    setRenameTarget(p);
    setRenameValue(p.name);
    setRenameErr(null);
  };

  const confirmRename = () => {
    if (!renameTarget) return;
    const title = renameValue.trim();
    if (!title) {
      setRenameErr("名称不能为空");
      return;
    }
    void saveProject({
      ...renameTarget,
      name: title,
      description: title,
    })
      .then(() => {
        setRenameTarget(null);
        setRenameValue("");
        setRenameErr(null);
        refresh();
      })
      .catch((e) => setRenameErr(e instanceof Error ? e.message : String(e)));
  };

  const confirmBatchDelete = () => {
    if (!batchDeleteIds?.length) return;
    setDeleting(true);
    void Promise.all(batchDeleteIds.map((id) => deleteProject(id)))
      .then(() => {
        setBatchDeleteIds(null);
        setSelectedIds(new Set());
        refresh();
      })
      .catch((e) => window.alert(e instanceof Error ? e.message : String(e)))
      .finally(() => setDeleting(false));
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1200px] px-4 py-6 lg:px-6 lg:py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">因子检测</h1>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2 lg:gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索检测名称…"
            className="w-full max-w-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200 lg:max-w-md"
          />
          {selectedIds.size > 0 ? (
            <button
              type="button"
              onClick={() => setBatchDeleteIds([...selectedIds])}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 shadow-sm hover:bg-red-50"
            >
              <Trash2 className="h-4 w-4" />
              删除所选（{selectedIds.size}）
            </button>
          ) : null}
          <div className="flex w-full flex-wrap items-center gap-2 lg:ml-auto lg:w-auto">
            <button
              type="button"
              onClick={openCreate}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              新建检测
            </button>
            <Link
              to="/factor/library"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-50"
            >
              <FileText className="h-4 w-4" />
              查看因子库
            </Link>
          </div>
        </div>

        {err && <p className="mb-3 text-sm text-red-600">{err}</p>}
        {loading ? (
          <p className="py-16 text-center text-sm text-slate-400">加载中…</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={allDeletableSelected}
                      disabled={!deletableFiltered.length}
                      onChange={(e) => toggleAll(e.target.checked)}
                      aria-label="全选可删除项"
                      className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40"
                    />
                  </th>
                  <th className="px-4 py-3">检测名称</th>
                  <th className="hidden px-4 py-3 lg:table-cell">类型</th>
                  <th className="hidden px-4 py-3 lg:table-cell">最后修改时间</th>
                  <th className="hidden px-4 py-3 lg:table-cell">检测次数</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((p) => (
                  <tr key={p.id} className="border-t border-slate-100">
                    <td className="px-4 py-3">
                      {!p.sample ? (
                        <input
                          type="checkbox"
                          checked={selectedIds.has(p.id)}
                          onChange={(e) => toggleOne(p.id, e.target.checked)}
                          aria-label={`选择 ${p.name}`}
                          className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                        />
                      ) : null}
                    </td>
                    <td className="max-w-[280px] px-4 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <p
                          className="truncate font-semibold text-slate-900"
                          title={p.name}
                        >
                          {p.name}
                        </p>
                        {p.sample ? (
                          <span className="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                            样例
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 lg:table-cell">
                      <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                        股票
                      </span>
                    </td>
                    <td className="hidden px-4 py-3 font-mono text-xs text-slate-600 lg:table-cell">
                      {p.updatedAt?.replace("T", " ").slice(0, 19)}
                    </td>
                    <td className="hidden px-4 py-3 tabular-nums text-slate-700 lg:table-cell">{p.runCount}</td>
                    <td className="px-4 py-3 text-right text-xs">
                      <Link
                        to={`/factor/detect/${p.id}`}
                        className="mr-3 font-medium text-blue-600 hover:underline"
                      >
                        检测
                      </Link>
                      <Link
                        to={`/factor/detect/${p.id}/history`}
                        className="mr-3 font-medium text-blue-600 hover:underline"
                      >
                        检测列表
                      </Link>
                      {!p.sample ? (
                        <>
                          <button
                            type="button"
                            className="mr-3 inline-flex align-middle text-slate-400 hover:text-blue-600"
                            onClick={() => openRename(p)}
                            title="改名"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            className="inline-flex text-slate-400 hover:text-red-600"
                            onClick={() => setDeleteTarget(p)}
                            title="删除"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={6} className="px-4 py-16 text-center text-slate-400">
                      暂无项目，点击「新建检测」开始
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {!loading && filtered.length > 0 ? (
          <div className="mt-4 flex flex-col items-center gap-2 sm:flex-row sm:justify-between">
            <p className="text-xs text-slate-500">
              共 {filtered.length} 条 · 第 {pageSafe}/{totalPages} 页
            </p>
            <PagerBar page={pageSafe} totalPages={totalPages} onJump={setPage} />
          </div>
        ) : null}

        {nameModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
              <h2 className="text-lg font-bold text-slate-900">新建检测</h2>
              <input
                className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="检测名称"
                autoFocus
              />
              {createErr && <p className="mt-2 text-xs text-red-600">{createErr}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  onClick={() => setNameModal(false)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white"
                  onClick={confirmCreate}
                >
                  创建
                </button>
              </div>
            </div>
          </div>
        )}

        {renameTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
              <h2 className="text-lg font-bold text-slate-900">重命名检测</h2>
              <input
                className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") confirmRename();
                }}
                placeholder="检测名称"
                autoFocus
              />
              {renameErr && <p className="mt-2 text-xs text-red-600">{renameErr}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  onClick={() => setRenameTarget(null)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white"
                  onClick={confirmRename}
                >
                  保存
                </button>
              </div>
            </div>
          </div>
        )}

        {deleteTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
            <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl">
              <p className="text-sm text-slate-700">
                确认删除「{deleteTarget.name}」？检测记录将一并删除。
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-lg px-3 py-2 text-sm"
                  onClick={() => setDeleteTarget(null)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white"
                  onClick={() => {
                    void deleteProject(deleteTarget.id).then(() => {
                      setDeleteTarget(null);
                      setSelectedIds((prev) => {
                        const next = new Set(prev);
                        next.delete(deleteTarget.id);
                        return next;
                      });
                      refresh();
                    });
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        )}

        {batchDeleteIds && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
            <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl">
              <p className="text-sm text-slate-700">
                确认删除所选 {batchDeleteIds.length} 个检测？检测记录将一并删除。
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-lg px-3 py-2 text-sm"
                  disabled={deleting}
                  onClick={() => setBatchDeleteIds(null)}
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={deleting}
                  className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  onClick={confirmBatchDelete}
                >
                  {deleting ? "删除中…" : "删除"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
