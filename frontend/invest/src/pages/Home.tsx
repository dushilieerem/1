import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Bell, BookOpen, ChevronRight, Search, Sparkles } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, LoadingCards, SectionHead, Sparkline, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import GlossarySheet from "../GlossarySheet";
import { LocaleToggle, useLocale, withMarket } from "../i18n";

type HomeData = any;

const INDEX_LABEL: Record<string, { zh: string; en: string }> = {
  "000300": { zh: "沪深300", en: "CSI 300" },
  "000905": { zh: "中证500", en: "CSI 500" },
  "000015": { zh: "上证红利", en: "SSE Dividend" },
  "399101": { zh: "深证综指", en: "SZ Composite" },
  "399303": { zh: "国证2000", en: "CNI 2000" },
  "399317": { zh: "国证A指", en: "CNI A" },
};

function indexLabel(name: string, t: (zh: string, en: string) => string) {
  const key = String(name || "").replace(/\.(SH|SZ)$/i, "");
  const item = INDEX_LABEL[key];
  if (item) return t(item.zh, item.en);
  if (/^\d{6}$/.test(key)) return t(`指数 ${key}`, `Index ${key}`);
  return name;
}

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { t, market } = useLocale();
  const displayName = user?.display_name === "演示用户"
    ? t("演示用户", "Demo user")
    : user?.display_name || t("演示用户", "Demo user");
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [glossary, setGlossary] = useState(false);
  const usUnavailable = data?.market === "US" && data?.hasQuotes === false;

  const load = () => {
    setError(null);
    setData(null);
    api<HomeData>(withMarket("/api/invest/home", market))
      .then(setData)
      .catch((e) => setError(e.message));
  };

  useEffect(load, [market]);

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
            <h1>{t("下午好，", "Good afternoon, ")}{displayName}</h1>
            <p>
              {t("先看懂，再决定", "Understand first, then decide")} · {data?.dataDate || "2026-10-23"} ·{" "}
              {data?.isDemo ? t("演示数据", "Demo data") : market === "US" ? (data?.dataSource || "Public EOD (US)") : t("公开 EOD", "Public EOD")}
            </p>
          </div>
          <div className="home-actions">
            <LocaleToggle />
            <button className="round-btn" aria-label={t("通知", "Notifications")} onClick={() => nav("/watch")}>
              <Bell size={20} />
              <i className="notice-dot" />
            </button>
            <button className="avatar" onClick={() => nav("/me")} aria-label={t("我的", "Me")}>
              {(displayName || t("演", "D")).slice(0, 1)}
            </button>
          </div>
        </div>
        <button className="searchbar" onClick={() => nav("/search")}>
          <Search size={18} />
          <span>{market === "US" ? (usUnavailable ? t("美股搜索暂不可用", "US search unavailable") : t("搜索美股代码，如 AAPL", "Search US ticker, e.g. AAPL")) : t("搜索股票 / 行业 / 主题", "Search stocks / industries / themes")}</span>
        </button>
        {market === "CN" ? (
          <button className="ai-entry" onClick={() => nav("/ai")}>
            <Sparkles size={16} />
            <span>{t("AI 管家 · 问个股、组合或复盘", "AI copilot · ask about a stock, portfolio or review")}</span>
            <ChevronRight size={15} />
          </button>
        ) : (
          <div className="ai-entry market-note">
            <Sparkles size={16} />
            <span>
              {usUnavailable
                ? t("当前数据视图没有美股行情；切换到中文查看 A 股。", "This data view has no US quotes; switch to 中文 for A-share coverage.")
                : t("美股版当前提供行情与自选；AI 与基本面数据待接入。", "US mode currently covers quotes and watchlists; AI and fundamentals are not available (no free stable source).")}
            </span>
          </div>
        )}
      </header>

      {data?.isStale ? (
        <div className="stale-banner">
          {t(
            `数据截至 ${data.dataDate}，落后 ${data.ageTradingDays ?? data.ageDays} 个交易日；请先刷新 EOD 数据再判断。`,
            `Data as of ${data.dataDate}, ${data.ageTradingDays ?? data.ageDays} trading day(s) behind; refresh EOD data before drawing conclusions.`,
          )}
        </div>
      ) : null}

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <>
          {usUnavailable ? (
            <section className="card empty-data">
              <h2>{t("美股行情暂未接入", "US quotes not available")}</h2>
              <p>
                {t(
                  "当前数据视图只有 A 股覆盖，美股行情、财务、估值、新闻都未接入。切换到中文可查看 A 股。",
                  "The current data view only covers A-shares; US quotes, financials, valuation and news are not connected. Switch to 中文 for A-share coverage.",
                )}
              </p>
            </section>
          ) : (
          <>
          <section className="daily-card">
            <div className="daily-head">
              <div className="row gap6">
                <Sparkles size={15} />
                <b>{t("今日概览", "Today")}</b>
              </div>
              <span className="daily-tag">{t("收盘后更新", "Updated after close")}</span>
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
            <div className="daily-foot">{t("按自选、组合与收盘数据生成 · 非投资建议", "Built from watchlist, portfolio and EOD data · not investment advice")}</div>
          </section>

          <section className="card">
            <div className="card-title-row">
              <h2>{data.review.title || t("收盘复盘", "Close review")}</h2>
              <span className="hint">{t("规则摘要 · 非投资建议", "Rule-based summary · not investment advice")}</span>
            </div>
            <p className="review-summary">{data.review.summary}</p>
            <ul className="fact-list">
              {data.review.facts.map((f: string, i: number) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </section>

          {data.indices.length ? (
            <div className="index-strip">
              {data.indices.map((it: any) => (
                <div className="index-cell" key={it.name}>
                  <span>{indexLabel(it.name, t)}</span>
                  <b>{it.value}</b>
                  <em className={it.change >= 0 ? "up" : "down"}>{fmtPct(it.change)}</em>
                </div>
              ))}
            </div>
          ) : null}

          {data.topics.length ? (
            <>
              <SectionHead
                title={t("今日热点", "Today's themes")}
                sub={t("按板块热度排序", "Ranked by sector heat")}
                action={<button className="link-btn" onClick={() => nav("/search")}>{t("全部", "All")} <ChevronRight size={14} /></button>}
              />
              <div className="stack">
                {data.topics.map((topic: any) => (
                  <button className="topic-card" key={topic.id} onClick={() => nav(`/topic/${topic.id}`)}>
                    <div className="topic-top">
                      <div>
                        <span className="topic-kicker">{t("行业 / 主题", "Sector / theme")}</span>
                        <h3>{topic.name}</h3>
                      </div>
                      {topic.spark?.length >= 2 ? (
                        <Sparkline values={topic.spark} />
                      ) : (
                        <span className="hint">{t("走势待补充", "Trend pending")}</span>
                      )}
                    </div>
                    <p>{topic.summary}</p>
                    <div className="topic-foot">
                      <Tag tone="amber">{t("估值", "Valuation")} {topic.valuationPercentile?.toFixed?.(0) ?? topic.valuationPercentile}% {t("分位", "pct")}</Tag>
                      <Tag tone="gray">{t("热度", "Heat")} {topic.heat?.toFixed?.(0) ?? topic.heat}</Tag>
                      <span className="topic-go">{t("查看", "View")} <ArrowRight size={14} /></span>
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : null}

          <SectionHead
            title={t("我的自选", "My watchlist")}
            sub={t(`${data.watchlist.length} 只`, `${data.watchlist.length} name(s)`)}
            action={<button className="link-btn" onClick={() => nav("/watch")}>{t("管理", "Manage")} <ChevronRight size={14} /></button>}
          />
          <div className="card list-card">
            {data.watchlist.length === 0 ? (
              <div className="empty-inline">{t("还没有自选，去搜索添加。", "No names yet. Search to add some.")}</div>
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
          </>
          )}

          <SectionHead title={t("3 分钟学习", "3-minute learn")} sub={t("术语随问随学", "Tap a term to learn")} />
          <button className="learn-card" onClick={() => setGlossary(true)}>
            <div className="learn-icon"><BookOpen size={20} /></div>
            <div>
              <b>{t("估值分位：贵不贵，跟什么比？", "Valuation percentile: expensive versus what?")}</b>
              <p>{t("先搞懂 PE 分位、拥挤度，再看热点。", "Understand P/E percentile and crowding before chasing themes.")}</p>
            </div>
            <ChevronRight size={18} />
          </button>

          <Disclaimer>
            {market === "US"
              ? usUnavailable
                ? t("美股行情未接入", "US quotes not connected")
                : t("美股行情：公开 EOD · 无财务/估值/新闻/指数", "US quotes: public EOD · no fundamentals, valuation, news or indices")
              : data.isDemo
                ? t("演示数据", "Demo data")
                : t("行情/组合/主题：公开 EOD（主题为等权代理） · 资讯：公开标题", "Quotes/portfolio/themes: public EOD (themes are equal-weight proxies) · News: public headlines")}
            {" · "}
            {t("收盘后更新 · 不构成投资建议", "Updated after close · not investment advice")}
          </Disclaimer>
        </>
      ) : null}

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} items={data?.glossary} />
    </div>
  );
}
