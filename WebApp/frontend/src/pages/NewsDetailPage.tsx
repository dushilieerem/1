import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
  formatNewsTime,
  getNews,
  type NewsItem,
} from "@/lib/newsApi";
import { pushBrowseHistory } from "@/lib/browseHistory";

function catLabel(id: string) {
  return NEWS_CATEGORIES.find((c) => c.id === id)?.label || id;
}

function formatFullTime(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day} ${formatNewsTime(iso)}`;
}

/** 站内资讯详情：宽版双栏，正文落本站。 */
export function NewsDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
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
        <div className="mx-auto flex max-w-[1440px] items-center px-6 py-3">
          <button
            type="button"
            onClick={() => navigate("/news")}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-rose-700"
          >
            <ArrowLeft className="h-4 w-4" />
            返回资讯
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1440px] px-6 py-8">
        {loading ? (
          <div className="rounded-3xl border border-slate-200 bg-white px-8 py-24 text-center text-sm text-slate-400">
            加载中…
          </div>
        ) : err || !item ? (
          <div className="rounded-3xl border border-rose-100 bg-white px-8 py-24 text-center text-sm text-rose-600">
            {err || "未找到该资讯"}
          </div>
        ) : (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
            <article className="min-w-0 overflow-hidden rounded-3xl border border-slate-200/90 bg-white shadow-sm">
              <header className="border-b border-rose-100 bg-gradient-to-br from-rose-50 via-white to-amber-50/80 px-8 py-10 sm:px-12 sm:py-12">
                <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-1 font-semibold text-rose-800">
                    <Newspaper className="h-3.5 w-3.5" />
                    {item.sourceLabel}
                  </span>
                  <span>{formatFullTime(item.publishedAt)}</span>
                  <span className="text-slate-300">·</span>
                  <span>{catLabel(item.category)}</span>
                </div>
                <h1 className="font-news max-w-4xl text-3xl font-semibold leading-snug tracking-tight text-slate-900 sm:text-4xl">
                  {item.title}
                </h1>
              </header>

              <div className="px-8 py-10 sm:px-12 sm:py-12">
                {(item.themes.length > 0 || item.symbols.length > 0) && (
                  <div className="mb-8 flex flex-wrap gap-2">
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
                        to={`/data/symbol/${encodeURIComponent(sym)}`}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:border-rose-300 hover:text-rose-700"
                      >
                        <Building2 className="h-3.5 w-3.5" />
                        {sym}
                      </Link>
                    ))}
                  </div>
                )}

                {lead ? (
                  <p className="mb-8 border-l-4 border-rose-500 pl-4 text-lg font-medium leading-relaxed text-slate-800">
                    {lead}
                  </p>
                ) : null}

                <div className="font-news max-w-none space-y-5 text-[17px] leading-8 text-slate-800">
                  {paragraphs.length > 0 ? (
                    paragraphs.map((p, i) => (
                      <p key={i} className="whitespace-pre-wrap">
                        {p}
                      </p>
                    ))
                  ) : (
                    <p className="text-slate-500">暂无更多正文，可查看源站原文。</p>
                  )}
                </div>

                {footnote ? (
                  <p className="mt-10 text-xs leading-relaxed text-slate-400">{footnote}</p>
                ) : null}

                {item.url ? (
                  <div className="mt-10 border-t border-slate-100 pt-6">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-rose-700"
                    >
                      查看源站原文
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                ) : null}
              </div>
            </article>

            <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
              <div className="rounded-3xl border border-slate-200/90 bg-white p-5 shadow-sm">
                <h2 className="mb-3 text-sm font-bold text-slate-900">关联标的</h2>
                {item.symbols.length > 0 ? (
                  <ul className="space-y-2">
                    {item.symbols.map((sym) => (
                      <li key={sym}>
                        <Link
                          to={`/data/symbol/${encodeURIComponent(sym)}`}
                          className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-800 hover:bg-rose-50 hover:text-rose-700"
                        >
                          <Building2 className="h-4 w-4 text-rose-600" />
                          {sym}
                          <span className="ml-auto text-xs font-normal text-slate-400">K 线</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">本条暂无关联代码</p>
                )}
              </div>

              <div className="rounded-3xl border border-slate-200/90 bg-white p-5 shadow-sm">
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

              <div className="rounded-3xl border border-slate-200/90 bg-white p-5 text-sm text-slate-600 shadow-sm">
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
