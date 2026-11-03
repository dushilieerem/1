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

export function fmtDate(value: string | null | undefined) {
  if (!value) return "—";
  return value.slice(0, 10);
}

export function cls(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}
