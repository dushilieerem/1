import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Bell, BookOpen, ChevronRight, Search, Sparkles } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, LoadingCards, SectionHead, Sparkline, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import GlossarySheet from "../GlossarySheet";
import AiPanel from "../components/AiPanel";

type HomeData = any;

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [glossary, setGlossary] = useState(false);

  const load = () => {
    setError(null);
    api<HomeData>("/api/invest/home")
      .then(setData)
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const openLink = (link: any) => {
    if (!link) return;
    if (link.type === "stock") nav(`/stock/${link.id}`);
    else if (link.type === "topic") nav(`/topic/${link.id}`);
    else if (link.type === "portfolio") nav("/portfolio");
  };

  return (
    <div className="page home-page">
      <header className="home-head">
        <div className="home-row">
          <div>
            <h1>下午好，{user?.display_name || "演示用户"}</h1>
            <p>先看懂，再决定 · {data?.dataDate || "2026-10-23"} · {data?.isDemo ? "演示数据" : "公开 EOD"}</p>
          </div>
          <div className="home-actions">
            <button className="round-btn" aria-label="通知" onClick={() => nav("/watch")}>
              <Bell size={20} />
              <i className="notice-dot" />
            </button>
            <button className="avatar" onClick={() => nav("/me")} aria-label="我的">
              {(user?.display_name || "演").slice(0, 1)}
            </button>
          </div>
        </div>
        <button className="searchbar" onClick={() => nav("/search")}>
          <Search size={18} />
          <span>搜索股票 / 行业 / 主题</span>
        </button>
        <button className="ai-entry" onClick={() => nav("/ai")}>
          <Sparkles size={16} />
          <span>AI 管家 · 问个股、组合或复盘</span>
          <ChevronRight size={15} />
        </button>
      </header>

      {data?.isStale ? (
        <div className="stale-banner">
          数据截至 {data.dataDate}，落后 {data.ageTradingDays ?? data.ageDays} 个交易日；请先刷新 EOD 数据再判断。
        </div>
      ) : null}

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <>
          <section className="daily-card">
            <div className="daily-head">
              <div className="row gap6">
                <Sparkles size={15} />
                <b>今日概览</b>
              </div>
              <span className="daily-tag">收盘后更新</span>
            </div>
            <div className="daily-list">
              {data.daily.map((item: any, idx: number) => (
                <button className="daily-item" key={idx} onClick={() => openLink(item.link)}>
                  <span className={`dot dot-${idx === 0 ? "red" : idx === 1 ? "amber" : "gray"}`} />
                  <span className="daily-text">
                    <b>{item.title}</b>
                    <span>{item.detail}</span>
                  </span>
                  <ChevronRight size={15} className="daily-arrow" />
                </button>
              ))}
            </div>
            <div className="daily-foot">按自选、组合与收盘数据生成 · 非投资建议</div>
          </section>

          <AiPanel
            title="AI 今日解读"
            subtitle="基于自选、持仓与收盘数据生成；只解释今天发生了什么，不构成投资建议。"
            endpoint="/api/invest/ai/daily"
            buttonLabel="生成今日解读"
          />

          <section className="card">
            <div className="card-title-row">
              <h2>收盘复盘</h2>
              <span className="hint">规则摘要 · 非投资建议</span>
            </div>
            <p className="review-summary">{data.review.summary}</p>
            <ul className="fact-list">
              {data.review.facts.map((f: string, i: number) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </section>

          <div className="index-strip">
            {data.indices.map((it: any) => (
              <div className="index-cell" key={it.name}>
                <span>{it.name}</span>
                <b>{it.value}</b>
                <em className={it.change >= 0 ? "up" : "down"}>{fmtPct(it.change)}</em>
              </div>
            ))}
          </div>

          <SectionHead
            title="今日热点"
            sub="按板块热度排序"
            action={<button className="link-btn" onClick={() => nav("/search")}>全部 <ChevronRight size={14} /></button>}
          />
          <div className="stack">
            {data.topics.map((t: any) => (
              <button className="topic-card" key={t.id} onClick={() => nav(`/topic/${t.id}`)}>
                <div className="topic-top">
                  <div>
                    <span className="topic-kicker">行业 / 主题</span>
                    <h3>{t.name}</h3>
                  </div>
                  <Sparkline values={t.spark} />
                </div>
                <p>{t.summary}</p>
                <div className="topic-foot">
                  <Tag tone="amber">估值 {t.valuationPercentile?.toFixed?.(0) ?? t.valuationPercentile}% 分位</Tag>
                  <Tag tone="gray">热度 {t.heat?.toFixed?.(0) ?? t.heat}</Tag>
                  <span className="topic-go">查看 <ArrowRight size={14} /></span>
                </div>
              </button>
            ))}
          </div>

          <SectionHead
            title="我的自选"
            sub={`${data.watchlist.length} 只`}
            action={<button className="link-btn" onClick={() => nav("/watch")}>管理 <ChevronRight size={14} /></button>}
          />
          <div className="card list-card">
            {data.watchlist.length === 0 ? (
              <div className="empty-inline">还没有自选，去搜索添加。</div>
            ) : (
              data.watchlist.map((s: any) => (
                <button className="stock-row" key={s.code} onClick={() => nav(`/stock/${s.code}`)}>
                  <div>
                    <b>{s.name}</b>
                    <span>{s.code} · {s.group}</span>
                  </div>
                  <div className="stock-price">
                    <b>{formatPrice(s.price)}</b>
                    <em className={s.changePct >= 0 ? "up" : "down"}>{fmtPct(s.changePct)}</em>
                  </div>
                </button>
              ))
            )}
          </div>

          <SectionHead title="3 分钟学习" sub="术语随问随学" />
          <button className="learn-card" onClick={() => setGlossary(true)}>
            <div className="learn-icon"><BookOpen size={20} /></div>
            <div>
              <b>估值分位：贵不贵，跟什么比？</b>
              <p>先搞懂 PE 分位、拥挤度，再看热点。</p>
            </div>
            <ChevronRight size={18} />
          </button>

          <Disclaimer>{data.isDemo ? "演示数据" : "行情/组合/主题：公开 EOD（主题为等权代理） · 资讯：公开标题"} · 收盘后更新 · 不构成投资建议</Disclaimer>
        </>
      ) : null}

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} />
    </div>
  );
}
