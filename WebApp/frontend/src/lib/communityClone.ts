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
  // 存根名是 qlib_* 但索引未命中时，仍按动态库名走检测（避免误进自定义页）
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

/**
 * 策略克隆用源码：已是完整策略则原样返回；
 * 否则公用库命中则拉本地真实实现（含 _ 辅助）。
 * qlib_alpha 动态特征按命名规则展开公式（策略 API 无 library_name）。
 */
export async function resolveStrategyCloneSource(codeSnippet: string): Promise<string> {
  const code = (codeSnippet || "").trim();
  if (!code) throw new Error("该帖没有代码片段，无法克隆到策略研究");

  // 帖子已是完整策略：不要按首个 def 当成单因子去「展开」
  const looksFullStrategy =
    /FactorPortfolioStrategy/.test(code) ||
    /def\s+generate_signals\s*\(/.test(code) ||
    (/^\s*class\s+\w+/m.test(code) && /@factor\b/.test(code));
  if (looksFullStrategy) {
    return code;
  }

  const target = await resolveCommunityCloneTarget(code);
  if (target.kind === "public" || target.kind === "owned_custom") {
    const f = target.factor;
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
    // 只改公开方法名；勿用 renameMethodDef（会误改第一个 _ 辅助）
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
