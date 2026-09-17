import { FormEvent, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, MessageSquare, Send } from "lucide-react";
import { testProviderChat } from "@/lib/api";

type Turn = { role: "user" | "assistant"; content: string };

/** 单模型对话探测：不改默认角色，直接打供应商 chat/completions */
export function ModelTestPage() {
  const [params] = useSearchParams();
  const providerKey = (params.get("provider") || "").trim();
  const modelName = (params.get("model") || "").trim();

  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const title = useMemo(() => {
    if (modelName) return modelName;
    return "模型对话测试";
  }, [modelName]);

  const onSend = async (e?: FormEvent) => {
    e?.preventDefault();
    const msg = input.trim();
    if (!msg || loading) return;
    if (!providerKey || !modelName) {
      setErr("缺少供应商或模型名，请从「模型供应商」页点击「对话测试」进入");
      return;
    }
    setErr(null);
    setTurns((t) => [...t, { role: "user", content: msg }]);
    setInput("");
    setLoading(true);
    try {
      const out = await testProviderChat({
        providerKey,
        modelName,
        message: msg,
      });
      setTurns((t) => [
        ...t,
        { role: "assistant", content: out.answer || "（空回复）" },
      ]);
    } catch (ex) {
      const message = ex instanceof Error ? ex.message : String(ex);
      setErr(message);
      // 错误只在顶栏提示，不重复塞进对话气泡
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100dvh-5.5rem)] max-w-3xl flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/settings/models"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          返回模型配置
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <MessageSquare className="h-5 w-5 text-violet-600" />
            {title}
          </h1>
        </div>
      </div>

      {err ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {err}
        </p>
      ) : null}

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        {turns.length === 0 ? (
          <p className="py-16 text-center text-sm text-slate-400">
            发送一条消息，验证该模型是否可用（不修改默认 LLM 设置）
          </p>
        ) : (
          turns.map((t, i) => (
            <div
              key={`${t.role}-${i}`}
              className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                  t.role === "user"
                    ? "bg-violet-600 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                {t.content}
              </div>
            </div>
          ))
        )}
        {loading ? (
          <p className="text-center text-xs text-slate-400">模型生成中…</p>
        ) : null}
      </div>

      <form
        onSubmit={(e) => void onSend(e)}
        className="flex gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm"
      >
        <input
          className="min-w-0 flex-1 rounded-xl border-0 bg-transparent px-3 py-2.5 text-sm outline-none"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入测试问题…"
          disabled={loading || !providerKey || !modelName}
        />
        <button
          type="submit"
          disabled={loading || !input.trim() || !providerKey || !modelName}
          className="inline-flex items-center gap-1 rounded-xl bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
          发送
        </button>
      </form>
    </div>
  );
}
