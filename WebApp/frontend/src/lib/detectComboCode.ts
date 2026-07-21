import type { WeightMode } from "./detectStore";

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
