import { useEffect, useRef, useState } from "react";
import { ygGenerateFactorDraft, type AiFactorDraft, type AiFactorGenerationResult } from "@/lib/aiFactorApi";
import { subscribeAuth } from "@/lib/researchClient";
import {newUuidV4} from '@/lib/uuid';

export function FactorDraftAssistant({ hypothesis, name, draftVersion, onApply }: {
  hypothesis: string; name: string; draftVersion: string; onApply: (factor: AiFactorDraft) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [proposal, setProposal] = useState<{ result: AiFactorGenerationResult; version: string }>();
  const control = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  useEffect(() => {
    const reset = () => { ++sequence.current; control.current?.abort(); control.current = null; setBusy(false); setProposal(undefined); setError(""); };
    const unsubscribe = subscribeAuth(reset);
    return () => { ++sequence.current; control.current?.abort(); unsubscribe(); };
  }, []);
  async function generate() {
    if (control.current) return;
    if (hypothesis.trim().length < 10) { setError("请先填写至少 10 个字的研究假设，说明使用的数据与计算方法。"); return; }
    const controller = new AbortController();
    control.current = controller;
    const current = ++sequence.current;
    const version = draftVersion;
    setBusy(true); setError(""); setProposal(undefined);
    try {
      const result = await ygGenerateFactorDraft({
        prompt: hypothesis.trim(),
        context: { frequency: "1d", preferred_factor_name: name.trim() || null },
        idempotency_key: newUuidV4(),
      }, controller.signal);
      if (current === sequence.current) setProposal({result, version});
    } catch (e) {
      if (current === sequence.current && !controller.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (current === sequence.current) { setBusy(false); control.current = null; }
    }
  }
  function stopWaiting() {
    ++sequence.current; control.current?.abort(); control.current = null; setBusy(false);
    setError("已停止等待。已提交的模型请求可能仍在服务端完成，本页不会自动采纳其结果。");
  }
  const stale = proposal && proposal.version !== draftVersion;
  const result = proposal?.result;
  const canApply = result?.status === "ready" && result.validation.status === "passed" && result.factor && !stale;
  return <aside aria-label="因子草稿助手" className="space-y-3 rounded-xl border border-purple-200 bg-purple-50/50 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-sm font-semibold text-[#65358D]">AI 因子草稿助手</h3>
      <button type="button" disabled={busy} onClick={() => void generate()} className="rounded-lg border border-purple-300 bg-white px-3 py-2 text-sm text-[#65358D] disabled:opacity-50">{busy ? "生成并校验中…" : "根据研究假设生成代码"}</button>
    </div>
    <p className="text-xs text-slate-600">使用平台现有生成与静态校验能力。建议经你采纳后才填入表单；不会自动保存、回测或审批。</p>
    {busy && <div role="status" className="text-sm">正在请求平台生成草稿并进行静态校验。<button type="button" className="ml-3 underline" onClick={stopWaiting}>停止等待</button></div>}
    {error && <div role="alert" className="text-sm text-red-700"><p>本次请求未完成，未采纳任何代码。</p><details className="mt-1"><summary className="cursor-pointer">错误详情</summary><p className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all">{error}</p></details></div>}
    {result && <div className="space-y-3">
      <p className="text-sm font-medium">{result.validation.status === "passed" ? "静态校验通过，等待采纳" : "未通过静态校验"}</p>
      {result.validation.errors?.map((value,i) => <p key={i} className="text-sm text-red-700">{value}</p>)}
      {result.factor && <>
        <p className="text-sm">{result.factor.description}</p>
        <pre className="max-h-64 overflow-auto rounded-lg bg-white p-3 text-xs">{result.factor.factor_code}</pre>
        <p className="break-words text-xs text-slate-500">使用字段：{result.factor.used_fields.join("、") || "未声明"}</p>
        {[...result.factor.assumptions, ...result.factor.warnings, ...result.validation.warnings].map((value,i) => <p key={i} className="text-xs text-slate-600">{value}</p>)}
      </>}
      <details className="text-xs text-slate-500"><summary className="cursor-pointer">本次调用记录</summary><p className="mt-2 break-all">请求：{result.generation_id}</p><p>模型：{result.meta?.model_alias || "未返回"} · 耗时：{result.meta?.latency_ms ?? "未返回"} ms</p><p>提示词版本：{result.meta?.prompt_version || "未返回"} · 校验规则：{result.validation.capability_catalog_version || "未返回"}</p></details>
      {stale && <p role="status" className="text-sm text-amber-700">当前研究内容已修改，请重新生成建议，避免覆盖你的编辑。</p>}
      {result.factor && <button type="button" disabled={!canApply} className="rounded-lg bg-[#65358D] px-4 py-2 text-sm text-white disabled:opacity-50" onClick={() => { if (canApply && result.factor) { onApply(result.factor); setProposal(undefined); } }}>采纳到代码表单</button>}
    </div>}
  </aside>;
}
