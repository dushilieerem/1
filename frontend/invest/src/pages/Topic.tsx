import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, ChevronRight, Share2 } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import GlossarySheet from "../GlossarySheet";

export default function Topic() {
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
        <PageHeader title="热点" back onBack={() => nav(-1)} />
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <PageHeader title="热点" back onBack={() => nav(-1)} />
        <LoadingCards rows={4} />
      </div>
    );
  }

  const vp = Number(data.valuationPercentile ?? 0);
  const tp = Number(data.turnoverPercentile ?? 0);
  const headline = vp >= 80 ? "热度在，估值也在高位" : vp >= 50 ? "热度在，估值中性" : "热度在，估值不算贵";
  const context = vp >= 80
    ? "估值与拥挤度都在高位，历史上这种组合往往不是“便宜”的位置。"
    : vp >= 50
      ? "估值中性、拥挤度偏高，历史上这种组合的内部分化较大。"
      : "估值不高，但拥挤度偏高；历史上这种组合的收益分布仍不占优。";

  return (
    <div className="page topic-page">
      <PageHeader
        title="热点深读"
        sub="板块数据 · 非投资建议"
        back
        onBack={() => nav(-1)}
        right={
          <button className="round-btn" aria-label="分享" onClick={() => navigator.clipboard?.writeText(location.href)}>
            <Share2 size={18} />
          </button>
        }
      />

      <div className="topic-tags">
        <Tag tone="red">行业 · {data.name}</Tag>
        <Tag tone="amber">估值 {data.valuationPercentile?.toFixed?.(0)}% 分位</Tag>
        <Tag tone="gray">{data.isDemo ? "主题演示" : "等权代理"} · {data.updatedAt?.slice?.(0, 10) || "2026-10-23"}</Tag>
      </div>
      <h1 className="topic-title">{data.name}：{headline}</h1>
      <p className="topic-desc">{data.summary}</p>

      <section className="card">
        <div className="card-title-row">
          <h2>关键事实</h2>
          <span className="hint">可回源</span>
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
          <AlertTriangle size={16} /> 你现在正在追高吗？
        </div>
        <p className="muted">
          热度 {data.heat?.toFixed?.(0)}、估值 {vp.toFixed(0)}% 分位、拥挤度 {tp.toFixed(0)}% 分位。{context}
        </p>
        <div className="base-grid">
          <div className="base-cell">
            <span>未来 20 日收益中位数</span>
            <b className={data.baseRate.medianReturn >= 0 ? "up" : "down"}>{fmtPct(data.baseRate.medianReturn, 1)}</b>
          </div>
          <div className="base-cell">
            <span>未来 20 日最大回撤中位数</span>
            <b className="down">{fmtPct(data.baseRate.maxDrawdown, 1)}</b>
          </div>
          <div className="base-cell">
            <span>跑赢概率</span>
            <b>{data.baseRate.winRate?.toFixed?.(0)}%</b>
          </div>
          <div className="base-cell">
            <span>样本</span>
            <b>{data.baseRate.sample} 次</b>
          </div>
        </div>
        <div className="hint">{data.baseRate.period} · 历史分布不是预测，样本偏差需考虑。</div>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>关键点</h2><span className="hint">规则摘要</span></div>
        <ul className="bullet-list">
          {data.keyPoints.map((p: string, i: number) => <li key={i}>{p}</li>)}
        </ul>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>风险</h2><span className="hint">不是“不涨”，而是“定价了多少”</span></div>
        {data.risks.map((r: any, i: number) => (
          <div className="risk-item" key={i}>
            <AlertTriangle size={16} />
            <div><b>{r.title}</b><p>{r.detail}</p></div>
          </div>
        ))}
      </section>

      <section className="card">
        <div className="card-title-row">
          <h2>相关标的</h2>
          <span className="hint">{data.stocks.length} 只</span>
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
          <h2>相关资讯</h2>
          <button className="link-btn" onClick={() => setNewsOpen(true)}>全部 <ChevronRight size={14} /></button>
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

      <Disclaimer>{data.isDemo ? "主题指数与 base rate 为演示数据；相关个股为收盘数据。" : "主题指数为成分股等权代理（非官方指数）；相关个股为收盘数据；"}{data.newsIsDemo ? "资讯为演示。" : "相关资讯为公开标题+链接。"} 不构成投资建议。</Disclaimer>

      <div className="bottom-cta">
        <button className="btn btn-ghost" onClick={() => setGlossary(true)}>查术语</button>
        <button className="btn btn-primary" onClick={() => data.stocks[0] && nav(`/stock/${data.stocks[0].code}`)}>
          看相关个股 <ArrowRight size={16} />
        </button>
      </div>

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} />
      <Sheet open={newsOpen} onClose={() => setNewsOpen(false)} title="主题资讯" sub="标题 + 链接 · 非投资建议">
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
