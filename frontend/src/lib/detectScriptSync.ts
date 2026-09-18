/**
 * 检测页右侧脚本：注释（内置/自定义）+ 自定义函数体 + 组合入口。
 * 组合入口名用主因子名或 factor，不再使用 combo_factor。
 */
import type { DetectProjectConfig } from "./detectStore";
import { buildComboFunction, isPlatformFactorLib } from "./detectComboCode";
import type { FactorMeta } from "./factorCatalog";

export type DetectScriptBodies = Record<string, string>;

/** 平台官方库 / RE 内置 → 内置；用户库、草稿、custom_lib → 自定义 */
export function isCustomFactorMeta(meta?: FactorMeta | null): boolean {
  if (!meta) return true;
  if (meta.userLibraryId != null || meta.ownerId != null) return true;
  if (meta.library === "custom_lib" || meta.library === "draft_lib") return true;
  if (isPlatformFactorLib(meta.library)) return false;
  return true;
}

export function factorCommentLine(meta: FactorMeta | undefined, code: string): string {
  const kind = isCustomFactorMeta(meta) ? "自定义" : "内置";
  const title = (
    meta?.displayName ||
    meta?.nameEn ||
    meta?.description ||
    meta?.explain ||
    ""
  ).trim();
  if (title && title !== code) return `# [${kind}] ${code} — ${title}`;
  return `# [${kind}] ${code}`;
}

/** 按顶层 def 切分方法体 */
export function splitTopLevelDefs(src: string): Record<string, string> {
  const text = (src || "").replace(/\r\n/g, "\n");
  const re = /^def\s+([A-Za-z_]\w*)\s*\(/gm;
  const hits: { name: string; index: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    hits.push({ name: m[1], index: m.index });
  }
  const out: Record<string, string> = {};
  for (let i = 0; i < hits.length; i++) {
    const start = hits[i].index;
    const end = i + 1 < hits.length ? hits[i + 1].index : text.length;
    out[hits[i].name] = text.slice(start, end).trim();
  }
  return out;
}

/** 多因子组合入口名：主自定义因子名，否则 factor（兼容旧 combo_factor） */
export function resolveDetectEntryName(
  preferred?: string | null,
  fallback = "factor",
): string {
  const name = (preferred || "").trim();
  if (
    name &&
    name !== "combo_factor" &&
    name !== "custom_combo" &&
    /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)
  ) {
    return name;
  }
  return fallback;
}

