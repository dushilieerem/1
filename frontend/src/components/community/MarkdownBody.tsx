import { useMemo, useState, type MouseEvent } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DOMPurify from "dompurify";
import {
  highlightHtmlCodeBlocks,
  highlightSource,
} from "@/lib/codeHighlight";
import { ImageLightbox } from "@/components/community/ImageLightbox";

const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-5 text-xl font-bold tracking-tight text-slate-900 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2.5 mt-4 text-lg font-bold tracking-tight text-slate-900 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-3.5 text-base font-semibold text-slate-900 first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="mb-3 last:mb-0 leading-8 text-slate-700">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1 pl-5 text-slate-700 last:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5 text-slate-700 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-7">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-4 border-slate-200 pl-3 text-slate-500 italic last:mb-0">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-red-600 underline-offset-2 hover:underline"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-5 border-slate-200" />,
  code: ({ className, children }) => {
    const inline = !className;
    if (inline) {
      return (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.85em] text-red-700">
          {children}
        </code>
      );
    }
    const text = String(children).replace(/\n$/, "");
    const lang =
      /language-([\w+-]+)/i.exec(className || "")?.[1]?.toLowerCase() || "python";
    const { html } = highlightSource(text, lang);
    return (
      <code
        className={`hljs language-${lang} font-mono text-xs leading-relaxed`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  },
  pre: ({ children }) => (
    <pre className="community-code-block mb-3 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 p-4 last:mb-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-slate-200 bg-slate-50 px-3 py-1.5 text-left font-semibold text-slate-800">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-200 px-3 py-1.5 text-slate-700">{children}</td>
  ),
};

function looksLikeHtml(source: string): boolean {
  const t = source.trim();
  return /^\s*</.test(t) && /<\/[a-z][\w-]*>/i.test(t);
}

/** 社区正文：阅读态对代码块做高亮 */
export function MarkdownBody({
  source,
  className = "",
  /** 读帖摘要等场景：强制按 Markdown 解析，避免模型夹杂尖括号被当成 HTML */
  forceMarkdown = false,
}: {
  source: string;
  className?: string;
  forceMarkdown?: boolean;
}) {
  const text = source.trim();
  const [preview, setPreview] = useState<string | null>(null);
  const html = useMemo(() => {
    if (forceMarkdown || !text || !looksLikeHtml(text)) return null;
    const clean = DOMPurify.sanitize(text, {
      USE_PROFILES: { html: true },
      ADD_DATA_URI_TAGS: ["img"],
      ADD_ATTR: ["class", "style"],
    });
    return highlightHtmlCodeBlocks(clean);
  }, [text, forceMarkdown]);

  const onClickImg = (e: MouseEvent<HTMLElement>) => {
    const t = e.target;
    if (!(t instanceof HTMLImageElement)) return;
    const src = t.currentSrc || t.src;
    if (src) {
      e.preventDefault();
      setPreview(src);
    }
  };

  if (!text) {
    return <p className={`text-slate-400 ${className}`}>（无正文）</p>;
  }

  if (html != null) {
    return (
      <>
        <div
          className={`community-post-body text-[15px] leading-8 text-slate-700 ${className}`}
          dangerouslySetInnerHTML={{ __html: html }}
          onClick={onClickImg}
        />
        <ImageLightbox src={preview} onClose={() => setPreview(null)} />
      </>
    );
  }

  return (
    <>
      <div className={`text-[15px] ${className}`} onClick={onClickImg}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {text}
        </ReactMarkdown>
      </div>
      <ImageLightbox src={preview} onClose={() => setPreview(null)} />
    </>
  );
}

/** 帖子底部「代码片段」高亮展示 */
export function HighlightedCodeBlock({
  code,
  language = "python",
}: {
  code: string;
  language?: string;
}) {
  const { html } = useMemo(
    () => highlightSource(code, language),
    [code, language],
  );
  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <span className="text-xs font-medium tracking-wide text-slate-400">
          CODE
        </span>
        <span className="text-[11px] uppercase text-slate-500">{language}</span>
      </div>
      <pre className="community-code-block overflow-x-auto p-4 text-xs leading-relaxed text-slate-100">
        <code
          className={`hljs language-${language}`}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </pre>
    </div>
  );
}
