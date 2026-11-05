import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, History, RotateCcw, Save, Search, ShieldCheck, X } from "lucide-react";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  getAiAgentPromptHistory,
  listAiAgents,
  resetAiAgentPrompt,
  saveAiAgentPrompt,
  type AiAgent,
  type AiAgentPromptHistory,
} from "@/lib/aiAgentApi";

const SOURCE_LABEL: Record<string, string> = {
  institution: "机构 Agent",
  platform: "平台 Agent",
  skill: "Agent 技能",
};

/** 个人中心 · Agent 管理：展示所有 Agent，管理员可改机构/平台提示词。 */
export function MeAgentsPanel() {
  const confirm = useConfirm();
  const [items, setItems] = useState<AiAgent[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "institution" | "platform" | "skill">("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<AiAgent | null>(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<AiAgentPromptHistory[]>([]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listAiAgents()
      .then((data) => {
        setItems(data.items || []);
        setCanEdit(Boolean(data.can_edit));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const filtered = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    return items.filter((item) => {
      if (filter !== "all" && item.source !== filter) return false;
      if (!keyword) return true;
      return `${item.name} ${item.task_id} ${item.group} ${item.description}`.toLowerCase().includes(keyword);
    });
  }, [items, filter, q]);

  const open = (item: AiAgent) => {
    setSelected(item);
    setDraft(item.prompt || item.default_prompt || "");
    setNote("");
    setHistory([]);
    if (canEdit && item.editable) {
      void getAiAgentPromptHistory(item.task_id).then(setHistory).catch(() => setHistory([]));
    }
  };

  const refreshSelected = (agent: AiAgent) => {
    setSelected(agent);
    setDraft(agent.prompt || agent.default_prompt || "");
    setItems((prev) => prev.map((item) => (item.task_id === agent.task_id ? agent : item)));
  };

  const save = async () => {
    if (!selected || !draft.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await saveAiAgentPrompt(selected.task_id, draft, note);
      if (res.agent) refreshSelected(res.agent);
      const hist = await getAiAgentPromptHistory(selected.task_id);
      setHistory(hist);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!selected) return;
    const ok = await confirm({
      title: "恢复默认提示词？",
      message: "当前自定义版本会归档，下一次生成使用代码默认提示词。",
      confirmLabel: "恢复默认",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const res = await resetAiAgentPrompt(selected.task_id);
      if (res.agent) refreshSelected(res.agent);
      const hist = await getAiAgentPromptHistory(selected.task_id);
      setHistory(hist);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Agent 管理</h2>
          <p className="mt-1 text-sm text-slate-500">
            展示系统内全部 Agent；机构/平台 Agent 由管理员维护提示词，改动会记录版本并可恢复默认。
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
          <Bot className="h-3.5 w-3.5" /> {items.length} 个 Agent
        </span>
      </div>

      {error ? (
        <div className="mb-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {[
          ["all", "全部"],
          ["institution", "机构 Agent"],
          ["platform", "平台 Agent"],
          ["skill", "Agent 技能"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key as typeof filter)}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              filter === key
                ? "border-violet-200 bg-violet-50 text-violet-700"
                : "border-slate-200 bg-white text-slate-600"
            }`}
          >
            {label}
          </button>
        ))}
        <label className="ml-auto flex min-w-[180px] items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5">
          <Search className="h-3.5 w-3.5 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索名称 / task_id"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </label>
      </div>

      {loading ? <p className="text-sm text-slate-500">正在加载 Agent…</p> : null}
      {!loading && !filtered.length ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          没有匹配的 Agent。
        </p>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        {filtered.map((item) => (
          <button
            key={item.task_id}
            type="button"
            onClick={() => open(item)}
            className="rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-violet-300"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-slate-900">{item.name}</p>
                <p className="mt-0.5 font-mono text-[11px] text-slate-500">{item.task_id}</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
                {SOURCE_LABEL[item.source] || item.source}
              </span>
            </div>
            <p className="mt-2 line-clamp-2 text-xs text-slate-500">{item.description}</p>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-slate-500">
              <span className="rounded bg-slate-50 px-1.5 py-0.5">{item.group}</span>
              {item.auto_run ? <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">自动运行</span> : null}
              <span className="rounded bg-slate-50 px-1.5 py-0.5">v{item.prompt_version}</span>
              {item.override ? <span className="rounded bg-violet-50 px-1.5 py-0.5 text-violet-700">已覆盖</span> : null}
              {!item.editable ? <span className="rounded bg-slate-50 px-1.5 py-0.5">只读</span> : null}
            </div>
          </button>
        ))}
      </div>

      {selected ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-3 sm:p-6">
          <div className="my-4 w-full max-w-3xl rounded-2xl bg-white p-5 shadow-2xl">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">{selected.name}</h3>
                <p className="mt-0.5 font-mono text-[11px] text-slate-500">{selected.task_id}</p>
                <p className="mt-1 text-xs text-slate-500">{selected.description}</p>
              </div>
              <button type="button" onClick={() => setSelected(null)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
              <div className="flex flex-wrap items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-slate-500" />
                {canEdit && selected.editable
                  ? "管理员可编辑；保存后版本 +1，旧 AI 结果缓存自动失效。"
                  : "当前账号只读；机构/平台 Agent 提示词仅管理员可改。"}
                <span className="rounded bg-white px-1.5 py-0.5">v{selected.prompt_version}</span>
                {selected.override ? <span className="rounded bg-violet-100 px-1.5 py-0.5 text-violet-700">已覆盖</span> : null}
              </div>
            </div>

            <label className="mt-4 block text-xs font-medium text-slate-600">
              提示词
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={!canEdit || !selected.editable || busy}
                className="mt-1 min-h-[260px] w-full rounded-xl border border-slate-200 bg-white p-3 font-mono text-xs leading-relaxed text-slate-700 outline-none focus:border-violet-300 disabled:bg-slate-50"
              />
            </label>
            <p className="mt-1 text-[11px] text-slate-400">
              系统仍会强制 JSON 校验、50 字摘要、证据引用与风控约束；提示词不能关闭这些规则。
            </p>

            {canEdit && selected.editable ? (
              <label className="mt-3 block text-xs font-medium text-slate-600">
                变更说明（可选）
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-violet-300"
                  placeholder="例如：加强反证要求"
                />
              </label>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2">
              {canEdit && selected.editable ? (
                <>
                  <button
                    type="button"
                    disabled={busy || !draft.trim()}
                    onClick={() => void save()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    <Save className="h-4 w-4" /> {busy ? "保存中…" : "保存提示词"}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reset()}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 disabled:opacity-50"
                  >
                    <RotateCcw className="h-4 w-4" /> 恢复默认
                  </button>
                </>
              ) : null}
              {canEdit && selected.editable ? (
                <button
                  type="button"
                  onClick={() => {
                    void getAiAgentPromptHistory(selected.task_id)
                      .then(setHistory)
                      .catch((e: Error) => setError(e.message));
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600"
                >
                  <History className="h-4 w-4" /> 版本历史
                </button>
              ) : null}
            </div>

            {history.length ? (
              <div className="mt-4 max-h-64 overflow-y-auto rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-3 py-2">版本</th>
                      <th className="px-3 py-2">动作</th>
                      <th className="px-3 py-2">状态</th>
                      <th className="px-3 py-2">时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((row) => (
                      <tr key={row.id} className="border-t border-slate-100">
                        <td className="px-3 py-2">v{row.version_no}</td>
                        <td className="px-3 py-2">{row.action === "reset" ? "恢复默认" : "保存"}</td>
                        <td className="px-3 py-2">{row.status === "active" ? "生效中" : "已归档"}</td>
                        <td className="px-3 py-2 text-slate-500">{row.created_at?.slice(0, 19).replace("T", " ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
