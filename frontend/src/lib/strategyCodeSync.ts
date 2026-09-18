/** 策略代码顶部参数块：与左侧表单双向同步 */

import { periodToStartEnd } from "@/lib/detectStore";

export type StrategySyncParams = {
  universe: string;
  benchmark: string;
  commission_rate: number;
  stamp_tax: number;
  slippage_rate: number;
  initial_capital: number;
  top_n: number;
  rebalance_days: number;
  /** period = 预设周期；custom = 自定义起止 */
  range_mode: "period" | "custom";
  /** 预设键：1y / 3y / 5y / 10y 等 */
  backtest_period: string;
  start_date: string;
  end_date: string;
};

const BEGIN = "# --- SVQUANT_PARAMS (与左侧表单同步，请求以表单为准) ---";
const END = "# --- SVQUANT_PARAMS_END ---";

export const DEFAULT_STRATEGY_CODE = `from app.services.strategy.vectorized.factor_strategy import (
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
RANGE_MODE = "period"
BACKTEST_PERIOD = "10y"
START_DATE = ""
END_DATE = ""
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 30
REBALANCE_DAYS = 20
${END}


class MyStrategy(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    # --- SVQUANT_FACTORS_BEGIN ---
    # 请从左侧选择因子（可不选，也可在右侧手写 @factor）
    # --- SVQUANT_FACTORS_END ---

    # --- SVQUANT_EXTRA_BEGIN （信号外逻辑，可手写） ---
    def _post_signal(self, raw):
        """信号外逻辑钩子：默认透传。可在此做趋势门控 / 过滤。"""
        return raw
    # --- SVQUANT_EXTRA_END ---

    # --- SVQUANT_SIGNAL_BEGIN ---
    @signal
    def score(self):
        raw = self.close.pct_change(20) * 0  # 请选择因子
        return self._post_signal(raw)
    # --- SVQUANT_SIGNAL_END ---
`;

/** 事件驱动策略空壳（与左侧回测壳参数块同步） */
export const DEFAULT_EVENT_STRATEGY_CODE = `${BEGIN}
UNIVERSE = "CSI500"
BENCHMARK = "CSI300"
RANGE_MODE = "period"
BACKTEST_PERIOD = "3y"
START_DATE = ""
END_DATE = ""
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 10
REBALANCE_DAYS = 1
${END}


class MyEventStrategy:
    """日频事件策略骨架：在 initialize / rebalance 中编写逻辑。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "amount"})
    required_market_state = frozenset({"suspended", "limit_up", "limit_down"})

    def __init__(
        self,
        benchmark_symbol: str = "000300.SH",
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
    ) -> None:
        self.benchmark_symbol = benchmark_symbol
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        # TODO: 编写选股 / 下单逻辑，例如 context.orders.target_value(...)
        pass
`;

export type StrategyEngineMode = "vectorized" | "event";

