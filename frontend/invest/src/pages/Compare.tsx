import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Plus, Search, X } from "lucide-react";
import { api } from "../api";
import CompareView, { type ComparePayload } from "../components/CompareView";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader } from "../components";
import { displayIndustry } from "../lib";
import { useLocale } from "../i18n";

type CompareResponse = ComparePayload & {
  ok?: boolean;
  error?: string;
  unresolved?: string;
  suggestions?: Array<{ code: string; name: string }>;
};

export default function Compare() {
  const { t } = useLocale();
  const nav = useNavigate();
  const { a = "", b = "", c = "" } = useParams();
  const codes = [a, b, c].filter(Boolean);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);

  useEffect(() => {
    if (codes.length < 2) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    api<CompareResponse>(`/api/invest/compare?codes=${encodeURIComponent(codes.join(","))}`)
      .then((d) => {
        setData(d);
        if (!d.ok) setError(d.error || t("对比失败", "Comparison failed"));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.join(",")]);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      api<any>(`/api/invest/search?q=${encodeURIComponent(term)}`)
        .then((d) => setResults((d.results || []).filter((x: any) => x.type === "stock" && !codes.includes(x.id))))
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, codes.join(",")]);

  const add = (code: string) => {
    const next = [...codes, code].slice(0, 3);
    setQ("");
    setResults([]);
    nav(`/compare/${next.join("/")}`);
  };

  const remove = (index: number) => {
    const next = codes.filter((_, i) => i !== index);
    nav(next.length ? `/compare/${next.join("/")}` : "/compare");
  };

  return (
    <div className="page">
      <PageHeader
        title={t("多标的对比", "Stock comparison")}
        sub={t("最多 3 只 · 同口径差异，不判断谁更好", "Up to 3 names · like-for-like differences, without picking a winner")}
        back
        onBack={() => nav(-1)}
      />

      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {data?.suggestions?.length ? (
        <section className="card">
          <p className="hint">{t("未识别的标的，您想找的是不是：", "Could you mean one of these?")}</p>
          <div className="post-list">
            {data.suggestions.map((item) => (
              <button
                key={item.code}
                type="button"
                className="post-row"
                style={{ textAlign: "left" }}
                onClick={() => (data.unresolved ? add(item.code) : add(item.code))}
              >
                <div className="post-row-title">{item.name}</div>
                <div className="hint">{item.code}</div>
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {loading && !data ? <LoadingCards rows={3} /> : null}

      {data?.ok !== false && data?.items?.length ? (
        <div className="card compare-head">
          <div className="compare-head-names">
            {data.items.map((item, index) => (
              <div key={item.code}>
                <b>{item.name}</b>
                <span className="hint">{item.code} · {item.industry ? displayIndustry(item.industry) : "—"}</span>
                <button
                  className="compare-remove"
                  aria-label={t("移除", "Remove")}
                  onClick={() => remove(index)}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {data?.ok !== false && data?.items?.length ? <CompareView data={data} /> : null}

      {codes.length < 3 ? (
        <section className="card">
          <div className="card-title-row">
            <h2>{codes.length === 0 ? t("选择第一只", "Choose the first name") : codes.length < 2 ? t("再选一只开始对比", "Add a second name") : t("添加第三只（可选）", "Add a third name (optional)")}</h2>
            <span className="hint">{codes.length}/3</span>
          </div>
          <div className="compare-search">
            <Search size={15} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("输入代码或名称", "Enter a code or name")}
            />
            <Plus size={15} />
          </div>
          <div className="post-list">
            {results.map((it: any) => (
              <button key={it.id} type="button" className="post-row" style={{ textAlign: "left" }} onClick={() => add(it.id)}>
                <div className="post-row-title">{it.name}</div>
                <div className="hint">{it.id} · {it.industry ? displayIndustry(it.industry) : "—"}</div>
              </button>
            ))}
          </div>
          {!results.length ? <p className="hint">{t("搜索后选择要对比的标的。", "Search, then pick a stock to compare.")}</p> : null}
        </section>
      ) : null}

      {codes.length < 2 && !error ? (
        <EmptyState
          title={t("先选两只股票", "Pick two stocks first")}
          detail={t("对比行情、财务与估值；最多 3 只。", "Compare quotes, financials and valuation for up to 3 names.")}
        />
      ) : null}

      <Disclaimer>{t("对比仅描述数据差异，不构成投资建议。", "The comparison describes data differences only and is not investment advice.")}</Disclaimer>
      <button className="btn btn-ghost btn-sm" onClick={() => nav(-1)}><ArrowLeft size={14} /> {t("返回", "Back")}</button>
    </div>
  );
}
