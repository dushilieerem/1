import { CodeFormulaPreview } from "@/lib/codeFormulaPreview";

/** 公式展示：代码式用彩色结构预览（对齐 NBQuant） */
export function FactorFormula({ formula }: { formula: string }) {
  const raw = formula.trim();
  if (!raw) return <p className="text-sm text-slate-400">暂无公式</p>;
  return <CodeFormulaPreview formula={raw} />;
}
