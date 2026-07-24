import { load as yamlLoad } from "js-yaml";
import { authHeaders } from "@/lib/auth";

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
  ownerId?: number;
};

export const LABELS: Record<string, string> = {
  custom_lib: "自定义",
  momentum_lib: "动量/趋势",
  value_lib: "价值/估值",
  technical_lib: "技术指标",
  volatility_lib: "波动/风险",
  trading_lib: "量价/成交",
  jq_compat_emotion: "聚宽情绪",
  jq_compat_risk: "聚宽风险",
  jq_compat_technical: "聚宽技术",
  qlib_alpha: "Qlib特征",
};

export const FILTER_TABS = ["全部", ...Object.values(LABELS)] as const;

/** 动态注册、无法从 .py 静态抽取方法体的库（检测走 RE library_name） */
export const DYNAMIC_FACTOR_LIBS = new Set(["qlib_alpha"]);

let cache: FactorMeta[] | null = null;

export async function loadFactors(force = false): Promise<FactorMeta[]> {
  if (cache && !force) return cache;
  const res = await fetch("/api/factor/index", {
    cache: "no-store",
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`读取索引失败 HTTP ${res.status}`);
  const raw = yamlLoad(await res.text()) as {
    libraries?: Record<
      string,
      {
        file: string;
        description?: string;
        factors?: Array<{
          name: string;
          method_name?: string;
          owner_id?: number;
          description?: string;
          explain?: string;
          formula?: string;
          source_name?: string;
          params?: Record<string, string | number>;
          tags?: string[];
        }>;
      }
    >;
  };
  const out: FactorMeta[] = [];
  for (const [key, lib] of Object.entries(raw.libraries || {})) {
    for (const f of lib.factors || []) {
      const desc = f.description || f.source_name || f.name;
      const params = f.params || {};
      const explainRaw = f.explain || desc;
      out.push({
        name: f.name,
        methodName: f.method_name || f.name,
        description: desc,
        explain: applyParams(explainRaw, params),
        formula: applyParams(f.formula || "", params),
        params,
        library: key,
        libraryFile: lib.file,
        libraryLabel: LABELS[key] || lib.description || key,
        tags: f.tags,
        ownerId: f.owner_id,
      });
    }
  }
  cache = out;
  return out;
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
