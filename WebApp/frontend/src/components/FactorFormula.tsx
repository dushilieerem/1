import { CodeFormulaPreview } from "@/lib/codeFormulaPreview";

/** 公式展示：多行 Python 源码预览（保留换行，不做分数排版） */
export function FactorFormula({ formula }: { formula: string }) {
  const raw = formula.trim();
  if (!raw) return <p className="text-sm text-slate-400">暂无公式</p>;
  return <CodeFormulaPreview formula={raw} />;
}
