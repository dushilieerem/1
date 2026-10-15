import type { AiFactorDraft } from "../lib/aiFactorApi";

export function AiFactorExplanation({ draft }: { draft: AiFactorDraft }) {
  return (
    <section aria-label="因子说明" className="space-y-2 border-b border-slate-200/60 px-3 py-3 text-sm leading-6 text-slate-600">
      <h2 className="font-semibold text-slate-800">因子说明</h2>
      <p className="whitespace-pre-wrap">{draft.description || "生成服务未提供因子说明，请核对代码后再检测。"}</p>
      {draft.assumptions?.length > 0 && (
        <div><h3 className="font-medium">计算假设与数据要求</h3><ul className="list-disc pl-5">{draft.assumptions.map((text, i) => <li key={i}>{text}</li>)}</ul></div>
      )}
      {draft.warnings?.length > 0 && (
        <div className="text-amber-800"><h3 className="font-medium">注意事项</h3><ul className="list-disc pl-5">{draft.warnings.map((text, i) => <li key={i}>{text}</li>)}</ul></div>
      )}
    </section>
  );
}
