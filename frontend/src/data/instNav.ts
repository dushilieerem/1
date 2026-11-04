import type { InstAccess, InstWorkspace } from "@/lib/instAuth";

/** 线性流程 B：交易执行合并进审批通过动作，不再作为独立菜单。 */
const HIDDEN_WORKSPACE_KEYS = new Set(["execution"]);

/** 菜单顺序：保留服务端工作区 key，隐藏项不影响权限矩阵。 */
export const INST_WORKSPACE_ORDER = [
  "overview",
  "ideas",
  "research",
  "debate",
  "approvals",
  "execution",
  "portfolio",
  "monitor",
  "about",
] as const;

function orderIndex(key: string): number {
  const i = INST_WORKSPACE_ORDER.indexOf(key as (typeof INST_WORKSPACE_ORDER)[number]);
  return i === -1 ? INST_WORKSPACE_ORDER.length : i;
}

/** 稳定排序：已知工作区按固定顺序，未知 key 保持相对顺序排末尾 */
export function sortWorkspaces(list: InstWorkspace[]): InstWorkspace[] {
  return [...list]
    .map((item, index) => ({ item, index }))
    .sort((a, b) => orderIndex(a.item.key) - orderIndex(b.item.key) || a.index - b.index)
    .map((x) => x.item);
}

/** 菜单只渲染服务端允许的工作区；none 与 visible=false 都不出现 */
export function visibleWorkspaces(list: InstWorkspace[] | null | undefined): InstWorkspace[] {
  if (!list) return [];
  const seen = new Set<string>();
  const out: InstWorkspace[] = [];
  for (const item of sortWorkspaces(list)) {
    if (!item || !item.key || seen.has(item.key)) continue;
    if (HIDDEN_WORKSPACE_KEYS.has(item.key)) continue;
    if (!item.visible || item.access === "none") continue;
    seen.add(item.key);
    out.push(item);
  }
  return out;
}

/** 只读/摘要角色在菜单与页面上的标识；可写角色不显示 */
export function accessBadge(access: InstAccess): "只读" | "仅摘要" | null {
  if (access === "read") return "只读";
  if (access === "digest") return "仅摘要";
  return null;
}

/** 当前路径命中的工作区（按最长 path 前缀匹配） */
export function workspaceForPath(
  list: InstWorkspace[] | null | undefined,
  pathname: string,
): InstWorkspace | null {
  if (!list?.length) return null;
  let hit: InstWorkspace | null = null;
  for (const item of list) {
    if (pathname === item.path || pathname.startsWith(`${item.path}/`)) {
      if (!hit || item.path.length > hit.path.length) hit = item;
    }
  }
  return hit;
}

/** 本轮只交付驾驶舱，其余工作区给出明确的下一阶段范围，避免出现死链 */
export const INST_PLACEHOLDERS: Record<
  string,
  { summary: string; points: string[] }
> = {
  ideas: {
    summary: "从产业变化、商业质量与估值偏离中发现研究线索，并保留未入选理由。",
    points: ["24 家演示标的与三市场筛选", "立项 / 观察 / 放弃与理由留存", "自然语言研究条件解析"],
  },
  research: {
    summary: "六维研究、资料包与版本化审核，结论必须带来源与反证条件。",
    points: ["六维研究任务与进度", "资料包 / 版本 / 复核门禁", "估值参数与敏感性表"],
  },
  debate: {
    summary: "正反方独立立论、两轮交叉质询，保留未解决异议。",
    points: ["正反方隔离上下文", "两轮辩论与记录", "四类结论与门禁"],
  },
  portfolio: {
    summary: "组合配置、币种敞口与发行人聚合，区分批准与持仓。",
    points: ["配置 + 现金 = 100%", "CNY / USD / HKD 敞口", "A/H/ADR 经济敞口聚合"],
  },
  approvals: {
    summary: "议案登记、合伙人复核、独立风控与 Chairman 审批。",
    points: ["议案版本与阶段流转", "风控硬性阻断", "授权快照与执行前复核"],
  },
  execution: {
    summary: "只执行有效授权，记录成交、对账与异常处置。",
    points: ["授权校验条", "幂等提交与部分成交", "SimBroker 纸面执行"],
  },
  monitor: {
    summary: "持仓跟踪、经营预警与退出研究，退出重新走审批。",
    points: ["投后论点台账", "经营预警与复核", "退出议案与复盘"],
  },
  about: {
    summary: "AI 团队、角色权限矩阵与平台方案入口。",
    points: ["六角色职责边界", "权限矩阵", "平台方案与免责声明"],
  },
};

