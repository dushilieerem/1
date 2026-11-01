import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader } from "../components";

type Notification = {
  id: number;
  type: string;
  post_id: number;
  comment_id?: number | null;
  post_title?: string;
  comment_body?: string;
  created_at?: string;
  read_at?: string | null;
  actor?: { display_name?: string; username?: string };
};

const TYPE_LABEL: Record<string, string> = {
  reply: "回复了你",
  mention: "提到了你",
  like: "赞了你",
};

export default function Notifications() {
  const nav = useNavigate();
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api<{ items: Notification[] }>("/api/community/notifications?limit=50")
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const markAll = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/api/community/notifications/read", {
        method: "POST",
        body: JSON.stringify({ all: true }),
      });
      load();
    } catch (e: any) {
      setError(e.message || "操作失败");
    } finally {
      setBusy(false);
    }
  };

  const unread = items.filter((item) => !item.read_at).length;

  return (
    <div className="page">
      <PageHeader
        title="消息通知"
        sub={unread ? `${unread} 条未读` : "全部已读"}
        back
        onBack={() => nav(-1)}
        right={
          unread ? (
            <button className="chip" onClick={markAll} disabled={busy}>
              {busy ? "处理中…" : "全部已读"}
            </button>
          ) : null
        }
      />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}

      {!loading && !items.length ? (
        <EmptyState title="没有消息" detail="有人回复、提到或赞你时会出现在这里。" />
      ) : null}

      {!loading && items.length ? (
        <div className="post-list">
          {items.map((item) => (
            <Link key={item.id} to={`/community/${item.post_id}`} className="post-row">
              <div className="post-row-title" style={{ fontSize: 13.5 }}>
                <Bell size={13} style={{ marginRight: 4 }} />
                {item.actor?.display_name || item.actor?.username || "有人"} {TYPE_LABEL[item.type] || item.type}
                {!item.read_at ? <span className="dot" /> : null}
              </div>
              <div className="post-row-meta">
                <span>{item.post_title || "帖子"}</span>
              </div>
              {item.comment_body ? <div className="hint">{item.comment_body}</div> : null}
              <div className="post-row-stats">
                <span>{item.created_at?.slice(0, 16).replace("T", " ")}</span>
              </div>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
