import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, MessageCircle, Star } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  excerpt,
  formatPostTime,
  listMyFavorites,
  type CommunityPost,
} from "@/lib/communityApi";

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
    <div className="min-h-[calc(100vh-4rem)] bg-[#f3f5f8]">
      <div className="mx-auto max-w-[880px] px-5 py-6">
        <Link to="/community" className="text-sm text-slate-500 hover:text-red-600">
          ← 返回社区
        </Link>
        <h1 className="mt-3 text-xl font-bold text-slate-900">我的收藏</h1>
        <p className="mt-1 text-sm text-slate-500">
          {loading ? "加载中…" : `共 ${total} 篇`}
        </p>

        {err && (
          <p className="mt-4 rounded border border-red-100 bg-white px-4 py-3 text-sm text-red-600">
            {err}
          </p>
        )}

        {!loading && !err && items.length === 0 && (
          <div className="mt-6 rounded border border-slate-200 bg-white px-5 py-16 text-center">
            <p className="text-sm text-slate-500">还没有收藏</p>
            <Link
              to="/community"
              className="mt-4 inline-block text-sm font-medium text-red-600 hover:underline"
            >
              去社区看看
            </Link>
          </div>
        )}

        <ul className="mt-4 overflow-hidden rounded border border-slate-200 bg-white shadow-sm shadow-slate-200/40 divide-y divide-slate-100">
          {items.map((post) => (
            <li key={post.id}>
              <Link
                to={`/community/post/${post.id}`}
                className="block px-5 py-4 hover:bg-slate-50/80"
              >
                <h2 className="text-[15px] font-semibold text-slate-900">{post.title}</h2>
                <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                  {excerpt(post.body || "", 120)}
                </p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
                  <span>{post.section_label}</span>
                  <span className="inline-flex items-center gap-1">
                    <Eye className="h-3 w-3" />
                    {post.view_count}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <MessageCircle className="h-3 w-3" />
                    {post.comment_count ?? 0}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Star className="h-3 w-3" />
                    {post.favorite_count ?? 0}
                  </span>
                  <span>{formatPostTime(post.created_at)}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
