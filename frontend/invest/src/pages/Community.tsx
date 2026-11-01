import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Plus } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";

type Post = {
  id: number;
  section: string;
  section_label: string;
  title: string;
  body: string;
  view_count: number;
  comment_count: number;
  like_count: number;
  created_at?: string;
  author?: { username?: string; display_name?: string };
};

type Feed = { items: Post[]; total: number; sections?: Array<{ id: string; label: string }> };

export default function Community() {
  const { user } = useAuth();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [section, setSection] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = (next: string) => {
    setLoading(true);
    setError(null);
    const qs = new URLSearchParams({ limit: "30", sort: "newest" });
    if (next) qs.set("section", next);
    api<Feed>(`/api/community/posts?${qs.toString()}`)
      .then(setFeed)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => load(section), [section]);

  return (
    <div className="page">
      <PageHeader
        title="社区"
        sub="策略、因子与热点讨论 · 内容需遵守社区规范"
        right={
          user ? (
            <Link to="/community/new" className="round-btn" aria-label="发帖">
              <Plus size={20} />
            </Link>
          ) : null
        }
      />

      <div className="chips">
        <button className={`chip ${section === "" ? "on" : ""}`} onClick={() => setSection("")}>
          全部
        </button>
        {(feed?.sections || []).map((item) => (
          <button
            key={item.id}
            className={`chip ${section === item.id ? "on" : ""}`}
            onClick={() => setSection(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <ErrorState message={error} onRetry={() => load(section)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}

      {!loading && feed && !feed.items.length ? (
        <EmptyState title="还没有帖子" detail="来发第一帖，分享你的研究或问题。" />
      ) : null}

      {!loading && feed?.items.length ? (
        <div className="post-list">
          {feed.items.map((post) => (
            <Link key={post.id} to={`/community/${post.id}`} className="post-row">
              <div className="post-row-main">
                <div className="post-row-title">{post.title}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{post.section_label}</Tag>
                  <span>{post.author?.display_name || post.author?.username || "匿名"}</span>
                  <span>· {post.created_at?.slice(0, 10)}</span>
                </div>
                <div className="post-row-stats">
                  <span>{post.view_count} 阅读</span>
                  <span>{post.like_count} 赞</span>
                  <span>
                    <MessageSquare size={12} /> {post.comment_count}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : null}

      <Disclaimer>社区内容为用户观点，不构成投资建议；违规内容可举报。</Disclaimer>
    </div>
  );
}
