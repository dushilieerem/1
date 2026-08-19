import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronLeft, ChevronRight, List } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  DEFAULT_HELP_DOC,
  extractHelpHeadings,
  getHelpDoc,
  HELP_DOCS,
  slugifyHeading,
  type HelpDocId,
  type HelpDocMeta,
} from "@/content/help/catalog";
import { loadHelpMarkdown } from "@/content/help/docs";
import { highlightSource } from "@/lib/codeHighlight";

function groupDocs(docs: HelpDocMeta[]): { group: string; items: HelpDocMeta[] }[] {
  const order: string[] = [];
  const map = new Map<string, HelpDocMeta[]>();
  for (const d of docs) {
    if (!map.has(d.group)) {
      map.set(d.group, []);
      order.push(d.group);
    }
    map.get(d.group)!.push(d);
  }
  return order.map((group) => ({ group, items: map.get(group)! }));
}

const helpMdComponents: Components = {
  h1: ({ children }) => {
    const text = String(children);
    return (
      <h1
        id={slugifyHeading(text)}
        className="mb-4 scroll-mt-24 border-b border-slate-200 pb-3 text-2xl font-bold tracking-tight text-slate-900"
      >
        {children}
      </h1>
    );
  },
  h2: ({ children }) => {
    const text = flatText(children);
    return (
      <h2
        id={slugifyHeading(text)}
        className="mb-3 mt-10 scroll-mt-24 text-xl font-bold text-slate-900 first:mt-0"
      >
        {children}
      </h2>
    );
  },
  h3: ({ children }) => {
    const text = flatText(children);
    return (
      <h3
        id={slugifyHeading(text)}
        className="mb-2 mt-7 scroll-mt-24 text-base font-semibold text-slate-800"
      >
        {children}
      </h3>
    );
  },
  p: ({ children }) => (
    <p className="mb-3 last:mb-0 text-[15px] leading-7 text-slate-700">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1.5 pl-5 text-[15px] text-slate-700 last:mb-0">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1.5 pl-5 text-[15px] text-slate-700 last:mb-0">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-7">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="mb-4 border-l-[3px] border-sky-300 bg-sky-50/60 px-4 py-2 text-sm text-slate-600 last:mb-0">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      className="font-medium text-sky-700 underline-offset-2 hover:underline"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-8 border-slate-200" />,
  code: ({ className, children }) => {
    const inline = !className;
    if (inline) {
      return (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.86em] text-rose-700">
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
        className={`hljs language-${lang} font-mono text-[13px] leading-[1.7] text-slate-800`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  },
  pre: ({ children }) => (
    <pre className="help-code-block mb-4 overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-4 last:mb-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="mb-4 overflow-x-auto last:mb-0">
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-slate-200 bg-slate-50 px-3 py-2 text-left font-semibold text-slate-800">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-200 px-3 py-2 text-slate-700">{children}</td>
  ),
};

function flatText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(flatText).join("");
  if (typeof node === "object" && "props" in node) {
    return flatText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function HelpSidebar({
  activeId,
  headings,
  expandedGroups,
  onToggleGroup,
}: {
  activeId: HelpDocId;
  headings: { id: string; text: string; level: 2 | 3 }[];
  expandedGroups: Record<string, boolean>;
  onToggleGroup: (group: string) => void;
}) {
  const groups = useMemo(() => groupDocs(HELP_DOCS), []);

  return (
    <nav className="help-sidebar text-sm" aria-label="帮助目录">
      <div className="mb-3 border-b border-slate-200 pb-2 text-base font-bold text-slate-900">
        帮助文档
      </div>
      {groups.map(({ group, items }) => {
        const open = expandedGroups[group] !== false;
        return (
          <div key={group} className="mb-2">
            <button
              type="button"
              onClick={() => onToggleGroup(group)}
              className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left font-semibold text-slate-800 hover:bg-slate-50"
            >
              <span>{group}</span>
              <ChevronDown
                className={`h-4 w-4 shrink-0 text-slate-400 transition ${open ? "" : "-rotate-90"}`}
              />
            </button>
            {open && (
              <ul className="mt-0.5 space-y-0.5 border-l border-slate-200 ml-2 pl-1">
                {items.map((doc) => {
                  const active = doc.id === activeId;
                  return (
                    <li key={doc.id}>
                      <Link
                        to={`/help/${doc.id}`}
                        className={`block rounded px-2 py-1.5 leading-snug ${
                          active
                            ? "bg-sky-50 font-medium text-sky-700"
                            : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                        }`}
                      >
                        {doc.title}
                      </Link>
                      {active && headings.length > 0 && (
                        <ul className="mt-0.5 mb-1 space-y-0.5 border-l border-slate-100 ml-2 pl-1">
                          {headings.map((h) => (
                            <li key={h.id}>
                              <a
                                href={`#${h.id}`}
                                className={`block rounded px-2 py-1 text-xs leading-snug text-slate-500 hover:bg-slate-50 hover:text-sky-700 ${
                                  h.level === 3 ? "pl-4" : ""
                                }`}
                              >
                                {h.text}
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}

function HelpArticle({ doc }: { doc: HelpDocMeta }) {
  const md = useMemo(() => loadHelpMarkdown(doc.id), [doc.id]);
  const headings = useMemo(() => extractHelpHeadings(md), [md]);
  const idx = HELP_DOCS.findIndex((d) => d.id === doc.id);
  const prev = idx > 0 ? HELP_DOCS[idx - 1] : null;
  const next = idx >= 0 && idx < HELP_DOCS.length - 1 ? HELP_DOCS[idx + 1] : null;

  useEffect(() => {
    if (!window.location.hash) {
      window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
    }
  }, [doc.id]);

  return (
    <article className="min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={helpMdComponents}>
        {md}
      </ReactMarkdown>

      <nav
        className="mt-12 flex flex-col gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-stretch sm:justify-between"
        aria-label="上下篇"
      >
        {prev ? (
          <Link
            to={`/help/${prev.id}`}
            className="group flex min-w-0 flex-1 items-start gap-2 rounded-lg border border-slate-200 px-4 py-3 hover:border-sky-300 hover:bg-sky-50/50"
          >
            <ChevronLeft className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 group-hover:text-sky-600" />
            <span className="min-w-0">
              <span className="block text-xs text-slate-400">上一篇</span>
              <span className="block truncate text-sm font-medium text-slate-800 group-hover:text-sky-700">
                {prev.title}
              </span>
            </span>
          </Link>
        ) : (
          <span className="flex-1" />
        )}
        {next ? (
          <Link
            to={`/help/${next.id}`}
            className="group flex min-w-0 flex-1 items-start justify-end gap-2 rounded-lg border border-slate-200 px-4 py-3 text-right hover:border-sky-300 hover:bg-sky-50/50"
          >
            <span className="min-w-0">
              <span className="block text-xs text-slate-400">下一篇</span>
              <span className="block truncate text-sm font-medium text-slate-800 group-hover:text-sky-700">
                {next.title}
              </span>
            </span>
            <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 group-hover:text-sky-600" />
          </Link>
        ) : (
          <span className="flex-1" />
        )}
      </nav>
    </article>
  );
}

/** 帮助中心：左目录 + 右 Markdown（聚宽 / 同花顺文档风） */
export function HelpPage() {
  const { docId } = useParams<{ docId?: string }>();
  if (!docId) {
    return <Navigate to={`/help/${DEFAULT_HELP_DOC}`} replace />;
  }

  const known = HELP_DOCS.some((d) => d.id === docId);
  if (!known) {
    return <Navigate to={`/help/${DEFAULT_HELP_DOC}`} replace />;
  }

  return <HelpDocView docId={docId as HelpDocId} />;
}

function HelpDocView({ docId }: { docId: HelpDocId }) {
  const doc = getHelpDoc(docId);
  const md = useMemo(() => loadHelpMarkdown(doc.id), [doc.id]);
  const headings = useMemo(() => extractHelpHeadings(md), [md]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const d of HELP_DOCS) init[d.group] = true;
    return init;
  });

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-white">
      <div className="mx-auto flex max-w-[1440px] gap-0 px-4 sm:px-6 lg:px-8">
        {/* 桌面侧栏 */}
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-[260px] shrink-0 overflow-y-auto border-r border-slate-200 py-6 pr-4 lg:block">
          <HelpSidebar
            activeId={doc.id}
            headings={headings}
            expandedGroups={expandedGroups}
            onToggleGroup={(g) =>
              setExpandedGroups((prev) => ({ ...prev, [g]: prev[g] === false }))
            }
          />
        </aside>

        <div className="min-w-0 flex-1 py-6 lg:pl-10 lg:pr-4">
          {/* 移动端目录 */}
          <div className="mb-4 lg:hidden">
            <button
              type="button"
              onClick={() => setMobileOpen((v) => !v)}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700"
            >
              <List className="h-4 w-4" />
              目录 · {doc.title}
              <ChevronDown className={`h-4 w-4 transition ${mobileOpen ? "rotate-180" : ""}`} />
            </button>
            {mobileOpen && (
              <div className="mt-2 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <HelpSidebar
                  activeId={doc.id}
                  headings={headings}
                  expandedGroups={expandedGroups}
                  onToggleGroup={(g) =>
                    setExpandedGroups((prev) => ({
                      ...prev,
                      [g]: prev[g] === false,
                    }))
                  }
                />
              </div>
            )}
          </div>

          <HelpArticle doc={doc} />
        </div>
      </div>
    </div>
  );
}

/** @deprecated 旧路由兼容 */
export const ApiDocsPlaceholderPage = HelpPage;
