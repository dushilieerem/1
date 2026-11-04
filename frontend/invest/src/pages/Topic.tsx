import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, ChevronRight, Share2 } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import { useLocale } from "../i18n";
import GlossarySheet from "../GlossarySheet";

export default function Topic() {
  const { t } = useLocale();
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [glossary, setGlossary] = useState(false);
  const [newsOpen, setNewsOpen] = useState(false);

  const load = () => {
    setError(null);
    api(`/api/invest/topic/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, [id]);

  if (error) {
    return (
      <div className="page">
        <PageHeader title={t("热点", "Trending")} back onBack={() => nav(-1)} />
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <PageHeader title={t("热点", "Trending")} back onBack={() => nav(-1)} />
        <LoadingCards rows={4} />
      </div>
    );
  }

  const vp = Number(data.valuationPercentile ?? 0);
  const tp = Number(data.turnoverPercentile ?? 0);
  const headline = vp >= 80
    ? t("热度在，估值也在高位", "Heat is here, and so is a rich valuation")
    : vp >= 50
      ? t("热度在，估值中性", "Heat is here, valuation is neutral")
      : t("热度在，估值不算贵", "Heat is here, valuation is not expensive");
  const context = vp >= 80
    ? t("估值与拥挤度都在高位，历史上这种组合往往不是“便宜”的位置。", "Both valuation and crowding are elevated; historically this combination has not been a \"cheap\" spot.")
    : vp >= 50
      ? t("估值中性、拥挤度偏高，历史上这种组合的内部分化较大。", "Valuation is neutral but crowding is high; historically this combination has seen wide internal dispersion.")
      : t("估值不高，但拥挤度偏高；历史上这种组合的收益分布仍不占优。", "Valuation is not high but crowding is elevated; historically the return distribution of this combination has still been unfavorable.");

  return (
    <div className="page topic-page">
      <PageHeader
        title={t("热点深读", "Trend deep dive")}
        sub={t("板块数据 · 非投资建议", "Sector data · Not investment advice")}
        back
        onBack={() => nav(-1)}
        right={
          <button className="round-btn" aria-label={t("分享", "Share")} onClick={() => navigator.clipboard?.writeText(location.href)}>
            <Share2 size={18} />
          </button>
        }
      />

      <div className="topic-tags">
        <Tag tone="red">{t("行业", "Sector")} · {data.name}</Tag>
        <Tag tone="amber">{t(`估值 ${data.valuationPercentile?.toFixed?.(0)}% 分位`, `Valuation percentile ${data.valuationPercentile?.toFixed?.(0)}%`)}</Tag>
        <Tag tone="gray">{data.isDemo ? t("主题演示", "Thematic demo") : t("等权代理", "Equal-weight proxy")} · {data.updatedAt?.slice?.(0, 10) || "2026-10-23"}</Tag>
      </div>
      <h1 className="topic-title">{data.name}{t("：", ": ")}{headline}</h1>
      <p className="topic-desc">{data.summary}</p>

      <section className="card">
        <div className="card-title-row">
          <h2>{t("关键事实", "Key facts")}</h2>
          <span className="hint">{t("可回源", "Traceable sources")}</span>
        </div>
        <div className="evidence-list">
          {data.facts.map((f: any, i: number) => (
            <div className="evidence" key={i}>
              <b>[{i + 1}]</b>
              <div>
                <p>{f.detail}</p>
                <span>{f.title} · {f.source} · {f.date}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card guard-card">
        <div className="guard-line">
          <AlertTriangle size={16} /> {t("你现在正在追高吗？", "Are you chasing a high?")}
        </div>
        <p className="muted">
          {t(`热度 ${data.heat?.toFixed?.(0)} · 估值 ${vp.toFixed(0)}% 分位 · 拥挤度 ${tp.toFixed(0)}% 分位。${context}`, `Heat ${data.heat?.toFixed?.(0)} · valuation ${vp.toFixed(0)}th percentile · crowding ${tp.toFixed(0)}th percentile. ${context}`)}
        </p>
        <div className="base-grid">
          <div className="base-cell">
            <span>{t("未来 20 日收益中位数", "Median 20-day forward return")}</span>
            <b className={data.baseRate.medianReturn >= 0 ? "up" : "down"}>{fmtPct(data.baseRate.medianReturn, 1)}</b>
          </div>
          <div className="base-cell">
            <span>{t("未来 20 日最大回撤中位数", "Median 20-day forward max drawdown")}</span>
            <b className="down">{fmtPct(data.baseRate.maxDrawdown, 1)}</b>
          </div>
          <div className="base-cell">
            <span>{t("跑赢概率", "Outperformance probability")}</span>
            <b>{data.baseRate.winRate?.toFixed?.(0)}%</b>
          </div>
          <div className="base-cell">
            <span>{t("样本", "Sample")}</span>
            <b>{data.baseRate.sample} {t("次", "obs.")}</b>
          </div>
        </div>
        <div className="hint">{data.baseRate.period} · {t("历史分布不是预测，样本偏差需考虑。", "Historical distributions are not forecasts; consider sample bias.")}</div>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>{t("关键点", "Key points")}</h2><span className="hint">{t("规则摘要", "Rule summary")}</span></div>
        <ul className="bullet-list">
          {data.keyPoints.map((p: string, i: number) => <li key={i}>{p}</li>)}
        </ul>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>{t("风险", "Risks")}</h2><span className="hint">{t("不是“不涨”，而是“定价了多少”", "It is not about \"not rising\", but about \"how much is priced in\"")}</span></div>
        {data.risks.map((r: any, i: number) => (
          <div className="risk-item" key={i}>
            <AlertTriangle size={16} />
            <div><b>{r.title}</b><p>{r.detail}</p></div>
          </div>
        ))}
      </section>

      <section className="card">
        <div className="card-title-row">
          <h2>{t("相关标的", "Related stocks")}</h2>
          <span className="hint">{data.stocks.length} {t("只", "stocks")}</span>
        </div>
        <div className="chips">
          {data.stocks.map((s: any) => (
            <button className="stock-chip" key={s.code} onClick={() => nav(`/stock/${s.code}`)}>
              {s.name} <em className={s.changePct >= 0 ? "up" : "down"}>{fmtPct(s.changePct)}</em>
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card-title-row">
          <h2>{t("相关资讯", "Related news")}</h2>
          <button className="link-btn" onClick={() => setNewsOpen(true)}>{t("全部", "All")} <ChevronRight size={14} /></button>
        </div>
        <div className="news-list">
          {data.news.slice(0, 3).map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <span>{n.source} · {n.published_at}</span>
            </a>
          ))}
        </div>
      </section>

      <Disclaimer>
        {data.isDemo
          ? t("主题指数与 base rate 为演示数据；相关个股为收盘数据。", "The thematic index and base rates are demo data; related stocks use closing data.")
          : t("主题指数为成分股等权代理（非官方指数）；相关个股为收盘数据；", "The thematic index is an equal-weight proxy of constituents (not an official index); related stocks use closing data;")}
        {" "}
        {data.newsIsDemo ? t("资讯为演示。", "News is demo data.") : t("相关资讯为公开标题+链接。", "Related news are public headlines and links.")}
        {" "}
        {t("不构成投资建议。", "Not investment advice.")}
      </Disclaimer>

      <div className="bottom-cta">
        <button className="btn btn-ghost" onClick={() => setGlossary(true)}>{t("查术语", "Glossary")}</button>
        <button className="btn btn-primary" onClick={() => data.stocks[0] && nav(`/stock/${data.stocks[0].code}`)}>
          {t("看相关个股", "View related stocks")} <ArrowRight size={16} />
        </button>
      </div>

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} />
      <Sheet open={newsOpen} onClose={() => setNewsOpen(false)} title={t("主题资讯", "Thematic news")} sub={t("标题 + 链接 · 非投资建议", "Headlines + links · Not investment advice")}>
        <div className="news-list">
          {data.news.map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <span>{n.source} · {n.published_at}</span>
            </a>
          ))}
        </div>
      </Sheet>
    </div>
  );
}
