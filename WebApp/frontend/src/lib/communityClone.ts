import {
  DYNAMIC_FACTOR_LIBS,
  extractDefName,
  extractFactorWithHelpers,
  loadFactors,
  loadLibrarySource,
  type FactorMeta,
} from "@/lib/factorCatalog";
import {
  expandQlibAlphaFactorSource,
  isQlibAlphaFactorName,
} from "@/lib/qlibFactorExpand";
import { isPlatformFactorLib } from "@/lib/detectComboCode";
import type { DraftDetectFactor, WeightMode } from "@/lib/detectStore";
import { listAllUserLibraryFactors } from "@/lib/userFactorLibraries";

/** 公用库因子（非 custom_lib）；按逻辑名或物理方法名匹配 */
export function findPublicLibraryFactor(
  factors: FactorMeta[],
  defName: string | null,
): FactorMeta | null {
  if (!defName) return null;
  return (
    factors.find(
      (f) =>
        f.library !== "custom_lib" &&
        (f.name === defName || f.methodName === defName),
    ) || null
  );
}

/** 当前用户自定义库中已有的同名因子 */
export function findOwnedCustomFactor(
  factors: FactorMeta[],
  defName: string | null,
): FactorMeta | null {
  if (!defName) return null;
  return (
    factors.find(
      (f) =>
        f.library === "custom_lib" &&
        (f.name === defName ||
          f.methodName === defName ||
          (f.methodName || "").endsWith(`_${defName}`)),
    ) || null
  );
}

/** 组合入口名：分享时保留源码（不含内置实现） */
export function isComboEntryName(name: string): boolean {
  return name === "combo_factor" || name === "custom_combo";
}

/** 平台内置 / 本机官方库 / 动态库：社区不得贴出函数体 */
export function shouldHideFactorSource(meta: FactorMeta | null | undefined): boolean {
  if (!meta) return false;
  return (
    isPlatformFactorLib(meta.library) || DYNAMIC_FACTOR_LIBS.has(meta.library)
  );
}

export type TopLevelDefBlock = {
  name: string;
  block: string;
  /** 块在全文中的起始行（0-based） */
  startLine: number;
};

/** 拆顶格 def 块（因子分享片段） */
export function splitTopLevelDefBlocks(code: string): TopLevelDefBlock[] {
  const lines = (code || "").replace(/\r\n/g, "\n").split("\n");
  const out: TopLevelDefBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const m = /^def\s+([A-Za-z_]\w*)\s*\(/.exec(lines[i]);
    if (!m) {
      i++;
      continue;
    }
    const name = m[1];
    const startLine = i;
    i++;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) {
        i++;
        continue;
      }
      if (/^def\s+/.test(line)) break;
      if (/^\S/.test(line)) break;
      i++;
    }
    let end = i;
    while (end > startLine + 1 && !lines[end - 1].trim()) end--;
    out.push({
      name,
      startLine,
      block: lines.slice(startLine, end).join("\n"),
    });
  }
  return out;
}

/** 社区分享存根：只有 pass / NotImplemented，无真实计算 */
export function isCommunityShareStub(code: string): boolean {
  const cleaned = (code || "")
    .replace(/"""[\s\S]*?"""/g, "")
    .replace(/'''[\s\S]*?'''/g, "")
    .replace(/^\s*#.*$/gm, "")
    .replace(/^\s*def\s+\w+\s*\([^)]*\)\s*:\s*/m, "")
    .trim();
  if (!cleaned) return true;
  if (/^pass\s*$/.test(cleaned)) return true;
  if (/^raise\s+NotImplementedError\b/.test(cleaned)) return true;
  return false;
}

/** 社区分享存根：只保留 def 名 + 一句中文说明，不贴实现 */
export function buildBuiltinFactorShareStub(
  factorName: string,
  libraryName?: string | string[] | null,
  chineseName?: string | null,
): string {
  const safe =
    /^[A-Za-z_][A-Za-z0-9_]*$/.test(factorName) ? factorName : "shared_factor";
  const label = (chineseName || "").trim() || safe;
  return [
    `def ${safe}(self):`,
    `    """内置因子：${label}"""`,
    `    pass`,
  ].join("\n");
}

