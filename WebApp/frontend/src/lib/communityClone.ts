import { extractDefName, loadFactors, type FactorMeta } from "@/lib/factorCatalog";

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
  return { kind: "custom", defName };
}
