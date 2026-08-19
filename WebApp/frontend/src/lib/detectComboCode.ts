import type { WeightMode } from "./detectStore";
import type { FactorMeta } from "./factorCatalog";

/**
 * 本机/用户库（须传 factor_code）。
 * 其余凡带 library 名的一律当 ResearchEngine 官方库走 library_name，
 * 避免再漏 gtja / wq / emotion 等白名单。
 */
export function isLocalFactorLib(library: string | undefined | null): boolean {
  if (!library) return true;
  if (library === "custom_lib" || library === "draft_lib") return true;
  if (library.startsWith("user_lib_")) return true;
  return false;
}

/** ResearchEngine 已登记的 library_name 库（非本机自定义）。 */
export function isReBuiltinLib(library: string | undefined | null): boolean {
  return Boolean(library) && !isLocalFactorLib(library);
}

/** @deprecated 保留导出，避免旧引用炸裂；请用 isReBuiltinLib */
export const RE_BUILTIN_LIBS = new Set<string>([
  "emotion_indicators",
  "risk_indicators",
  "technical_indicators",
  "classic_indicators",
  "alpha_features",
  "momentum_lib",
  "value_lib",
  "technical_lib",
  "volatility_lib",
  "trading_lib",
  "alpha_library",
  "gtja_alpha191",
  "worldquant_alpha101",
  "qlib_alpha",
  "jq_compat_technical",
  "jq_compat_risk",
  "jq_compat_emotion",
]);

/** @deprecated 五库已并入 RE；保留空集避免旧引用炸裂 */
export const PLATFORM_LOCAL_LIBS = new Set<string>();

/** 同名因子多库时优先官方 RE 库（如 wvad 同时在 classic / emotion） */
export function resolveFactorMeta(
  factors: FactorMeta[],
  name: string,
): FactorMeta | undefined {
  const hits = factors.filter((f) => f.name === name);
  if (!hits.length) return undefined;
  const re = hits.find((f) => isReBuiltinLib(f.library));
  return re || hits[0];
}

/** 平台托管因子（RE 内置）——检测页/因子库不展示完整实现 */
export function isPlatformFactorLib(library: string | undefined | null): boolean {
  return isReBuiltinLib(library);
}

