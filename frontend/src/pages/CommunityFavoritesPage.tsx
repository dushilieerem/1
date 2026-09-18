import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getStoredUser } from "@/lib/auth";
import { listMyFavorites, type CommunityPost } from "@/lib/communityApi";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  PostListItem,
} from "@/components/community/communityUi";

export function CommunityFavoritesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent("/community/favorites")}`, {
        replace: true,
      });
      return;
    }
    let cancelled = false;
    setLoading(true);
    void listMyFavorites({ limit: 50 })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((ex) => {
        if (!cancelled) setErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[880px] px-5 py-6 animate-fade-up">
        <CommunityBackLink to="/community/me" label="返回个人主页" />
        <div className="mt-4">
          <p className="text-xs font-medium tracking-wide text-red-500/90">SAVED</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
            我的收藏
          </h1>
          <p className="mt-1.5 text-sm text-slate-500">
            {loading ? "加载中…" : `共 ${total} 篇`}
          </p>
        </div>

        {err && (
          <p className="mt-4 rounded-xl border border-red-100 bg-white px-4 py-3 text-sm text-red-600">
            {err}
          </p>
        )}

        {!loading && !err && items.length === 0 && (
          <CommunityPanel className="mt-5 px-5 py-16 text-center">
            <p className="text-base font-medium text-slate-800">还没有收藏</p>
            <p className="mt-1 text-sm text-slate-500">在帖子详情里点星标即可收藏</p>
            <Link
              to="/community"
              className="mt-5 inline-block text-sm font-medium text-red-600 hover:underline"
            >
              去社区看看
            </Link>
          </CommunityPanel>
        )}

        {items.length > 0 && (
          <CommunityPanel className="mt-5">
            <ul className="divide-y divide-slate-100">
              {items.map((post) => (
                <li key={post.id}>
                  <PostListItem post={post} />
                </li>
              ))}
            </ul>
          </CommunityPanel>
        )}
      </div>
    </CommunityPageShell>
  );
}
