/**
 * 审计：对 catalog 中每个 RE 内置因子跑 buildYgFactorRequestParts（单因子直通）。
 * 用法：在 frontend 目录执行
 *   npx --yes tsx scripts/audit-builtin-parts.ts
 */
import {
  auditBuiltinPassthroughParts,
  isReBuiltinLib,
} from "../src/lib/detectComboCode.ts";
import type { FactorMeta } from "../src/lib/factorCatalog.ts";

const API = process.env.SVQUANT_API || "http://127.0.0.1:8766";

async function main() {
  const res = await fetch(`${API}/api/factor/re-catalog?all=1`);
  if (!res.ok) throw new Error(`re-catalog HTTP ${res.status}`);
  const data = (await res.json()) as { factors?: Array<Record<string, unknown>> };
  const raw = data.factors || [];
  const all: FactorMeta[] = raw.map((f) => {
    const name = String(f.name || "");
    const library = String(f.library || "");
    return {
      name,
      methodName: name,
      description: String(f.description || name),
      explain: String(f.description || name),
      formula: "",
      params: {},
      library,
      libraryFile: "",
      libraryLabel: library,
    };
  });
  const builtins = all.filter((f) => isReBuiltinLib(f.library));
  console.log(`catalog 总数=${all.length} 内置=${builtins.length}`);
  const bad = auditBuiltinPassthroughParts(all);
  if (bad.length) {
    console.error(`FAIL ${bad.length} 项不合格:`);
    for (const b of bad.slice(0, 40)) {
      console.error(`  ${b.library}.${b.name}: ${b.reason}`, JSON.stringify(b.parts));
    }
    process.exit(1);
  }
  console.log(
    `OK 全部 ${builtins.length} 个内置因子单因子直通均为 library_name + factor_name（无 factor_code）`,
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
