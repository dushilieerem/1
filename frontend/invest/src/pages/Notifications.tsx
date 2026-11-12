import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader } from "../components";
import { useLocale } from "../i18n";

type CommunityNotification = {
  id: number;
  type: string;
  post_id: number;
  post_title?: string;
  comment_body?: string;
  created_at?: string;
  read_at?: string | null;
  actor?: { display_name?: string; username?: string };
};

type EventLog = {
  id: number;
  code: string;
  title: string;
  detail?: string;
  triggered_at: string;
  read: boolean;
};

type Item =
  | { kind: "community"; at: string; data: CommunityNotification }
  | { kind: "event"; at: string; data: EventLog };

const TYPE_LABEL: Record<string, { zh: string; en: string }> = {
  reply: { zh: "回复了你", en: "replied to you" },
  mention: { zh: "提到了你", en: "mentioned you" },
  like: { zh: "赞了你", en: "liked your post" },
};

const TABS: Array<{ key: "all" | "guard" | "community"; zh: string; en: string }> = [
  { key: "all", zh: "全部", en: "All" },
  { key: "guard", zh: "提醒", en: "Reminders" },
  { key: "community", zh: "社区互动", en: "Community" },
];

export default function Notifications() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [community, setCommunity] = useState<CommunityNotification[]>([]);
  const [events, setEvents] = useState<EventLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"all" | "guard" | "community">("all");

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      api<{ items: CommunityNotification[] }>("/api/community/notifications?limit=50").catch(() => ({ items: [] })),
      api<{ items: EventLog[] }>("/api/invest/event-logs?limit=50").catch(() => ({ items: [] })),
    ])
      .then(([c, e]) => {
        setCommunity(c.items || []);
        setEvents(e.items || []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const items: Item[] = useMemo(() => {
    const merged: Item[] = [
      ...community.map((x) => ({ kind: "community" as const, at: x.created_at || "", data: x })),
      ...events.map((x) => ({ kind: "event" as const, at: x.triggered_at || "", data: x })),
    ];
    merged.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
    if (tab === "community") return merged.filter((x) => x.kind === "community");
    if (tab === "guard") return merged.filter((x) => x.kind === "event");
    return merged;
  }, [community, events, tab]);

  const unread =
    community.filter((x) => !x.read_at).length + events.filter((x) => !x.read).length;

  const markAll = async () => {
    setBusy(true);
    try {
      await api("/api/community/notifications/read", { method: "POST", body: JSON.stringify({ all: true }) });
      await api("/api/invest/event-logs/read", { method: "POST", body: JSON.stringify({ all: true }) });
      load();
    } catch (e: any) {
      setError(e.message || t("操作失败", "Action failed"));
    } finally {
      setBusy(false);
    }
  };

  const markOne = async (item: Item) => {
    try {
      if (item.kind === "event" && !item.data.read) {
        await api("/api/invest/event-logs/read", { method: "POST", body: JSON.stringify({ id: item.data.id }) });
        setEvents((prev) => prev.map((x) => (x.id === item.data.id ? { ...x, read: true } : x)));
      }
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="page">
      <PageHeader
        title={t("消息通知", "Notifications")}
        sub={unread ? t(`${unread} 条未读`, `${unread} unread`) : t("全部已读", "All read")}
        back
        onBack={() => nav(-1)}
        right={
          unread ? <button className="chip" onClick={markAll} disabled={busy}>{busy ? t("处理中…", "Processing…") : t("全部已读", "Mark all read")}</button> : undefined
        }
      />

      <div className="seg">
        {TABS.map((item) => (
          <button key={item.key} className={tab === item.key ? "on" : ""} onClick={() => setTab(item.key)}>{t(item.zh, item.en)}</button>
        ))}
      </div>

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !items.length ? (
        <EmptyState title={t("没有消息", "No notifications")} detail={t("提醒触发或社区互动后会出现在这里。", "Reminder alerts and community activity will appear here.")} />
      ) : null}

      {!loading && items.length ? (
        <div className="post-list">
          {items.map((item) => {
            const unreadItem = item.kind === "community" ? !item.data.read_at : !item.data.read;
            if (item.kind === "community") {
              const n = item.data;
              return (
                <Link key={`c${n.id}`} to={`/community/${n.post_id}`} className="post-row" onClick={() => void markOne(item)}>
                  <div className="post-row-title" style={{ fontSize: 13.5 }}>
                    <Bell size={13} style={{ marginRight: 4 }} />
                    {n.actor?.display_name || n.actor?.username || t("有人", "Someone")} {TYPE_LABEL[n.type] ? t(TYPE_LABEL[n.type].zh, TYPE_LABEL[n.type].en) : n.type}
                    {unreadItem ? <span className="dot" /> : null}
                  </div>
                  <div className="post-row-meta"><span>{n.post_title || t("帖子", "Post")}</span></div>
                  {n.comment_body ? <div className="hint">{n.comment_body}</div> : null}
                  <div className="post-row-stats"><span>{n.created_at?.slice(0, 16).replace("T", " ")}</span></div>
                </Link>
              );
            }
            const e = item.data;
            return (
              <button
                key={`e${e.id}`}
                className="post-row"
                style={{ textAlign: "left" }}
                onClick={() => { void markOne(item); nav(`/watch`); }}
              >
                <div className="post-row-title" style={{ fontSize: 13.5 }}>
                  <Bell size={13} style={{ marginRight: 4 }} /> {e.title || e.code}
                  {unreadItem ? <span className="dot" /> : null}
                </div>
                {e.detail ? <div className="hint">{e.detail}</div> : null}
                <div className="post-row-stats"><span>{e.triggered_at?.slice(0, 16)}</span></div>
              </button>
            );
          })}
        </div>
      ) : null}

    </div>
  );
}
