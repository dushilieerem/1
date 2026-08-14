/**
 * 检测页右侧脚本：每选一个因子加一行注释（内置/自定义），
 * 下方可写自定义函数体与 combo_factor。参数只在左侧改，右侧不展示。
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
  const title = (meta?.description || meta?.explain || "").trim();
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

export function buildDetectScript(opts: {
  config: DetectProjectConfig;
  projectName?: string;
  catalogByName: Map<string, FactorMeta>;
  /** 需要展示的函数体（自定义/用户库）；平台因子不要传入 */
  factorBodies?: DetectScriptBodies;
  draftMode?: boolean;
  draftBody?: string;
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

  const bodies = opts.factorBodies || {};
  const bodyBlocks: string[] = [];
  for (const code of codes) {
    const b = (bodies[code] || "").trim();
    if (b) bodyBlocks.push(b);
  }

  const combo = buildComboFunction({
    mode: cfg.weightMode,
    factorCodes: codes,
    weights: cfg.weights,
    powers: cfg.powers,
    customCombine: cfg.customCombine,
    entryName: "combo_factor",
    title: opts.projectName || "组合因子",
  }).trim();

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

export type ParsedDetectScript = {
  /** 从脚本抽出的因子函数体（不含 combo_factor） */
  factorBodies: DetectScriptBodies;
  comboFn: string | null;
};

/** 只解析函数体；注释与参数不同步回左侧 */
export function parseDetectScript(src: string): ParsedDetectScript | null {
  const text = (src || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return null;

  const defs = splitTopLevelDefs(text);
  const factorBodies: DetectScriptBodies = {};
  let comboFn: string | null = null;
  for (const [name, body] of Object.entries(defs)) {
    if (name === "combo_factor") {
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
