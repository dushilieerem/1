import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { getStoredUser, subscribeAuth } from "@/lib/auth";
import {
  clearStrategyClientCache,
  createStrategyProject,
  deleteStrategyProject,
  listVisibleStrategyProjects,
  openStrategyInNewTab,
  saveStrategyProject,
  type StrategyProject,
} from "@/lib/strategyStore";

export function StrategyResearchListPage() {
  const [projects, setProjects] = useState<StrategyProject[]>([]);
  const [query, setQuery] = useState("");
  const [nameModal, setNameModal] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [renameTarget, setRenameTarget] = useState<StrategyProject | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameErr, setRenameErr] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<StrategyProject | null>(null);
  const [batchDeleteIds, setBatchDeleteIds] = useState<string[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [deleting, setDeleting] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    setErr(null);
    void listVisibleStrategyProjects()
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
      clearStrategyClientCache();
      setSelectedIds(new Set());
      refresh();
    });
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = !q
      ? projects
      : projects.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.description.toLowerCase().includes(q),
        );
    // 样例始终沉底（与因子检测「5日动量样例」一致）
    return [...list].sort((a, b) => Number(!!a.sample) - Number(!!b.sample));
  }, [projects, query]);

  const deletableFiltered = useMemo(
    () => filtered.filter((p) => !p.sample),
    [filtered],
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
    void createStrategyProject(title)
      .then((p) => {
        setNameModal(false);
        setProjectName("");
        setCreateErr(null);
        openStrategyInNewTab(p.id);
        refresh();
      })
      .catch((e) => setCreateErr(e instanceof Error ? e.message : String(e)));
  };

  const openRename = (p: StrategyProject) => {
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
    void saveStrategyProject({
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
    void Promise.all(batchDeleteIds.map((id) => deleteStrategyProject(id)))
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
          <h1 className="text-2xl font-bold text-slate-900">策略研究</h1>
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
          </div>
        </div>

        {err && <p className="mb-3 text-sm text-red-600">{err}</p>}
        {loading && <p className="mb-3 text-sm text-slate-400">加载中…</p>}

        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={allDeletableSelected}
                    disabled={!deletableFiltered.length}
                    onChange={(e) => toggleAll(e.target.checked)}
                    aria-label="全选"
                    className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40"
                  />
                </th>
                <th className="px-4 py-3 font-medium">检测名称</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">最后修改</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">回测次数</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50/80">
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
                  <td className="px-4 py-3 font-medium text-slate-900">
                    <div className="flex items-center gap-2">
                      <span>{p.name}</span>
                      {p.sample ? (
                        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                          样例
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="hidden px-4 py-3 font-mono text-xs text-slate-600 lg:table-cell">
                    {p.updatedAt?.replace("T", " ").slice(0, 19)}
                  </td>
                  <td className="hidden px-4 py-3 tabular-nums text-slate-700 lg:table-cell">{p.runCount}</td>
                  <td className="px-4 py-3 text-right text-xs">
                    <button
                      type="button"
                      className="mr-3 font-medium text-blue-600 hover:underline"
                      onClick={() => openStrategyInNewTab(p.id)}
                    >
                      回测
                    </button>
                    <Link
                      to={`/strategy/research/${p.id}/history`}
                      className="mr-3 font-medium text-blue-600 hover:underline"
                    >
                      历史
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
              {!filtered.length && !loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-16 text-center text-slate-400">
                    暂无检测，点击「新建检测」开始
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {nameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-lg font-bold text-slate-900">新建检测</h2>
            <input
              autoFocus
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmCreate();
              }}
              placeholder="检测名称"
              className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200"
            />
            {createErr && <p className="mt-2 text-sm text-red-600">{createErr}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setNameModal(false)}
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmCreate}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {renameTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-lg font-bold text-slate-900">重命名检测</h2>
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmRename();
              }}
              placeholder="检测名称"
              className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200"
            />
            {renameErr && <p className="mt-2 text-sm text-red-600">{renameErr}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRenameTarget(null)}
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmRename}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <p className="text-sm text-slate-700">
              确认删除「{deleteTarget.name}」？回测记录将一并删除。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  void deleteStrategyProject(deleteTarget.id)
                    .then(() => {
                      setDeleteTarget(null);
                      setSelectedIds((prev) => {
                        const next = new Set(prev);
                        next.delete(deleteTarget.id);
                        return next;
                      });
                      refresh();
                    })
                    .catch((e) =>
                      window.alert(e instanceof Error ? e.message : String(e)),
                    );
                }}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}

      {batchDeleteIds && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <p className="text-sm text-slate-700">
              确认删除所选 {batchDeleteIds.length} 个策略？回测记录将一并删除。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => setBatchDeleteIds(null)}
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-60"
              >
                取消
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={confirmBatchDelete}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deleting ? "删除中…" : "删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
