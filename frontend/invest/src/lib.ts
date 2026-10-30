export function fmtPct(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  let text = value.toFixed(digits);
  if (text.startsWith("-0.") && Number(text) === 0) text = text.slice(1);
  return `${value > 0 ? "+" : ""}${text}%`;
}

export function fmtNum(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function fmtMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)} 万亿`;
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)} 万`;
  return formatPrice(value);
}

export function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value >= 100 ? value.toFixed(2) : value >= 10 ? value.toFixed(2) : value.toFixed(3);
}

export function fmtDate(value: string | null | undefined) {
  if (!value) return "—";
  return value.slice(0, 10);
}

export function cls(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}
