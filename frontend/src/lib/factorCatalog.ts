import { researchFetch as fetch } from "./researchClient";
import { load as yamlLoad } from "js-yaml";
import { authHeaders } from "@/lib/researchClient";

export type FactorMeta = {
  name: string;
  /** 磁盘/源码中的物理方法名；自定义因子为 u{userId}_{name} */
  methodName: string;
  description: string;
  explain: string;
  formula: string;
  params: Record<string, string | number>;
  library: string;
  libraryFile: string;
  libraryLabel: string;
  tags?: string[];
  /** RE 主因子库分类 ID，如 SV01 */
  categoryId?: string;
  /** 中文短名，如「涨跌日频率差」 */
  displayName?: string;
  /** 英文展示名；主因子库列表主标题优先用此字段 */
  nameEn?: string;
  ownerId?: number;
  /** 用户库因子：直接带源码，无需读文件 */
  body?: string;
  /** 用户库：false 表示尚无有效公式（黄色） */
  formulaReady?: boolean;
  userLibraryId?: number;
  userLibraryName?: string;
  /** 用户库因子行 id（删除用） */
  userLibraryFactorId?: number;
};

/** 主因子库 category_id 展示名顺序（与同步侧 CATEGORY_ID_LABELS 一致） */
export const SV_CATEGORY_LABEL_ORDER = [
  "动量因子",
  "技术复合因子",
  // RE 目录实际返回 category_name=反转因子（28 个因子，未落在 CATEGORY_ID_LABELS 里）；
  // 不收进来会掉进下面的「其余按拼音排序」分支，Tab 顺序错乱。
  "反转因子",
  "Beta因子",
  "区间与通道因子",
  "流动性因子",
  "资金流与量能因子",
  "量价关系因子",
  "日内结构因子",
  "波动率因子",
  "估值因子",
  "规模因子",
  "风险分布因子",
  "待复核",
  "标签与不可交易",
] as const;

export const LABELS: Record<string, string> = {
  // 检测选因子 / 面板分类：动量优先，再经典库，再同事新库
  momentum_lib: "动量/趋势",
  value_lib: "价值/估值",
  technical_lib: "技术指标",
  classic_indicators: "经典指标",
  volatility_lib: "波动/风险",
  trading_lib: "量价/成交",
  emotion_indicators: "情绪因子",
  risk_indicators: "风险因子",
  technical_indicators: "技术指标库",
  alpha_features: "Alpha158/360",
  alpha_library: "Alpha库",
  worldquant_alpha101: "WorldQuant/Alpha101",
  gtja_alpha191: "国泰君安Alpha191",
  custom_lib: "自定义",
  主因子库: "主因子库",
};

/** 旧库名仅用于历史帖/缓存展示，不再作为分类 Tab */
export const LEGACY_LABELS: Record<string, string> = {
  jq_compat_emotion: "聚宽情绪",
  jq_compat_risk: "聚宽风险",
  jq_compat_technical: "聚宽技术",
  qlib_alpha: "Qlib特征",
};

/** 与 index.yaml libraries 常见顺序一致；Tab 只展示实际出现的库 */
export const LIBRARY_TAB_ORDER = Object.keys(LABELS);

/** 内置因子库分类键（不含「自定义」） */
export const BUILTIN_LIBRARY_KEYS = LIBRARY_TAB_ORDER.filter(
  (k) => k !== "custom_lib",
);

export function builtinCategoryLabelsFromFactors(factors: FactorMeta[]): string[] {
  const present = new Set(
    factors
      .filter((f) => f.library !== "custom_lib")
      .map((f) => f.libraryLabel)
      .filter(Boolean),
  );
  // 主因子库：按 SV 分类固定顺序
  const svOrdered = SV_CATEGORY_LABEL_ORDER.filter((lab) => present.has(lab));
  if (svOrdered.length > 0) {
    const rest = [...present].filter((lab) => !SV_CATEGORY_LABEL_ORDER.includes(lab as (typeof SV_CATEGORY_LABEL_ORDER)[number]));
    return [...svOrdered, ...rest.sort((a, b) => a.localeCompare(b, "zh"))];
  }
  return filterTabsFromFactors(
    factors.filter((f) => f.library !== "custom_lib"),
  ).slice(1);
}

