import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, Search } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { useLocale } from "../i18n";

type Term = {
  id: string;
  term: string;
  aliases?: string[];
  category: string;
  definition: string;
  how_to: string;
  range: string;
  example: string;
  plain?: string;
  misuse?: string;
  related?: string[];
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const categoryLabel = (value: string) => {
    const known = CATEGORIES.find((x) => x.zh === value);
    return known ? t(known.zh, known.en) : value;
  };

  const open = (term: Term) => {
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
            <EmptyState title={t("没有匹配的术语", "No matching terms")} detail={t("换个关键词，或到「问 AI」里直接问。", "Try another keyword, or ask directly in “Ask AI”.")} />
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

      <Sheet open={!!active} onClose={close} title={active?.term || t("术语", "Term")} sub={active ? `${categoryLabel(active.category)} · ${t("术语库", "Glossary")}` : ""}>
        {active ? (
          <div className="term-detail">
            <p className="term-def">{active.definition}</p>
            {active.plain ? <div className="term-block"><b>{t("一句话理解", "In one sentence")}</b><p>{active.plain}</p></div> : null}
            <div className="term-block"><b>{t("怎么看", "How to read")}</b><p>{active.how_to}</p></div>
            <div className="term-block"><b>{t("参考区间", "Reference range")}</b><p>{active.range}</p></div>
            <div className="term-block"><b>{t("例子", "Example")}</b><p>{active.example}</p></div>
            {active.misuse ? <div className="term-block"><b>{t("常见误用", "Common misuse")}</b><p>{active.misuse}</p></div> : null}
            {active.related?.length ? (
              <p className="hint">{t("相关：", "Related: ")}{active.related.map((id) => items.find((x) => x.id === id)?.term || id).join(t("、", ", "))}</p>
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
