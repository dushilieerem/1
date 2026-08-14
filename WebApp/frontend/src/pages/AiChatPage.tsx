import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import {
  Bot,
  Check,
  ChevronDown,
  Copy,
  ArrowLeft,
  Menu,
  Pencil,
  Plus,
  Search,
  SendHorizontal,
  Sparkles,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { authHeaders, getStoredUser, subscribeAuth, type AuthUser } from "@/lib/auth";
import { highlightSource } from "@/lib/codeHighlight";
import { useKeyboardInset } from "@/hooks/useKeyboardInset";

type ChatMsg = { role: "user" | "assistant" | "system"; content: string };
type ChatThread = {
  id: string;
  title: string;
  model: string;
  messages: ChatMsg[];
  updatedAt: number;
};
type ArkModel = { id: string; label: string; family?: string };

/**
 * 离线兜底列表。正式列表以服务端 ark_chat.ARK_CHAT_MODELS 为准（加/删模型只改后端一处）。
 */
const FALLBACK_MODELS: ArkModel[] = [
  { id: "ark-code-latest", label: "ark-code-latest", family: "ark" },
  { id: "doubao-seed-2.0-pro", label: "Doubao Seed 2.0 Pro", family: "doubao" },
  { id: "doubao-seed-2.0-code", label: "Doubao Seed 2.0 Code", family: "doubao" },
  { id: "doubao-seed-2.0-lite", label: "Doubao Seed 2.0 Lite", family: "doubao" },
  { id: "doubao-seed-2.0-mini", label: "Doubao Seed 2.0 Mini", family: "doubao" },
  { id: "kimi-k2.6", label: "Kimi K2.6", family: "kimi" },
  { id: "kimi-k2.6-thinking", label: "Kimi K2.6 Thinking", family: "kimi" },
  { id: "minimax-latest", label: "MiniMax Latest", family: "minimax" },
  { id: "deepseek-ai/DeepSeek-V3", label: "DeepSeek V3", family: "deepseek" },
  { id: "Qwen/Qwen2.5-72B-Instruct", label: "Qwen2.5 72B", family: "qwen" },
  { id: "Qwen/Qwen2.5-Coder-32B-Instruct", label: "Qwen2.5 Coder 32B", family: "qwen" },
  { id: "THUDM/glm-4-9b-chat", label: "GLM-4 9B", family: "glm" },
];

const LS_THREADS_PREFIX = "svq.ai.chat.threads.v2.";
const LS_MODEL_PREFIX = "svq.ai.chat.model.v2.";
const LS_MODEL_LEGACY = "svq.ai.chat.model.v1";
const CHAT_WIDTH = "mx-auto w-full max-w-[min(100%,88rem)]";

function userScope(user: AuthUser | null): string {
  if (user?.id != null) return `u${user.id}`;
  if (user?.username) return `n_${user.username}`;
  return "anon";
}

function threadsKey(user: AuthUser | null) {
  return `${LS_THREADS_PREFIX}${userScope(user)}`;
}

function modelKey(user: AuthUser | null) {
  return `${LS_MODEL_PREFIX}${userScope(user)}`;
}

function uid() {
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function loadThreads(user: AuthUser | null): ChatThread[] {
  try {
    const raw = localStorage.getItem(threadsKey(user));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatThread[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveThreads(user: AuthUser | null, threads: ChatThread[]) {
  localStorage.setItem(threadsKey(user), JSON.stringify(threads.slice(0, 40)));
}

function loadModel(user: AuthUser | null): string {
  const saved = localStorage.getItem(modelKey(user)) || localStorage.getItem(LS_MODEL_LEGACY);
  return saved || "ark-code-latest";
}

/** 各厂商原色：豆包蓝 / Kimi 深灰 / MiniMax 紫 / Ark 橙（仅 ark） */
function familyMeta(family?: string) {
  const f = (family || "ark").toLowerCase();
  if (f === "doubao") return { bg: "bg-sky-500", Icon: Sparkles };
  if (f === "kimi") return { bg: "bg-slate-800", Icon: Bot };
  if (f === "minimax") return { bg: "bg-violet-600", Icon: Sparkles };
  if (f === "deepseek") return { bg: "bg-indigo-600", Icon: Bot };
  if (f === "qwen") return { bg: "bg-teal-600", Icon: Sparkles };
  if (f === "glm") return { bg: "bg-emerald-600", Icon: Zap };
  return { bg: "bg-orange-500", Icon: Zap };
}

function guessFamily(id: string, family?: string) {
  if (family) return family;
  const s = id.toLowerCase();
  if (s.includes("doubao")) return "doubao";
  if (s.includes("kimi")) return "kimi";
  if (s.includes("minimax")) return "minimax";
  if (s.includes("deepseek")) return "deepseek";
  if (s.includes("qwen")) return "qwen";
  if (s.includes("glm")) return "glm";
  return "ark";
}

/** 把数学模式里裸露的中文包进 \text{…}，便于 KaTeX 排版 */
function wrapCjkAsText(body: string): string {
  const slots: string[] = [];
  let s = body.replace(
    /\\(?:text|mathrm|operatorname|textbf|textit)\{([^{}]*)\}/g,
    (m) => {
      slots.push(m);
      return `\uE000${slots.length - 1}\uE001`;
    },
  );
  s = s.replace(
    /[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9％%\s（）()\-_·、，]*/g,
    (m) => `\\text{${m.trim()}}`,
  );
  s = s.replace(/\uE000(\d+)\uE001/g, (_m, i) => slots[Number(i)] || "");
  return s;
}

function prepareMathBody(raw: string, display: boolean): string {
  let fixed = raw
    .trim()
    .replace(/_(\(([^)]+)\))/g, (_m, _p, inner: string) => `_{${inner}}`)
    .replace(/\^(\(([^)]+)\))/g, (_m, _p, inner: string) => `^{${inner}}`);
  // 含中文的展示公式用 \dfrac，竖排分数更清晰
  if (display && /[\u4e00-\u9fff]/.test(fixed)) {
    fixed = fixed.replace(/\\frac\b/g, "\\dfrac");
  }
  if (/[\u4e00-\u9fff]/.test(fixed)) {
    fixed = wrapCjkAsText(fixed);
  }
  return fixed;
}

/** 把「PE = (中文)/(中文)」这类纯文本提升为 KaTeX 公式块 */
function promotePlainChineseFormulas(src: string): string {
  return src.replace(/^([A-Za-z][A-Za-z0-9]*)\s*=\s*(.+)$/gm, (full, name: string, rhs: string) => {
    if (!/[\u4e00-\u9fff]/.test(rhs)) return full;
    if (/\$|\\dfrac|\\frac|\\text\{/.test(rhs)) return full;
    if (!/\([^)]+\)\s*\/\s*\([^)]+\)/.test(rhs) && !/[\u4e00-\u9fff].*\/.*[\u4e00-\u9fff]/.test(rhs)) {
      return full;
    }
    let mathRhs = rhs.trim();
    mathRhs = mathRhs.replace(/\(([^)]+)\)\s*\/\s*\(([^)]+)\)/g, (_m, a: string, b: string) => {
      return `\\dfrac{\\text{${a.trim()}}}{\\text{${b.trim()}}}`;
    });
    mathRhs = mathRhs.replace(
      /([\u4e00-\u9fff][^\/=\n]*?)\s*\/\s*([\u4e00-\u9fff][^\/=\n]*?)(?=\s*=|\s*$)/g,
      (_m, a: string, b: string) => `\\dfrac{\\text{${a.trim()}}}{\\text{${b.trim()}}}`,
    );
    return `$$\n${name} = ${mathRhs}\n$$`;
  });
}