export function labelForLibrary(key: string, _fallback?: string): string {
  // 分类名必须稳定：勿用 RE 的 description 当 label，否则 Tab 键与 counts 对不上
  return LABELS[key] || LEGACY_LABELS[key] || key;
}

export function libraryKeyFromLabel(label: string): string | undefined {
  const hit = Object.entries(LABELS).find(([, v]) => v === label);
  if (hit) return hit[0];
  const legacy = Object.entries(LEGACY_LABELS).find(([, v]) => v === label);
  return legacy?.[0];
}

/** 按当前目录实际库生成「全部 + 分类」Tab（去掉 index 里没有的） */
export function filterTabsFromLibraries(libraryKeys: Iterable<string>): string[] {
  const present = new Set(libraryKeys);
  const ordered = LIBRARY_TAB_ORDER.filter((k) => present.has(k)).map((k) => LABELS[k]);
  for (const k of present) {
    if (!(k in LABELS)) {
      const lab = labelForLibrary(k);
      if (!ordered.includes(lab)) ordered.push(lab);
    }
  }
  return ["全部", ...ordered];
}

export function filterTabsFromFactors(factors: FactorMeta[]): string[] {
  return filterTabsFromLibraries(factors.map((f) => f.library));
}

/** @deprecated 请用 filterTabsFromFactors；保留避免旧引用炸裂 */
export const FILTER_TABS = ["全部", ...Object.values(LABELS)] as const;

/** 动态注册、无法从 .py 静态抽取方法体的库（检测走 RE library_name） */
export const DYNAMIC_FACTOR_LIBS = new Set(["alpha_features", "qlib_alpha"]);

let cache: FactorMeta[] | null = null;

export type ReCatalogMeta = {
  fetchedAt?: string;
  source?: string;
  factorCount?: number;
};

let reCatalogMeta: ReCatalogMeta | null = null;

export function getReCatalogMeta(): ReCatalogMeta | null {
  return reCatalogMeta;
}

