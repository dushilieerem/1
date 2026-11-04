export function fmtPct(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  let text = value.toFixed(digits);
  if (text.startsWith("-0.") && Number(text) === 0) text = text.slice(1);
  return `${value > 0 ? "+" : ""}${text}%`;
}

function isEn(): boolean {
  try {
    return localStorage.getItem("svq_invest_locale") === "en";
  } catch {
    return false;
  }
}

export function fmtNum(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(isEn() ? "en-US" : "zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function fmtMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (isEn()) {
    if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
    if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
    return formatPrice(value);
  }
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)} 万亿`;
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)} 万`;
  return formatPrice(value);
}

export function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value >= 100 ? value.toFixed(2) : value >= 10 ? value.toFixed(2) : value.toFixed(3);
}

/** 市值字段：后端单位为亿元，展示时明确亿/万亿或 B/T。 */
export function fmtMarketCap(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const yuan = Number(value) * 1e8;
  if (isEn()) {
    if (yuan >= 1e12) return `${(yuan / 1e12).toFixed(2)}T`;
    if (yuan >= 1e9) return `${(yuan / 1e9).toFixed(2)}B`;
    if (yuan >= 1e6) return `${(yuan / 1e6).toFixed(1)}M`;
    return `${yuan.toFixed(0)}`;
  }
  if (value >= 1e4) return `${(value / 1e4).toFixed(2)} 万亿`;
  return `${Number(value) >= 100 ? Number(value).toFixed(0) : Number(value).toFixed(1)} 亿`;
}

/** 成交量（股）：用万/亿股或 K/M 展示，避免一长串数字。 */
export function fmtShares(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (isEn()) {
    if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B sh`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M sh`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K sh`;
    return `${value.toFixed(0)} sh`;
  }
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿股`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)} 万股`;
  return `${value.toFixed(0)} 股`;
}

/** 带正负号的金额（万 / 亿），用于收益、盈亏与调仓金额。 */
export function fmtSignedMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  if (isEn()) {
    if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
    if (abs === 0) return "0";
    return `${sign}${abs.toFixed(0)}`;
  }
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e3) return `${sign}${(abs / 1e4).toFixed(1)}万`;
  if (abs === 0) return "0";
  return `${sign}${abs.toFixed(0)}`;
}

/** 总资产等大额展示：优先「万 / 亿」。 */
export function fmtWan(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (isEn()) {
    if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
    if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
    return value.toFixed(0);
  }
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)} 万`;
  return value.toFixed(0);
}

const ENUM_EN: Record<string, string> = {
  pending: "Pending",
  passed: "Passed",
  failed: "Failed",
  active: "Active",
  inactive: "Inactive",
  archived: "Archived",
  vectorized: "Vectorized",
  event_driven: "Event-driven",
  local: "Local",
  remote: "Remote",
  paper: "Paper",
  live: "Live",
  stock: "Stock",
  etf: "ETF",
  csi300: "CSI 300",
  csi500: "CSI 500",
  csi1000: "CSI 1000",
  trend: "Trend",
  momentum: "Momentum",
  reversal: "Reversal",
  low_volatility: "Low volatility",
  minimum_variance: "Minimum variance",
  statistical_arbitrage: "Statistical arbitrage",
  value: "Value",
  value_growth: "Value growth",
  custom: "Custom",
  持有: "Holding",
  空仓: "No positions",
  进取型: "Aggressive",
  稳健型: "Balanced",
  保守型: "Conservative",
  "公开 EOD（腾讯 / 东方财富）": "Public EOD (Tencent / Eastmoney)",
  本地演示数据: "Local demo data",
  "US coverage unavailable": "US coverage unavailable",
};

const ENUM_ZH: Record<string, string> = {
  pending: "待校验",
  passed: "已通过",
  failed: "未通过",
  active: "生效中",
  inactive: "已停止",
  archived: "已归档",
  vectorized: "向量化",
  event_driven: "事件驱动",
  local: "本地",
  remote: "远程",
  paper: "模拟盘",
  live: "实盘",
  stock: "股票",
  etf: "ETF",
  csi300: "沪深300",
  csi500: "中证500",
  csi1000: "中证1000",
  trend: "趋势",
  momentum: "动量",
  reversal: "反转",
  low_volatility: "低波动",
  minimum_variance: "最小方差",
  statistical_arbitrage: "统计套利",
  value: "价值",
  value_growth: "价值成长",
  custom: "自定义",
  "US coverage unavailable": "美股数据未接入",
};

/** 把 pending/passed、vectorized、持有/空仓 等枚举转成人话；未知值原样返回。 */
export function humanizeEnum(value: string | null | undefined) {
  const text = String(value ?? "").trim();
  if (!text) return "—";
  const map = isEn() ? ENUM_EN : ENUM_ZH;
  return map[text] || map[text.toLowerCase()] || text;
}

/** 行业字段兜底：不要把 801780.SI 这类代码直接丢给用户。 */
export function displayIndustry(value: string | null | undefined) {
  const text = String(value || "").trim();
  if (!text) return isEn() ? "Industry not mapped" : "行业未映射";
  if (/^\d{6}\.(SI|SH|SZ)$/i.test(text)) {
    return isEn() ? "Industry code (mapping pending)" : "行业代码（映射中）";
  }
  if (text === "未分类") return isEn() ? "Unclassified" : "未分类";
  if (text === "US equity") return isEn() ? "US equity" : "美股";
  return text;
}

/** 文本里夹杂行业代码时做替换，用于搜索结果的 code · industry 组合串。 */
export function displayIndustryText(value: string | null | undefined) {
  return String(value || "").replace(
    /\b\d{6}\.(SI|SH|SZ)\b/gi,
    isEn() ? "industry code (mapping pending)" : "行业代码（映射中）",
  );
}

export function fmtDate(value: string | null | undefined) {
  if (!value) return "—";
  return value.slice(0, 10);
}

export function cls(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}
