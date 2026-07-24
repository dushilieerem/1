import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FilePenLine, Trash2 } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  deleteCommunityPost,
  formatPostTime,
  listMyPosts,
  type CommunityPost,
} from "@/lib/communityApi";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  PrimaryButton,
  SectionPill,
} from "@/components/community/communityUi";

export function CommunityDraftsPage() {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await listMyPosts({ status: "draft", limit: 50 });
      setItems(data.items);
      setTotal(data.total);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent("/community/drafts")}`, {
        replace: true,
      });
      return;
    }
    void reload();
  }, [navigate, reload]);

  const onDelete = async (post: CommunityPost) => {
    const ok = await confirm({
      title: "删除草稿",
      message: `确认删除草稿「${post.title}」？删除后不可恢复。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    setBusyId(post.id);
    setErr(null);
    try {
      await deleteCommunityPost(post.id);
      await reload();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[880px] px-5 py-6 animate-fade-up">
        <CommunityBackLink to="/community/me" label="返回个人主页" />
        <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-medium tracking-wide text-red-500/90">DRAFTS</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
              草稿箱
            </h1>
            <p className="mt-1.5 text-sm text-slate-500">
              {loading ? "加载中…" : `共 ${total} 篇`}
            </p>
          </div>
          <PrimaryButton onClick={() => navigate("/community/new")}>
            <FilePenLine className="h-4 w-4" />
            写新帖
          </PrimaryButton>
        </div>

        {err && (
          <p className="mt-4 rounded-xl border border-red-100 bg-white px-4 py-3 text-sm text-red-600">
            {err}
          </p>
        )}

        {!loading && !err && items.length === 0 && (
          <CommunityPanel className="mt-5 px-5 py-16 text-center">
            <p className="text-base font-medium text-slate-800">暂无草稿</p>
            <p className="mt-1 text-sm text-slate-500">
              发帖时点「存草稿」会出现在这里
            </p>
            <PrimaryButton onClick={() => navigate("/community/new")} className="mt-5">
              去写帖
            </PrimaryButton>
          </CommunityPanel>
        )}

        {items.length > 0 && (
          <CommunityPanel className="mt-5">
            <ul className="divide-y divide-slate-100">
              {items.map((post) => {
                const busy = busyId === post.id;
                return (
                  <li
                    key={post.id}
                    className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <SectionPill
                          section={post.section}
                          label={post.section_label}
                        />
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                          草稿
                        </span>
                        <Link
                          to={`/community/post/${post.id}/edit`}
                          className="truncate text-sm font-semibold text-slate-900 hover:text-red-600"
                        >
                          {post.title || "未命名草稿"}
                        </Link>
                      </div>
                      <p className="mt-1.5 text-xs text-slate-400">
                        更新于 {formatPostTime(post.updated_at || post.created_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <Link
                        to={`/community/post/${post.id}/edit`}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <FilePenLine className="h-3.5 w-3.5" />
                        继续编辑
                      </Link>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onDelete(post)}
                        className="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        删除
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </CommunityPanel>
        )}
      </div>
    </CommunityPageShell>
  );
}
