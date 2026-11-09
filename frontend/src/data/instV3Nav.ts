export type V3StageKey = "find" | "research" | "debate" | "approve" | "execute" | "manage";

export type V3NavItem = {
  key: string;
  label: string;
  path: string;
  no?: string;
  permission: string;
  roles?: string[];
};

export type V3NavGroup = { label: string; hint?: string; items: V3NavItem[] };

export const V3_NAV_GROUPS: V3NavGroup[] = [
  {
    label: "投资工作空间",
    items: [
      { key: "dashboard", label: "投资工作台", path: "/inst-v3", permission: "overview" },
      { key: "pipeline", label: "项目流水线", path: "/inst-v3/pipeline", permission: "overview" },
    ],
  },
  {
    label: "流程工作台",
    hint: "Agent 运行",
    items: [
      { key: "research", label: "价值分析", no: "02", path: "/inst-v3/research", permission: "research" },
      { key: "debate", label: "多空辩论", no: "03", path: "/inst-v3/debate", permission: "debate" },
      { key: "approvals", label: "投委会审批", no: "04", path: "/inst-v3/approvals", permission: "approvals" },
      { key: "execute", label: "执行成交", no: "05", path: "/inst-v3/execute", permission: "execution" },
      { key: "manage", label: "投资管理", no: "06", path: "/inst-v3/manage", permission: "portfolio" },
    ],
  },
  {
    label: "规则与说明",
    items: [{ key: "playbook", label: "流程与权限", path: "/inst-v3/playbook", permission: "overview" }],
  },
];

const APPROVER_ROLES = new Set(["partner", "risk", "chairman"]);

/** v3 导航可见性：生产按登录角色裁剪；不提供前端角色切换。 */
export function visibleV3Nav(
  role: string,
  permissions: Record<string, string> | null | undefined,
): V3NavGroup[] {
  const perms = permissions || {};
  const can = (key: string) => (perms[key] || "none") !== "none";
  return V3_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (!can(item.permission)) return false;
      // 审批角色只看流水线/审批/权限；不进入 02/03/05/06 工作台。
      if (APPROVER_ROLES.has(role) && ["research", "debate", "execute", "manage"].includes(item.key)) {
        return false;
      }
      return true;
    }),
  })).filter((group) => group.items.length > 0);
}

export function v3TitleForPath(pathname: string): string {
  if (pathname.startsWith("/inst-v3/pipeline")) return "项目流水线";
  if (pathname.startsWith("/inst-v3/research")) return "价值分析";
  if (pathname.startsWith("/inst-v3/debate")) return "多空辩论";
  if (pathname.startsWith("/inst-v3/approvals")) return "投委会审批";
  if (pathname.startsWith("/inst-v3/execute")) return "执行成交";
  if (pathname.startsWith("/inst-v3/manage")) return "投资管理";
  if (pathname.startsWith("/inst-v3/playbook")) return "流程与权限";
  return "投资工作台";
}
