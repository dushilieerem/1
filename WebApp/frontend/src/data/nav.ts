export const NAV_ITEMS = [
  { to: "/", label: "首页" },
  { to: "/data", label: "数据" },
  { to: "/community", label: "社区" },
] as const;

export const STRATEGY_NAV_ITEMS = [
  { to: "/strategy/research", label: "策略研究" },
  { to: "/strategy/library", label: "策略库" },
  { to: "/strategy/ai", label: "AI辅助策略设计" },
] as const;

export const FACTOR_NAV_ITEMS = [
  { to: "/factor/library", label: "因子库" },
  { to: "/factor/ai", label: "AI因子推荐" },
  { to: "/factor/detect", label: "因子检测" },
  { to: "/factor/dashboard", label: "因子面板" },
] as const;
