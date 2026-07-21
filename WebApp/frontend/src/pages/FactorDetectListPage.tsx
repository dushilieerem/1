import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Plus, Trash2 } from "lucide-react";
import {
  clearDetectClientCache,
  createProject,
  deleteProject,
  listVisibleProjects,
  type DetectProject,
} from "@/lib/detectStore";
import { getStoredUser, subscribeAuth } from "@/lib/auth";

export function FactorDetectListPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<DetectProject[]>([]);
  const [query, setQuery] = useState("");
  const [nameModal, setNameModal] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DetectProject | null>(null);
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    setErr(null);
    void listVisibleProjects()
      .then(setProjects)
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
    void createProject("custom_combo", title, title)
      .then((p) => {
        setNameModal(false);
        navigate(`/factor/detect/${p.id}`);
      })
      .catch((e) => setCreateErr(e instanceof Error ? e.message : String(e)));
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1200px] px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">因子检测</h1>
            <p className="mt-1 text-sm text-slate-600">
              已完成检测的因子会出现在此列表；也可新建后配置并运行
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={openCreate}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              新建因子
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

        <div className="mb-4">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索因子名称…"
            className="w-full max-w-md rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200"
          />
        </div>

        {err && <p className="mb-3 text-sm text-red-600">{err}</p>}
        {loading ? (
          <p className="py-16 text-center text-sm text-slate-400">加载中…</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">因子名称</th>
                  <th className="px-4 py-3">类型</th>
                  <th className="px-4 py-3">最后修改时间</th>
                  <th className="px-4 py-3">检测次数</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id} className="border-t border-slate-100">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-slate-900">{p.name}</p>
                        {p.sample ? (
                          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                            样例
                          </span>
                        ) : null}
                      </div>
                      <code className="text-xs text-slate-400">{p.factorName}</code>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                        股票
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">
                      {p.updatedAt?.replace("T", " ").slice(0, 19)}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-slate-700">{p.runCount}</td>
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
                        <button
                          type="button"
                          className="inline-flex text-slate-400 hover:text-red-600"
                          onClick={() => setDeleteTarget(p)}
                          title="删除"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={5} className="px-4 py-16 text-center text-slate-400">
                      暂无项目，点击「新建因子」开始
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

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
      </div>
    </div>
  );
}
