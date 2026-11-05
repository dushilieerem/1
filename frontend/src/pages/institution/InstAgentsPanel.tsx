import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, History, RotateCcw, Save, Search, ShieldCheck, X } from "lucide-react";
import { instApi } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "./instUi";

type AiAgent = {
  task_id: string;
  name: string;
  group: string;
  description: string;
  auto_run: boolean;
  editable: boolean;
  source: string;
  prompt_version: string;
  override: boolean;
  prompt: string | null;
  default_prompt: string | null;
};

type AgentList = { items: AiAgent[]; count: number; editable_count: number; can_edit: boolean };
type PromptHistory = {
  id: number;
  version_no: number;
  action: string;
  status: string;
  created_at?: string;
};

const SOURCE_LABEL: Record<string, string> = {
  institution: "机构 Agent",
  platform: "平台 Agent",
  skill: "Agent 技能",
};

/** 机构端 Agent 管理：替代原 Agent 能力页，展示全部 Agent，经理可改提示词。 */
export function InstAgentsPanel() {
  const session = useInstSession();
  const { t } = useInstLocale();
  const [items, setItems] = useState<AiAgent[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "institution" | "platform" | "skill">("institution");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<AiAgent | null>(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<PromptHistory[]>([]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    instApi<AgentList>("/agents")
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
      void instApi<{ items: PromptHistory[] }>(`/agents/${encodeURIComponent(item.task_id)}/prompt/history`)
        .then((res) => setHistory(res.items || []))
        .catch(() => setHistory([]));
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
      const res = await instApi<{ agent: AiAgent }>(`/agents/${encodeURIComponent(selected.task_id)}/prompt`, {
        method: "PUT",
        body: { prompt: draft, note: note || null },
      });
      if (res.agent) refreshSelected(res.agent);
      const hist = await instApi<{ items: PromptHistory[] }>(
        `/agents/${encodeURIComponent(selected.task_id)}/prompt/history`,
      );
      setHistory(hist.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!selected) return;
    if (!window.confirm(t("恢复默认提示词？当前版本会归档。", "Reset to the default prompt? The current version will be archived."))) return;
    setBusy(true);
    setError(null);
    try {
      const res = await instApi<{ agent: AiAgent }>(
        `/agents/${encodeURIComponent(selected.task_id)}/prompt/reset`,
        { method: "POST" },
      );
      if (res.agent) refreshSelected(res.agent);
      const hist = await instApi<{ items: PromptHistory[] }>(
        `/agents/${encodeURIComponent(selected.task_id)}/prompt/history`,
      );
      setHistory(hist.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title={t("Agent 管理", "Agent management")}
      desc={t(
        "展示系统内全部 Agent；机构/平台 Agent 由投资经理维护提示词，改动会记录版本并可恢复默认。",
        "All agents in the system. The investment manager can edit institution/platform prompts with version history and reset.",
      )}
      actions={<Badge tone="gold">{items.length} {t("个 Agent", "agents")}</Badge>}
    >
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {loading ? <Loading label={t("正在加载 Agent…", "Loading agents…")} /> : null}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {[
          ["institution", t("机构 Agent", "Institution")],
          ["platform", t("平台 Agent", "Platform")],
          ["skill", t("Agent 技能", "Skills")],
          ["all", t("全部", "All")],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key as typeof filter)}
            className={`rounded-lg border px-3 py-1.5 text-xs transition ${
              filter === key
                ? "border-[#b42345] bg-[#fbe9ef] text-[#a31f42]"
                : "border-[#dde5f2] bg-white text-[#68738b] hover:border-[#7950ba]"
            }`}
          >
            {label}
          </button>
        ))}
        <label className="ml-auto flex min-w-[190px] items-center gap-2 rounded-lg border border-[#dde5f2] bg-white px-3 py-1.5">
          <Search className="h-3.5 w-3.5 text-[#a9a4bd]" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("搜索名称 / task_id", "Search name / task_id")}
            className="min-w-0 flex-1 bg-transparent text-xs outline-none"
          />
        </label>
      </div>

      {!loading && !filtered.length ? <Empty>{t("没有匹配的 Agent。", "No matching agents.")}</Empty> : null}

      <div className="grid gap-3 lg:grid-cols-2">
        {filtered.map((item) => (
          <button
            key={item.task_id}
            type="button"
            onClick={() => open(item)}
            className="rounded-xl border border-[#dde5f2] bg-white p-4 text-left transition hover:border-[#7950ba]"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-[#171923]">{item.name}</p>
                <p className="mt-0.5 font-mono text-[10px] text-[#77718c]">{item.task_id}</p>
              </div>
              <Badge tone={item.source === "institution" ? "gold" : "slate"}>
                {SOURCE_LABEL[item.source] || item.source}
              </Badge>
            </div>
            <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-[#68738b]">{item.description}</p>
            <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-[#77718c]">
              <span className="rounded bg-[#f8faff] px-1.5 py-0.5">{item.group}</span>
              {item.auto_run ? <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">{t("自动运行", "Auto")}</span> : null}
              <span className="rounded bg-[#f8faff] px-1.5 py-0.5">v{item.prompt_version}</span>
              {item.override ? <span className="rounded bg-[#f2eafa] px-1.5 py-0.5 text-[#7950ba]">{t("已覆盖", "Overridden")}</span> : null}
              {!item.editable ? <span className="rounded bg-[#f8faff] px-1.5 py-0.5">{t("只读", "Read-only")}</span> : null}
            </div>
          </button>
        ))}
      </div>

      {selected ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#171923]/45 p-3 sm:p-6">
          <div className="my-4 w-full max-w-3xl rounded-2xl bg-white p-5 shadow-2xl">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-lg font-semibold text-[#171923]">{selected.name}</h3>
                <p className="mt-0.5 font-mono text-[10px] text-[#77718c]">{selected.task_id}</p>
                <p className="mt-1 text-xs text-[#68738b]">{selected.description}</p>
              </div>
              <Button variant="ghost" onClick={() => setSelected(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3 text-[11px] text-[#68738b]">
              <ShieldCheck className="h-4 w-4 text-[#b42345]" />
              {canEdit && selected.editable
                ? t("投资经理可编辑；保存后版本 +1，旧 AI 结果缓存自动失效。", "Manager can edit; saving bumps the version and invalidates cached AI results.")
                : t("当前角色只读；机构/平台 Agent 提示词仅投资经理可改。", "Read-only for this role; only the investment manager can edit institution/platform prompts.")}
              <Badge tone="slate">v{selected.prompt_version}</Badge>
              {selected.override ? <Badge tone="gold">{t("已覆盖", "Overridden")}</Badge> : null}
              <span className="ml-auto text-[10px]">{session.role_label_cn}</span>
            </div>

            <label className="mt-4 block text-xs font-medium text-[#505369]">
              {t("提示词", "Prompt")}
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={!canEdit || !selected.editable || busy}
                className="mt-1 min-h-[260px] w-full rounded-xl border border-[#dde5f2] bg-white p-3 font-mono text-xs leading-relaxed text-[#505369] outline-none focus:border-[#7950ba] disabled:bg-[#f8faff]"
              />
            </label>
            <p className="mt-1 text-[10px] leading-relaxed text-[#77718c]">
              {t(
                "系统仍强制 JSON 校验、50 字摘要、证据引用、hash 绑定与审批门禁；提示词不能关闭这些规则。",
                "JSON validation, 50-character summaries, evidence citations, hash binding and approval gates remain enforced.",
              )}
            </p>

            {canEdit && selected.editable ? (
              <label className="mt-3 block text-xs font-medium text-[#505369]">
                {t("变更说明（可选）", "Change note (optional)")}
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#dde5f2] px-3 py-2 text-sm outline-none focus:border-[#7950ba]"
                  placeholder={t("例如：加强反证要求", "e.g. strengthen falsifiers")}
                />
              </label>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2">
              {canEdit && selected.editable ? (
                <>
                  <Button variant="gold" disabled={busy || !draft.trim()} onClick={() => void save()}>
                    <Save className="mr-1 h-4 w-4" />
                    {busy ? t("保存中…", "Saving…") : t("保存提示词", "Save prompt")}
                  </Button>
                  <Button variant="ghost" disabled={busy} onClick={() => void reset()}>
                    <RotateCcw className="mr-1 h-4 w-4" /> {t("恢复默认", "Reset")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      void instApi<{ items: PromptHistory[] }>(
                        `/agents/${encodeURIComponent(selected.task_id)}/prompt/history`,
                      )
                        .then((res) => setHistory(res.items || []))
                        .catch((e: Error) => setError(e.message));
                    }}
                  >
                    <History className="mr-1 h-4 w-4" /> {t("版本历史", "History")}
                  </Button>
                </>
              ) : null}
            </div>

            {history.length ? (
              <div className="mt-4 max-h-60 overflow-y-auto rounded-xl border border-[#e3eaf8]">
                <table className="w-full text-left text-[11px]">
                  <thead className="bg-[#f8faff] text-[#77718c]">
                    <tr>
                      <th className="px-3 py-2">{t("版本", "Version")}</th>
                      <th className="px-3 py-2">{t("动作", "Action")}</th>
                      <th className="px-3 py-2">{t("状态", "Status")}</th>
                      <th className="px-3 py-2">{t("时间", "Time")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((row) => (
                      <tr key={row.id} className="border-t border-[#eef1f8]">
                        <td className="px-3 py-2">v{row.version_no}</td>
                        <td className="px-3 py-2">{row.action === "reset" ? t("恢复默认", "Reset") : t("保存", "Save")}</td>
                        <td className="px-3 py-2">{row.status === "active" ? t("生效中", "Active") : t("已归档", "Archived")}</td>
                        <td className="px-3 py-2 text-[#77718c]">{row.created_at?.slice(0, 19).replace("T", " ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </Card>
  );
}