/** 检测页展示用存根（提交仍用真实 methodBodies / library_name） */
export function buildPlatformFactorStub(meta: {
  name: string;
  description?: string;
  library: string;
  formula?: string;
  explain?: string;
}): string {
  const title = (meta.description || meta.name).trim();
  return [
    `# ${title}`,
    `# 库 ${meta.library} · 因子 ${meta.name}`,
    `# 源码由 ResearchEngine 托管，本站不展示公式`,
    `# 提交：library_name=${meta.library} + factor_name=${meta.name}`,
  ].join("\n");
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
    if (codes.length === 1) {
      return `def ${entry}(self):\n    """${title}"""\n    return self.${codes[0]}()`;
    }
    if (codes.length > 1) {
      const expr = codes.map((c) => `self.${c}()`).join(" + ");
      return `def ${entry}(self):\n    """${title} · 自定义组合"""\n    return ${expr}`;
    }
    return `def ${entry}(self):\n    """${title}"""\n    # 先在左侧添加因子，再写合成表达式，例如 return self.momentum_5d()\n    return self.close.pct_change(5)`;
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

/** 从单方法体取最后一个 return 表达式；多语句则返回 null */
function lastReturnExpr(methodSrc: string): string | null {
  const lines = methodSrc.replace(/\r\n/g, "\n").split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const m = /^\s*return\s+(.+?)\s*$/.exec(lines[i]);
    if (m) return m[1].replace(/\s+#.*$/, "").trim();
  }
  return null;
}

function methodDefName(methodSrc: string): string | null {
  const m = /^\s*def\s+([A-Za-z_]\w*)\s*\(/.exec(methodSrc);
  return m?.[1] ?? null;
}

/**
 * RE 文档要求自定义 factor_code「只传单个函数」。
 * 有 library_name 时，把本地简单因子的 return 内联进 combo，避免多 def。
 */
export function inlineLocalMethodsIntoCombo(
  comboFn: string,
  localBodies: string[],
): string {
  let combo = comboFn.trim();
  if (!combo || !localBodies.length) return combo;

  for (const body of localBodies) {
    const name = methodDefName(body);
    const expr = lastReturnExpr(body);
    if (!name || !expr) continue;
    // 仅当方法体除 docstring/注释外基本是单 return 时内联
    const stripped = body
      .replace(/^\s*def\s+\w+\s*\([^)]*\)\s*:\s*/m, "")
      .replace(/"""[\s\S]*?"""/g, "")
      .replace(/'''[\s\S]*?'''/g, "")
      .replace(/^\s*#.*$/gm, "")
      .trim();
    if (!/^return\s+/.test(stripped) || stripped.includes("\n")) continue;
    const re = new RegExp(
      `self\\.${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\(\\s*\\)`,
      "g",
    );
    combo = combo.replace(re, `(${expr})`);
  }
  return combo;
}

/**
 * 组装发给 RE 的因子字段。
 * - RE 内置库走 library_name（完整库含私有辅助）
 * - 本地 / 自定义仍抽码进 factor_code
 * - 本地 + library_name：尽量内联成单函数（对齐 RE「只传一个函数」）
 * - preferredLibraries：检测配置里落库的 name→library，优先于 catalog 解析（避免竞态/同名）
 */
export function buildYgFactorRequestParts(opts: {
  factors: FactorMeta[];
  factorCodes: string[];
  methodBodies: string[];
  comboFn: string;
  entryName: string;
  /** 选因子时持久化的库名；内置因子必须有 */
  preferredLibraries?: Record<string, string>;
}): YgFactorRequestParts {
  const pref = opts.preferredLibraries || {};

  const metas: FactorMeta[] = opts.factorCodes.map((c) => {
    const fromCatalog = resolveFactorMeta(opts.factors, c);
    const lib = (pref[c] || fromCatalog?.library || "").trim();
    if (fromCatalog) {
      return lib && lib !== fromCatalog.library
        ? { ...fromCatalog, library: lib }
        : fromCatalog;
    }
    // catalog 未就绪时，仍用持久化 library 拼出最小 meta，避免空 UserFactorLibrary
    if (lib) {
      return {
        name: c,
        methodName: c,
        description: c,
        explain: c,
        formula: "",
        params: {},
        library: lib,
        libraryFile: "",
        libraryLabel: lib,
      } as FactorMeta;
    }
    return undefined;
  }).filter((m): m is FactorMeta => Boolean(m));

  const builtinLibs = [
    ...new Set(metas.filter((m) => isReBuiltinLib(m.library)).map((m) => m.library)),
  ];
  const localMetas = metas.filter((m) => !isReBuiltinLib(m.library));
  const needsLocalCode = localMetas.length > 0;
  const customOnly =
    opts.factorCodes.length === 0 && Boolean(opts.comboFn.trim());

  // 纯单因子 + RE 内置 + passthrough → 只传 library_name（切勿带 factor_code，
  // 否则 RE 装进空 UserFactorLibrary，self.xxx() 必炸）
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

  // 目录里暂时找不到 meta，但 combo 是 return self.{code}() 且 code 像官方名：
  // 仍尝试用 catalog / 持久化库补 library_name
  if (
    metas.length === 0 &&
    opts.factorCodes.length === 1 &&
    isPassthroughCombo(opts.comboFn, opts.factorCodes[0])
  ) {
    const code = opts.factorCodes[0];
    const hit = resolveFactorMeta(opts.factors, code);
    const lib = pref[code] || hit?.library;
    if (lib && isReBuiltinLib(lib)) {
      return {
        library_name: lib,
        factor_name: hit?.name || code,
      };
    }
  }

  const localBodies = opts.methodBodies
    .map((m) => m.trim())
    // 展示/RE 存根（以 # 开头、无 def）不得当 factor_code
    .filter((m) => m && /^\s*def\s+\w+/.test(m));

  // 单本地/自定义因子 + 直通组合 → 只传该因子函数本身（入口名=因子名）
  if (
    metas.length === 1 &&
    needsLocalCode &&
    builtinLibs.length === 0 &&
    localBodies.length === 1 &&
    isPassthroughCombo(opts.comboFn, metas[0].name)
  ) {
    return {
      factor_name: metas[0].name,
      factor_code: localBodies[0],
    };
  }

  let factorCode: string | undefined;
  if (needsLocalCode && builtinLibs.length > 0) {
    // 混合：优先单函数内联
    const inlined = inlineLocalMethodsIntoCombo(opts.comboFn, localBodies);
    const stillCallsLocal = localMetas.some((m) =>
      new RegExp(`self\\.${m.name}\\s*\\(`).test(inlined),
    );
    factorCode = stillCallsLocal
      ? buildDetectFactorCode(localBodies, opts.comboFn)
      : inlined.trim();
  } else if (needsLocalCode || customOnly) {
    factorCode = buildDetectFactorCode(localBodies, opts.comboFn);
  } else if (
    // 单 RE 因子：始终只带 library_name + factor_name（含非严格 passthrough）
    metas.length === 1 &&
    builtinLibs.length === 1 &&
    !needsLocalCode
  ) {
    return {
      library_name: builtinLibs[0],
      factor_name: metas[0].name,
    };
  } else if (
    // 多 RE 内置：combo + library_name（数组），禁止无 library 的空壳 factor_code
    metas.length > 1 &&
    builtinLibs.length >= 1 &&
    !needsLocalCode
  ) {
    factorCode = opts.comboFn.trim();
  } else {
    factorCode = opts.comboFn.trim();
  }

  const parts: YgFactorRequestParts = {
    factor_name: opts.entryName,
  };
  if (factorCode) parts.factor_code = factorCode;
  if (builtinLibs.length === 1) parts.library_name = builtinLibs[0];
  else if (builtinLibs.length > 1) parts.library_name = builtinLibs;

  return parts;
}

/**
 * 审计：每个 RE 内置因子单独直通提交时，必须只有 library_name + factor_name。
 * 返回不合格项（空数组 = 全过）。
 */
export function auditBuiltinPassthroughParts(
  factors: FactorMeta[],
): Array<{ name: string; library: string; reason: string; parts: YgFactorRequestParts }> {
  const bad: Array<{
    name: string;
    library: string;
    reason: string;
    parts: YgFactorRequestParts;
  }> = [];
  const builtins = factors.filter((f) => isReBuiltinLib(f.library));
  for (const f of builtins) {
    const combo = `def combo_factor(self):\n    return self.${f.name}()`;
    const parts = buildYgFactorRequestParts({
      factors,
      factorCodes: [f.name],
      methodBodies: [buildPlatformFactorStub(f)],
      comboFn: combo,
      entryName: "combo_factor",
      preferredLibraries: { [f.name]: f.library },
    });
    if (!parts.library_name) {
      bad.push({ name: f.name, library: f.library, reason: "缺少 library_name", parts });
      continue;
    }
    const libOk = Array.isArray(parts.library_name)
      ? parts.library_name.includes(f.library)
      : parts.library_name === f.library;
    if (!libOk) {
      bad.push({
        name: f.name,
        library: f.library,
        reason: `library_name 不匹配: ${JSON.stringify(parts.library_name)}`,
        parts,
      });
      continue;
    }
    if (parts.factor_code) {
      bad.push({
        name: f.name,
        library: f.library,
        reason: "单因子直通仍带了 factor_code",
        parts,
      });
      continue;
    }
    if (parts.factor_name !== f.name) {
      bad.push({
        name: f.name,
        library: f.library,
        reason: `factor_name=${parts.factor_name} 应为 ${f.name}`,
        parts,
      });
    }
  }
  return bad;
}
