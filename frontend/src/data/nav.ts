export const NAV_ITEMS = [
  { to: "/", label: "首页" },
  { to: "/community", label: "社区" },
  { to: "/news", label: "资讯" },
] as const;

/** 资讯页一级分类（与设计文档一致） */
export const NEWS_CATEGORIES = [
  { id: "all", label: "全部" },
  { id: "flash", label: "快讯" },
  { id: "market", label: "市场" },
  { id: "announce", label: "公告" },
  { id: "research", label: "研报" },
  { id: "policy", label: "政策" },
  { id: "global", label: "海外" },
] as const;

export const NEWS_SOURCES = [
  {
    id: "cls",
    label: "财联社",
    role: "快讯/电报",
    url: "https://www.cls.cn/",
  },
  {
    id: "eastmoney",
    label: "东方财富",
    role: "个股/市场新闻",
    url: "https://www.eastmoney.com/",
  },
  {
    id: "cninfo",
    label: "巨潮资讯",
    role: "法定公告",
    url: "https://www.cninfo.com.cn/new/index.jsp",
  },
  {
    id: "10jqka",
    label: "同花顺",
    role: "题材/热点",
    url: "https://www.10jqka.com.cn/",
  },
  {
    id: "wallstreetcn",
    label: "华尔街见闻",
    role: "宏观/全球",
    url: "https://wallstreetcn.com/",
  },
  {
    id: "bloomberg",
    label: "彭博社",
    role: "海外/国际",
    url: "https://www.bloomberg.com/asia",
  },
] as const;

export const DATA_NAV_ITEMS = [
  { to: "/data/kline", label: "K线面板" },
  { to: "/data/watchlist", label: "自选股组合" },
  { to: "/data/fields", label: "字段说明与样例" },
] as const;

/** 顶栏「帮助」：文档 / API 说明入口（原数据下拉里的 API 占位迁此） */
export const HELP_NAV = { to: "/help", label: "帮助" } as const;

/** 模拟盘：日终 VWAP 结算账户 */
export const PAPER_NAV = { to: "/paper", label: "模拟盘" } as const;

export const STRATEGY_NAV_ITEMS = [
  { to: "/strategy/plaza", label: "策略广场" },
  { to: "/strategy/library", label: "策略库" },
  { to: "/strategy/ai", label: "AI策略生成" },
  { to: "/strategy/research", label: "检测报告" },
  { to: "/strategy/convert", label: "代码转换" },
] as const;

export const FACTOR_NAV_ITEMS = [
  { to: "/factor/library", label: "因子库" },
  { to: "/factor/ai", label: "AI因子生成" },
  { to: "/factor/detect", label: "检测报告" },
  { to: "/factor/dashboard", label: "因子面板" },
] as const;
