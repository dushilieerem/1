import { useEffect, useState } from "react";
import { LifeBuoy, Send } from "lucide-react";
import { authHeaders } from "@/lib/auth";

type Ticket = {
  id: number;
  category: string;
  subject: string;
  body: string;
  status: string;
  priority?: string;
  created_at?: string;
  updated_at?: string;
  replies?: Array<{ id: number; author_type: string; body: string; created_at?: string }>;
};

const CATEGORIES: Array<[string, string]> = [
  ["account", "账号与登录"],
  ["data", "行情与数据"],
  ["ai", "AI 功能"],
  ["community", "社区"],
  ["billing", "付费与发票"],
  ["other", "其他"],
];

const STATUS: Record<string, string> = {
  open: "待处理",
  in_progress: "处理中",
  closed: "已关闭",
};

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string })?.detail || `HTTP ${res.status}`);
  return data as T;
}

export default function SupportPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [category, setCategory] = useState("account");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await call<{ items: Ticket[] }>("/api/support/tickets");
      setTickets(data.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const open = async (id: number) => {
    try {
      const data = await call<{ ticket: Ticket }>(`/api/support/tickets/${id}`);
      setSelected(data.ticket);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await call("/api/support/tickets", {
        method: "POST",
        body: JSON.stringify({ category, subject, body }),
      });
      setSubject("");
      setBody("");
      setMessage("工单已提交，我们会尽快回复。");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sendReply = async () => {
    if (!selected || !reply.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await call<{ ticket: Ticket }>(
        `/api/support/tickets/${selected.id}/replies`,
        { method: "POST", body: JSON.stringify({ body: reply }) },
      );
      setSelected(data.ticket);
      setReply("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-8">
      <header>
        <p className="text-[11px] tracking-[0.18em] text-red-600">SUPPORT</p>
        <h1 className="mt-1 flex items-center gap-2 font-display text-2xl font-semibold text-slate-900">
          <LifeBuoy className="h-6 w-6 text-red-500" /> 客服与工单
        </h1>
        <p className="mt-1 text-sm text-slate-500">提交问题后会生成工单；回复和状态变化会保留在工单里。</p>
      </header>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div> : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-800">新建工单</h2>
          <div className="mt-3 space-y-3">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              {CATEGORIES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={120}
              placeholder="问题标题（2–120 字）"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-red-400"
            />
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={5000}
              placeholder="描述问题、复现步骤与期望结果"
              className="min-h-[140px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-red-400"
            />
            <button
              type="button"
              disabled={busy || subject.trim().length < 2 || !body.trim()}
              onClick={() => void submit()}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
            >
              <Send className="h-4 w-4" /> {busy ? "提交中…" : "提交工单"}
            </button>
          </div>

          <h2 className="mt-6 text-sm font-semibold text-slate-800">我的工单</h2>
          {tickets.length ? (
            <ul className="mt-2 divide-y divide-slate-100">
              {tickets.map((ticket) => (
                <li key={ticket.id}>
                  <button
                    type="button"
                    onClick={() => void open(ticket.id)}
                    className="flex w-full items-center justify-between gap-2 py-2.5 text-left text-sm hover:text-red-600"
                  >
                    <span className="truncate">{ticket.subject}</span>
                    <span className="shrink-0 text-[11px] text-slate-400">
                      {STATUS[ticket.status] || ticket.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-slate-400">还没有工单。</p>
          )}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          {selected ? (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-800">{selected.subject}</h2>
                  <p className="mt-1 text-[11px] text-slate-400">
                    #{selected.id} · {STATUS[selected.status] || selected.status} · {selected.created_at}
                  </p>
                </div>
                <button type="button" onClick={() => setSelected(null)} className="text-xs text-slate-400 hover:text-slate-600">
                  关闭
                </button>
              </div>
              <p className="mt-3 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{selected.body}</p>
              <ul className="mt-3 space-y-2">
                {(selected.replies || []).map((item) => (
                  <li
                    key={item.id}
                    className={`rounded-xl p-3 text-sm ${
                      item.author_type === "admin" ? "bg-red-50 text-red-800" : "bg-slate-50 text-slate-700"
                    }`}
                  >
                    <p className="text-[10px] text-slate-400">
                      {item.author_type === "admin" ? "客服" : "我"} · {item.created_at}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap">{item.body}</p>
                  </li>
                ))}
              </ul>
              {selected.status !== "closed" ? (
                <div className="mt-4 space-y-2">
                  <textarea
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    maxLength={5000}
                    placeholder="补充说明…"
                    className="min-h-[90px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-red-400"
                  />
                  <button
                    type="button"
                    disabled={busy || !reply.trim()}
                    onClick={() => void sendReply()}
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                  >
                    发送回复
                  </button>
                </div>
              ) : (
                <p className="mt-4 text-xs text-slate-400">工单已关闭。</p>
              )}
            </>
          ) : (
            <p className="text-sm text-slate-400">选择左侧工单查看详情与回复。</p>
          )}
        </section>
      </div>
    </div>
  );
}