function factorChineseLabel(meta: FactorMeta | null | undefined, fallback: string): string {
  if (!meta) return fallback;
  const d = (meta.description || "").trim();
  const e = (meta.explain || "").trim();
  if (d && d !== meta.name) return d;
  if (e && e !== meta.name && e !== d) return e;
  return d || e || fallback;
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function blockReferencesName(block: string, name: string): boolean {
  return new RegExp(`\\b${escapeRe(name)}\\s*\\(`).test(block);
}

/**
 * 社区分享脱敏：平台内置因子 → pass 存根；combo / 用户自定义保留。
 * 仅被脱敏块引用的 _ 辅助一并去掉，避免泄露实现。
 */
export async function sanitizeFactorShareCode(
  code: string,
  opts?: {
    libraryName?: string | string[] | null;
    factorName?: string | null;
    catalog?: FactorMeta[];
  },
): Promise<string> {
  const raw = (code || "").trim();
  if (!raw) {
    const fname = (opts?.factorName || "").trim();
    const lib = opts?.libraryName;
    if (fname && lib) {
      const catalog = opts?.catalog || (await loadFactors(true).catch(() => []));
      const pub = findPublicLibraryFactor(catalog, fname);
      return buildBuiltinFactorShareStub(
        fname,
        lib,
        factorChineseLabel(pub, fname),
      );
    }
    return "";
  }

  const catalog = opts?.catalog || (await loadFactors(true).catch(() => []));
  const blocks = splitTopLevelDefBlocks(raw);
  if (!blocks.length) {
    // 无 def：可能是注释存根；有 library 则换正式 pass 存根
    const fname = (opts?.factorName || "").trim();
    const lib = opts?.libraryName;
    if (fname && lib) {
      const pub = findPublicLibraryFactor(catalog, fname);
      return buildBuiltinFactorShareStub(
        fname,
        lib,
        factorChineseLabel(pub, fname),
      );
    }
    return raw;
  }

  type Kept = { name: string; text: string; stubbed: boolean };
  const kept: Kept[] = [];
  for (const b of blocks) {
    if (b.name.startsWith("_")) continue;
    if (isComboEntryName(b.name)) {
      kept.push({ name: b.name, text: b.block, stubbed: false });
      continue;
    }
    const pub = findPublicLibraryFactor(catalog, b.name);
    if (shouldHideFactorSource(pub) || (pub && isCommunityShareStub(b.block))) {
      const lib = pub?.library || opts?.libraryName || "builtin";
      const id = pub?.name || b.name;
      kept.push({
        name: id,
        text: buildBuiltinFactorShareStub(
          id,
          lib,
          factorChineseLabel(pub, id),
        ),
        stubbed: true,
      });
      continue;
    }
    kept.push({ name: b.name, text: b.block, stubbed: false });
  }

  // 私有辅助：仅当仍被「未脱敏」块引用时保留
  const keptBodies = kept.filter((k) => !k.stubbed).map((k) => k.text);
  for (const b of blocks) {
    if (!b.name.startsWith("_")) continue;
    if (keptBodies.some((t) => blockReferencesName(t, b.name))) {
      kept.push({ name: b.name, text: b.block, stubbed: false });
    }
  }

  // 稳定顺序：原出现序
  const order = new Map(blocks.map((b, i) => [b.name, i]));
  kept.sort(
    (a, b) => (order.get(a.name) ?? 999) - (order.get(b.name) ?? 999),
  );

  if (!kept.length) {
    const fname = (opts?.factorName || blocks[0]?.name || "").trim();
    const lib = opts?.libraryName;
    if (fname && lib) {
      const pub = findPublicLibraryFactor(catalog, fname);
      return buildBuiltinFactorShareStub(
        fname,
        lib,
        factorChineseLabel(pub, fname),
      );
    }
    return "";
  }
  return kept.map((k) => k.text).join("\n\n");
}

/**
 * 策略分享脱敏：类内 @factor 若命中平台库，函数体改为 pass。
 * @signal / 自定义 @factor / EXTRA 保留。
 */
export async function sanitizeStrategyShareCode(
  code: string,
  catalog?: FactorMeta[],
): Promise<string> {
  const raw = (code || "").trim();
  if (!raw) return "";
  const factors = catalog || (await loadFactors(true).catch(() => []));
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const defM = /^([ \t]*)def\s+([A-Za-z_]\w*)\s*\(/.exec(line);
    if (!defM) {
      out.push(line);
      i++;
      continue;
    }
    const indent = defM[1];
    const name = defM[2];
    const bodyPrefix = indent + "    ";

    let decoIdx = -1;
    for (let j = out.length - 1; j >= 0; j--) {
      if (!out[j].trim()) continue;
      if (/^[ \t]*@factor\b/.test(out[j])) decoIdx = j;
      break;
    }
    const hasFactorDeco = decoIdx >= 0;

    let end = i + 1;
    while (end < lines.length) {
      const L = lines[end];
      if (!L.trim()) {
        end++;
        continue;
      }
      if (L.startsWith(bodyPrefix)) {
        end++;
        continue;
      }
      break;
    }

    const pub = findPublicLibraryFactor(factors, name);
    const hide =
      !name.startsWith("_") &&
      !isComboEntryName(name) &&
      shouldHideFactorSource(pub) &&
      (hasFactorDeco || indent.length > 0);

    if (hide && pub) {
      if (hasFactorDeco) {
        out.splice(decoIdx);
      }
      const stub = buildBuiltinFactorShareStub(
        pub.name,
        pub.library,
        factorChineseLabel(pub, pub.name),
      )
        .split("\n")
        .map((ln) => (ln.trim() ? indent + ln : ln));
      if (hasFactorDeco || indent.length > 0) {
        out.push(`${indent}@factor`);
      }
      out.push(...stub);
      i = end;
      continue;
    }

    out.push(...lines.slice(i, end));
    i = end;
  }

  return out.join("\n");
}

export async function resolveCommunityCloneTarget(codeSnippet: string): Promise<
  | { kind: "public"; factor: FactorMeta }
  | { kind: "owned_custom"; factor: FactorMeta }
  | { kind: "custom"; defName: string | null }
> {
  const code = (codeSnippet || "").trim();
  if (!code) throw new Error("该帖没有代码片段，无法克隆到因子检测");
  if (!/^\s*def\s+[A-Za-z_]\w*\s*\(/m.test(code)) {
    throw new Error("代码片段须含完整函数，例如 def my_factor(self): ...");
  }
  const defName = extractDefName(code);
  const factors = await loadFactors(true);
  const pub = findPublicLibraryFactor(factors, defName);
  if (pub) return { kind: "public", factor: pub };
  const owned = findOwnedCustomFactor(factors, defName);
  if (owned) return { kind: "owned_custom", factor: owned };
  if (defName && isQlibAlphaFactorName(defName)) {
    return {
      kind: "public",
      factor: {
        name: defName,
        methodName: defName,
        description: defName,
        explain: defName,
        formula: "",
        params: {},
        library: "qlib_alpha",
        libraryFile: "qlib_alpha.py",
        libraryLabel: "Qlib特征",
      },
    };
  }
  return { kind: "custom", defName };
}

export type CommunityDetectClonePlan =
  | {
      kind: "library";
      factorIds: string[];
      comboFn: string;
      weightMode: WeightMode;
    }
  | {
      /** 公用/已有库因子 + 帖内自定义实现（临时草稿，不强制入库） */
      kind: "mixed";
      factorIds: string[];
      comboFn: string;
      weightMode: WeightMode;
      customDrafts: DraftDetectFactor[];
      /** @deprecated 兼容旧调用 */
      customCode?: string;
      suggestedName?: string | null;
    }
  | {
      /** 纯自定义：直接以临时草稿进检测，不再弹「新建因子」 */
      kind: "custom_draft";
      code: string;
      suggestedName: string | null;
      customDrafts: DraftDetectFactor[];
      comboFn?: string;
      weightMode?: WeightMode;
    };

function inferWeightModeFromCombo(comboFn: string): WeightMode {
  const c = comboFn || "";
  if (/\*\*/.test(c) && /self\.rank\s*\(/.test(c)) return "product";
  if (/[\d.]+\s*\*\s*self\./.test(c) || /self\.rank\s*\(/.test(c)) return "sum";
  return "custom";
}

/** 从 def 块 docstring 取首行中文说明 */
export function extractFactorDocline(block: string): string {
  const m = /(?:"""|''')([\s\S]*?)(?:"""|''')/.exec(block || "");
  if (!m) return "";
  const line = m[1]
    .trim()
    .split(/\r?\n/)
    .map((s) => s.trim())
    .find(Boolean);
  return line || "";
}

function customBlockToDraft(block: string): DraftDetectFactor | null {
  const name = extractDefName(block);
  if (!name || isComboEntryName(name) || name.startsWith("_")) return null;
  const description = extractFactorDocline(block) || name;
  return {
    name,
    description,
    category: "其他",
    body: block.trim(),
  };
}

/** 解析社区代码 → 因子检测克隆方案（公用库直选 / 临时草稿 / 弹窗新建） */
export async function planCommunityDetectClone(
  codeSnippet: string,
): Promise<CommunityDetectClonePlan> {
  const code = (codeSnippet || "").trim();
  if (!code) throw new Error("该帖没有代码片段，无法克隆到因子检测");
  const [factors, userRows] = await Promise.all([
    loadFactors(true),
    listAllUserLibraryFactors().catch(() => []),
  ]);
  const ownedNames = new Set(userRows.map((r) => r.name));
  const blocks = splitTopLevelDefBlocks(code);
  if (!blocks.length) {
    throw new Error("代码片段须含完整函数，例如 def my_factor(self): ...");
  }

  const libraryIds: string[] = [];
  let comboFn = "";
  const customBlocks: string[] = [];

  for (const b of blocks) {
    if (b.name.startsWith("_")) continue;
    if (isComboEntryName(b.name)) {
      comboFn = b.block;
      continue;
    }
    const pub = findPublicLibraryFactor(factors, b.name);
    // 平台内置 / 本机官方库：无论帖子里是 pass 存根还是误带了完整实现，
    // 一律按公用因子选中（不走自定义草稿，避免左侧只剩一个琥珀色因子）
    if (pub && shouldHideFactorSource(pub)) {
      if (!libraryIds.includes(pub.name)) libraryIds.push(pub.name);
      continue;
    }
    if (pub && isCommunityShareStub(b.block)) {
      if (!libraryIds.includes(pub.name)) libraryIds.push(pub.name);
      continue;
    }
    if (b.name && isQlibAlphaFactorName(b.name)) {
      if (!libraryIds.includes(b.name)) libraryIds.push(b.name);
      continue;
    }
    // 也认 docstring「内置因子：…」存根（名字偶发对不上索引时）
    if (
      isCommunityShareStub(b.block) &&
      /"""\s*内置因子[：:]/.test(b.block)
    ) {
      const id = pub?.name || b.name;
      if (!libraryIds.includes(id)) libraryIds.push(id);
      continue;
    }
    // 本人因子库已有同名 → 直接复用，不建临时草稿、不弹窗
    const owned = findOwnedCustomFactor(factors, b.name);
    if (owned) {
      if (!libraryIds.includes(owned.name)) libraryIds.push(owned.name);
      continue;
    }
    if (ownedNames.has(b.name)) {
      if (!libraryIds.includes(b.name)) libraryIds.push(b.name);
      continue;
    }
    customBlocks.push(b.block);
  }

  const customDrafts = customBlocks
    .map(customBlockToDraft)
    .filter((d): d is DraftDetectFactor => Boolean(d));

  if (libraryIds.length && !customDrafts.length) {
    const mode = comboFn ? inferWeightModeFromCombo(comboFn) : "sum";
    // 纯相加 / 无权重写法 → 赋权相加；否则保留自定义 combo
    const looksPlainSum =
      !comboFn ||
      (/^\s*return\s+self\.\w+\(\s*\)(\s*\+\s*self\.\w+\(\s*\))*\s*$/m.test(
        comboFn.replace(/"""[\s\S]*?"""/g, "").replace(/'''[\s\S]*?'''/g, ""),
      ) &&
        !/\*\*/.test(comboFn) &&
        !/[\d.]+\s*\*/.test(comboFn));
    return {
      kind: "library",
      factorIds: libraryIds,
      comboFn:
        comboFn ||
        (libraryIds.length === 1
          ? `def combo_factor(self):\n    """直通"""\n    return self.${libraryIds[0]}()`
          : `def combo_factor(self):\n    """自定义组合"""\n    return ${libraryIds.map((c) => `self.${c}()`).join(" + ")}`),
      weightMode:
        libraryIds.length === 1
          ? "sum"
          : looksPlainSum
            ? "sum"
            : mode || "custom",
    };
  }

  // 混合：库因子 + 帖内自定义 → 自定义作临时草稿带入检测（可报告页再入库）
  if (libraryIds.length && customDrafts.length) {
    const mode = comboFn ? inferWeightModeFromCombo(comboFn) : "custom";
    const allIds = [
      ...libraryIds,
      ...customDrafts.map((d) => d.name).filter((n) => !libraryIds.includes(n)),
    ];
    return {
      kind: "mixed",
      factorIds: libraryIds,
      comboFn:
        comboFn ||
        `def combo_factor(self):\n    """自定义组合"""\n    return ${allIds
          .map((c) => `self.${c}()`)
          .join(" + ")}`,
      weightMode: mode === "sum" || mode === "product" ? mode : "custom",
      customDrafts,
      customCode: customDrafts.map((d) => d.body).join("\n\n"),
      suggestedName: customDrafts[0]?.name ?? null,
    };
  }

  // 纯自定义：也走临时草稿直开检测（不再弹新建因子表单）
  if (!customDrafts.length) {
    const fallback = customBlockToDraft(code);
    if (fallback) customDrafts.push(fallback);
  }
  const mode = comboFn ? inferWeightModeFromCombo(comboFn) : "sum";
  return {
    kind: "custom_draft",
    code,
    suggestedName: customDrafts[0]?.name || extractDefName(code),
    customDrafts,
    comboFn: comboFn || undefined,
    weightMode:
      customDrafts.length <= 1
        ? "sum"
        : mode === "sum" || mode === "product"
          ? mode
          : "custom",
  };
}

async function expandPublicFactorSource(f: FactorMeta): Promise<string> {
  if (DYNAMIC_FACTOR_LIBS.has(f.library) || isQlibAlphaFactorName(f.name)) {
    const expanded = expandQlibAlphaFactorSource(f.name);
    if (!expanded) {
      throw new Error(
        `「${f.name}」暂无法展开为策略源码（未识别的 Qlib 特征名）。请改用「克隆到因子检测」。`,
      );
    }
    return expanded;
  }
  const src = await loadLibrarySource(f.libraryFile);
  const methodName = f.methodName || f.name;
  let extracted = extractFactorWithHelpers(src, methodName);
  if (methodName !== f.name) {
    extracted = extracted.replace(
      new RegExp(
        `^def\\s+${methodName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\(`,
        "m",
      ),
      `def ${f.name}(`,
    );
  }
  return extracted;
}

/**
 * 策略克隆用源码：已是完整策略则原样返回（类内平台 pass 存根会本机展开）；
 * 公用库存根 / 多因子存根 → 本机展开实现；自定义保留原文。
 */
export async function resolveStrategyCloneSource(codeSnippet: string): Promise<string> {
  const code = (codeSnippet || "").trim();
  if (!code) throw new Error("该帖没有代码片段，无法克隆到策略研究");

  const looksFullStrategy =
    /FactorPortfolioStrategy/.test(code) ||
    /def\s+generate_signals\s*\(/.test(code) ||
    (/^\s*class\s+\w+/m.test(code) && /@factor\b/.test(code));
  if (looksFullStrategy) {
    return expandStrategyPlatformStubs(code);
  }

  const blocks = splitTopLevelDefBlocks(code);
  const factors = await loadFactors(true);

  // 多 def（含 combo）或单存根：逐个展开公用库
  if (blocks.length >= 1) {
    const publicLike = blocks.filter((b) => !b.name.startsWith("_"));
    const needsExpand = publicLike.some((b) => {
      if (isComboEntryName(b.name)) return false;
      const pub = findPublicLibraryFactor(factors, b.name);
      return (
        isCommunityShareStub(b.block) ||
        (pub != null && shouldHideFactorSource(pub))
      );
    });
    const multi = publicLike.length > 1 || needsExpand;

    if (multi) {
      const parts: string[] = [];
      for (const b of blocks) {
        if (isComboEntryName(b.name)) {
          parts.push(b.block);
          continue;
        }
        if (b.name.startsWith("_")) {
          if (!isCommunityShareStub(b.block)) parts.push(b.block);
          continue;
        }
        const pub = findPublicLibraryFactor(factors, b.name);
        if (
          pub &&
          (isCommunityShareStub(b.block) || shouldHideFactorSource(pub))
        ) {
          parts.push(await expandPublicFactorSource(pub));
          continue;
        }
        if (isCommunityShareStub(b.block)) {
          if (isQlibAlphaFactorName(b.name)) {
            const expanded = expandQlibAlphaFactorSource(b.name);
            if (expanded) {
              parts.push(expanded);
              continue;
            }
          }
          throw new Error(
            `「${b.name}」是公用库存根且未匹配到本地因子库，无法克隆到策略。请改用「克隆到因子检测」。`,
          );
        }
        parts.push(b.block);
      }
      return parts.join("\n\n");
    }
  }

  const target = await resolveCommunityCloneTarget(code);
  if (target.kind === "public" || target.kind === "owned_custom") {
    return expandPublicFactorSource(target.factor);
  }

  if (isCommunityShareStub(code)) {
    const defName = extractDefName(code);
    if (defName && isQlibAlphaFactorName(defName)) {
      const expanded = expandQlibAlphaFactorSource(defName);
      if (expanded) return expanded;
    }
    throw new Error(
      "该帖代码是公用库存根（无实现），且未匹配到本地因子库，无法克隆到策略。请从因子检测报告重新分享，或改用「克隆到因子检测」。",
    );
  }
  return code;
}

/** 完整策略类内：把平台 @factor pass 存根本机展开 */
async function expandStrategyPlatformStubs(code: string): Promise<string> {
  const factors = await loadFactors(true).catch(() => [] as FactorMeta[]);
  const lines = code.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const defM = /^([ \t]*)def\s+([A-Za-z_]\w*)\s*\(/.exec(line);
    if (!defM) {
      out.push(line);
      i++;
      continue;
    }
    const indent = defM[1];
    const name = defM[2];
    const bodyPrefix = indent + "    ";
    let decoIdx = -1;
    for (let j = out.length - 1; j >= 0; j--) {
      if (!out[j].trim()) continue;
      if (/^[ \t]*@factor\b/.test(out[j])) decoIdx = j;
      break;
    }
    const hasFactorDeco = decoIdx >= 0;
    let end = i + 1;
    while (end < lines.length) {
      const L = lines[end];
      if (!L.trim()) {
        end++;
        continue;
      }
      if (L.startsWith(bodyPrefix)) {
        end++;
        continue;
      }
      break;
    }
    const methodText = lines.slice(i, end).join("\n");
    const pub = findPublicLibraryFactor(factors, name);
    if (
      hasFactorDeco &&
      pub &&
      shouldHideFactorSource(pub) &&
      isCommunityShareStub(methodText)
    ) {
      if (hasFactorDeco) out.splice(decoIdx);
      const expanded = await expandPublicFactorSource(pub);
      const indented = expanded
        .replace(/\r\n/g, "\n")
        .split("\n")
        .map((ln) => (ln.trim() ? indent + ln : ln));
      out.push(`${indent}@factor`);
      out.push(...indented);
      i = end;
      continue;
    }
    out.push(...lines.slice(i, end));
    i = end;
  }
  return out.join("\n");
}
