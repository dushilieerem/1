import type { AiStrategyDraft } from "../lib/aiStrategyApi";

export function AiStrategyExplanation({ draft }: { draft: AiStrategyDraft }) {
  return (
    <section aria-label="策略说明" className="space-y-2 border-b border-slate-200/60 px-3 py-3 text-sm leading-6 text-slate-600">
      <h2 className="font-semibold text-slate-800">策略说明</h2>
      <p className="whitespace-pre-wrap">{draft.description || "生成服务未提供策略说明，请核对代码后再研究。"}</p>
      {draft.assumptions?.length > 0 && (
        <div><h3 className="font-medium">选股假设与数据要求</h3><ul className="list-disc pl-5">{draft.assumptions.map((text, i) => <li key={i}>{text}</li>)}</ul></div>
      )}
      {draft.warnings?.length > 0 && (
        <div className="text-amber-800"><h3 className="font-medium">注意事项</h3><ul className="list-disc pl-5">{draft.warnings.map((text, i) => <li key={i}>{text}</li>)}</ul></div>
      )}
    </section>
  );
}
