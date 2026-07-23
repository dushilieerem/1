import type { WeightMode } from "./detectStore";
import type { FactorMeta } from "./factorCatalog";

/** ResearchEngine 支持 library_name 加载的完整内置库（含私有 _xxx） */
export const RE_BUILTIN_LIBS = new Set([
  "alpha_library",
  "qlib_alpha",
  "jq_compat_technical",
  "jq_compat_risk",
  "jq_compat_emotion",
]);

export function isReBuiltinLib(library: string | undefined | null): boolean {
  return Boolean(library && RE_BUILTIN_LIBS.has(library));
}

/** 根据赋权模式生成组合入口函数 */
export function buildComboFunction(opts: {
  mode: WeightMode;
  factorCodes: string[];
  weights: number[];
  powers: number[];
  customCombine: string;
  entryName?: string;
  title?: string;
}): string {
  const entry = opts.entryName || "combo_factor";
  const title = opts.title || "组合因子";
  const codes = opts.factorCodes;

  if (opts.mode === "custom") {
    const custom = (opts.customCombine || "").trim();
    if (custom) return custom;
    return `def ${entry}(self):\n    """${title}"""\n    return self.close.pct_change(5)`;
  }

  if (codes.length === 0) {
    return `def ${entry}(self):\n    """${title}"""\n    return self.close.pct_change(5)`;
  }

  if (codes.length === 1) {
    return `def ${entry}(self):\n    """${title}"""\n    return self.${codes[0]}()`;
  }

  if (opts.mode === "product") {
    const parts = codes.map((c, i) => `(self.${c}() ** ${Number(opts.powers[i] ?? 1)})`);
    return `def ${entry}(self):\n    """${title} · 赋幂相乘"""\n    return ${parts.join(" * ")}`;
  }

  // sum
  const parts = codes.map((c, i) => {
    const w = (Number(opts.weights[i] ?? 0) / 100).toFixed(4);
    return `${w} * self.${c}()`;
  });
  return `def ${entry}(self):\n    """${title} · 赋权相加"""\n    return ${parts.join(" + ")}`;
}

/** 拼成发给 RE 的完整 factor_code */
export function buildDetectFactorCode(methodBodies: string[], comboFn: string): string {
  const methods = methodBodies.map((m) => m.trim()).filter(Boolean);
  const combo = comboFn.trim();
  return [...methods, combo].filter(Boolean).join("\n\n");
}

/** 从组合函数里取入口名 */
export function extractEntryName(comboFn: string, fallback = "combo_factor"): string {
  const m = comboFn.match(/^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/m);
  return m?.[1] || fallback;
}

/** 判断 combo 是否等价于「直接 return self.{name}()」 */
export function isPassthroughCombo(comboFn: string, factorName: string): boolean {
  const cleaned = comboFn
    .replace(/^\s*def\s+\w+\s*\([^)]*\)\s*:\s*/m, "")
    .replace(/"""[\s\S]*?"""/g, "")
    .replace(/'''[\s\S]*?'''/g, "")
    .replace(/^\s*#.*$/gm, "")
    .trim();
  const re = new RegExp(
    `^return\\s+self\\.${factorName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\(\\s*\\)\\s*$`,
  );
  return re.test(cleaned);
}

export type YgFactorRequestParts = {
  factor_code?: string;
  library_name?: string | string[];
  factor_name: string;
};

/**
 * 组装发给 RE 的因子字段。
 * - RE 内置库走 library_name（完整库含私有辅助）
 * - 本地 / 自定义仍抽码进 factor_code
 */
export function buildYgFactorRequestParts(opts: {
  factors: FactorMeta[];
  factorCodes: string[];
  methodBodies: string[];
  comboFn: string;
  entryName: string;
}): YgFactorRequestParts {
  const byName = new Map(opts.factors.map((f) => [f.name, f]));
  const metas = opts.factorCodes
    .map((c) => byName.get(c))
    .filter((m): m is FactorMeta => Boolean(m));

  const builtinLibs = [
    ...new Set(metas.filter((m) => isReBuiltinLib(m.library)).map((m) => m.library)),
  ];
  const localMetas = metas.filter((m) => !isReBuiltinLib(m.library));
  const needsLocalCode = localMetas.length > 0;
  const customOnly =
    opts.factorCodes.length === 0 && Boolean(opts.comboFn.trim());

  // 纯单因子 + RE 内置 + passthrough → 不传 factor_code
  if (
    metas.length === 1 &&
    builtinLibs.length === 1 &&
    !needsLocalCode &&
    isPassthroughCombo(opts.comboFn, metas[0].name)
  ) {
    return {
      library_name: builtinLibs[0],
      factor_name: metas[0].name,
    };
  }

  const localBodies = opts.methodBodies
    .map((m) => m.trim())
    .filter((m) => m && !m.startsWith("# RE库"));
  const factorCode = needsLocalCode || customOnly
    ? buildDetectFactorCode(localBodies, opts.comboFn)
    : opts.comboFn.trim();

  const parts: YgFactorRequestParts = {
    factor_name: opts.entryName,
  };
  if (factorCode) parts.factor_code = factorCode;
  if (builtinLibs.length === 1) parts.library_name = builtinLibs[0];
  else if (builtinLibs.length > 1) parts.library_name = builtinLibs;

  return parts;
}
