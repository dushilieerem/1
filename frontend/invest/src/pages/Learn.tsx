import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, Search } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";

type Term = {
  id: string;
  term: string;
  aliases?: string[];
  category: string;
  definition: string;
  how_to: string;
  range: string;
  example: string;
  related?: string[];
};

const CATEGORIES = ["全部", "指标", "估值", "财务", "风险", "交易"];

export default function Learn() {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<Term[]>([]);
  const [categories, setCategories] = useState<string[]>(CATEGORIES);
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
      return [item.term, item.definition, ...(item.aliases || [])].join(" ").toLowerCase().includes(text);
    });
  }, [items, category, q]);

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
      <PageHeader title="学习中心" sub="术语随问随学 · 静态口径，不由模型生成" />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading ? (
        <>
          <div className="seg" style={{ overflowX: "auto" }}>
            {categories.map((c) => (
              <button key={c} className={category === c ? "on" : ""} onClick={() => setCategory(c)}>
                {c}
              </button>
            ))}
          </div>
          <label className="search-row">
            <Search size={16} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索术语、别名或定义" />
          </label>
          {!filtered.length ? (
            <EmptyState title="没有匹配的术语" detail="换个关键词，或到「问 AI」里直接问。" />
          ) : (
            <div className="post-list">
              {filtered.map((item) => (
                <button key={item.id} className="post-row" style={{ textAlign: "left" }} onClick={() => open(item)}>
                  <div className="post-row-title">{item.term}</div>
                  <div className="post-row-meta">
                    <Tag tone="gray">{item.category}</Tag>
                    {item.aliases?.length ? <span>{item.aliases.join(" / ")}</span> : null}
                  </div>
                  <div className="hint">{item.definition}</div>
                </button>
              ))}
            </div>
          )}
        </>
      ) : null}

      <Sheet open={!!active} onClose={close} title={active?.term || "术语"} sub={active ? `${active.category} · 术语库` : ""}>
        {active ? (
          <div className="term-detail">
            <p className="term-def">{active.definition}</p>
            <div className="term-block"><b>怎么看</b><p>{active.how_to}</p></div>
            <div className="term-block"><b>参考区间</b><p>{active.range}</p></div>
            <div className="term-block"><b>例子</b><p>{active.example}</p></div>
            {active.related?.length ? (
              <p className="hint">相关：{active.related.join("、")}</p>
            ) : null}
            <p className="hint">
              <BookOpen size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              术语库口径 · 非投资建议；返回原页面会保留上下文。
            </p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
