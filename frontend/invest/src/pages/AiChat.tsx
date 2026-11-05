import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronUp, Mic, MicOff, Send, SlidersHorizontal, Sparkles } from "lucide-react";
import { api } from "../api";
import { ErrorState, PageHeader, Sparkline, Tag } from "../components";
import { ConditionPicker, ConditionScreener, looksLikeCondition, type ConditionResponse, type RelaxAction } from "../components/ConditionScreener";
import { useLocale } from "../i18n";

type Section = { key?: string; title?: string; body?: string; type?: string; items?: Array<{ k?: string; v?: string }> };
type Card = { summary?: string; sections?: Section[]; disclaimer?: string; meta?: { dataSource?: string } };
type Chart = { code?: string; bars?: Array<{ date?: string; close?: number }> };
type Step = { key: string; label: string; status: string; detail?: string };
type Msg = {
  role: "user" | "ai";
  text?: string;
  card?: Card;
  chart?: Chart;
  intent?: string;
  need?: string[];
  blocked?: boolean;
  steps?: Step[];
  evidence?: Array<{ title?: string; detail?: string }>;
};

type Template = { id: string; label: { zh: string; en: string }; text: { zh: string; en: string } };

const TEMPLATES: Template[] = [
  { id: "stock", label: { zh: "个股解读", en: "Stock analysis" }, text: { zh: "分析 [标的] 的基本面、估值和主要风险", en: "Analyze the fundamentals, valuation and main risks of [ticker]" } },
  { id: "debate", label: { zh: "多空分析", en: "Bull vs bear" }, text: { zh: "看多和看空 [标的] 的主要依据分别是什么", en: "What are the main bull and bear cases for [ticker]?" } },
  { id: "compare", label: { zh: "多标的对比", en: "Compare stocks" }, text: { zh: "对比 [标的A] 和 [标的B] 的估值与财务", en: "Compare the valuation and financials of [ticker A] and [ticker B]" } },
  { id: "portfolio", label: { zh: "组合诊断", en: "Portfolio checkup" }, text: { zh: "我的组合风险主要在哪里", en: "Where is the main risk in my portfolio?" } },
  { id: "condition", label: { zh: "条件选股", en: "Screen stocks" }, text: { zh: "帮我找 [条件] 的股票", en: "Find me stocks matching [criteria]" } },
  { id: "announcement", label: { zh: "公告解读", en: "Filing analysis" }, text: { zh: "解读公告：[标题]", en: "Explain this filing: [title]" } },
  { id: "review", label: { zh: "每日复盘", en: "Daily review" }, text: { zh: "今天复盘", en: "Review today's market" } },
  { id: "allocation", label: { zh: "配置/定投", en: "Allocation / DCA" }, text: { zh: "我计划 [期限]、风险偏好 [风险偏好]，如何理解当前配置和定投节奏", en: "My horizon is [horizon] and my risk appetite is [risk appetite]; how should I think about my allocation and DCA pace?" } },
  { id: "glossary", label: { zh: "术语解释", en: "Explain a term" }, text: { zh: "什么是 [术语]", en: "What is [term]?" } },
];

const ORDER_KEY = "svq_ai_template_order";
const MEMORY_KEY = "svq_ai_memory";
const QUICK: Array<{ zh: string; en: string }> = [
  { zh: "今天复盘", en: "Review today's market" },
  { zh: "我的组合风险", en: "Risks in my portfolio" },
  { zh: "贵州茅台多空", en: "Kweichow Moutai bull vs bear" },
  { zh: "宁德时代和比亚迪对比", en: "CATL vs BYD comparison" },
  { zh: "我计划 3 年以上、稳健型，每月定投多少合适", en: "I have a 3+ year horizon and a conservative profile; how much should I invest monthly?" },
];

function loadOrder(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]");
    const known = TEMPLATES.map((x) => x.id);
    const saved = Array.isArray(raw) ? raw.filter((x) => known.includes(x)) : [];
    return [...saved, ...known.filter((x) => !saved.includes(x))];
  } catch {
    return TEMPLATES.map((x) => x.id);
  }
}

