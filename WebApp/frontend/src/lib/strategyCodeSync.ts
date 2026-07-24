/** 策略代码顶部参数块：与左侧表单双向同步 */

export type StrategySyncParams = {
  universe: string;
  benchmark: string;
  commission_rate: number;
  stamp_tax: number;
  slippage_rate: number;
  initial_capital: number;
  top_n: number;
  rebalance_days: number;
};

const BEGIN = "# --- SVQUANT_PARAMS (与左侧表单同步，请求以表单为准) ---";
const END = "# --- SVQUANT_PARAMS_END ---";

export const DEFAULT_STRATEGY_CODE = `from quantcore import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)

${BEGIN}
UNIVERSE = "CSI500"
BENCHMARK = "CSI300"
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 30
REBALANCE_DAYS = 20
${END}


class DemoMomentumStrategy(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def momentum_20d(self):
        return self.close.pct_change(20)

    @signal
    def score(self):
        return self.rank(self.momentum_20d())
`;

function formatCapital(n: number): string {
  if (!Number.isFinite(n)) return "1_000_000";
  const v = Math.round(n);
  if (v >= 1_000_000 && v % 1_000_000 === 0) {
    return `${v / 1_000_000}_000_000`;
  }
  if (v >= 1000) {
    return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, "_");
  }
  return String(v);
}

function parseNumberLiteral(raw: string): number | null {
  const t = raw.trim().replace(/_/g, "");
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function buildParamsBlock(p: StrategySyncParams): string {
  return [
    BEGIN,
    `UNIVERSE = ${JSON.stringify(p.universe)}`,
    `BENCHMARK = ${JSON.stringify(p.benchmark)}`,
    `COMMISSION_RATE = ${p.commission_rate}`,
    `STAMP_TAX = ${p.stamp_tax}`,
    `SLIPPAGE_RATE = ${p.slippage_rate}`,
    `INITIAL_CAPITAL = ${formatCapital(p.initial_capital)}`,
    `TOP_N = ${Math.max(1, Math.round(p.top_n))}`,
    `REBALANCE_DAYS = ${Math.max(1, Math.round(p.rebalance_days))}`,
    END,
  ].join("\n");
}

function applyClassLiterals(code: string, topN: number, rebalanceDays: number): string {
  const n = Math.max(1, Math.round(topN));
  const d = Math.max(1, Math.round(rebalanceDays));
  return code
    .replace(/TopN\s*\(\s*\d+\s*\)/g, `TopN(${n})`)
    .replace(/EveryNTradingDays\s*\(\s*\d+\s*\)/g, `EveryNTradingDays(${d})`);
}

/** 左侧参数 → 写回代码中的参数块 + TopN / EveryNTradingDays */
export function applyParamsToCode(code: string, params: StrategySyncParams): string {
  const block = buildParamsBlock(params);
  const beginIdx = code.indexOf(BEGIN);
  const endIdx = code.indexOf(END);
  let next: string;
  if (beginIdx >= 0 && endIdx > beginIdx) {
    const afterEnd = endIdx + END.length;
    next = code.slice(0, beginIdx) + block + code.slice(afterEnd);
  } else {
    const lines = code.split("\n");
    let insertAt = 0;
    for (let i = 0; i < lines.length; i++) {
      const t = lines[i].trim();
      if (t.startsWith("from ") || t.startsWith("import ")) insertAt = i + 1;
      else if (t === "" && insertAt > 0) {
        // keep scanning blank after imports
      } else if (insertAt > 0 && t) break;
    }
    const head = lines.slice(0, insertAt).join("\n");
    const tail = lines.slice(insertAt).join("\n");
    next = `${head}${head.endsWith("\n") || !head ? "" : "\n"}\n${block}\n\n${tail.replace(/^\n+/, "")}`;
  }
  return applyClassLiterals(next, params.top_n, params.rebalance_days);
}

/** 从代码解析参数；缺项返回 null 字段由调用方保留原值 */
export function parseParamsFromCode(code: string): Partial<StrategySyncParams> {
  const out: Partial<StrategySyncParams> = {};
  const uni = /UNIVERSE\s*=\s*["']([^"']+)["']/.exec(code);
  if (uni) out.universe = uni[1];
  const bm = /BENCHMARK\s*=\s*["']([^"']+)["']/.exec(code);
  if (bm) out.benchmark = bm[1];
  const c = /COMMISSION_RATE\s*=\s*([0-9_]+(?:\.[0-9]+)?)/.exec(code);
  if (c) {
    const n = parseNumberLiteral(c[1]);
    if (n != null) out.commission_rate = n;
  }
  const st = /STAMP_TAX\s*=\s*([0-9_]+(?:\.[0-9]+)?)/.exec(code);
  if (st) {
    const n = parseNumberLiteral(st[1]);
    if (n != null) out.stamp_tax = n;
  }
  const s = /SLIPPAGE_RATE\s*=\s*([0-9_]+(?:\.[0-9]+)?)/.exec(code);
  if (s) {
    const n = parseNumberLiteral(s[1]);
    if (n != null) out.slippage_rate = n;
  }
  const cap = /INITIAL_CAPITAL\s*=\s*([0-9_]+(?:\.[0-9]+)?)/.exec(code);
  if (cap) {
    const n = parseNumberLiteral(cap[1]);
    if (n != null) out.initial_capital = n;
  }
  const topBlock = /TOP_N\s*=\s*([0-9_]+)/.exec(code);
  const topCls = /TopN\s*\(\s*(\d+)\s*\)/.exec(code);
  if (topCls) out.top_n = Number(topCls[1]);
  else if (topBlock) {
    const n = parseNumberLiteral(topBlock[1]);
    if (n != null) out.top_n = n;
  }
  const rebBlock = /REBALANCE_DAYS\s*=\s*([0-9_]+)/.exec(code);
  const rebCls = /EveryNTradingDays\s*\(\s*(\d+)\s*\)/.exec(code);
  if (rebCls) out.rebalance_days = Number(rebCls[1]);
  else if (rebBlock) {
    const n = parseNumberLiteral(rebBlock[1]);
    if (n != null) out.rebalance_days = n;
  }
  return out;
}

const STRATEGY_IMPORTS = `from quantcore import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)`;

function defaultParamsBlock(): string {
  return buildParamsBlock({
    universe: "CSI500",
    benchmark: "CSI300",
    commission_rate: 0.0003,
    stamp_tax: 0.001,
    slippage_rate: 0.001,
    initial_capital: 1_000_000,
    top_n: 30,
    rebalance_days: 20,
  });
}

function listTopLevelDefs(code: string): string[] {
  const names: string[] = [];
  const re = /^def\s+([A-Za-z_]\w*)\s*\(/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(code))) names.push(m[1]);
  return names;
}

