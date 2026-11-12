/** 策略页信号因子：对齐因子检测，从 600+ 因子库选码并写入 @factor / @signal */

import {
  DYNAMIC_FACTOR_LIBS,
  extractFactorWithHelpers,
  loadFactors,
  loadLibrarySource,
  type FactorMeta,
} from "@/lib/factorCatalog";
import {
  listAllUserLibraryFactors,
  userLibraryFactorToMeta,
} from "@/lib/userFactorLibraries";
import {
  expandQlibAlphaFactorSource,
  isQlibAlphaFactorName,
} from "@/lib/qlibFactorExpand";

export type StrategyWeightMode = "sum" | "product" | "custom";

/** 是否适合展示「因子选择+权重」（结构化组合模板） */
export function usesFactorPortfolioTemplate(code: string): boolean {
  const c = code || "";
  if (!/FactorPortfolioStrategy/.test(c)) return false;
  if (/def\s+generate_signals\s*\(/.test(c)) return false;
  return true;
}

export const FACTORS_BEGIN = "    # --- SVQUANT_FACTORS_BEGIN ---";
export const FACTORS_END = "    # --- SVQUANT_FACTORS_END ---";
export const EXTRA_BEGIN = "    # --- SVQUANT_EXTRA_BEGIN （信号外逻辑，可手写） ---";
export const EXTRA_END = "    # --- SVQUANT_EXTRA_END ---";
export const SIGNAL_BEGIN = "    # --- SVQUANT_SIGNAL_BEGIN ---";
export const SIGNAL_END = "    # --- SVQUANT_SIGNAL_END ---";

function equalWeights(n: number): number[] {
  if (n <= 0) return [];
  const base = Math.floor(100 / n);
  const weights = Array.from({ length: n }, () => base);
  weights[0] += 100 - base * n;
  return weights;
}

export function equalPowers(n: number): number[] {
  return Array.from({ length: n }, () => 1);
}

export function normalizeSignalWeights(
  ids: string[],
  weights?: number[],
): number[] {
  const n = ids.length;
  if (n <= 0) return [];
  if (!weights || weights.length !== n) return equalWeights(n);
  const sum = weights.reduce((a, b) => a + (Number(b) || 0), 0);
  if (sum <= 0) return equalWeights(n);
  return weights.map((w) => Number(w) || 0);
}

export function normalizeSignalPowers(
  ids: string[],
  powers?: number[],
): number[] {
  const n = ids.length;
  if (n <= 0) return [];
  if (!powers || powers.length !== n) return equalPowers(n);
  return powers.map((p) => (typeof p === "number" && Number.isFinite(p) ? p : 1));
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function indentClassBody(src: string): string {
  return src
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => (line.trim() ? `    ${line}` : line))
    .join("\n");
}

function splitTopLevelDefs(src: string): { name: string; block: string }[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out: { name: string; block: string }[] = [];
  let i = 0;
  while (i < lines.length) {
    const m = /^def\s+([A-Za-z_]\w*)\s*\(/.exec(lines[i]);
    if (!m) {
      i += 1;
      continue;
    }
    const name = m[1];
    const chunk = [lines[i]];
    i += 1;
    while (i < lines.length) {
      const line = lines[i];
      if (/^def\s+[A-Za-z_]\w*\s*\(/.test(line)) break;
      chunk.push(line);
      i += 1;
    }
    while (chunk.length > 1 && !chunk[chunk.length - 1].trim()) chunk.pop();
    out.push({ name, block: chunk.join("\n") });
  }
  return out;
}

async function resolveOneFactorSource(meta: FactorMeta): Promise<string> {
  if (meta.userLibraryFactorId != null || (meta.library || "").startsWith("user_lib_")) {
    let body = (meta.body || "").trim();
    if (meta.formulaReady === false || !body) {
      throw new Error(`个人因子「${meta.name}」尚未填写公式，请先在因子库补全源码。`);
    }
    const methodName = meta.methodName || meta.name;
    if (methodName !== meta.name) {
      body = body.replace(
        new RegExp(`^def\\s+${escapeRe(methodName)}\\s*\\(`, "m"),
        `def ${meta.name}(`,
      );
    }
    return body;
  }
  if (DYNAMIC_FACTOR_LIBS.has(meta.library) || isQlibAlphaFactorName(meta.name)) {
    const expanded = expandQlibAlphaFactorSource(meta.name);
    if (!expanded) {
      throw new Error(
        `「${meta.name}」属于动态库，暂无法展开为策略源码，请换其它因子。`,
      );
    }
    return expanded;
  }
  const src = await loadLibrarySource(meta.libraryFile);
  const methodName = meta.methodName || meta.name;
  let extracted = extractFactorWithHelpers(src, methodName);
  if (methodName !== meta.name) {
    extracted = extracted.replace(
      new RegExp(`^def\\s+${escapeRe(methodName)}\\s*\\(`, "m"),
      `def ${meta.name}(`,
    );
  }
  return extracted;
}

/** 合法 Python 方法名（策略内自定义因子） */
export function isValidFactorMethodName(name: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name);
}

/** 策略内一次性因子 stub（不在因子目录时新建用） */
export const CUSTOM_FACTOR_STUB_MARKER =
  "return self.close.pct_change(20) * 0  # TODO";

export function buildCustomFactorStub(
  methodName: string,
  description?: string,
): string {
  if (!isValidFactorMethodName(methodName)) {
    throw new Error(`非法因子名「${methodName}」`);
  }
  const doc = (description || "临时因子（仅本策略）")
    .replace(/\\/g, "\\\\")
    .replace(/"""/g, "'''");
  return [
    `def ${methodName}(self):`,
    `    """${doc}"""`,
    `    ${CUSTOM_FACTOR_STUB_MARKER}`,
  ].join("\n");
}

/** 找出代码里仍是未编辑占位实现的临时因子名；有则必须阻止回测。 */
export function findUneditedFactorStub(code: string): string | null {
  const lines = (code || "").replace(/\r\n/g, "\n").split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    if (!lines[i].includes(CUSTOM_FACTOR_STUB_MARKER)) continue;
    for (let j = i; j >= 0; j -= 1) {
      const m = /^\s*def\s+([A-Za-z_]\w*)\s*\(/.exec(lines[j]);
      if (m) return m[1];
    }
    return "临时因子";
  }
  return null;
}

export async function resolveStrategyFactorBodies(
  factorIds: string[],
  opts?: { fallbackCode?: string; tempLabels?: Record<string, string> },
): Promise<string> {
  if (!factorIds.length) {
    return "    # 请从左侧选择因子（可不选，也可在右侧手写 @factor）";
  }
  const catalog = await loadFactors();
  let personal: FactorMeta[] = [];
  let personalError = "";
  try {
    personal = (await listAllUserLibraryFactors()).map(userLibraryFactorToMeta);
  } catch (e) {
    personalError = e instanceof Error ? e.message : String(e);
  }
  const byName = new Map(catalog.map((f) => [f.name, f]));
  const ambiguous = new Set<string>();
  for (const f of personal) {
    if (byName.has(f.name)) ambiguous.add(f.name);
    byName.set(f.name, f);
  }
  const seen = new Set<string>();
  const pieces: string[] = [];
  const fallback = opts?.fallbackCode || "";
  const tempLabels = opts?.tempLabels || {};

  for (const id of factorIds) {
    if (ambiguous.has(id)) {
      throw new Error(
        `因子「${id}」同时存在于内置库和个人因子库，名称冲突无法确定源码；请重命名个人因子后重试。`,
      );
    }
    const meta = byName.get(id);
    let raw: string;
    if (meta) {
      raw = await resolveOneFactorSource(meta);
    } else {
      // 优先保留策略代码里已有实现；临时因子才允许生成可编辑 stub
      const fromCode = extractFactorDefFromCode(fallback, id);
      if (fromCode) {
        raw = fromCode;
      } else if (tempLabels[id]) {
        raw = buildCustomFactorStub(id, tempLabels[id]);
      } else if (personalError) {
        throw new Error(
          `无法加载个人因子库（${personalError}），且「${id}」不是内置因子或策略内已有实现，请重试。`,
        );
      } else {
        throw new Error(
          `因子「${id}」不在内置/个人因子目录中，策略代码里也没有实现；请重新选择，或先编辑临时因子。`,
        );
      }
    }
    const defs = splitTopLevelDefs(raw);
    if (!defs.some((d) => d.name === id)) {
      throw new Error(
        `因子「${id}」的源码中未解析出对应方法，已停止同步；请检查因子源码或重新选择。`,
      );
    }
    for (const { name, block } of defs) {
      if (seen.has(name)) continue;
      seen.add(name);
      const isSelectedPublic =
        !name.startsWith("_") && (name === id || factorIds.includes(name));
      const text = isSelectedPublic ? `@factor\n${block}` : block;
      pieces.push(indentClassBody(text));
    }
  }
  return pieces.join("\n\n");
}

/** 从策略代码 FACTORS 块（或全文）抽出某个 @factor 方法（含前置 _ 辅助） */
export function extractFactorDefFromCode(code: string, methodName: string): string | null {
  if (!code || !methodName) return null;
  const marked = extractMarked(code, FACTORS_BEGIN, FACTORS_END);
  const src = (marked || code).replace(/\r\n/g, "\n");
  // 去掉标记行再解析
  const cleaned = src
    .replace(FACTORS_BEGIN, "")
    .replace(FACTORS_END, "")
    .replace(/^#\s*请从左侧选择因子.*$/m, "");

  const defs = splitTopLevelDefs(
    cleaned
      .split("\n")
      .map((l) => l.replace(/^    /, "")) // 去类缩进
      .join("\n")
      .replace(/@factor\s*\n/g, ""),
  );
  if (!defs.length) {
    // 再试：保留 @factor 行的粗解析
    const re = new RegExp(
      `@factor\\s*\\n\\s*def\\s+${escapeRe(methodName)}\\s*\\([\\s\\S]*?(?=\\n\\s*@factor|\\n\\s*@signal|\\n\\s*# --- SVQUANT_|$)`,
    );
    const m = re.exec(code.replace(/\r\n/g, "\n"));
    if (!m) return null;
    return m[0]
      .replace(/^@factor\s*\n/, "")
      .split("\n")
      .map((l) => l.replace(/^    /, ""))
      .join("\n")
      .trim();
  }
  const helpers = defs.filter((d) => d.name.startsWith("_"));
  const main = defs.find((d) => d.name === methodName);
  if (!main) return null;
  return [...helpers.map((h) => h.block), main.block].join("\n\n");
}

/**
 * 从策略代码解析左侧应预选的因子 / 权重 / 合成模式。
 * - 能解析出加权 rank → sum
 * - 能解析出赋幂相乘 → product
 * - 否则 custom（保留手写 @signal），权重等权仅用于展示
 */
export function parseLibrarySignalSelection(code: string): {
  ids: string[];
  weights: number[];
  powers: number[];
  weightMode: StrategyWeightMode;
} {
  const c = (code || "").replace(/\r\n/g, "\n");
  const ids: string[] = [];
  const re = /@factor\s*\n\s*def\s+([A-Za-z_]\w*)\s*\(/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(c))) {
    if (!ids.includes(m[1])) ids.push(m[1]);
  }
  if (!ids.length) {
    return { ids: [], weights: [], powers: [], weightMode: "sum" };
  }

  const sigMarked = extractMarked(c, SIGNAL_BEGIN, SIGNAL_END) || c;
  // 赋权相加：0.5 * self.rank(self.xxx())
  const sumParts: { coef: number; method: string }[] = [];
  const sumRe =
    /([\d.]+)\s*\*\s*self\.rank\(\s*self\.([A-Za-z_]\w*)\(\s*\)\s*\)/g;
  while ((m = sumRe.exec(sigMarked))) {
    sumParts.push({ coef: Number(m[1]), method: m[2] });
  }
  if (
    sumParts.length >= 1 &&
    sumParts.every((p) => ids.includes(p.method)) &&
    new Set(sumParts.map((p) => p.method)).size === sumParts.length
  ) {
    const ordered = ids.map((id) => {
      const hit = sumParts.find((p) => p.method === id);
      return hit ? hit.coef : 0;
    });
    const s = ordered.reduce((a, b) => a + b, 0) || 1;
    const weights = ordered.map((x) => Math.round((x / s) * 100));
    const drift = 100 - weights.reduce((a, b) => a + b, 0);
    if (weights.length) weights[0] += drift;
    return {
      ids,
      weights,
      powers: equalPowers(ids.length),
      weightMode: "sum",
    };
  }

  // 赋幂相乘：(self.rank(self.xxx()) ** 1.2)
  const prodParts: { power: number; method: string }[] = [];
  const prodRe =
    /self\.rank\(\s*self\.([A-Za-z_]\w*)\(\s*\)\s*\)\s*\*\*\s*([\d.]+)/g;
  while ((m = prodRe.exec(sigMarked))) {
    prodParts.push({ method: m[1], power: Number(m[2]) });
  }
  if (
    prodParts.length >= 1 &&
    prodParts.every((p) => ids.includes(p.method)) &&
    new Set(prodParts.map((p) => p.method)).size === prodParts.length
  ) {
    return {
      ids,
      weights: equalWeights(ids.length),
      powers: ids.map((id) => prodParts.find((p) => p.method === id)?.power ?? 1),
      weightMode: "product",
    };
  }

  // 单因子且 signal 仅为 self.xxx() / rank(self.xxx())（含 wrap 后的 raw =）→ sum 100%
  if (ids.length === 1) {
    const only = ids[0];
    const call = `(?:self\\.rank\\(\\s*)?self\\.${escapeRe(only)}\\(\\s*\\)`;
    const simple = new RegExp(
      `(?:return\\s+|raw\\s*=\\s*)${call}`,
    );
    if (simple.test(sigMarked) && !/where\s*\(/.test(sigMarked)) {
      return {
        ids,
        weights: [100],
        powers: [1],
        weightMode: "sum",
      };
    }
  }

  // 复杂手写 signal（如双均线 where 过滤）→ 自定义，因子仍预选
  return {
    ids,
    weights: equalWeights(ids.length),
    powers: equalPowers(ids.length),
    weightMode: "custom",
  };
}

/** 左侧因子为空时：从代码 @factor 块补全；仍空则用 fallback（如项目配置 / 历史快照）。 */
export function hydrateSignalSelection<
  T extends {
    strategy_code?: string;
    signal_factor_ids?: string[];
    signal_factor_weights?: number[];
    signal_factor_powers?: number[];
    signal_weight_mode?: StrategyWeightMode;
    signal_temp_labels?: Record<string, string>;
  },
>(
  config: T,
  fallback?: Partial<
    Pick<
      T,
      | "signal_factor_ids"
      | "signal_factor_weights"
      | "signal_factor_powers"
      | "signal_weight_mode"
      | "signal_temp_labels"
    >
  > | null,
): T {
  if ((config.signal_factor_ids || []).length > 0) return config;
  const parsed = parseLibrarySignalSelection(config.strategy_code || "");
  if (parsed.ids.length > 0) {
    return {
      ...config,
      signal_factor_ids: parsed.ids,
      signal_factor_weights: parsed.weights,
      signal_factor_powers: parsed.powers,
      signal_weight_mode: parsed.weightMode,
    };
  }
  const fbIds = fallback?.signal_factor_ids || [];
  if (fbIds.length > 0) {
    return {
      ...config,
      signal_factor_ids: fbIds,
      signal_factor_weights:
        fallback?.signal_factor_weights || equalWeights(fbIds.length),
      signal_factor_powers:
        fallback?.signal_factor_powers || equalPowers(fbIds.length),
      signal_weight_mode: fallback?.signal_weight_mode || "sum",
      signal_temp_labels: {
        ...(config.signal_temp_labels || {}),
        ...(fallback?.signal_temp_labels || {}),
      },
    };
  }
  return config;
}

function buildFactorBlock(bodiesInner: string): string {
  const inner = (bodiesInner || "").replace(/\s+$/, "");
  return `${FACTORS_BEGIN}\n${inner}\n${FACTORS_END}`;
}

function buildSignalBlock(
  ids: string[],
  weights: number[],
  powers: number[],
  mode: StrategyWeightMode,
): string {
  const lines = [SIGNAL_BEGIN, "    @signal", "    def score(self):"];
  const valid = ids.filter((id) => /^[A-Za-z_]\w*$/.test(id));

  if (mode === "custom") {
    lines.push(`        # 自定义合成：请在下方自行编写（可用 self.<因子>()）`);
    if (valid.length) {
      lines.push(
        `        # 已选：${valid.map((c) => `self.${c}()`).join("、")}`,
      );
      lines.push(`        raw = self.rank(self.${valid[0]}())`);
    } else {
      lines.push(`        raw = self.close.pct_change(20) * 0  # 请先选择因子`);
    }
    lines.push(`        return self._post_signal(raw)`);
    lines.push(SIGNAL_END);
    return lines.join("\n");
  }

  if (!valid.length) {
    lines.push(`        raw = self.close.pct_change(20) * 0  # 请选择因子`);
    lines.push(`        return self._post_signal(raw)`);
    lines.push(SIGNAL_END);
    return lines.join("\n");
  }

  if (mode === "product") {
    const p = normalizeSignalPowers(valid, powers);
    const parts = valid.map(
      (method, i) => `(self.rank(self.${method}()) ** ${p[i] ?? 1})`,
    );
    if (parts.length === 1) {
      lines.push(`        raw = ${parts[0]}`);
    } else {
      lines.push(`        raw = (`);
      parts.forEach((part, i) => {
        lines.push(`            ${part}${i < parts.length - 1 ? " *" : ""}`);
      });
      lines.push(`        )`);
    }
  } else {
    const w = normalizeSignalWeights(valid, weights);
    const sum = w.reduce((a, b) => a + b, 0) || 1;
    const parts = valid.map((method, i) => {
      const coef = (w[i] / sum).toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
      return `${coef} * self.rank(self.${method}())`;
    });
    if (parts.length === 1) {
      lines.push(`        raw = ${parts[0]}`);
    } else {
      lines.push(`        raw = (`);
      parts.forEach((part, i) => {
        lines.push(`            ${part}${i < parts.length - 1 ? " +" : ""}`);
      });
      lines.push(`        )`);
    }
  }
  lines.push(`        return self._post_signal(raw)`);
  lines.push(SIGNAL_END);
  return lines.join("\n");
}

function defaultExtraBlock(): string {
  return [
    EXTRA_BEGIN,
    "    def _post_signal(self, raw):",
    '        """信号外逻辑钩子：默认透传。可在此做趋势门控 / 过滤。"""',
    "        return raw",
    EXTRA_END,
  ].join("\n");
}

function extractMarked(code: string, begin: string, end: string): string | null {
  const bi = code.indexOf(begin);
  const ei = code.indexOf(end);
  if (bi < 0 || ei < 0 || ei <= bi) return null;
  return code.slice(bi, ei + end.length);
}

function ensurePostSignal(extra: string): string {
  if (/def\s+_post_signal\s*\(/.test(extra)) return extra;
  return extra.replace(
    EXTRA_END,
    [
      "    def _post_signal(self, raw):",
      '        """信号外逻辑钩子：默认透传。可在此做趋势门控 / 过滤。"""',
      "        return raw",
      EXTRA_END,
    ].join("\n"),
  );
}

export type ApplySignalOpts = {
  mode?: StrategyWeightMode;
  powers?: number[];
  /** custom 模式下改因子时默认不覆盖已手写的 @signal */
  rewriteSignal?: boolean;
};

/**
 * 按所选因子/权重重写 @factor 与 @signal；factorBodies 为 resolveStrategyFactorBodies 的结果。
 */
export function applySignalFactorsToCode(
  code: string,
  factorIds: string[],
  weights: number[],
  factorBodies: string,
  opts?: ApplySignalOpts,
): string {
  if (!usesFactorPortfolioTemplate(code)) return code;
  const mode: StrategyWeightMode = opts?.mode || "sum";
  const ids = factorIds.filter((id) => /^[A-Za-z_]\w*$/.test(id));
  const w = normalizeSignalWeights(ids, weights);
  const powers = normalizeSignalPowers(ids, opts?.powers);
  const factorBlock = buildFactorBlock(factorBodies);
  const rewriteSignal =
    opts?.rewriteSignal !== undefined
      ? opts.rewriteSignal
      : mode !== "custom";
  const signalBlock = buildSignalBlock(ids, w, powers, mode);
  let extra = extractMarked(code, EXTRA_BEGIN, EXTRA_END);
  if (!extra) extra = defaultExtraBlock();
  extra = ensurePostSignal(extra);

  const hasF = code.includes(FACTORS_BEGIN) && code.includes(FACTORS_END);
  const hasS = code.includes(SIGNAL_BEGIN) && code.includes(SIGNAL_END);
  const hasE = code.includes(EXTRA_BEGIN) && code.includes(EXTRA_END);

  if (hasF && hasS) {
    let next = code;
    next = next.replace(
      new RegExp(
        `${escapeRe(FACTORS_BEGIN)}[\\s\\S]*?${escapeRe(FACTORS_END)}`,
      ),
      () => factorBlock,
    );
    if (hasE) {
      next = next.replace(
        new RegExp(`${escapeRe(EXTRA_BEGIN)}[\\s\\S]*?${escapeRe(EXTRA_END)}`),
        () => extra!,
      );
    } else {
      next = next.replace(
        new RegExp(`${escapeRe(FACTORS_END)}`),
        `${FACTORS_END}\n\n${extra}`,
      );
    }
    if (rewriteSignal) {
      next = next.replace(
        new RegExp(`${escapeRe(SIGNAL_BEGIN)}[\\s\\S]*?${escapeRe(SIGNAL_END)}`),
        () => signalBlock,
      );
    }
    return next;
  }

  const classMatch = /class\s+(\w+)\s*\(\s*FactorPortfolioStrategy\s*\)\s*:/.exec(
    code,
  );
  if (!classMatch) return code;

  const assembled = `\n${factorBlock}\n\n${extra}\n\n${signalBlock}\n`;
  const clsStart = classMatch.index!;
  const afterClassHeader = code.indexOf("\n", clsStart) + 1;
  const before = code.slice(0, afterClassHeader);
  const body = code.slice(afterClassHeader);
  const attrEnd = body.search(/\n    @(?:factor|signal)\b/);
  const attrs =
    attrEnd >= 0
      ? body.slice(0, attrEnd).replace(/\s+$/, "")
      : body.replace(/\s+$/, "");
  return `${before}${attrs}\n${assembled}`;
}
