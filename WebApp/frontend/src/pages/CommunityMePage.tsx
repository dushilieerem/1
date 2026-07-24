import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, Bookmark, FilePenLine, FileText, Shield, UserRound } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import { getMyAgentUsage } from "@/lib/agentApi";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
} from "@/components/community/communityUi";

const LINKS = [
  {
    to: "/community/messages",
    label: "消息中心",
    desc: "帖下新评论 · 回复我的评论 · 收到的赞",
    icon: Bell,
  },
  {
    to: "/community/mine",
    label: "我的发帖",
    desc: "查看自己发布的帖子",
    icon: FileText,
  },
  {
    to: "/community/drafts",
    label: "草稿箱",
    desc: "未发布的草稿 · 继续编辑或删除",
    icon: FilePenLine,
  },
  {
    to: "/community/favorites",
    label: "我的收藏",
    desc: "收藏过的社区内容",
    icon: Bookmark,
  },
];

export function CommunityMePage() {
  const [user] = useState(() => getStoredUser());
  const [agentLine, setAgentLine] = useState<string | null>(null);
  const name = user?.display_name || user?.username || "用户";
  const initial = name.slice(0, 1).toUpperCase();
  const links =
    user?.role === "admin"
      ? [
          ...LINKS,
          {
            to: "/community/mod",
            label: "管理仓",
            desc: "已下架 · 已置顶 · Agent 用量 · 恢复 / 彻底删除",
            icon: Shield,
          },
        ]
      : LINKS;

  useEffect(() => {
    if (!user) return;
    void getMyAgentUsage()
      .then((u) =>
        setAgentLine(`Agent 今日 ${u.used_today}/${u.quota_daily}（剩余 ${u.remaining}）`),
      )
      .catch(() => setAgentLine(null));
  }, [user]);

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[720px] px-5 py-6 animate-fade-up">
        <CommunityBackLink to="/community" label="返回社区" />

        <CommunityPanel className="mt-4 overflow-hidden">
          <div className="border-b border-slate-100 bg-gradient-to-r from-red-50/60 to-transparent px-6 py-6">
            <div className="flex items-center gap-4">
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-red-500 to-rose-600 text-lg font-bold text-white">
                {initial}
              </span>
              <div>
                <p className="text-xs font-medium tracking-wide text-red-500/90">
                  PROFILE
                </p>
                <h1 className="mt-0.5 text-2xl font-bold tracking-tight text-slate-900">
                  {name}
                </h1>
                <p className="mt-1 text-sm text-slate-500">
                  {user?.role === "admin" ? "管理员" : "用户"}
                  {user?.username ? ` · ${user.username}` : ""}
                </p>
                {agentLine && (
                  <p className="mt-1 text-xs text-slate-400">{agentLine}</p>
                )}
              </div>
            </div>
          </div>

          <ul className="divide-y divide-slate-100">
            {links.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="flex items-center gap-3 px-6 py-4 transition hover:bg-slate-50"
                  >
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-slate-900">
                        {item.label}
                      </span>
                      <span className="block text-xs text-slate-500">
                        {item.desc}
                      </span>
                    </span>
                    <UserRound className="h-4 w-4 text-slate-300" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </CommunityPanel>
      </div>
    </CommunityPageShell>
  );
}