export function buildDetectScript(opts: {
  config: DetectProjectConfig;
  projectName?: string;
  catalogByName: Map<string, FactorMeta>;
  /** 需要展示的函数体（自定义/用户库）；平台因子不要传入 */
  factorBodies?: DetectScriptBodies;
  draftMode?: boolean;
  draftBody?: string;
  /** 不生成组合入口（内置只读、单因子手写等） */
  omitCombo?: boolean;
  /** 只输出注释行（内置因子） */
  commentsOnly?: boolean;
  /** 组合入口函数名 */
  entryName?: string;
  /** 参与赋权的因子（默认全部 factorCodes） */
  ingredientCodes?: string[];
}): string {
  const cfg = opts.config;
  if (opts.draftMode) {
    return (
      (opts.draftBody || "").trim() ||
      `def factor(self):\n    return self.close.pct_change(5)\n`
    );
  }

  const codes = cfg.factorCodes || [];
  const lines: string[] = [];

  if (!codes.length) {
    lines.push("# 在左侧添加因子后，此处会生成对应注释");
  } else {
    for (const code of codes) {
      lines.push(factorCommentLine(opts.catalogByName.get(code), code));
    }
  }

  if (opts.commentsOnly) {
    return lines.join("\n").replace(/\n{3,}/g, "\n\n") + "\n";
  }

  const entry = resolveDetectEntryName(opts.entryName);
  const ingredients =
    opts.ingredientCodes && opts.ingredientCodes.length
      ? opts.ingredientCodes
      : codes.filter((c) => c !== entry);

  const bodies = opts.factorBodies || {};
  const bodyBlocks: string[] = [];
  for (const code of codes) {
    // 入口函数由下面组合生成，避免与手写 body 重复
    if (code === entry && !opts.omitCombo && ingredients.length > 0) continue;
    const b = (bodies[code] || "").trim();
    if (b) bodyBlocks.push(b);
  }

  let combo = "";
  if (!opts.omitCombo && ingredients.length > 0) {
    const weightIdx = ingredients.map((c) => codes.indexOf(c));
    const weights = weightIdx.map((i) =>
      i >= 0 ? Number(cfg.weights[i] ?? 0) : 0,
    );
    const powers = weightIdx.map((i) =>
      i >= 0 ? Number(cfg.powers[i] ?? 1) : 1,
    );
    // 权重只对应 ingredients 时，若与 codes 等长则直接用 cfg
    const useCfgWeights =
      ingredients.length === codes.length &&
      ingredients.every((c, i) => c === codes[i]);
    combo = buildComboFunction({
      mode: cfg.weightMode,
      factorCodes: ingredients,
      weights: useCfgWeights ? cfg.weights : equalizeWeights(weights, ingredients.length),
      powers: useCfgWeights ? cfg.powers : powers,
      customCombine: renameComboDef(cfg.customCombine, entry),
      entryName: entry,
      title: opts.projectName || "组合因子",
    }).trim();
  }

  if (bodyBlocks.length || combo) {
    lines.push("");
  }
  if (bodyBlocks.length) {
    lines.push(...bodyBlocks);
    if (combo) lines.push("");
  }
  if (combo) {
    lines.push(combo);
  }

  return lines.join("\n").replace(/\n{3,}/g, "\n\n") + "\n";
}

function equalizeWeights(ws: number[], n: number): number[] {
  if (n <= 0) return [];
  const sum = ws.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
  if (sum > 0) return ws.map((w) => Number(w) || 0);
  const each = Math.round((100 / n) * 10000) / 10000;
  return Array.from({ length: n }, () => each);
}

/** 把旧 combo_factor / 其它入口 def 名改成目标入口名 */
export function renameComboDef(src: string, entryName: string): string {
  const text = (src || "").trim();
  if (!text) return text;
  return text.replace(
    /^def\s+(?:combo_factor|custom_combo|factor)\s*\(/m,
    `def ${entryName}(`,
  );
}

export type ParsedDetectScript = {
  /** 从脚本抽出的因子函数体（不含组合入口） */
  factorBodies: DetectScriptBodies;
  comboFn: string | null;
};

const ENTRY_NAMES = new Set(["combo_factor", "custom_combo", "factor"]);

/** 只解析函数体；注释与参数不同步回左侧 */
export function parseDetectScript(
  src: string,
  entryName?: string | null,
): ParsedDetectScript | null {
  const text = (src || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return null;

  const entry = resolveDetectEntryName(entryName);
  const defs = splitTopLevelDefs(text);
  const factorBodies: DetectScriptBodies = {};
  let comboFn: string | null = null;
  for (const [name, body] of Object.entries(defs)) {
    if (name === entry || ENTRY_NAMES.has(name)) {
      comboFn = body;
      continue;
    }
    factorBodies[name] = body;
  }
  return { factorBodies, comboFn };
}

/** 决定哪些因子要在脚本里展示函数体 */
export function bodiesForScriptDisplay(opts: {
  factorCodes: string[];
  catalogByName: Map<string, FactorMeta>;
  methodBodies: string[];
  overrides?: DetectScriptBodies;
}): DetectScriptBodies {
  const out: DetectScriptBodies = {};
  opts.factorCodes.forEach((code, i) => {
    const meta = opts.catalogByName.get(code);
    if (meta && isPlatformFactorLib(meta.library)) return;
    const ov = opts.overrides?.[code]?.trim();
    if (ov) {
      out[code] = ov;
      return;
    }
    const body = opts.methodBodies[i]?.trim();
    if (body && /^\s*def\s+/.test(body)) out[code] = body;
  });
  return out;
}
