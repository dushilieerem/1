import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Mic, MicOff, Send, Sparkles } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, PageHeader, Sparkline, Tag } from "../components";

type Section = { key?: string; title?: string; body?: string; type?: string; items?: Array<{ k?: string; v?: string }> };
type Card = { summary?: string; sections?: Section[]; disclaimer?: string; meta?: { dataSource?: string } };
type Chart = { code?: string; bars?: Array<{ date?: string; close?: number }> };
type Msg = {
  role: "user" | "ai";
  text?: string;
  card?: Card;
  chart?: Chart;
  intent?: string;
  need?: string[];
  blocked?: boolean;
};

const QUICK = ["今天复盘", "我的组合风险", "贵州茅台多空", "宁德时代和比亚迪对比", "帮我找 PE 低、股息高的股票"];

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
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const send = async (text?: string) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    try {
      const data = await api<any>("/api/invest/ai/chat", {
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
        },
      ]);
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
              setMessages((prev) => [
                ...prev,
                {
                  role: "ai",
                  text: `语音已转写。可确认：${fixes.map((f: any) => `${f.from} → ${f.to}`).join("；")}`,
                },
              ]);
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

      {!messages.length ? (
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
                {m.text ? <p className="hint">{m.text}</p> : null}
                {m.card?.summary ? <p className="ai-summary">{m.card.summary}</p> : null}
                {splitSections(m.card).map((s, j) => (
                  <div key={j} className="ai-section">
                    {s.title ? <b>{s.title}</b> : null}
                    {s.body ? <p>{s.body}</p> : null}
                    {s.items?.length ? (
                      <ul>
                        {s.items.map((it, k) => (
                          <li key={k}>
                            {it.k ? <span>{it.k}：</span> : null}
                            {it.v}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ))}
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
        {busy ? <div className="ai-msg ai"><p className="hint">正在基于收盘数据生成…</p></div> : null}
      </div>

      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}

      <div className="ai-composer">
        <button className={`round-btn ${recording ? "recording" : ""}`} onClick={() => void toggleRecord()} aria-label={recording ? "停止录音" : "语音输入"}>
          {recording ? <MicOff size={18} /> : <Mic size={18} />}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
          placeholder={recording ? "录音中，点麦克风结束…" : "问个股、组合、复盘或条件选股"}
        />
        <button className="btn btn-primary btn-sm" onClick={() => void send()} disabled={busy || !input.trim()}>
          <Send size={15} /> 发送
        </button>
      </div>
      <Disclaimer>AI 生成内容仅作研究辅助；不提供买卖点、目标价、收益承诺。</Disclaimer>
      <button className="btn btn-ghost btn-sm" onClick={() => nav(-1)} style={{ marginTop: 8 }}>
        <ArrowLeft size={14} /> 返回
      </button>
    </div>
  );
}
