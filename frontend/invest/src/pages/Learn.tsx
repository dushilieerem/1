import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, Search } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { useLocale } from "../i18n";

type Term = {
  id: string;
  term: string;
  term_en?: string;
  aliases?: string[];
  category: string;
  definition: string;
  how_to: string;
  range: string;
  example: string;
  plain?: string;
  misuse?: string;
  related?: string[];
  formula?: string;
  formula_vars?: string;
  calc_example?: string;
  misreads?: Array<{ myth: string; why: string }>;
  compare?: Array<{ term: string; denominator: string; when: string }>;
  where?: string;
};

const CATEGORIES: Array<{ zh: string; en: string }> = [
  { zh: "全部", en: "All" },
  { zh: "指标", en: "Indicators" },
  { zh: "估值", en: "Valuation" },
  { zh: "财务", en: "Financials" },
  { zh: "风险", en: "Risk" },
  { zh: "交易", en: "Trading" },
];

export default function Learn() {
  const { t } = useLocale();
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<Term[]>([]);
  const [categories, setCategories] = useState<string[]>(CATEGORIES.map((c) => c.zh));
  const [category, setCategory] = useState("全部");
  const [q, setQ] = useState("");
  const [active, setActive] = useState<Term | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Term[]>([]);
  const [suggestMessage, setSuggestMessage] = useState("");

  useEffect(() => {
    api<{ items: Term[]; categories?: string[] }>("/api/invest/glossary")
      .then((d) => {
        setItems(d.items || []);
        if (d.categories?.length) setCategories(["全部", ...d.categories]);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const termId = params.get("term");
    if (!termId || !items.length) return;
    const found = items.find((x) => x.id === termId || x.term === termId);
    if (found) setActive(found);
  }, [params, items]);

  const filtered = useMemo(() => {
    const text = q.trim().toLowerCase();
    return items.filter((item) => {
      if (category !== "全部" && item.category !== category) return false;
      if (!text) return true;
      return [item.term, item.definition, item.plain || "", item.misuse || "", ...(item.aliases || [])].join(" ").toLowerCase().includes(text);
    });
  }, [items, category, q]);

  useEffect(() => {
    const text = q.trim();
    if (!text || filtered.length) {
      setSuggestions([]);
      setSuggestMessage("");
      return;
    }
    const timer = window.setTimeout(() => {
      api<{ candidates?: Term[]; message?: string }>(`/api/invest/glossary/lookup?q=${encodeURIComponent(text)}`)
        .then((d) => {
          setSuggestions((d.candidates || []).slice(0, 3));
          setSuggestMessage(d.message || "");
        })
        .catch(() => setSuggestions([]));
    }, 260);
    return () => window.clearTimeout(timer);
  }, [q, filtered.length]);

  const categoryLabel = (value: string) => {
    const known = CATEGORIES.find((x) => x.zh === value);
    return known ? t(known.zh, known.en) : value;
  };

  const open = (term: Term) => {
    setExpanded(false);
    setActive(term);
    setParams({ term: term.id }, { replace: true });
  };
  const close = () => {
    setActive(null);
    setParams({}, { replace: true });
  };

  return (
    <div className="page">
      <PageHeader title={t("学习中心", "Learning center")} sub={t("术语随问随学 · 静态口径，不由模型生成", "Look up terms as you go · static definitions, not model-generated")} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading ? (
        <>
          <div className="seg" style={{ overflowX: "auto" }}>
            {categories.map((c) => {
              const known = CATEGORIES.find((x) => x.zh === c);
              return (
                <button key={c} className={category === c ? "on" : ""} onClick={() => setCategory(c)}>
                  {known ? t(known.zh, known.en) : c}
                </button>
              );
            })}
          </div>
          <label className="search-row">
            <Search size={16} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("搜索术语、别名或定义", "Search terms, aliases, or definitions")} />
          </label>
          {!filtered.length ? (
            suggestions.length ? (
              <section className="card term-suggest">
                <b>{suggestMessage || t("没找到完全匹配的词条，你要找的是不是：", "No exact match — did you mean:")}</b>
                <div className="term-suggest-list">
                  {suggestions.map((item) => (
                    <button key={item.id} type="button" className="chip" onClick={() => open(item)}>
                      {item.term}
                    </button>
                  ))}
                </div>
                <p className="hint">{t("点一个直接查看词条；定义来自词库，不由模型生成。", "Pick one to open the entry; definitions come from the glossary, not the model.")}</p>
              </section>
            ) : (
              <EmptyState title={t("没有匹配的术语", "No matching terms")} detail={t("换个关键词，或到「问 AI」里直接问。", "Try another keyword, or ask directly in “Ask AI”.")} />
            )
          ) : (
            <div className="post-list">
              {filtered.map((item) => (
                <button key={item.id} className="post-row" style={{ textAlign: "left" }} onClick={() => open(item)}>
                  <div className="post-row-title">{item.term}</div>
                  <div className="post-row-meta">
                    <Tag tone="gray">{categoryLabel(item.category)}</Tag>
                    {item.aliases?.length ? <span>{item.aliases.join(" / ")}</span> : null}
                  </div>
                  <div className="hint">{item.definition}</div>
                </button>
              ))}
            </div>
          )}
        </>
      ) : null}

      <Sheet
        open={!!active}
        onClose={close}
        title={active ? `${active.term}${active.term_en ? ` · ${active.term_en}` : ""}` : t("术语", "Term")}
        sub={active ? `${categoryLabel(active.category)} · ${t("术语库", "Glossary")}` : ""}
      >
        {active ? (
          <div className="term-detail">
            <p className="term-def">{active.definition}</p>
            {active.plain ? <div className="term-block"><b>{t("一句话理解", "In one sentence")}</b><p>{active.plain}</p></div> : null}
            <div className="term-block"><b>{t("怎么看", "How to read")}</b><p>{active.how_to}</p></div>
            <div className="term-block"><b>{t("参考区间", "Reference range")}</b><p>{active.range}</p></div>
            <div className="term-block"><b>{t("例子", "Example")}</b><p>{active.example}</p></div>

            {active.formula || active.misreads?.length || active.compare?.length || active.where ? (
              <button type="button" className="btn btn-ghost btn-sm term-expand" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
                {expanded ? t("收起更多", "Show less") : t("展开更多", "Show more")}
              </button>
            ) : null}

            {expanded ? (
              <div className="term-more">
                {active.formula ? (
                  <div className="term-block">
                    <b>{t("怎么算", "How it is calculated")}</b>
                    <p className="term-formula">{active.formula}</p>
                    {active.formula_vars ? <p className="hint">{active.formula_vars}</p> : null}
                    {active.calc_example ? <p>{t("算例：", "Example: ")}{active.calc_example}</p> : null}
                  </div>
                ) : null}
                {active.misreads?.length ? (
                  <div className="term-block">
                    <b>{t("常见误读", "Common misreads")}</b>
                    <ul className="term-misreads">
                      {active.misreads.map((item, i) => (
                        <li key={i}><b>{item.myth}</b><span>{item.why}</span></li>
                      ))}
                    </ul>
                  </div>
                ) : active.misuse ? (
                  <div className="term-block"><b>{t("常见误用", "Common misuse")}</b><p>{active.misuse}</p></div>
                ) : null}
                {active.compare?.length ? (
                  <div className="term-block">
                    <b>{t("相近概念", "Related concepts")}</b>
                    <div className="term-compare-wrap">
                      <table className="data-table term-compare">
                        <thead><tr><th>{t("指标", "Metric")}</th><th>{t("分母 / 口径", "Denominator")}</th><th>{t("什么时候用", "When to use")}</th></tr></thead>
                        <tbody>
                          {active.compare.map((row, i) => (
                            <tr key={i}><td>{row.term}</td><td>{row.denominator}</td><td>{row.when}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
                {active.where ? <div className="term-block"><b>{t("在哪看", "Where to find it")}</b><p>{active.where}</p></div> : null}
                {active.related?.length ? (
                  <p className="hint">{t("相关：", "Related: ")}{active.related.map((id) => items.find((x) => x.id === id)?.term || id).join(t("、", ", "))}</p>
                ) : null}
              </div>
            ) : null}

            <p className="hint">
              <BookOpen size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              {t("术语库口径 · 非投资建议；返回原页面会保留上下文。", "Glossary definitions · not investment advice; returning to the original page keeps its context.")}
            </p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
