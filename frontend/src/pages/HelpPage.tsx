import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronLeft, ChevronRight, List, Search } from "lucide-react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
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
import { getLocale, setLocale, t, type Locale } from "@/lib/i18n";

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

/** 帮助页内标题锚点滚动（SPA 下点目录不会自动跳位） */
function scrollToHelpHeading(hash: string, behavior: ScrollBehavior = "smooth") {
  const raw = hash.replace(/^#/, "").trim();
  if (!raw) return false;
  let id = raw;
  try {
    id = decodeURIComponent(raw);
  } catch {
    /* keep raw */
  }
  const el = document.getElementById(id);
  if (!el) return false;
  el.scrollIntoView({ behavior, block: "start" });
  return true;
}

function HelpSidebar({
  activeId,
  headingsByDoc,
  expandedGroups,
  expandedDocs,
  onToggleGroup,
  onToggleDoc,
}: {
  activeId: HelpDocId;
  headingsByDoc: Record<string, { id: string; text: string; level: 2 | 3 }[]>;
  expandedGroups: Record<string, boolean>;
  expandedDocs: Record<string, boolean>;
  onToggleGroup: (group: string) => void;
  onToggleDoc: (docId: HelpDocId) => void;
}) {
  const navigate = useNavigate();
  const [locale, setLocaleState] = useState<Locale>(() => getLocale());
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return HELP_DOCS;
    return HELP_DOCS.filter((d) => {
      if (d.title.toLowerCase().includes(q) || d.group.toLowerCase().includes(q)) return true;
      try {
        return loadHelpMarkdown(d.id).toLowerCase().includes(q);
      } catch {
        return false;
      }
    });
  }, [query]);
  const groups = useMemo(() => groupDocs(filtered), [filtered]);

  return (
    <nav className="help-sidebar text-sm" aria-label="帮助目录">
      <div className="mb-3 flex items-center justify-between border-b border-slate-200 pb-2 text-base font-bold text-slate-900">
        <span>{t("帮助文档", "Help", locale)}</span>
        <button
          type="button"
          onClick={() => {
            const next: Locale = locale === "en" ? "zh" : "en";
            setLocale(next);
            setLocaleState(next);
          }}
          aria-label={t("切换语言", "Switch language", locale)}
          className="rounded-md border border-slate-200 px-2 py-0.5 text-xs font-medium text-slate-500 hover:bg-slate-50"
        >
          {locale === "en" ? "中文" : "EN"}
        </button>
      </div>
      <label className="relative mb-3 block">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("搜索帮助文档…", "Search help…", locale)}
          aria-label="搜索帮助文档"
          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-7 pr-2 text-sm text-slate-800 outline-none focus:border-sky-300 focus:bg-white"
        />
      </label>
      {query.trim() && filtered.length === 0 && (
        <p className="px-2 py-1 text-xs text-slate-400">没有匹配的文档</p>
      )}
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
                  const docHeadings = headingsByDoc[doc.id] || [];
                  const docOpen = expandedDocs[doc.id] === true;
                  const rowClass = `flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left leading-snug ${
                    active
                      ? "bg-sky-50 font-medium text-sky-700"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`;
                  return (
                    <li key={doc.id}>
                      {docHeadings.length > 0 ? (
                        <button
                          type="button"
                          aria-expanded={docOpen}
                          onClick={() => {
                            const willOpen = !docOpen;
                            onToggleDoc(doc.id);
                            if (willOpen && !active) navigate(`/help/${doc.id}`);
                          }}
                          className={rowClass}
                        >
                          <span className="min-w-0">{doc.title}</span>
                          <ChevronDown
                            className={`h-3.5 w-3.5 shrink-0 text-slate-400 transition ${
                              docOpen ? "" : "-rotate-90"
                            }`}
                          />
                        </button>
                      ) : (
                        <Link to={`/help/${doc.id}`} className={rowClass}>
                          <span className="min-w-0">{doc.title}</span>
                        </Link>
                      )}
                      {docOpen && docHeadings.length > 0 && (
                        <ul className="mt-0.5 mb-1 space-y-0.5 border-l border-slate-100 ml-2 pl-1">
                          {docHeadings.map((h) => (
                            <li key={h.id}>
                              <Link
                                to={{ pathname: `/help/${doc.id}`, hash: h.id }}
                                onClick={(e) => {
                                  // 已在本篇时 RR 往往不滚屏，手动定位
                                  if (doc.id === activeId) {
                                    e.preventDefault();
                                    const href = `#${h.id}`;
                                    if (window.location.hash !== href) {
                                      window.history.pushState(null, "", href);
                                    }
                                    scrollToHelpHeading(h.id);
                                  }
                                }}
                                className={`block rounded px-2 py-1 text-xs leading-snug text-slate-500 hover:bg-slate-50 hover:text-sky-700 ${
                                  h.level === 3 ? "pl-4" : ""
                                }`}
                              >
                                {h.text}
                              </Link>
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
      <div className="mt-4 border-t border-slate-200 pt-3">
        <Link
          to="/support"
          className="flex items-center gap-2 rounded px-2 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
        >
          联系客服 / 提交工单
        </Link>
      </div>
    </nav>
  );
}

function HelpArticle({ doc }: { doc: HelpDocMeta }) {
  const md = useMemo(() => loadHelpMarkdown(doc.id), [doc.id]);
  const location = useLocation();
  const idx = HELP_DOCS.findIndex((d) => d.id === doc.id);
  const prev = idx > 0 ? HELP_DOCS[idx - 1] : null;
  const next = idx >= 0 && idx < HELP_DOCS.length - 1 ? HELP_DOCS[idx + 1] : null;

  useEffect(() => {
    const hash = location.hash;
    if (!hash) {
      window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
      return;
    }
    let tries = 0;
    const tick = () => {
      if (scrollToHelpHeading(hash) || tries++ > 30) return;
      window.setTimeout(tick, 16);
    };
    // 等 Markdown 标题进 DOM
    window.setTimeout(tick, 0);
  }, [doc.id, location.hash, md]);

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
  const headingsByDoc = useMemo(() => {
    const map: Record<string, { id: string; text: string; level: 2 | 3 }[]> = {};
    for (const d of HELP_DOCS) {
      map[d.id] = extractHelpHeadings(loadHelpMarkdown(d.id));
    }
    return map;
  }, []);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const d of HELP_DOCS) init[d.group] = true;
    return init;
  });
  // 多篇可同时展开章节目录；进入某篇时自动展开该篇
  const [expandedDocs, setExpandedDocs] = useState<Record<string, boolean>>(() => ({
    [docId]: true,
  }));

  useEffect(() => {
    setExpandedDocs((prev) => (prev[docId] ? prev : { ...prev, [docId]: true }));
  }, [docId]);

  const toggleGroup = (g: string) => {
    setExpandedGroups((prev) => ({
      ...prev,
      [g]: prev[g] === false,
    }));
  };

  const toggleDoc = (id: HelpDocId) => {
    setExpandedDocs((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const sidebar = (
    <HelpSidebar
      activeId={doc.id}
      headingsByDoc={headingsByDoc}
      expandedGroups={expandedGroups}
      expandedDocs={expandedDocs}
      onToggleGroup={toggleGroup}
      onToggleDoc={toggleDoc}
    />
  );

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-white">
      <div className="mx-auto flex max-w-[1440px] gap-0 px-4 sm:px-6 lg:px-8">
        {/* 桌面侧栏 */}
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-[260px] shrink-0 overflow-y-auto border-r border-slate-200 py-6 pr-4 lg:block">
          {sidebar}
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
                {sidebar}
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
