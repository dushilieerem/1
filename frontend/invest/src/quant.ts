export type FactorMeta = {
  key: string;
  name: string;
  name_en: string;
  formula: string;
  formula_en: string;
  direction: "high" | "low";
  unit: "ratio" | "pct" | "yi";
  plain: string;
  plain_en: string;
  high_label: string;
  low_label: string;
  high_label_en: string;
  low_label_en: string;
};

export type FactorRow = FactorMeta & {
  return_1m: number | null;
  return_1y: number | null;
  percentile: number | null;
  ic_mean: number | null;
  ic_win: number | null;
  crowding: number | null;
  crowding_percentile: number | null;
  crowding_level: "high" | "mid" | "low";
  series?: Array<{ date: string; value: number }>;
};

export type FactorBoard = {
  range: "1m" | "1y";
  range_label: string;
  range_label_en: string;
  factors: FactorRow[];
  style: {
    key: "attack" | "defense" | "balanced";
    label: string;
    label_en: string;
    sentence: string;
    sentence_en: string;
    tags: string[];
    tags_en: string[];
    strongest?: string;
    strongest_name?: string;
    note: string;
    note_en: string;
    method?: string;
    method_en?: string;
  };
  correlations: Array<Array<number | null>>;
  correlation_keys: string[];
  meta: {
    universe: string;
    universe_en?: string;
    definition: string;
    percentile_definition: string;
    frequency: string;
    frequency_en?: string;
    risk_free: number;
  };
  data_date: string;
  disclaimer: string;
};

export type QuantFactor = { key: string; direction: "high" | "low" };

export type FocusItem = {
  type: "strategy" | "paper" | "factor" | "todo";
  id?: number | string;
  title: string;
  title_en?: string;
  detail: string;
  detail_en?: string;
  deviation?: number;
  link: string;
  severity: number;
};

export type Overview = {
  data_date: string;
  style: FactorBoard["style"];
  focus: { count: number; items: FocusItem[]; empty_text: string };
  entries: Array<{ key: string; title: string; title_en: string; status: string; status_en: string; link: string }>;
  counts: { strategies: number; drafts: number; backtests: number; papers: number; latest_backtest: string | null };
  disclaimer: string;
};

export type Backtest = {
  id: string;
  name: string;
  factors: Array<FactorMeta & { chosen_direction?: string }>;
  universe: string;
  start_date: string;
  end_date: string;
  range?: string;
  metrics: Record<string, number | null>;
  curve: Array<{ date: string; nav: number; benchmark: number }>;
  assumptions: Record<string, string | number | boolean>;
  holdings: Array<{ code: string; name: string }>;
  shortened: boolean;
  engine?: "re" | "local";
  engine_reason?: string | null;
  engine_error?: string | null;
  created_at?: string;
  disclaimer?: string;
};

export type Draft = {
  id: number;
  name: string;
  factors: Array<FactorMeta & { chosen_direction?: string }>;
  universe: string;
  universe_name?: string;
  last_backtest_id?: string | null;
  created_at?: string;
};

export type Strategy = {
  id: number;
  name: string;
  factors: Array<FactorMeta & { chosen_direction?: string }>;
  universe: string;
  universe_name?: string;
  status: "tracking" | "attention";
  status_label: string;
  status_label_en: string;
  today?: number | null;
  drawdown?: number | null;
  next_rebalance?: string;
  paper_id?: number | null;
  backtest_id?: string | null;
  project_id?: string | null;
  deviation?: number | null;
  created_at?: string;
  backtest?: Backtest | null;
  risk_compare?: Array<{ label: string; label_en: string; value: any }>;
  rules?: string;
  paper?: Paper | null;
};