async function loadBuiltinFromResearchEngine(
  opts?: { fresh?: boolean },
): Promise<FactorMeta[]> {
  // 本机 BFF：默认读 PG 全库快照（all=1）；fresh=1 才当场打 RE（慢）
  const q = new URLSearchParams({ all: "1" });
  if (opts?.fresh) q.set("fresh", "1");
  const res = await fetch(`/api/factor/re-catalog?${q}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`读取因子目录失败 HTTP ${res.status}`);
  }
  const data = (await res.json()) as {
    ok?: boolean;
    error?: string;
    fetched_at?: string;
    source?: string;
    factor_count?: number;
    factors?: Array<{
      name: string;
      description?: string;
      library: string;
      library_description?: string | null;
      tags?: string[];
      category_id?: string | null;
      category_label?: string | null;
      category_name?: string | null;
      factor_id?: string | null;
      display_name?: string | null;
      name_en?: string | null;
    }>;
  };
  if (data.ok === false) {
    throw new Error(data.error || "读取 RE 因子目录失败");
  }
  reCatalogMeta = {
    fetchedAt: data.fetched_at,
    source: data.source,
    factorCount: data.factor_count ?? data.factors?.length,
  };
  const out: FactorMeta[] = [];
  for (const f of data.factors || []) {
    const desc = (f.description || f.name || "").trim() || f.name;
    const categoryLabel = (
      f.category_label ||
      f.category_name ||
      ""
    ).trim();
    out.push({
      name: f.name,
      methodName: f.name,
      description: desc,
      explain: desc,
      formula: "",
      params: {},
      library: f.library,
      libraryFile: "",
      // 有 category_label 时按分类展示/筛选；否则回退库名
      libraryLabel: categoryLabel || labelForLibrary(f.library),
      tags: f.tags,
      categoryId: f.category_id || undefined,
      displayName: (f.display_name || "").trim() || undefined,
      nameEn: (f.name_en || "").trim() || undefined,
    });
  }
  return out;
}

/** 列表/芯片主标题：优先英文名，其次中文短名，再回退方法名 */
export function factorTitle(f: Pick<FactorMeta, "name" | "nameEn" | "displayName">): string {
  return (f.nameEn || f.displayName || f.name).trim() || f.name;
}

/** 释义行：description / explain */
export function factorExplainText(
  f: Pick<FactorMeta, "description" | "explain" | "name">,
): string {
  return (f.description || f.explain || f.name).trim() || f.name;
}

/** 仅合并本机 custom_lib（用户自定义）；官方目录已改由 RE 提供 */
async function loadCustomFromLocalIndex(): Promise<FactorMeta[]> {
  const res = await fetch("/api/factor/index", {
    cache: "no-store",
    headers: { ...authHeaders() },
  });
  if (!res.ok) return [];
  const raw = yamlLoad(await res.text()) as {
    libraries?: Record<
      string,
      {
        file?: string;
        description?: string;
        factors?: Array<{
          name: string;
          method_name?: string;
          owner_id?: number;
          description?: string;
          explain?: string;
          formula?: string;
          params?: Record<string, string | number>;
          tags?: string[];
          body?: string;
        }>;
      }
    >;
  };
  const custom = raw.libraries?.custom_lib;
  if (!custom) return [];
  const out: FactorMeta[] = [];
  for (const f of custom.factors || []) {
    const desc = f.description || f.name;
    const params = f.params || {};
    out.push({
      name: f.name,
      methodName: f.method_name || f.name,
      description: desc,
      explain: applyParams(f.explain || desc, params),
      formula: applyParams(f.formula || "", params),
      params,
      library: "custom_lib",
      libraryFile: custom.file || "custom_lib.py",
      libraryLabel: labelForLibrary("custom_lib", custom.description || "自定义"),
      tags: f.tags,
      ownerId: f.owner_id,
      body: f.body,
    });
  }
  return out;
}

export async function loadFactors(
  force = false,
  opts?: { freshCatalog?: boolean },
): Promise<FactorMeta[]> {
  if (cache && !force && !opts?.freshCatalog) return cache;
  const [builtin, custom] = await Promise.all([
    loadBuiltinFromResearchEngine({ fresh: Boolean(opts?.freshCatalog) }),
    loadCustomFromLocalIndex(),
  ]);
  cache = [...builtin, ...custom];
  return cache;
}

export type SyncOfficialCatalogResult = {
  factors: FactorMeta[];
  message: string;
  factorCount: number;
  changed: boolean;
  libraryCounts?: Record<string, number>;
};

/** 管理员：POST 同步 RE 全库 → PG；所有账户读同一内置快照 */
export async function syncOfficialFactorCatalog(): Promise<SyncOfficialCatalogResult> {
  const res = await fetch("/api/factor/re-catalog/sync", {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ all: true }),
  });
  const data = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    error?: string;
    message?: string;
    changed?: boolean;
    factor_count?: number;
    factors?: unknown[];
    library_factor_counts?: Record<string, number>;
  };
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `同步失败 HTTP ${res.status}`);
  }
  clearFactorCache();
  const factors = await loadFactors(true);
  const builtin = factors.filter((f) => f.library !== "custom_lib");
  const factorCount = data.factor_count ?? data.factors?.length ?? builtin.length;
  if (!factorCount) {
    throw new Error("同步结果为空，请检查 ResearchEngine 是否可达");
  }
  // 读回数量若明显偏少，提示不要静默当成功
  if (builtin.length > 0 && builtin.length + 5 < factorCount) {
    throw new Error(
      `同步写库 ${factorCount} 个，但页面读回仅 ${builtin.length} 个，请刷新重试`,
    );
  }
  return {
    factors,
    message: data.message || `已同步 ${factorCount} 个因子`,
    factorCount: builtin.length || factorCount,
    changed: Boolean(data.changed),
    libraryCounts: data.library_factor_counts,
  };
}

export function clearFactorCache() {
  cache = null;
}

export async function loadLibrarySource(file: string): Promise<string> {
  const res = await fetch(`/api/factor/file/${encodeURIComponent(file)}`, {
    cache: "no-store",
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`读取 ${file} 失败`);
  return res.text();
}

/** 把源码中的 def 名改成逻辑名，便于组合里 self.name() */
export function renameMethodDef(methodSource: string, logicalName: string): string {
  return methodSource.replace(/^def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(/m, `def ${logicalName}(`);
}

export function extractMethod(source: string, methodName: string): string {
  const lines = source.split(/\r?\n/);
  const startRe = new RegExp(`^(\\s*)def\\s+${methodName}\\s*\\(`);
  let start = -1;
  let indent = "";
  for (let i = 0; i < lines.length; i++) {
    const m = startRe.exec(lines[i]);
    if (m) {
      start = i;
      indent = m[1];
      break;
    }
  }
  if (start < 0) throw new Error(`未找到方法 ${methodName}`);
  const out = [lines[start]];
  const bodyIndent = indent + "    ";
  for (let i = start + 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) {
      out.push(line);
      continue;
    }
    // 方法体必须比 def 多缩进；同级注释（如「# === 换手率 ===」）或下一个 def 都结束
    if (line.startsWith(bodyIndent)) {
      out.push(line);
      continue;
    }
    break;
  }
  const n = indent.length;
  // 去掉尾部空行
  while (out.length > 1 && !out[out.length - 1].trim()) out.pop();
  return out.map((ln) => (ln.length >= n ? ln.slice(n) : ln)).join("\n").trim();
}

/** 列出源码中类内全部方法名（含私有 _xxx） */
export function listClassMethodNames(source: string): string[] {
  const lines = source.split(/\r?\n/);
  let classIndent = -1;
  const names: string[] = [];
  for (const line of lines) {
    const cm = /^(\s*)class\s+\w+/.exec(line);
    if (cm) {
      classIndent = cm[1].length;
      continue;
    }
    if (classIndent < 0) continue;
    if (line.trim() && !/^\s/.test(line) && !line.startsWith(" ".repeat(classIndent))) {
      // 离开该类（顶格其它内容）
      if (!line.startsWith(" ".repeat(classIndent + 1)) && /^class\s|^\S/.test(line.trim() ? line : "x")) {
        /* keep scanning; multiple classes rare */
      }
    }
    const dm = /^(\s*)def\s+([A-Za-z_]\w*)\s*\(/.exec(line);
    if (!dm) continue;
    if (dm[1].length <= classIndent) continue;
    names.push(dm[2]);
  }
  return names;
}

/**
 * 抽出公开因子 + 同类全部私有辅助（策略克隆用；策略 API 不支持 library_name）。
 */
export function extractFactorWithHelpers(source: string, methodName: string): string {
  const names = listClassMethodNames(source);
  if (!names.includes(methodName)) {
    // 退回单方法（文件可能无 class 包裹）
    return extractMethod(source, methodName);
  }
  const helpers = names.filter((n) => n.startsWith("_"));
  const parts: string[] = [];
  for (const h of helpers) {
    try {
      parts.push(extractMethod(source, h));
    } catch {
      /* skip */
    }
  }
  parts.push(extractMethod(source, methodName));
  return parts.filter(Boolean).join("\n\n");
}

/** 把 params / 签名默认值填进公式，避免 window 等占位符导致多条一模一样 */
export function applyParams(text: string, params: Record<string, string | number>): string {
  if (!text) return text;
  let out = text;
  for (const [k, v] of Object.entries(params)) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(k)) continue;
    out = out.replace(new RegExp(`\\b${k}\\b`, "g"), String(v));
  }
  return out;
}

function parseSignatureDefaults(methodSource: string): Record<string, string | number> {
  const defLine = methodSource.split(/\r?\n/)[0] || "";
  const params: Record<string, string | number> = {};
  const re = /(\w+)\s*(?::\s*[^=,)]+)?\s*=\s*([^,)]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(defLine))) {
    if (m[1] === "self") continue;
    const raw = m[2].trim();
    const num = Number(raw);
    params[m[1]] = Number.isFinite(num) && raw !== "" ? num : raw.replace(/^['"]|['"]$/g, "");
  }
  return params;
}

/** 从方法体抽出 return 表达式，供彩色公式预览 */
export function extractReturnExpr(methodSource: string): string {
  const lines = methodSource.split(/\r?\n/);
  for (let i = lines.length - 1; i >= 0; i--) {
    const m = lines[i].match(/^\s*return\s+(.+?)\s*$/);
    if (m) return m[1].replace(/\s+#.*$/, "").trim();
  }
  return "";
}

/** 从完整方法源码解析 def 函数名 */
export function extractDefName(source: string): string | null {
  const m = source.match(/^\s*def\s+([A-Za-z_]\w*)\s*\(/m);
  return m ? m[1] : null;
}

/**
 * 编辑页展示：把物理方法名 u{id}_{logical} 改写成逻辑名，
 * 用户只写/看逻辑名；入库时后端再换成物理名。
 */
export function toLogicalMethodBody(methodSource: string, logicalName: string): string {
  const logical = (logicalName || "").trim();
  if (!logical || !methodSource.trim()) return methodSource;
  let out = methodSource.replace(
    new RegExp(`^(\\s*def\\s+)u\\d+_${logical.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s*\\()`, "m"),
    `$1${logical}$2`,
  );
  // 若已是逻辑名则不变；若 def 名恰好等于 logical 也保持
  const def = extractDefName(out);
  if (def && def !== logical && def.endsWith(`_${logical}`)) {
    out = out.replace(
      new RegExp(`^(\\s*def\\s+)${def.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s*\\()`, "m"),
      `$1${logical}$2`,
    );
  }
  return out;
}

/** 展开公式：优先多行有效语句；并把签名默认参数代入 */
export function formatFactorFormula(methodSource: string, extraParams?: Record<string, string | number>): string {
  const defaults = { ...parseSignatureDefaults(methodSource), ...(extraParams || {}) };
  // 完整 def 方法：保留函数头，只做参数替换
  if (/^\s*def\s+/m.test(methodSource)) {
    return applyParams(methodSource.trim(), defaults);
  }
  const lines = methodSource.split(/\r?\n/).slice(1);
  const stmts: string[] = [];
  let inDoc = false;
  for (const line of lines) {
    const t = line.trim();
    if (!t) continue;
    if (!inDoc && (t.startsWith('"""') || t.startsWith("'''"))) {
      if ((t.match(/"""/g) || []).length >= 2 || (t.match(/'''/g) || []).length >= 2) continue;
      inDoc = true;
      continue;
    }
    if (inDoc) {
      if (t.endsWith('"""') || t.endsWith("'''")) inDoc = false;
      continue;
    }
    if (t.startsWith("#")) continue;
    stmts.push(t);
  }
  if (stmts.length > 1) return applyParams(stmts.join("\n"), defaults);
  const expr = extractReturnExpr(methodSource);
  if (expr) return applyParams(expr, defaults);
  return applyParams(stmts[0] || "", defaults);
}

/** 编辑页：从方法源码抽出可编辑表达式（去掉 def / docstring） */
export function extractEditableBody(methodSource: string): string {
  const lines = methodSource.split(/\r?\n/).slice(1);
  const out: string[] = [];
  let inDoc = false;
  for (const line of lines) {
    const t = line.trim();
    if (!t && !out.length) continue;
    if (!inDoc && (t.startsWith('"""') || t.startsWith("'''"))) {
      if ((t.match(/"""/g) || []).length >= 2 || (t.match(/'''/g) || []).length >= 2) continue;
      inDoc = true;
      continue;
    }
    if (inDoc) {
      if (t.endsWith('"""') || t.endsWith("'''")) inDoc = false;
      continue;
    }
    out.push(line.replace(/^\s{4}/, ""));
  }
  while (out.length && !out[0].trim()) out.shift();
  while (out.length && !out[out.length - 1].trim()) out.pop();
  return out.join("\n").trim();
}

export const UNIVERSES = [
  { value: "CSI300", label: "沪深300" },
  { value: "CSI500", label: "中证500" },
  { value: "CSI800", label: "中证800" },
  { value: "CSI1000", label: "中证1000" },
  { value: "SSE50", label: "上证50" },
] as const;

export const PERIODS = [
  { value: "3m", label: "近3月" },
  { value: "1y", label: "近1年" },
  { value: "3y", label: "近3年" },
  { value: "10y", label: "近10年" },
  { value: "all", label: "全部" },
] as const;