function indentBlock(src: string, spaces = 4): string {
  const pad = " ".repeat(spaces);
  return src
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => (line.trim() ? pad + line : line))
    .join("\n");
}

/**
 * 社区因子代码 → 可回测的 FactorPortfolioStrategy。
 * 已含策略类则尽量只补 import / 参数块。
 */
export function wrapFactorCodeAsStrategy(raw: string): string {
  const code = (raw || "").trim();
  if (!code) return DEFAULT_STRATEGY_CODE;

  const hasClass = /^\s*class\s+\w+/m.test(code);
  const looksStrategy =
    hasClass &&
    (/FactorPortfolioStrategy/.test(code) || /generate_signals/.test(code));

  if (looksStrategy) {
    let next = code;
    if (!/from\s+quantcore\s+import/.test(next) && !/import\s+quantcore/.test(next)) {
      next = `${STRATEGY_IMPORTS}\n\n${next}`;
    }
    if (!next.includes(BEGIN)) {
      next = applyParamsToCode(next, {
        universe: "CSI500",
        benchmark: "CSI300",
        commission_rate: 0.0003,
        stamp_tax: 0.001,
        slippage_rate: 0.001,
        initial_capital: 1_000_000,
        top_n: 30,
        rebalance_days: 20,
      });
    }
    return next;
  }

  const defs = listTopLevelDefs(code);
  if (!defs.length) {
    return `${STRATEGY_IMPORTS}\n\n${defaultParamsBlock()}\n\n${code}\n`;
  }

  const publicDefs = defs.filter((n) => !n.startsWith("_"));
  const scoreName =
    publicDefs.find((n) => n !== "combo_factor") ||
    publicDefs[publicDefs.length - 1] ||
    defs[defs.length - 1];

  // 仅给公开方法加 @factor；私有 _xxx 保持普通方法供调用
  const lines = code.replace(/\r\n/g, "\n").split("\n");
  const outLines: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const defMatch = /^(\s*)def\s+([A-Za-z_]\w*)\s*\(/.exec(line);
    if (
      defMatch &&
      defs.includes(defMatch[2]) &&
      !defMatch[2].startsWith("_")
    ) {
      const prev = outLines.length ? outLines[outLines.length - 1].trim() : "";
      if (!/^@(?:factor|signal)\b/.test(prev)) {
        outLines.push(`${defMatch[1]}@factor`);
      }
    }
    outLines.push(line);
  }
  const body = outLines.join("\n");

  const classBody = [
    "class CommunityCloneStrategy(FactorPortfolioStrategy):",
    "    selector = TopN(30)",
    "    weighting = EqualWeight()",
    "    rebalance = EveryNTradingDays(20)",
    "",
    indentBlock(body.trim(), 4),
    "",
    "    @signal",
    "    def score(self):",
    `        return self.rank(self.${scoreName}())`,
    "",
  ].join("\n");

  return `${STRATEGY_IMPORTS}\n\n${defaultParamsBlock()}\n\n${classBody}`;
}

