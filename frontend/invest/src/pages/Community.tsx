import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Plus } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

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

const SECTION_EN: Record<string, string> = {
  策略分享: "Strategy share",
  因子笔记: "Factor notes",
  问答: "Q&A",
  热点分析: "Market topics",
  官方: "Official",
};

export default function Community() {
  const { user } = useAuth();
  const { t, locale } = useLocale();
  const sectionLabel = (label: string) => (locale === "en" ? SECTION_EN[label] || label : label);
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
        title={t("社区", "Community")}
        sub={t("策略、因子与热点讨论 · 内容需遵守社区规范", "Strategies, factors, and market topics · follow the community guidelines")}
        right={
          user ? (
            <Link to="/community/new" className="round-btn" aria-label={t("发帖", "New post")}>
              <Plus size={20} />
            </Link>
          ) : null
        }
      />

      <div className="chips">
        <button className={`chip ${section === "" ? "on" : ""}`} onClick={() => setSection("")}>
          {t("全部", "All")}
        </button>
        {(feed?.sections || []).map((item) => (
          <button
            key={item.id}
            className={`chip ${section === item.id ? "on" : ""}`}
            onClick={() => setSection(item.id)}
          >
            {sectionLabel(item.label)}
          </button>
        ))}
      </div>

      {error ? <ErrorState message={error} onRetry={() => load(section)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}

      {!loading && feed && !feed.items.length ? (
        <EmptyState title={t("还没有帖子", "No posts yet")} detail={t("来发第一帖，分享你的研究或问题。", "Start the first thread and share your research or questions.")} />
      ) : null}

      {!loading && feed?.items.length ? (
        <div className="post-list">
          {feed.items.map((post) => (
            <Link key={post.id} to={`/community/${post.id}`} className="post-row">
              <div className="post-row-main">
                <div className="post-row-title">{post.title}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{sectionLabel(post.section_label)}</Tag>
                  <span>{post.author?.display_name || post.author?.username || t("匿名", "Anonymous")}</span>
                  <span>· {post.created_at?.slice(0, 10)}</span>
                </div>
                <div className="post-row-stats">
                  <span>{t(`${post.view_count} 阅读`, `${post.view_count} views`)}</span>
                  <span>{t(`${post.like_count} 赞`, `${post.like_count} likes`)}</span>
                  <span>
                    <MessageSquare size={12} /> {post.comment_count}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : null}

      <Disclaimer>{t("社区内容为用户观点，不构成投资建议；违规内容可举报。", "Community content reflects users' views and is not investment advice; report any violations.")}</Disclaimer>
    </div>
  );
}
