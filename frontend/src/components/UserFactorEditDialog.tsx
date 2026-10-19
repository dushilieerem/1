import { useState } from "react";
import type { FactorMeta } from "../lib/factorCatalog";
import { factorNameError } from "../lib/factorName";
import { updateUserLibraryFactor, userLibraryFactorToMeta } from "../lib/userFactorLibraries";

export function UserFactorEditDialog({ factor, onSaved, onClose }: {
  factor: FactorMeta; onSaved: (factor: FactorMeta) => void; onClose: () => void;
}) {
  const [name, setName] = useState(factor.name);
  const [description, setDescription] = useState(factor.description || "");
  const [body, setBody] = useState(factor.body || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    if (busy) return;
    setError("");
    const nameError = factorNameError(name);
    if (nameError) { setError(nameError); return; }
    if (!description.trim()) { setError("请填写因子说明"); return; }
    if (factor.body?.trim() && !body.trim()) { setError("因子代码不能为空"); return; }
    setBusy(true);
    try {
      // 改名时同步入口函数名；保留正文，不替换注释/字符串中的同名文字。
      const code = body.replace(new RegExp(`^(def\\s+)${factor.name}(\\s*\\()`, "m"), `$1${name.trim()}$2`);
      const saved = await updateUserLibraryFactor(factor.userLibraryId!, factor.userLibraryFactorId!, {
        name: name.trim(), description: description.trim(), body: code,
      });
      onSaved(userLibraryFactorToMeta(saved));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
    <div role="dialog" aria-modal="true" aria-label="编辑因子" className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-xl">
      <h3 className="mb-4 font-bold">编辑因子</h3>
      <label className="mb-3 block text-sm">因子代码名<input className="mt-1 block w-full rounded border p-2" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} /></label>
      <label className="mb-3 block text-sm">因子说明<input className="mt-1 block w-full rounded border p-2" value={description} onChange={(e) => setDescription(e.target.value)} disabled={busy} /></label>
      <label className="mb-3 block text-sm">因子代码<textarea className="mt-1 block w-full rounded border p-2 font-mono" rows={12} value={body} onChange={(e) => setBody(e.target.value)} disabled={busy} spellCheck={false} /></label>
      <p className="text-xs text-slate-500">修改只影响后续检测，历史报告保留原有代码和结果。</p>
      {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
      <div className="mt-4 flex justify-end gap-3"><button disabled={busy} onClick={onClose}>取消</button><button className="rounded bg-blue-600 px-4 py-2 text-white" disabled={busy} onClick={() => void save()}>{busy ? "保存中…" : "保存"}</button></div>
    </div>
  </div>;
}