export type Paper = {
  id: number;
  name: string;
  status: string;
  start_capital: number;
  start_date: string;
  data_date?: string;
  run_days: number;
  cumulative: number | null;
  today: number | null;
  deviation: number | null;
  metrics: Record<string, number | null>;
  positions: Array<{ code: string; name: string; weight: number; price: number | null; market_value: number | null }>;
  trades: Array<{
    date: string;
    code: string;
    name: string;
    side: "buy" | "sell";
    weight_before: number;
    weight_after: number;
    weight_delta: number;
    price: number | null;
    quantity?: number | null;
    simulated: boolean;
  }>;
  factors: FactorMeta[];
  universe: string;
  universe_name?: string;
  message?: string | null;
  disclaimer?: string;
  curve?: Array<{ date: string; nav: number }>;
};

export type PlazaItem = {
  id: number;
  title: string;
  author: string;
  factors: Array<FactorMeta & { chosen_direction?: string }>;
  universe: string;
  universe_name?: string;
  annual_return: number | null;
  max_drawdown: number | null;
  sharpe: number | null;
  curve: number[];
  followers: number;
  followed: boolean;
  is_demo?: boolean;
  range: string;
};

export type PlazaDetail = Omit<PlazaItem, "curve"> & {
  metrics: Record<string, number | null>;
  curve: Array<{ date: string; nav: number; benchmark?: number }>;
  note: string;
};

export const RE_FACTOR_KEYS = new Set(["value", "momentum", "volatility", "liquidity"]);

export function supportsRePaper(factors: Array<{ key: string }> | undefined): boolean {
  const list = factors || [];
  return list.length > 0 && list.every((f) => RE_FACTOR_KEYS.has(f.key));
}

export const UNIVERSE_LABEL: Record<string, { zh: string; en: string }> = {
  hs300: { zh: "沪深300", en: "CSI 300" },
  zz500: { zh: "中证500", en: "CSI 500" },
  all: { zh: "全市场", en: "All A-shares" },
  board: { zh: "全市场总市值前 500", en: "Top 500 by market cap" },
};

type Translate = (zh: string, en: string) => string;

export function universeLabel(key: string, t: Translate) {
  const item = UNIVERSE_LABEL[key];
  return item ? t(item.zh, item.en) : key;
}

export function factorName(f: { name: string; name_en: string }, locale: "zh" | "en") {
  return locale === "en" ? f.name_en : f.name;
}

export function factorFormula(f: FactorMeta, locale: "zh" | "en") {
  return locale === "en" ? f.formula_en : f.formula;
}

export function factorPlain(f: FactorMeta, locale: "zh" | "en") {
  return locale === "en" ? f.plain_en : f.plain;
}

export function directionLabel(f: FactorMeta, direction: "high" | "low", locale: "zh" | "en") {
  if (direction === "high") return locale === "en" ? f.high_label_en : f.high_label;
  return locale === "en" ? f.low_label_en : f.low_label;
}

export function fmtSignedPct(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const text = value.toFixed(digits);
  return `${value > 0 ? "+" : value < 0 ? "" : ""}${text}%`;
}

export function fmtFactorValue(value: number | null | undefined, unit: FactorMeta["unit"], locale: "zh" | "en") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (unit === "ratio") return value.toFixed(4);
  if (unit === "yi") {
    const yi = value / 1e8;
    return locale === "en" ? `${yi.toFixed(2)}e8` : `${yi.toFixed(2)} 亿`;
  }
  return `${(value * 100).toFixed(2)}%`;
}

export function metric(
  value: number | null | undefined,
  style: "pct" | "pctu" | "num" | "int" = "pct",
  digits = 2,
) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  if (style === "pct") return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
  if (style === "pctu") return `${n.toFixed(1)}%`;
  if (style === "int") return `${Math.round(n)}`;
  return n.toFixed(digits);
}

export function trendClass(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value) > 0 ? "pos" : Number(value) < 0 ? "neg" : "";
}

export function curveValues(curve: Array<{ nav?: number; benchmark?: number }> | undefined, key: "nav" | "benchmark" = "nav") {
  return (curve || []).map((p) => Number(p[key])).filter((n) => Number.isFinite(n));
}
