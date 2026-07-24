import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  formatPostTime,
  listNotifications,
  markNotificationsRead,
  unreadNotificationCount,
  type CommunityNotification,
  type NotificationType,
} from "@/lib/communityApi";
import {
  AuthorAvatar,
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
} from "@/components/community/communityUi";

const TABS: { id: NotificationType; label: string }[] = [
  { id: "reply", label: "回复我的" },
  { id: "mention", label: "@我的" },
  { id: "like", label: "收到的赞" },
];

function typeLabel(t: NotificationType) {
  if (t === "reply") return "回复了你";
  if (t === "mention") return "在评论里 @了你";
  return "赞了你的评论";
}

export function CommunityMessagesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabRaw = searchParams.get("tab") || "reply";
  const tab: NotificationType = TABS.some((t) => t.id === tabRaw)
    ? (tabRaw as NotificationType)
    : "reply";
  const [items, setItems] = useState<CommunityNotification[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = async (typ: NotificationType) => {
    setLoading(true);
    setErr(null);
    try {
      const [list, unread] = await Promise.all([
        listNotifications({ type: typ, limit: 50 }),
        unreadNotificationCount(),
      ]);
      setItems(list.items);
      setCounts(unread.by_type || {});
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(tab);
  }, [tab]);

  const setTab = (id: NotificationType) => {
    setSearchParams({ tab: id }, { replace: true });
  };

  const onOpen = async (n: CommunityNotification) => {
    if (!n.read_at) {
      try {
        const res = await markNotificationsRead({ ids: [n.id] });
        setCounts(res.by_type || {});
        setItems((prev) =>
          prev.map((x) =>
            x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x,
          ),
        );
      } catch {
        // ignore
      }
    }
  };

  const markTabRead = async () => {
    try {
      const res = await markNotificationsRead({ type: tab });
      setCounts(res.by_type || {});
      setItems((prev) =>
        prev.map((x) => ({ ...x, read_at: x.read_at || new Date().toISOString() })),
      );
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    }
  };

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[880px] px-5 py-6 animate-fade-up">
        <CommunityBackLink to="/community/me" label="返回个人主页" />

        <CommunityPanel className="mt-4">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
            <div>
              <p className="text-xs font-medium tracking-wide text-red-500/90">
                MESSAGES
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                消息
              </h1>
            </div>
            <button
              type="button"
              onClick={() => void markTabRead()}
              className="text-xs font-medium text-slate-500 hover:text-red-600"
            >
              本栏标为已读
            </button>
          </div>

          <nav className="flex gap-1 border-b border-slate-100 px-3 sm:px-4">
            {TABS.map((t) => {
              const active = tab === t.id;
              const n = counts[t.id] || 0;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`relative px-3 py-3 text-sm transition ${
                    active
                      ? "font-semibold text-red-600"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t.label}
                  {n > 0 && (
                    <span className="ml-1.5 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                      {n > 99 ? "99+" : n}
                    </span>
                  )}
                  {active && (
                    <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-red-500" />
                  )}
                </button>
              );
            })}
          </nav>

          {err && (
            <p className="mx-5 mt-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
              {err}
            </p>
          )}

          {loading ? (
            <p className="px-5 py-16 text-center text-sm text-slate-400">加载中…</p>
          ) : items.length === 0 ? (
            <p className="px-5 py-16 text-center text-sm text-slate-400">暂无消息</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((n) => {
                const actor =
                  n.actor.display_name || n.actor.username || "用户";
                const href = `/community/post/${n.post_id}${
                  n.comment_id ? `?comment=${n.comment_id}` : ""
                }`;
                return (
                  <li key={n.id}>
                    <Link
                      to={href}
                      onClick={() => void onOpen(n)}
                      className={`flex gap-3 px-5 py-4 transition hover:bg-slate-50 sm:px-6 ${
                        !n.read_at ? "bg-red-50/30" : ""
                      }`}
                    >
                      <AuthorAvatar name={actor} size="md" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-800">
                          <span className="font-semibold">{actor}</span>{" "}
                          <span className="text-slate-600">{typeLabel(n.type)}</span>
                        </p>
                        {n.comment_body && (
                          <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                            {n.comment_body}
                          </p>
                        )}
                        <p className="mt-1 text-[11px] text-slate-400">
                          {formatPostTime(n.created_at)}
                        </p>
                      </div>
                      <div className="w-28 shrink-0 text-right text-xs text-slate-500 line-clamp-3">
                        {n.post_title}
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </CommunityPanel>
      </div>
    </CommunityPageShell>
  );
}