/** ✅/❌ 对比项换行 */
function formatContrastBullets(src: string): string {
  let s = src;
  s = s.replace(/([^\n✅❌☑️✓✗×])\s*([✅❌☑️✓✗×])/g, "$1\n$2");
  s = s.replace(/^[ \t]*[-*•·]\s*(?=[✅❌☑️✓✗×])/gm, "");
  s = s.replace(/\n{3,}/g, "\n\n");
  return s;
}

/**
 * 未闭合的 $$ 会把后文整段吃成「红色公式」。
 * 在大纲标记 / 空行处强制闭合。
 */
function balanceDisplayMath(src: string): string {
  let out = "";
  let i = 0;
  let inMath = false;
  const outlineAt = (pos: number) => {
    const rest = src.slice(pos);
    return /^(?:#{1,6}\s|[一二三四五六七八九十]+[、.．]|\d{1,2}[\.、．]\s|[（(]\s*\d|[①②③④⑤⑥⑦⑧⑨⑩]|```|✅|❌)/.test(
      rest,
    );
  };
  while (i < src.length) {
    if (src.startsWith("$$", i)) {
      out += inMath ? "\n$$\n" : "$$\n";
      inMath = !inMath;
      i += 2;
      continue;
    }
    if (inMath && src[i] === "\n") {
      let j = i + 1;
      while (src[j] === " " || src[j] === "\t") j++;
      if (src[j] === "\n" || outlineAt(j) || j >= src.length) {
        out += "\n$$\n";
        inMath = false;
        continue;
      }
    }
    out += src[i];
    i += 1;
  }
  if (inMath) out += "\n$$";
  return out;
}

