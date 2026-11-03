import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronUp, Mic, MicOff, Send, Sparkles } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, PageHeader, Sparkline, Tag } from "../components";

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

type Template = { id: string; label: string; text: string };

const TEMPLATES: Template[] = [
  { id: "stock", label: "个股解读", text: "分析 [标的] 的基本面、估值和主要风险" },
  { id: "debate", label: "多空分析", text: "看多和看空 [标的] 的主要依据分别是什么" },
  { id: "compare", label: "多标的对比", text: "对比 [标的A] 和 [标的B] 的估值与财务" },
  { id: "portfolio", label: "组合诊断", text: "我的组合风险主要在哪里" },
  { id: "condition", label: "条件选股", text: "帮我找 [条件] 的股票" },
  { id: "announcement", label: "公告解读", text: "解读公告：[标题]" },
  { id: "review", label: "每日复盘", text: "今天复盘" },
  { id: "allocation", label: "配置/定投", text: "我计划 [期限]、风险偏好 [风险偏好]，如何理解当前配置和定投节奏" },
  { id: "glossary", label: "术语解释", text: "什么是 [术语]" },
];

const ORDER_KEY = "svq_ai_template_order";
const MEMORY_KEY = "svq_ai_memory";
const QUICK = ["今天复盘", "我的组合风险", "贵州茅台多空", "宁德时代和比亚迪对比", "我计划 3 年以上、稳健型，每月定投多少合适"];

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
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

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
    if (!q || busy) return;
    // 会话记忆：只在用户明显使用指代时补上上一标的
    if (/(它|这只|那只|这个票|那个票)/.test(q) && memory.lastStock && !q.includes(memory.lastStock.code)) {
      q = `上一标的：${memory.lastStock.name || ""}(${memory.lastStock.code})。问题：${q}`;
    }
    setInput("");
    setError(null);
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    try {
      const data = await api<any>(deep ? "/api/invest/ai/deep" : "/api/invest/ai/chat", {
        method: "POST",
        body: JSON.stringify({ query: q }),
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          text: data.need_clarify?.length ? `还需要：${data.need_clarify.join("、")}` : undefined,
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
      setError(e.message || "AI 请求失败");
    } finally {
      setBusy(false);
    }
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
        stream.getTracks().forEach((t) => t.stop());
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
              setMessages((prev) => [...prev, { role: "ai", text: `语音已转写。可确认：${fixes.map((f: any) => `${f.from} → ${f.to}`).join("；")}` }]);
            }
          } catch (e: any) {
            setError(e.message || "语音识别失败");
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
      setError(e.message || "无法访问麦克风");
    }
  };

  return (
    <div className="page ai-chat-page">
      <PageHeader title="AI 管家" sub="听懂问题、分发到个股/组合/量化能力；只解释数据，不构成投资建议" back onBack={() => nav(-1)} />

      <div className="ai-template-bar">
        {templates.slice(0, 6).map((t) => (
          <button key={t.id} className="chip" onClick={() => fill(t.text)}>{t.label}</button>
        ))}
        <button className="chip chip-more" onClick={() => setPanel((v) => !v)}>
          全部 {panel ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
      {panel ? (
        <section className="card ai-template-panel">
          <div className="card-title-row"><h2>快捷功能</h2><span className="hint">顺序会保存到本机</span></div>
          {templates.map((t, i) => (
            <div key={t.id} className="template-row">
              <button className="template-fill" onClick={() => fill(t.text)}>{t.label}</button>
              <div className="template-actions">
                <button aria-label="上移" disabled={i === 0} onClick={() => move(i, -1)}><ChevronUp size={14} /></button>
                <button aria-label="下移" disabled={i === templates.length - 1} onClick={() => move(i, 1)}><ChevronDown size={14} /></button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {!messages.length && !panel ? (
        <section className="card">
          <div className="card-title-row">
            <h2 className="row gap6"><Sparkles size={15} /> 可以这样问</h2>
            <Tag tone="blue">EOD 数据</Tag>
          </div>
          <div className="post-list">
            {QUICK.map((q) => (
              <button key={q} className="post-row" type="button" style={{ textAlign: "left" }} onClick={() => void send(q)}>
                <div className="post-row-title">{q}</div>
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
                {m.intent ? <div className="ai-msg-meta"><Tag tone={m.blocked ? "red" : "gray"}>{m.blocked ? "已拦截" : m.intent}</Tag></div> : null}
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
                      <ul>{s.items.map((it, k) => <li key={k}>{it.k ? <span>{it.k}：</span> : null}{it.v}</li>)}</ul>
                    ) : null}
                  </div>
                ))}
                {m.evidence?.length ? (
                  <div className="ai-section">
                    <b>证据链</b>
                    <ul>{m.evidence.slice(0, 4).map((ev, k) => <li key={k}>{ev.title}：{ev.detail}</li>)}</ul>
                  </div>
                ) : null}
                {m.chart?.bars?.length ? (
                  <div className="ai-chart">
                    <Sparkline values={m.chart.bars.map((b) => Number(b.close || 0))} width={220} height={44} />
                    <span className="hint">{m.chart.code} · 近 {m.chart.bars.length} 个交易日</span>
                  </div>
                ) : null}
                {m.card?.disclaimer ? <p className="hint">{m.card.disclaimer}</p> : null}
              </>
            ) : null}
          </div>
        ))}
        {busy ? <div className="ai-msg ai"><p className="hint">{deep ? "深度模式：取数 → 分析 → 护栏 → 汇总…" : "正在基于收盘数据生成…"}</p></div> : null}
      </div>

      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}

      <div className="ai-composer">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
          placeholder={recording ? "录音中，点麦克风结束…" : "问个股、组合、复盘或条件选股"}
        />
        <div className="ai-composer-actions">
          <button className={`round-btn ${recording ? "recording" : ""}`} onClick={() => void toggleRecord()} aria-label={recording ? "停止录音" : "语音输入"}>
            {recording ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <button className={`chip ${deep ? "on" : ""}`} onClick={() => setDeep((v) => !v)} title="深度思考">
            深度
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => void send()} disabled={busy || !input.trim()}>
            <Send size={15} /> 发送
          </button>
        </div>
      </div>
      {memory.lastStock ? (
        <p className="hint">会话记忆：上一标的 {memory.lastStock.name || memory.lastStock.code}（可在「我的」清除）</p>
      ) : null}
      <Disclaimer>AI 生成内容仅作研究辅助；不提供买卖点、目标价、收益承诺。</Disclaimer>
      <button className="btn btn-ghost btn-sm" onClick={() => nav(-1)} style={{ marginTop: 8 }}>
        <ArrowLeft size={14} /> 返回
      </button>
    </div>
  );
}
