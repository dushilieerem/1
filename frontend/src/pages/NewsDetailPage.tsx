import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Building2,
  ExternalLink,
  Newspaper,
  Tag,
} from "lucide-react";
import { NEWS_CATEGORIES } from "@/data/nav";
import {
  enrichNewsBody,
  formatNewsDate,
  getNews,
  type NewsItem,
} from "@/lib/newsApi";
import { pushBrowseHistory } from "@/lib/browseHistory";

function catLabel(id: string) {
  return NEWS_CATEGORIES.find((c) => c.id === id)?.label || id;
}

const URL_RE = /https?:\/\/[^\s<>"')\]，。；、！？]+/g;

/** 正文里的 http(s) 链接触发为可点链接，长链可断行 */
function renderLinkified(text: string): ReactNode {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  const re = new RegExp(URL_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const raw = m[0];
    const trimmed = raw.replace(/[.,;:!?）】》」』]+$/g, "");
    const trail = raw.slice(trimmed.length);
    nodes.push(
      <a
        key={`u-${key++}`}
        href={trimmed}
        target="_blank"
        rel="noreferrer"
        className="inline break-all font-medium text-rose-700 underline decoration-rose-200 underline-offset-2 hover:text-rose-800"
      >
        {trimmed}
      </a>,
    );
    if (trail) nodes.push(trail);
    last = m.index + raw.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length ? <>{nodes}</> : text;
}

/** 站内资讯详情：宽版双栏，正文落本站。 */
export function NewsDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const from = (searchParams.get("from") || "").trim();
  const packQ = (searchParams.get("pack") || "").trim();
  const bundleQ = (searchParams.get("bundle") || "").trim();
  const backToGather = from === "gather" || from.startsWith("/ai/gather");
  const backToIdea = from === "idea" || from.startsWith("/ai/idea");
  const backLabel = backToGather
    ? "返回证据包"
    : backToIdea
      ? "返回研究假设"
      : "返回资讯";
  const ideaBackPath = (() => {
    if (!backToIdea) return "/ai/idea";
    const q = new URLSearchParams();
    if (packQ) q.set("pack", packQ);
    if (bundleQ) q.set("bundle", bundleQ);
    const s = q.toString();
    return s ? `/ai/idea?${s}` : "/ai/idea";
  })();
  const [item, setItem] = useState<NewsItem | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!id) {
      setErr("无效资讯 id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setErr(null);
    void getNews(id)
      .then(async (it) => {
        if (cancelled) return;
        let finalItem = it;
        // 东财等：正文过短时尝试补抓
        const short =
          !it.body ||
          it.body.trim().length < 200 ||
          it.body.trim() === (it.summary || "").trim();
        if (short && it.source === "eastmoney" && it.url) {
          try {
            const en = await enrichNewsBody(it.id);
            if (en.enriched) {
              finalItem = await getNews(id);
            }
          } catch {
            /* 补抓失败仍展示原条目 */
          }
        }
        if (cancelled) return;
        setItem(finalItem);
        pushBrowseHistory({
          kind: "news",
          id: finalItem.id,
          title: finalItem.title,
          href: `/news/${finalItem.id}`,
          subtitle: finalItem.sourceLabel || finalItem.source,
        });
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setItem(null);
          setErr(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const { lead, paragraphs, footnote } = useMemo(() => {
    if (!item) return { lead: "", paragraphs: [] as string[], footnote: "" };
    const summary = (item.summary || "").trim();
    let raw = (item.body || "").trim();
    if (!raw) raw = summary;
    let note = "";
    const noteMatch = raw.match(/（站内演示正文）[^\n]*/);
    if (noteMatch) {
      note = noteMatch[0];
      raw = raw.replace(noteMatch[0], "").trim();
    }

    const collapse = (s: string) => s.replace(/\s+/g, " ").trim();
    const sumC = collapse(summary);
    const rawC = collapse(raw);

    const splitParas = (text: string) => {
      const parts = text
        .split(/\n{2,}/)
        .map((p) => p.trim())
        .filter(Boolean);
      // 正文里连续/重复段落去重（东财摘要被再写进 body 时常见）
      const out: string[] = [];
      const seen = new Set<string>();
      for (const p of parts) {
        const key = collapse(p);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        out.push(p);
      }
      return out;
    };

    // 摘要≈正文，或摘要只是正文压缩/截断：不单独展示 lead
    const summaryRedundant =
      !!sumC &&
      !!rawC &&
      (rawC === sumC ||
        rawC.startsWith(sumC) ||
        sumC === rawC ||
        (sumC.length >= 40 &&
          rawC.includes(sumC.slice(0, Math.min(120, sumC.length)))));

    let leadText = "";
    let paras: string[];

    if (!summary || summaryRedundant) {
      paras = splitParas(raw || summary);
      if (paras.length === 0 && (raw || summary)) {
        paras = [raw || summary];
      }
    } else {
      let rest = raw;
      if (raw.startsWith(summary)) {
        rest = raw.slice(summary.length).trim();
      }
      paras = splitParas(rest || raw);
      if (paras.length === 0 && raw) paras = [raw];
      leadText = summary;
    }

    // 兜底：lead 与任一正文段实质相同则丢掉 lead（截图里粉条+同文段落）
    if (leadText) {
      const leadC = collapse(leadText);
      if (paras.some((p) => collapse(p) === leadC || collapse(p).startsWith(leadC))) {
        leadText = "";
      }
    }

    return {
      lead: leadText,
      paragraphs: paras,
      footnote: note,
    };
  }, [item]);

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#f6f4f1]">
      <div className="border-b border-slate-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] items-center px-3 py-2.5 sm:px-6 sm:py-3">
          <button
            type="button"
            onClick={() => {
              if (backToGather) navigate("/ai/gather");
              else if (backToIdea) navigate(ideaBackPath);
              else if (from.startsWith("/")) navigate(from);
              else navigate("/news");
            }}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-rose-700"
          >
            <ArrowLeft className="h-4 w-4" />
            {backLabel}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1440px] px-3 py-4 sm:px-6 sm:py-8">
        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-white px-4 py-16 text-center text-sm text-slate-400 sm:rounded-3xl sm:px-8 sm:py-24">
            加载中…
          </div>
        ) : err || !item ? (
          <div className="rounded-2xl border border-rose-100 bg-white px-4 py-16 text-center text-sm text-rose-600 sm:rounded-3xl sm:px-8 sm:py-24">
            {err || "未找到该资讯"}
          </div>
        ) : (
          <div className="grid gap-4 sm:gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
            <article className="min-w-0 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm sm:rounded-3xl">
              <header className="border-b border-rose-100 bg-gradient-to-br from-rose-50 via-white to-amber-50/80 px-4 py-6 sm:px-8 sm:py-10 lg:px-12 lg:py-12">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 sm:mb-4">
                  <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-1 font-semibold text-rose-800">
                    <Newspaper className="h-3.5 w-3.5" />
                    {item.sourceLabel}
                  </span>
                  <span>{formatNewsDate(item.publishedAt)}</span>
                  <span className="text-slate-300">·</span>
                  <span>{catLabel(item.category)}</span>
                </div>
                <h1 className="font-news max-w-4xl text-xl font-semibold leading-snug tracking-tight text-slate-900 sm:text-3xl lg:text-4xl">
                  {item.title}
                </h1>
              </header>

              <div className="px-4 py-6 sm:px-8 sm:py-10 lg:px-12 lg:py-12">
                {/* 手机：题材/标的横滑，标的直达 K 线概览 */}
                {(item.themes.length > 0 || item.symbols.length > 0) && (
                  <div className="mb-5 -mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:mb-8 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0 lg:hidden">
                    {item.themes.map((t) => (
                      <span
                        key={t}
                        className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[#faf6f3] px-2.5 py-1 text-xs font-medium text-rose-800 ring-1 ring-rose-100 sm:px-3 sm:py-1.5 sm:text-sm"
                      >
                        <Tag className="h-3.5 w-3.5" />
                        {t}
                      </span>
                    ))}
                    {item.symbols.map((sym) => (
                      <Link
                        key={sym}
                        to={`/data/symbol/${encodeURIComponent(sym)}?from=news&newsId=${encodeURIComponent(String(item.id))}`}
                        className="inline-flex shrink-0 items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-800 hover:border-rose-300 sm:px-3 sm:py-1.5 sm:text-sm"
                      >
                        <Building2 className="h-3.5 w-3.5" />
                        {sym}
                        <span className="font-normal opacity-70">K线</span>
                      </Link>
                    ))}
                  </div>
                )}

                {/* 桌面：顶栏标签 */}
                {(item.themes.length > 0 || item.symbols.length > 0) && (
                  <div className="mb-8 hidden flex-wrap gap-2 lg:flex">
                    {item.themes.map((t) => (
                      <span
                        key={t}
                        className="inline-flex items-center gap-1 rounded-full bg-[#faf6f3] px-3 py-1.5 text-sm font-medium text-rose-800 ring-1 ring-rose-100"
                      >
                        <Tag className="h-3.5 w-3.5" />
                        {t}
                      </span>
                    ))}
                    {item.symbols.map((sym) => (
                      <Link
                        key={sym}
                        to={`/data/symbol/${encodeURIComponent(sym)}?from=news&newsId=${encodeURIComponent(String(item.id))}`}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:border-rose-300 hover:text-rose-700"
                      >
                        <Building2 className="h-3.5 w-3.5" />
                        {sym}
                      </Link>
                    ))}
                  </div>
                )}

                {lead ? (
                  <p className="mb-6 break-words border-l-4 border-rose-500 pl-3 text-base font-medium leading-relaxed text-slate-800 sm:mb-8 sm:pl-4 sm:text-lg">
                    {renderLinkified(lead)}
                  </p>
                ) : null}

                <div className="font-news max-w-none space-y-4 break-words text-[15px] leading-7 text-slate-800 sm:space-y-5 sm:text-[17px] sm:leading-8">
                  {paragraphs.length > 0 ? (
                    paragraphs.map((p, i) => (
                      <p key={i} className="whitespace-pre-wrap break-words">
                        {renderLinkified(p)}
                      </p>
                    ))
                  ) : (
                    <p className="text-slate-500">暂无更多正文，可查看源站原文。</p>
                  )}
                </div>

                {footnote ? (
                  <p className="mt-8 text-xs leading-relaxed text-slate-400 sm:mt-10">{footnote}</p>
                ) : null}

                {item.url ? (
                  <div className="mt-8 border-t border-slate-100 pt-5 sm:mt-10 sm:pt-6">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 break-all text-sm font-medium text-slate-500 hover:text-rose-700"
                    >
                      查看源站原文
                      <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                    </a>
                  </div>
                ) : null}
              </div>
            </article>

            <aside className="space-y-3 sm:space-y-4 lg:sticky lg:top-24 lg:self-start">
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm sm:rounded-3xl sm:p-5">
                <h2 className="mb-3 text-sm font-bold text-slate-900">关联标的</h2>
                {item.symbols.length > 0 ? (
                  <ul className="space-y-2">
                    {item.symbols.map((sym) => (
                      <li key={sym}>
                        <Link
                          to={`/data/symbol/${encodeURIComponent(sym)}?from=news&newsId=${encodeURIComponent(String(item.id))}`}
                          className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-800 hover:bg-rose-50 hover:text-rose-700"
                        >
                          <Building2 className="h-4 w-4 text-rose-600" />
                          <span className="min-w-0 truncate">{sym}</span>
                          <span className="ml-auto shrink-0 text-xs font-normal text-rose-600">
                            看 K 线
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">本条暂无关联代码</p>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm sm:rounded-3xl sm:p-5">
                <h2 className="mb-3 text-sm font-bold text-slate-900">题材</h2>
                {item.themes.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {item.themes.map((t) => (
                      <span
                        key={t}
                        className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-400">暂无题材标签</p>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 text-sm text-slate-600 shadow-sm sm:rounded-3xl sm:p-5">
                <div className="mb-1 font-bold text-slate-900">来源</div>
                <div>{item.sourceLabel}</div>
                <div className="mt-3 mb-1 font-bold text-slate-900">分类</div>
                <div>{catLabel(item.category)}</div>
              </div>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