/** 章内连续「1. 1. 1.」按出现顺序改成 1. 2. 3.（模型常全写 1.） */
function renumberSiblingItems(text: string): string {
  let n = 0;
  return text
    .split("\n")
    .map((line) => {
      const t = line.trim();
      if (/^(?:#{1,6}\s|[一二三四五六七八九十]+[、.．])/.test(t)) {
        n = 0;
        return line;
      }
      const m = /^(\s*)\d{1,2}([\.、．])(\s+.*)$/.exec(line);
      if (m) {
        n += 1;
        return `${m[1]}${n}${m[2]}${m[3]}`;
      }
      return line;
    })
    .join("\n");
}

function prepareAssistantText(src: string): string {
  let s = src || "";
  s = s.replace(/^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "");
  s = formatContrastBullets(s);
  // 粘在同一行的（1）/① 拆开
  s = s.replace(/([^\n])[ \t]*([（(]\s*[1-9１-９]{1,2}\s*[）)])/g, "$1\n$2");
  s = s.replace(/([^\n])[ \t]*([①②③④⑤⑥⑦⑧⑨⑩])/g, "$1\n$2");
  s = promotePlainChineseFormulas(s);
  s = s.replace(/\\\[([\s\S]*?)\\\]/g, (_m, body: string) => `$$\n${prepareMathBody(body, true)}\n$$`);
  s = s.replace(/\\\(([\s\S]*?)\\\)/g, (_m, body: string) => `$${prepareMathBody(body, false)}$`);
  s = balanceDisplayMath(s);

  // 编号重排时先挖掉代码/公式，避免跨块计数被打断后从 1 重来
  const holes: string[] = [];
  const park = (m: string) => {
    holes.push(m);
    return `\n%%H${holes.length - 1}%%\n`;
  };
  s = s.replace(/```[\s\S]*?```/g, park);
  s = s.replace(/\$\$[\s\S]+?\$\$/g, park);
  s = renumberSiblingItems(s);
  s = s.replace(/%%H(\d+)%%/g, (_m, i: string) => holes[Number(i)] || "");
  return s;
}

type ContentSeg =
  | { kind: "code"; lang: string; code: string }
  | { kind: "math"; tex: string }
  | { kind: "text"; text: string };

function splitContentSegments(src: string): ContentSeg[] {
  const s = prepareAssistantText(src);
  const segs: ContentSeg[] = [];
  const re = /```([\w+-]*)[ \t]*\n?([\s\S]*?)```|\$\$([\s\S]+?)\$\$/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) segs.push({ kind: "text", text: s.slice(last, m.index) });
    if (m[0].startsWith("```")) {
      segs.push({
        kind: "code",
        lang: (m[1] || "python").toLowerCase(),
        code: (m[2] || "").replace(/\n$/, ""),
      });
    } else {
      segs.push({ kind: "math", tex: prepareMathBody(m[3] || "", true) });
    }
    last = m.index + m[0].length;
  }
  if (last < s.length) segs.push({ kind: "text", text: s.slice(last) });
  return segs;
}

function renderKatex(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, {
      throwOnError: false,
      strict: false,
      displayMode: display,
      output: "html",
    });
  } catch {
    return tex;
  }
}

/** 行内：**粗体**、`code`、$math$ */
function InlineText({ text }: { text: string }) {
  const parts = useMemo(() => {
    const out: ReactNode[] = [];
    const re = /(\*\*[^*]+\*\*|`[^`]+`|\$(?!\$)([^$\n]+?)\$)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let key = 0;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      const token = m[0];
      if (token.startsWith("**")) {
        out.push(
          <strong key={key++} className="font-semibold text-slate-900">
            {token.slice(2, -2)}
          </strong>,
        );
      } else if (token.startsWith("`")) {
        out.push(
          <code
            key={key++}
            className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[12px] text-slate-800"
          >
            {token.slice(1, -1)}
          </code>,
        );
      } else {
        const tex = prepareMathBody(m[2] || "", false);
        out.push(
          <span
            key={key++}
            className="katex-inline"
            dangerouslySetInnerHTML={{ __html: renderKatex(tex, false) }}
          />,
        );
      }
      last = m.index + token.length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }, [text]);
  return <>{parts}</>;
}

