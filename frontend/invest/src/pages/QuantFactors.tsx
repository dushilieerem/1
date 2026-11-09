import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronUp, Info } from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { useLocale } from "../i18n";
import {
  directionLabel,
  factorFormula,
  factorName,
  factorPlain,
  fmtFactorValue,
  fmtSignedPct,
  trendClass,
  type FactorBoard,
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

function DirectionTag({ row }: { row: FactorMetaLike }) {
  const { t, locale } = useLocale();
  return (
    <Tag tone="gray">
      {t("方向", "Direction")}：{directionLabel(row, row.direction, locale)}
    </Tag>
  );
}

type FactorMetaLike = FactorRow;

export default function QuantFactors() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [params] = useSearchParams();
  const [board, setBoard] = useState<FactorBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<"1m" | "1y">("1m");
  const [intro, setIntro] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(params.get("open"));
  const [detailError, setDetailError] = useState<string | null>(null);

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
            <p className="quant-style-sentence">
              {locale === "en" ? board.style.sentence_en : board.style.sentence}
            </p>
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
                <p>{t("把当日所有股票的打分排队，前 20% 等权做多、后 20% 等权做空，两者的收益差就是「多空收益」。它描述过去，不预测未来。", "Rank all stocks each day, go equal-weight long the top 20% and short the bottom 20%; the spread is the long-short return. It describes the past, not the future.")}</p>
                <p>{t("分位表示当前因子取值在自身历史中的位置，只描述大小，不表达好坏。", "The percentile shows where the current factor value sits in its own history; it describes size, not quality.")}</p>
              </div>
            ) : null}
          </section>

          <div className="seg quant-range">
            <button className={range === "1m" ? "on" : ""} onClick={() => setRange("1m")}>{t("近 1 月", "Last month")}</button>
            <button className={range === "1y" ? "on" : ""} onClick={() => setRange("1y")}>{t("近 1 年", "Last year")}</button>
          </div>

          <p className="quant-board-meta">
            {range === "1m"
              ? t(
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · 近 1 月逐日累计多空 · ${board.meta.frequency} · 分位按因子历史取值`,
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · daily long-short over the last month · ${board.meta.frequency_en || board.meta.frequency} · percentile vs. history`,
              )
              : t(
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · 近 1 年按月调仓、扣单边 0.1% · ${board.meta.frequency} · 分位按因子历史取值`,
                `${locale === "en" ? board.meta.universe_en || board.meta.universe : board.meta.universe} · monthly long-short over the last year, 0.1% one-way cost · ${board.meta.frequency_en || board.meta.frequency} · percentile vs. history`,
              )}
          </p>

          <div className="quant-factor-list">
            {sorted.map((row, index) => {
              const value = range === "1m" ? row.return_1m : row.return_1y;
              return (
                <button className="quant-factor-row" key={row.key} onClick={() => loadDetail(row.key)}>
                  <span className="factor-rank">{index + 1}</span>
                  <span className="factor-main">
                    <b>{factorName(row, locale)}</b>
                    <small>{factorPlain(row, locale)}</small>
                  </span>
                  <span className="factor-stats">
                    <b className={trendClass(value)}>{fmtSignedPct(value)}</b>
                    <small>{t("分位", "Pctl")} {row.percentile === null ? "—" : `${row.percentile.toFixed(0)}%`}</small>
                  </span>
                </button>
              );
            })}
          </div>

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
        title={detail ? factorName(detail, locale) : t("因子详情", "Factor detail")}
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