/** 从源码推断执行模式 */
export function inferEngineModeFromCode(code: string): StrategyEngineMode {
  const c = code || "";
  if (/execution_mode\s*=\s*["']event["']/.test(c)) return "event";
  if (
    /def\s+initialize\s*\(\s*self\s*,\s*context/.test(c) &&
    !/FactorPortfolioStrategy/.test(c) &&
    !/def\s+generate_signals\s*\(/.test(c)
  ) {
    return "event";
  }
  return "vectorized";
}

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
    `RANGE_MODE = ${JSON.stringify(p.range_mode)}`,
    `BACKTEST_PERIOD = ${JSON.stringify(p.backtest_period)}`,
    `START_DATE = ${JSON.stringify(p.start_date || "")}`,
    `END_DATE = ${JSON.stringify(p.end_date || "")}`,
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

/**
 * 跳过模块 docstring 与全部 import（含多行 from x import ( ... )），
 * 返回应插入参数块的行号。
 */
function findAfterImportsLineIndex(lines: string[]): number {
  let i = 0;
  // 模块 docstring
  const first = (lines[0] || "").trim();
  if (first.startsWith('"""') || first.startsWith("'''")) {
    const q = first.slice(0, 3);
    if (first.length > 3 && first.endsWith(q)) {
      i = 1;
    } else {
      i = 1;
      while (i < lines.length && !lines[i].includes(q)) i += 1;
      if (i < lines.length) i += 1;
    }
  }
  while (i < lines.length && !lines[i].trim()) i += 1;

  while (i < lines.length) {
    const t = lines[i].trim();
    if (!(t.startsWith("from ") || t.startsWith("import "))) break;
    let depth = 0;
    do {
      for (const ch of lines[i]) {
        if (ch === "(") depth += 1;
        else if (ch === ")") depth -= 1;
      }
      i += 1;
    } while (i < lines.length && depth > 0);
    while (i < lines.length && !lines[i].trim()) i += 1;
  }
  return i;
}

/** 去掉已有参数块（兼容误插在 import 括号内的坏块），便于重新插到正确位置 */
function stripParamsBlock(code: string): string {
  let src = code.replace(/\r\n/g, "\n");
  // 兼容历史文案略有差异的标记行
  const beginRe =
    /^[ \t]*# --- SVQUANT_PARAMS\b.*---[ \t]*$/m;
  const endRe = /^[ \t]*# --- SVQUANT_PARAMS_END ---[ \t]*$/m;
  const bm = beginRe.exec(src);
  const em = endRe.exec(src);
  if (bm && em && (em.index ?? 0) > (bm.index ?? 0)) {
    const start = bm.index!;
    let end = em.index! + em[0].length;
    // 吃掉块后多余空行
    while (src[end] === "\n") end += 1;
    let before = src.slice(0, start);
    // 块前若多空行，收成最多一个换行
    before = before.replace(/\n{2,}$/, "\n");
    src = before + src.slice(end);
  }
  return src;
}

/** 左侧参数 → 写回代码中的参数块 + TopN / EveryNTradingDays */
export function applyParamsToCode(code: string, params: StrategySyncParams): string {
  const block = buildParamsBlock(params);
  // 先剥离旧块再按「import 之后」重插，修复多行 import 括号内误插导致的 SyntaxError
  const stripped = stripParamsBlock(code);
  const lines = stripped.split("\n");
  const insertAt = findAfterImportsLineIndex(lines);
  const head = lines.slice(0, insertAt).join("\n");
  const tail = lines.slice(insertAt).join("\n");
  const next = `${head}${head && !head.endsWith("\n") ? "\n" : ""}\n${block}\n\n${tail.replace(/^\n+/, "")}`;
  return applyClassLiterals(next, params.top_n, params.rebalance_days);
}

/** 从代码解析参数；缺项返回 null 字段由调用方保留原值 */
export function parseParamsFromCode(code: string): Partial<StrategySyncParams> {
  const out: Partial<StrategySyncParams> = {};
  const uni = /UNIVERSE\s*=\s*["']([^"']+)["']/.exec(code);
  if (uni) out.universe = uni[1];
  const bm = /BENCHMARK\s*=\s*["']([^"']+)["']/.exec(code);
  if (bm) out.benchmark = bm[1];
  const rm = /RANGE_MODE\s*=\s*["']([^"']+)["']/.exec(code);
  if (rm && (rm[1] === "period" || rm[1] === "custom")) {
    out.range_mode = rm[1];
  }
  const bp = /BACKTEST_PERIOD\s*=\s*["']([^"']+)["']/.exec(code);
  if (bp) out.backtest_period = bp[1];
  const sd = /START_DATE\s*=\s*["']([^"']*)["']/.exec(code);
  if (sd) out.start_date = sd[1];
  const ed = /END_DATE\s*=\s*["']([^"']*)["']/.exec(code);
  if (ed) out.end_date = ed[1];
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

const STRATEGY_IMPORTS = `from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)`;

/** 已有向量化策略 import（现网路径或旧 quantcore）则不再重复插入 */
function hasStrategyImports(code: string): boolean {
  return (
    /from\s+app\.services\.strategy\.vectorized\.factor_strategy\s+import/.test(
      code,
    ) ||
    /from\s+app\.quantcore\s+import/.test(code) ||
    /from\s+quantcore\s+import/.test(code) ||
    /import\s+quantcore\b/.test(code)
  );
}

/** 补平台 import 时保留 Python future import 必须位于普通 import 之前的规则。 */
function addStrategyImports(code: string): string {
  if (hasStrategyImports(code)) return code;
  const lines = code.replace(/\r\n/g, "\n").split("\n");
  const insertAt = findAfterImportsLineIndex(lines);
  const head = lines.slice(0, insertAt).join("\n").trimEnd();
  const tail = lines.slice(insertAt).join("\n").replace(/^\n+/, "");
  return [head, STRATEGY_IMPORTS, tail].filter(Boolean).join("\n\n");
}

function defaultRangeFields(period = "10y"): Pick<
  StrategySyncParams,
  "range_mode" | "backtest_period" | "start_date" | "end_date"
> {
  const r = periodToStartEnd(period);
  return {
    range_mode: "period",
    backtest_period: period,
    start_date: r.start,
    end_date: r.end,
  };
}

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
    ...defaultRangeFields("10y"),
  });
}

function mergeSyncParams(
  partial: Partial<StrategySyncParams> &
    Pick<
      StrategySyncParams,
      | "universe"
      | "benchmark"
      | "commission_rate"
      | "stamp_tax"
      | "slippage_rate"
      | "initial_capital"
      | "top_n"
      | "rebalance_days"
    >,
): StrategySyncParams {
  const period = partial.backtest_period || "10y";
  const fallback = defaultRangeFields(period);
  return {
    ...partial,
    range_mode: partial.range_mode || fallback.range_mode,
    backtest_period: period,
    start_date: partial.start_date || fallback.start_date,
    end_date: partial.end_date || fallback.end_date,
  };
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

const FACTORS_BEGIN = "    # --- SVQUANT_FACTORS_BEGIN ---";
const FACTORS_END = "    # --- SVQUANT_FACTORS_END ---";
const EXTRA_BEGIN = "    # --- SVQUANT_EXTRA_BEGIN （信号外逻辑，可手写） ---";
const EXTRA_END = "    # --- SVQUANT_EXTRA_END ---";
const SIGNAL_BEGIN = "    # --- SVQUANT_SIGNAL_BEGIN ---";
const SIGNAL_END = "    # --- SVQUANT_SIGNAL_END ---";

const DEFAULT_EXTRA = [
  EXTRA_BEGIN,
  "    def _post_signal(self, raw):",
  '        """信号外逻辑钩子：默认透传。可在此做趋势门控 / 过滤。"""',
  "        return raw",
  EXTRA_END,
].join("\n");

/**
 * 平台策略库源码 → 研究页模板（PARAMS + FACTORS/EXTRA/SIGNAL 标记）。
 * 保留原有 @factor / @signal 逻辑；同步 TopN / 调仓到参数块。
 */
export function wrapBuiltinLibraryStrategy(raw: string): string {
  let code = (raw || "").trim();
  if (!code) return DEFAULT_STRATEGY_CODE;

  // 事件策略：只补参数块，绝不包成 FactorPortfolio
  if (inferEngineModeFromCode(code) === "event") {
    const parsed = parseParamsFromCode(code);
    return applyParamsToCode(
      code,
      mergeSyncParams({
        universe: parsed.universe || "CSI500",
        benchmark: parsed.benchmark || "CSI300",
        commission_rate: parsed.commission_rate ?? 0.0003,
        stamp_tax: parsed.stamp_tax ?? 0.001,
        slippage_rate: parsed.slippage_rate ?? 0.001,
        initial_capital: parsed.initial_capital ?? 1_000_000,
        top_n: parsed.top_n ?? 10,
        rebalance_days: parsed.rebalance_days ?? 1,
        range_mode: parsed.range_mode,
        backtest_period: parsed.backtest_period || "3y",
        start_date: parsed.start_date,
        end_date: parsed.end_date,
      }),
    );
  }

  if (!hasStrategyImports(code)) {
    code = addStrategyImports(code);
  }

  // 已带完整标记：只补参数块，并用类属性对齐 TOP_N / REBALANCE
  if (
    code.includes(FACTORS_BEGIN) &&
    code.includes(SIGNAL_BEGIN) &&
    /FactorPortfolioStrategy/.test(code)
  ) {
    const parsed = parseParamsFromCode(code);
    return applyParamsToCode(
      code,
      mergeSyncParams({
        universe: parsed.universe || "CSI500",
        benchmark: parsed.benchmark || "CSI300",
        commission_rate: parsed.commission_rate ?? 0.0003,
        stamp_tax: parsed.stamp_tax ?? 0.001,
        slippage_rate: parsed.slippage_rate ?? 0.001,
        initial_capital: parsed.initial_capital ?? 1_000_000,
        top_n: parsed.top_n ?? 30,
        rebalance_days: parsed.rebalance_days ?? 20,
        range_mode: parsed.range_mode,
        backtest_period: parsed.backtest_period,
        start_date: parsed.start_date,
        end_date: parsed.end_date,
      }),
    );
  }

  // 旧 generate_signals：原样补参数（左侧积木会灰显）
  if (/def\s+generate_signals\s*\(/.test(code)) {
    const parsed = parseParamsFromCode(code);
    return applyParamsToCode(
      code,
      mergeSyncParams({
        universe: parsed.universe || "CSI500",
        benchmark: parsed.benchmark || "CSI300",
        commission_rate: parsed.commission_rate ?? 0.0003,
        stamp_tax: parsed.stamp_tax ?? 0.001,
        slippage_rate: parsed.slippage_rate ?? 0.001,
        initial_capital: parsed.initial_capital ?? 1_000_000,
        top_n: parsed.top_n ?? 30,
        rebalance_days: parsed.rebalance_days ?? 20,
        range_mode: parsed.range_mode,
        backtest_period: parsed.backtest_period,
        start_date: parsed.start_date,
        end_date: parsed.end_date,
      }),
    );
  }

  if (!/FactorPortfolioStrategy/.test(code)) {
    return wrapFactorCodeAsStrategy(code);
  }

  const classRe =
    /class\s+(\w+)\s*\(\s*FactorPortfolioStrategy\s*\)\s*:/;
  const classMatch = classRe.exec(code);
  if (!classMatch) {
    const parsed = parseParamsFromCode(code);
    return applyParamsToCode(
      code,
      mergeSyncParams({
        universe: "CSI500",
        benchmark: "CSI300",
        commission_rate: 0.0003,
        stamp_tax: 0.001,
        slippage_rate: 0.001,
        initial_capital: 1_000_000,
        top_n: parsed.top_n ?? 30,
        rebalance_days: parsed.rebalance_days ?? 20,
        range_mode: parsed.range_mode,
        backtest_period: parsed.backtest_period,
        start_date: parsed.start_date,
        end_date: parsed.end_date,
      }),
    );
  }

  const clsStart = classMatch.index!;
  const afterHeader = code.indexOf("\n", clsStart) + 1;
  const before = code.slice(0, afterHeader);
  let body = code.slice(afterHeader);

  // 切分：属性行 / @factor 段 / @signal 段
  const lines = body.replace(/\r\n/g, "\n").split("\n");
  const attrLines: string[] = [];
  const factorLines: string[] = [];
  const signalLines: string[] = [];
  let mode: "attr" | "factor" | "signal" = "attr";

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === "@factor") {
      mode = "factor";
      factorLines.push(line);
      continue;
    }
    if (trimmed === "@signal") {
      mode = "signal";
      signalLines.push(line);
      continue;
    }
    if (mode === "attr") {
      // 空行仍属属性区，直到第一个装饰器
      attrLines.push(line);
    } else if (mode === "factor") {
      factorLines.push(line);
    } else {
      signalLines.push(line);
    }
  }

  while (attrLines.length && !attrLines[attrLines.length - 1].trim()) {
    attrLines.pop();
  }
  while (factorLines.length && !factorLines[factorLines.length - 1].trim()) {
    factorLines.pop();
  }
  while (signalLines.length && !signalLines[signalLines.length - 1].trim()) {
    signalLines.pop();
  }

  let signalBody = signalLines.join("\n");
  // 简单 return → raw + _post_signal（尚无钩子时）
  if (
    signalBody &&
    !/_post_signal\s*\(/.test(signalBody) &&
    /^\s*@signal\s*\n\s*def\s+\w+\s*\([^)]*\)\s*:\s*\n(\s+)return\s+(.+)\s*$/m.test(
      signalBody,
    )
  ) {
    signalBody = signalBody.replace(
      /^(\s*)return\s+(.+)\s*$/m,
      (_m, ind, expr) => `${ind}raw = ${expr.trim()}\n${ind}return self._post_signal(raw)`,
    );
  }
  if (!signalBody.trim()) {
    signalBody = [
      "    @signal",
      "    def score(self):",
      "        raw = self.close.pct_change(20) * 0  # 请完善 signal",
      "        return self._post_signal(raw)",
    ].join("\n");
  }

  const factorBlock = factorLines.length
    ? `${FACTORS_BEGIN}\n${factorLines.join("\n")}\n${FACTORS_END}`
    : `${FACTORS_BEGIN}\n    # 请从左侧选择因子（可不选，也可在右侧手写 @factor）\n${FACTORS_END}`;

  const assembled = [
    attrLines.join("\n").replace(/\s+$/, ""),
    "",
    factorBlock,
    "",
    DEFAULT_EXTRA,
    "",
    `${SIGNAL_BEGIN}\n${signalBody}\n${SIGNAL_END}`,
    "",
  ].join("\n");

  let next = `${before}${assembled}`;
  const parsed = parseParamsFromCode(next);
  // 类属性优先（库策略 TopN/调仓）
  const top =
    Number(/TopN\s*\(\s*(\d+)\s*\)/.exec(next)?.[1]) || parsed.top_n || 30;
  const reb =
    Number(/EveryNTradingDays\s*\(\s*(\d+)\s*\)/.exec(next)?.[1]) ||
    parsed.rebalance_days ||
    20;
  next = applyParamsToCode(
    next,
    mergeSyncParams({
      universe: "CSI500",
      benchmark: "CSI300",
      commission_rate: 0.0003,
      stamp_tax: 0.001,
      slippage_rate: 0.001,
      initial_capital: 1_000_000,
      top_n: top,
      rebalance_days: reb,
      range_mode: parsed.range_mode,
      backtest_period: parsed.backtest_period,
      start_date: parsed.start_date,
      end_date: parsed.end_date,
    }),
  );
  return next;
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
    if (!hasStrategyImports(next)) {
      next = addStrategyImports(next);
    }
    if (!next.includes(BEGIN)) {
      next = applyParamsToCode(
        next,
        mergeSyncParams({
          universe: "CSI500",
          benchmark: "CSI300",
          commission_rate: 0.0003,
          stamp_tax: 0.001,
          slippage_rate: 0.001,
          initial_capital: 1_000_000,
          top_n: 30,
          rebalance_days: 20,
        }),
      );
    }
    return next;
  }

  const defs = listTopLevelDefs(code);
  if (!defs.length) {
    return `${addStrategyImports(code)}\n\n${defaultParamsBlock()}\n`;
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