function TextLines({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  return (
    <div className="text-[13px] leading-[1.75] text-slate-800 sm:text-sm">
      {lines.map((line, i) => {
        const t = line.trimEnd();
        if (!t.trim()) {
          return <div key={i} className="h-2.5" aria-hidden />;
        }
        const head = t.match(/^(#{1,6})\s+(.*)$/);
        if (head) {
          const depth = head[1].length;
          const body = head[2];
          if (depth <= 2) {
            return (
              <h2
                key={i}
                className="mb-1.5 mt-3 text-[15px] font-semibold tracking-tight text-slate-900 first:mt-0 sm:text-base"
              >
                <InlineText text={body} />
              </h2>
            );
          }
          return (
            <h3 key={i} className="mb-1 mt-2.5 text-sm font-semibold text-slate-800 first:mt-0">
              <InlineText text={body} />
            </h3>
          );
        }
        // 一、二、三、 当标题
        if (/^[一二三四五六七八九十]+[、.．]/.test(t.trim())) {
          return (
            <h2
              key={i}
              className="mb-1.5 mt-3 text-[15px] font-semibold tracking-tight text-slate-900 first:mt-0 sm:text-base"
            >
              <InlineText text={t.trim()} />
            </h2>
          );
        }
        const trimmed = t.trimStart();
        const indent =
          /^[（(]\s*\d/.test(trimmed) || /^[①②③④⑤⑥⑦⑧⑨⑩]/.test(trimmed)
            ? "pl-4"
            : /^\d{1,2}[\.、．]/.test(trimmed)
              ? "pl-1"
              : "";
        return (
          <div key={i} className={`break-words ${indent}`}>
            <InlineText text={t} />
          </div>
        );
      })}
    </div>
  );
}

function MathBlock({ tex }: { tex: string }) {
  const html = useMemo(() => renderKatex(tex, true), [tex]);
  return (
    <div
      className="ai-math-block my-3 overflow-x-auto text-center"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function CodeBlock({ className, children }: { className?: string; children?: ReactNode }) {
  const text = String(children ?? "").replace(/\n$/, "");
  const lang =
    /language-([\w+-]+)/i.exec(className || "")?.[1]?.toLowerCase() || "python";
  const { html } = highlightSource(text, lang);
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="ai-code-block mb-3 overflow-hidden rounded-xl border border-slate-200 bg-white last:mb-0">
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-3 py-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {lang}
        </span>
        <button
          type="button"
          onClick={() => void onCopy()}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-slate-500 hover:bg-white hover:text-slate-800"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="m-0 overflow-x-auto bg-white p-3">
        <code
          className={`hljs language-${lang} font-mono text-[12.5px] leading-[1.65] text-slate-800`}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </pre>
    </div>
  );
}

/**
 * 与流式阶段同一套「按行」排版：不走整篇 Markdown。
 * 只单独渲染 ```代码``` 和 $$公式$$，避免列表重置 / 未闭合 $$ 吞字。
 */
function Md({ text }: { text: string }) {
  const segs = useMemo(() => splitContentSegments(text), [text]);
  return (
    <div className="ai-md prose-katex max-w-full overflow-x-hidden break-words">
      {segs.map((seg, i) => {
        if (seg.kind === "code") {
          return (
            <CodeBlock key={i} className={`language-${seg.lang}`}>
              {seg.code}
            </CodeBlock>
          );
        }
        if (seg.kind === "math") {
          return <MathBlock key={i} tex={seg.tex} />;
        }
        if (!seg.text.trim()) return null;
        return <TextLines key={i} text={seg.text} />;
      })}
    </div>
  );
}

export function AiChatPage() {
  const navigate = useNavigate();
  const [me, setMe] = useState<AuthUser | null>(() => getStoredUser());
  const userInitial = (me?.display_name || me?.username || "我").slice(0, 1).toUpperCase();
  const userAvatar = (me?.avatar_url || "").trim();

  const [models, setModels] = useState<ArkModel[]>(FALLBACK_MODELS);
  const [configured, setConfigured] = useState(true);
  const [model, setModel] = useState(() => loadModel(getStoredUser()));
  const [modelOpen, setModelOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [threads, setThreads] = useState<ChatThread[]>(() => loadThreads(getStoredUser()));
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamHint, setStreamHint] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sideSearch, setSideSearch] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const modelMenuRef = useRef<HTMLDivElement>(null);
  const renameRef = useRef<HTMLInputElement>(null);
  const scopeRef = useRef(userScope(me));
  const kbInset = useKeyboardInset();
  const [composerH, setComposerH] = useState(120);

  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    const measure = () => setComposerH(el.offsetHeight || 120);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const active = useMemo(
    () => threads.find((t) => t.id === activeId) || null,
    [threads, activeId],
  );

  const currentModel = useMemo(() => {
    return models.find((m) => m.id === model) || models[0] || FALLBACK_MODELS[0];
  }, [models, model]);

  useEffect(() => subscribeAuth(() => setMe(getStoredUser())), []);

  // 聊天页锁住外层滚动，只保留消息区滚动条
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const prevHtml = html.style.overflow;
    const prevBody = body.style.overflow;
    html.style.overflow = "hidden";
    body.style.overflow = "hidden";
    return () => {
      html.style.overflow = prevHtml;
      body.style.overflow = prevBody;
    };
  }, []);

  // 换账号时切换本地历史桶，禁止串对话
  useEffect(() => {
    const scope = userScope(me);
    if (scopeRef.current === scope) return;
    scopeRef.current = scope;
    setThreads(loadThreads(me));
    setModel(loadModel(me));
    setActiveId(null);
    setInput("");
    setErr(null);
    setRenamingId(null);
  }, [me]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch("/api/ai/chat/models");
        const data = await res.json();
        setConfigured(Boolean(data.configured));
        const remote = (data.models || []) as ArkModel[];
        if (remote.length) {
          setModels(remote);
          const ids = new Set(remote.map((m) => m.id));
          setModel((prev) => (ids.has(prev) ? prev : remote[0].id));
        } else {
          setModels(FALLBACK_MODELS);
        }
      } catch {
        setConfigured(false);
        setModels(FALLBACK_MODELS);
      }
    })();
  }, []);

  useEffect(() => {
    saveThreads(me, threads);
  }, [threads, me]);

  useEffect(() => {
    localStorage.setItem(modelKey(me), model);
  }, [model, me]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages.length, active?.messages[active.messages.length - 1]?.content, busy]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!modelMenuRef.current?.contains(e.target as Node)) setModelOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (renamingId) renameRef.current?.focus();
  }, [renamingId]);

  const filteredThreads = useMemo(() => {
    const q = sideSearch.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        t.messages.some((m) => m.content.toLowerCase().includes(q)),
    );
  }, [threads, sideSearch]);

  const newChat = () => {
    setActiveId(null);
    setInput("");
    setErr(null);
    setDrawerOpen(false);
    setRenamingId(null);
    taRef.current?.focus();
  };

  const removeThread = (id: string) => {
    setThreads((prev) => prev.filter((t) => t.id !== id));
    if (activeId === id) setActiveId(null);
    if (renamingId === id) setRenamingId(null);
  };

  const startRename = (t: ChatThread) => {
    setRenamingId(t.id);
    setRenameDraft(t.title);
  };

  const commitRename = () => {
    if (!renamingId) return;
    const title = renameDraft.trim() || "未命名对话";
    setThreads((prev) =>
      prev.map((t) => (t.id === renamingId ? { ...t, title, updatedAt: Date.now() } : t)),
    );
    setRenamingId(null);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    if (!me) {
      setErr("请先登录后再使用 SV 助手");
      return;
    }
    setErr(null);
    setBusy(true);
    setStreamHint("正在连接模型…");
    setInput("");

    let threadId = activeId;
    let nextMessages: ChatMsg[];

    if (!threadId) {
      threadId = uid();
      const created: ChatThread = {
        id: threadId,
        title: text.slice(0, 28) + (text.length > 28 ? "…" : ""),
        model,
        messages: [{ role: "user", content: text }],
        updatedAt: Date.now(),
      };
      setThreads((prev) => [created, ...prev]);
      setActiveId(threadId);
      nextMessages = created.messages;
    } else {
      nextMessages = [...(active?.messages || []), { role: "user", content: text }];
      setThreads((prev) =>
        prev.map((t) =>
          t.id === threadId
            ? { ...t, messages: nextMessages, model, updatedAt: Date.now() }
            : t,
        ),
      );
    }

    // 先插入空助手气泡，流式往里写
    setThreads((prev) =>
      prev.map((t) =>
        t.id === threadId
          ? {
              ...t,
              messages: [...t.messages, { role: "assistant", content: "" }],
              updatedAt: Date.now(),
            }
          : t,
      ),
    );

    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          model,
          stream: true,
          messages: nextMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `请求失败 ${res.status}`);
      }

      const setAssistant = (content: string) => {
        setThreads((prev) =>
          prev.map((t) => {
            if (t.id !== threadId) return t;
            const msgs = [...t.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { role: "assistant", content };
            }
            return { ...t, messages: msgs, updatedAt: Date.now() };
          }),
        );
      };

      const ctype = (res.headers.get("content-type") || "").toLowerCase();
      // 旧进程或非流式：直接吃 JSON
      if (ctype.includes("application/json")) {
        const data = await res.json().catch(() => ({}));
        const reply = String(data.content || "").trim() || "（空回复）";
        setAssistant(reply);
        return;
      }

      if (!res.body) throw new Error("浏览器不支持流式响应");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let full = "";
      let raf = 0;
      let finished = false;

      const flushUi = () => {
        raf = 0;
        setAssistant(full);
      };

      const appendDelta = (delta: string) => {
        full += delta;
        setStreamHint(null);
        // 节流 UI：避免每个 token 都重渲 Markdown/KaTeX 拖慢体感速度
        if (!raf) {
          raf = window.requestAnimationFrame(flushUi);
        }
      };

      try {
        while (!finished) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n");
          buffer = parts.pop() || "";
          for (const line of parts) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const dataStr = trimmed.slice(5).trim();
            if (!dataStr) continue;
            if (dataStr === "[DONE]") {
              finished = true;
              break;
            }
            let obj: {
              delta?: string;
              error?: string;
              content?: string;
              status?: string;
            };
            try {
              obj = JSON.parse(dataStr) as {
                delta?: string;
                error?: string;
                content?: string;
                status?: string;
              };
            } catch {
              continue;
            }
            if (obj.error) throw new Error(obj.error);
            if (obj.status === "start") {
              setStreamHint("模型思考中…");
              continue;
            }
            if (obj.delta) appendDelta(obj.delta);
            else if (obj.content) appendDelta(obj.content);
          }
        }
      } finally {
        if (raf) {
          window.cancelAnimationFrame(raf);
          raf = 0;
        }
        try {
          await reader.cancel();
        } catch {
          /* ignore */
        }
      }

      // 整包 JSON 被当成“流”读进来的兜底
      if (!full.trim() && buffer.trim().startsWith("{")) {
        try {
          const obj = JSON.parse(buffer) as { content?: string; error?: string };
          if (obj.error) throw new Error(obj.error);
          if (obj.content) full = String(obj.content);
        } catch (e) {
          if (e instanceof Error && e.message && !e.message.includes("JSON")) throw e;
        }
      }

      setAssistant(full.trim() || "（空回复）");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      // 失败时去掉空助手气泡
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id !== threadId) return t;
          const msgs = [...t.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant" && !last.content.trim()) msgs.pop();
          return { ...t, messages: msgs };
        }),
      );
    } finally {
      setStreamHint(null);
      setBusy(false);
      taRef.current?.focus();
    }
  };

  const empty = !active || active.messages.length === 0;
  const curMeta = familyMeta(guessFamily(currentModel.id, currentModel.family));
  const CurIcon = curMeta.Icon;
  const headerTitle = empty ? "新对话" : active?.title || "对话";

  const renderUserAvatar = (className = "mt-1") => (
    <span
      className={`flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-700 text-xs font-semibold text-white ${className}`}
      title={me?.display_name || me?.username || "用户"}
    >
      {userAvatar ? (
        <img src={userAvatar} alt="" className="h-full w-full object-cover" />
      ) : (
        userInitial
      )}
    </span>
  );

  const modelPicker = (
    <div className="relative" ref={modelMenuRef}>
      <button
        type="button"
        onClick={() => setModelOpen((v) => !v)}
        title="选择模型"
        className="flex max-w-[min(100%,14rem)] items-center gap-1.5 rounded-full border border-slate-200 bg-white py-1.5 pl-1.5 pr-2.5 text-left hover:border-[#4d6bfe]/60"
      >
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white ${curMeta.bg}`}
        >
          <CurIcon className="h-3.5 w-3.5" />
        </span>
        <span className="truncate text-xs font-medium text-slate-700">{currentModel.label}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      </button>
      {modelOpen ? (
        <ul className="absolute bottom-[calc(100%+0.4rem)] right-0 z-30 max-h-[min(50vh,20rem)] w-[min(92vw,18rem)] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-2xl">
          {models.map((m) => {
            const meta = familyMeta(guessFamily(m.id, m.family));
            const Icon = meta.Icon;
            const on = m.id === model;
            return (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => {
                    setModel(m.id);
                    setModelOpen(false);
                  }}
                  className={`flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left ${
                    on ? "bg-slate-100" : "hover:bg-slate-50"
                  }`}
                >
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white ${meta.bg}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-slate-800">{m.label}</span>
                  {on ? <Check className="h-4 w-4 shrink-0 text-[#4d6bfe]" /> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );

  const sidebar = (
    <>
      <div className="flex items-center justify-between gap-2 border-b border-slate-200/80 px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#4d6bfe] text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold text-slate-800">SV 助手</span>
        </div>
        <button
          type="button"
          className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200/70 md:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-label="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-2 p-3">
        <button
          type="button"
          onClick={newChat}
          className="flex w-full items-center justify-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 hover:border-[#4d6bfe] hover:text-[#4d6bfe]"
        >
          <Plus className="h-4 w-4" />
          新建对话
        </button>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          <input
            value={sideSearch}
            onChange={(e) => setSideSearch(e.target.value)}
            placeholder="搜索对话"
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-2 text-xs text-slate-700 outline-none placeholder:text-slate-400 focus:border-[#4d6bfe]"
          />
        </div>
      </div>
      <div className="px-3 pb-1 text-[13px] font-medium text-slate-600">最近对话</div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {filteredThreads.length === 0 ? (
          <li className="px-2 py-6 text-center text-xs text-slate-400">暂无历史</li>
        ) : (
          filteredThreads.map((t) => (
            <li key={t.id} className="group relative">
              {renamingId === t.id ? (
                <div className="flex items-center gap-1 rounded-lg bg-white px-1.5 py-1.5 ring-1 ring-[#4d6bfe]/40">
                  <input
                    ref={renameRef}
                    value={renameDraft}
                    onChange={(e) => setRenameDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        commitRename();
                      }
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    onBlur={() => commitRename()}
                    className="min-w-0 flex-1 bg-transparent px-1 text-[13px] text-slate-800 outline-none"
                  />
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveId(t.id);
                      setErr(null);
                      setDrawerOpen(false);
                    }}
                    className={`w-full rounded-lg px-2.5 py-2 pr-14 text-left text-[13px] leading-snug ${
                      activeId === t.id
                        ? "bg-slate-200/90 font-medium text-slate-900"
                        : "text-slate-600 hover:bg-slate-200/50"
                    }`}
                  >
                    <span className="line-clamp-2">{t.title}</span>
                  </button>
                  <div className="absolute right-1 top-1.5 flex items-center gap-0.5 opacity-100 md:opacity-0 md:group-hover:opacity-100">
                    <button
                      type="button"
                      title="重命名"
                      className="rounded p-1 text-slate-400 hover:bg-white hover:text-[#4d6bfe]"
                      onClick={(e) => {
                        e.stopPropagation();
                        startRename(t);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      title="删除"
                      className="rounded p-1 text-slate-400 hover:bg-white hover:text-rose-500"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeThread(t.id);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </>
              )}
            </li>
          ))
        )}
      </ul>
    </>
  );

  return (
    <div className="relative flex h-full min-h-0 overflow-hidden bg-[#f7f8fa]">
      <aside className="hidden w-[14rem] shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-[#f3f4f6] md:flex lg:w-[15rem]">
        {sidebar}
      </aside>

      {drawerOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/40"
            aria-label="关闭历史"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(84vw,17rem)] flex-col bg-[#f3f4f6] shadow-2xl">
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="relative flex shrink-0 items-center gap-1 border-b border-slate-200 bg-white/90 px-2 py-2.5 backdrop-blur sm:px-5">
          <button
            type="button"
            className="z-10 rounded-lg p-2 text-slate-600 hover:bg-slate-100"
            onClick={() => {
              if (window.history.length > 1) navigate(-1);
              else navigate("/");
            }}
            aria-label="返回"
            title="返回"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="z-10 rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            onClick={() => setDrawerOpen(true)}
            aria-label="历史对话"
          >
            <Menu className="h-5 w-5" />
          </button>

          <h1 className="pointer-events-none absolute inset-x-20 truncate text-center text-sm font-medium text-slate-800 sm:inset-x-24 sm:text-[15px]">
            {headerTitle}
          </h1>

          <div className="z-10 ml-auto flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 md:hidden"
              onClick={newChat}
            >
              新对话
            </button>
            {renderUserAvatar("")}
          </div>
        </header>

        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-4 sm:px-4 sm:py-5 lg:px-6 max-md:pb-[calc(var(--composer-pad,7.5rem)+var(--kb-inset,0px))]"
          style={{ ["--composer-pad" as string]: `${composerH + 16}px` } as CSSProperties}
        >
          {empty ? (
            <div className={`${CHAT_WIDTH} flex flex-col items-center px-1 pt-8 text-center sm:pt-[16vh]`}>
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-[1.25rem] bg-[#4d6bfe] text-white shadow-lg shadow-blue-500/20 sm:mb-5 sm:h-16 sm:w-16">
                <Sparkles className="h-7 w-7 sm:h-8 sm:w-8" />
              </div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-800 sm:text-3xl">
                你好，我是 SV 助手
              </h2>
              {!configured ? (
                <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  服务端未读到 ARK_API_KEY，请确认系统环境变量或 backend/.env 并重启 API。
                </p>
              ) : null}
            </div>
          ) : (
            <div className={`${CHAT_WIDTH} space-y-4`}>
              {active?.messages.map((m, i) => (
                <div
                  key={`${i}-${m.role}`}
                  className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {m.role === "assistant" ? (
                    <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#4d6bfe] text-white shadow">
                      <Sparkles className="h-4 w-4" />
                    </span>
                  ) : null}
                  <div
                    className={`min-w-0 rounded-2xl px-3.5 py-2.5 sm:px-4 ${
                      m.role === "user"
                        ? "max-w-[min(100%,75%)] bg-[#4d6bfe] text-white shadow-md shadow-blue-500/15"
                        : "w-full flex-1 border border-slate-200/80 bg-white text-slate-800 shadow-sm"
                    }`}
                  >
                    {m.role === "user" ? (
                      <p className="whitespace-pre-wrap text-[13px] leading-relaxed sm:text-sm">
                        {m.content}
                      </p>
                    ) : !m.content ? (
                      <span className="text-[13px] text-slate-400 sm:text-sm">
                        {streamHint || "生成中…"}
                        <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-[#4d6bfe]/70 align-middle" />
                      </span>
                    ) : busy && i === (active?.messages.length || 0) - 1 ? (
                      // 流式中用纯文本 + 光标，结束再走 Markdown（避免每字重渲 KaTeX 卡死）
                      <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-800 sm:text-sm">
                        {m.content}
                        <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-[#4d6bfe]/70 align-middle" />
                      </p>
                    ) : (
                      <Md text={m.content} />
                    )}
                  </div>
                  {m.role === "user" ? renderUserAvatar() : null}
                </div>
              ))}
              {busy &&
              !(
                active?.messages.length &&
                active.messages[active.messages.length - 1]?.role === "assistant"
              ) ? (
                <div className="flex gap-2.5">
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#4d6bfe] text-white">
                    <Sparkles className="h-4 w-4" />
                  </span>
                  <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-400">
                    思考中…
                  </div>
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div
          ref={composerRef}
          className="z-50 border-t border-slate-200 bg-white px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-4 lg:relative lg:z-auto lg:shrink-0 lg:bg-white/90 lg:backdrop-blur lg:px-6 max-md:fixed max-md:inset-x-0 max-md:bottom-0"
          style={kbInset > 0 ? { bottom: kbInset } : undefined}
        >
          {err ? (
            <p className={`${CHAT_WIDTH} mb-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700`}>
              {err}
            </p>
          ) : null}
          <div className={`${CHAT_WIDTH} overflow-visible rounded-2xl border border-slate-200 bg-white p-2.5 shadow-lg shadow-slate-200/40 sm:p-3`}>
            <textarea
              ref={taRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
              }}
              onFocus={() => {
                // 等键盘顶起后再钉住输入条
                const pin = () => {
                  composerRef.current?.scrollIntoView({ block: "nearest" });
                  taRef.current?.scrollIntoView({ block: "nearest" });
                };
                pin();
                window.setTimeout(pin, 50);
                window.setTimeout(pin, 200);
                window.setTimeout(pin, 450);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={2}
              placeholder="向 SV 助手提问…"
              enterKeyHint="send"
              className="w-full resize-none bg-transparent text-base text-slate-800 outline-none placeholder:text-slate-400 sm:text-sm"
              disabled={busy}
            />
            <div className="mt-1.5 flex items-center justify-end gap-1.5">
              {modelPicker}
              <button
                type="button"
                onClick={() => void send()}
                disabled={busy || !input.trim()}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#4d6bfe] text-white hover:bg-[#3d5af5] disabled:bg-slate-300"
                aria-label="发送"
              >
                <SendHorizontal className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
