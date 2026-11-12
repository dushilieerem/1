import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronUp, Info } from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { useLocale } from "../i18n";
import {
  directionLabel,
  factorCategoryName,
  factorFormula,
  factorPlain,
  factorSubName,
  fmtFactorValue,
  fmtSignedPct,
  trendClass,
  type FactorBoard,
  type FactorCategory,
  type FactorRow,
} from "../quant";

type Detail = FactorRow & {
  chosen_direction?: "high" | "low";
  explain: string;
  explain_en: string;
  conclusions: Array<{ key: string; label: string; label_en: string; text: string; text_en?: string }>;
  top: Array<{ code: string; name: string; value: number }>;
  bottom: Array<{ code: string; name: string; value: number }>;
  footer: string;
  data_date: string;
};

function DirectionTag({ row }: { row: FactorRow }) {
  const { t, locale } = useLocale();
  return (
    <Tag tone="gray">
      {t("方向", "Direction")}：{directionLabel(row, row.direction, locale)}
    </Tag>
  );
}

export default function QuantFactors() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [params] = useSearchParams();
  const [board, setBoard] = useState<FactorBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<"1m" | "1y">("1m");
  const [view, setView] = useState<"board" | "library">("board");
  const [intro, setIntro] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(params.get("open"));
  const [detailError, setDetailError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, string>>({});

  useEffect(() => {
    setError(null);
    api<FactorBoard>("/api/invest/quant/factors?range=1m")
      .then(setBoard)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!openKey || !board) return;
    loadDetail(openKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openKey, board]);

  const loadDetail = (key: string) => {
    setDetailError(null);
    setOpenKey(key);
    api<Detail>(`/api/invest/quant/factors/${encodeURIComponent(key)}`)
      .then(setDetail)
      .catch((e) => setDetailError(e.message));
  };

  const sorted = useMemo(() => {
    const factors = board?.factors || [];
    const key = range === "1m" ? "return_1m" : "return_1y";
    return [...factors].sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      return Number(bv) - Number(av);
    });
  }, [board, range]);

  const categories = useMemo<FactorCategory[]>(() => {
    if (board?.categories?.length) {
      const key = range === "1m" ? "return_1m" : "return_1y";
      return board.categories.map((cat) => ({
        ...cat,
        factors: [...cat.factors].sort((a, b) => {
          const av = a[key];
          const bv = b[key];
          if (av === null || av === undefined) return 1;
          if (bv === null || bv === undefined) return -1;
          return Number(bv) - Number(av);
        }),
      }));
    }
    return [];
  }, [board, range]);

  const pick = (cat: FactorCategory) => cat.factors.find((f) => f.key === selected[cat.key]) || cat.factors[0];
  const valueOf = (row: FactorRow | undefined) => (range === "1m" ? row?.return_1m : row?.return_1y);
  const createWithFactor = () => {
    if (!detail) return;
    const d = detail.chosen_direction || detail.direction;
    nav(`/quant/strategies?tab=quick&preset=${encodeURIComponent(detail.key)}:${d}`);
    setDetail(null);
  };
  const createWithTop = () => {
    const top = sorted[0];
    if (!top) return;
    nav(`/quant/strategies?tab=quick&preset=${encodeURIComponent(`${top.key}:${top.direction}`)}`);
  };
  const openFactor = (cat: FactorCategory, key: string) => {
    setSelected((prev) => ({ ...prev, [cat.key]: key }));
    setExpanded(null);
    loadDetail(key);
  };

  return (
    <div className="page quant-page">
      <PageHeader
        title={t("因子", "Factors")}
        sub={t("先看市场在奖励什么，再看单个因子能不能用", "First what the market rewards, then whether a factor is usable")}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant")}
      />

      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!board && !error ? <LoadingCards rows={4} /> : null}

      {board ? (
        <>
          <section className="card quant-style-card">
            <div className="card-title-row">
              <h2>{t("市场风格", "Market style")}</h2>
              <Tag tone={board.style.key === "attack" ? "red" : board.style.key === "defense" ? "blue" : "gray"}>
                {locale === "en" ? board.style.label_en : board.style.label}
              </Tag>
            </div>
            <p className="quant-style-sentence">{locale === "en" ? board.style.sentence_en : board.style.sentence}</p>
            <div className="quant-tags">
              {(locale === "en" ? board.style.tags_en : board.style.tags || []).map((tag) => (
                <Tag key={tag} tone="gray">{tag}</Tag>
              ))}
            </div>
            <p className="hint">{locale === "en" ? board.style.method_en : board.style.method}</p>
            <p className="hint">{locale === "en" ? board.style.note_en : board.style.note}</p>
          </section>

          <section className="card quant-intro">
            <button className="quant-intro-toggle" onClick={() => setIntro((v) => !v)} aria-expanded={intro}>
              <span className="row gap6"><Info size={15} /> {t("因子入门", "Factor basics")}</span>
              {intro ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
            {intro ? (
              <div className="quant-intro-body">
                <p>{t("因子就是把股票按某个特征打分：便宜、涨得好、波动小、赚钱多、增长快、成交活跃。", "A factor scores stocks on one characteristic: cheap, rising, low-volatility, profitable, growing, or liquid.")}</p>
                <p>{t("7 大类下共 27 个细分因子；同一大类里的因子相关但不相同。", "There are 27 sub-factors across 7 categories; factors within a category are related but not identical.")}</p>
                <p>{t("把当日股票按因子排队，前 20% 等权做多、后 20% 等权做空，收益差就是多空收益。它描述过去，不预测未来。", "Rank stocks each day, go equal-weight long the top 20% and short the bottom 20%; the spread is the long-short return. It describes the past, not the future.")}</p>
              </div>
            ) : null}
          </section>

          <div className="seg quant-view-seg">
            <button className={view === "board" ? "on" : ""} onClick={() => setView("board")}>{t("因子榜", "Factor board")}</button>
            <button className={view === "library" ? "on" : ""} onClick={() => setView("library")}>{t("因子库", "Factor library")}</button>
          </div>

          <div className="seg quant-range">
            <button className={range === "1m" ? "on" : ""} onClick={() => setRange("1m")}>{t("近 1 月", "Last month")}</button>
            <button className={range === "1y" ? "on" : ""} onClick={() => setRange("1y")}>{t("近 1 年", "Last year")}</button>
          </div>

          <p className="quant-board-meta">
            {range === "1m"
              ? t(
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · 近 1 月逐日累计多空 · ${board.meta.frequency}`,
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · daily long-short over the last month · ${board.meta.frequency_en || board.meta.frequency}`,
              )
              : t(
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · 近 1 年按月调仓、扣单边 0.1% · ${board.meta.frequency}`,
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · monthly long-short over the last year, 0.1% one-way cost · ${board.meta.frequency_en || board.meta.frequency}`,
              )}
          </p>

          {view === "board" ? (
            <div className="quant-category-list">
              {categories.map((cat) => {
                const row = pick(cat);
                const value = valueOf(row);
                const isOpen = expanded === cat.key;
                return (
                  <div className={`quant-category-card ${isOpen ? "open" : ""}`} key={cat.key}>
                    <div
                      className="quant-category-head"
                      role="button"
                      tabIndex={0}
                      aria-expanded={isOpen}
                      onClick={() => setExpanded(isOpen ? null : cat.key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setExpanded(isOpen ? null : cat.key);
                        }
                      }}
                    >
                      <div className="quant-category-main">
                        {row ? <b>{factorCategoryName(row, locale)}因子 · {factorSubName(row, locale)}</b> : <b>{locale === "en" ? cat.name_en : cat.name}</b>}
                        {row ? <small>{factorPlain(row, locale)}</small> : null}
                      </div>
                      <div className="quant-category-stats">
                        <b className={trendClass(value)}>{fmtSignedPct(value)}</b>
                        <small>{t("分位", "Pctl")} {row?.percentile == null ? "—" : `${row.percentile.toFixed(0)}%`}</small>
                      </div>
                      {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                    {isOpen ? (
                      <div className="quant-subfactor-list">
                        {cat.factors.map((f) => (
                          <button
                            className={`quant-subfactor-row ${row?.key === f.key ? "on" : ""}`}
                            key={f.key}
                            onClick={() => openFactor(cat, f.key)}
                          >
                            <span><b>{factorSubName(f, locale)}</b><small>{factorFormula(f, locale)}</small></span>
                            <span className="quant-subfactor-stats">
                              <b className={trendClass(valueOf(f))}>{fmtSignedPct(valueOf(f))}</b>
                              <small>{f.percentile == null ? "—" : `${f.percentile.toFixed(0)}%`}</small>
                            </span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="quant-library">
              {categories.map((cat) => (
                <section className="card quant-library-group" key={cat.key}>
                  <div className="card-title-row">
                    <h2>{locale === "en" ? cat.name_en : cat.name}</h2>
                    <span className="hint">{cat.factors.length} {t("个细分", "sub-factors")}</span>
                  </div>
                  {cat.factors.map((f) => (
                    <button className="quant-library-row" key={f.key} onClick={() => openFactor(cat, f.key)}>
                      <span className="quant-library-name">
                        <b>{factorSubName(f, locale)}</b>
                        <small>{factorFormula(f, locale)}</small>
                      </span>
                      <span className="quant-library-stats">
                        <b className={trendClass(valueOf(f))}>{fmtSignedPct(valueOf(f))}</b>
                        <small>{t("分位", "Pctl")} {f.percentile == null ? "—" : `${f.percentile.toFixed(0)}%`}</small>
                      </span>
                    </button>
                  ))}
                </section>
              ))}
            </div>
          )}

          <button className="btn btn-primary w100 quant-factor-cta" onClick={createWithTop}>
            {t("带着因子去建策略", "Build a strategy with this factor")} <ArrowRight size={15} />
          </button>

          {detailError ? <ErrorState message={detailError} onRetry={() => openKey && loadDetail(openKey)} /> : null}
          <p className="quant-foot">{board.disclaimer}</p>
        </>
      ) : null}

      <Sheet
        open={!!detail}
        onClose={() => setDetail(null)}
        title={detail ? factorSubName(detail, locale) : t("因子详情", "Factor detail")}
        sub={detail ? factorFormula(detail, locale) : undefined}
        footer={
          detail ? (
            <button className="btn btn-primary w100" onClick={createWithFactor}>
              {t("带着这个因子去建策略", "Build a strategy with this factor")} <ArrowRight size={15} />
            </button>
          ) : undefined
        }
      >
        {detail ? (
          <div className="quant-detail">
            <div className="quant-detail-head">
              <div>
                <span>{t("当前分位", "Current percentile")}</span>
                <b>{detail.percentile === null ? "—" : `${detail.percentile.toFixed(0)}%`}</b>
              </div>
              <div>
                <span>{t("近 20 日多空收益", "20-day long-short")}</span>
                <b className={trendClass(detail.return_1m)}>{fmtSignedPct(detail.return_1m)}</b>
              </div>
              <DirectionTag row={detail} />
            </div>
            <p>{locale === "en" ? detail.explain_en : detail.explain}</p>
            <div className="quant-conclusions">
              {detail.conclusions.map((c) => (
                <div className="quant-conclusion" key={c.key}>
                  <b>{locale === "en" ? c.label_en : c.label}</b>
                  <span>{locale === "en" ? c.text_en || c.text : c.text}</span>
                </div>
              ))}
            </div>
            <div className="quant-two-col">
              <div>
                <h4>{t("取值最高 5 只", "Top 5 by value")}</h4>
                {detail.top.map((x) => (
                  <div className="quant-mini-row" key={x.code}>
                    <button className="link-btn" onClick={() => nav(`/stock/${x.code}`)}>{x.name}</button>
                    <span>{fmtFactorValue(x.value, detail.unit, locale)}</span>
                  </div>
                ))}
              </div>
              <div>
                <h4>{t("取值最低 5 只", "Bottom 5 by value")}</h4>
                {detail.bottom.map((x) => (
                  <div className="quant-mini-row" key={x.code}>
                    <button className="link-btn" onClick={() => nav(`/stock/${x.code}`)}>{x.name}</button>
                    <span>{fmtFactorValue(x.value, detail.unit, locale)}</span>
                  </div>
                ))}
              </div>
            </div>
            <p className="quant-foot">{detail.footer}</p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
