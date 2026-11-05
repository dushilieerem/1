import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Lock, RotateCcw, Save } from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

type Agent = {
  task_id: string;
  name: string;
  name_en: string;
  description: string;
  description_en: string;
  default_prompt: string;
  prompt: string;
  custom_prompt: string | null;
  is_custom: boolean;
  can_reset: boolean;
  editable: boolean;
  available: boolean;
};

export default function Agents() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [items, setItems] = useState<Agent[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    api<{ items: Agent[] }>("/api/invest/agents")
      .then((d) => {
        setItems(d.items || []);
        setDrafts(Object.fromEntries((d.items || []).map((a) => [a.task_id, a.prompt])));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const editable = useMemo(() => items.filter((a) => a.editable), [items]);

  const save = async (agent: Agent, prompt = drafts[agent.task_id] ?? agent.prompt) => {
    setSaving(agent.task_id);
    setNotice(null);
    try {
      const data = await api<any>(`/api/invest/agents/${encodeURIComponent(agent.task_id)}`, {
        method: "PUT",
        body: JSON.stringify({ prompt }),
      });
      setItems((prev) => prev.map((a) => (a.task_id === agent.task_id ? { ...a, prompt: data.prompt, custom_prompt: data.custom ? data.prompt : null, is_custom: !!data.custom, can_reset: !!data.custom } : a)));
      setDrafts((prev) => ({ ...prev, [agent.task_id]: data.prompt }));
      setNotice(t("已保存，下一次生成会使用新提示词", "Saved; the next generation will use this prompt"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(null);
    }
  };

  const reset = (agent: Agent) => save(agent, "");

  return (
    <div className="page">
      <PageHeader
        title={t("Agent 管理", "Agent management")}
        sub={t("管理 H5 内的 AI Agent 提示词 · 按你的账号生效", "Manage prompts for H5 AI agents · applied to your account")}
        back
        onBack={() => nav("/me")}
      />
      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {notice ? <button className="quant-notice" onClick={() => setNotice(null)}>{notice} ×</button> : null}

      <div className="callout blue">
        <Bot size={15} />
        <span>{t("提示词只改变解释口径，不改变合规边界；AI 输出限制 50 字，自动生成并落盘缓存。", "Prompts only change the explanation style, not compliance boundaries. AI output is capped at 50 characters, generated automatically and cached on disk.")}</span>
      </div>

      <div className="agent-list">
        {items.map((agent) => {
          const value = drafts[agent.task_id] ?? agent.prompt;
          const changed = value !== agent.prompt;
          return (
            <section className="card agent-card" key={agent.task_id}>
              <div className="card-title-row">
                <h2 className="row gap6">
                  <Bot size={15} /> {locale === "en" ? agent.name_en : agent.name}
                </h2>
                <div className="row gap6">
                  {agent.is_custom ? <Tag tone="blue">{t("已自定义", "Custom")}</Tag> : <Tag tone="gray">{t("默认", "Default")}</Tag>}
                  <Tag tone={agent.available ? "green" : "amber"}>{agent.available ? t("可用", "Ready") : t("未配置", "Not configured")}</Tag>
                </div>
              </div>
              <p className="hint">{locale === "en" ? agent.description_en : agent.description}</p>
              <p className="hint">task_id · {agent.task_id}</p>
              {agent.editable ? (
                <>
                  <textarea
                    className="agent-prompt"
                    value={value}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [agent.task_id]: e.target.value }))}
                    rows={6}
                    spellCheck={false}
                  />
                  <div className="row gap6 agent-actions">
                    <button className="btn btn-primary btn-sm" disabled={!changed || saving === agent.task_id} onClick={() => void save(agent)}>
                      <Save size={14} /> {saving === agent.task_id ? t("保存中…", "Saving…") : t("保存", "Save")}
                    </button>
                    <button className="btn btn-ghost btn-sm" disabled={!agent.can_reset || saving === agent.task_id} onClick={() => void reset(agent)}>
                      <RotateCcw size={14} /> {t("恢复默认", "Reset")}
                    </button>
                  </div>
                </>
              ) : (
                <div className="agent-locked">
                  <Lock size={14} />
                  <span>{t("该 Agent 用于结构化解析，提示词锁定。", "This agent is a structured parser; its prompt is locked.")}</span>
                </div>
              )}
            </section>
          );
        })}
      </div>
      {!loading && !editable.length ? <p className="hint">{t("暂无可编辑 Agent。", "No editable agents.")}</p> : null}
    </div>
  );
}