function loadMemory(): { lastStock?: { code: string; name?: string } } {
  try {
    return JSON.parse(localStorage.getItem(MEMORY_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveMemory(next: { lastStock?: { code: string; name?: string } }) {
  try {
    localStorage.setItem(MEMORY_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}

function splitSections(card?: Card) {
  return (card?.sections || []).filter((s) => s.title || s.body || s.items?.length);
}

export default function AiChat() {
  const { t } = useLocale();
  const nav = useNavigate();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [deep, setDeep] = useState(false);
  const [panel, setPanel] = useState(false);
  const [order, setOrder] = useState<string[]>(loadOrder);
  const [memory, setMemory] = useState(loadMemory);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [conditionMode, setConditionMode] = useState(false);
  const [conditionQuery, setConditionQuery] = useState("");
  const [condition, setCondition] = useState<ConditionResponse | null>(null);
  const [conditionBusy, setConditionBusy] = useState(false);
  const [addedCodes, setAddedCodes] = useState<Set<string>>(new Set());
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [input]);

  const choosePreset = (text: string) => {
    setInput(text);
    setPickerOpen(false);
    setPanel(false);
    setConditionMode(true);
    setCondition(null);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const runCondition = async (body: Record<string, unknown>) => {
    setError(null);
    try {
      const data = await api<ConditionResponse>("/api/invest/condition/screen", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setCondition(data);
      if (typeof body.query === "string") setConditionQuery(body.query);
    } catch (e: any) {
      setError(e?.message || t("条件筛选失败", "Screening failed"));
    }
  };

  const removeCondition = async (key: string) => {
    const current = condition?.conditions || condition?.parsed?.conditions || [];
    const remaining = current.filter((c) => c.key !== key);
    if (!remaining.length) {
      setCondition(null);
      return;
    }
    const text = remaining.map((c) => c.text || c.label).join("，");
    setInput(text);
    setConditionBusy(true);
    try {
      await runCondition({ conditions: remaining });
    } finally {
      setConditionBusy(false);
    }
  };

  const relaxCondition = async (action: RelaxAction) => {
    const current = condition?.conditions || condition?.parsed?.conditions || [];
    if (action.type === "remove") {
      if (action.key) await removeCondition(action.key);
      return;
    }
    if (action.type === "widen" && action.key) {
      const next = current.map((c) => (c.key === action.key ? { ...c, value: action.value } : c));
      setInput(next.map((c) => c.text || c.label).join("，"));
      setConditionBusy(true);
      try {
        await runCondition({ conditions: next });
      } finally {
        setConditionBusy(false);
      }
      return;
    }
    const nextQuery = action.type === "add" && action.query
      ? `${conditionQuery || (condition?.query || "")}，${action.query}`
      : action.query || "";
    setInput(nextQuery);
    setConditionMode(true);
    setCondition(null);
    if (action.type === "add" && nextQuery) {
      setConditionBusy(true);
      try {
        await runCondition({ query: nextQuery });
      } finally {
        setConditionBusy(false);
      }
    } else {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  const addToWatchlist = async (code: string) => {
    try {
      await api("/api/invest/watchlist", {
        method: "POST",
        body: JSON.stringify({ code, group: "条件选股" }),
      });
      setAddedCodes((prev) => new Set(prev).add(code));
    } catch (e: any) {
      setError(e?.message || t("加入自选失败", "Failed to add to watchlist"));
    }
  };

  const saveConditionGroup = async (codes: string[], group: string) => {
    const res = await api<{ added: number }>("/api/invest/condition/watchlist", {
      method: "POST",
      body: JSON.stringify({ codes, group }),
    });
    setAddedCodes((prev) => {
      const next = new Set(prev);
      codes.forEach((code) => next.add(code));
      return next;
    });
    return { added: Number(res?.added || 0) };
  };

  const templates = useMemo(() => order.map((id) => TEMPLATES.find((x) => x.id === id)).filter(Boolean) as Template[], [order]);

  const persistOrder = (next: string[]) => {
    setOrder(next);
    try {
      localStorage.setItem(ORDER_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  const move = (index: number, delta: number) => {
    const next = [...order];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    persistOrder(next);
  };

  const fill = (text: string) => {
    setInput(text);
    setPanel(false);
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      const start = text.indexOf("[");
      const end = text.indexOf("]", start + 1);
      if (start >= 0 && end > start) {
        el.focus();
        el.setSelectionRange(start + 1, end);
      }
    });
  };

  const send = async (text?: string) => {
    let q = (text ?? input).trim();
    if (!q || busy || conditionBusy) return;
    // 会话记忆：只在用户明显使用指代时补上上一标的
    if (/(它|这只|那只|这个票|那个票)/.test(q) && memory.lastStock && !q.includes(memory.lastStock.code)) {
      q = `上一标的：${memory.lastStock.name || ""}(${memory.lastStock.code})。问题：${q}`;
    }
    const conditionTurn = conditionMode || looksLikeCondition(q);
    setInput("");
    setError(null);
    setConditionMode(false);
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    if (conditionTurn) {
      setConditionBusy(true);
      try {
        await runCondition({ query: q });
      } finally {
        setConditionBusy(false);
      }
      return;
    }
    setCondition(null);
    setBusy(true);
    try {
      const data = await api<any>(deep ? "/api/invest/ai/deep" : "/api/invest/ai/chat", {
        method: "POST",
        body: JSON.stringify({ query: q }),
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          text: data.need_clarify?.length ? t(`还需要：${data.need_clarify.join("、")}`, `Also needed: ${data.need_clarify.join(", ")}`) : undefined,
          card: data.card,
          chart: data.chart,
          intent: data.intent,
          need: data.need_clarify,
          blocked: data.blocked,
          steps: data.steps,
          evidence: data.evidence,
        },
      ]);
      if (data.chart?.code) {
        const next = { lastStock: { code: data.chart.code, name: data.card?.sections?.[0]?.title } };
        setMemory(next);
        saveMemory(next);
      }
    } catch (e: any) {
      setError(e.message || t("AI 请求失败", "AI request failed"));
    } finally {
      setBusy(false);
    }
  };

  const clearMemory = () => {
    setMemory({});
    saveMemory({});
  };

  const toggleRecord = async () => {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (ev) => {
        if (ev.data.size) chunks.current.push(ev.data);
      };
      mr.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        const blob = new Blob(chunks.current, { type: mr.mimeType || "audio/webm" });
        if (!blob.size) return;
        const reader = new FileReader();
        reader.onload = async () => {
          const b64 = String(reader.result || "").split(",", 2)[1] || "";
          setBusy(true);
          try {
            const data = await api<any>("/api/invest/ai/voice", {
              method: "POST",
              body: JSON.stringify({ audio_base64: b64, mime: blob.type }),
            });
            const text = data.corrected?.text || data.asr?.text || "";
            setInput(text);
            const fixes = data.corrected?.corrections || [];
            if (fixes.length) {
              setMessages((prev) => [...prev, { role: "ai", text: t(`语音已转写。可确认：${fixes.map((f: any) => `${f.from} → ${f.to}`).join("；")}`, `Voice transcribed. Please confirm: ${fixes.map((f: any) => `${f.from} → ${f.to}`).join("; ")}`) }]);
            }
          } catch (e: any) {
            setError(e.message || t("语音识别失败", "Speech recognition failed"));
          } finally {
            setBusy(false);
          }
        };
        reader.readAsDataURL(blob);
      };
      recorder.current = mr;
      mr.start();
      setRecording(true);
    } catch (e: any) {
      setError(e.message || t("无法访问麦克风", "Cannot access the microphone"));
    }
  };

  return (
    <div className="page ai-chat-page">
      <PageHeader title={t("AI 管家", "AI Assistant")} sub={t("听懂问题、分发到个股/组合/量化/条件选股能力；只解释数据，不构成投资建议", "Understands your question and routes it to stock, portfolio, quant or screening capabilities; it only explains data and is not investment advice")} back onBack={() => nav(-1)} />

      {!messages.length && !panel ? (
        <section className="card">
          <div className="card-title-row">
            <h2 className="row gap6"><Sparkles size={15} /> {t("可以这样问", "Try asking")}</h2>
            <Tag tone="blue">{t("EOD 数据", "EOD data")}</Tag>
          </div>
          <div className="post-list">
            {QUICK.map((q) => (
              <button key={q.zh} className="post-row" type="button" style={{ textAlign: "left" }} onClick={() => void send(t(q.zh, q.en))}>
                <div className="post-row-title">{t(q.zh, q.en)}</div>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="ai-chat-list">
        {messages.map((m, i) => (
          <div key={i} className={`ai-msg ${m.role}`}>
            {m.role === "user" ? <p>{m.text}</p> : null}
            {m.role === "ai" ? (
              <>
                {m.intent ? <div className="ai-msg-meta"><Tag tone={m.blocked ? "red" : "gray"}>{m.blocked ? t("已拦截", "Blocked") : m.intent}</Tag></div> : null}
                {m.steps?.length ? (
                  <div className="deep-steps">
                    {m.steps.map((step) => (
                      <div key={step.key} className={`deep-step ${step.status}`}>
                        <span className="deep-dot" />
                        <div><b>{step.label}</b>{step.detail ? <p>{step.detail}</p> : null}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {m.text ? <p className="hint">{m.text}</p> : null}
                {m.card?.summary ? <p className="ai-summary">{m.card.summary}</p> : null}
                {splitSections(m.card).map((s, j) => (
                  <div key={j} className="ai-section">
                    {s.title ? <b>{s.title}</b> : null}
                    {s.body ? <p>{s.body}</p> : null}
                    {s.items?.length ? (
                      <ul>{s.items.map((it, k) => <li key={k}>{it.k ? <span>{it.k}{t("：", ": ")}</span> : null}{it.v}</li>)}</ul>
                    ) : null}
                  </div>
                ))}
                {m.evidence?.length ? (
                  <div className="ai-section">
                    <b>{t("证据链", "Evidence chain")}</b>
                    <ul>{m.evidence.slice(0, 4).map((ev, k) => <li key={k}>{ev.title}{t("：", ": ")}{ev.detail}</li>)}</ul>
                  </div>
                ) : null}
                {m.chart?.bars?.length ? (
                  <div className="ai-chart">
                    <Sparkline values={m.chart.bars.map((b) => Number(b.close || 0))} width={220} height={44} />
                    <span className="hint">{m.chart.code} · {t("近", "Last")} {m.chart.bars.length} {t("个交易日", "trading days")}</span>
                  </div>
                ) : null}
                {m.card?.disclaimer ? <p className="hint">{m.card.disclaimer}</p> : null}
              </>
            ) : null}
          </div>
        ))}
        {condition ? (
          <ConditionScreener
            data={condition}
            busy={busy || conditionBusy}
            addedCodes={addedCodes}
            onRemoveCondition={(key) => void removeCondition(key)}
            onRelax={(action) => void relaxCondition(action)}
            onAdd={(code) => void addToWatchlist(code)}
            onSaveGroup={saveConditionGroup}
            onFollowup={(text) => { setInput(text); requestAnimationFrame(() => inputRef.current?.focus()); }}
            onOpenStock={(code) => nav(`/stock/${code}`)}
          />
        ) : null}
        {conditionBusy ? <div className="ai-msg ai"><p className="hint">{t("正在解析条件并筛选…", "Parsing conditions and screening…")}</p></div> : null}
        {busy ? <div className="ai-msg ai"><p className="hint">{deep ? t("深度模式：取数 → 分析 → 护栏 → 汇总…", "Deep mode: fetch data → analyze → guardrails → summarize…") : t("正在基于收盘数据生成…", "Generating from closing data…")}</p></div> : null}
      </div>

      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}

      <div className="ai-template-bar">
        <button
          className={`chip condition-trigger ${pickerOpen ? "on" : ""}`}
          aria-label={t("打开条件选股", "Open stock screener")}
          onClick={() => { setPickerOpen((v) => !v); setPanel(false); }}
        >
          <SlidersHorizontal size={12} /> {t("条件选股", "Screen")}
        </button>
        <div className="ai-template-scroll">
          {templates.slice(0, 4).map((tpl) => (
            <button key={tpl.id} className="chip" onClick={() => (tpl.id === "condition" ? setPickerOpen(true) : fill(t(tpl.text.zh, tpl.text.en)))}>{t(tpl.label.zh, tpl.label.en)}</button>
          ))}
        </div>
        <button className="chip chip-more" onClick={() => setPanel((v) => !v)}>
          {t("全部", "All")} {panel ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
      {panel ? (
        <section className="card ai-template-panel">
          <div className="card-title-row"><h2>{t("快捷功能", "Quick actions")}</h2><span className="hint">{t("顺序会保存到本机", "Order is saved on this device")}</span></div>
          {templates.map((tpl, i) => (
            <div key={tpl.id} className="template-row">
              <button className="template-fill" onClick={() => (tpl.id === "condition" ? (setPickerOpen(true), setPanel(false)) : fill(t(tpl.text.zh, tpl.text.en)))}>{t(tpl.label.zh, tpl.label.en)}</button>
              <div className="template-actions">
                <button aria-label={t("上移", "Move up")} disabled={i === 0} onClick={() => move(i, -1)}><ChevronUp size={14} /></button>
                <button aria-label={t("下移", "Move down")} disabled={i === templates.length - 1} onClick={() => move(i, 1)}><ChevronDown size={14} /></button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {pickerOpen ? <ConditionPicker onSelect={choosePreset} onClose={() => setPickerOpen(false)} /> : null}

      <div className="ai-composer">
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder={recording ? t("录音中，点麦克风结束…", "Recording — tap the microphone to stop…") : t("问个股、组合、复盘或条件选股", "Ask about stocks, your portfolio, reviews or screening")}
        />
        <div className="ai-composer-actions">
          <button className={`round-btn ${recording ? "recording" : ""}`} onClick={() => void toggleRecord()} aria-label={recording ? t("停止录音", "Stop recording") : t("语音输入", "Voice input")}>
            {recording ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <button className={`chip ${deep ? "on" : ""}`} onClick={() => setDeep((v) => !v)} title={t("深度思考", "Deep thinking")}>
            {t("深度", "Deep")}
          </button>
          <button
            className={`chip ${memory.lastStock ? "on" : ""}`}
            onClick={clearMemory}
            disabled={!memory.lastStock}
            title={memory.lastStock ? t(`清除会话记忆：${memory.lastStock.name || memory.lastStock.code}`, `Clear session memory: ${memory.lastStock.name || memory.lastStock.code}`) : t("暂无会话记忆", "No session memory")}
          >
            {t("记忆", "Memory")}
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => void send()} disabled={busy || conditionBusy || !input.trim()}>
            <Send size={15} /> {t("发送", "Send")}
          </button>
        </div>
      </div>
    </div>
  );
}
