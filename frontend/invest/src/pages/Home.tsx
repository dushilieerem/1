import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, BookOpen, ChevronRight, Search, Sparkles } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, LoadingCards, Sheet, Tag } from "../components";
import { fmtPct } from "../lib";
import { LocaleToggle, useLocale, withMarket } from "../i18n";

type HomeData = any;

const fmtIndex = (value: any) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const fmtTurnover = (value: any) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return `${(n / 10000).toFixed(2)} 万亿`;
};

const mmdd = (value?: string | null) => {
  const text = String(value || "");
  return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(5, 10) : "—";
};

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { t, market, locale } = useLocale();
  const displayName = user?.display_name === "演示用户"
    ? t("演示用户", "Demo user")
    : user?.display_name || t("演示用户", "Demo user");
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [aiLine, setAiLine] = useState("");
  const [aiPending, setAiPending] = useState(false);
  const usUnavailable = data?.market === "US" && data?.hasQuotes === false;

  const load = () => {
    setError(null);
    setData(null);
    api<HomeData>(withMarket("/api/invest/home", market))
      .then(setData)
      .catch((e) => setError(e.message));
  };

  useEffect(load, [market]);

  useEffect(() => {
    if (!data || market !== "CN" || !data.daily?.length) {
      setAiLine("");
      setAiPending(false);
      return;
    }
    let cancelled = false;
    setAiPending(true);
    api<{ card?: { summary?: string } }>("/api/invest/ai/daily?refresh=0", { method: "POST" })
      .then((res) => { if (!cancelled) setAiLine(res.card?.summary || ""); })
      .catch(() => { if (!cancelled) setAiLine(""); })
      .finally(() => { if (!cancelled) setAiPending(false); });
    return () => { cancelled = true; };
  }, [data, market]);

  const openLink = (link: any) => {
    if (!link) return;
    if (link.type === "stock") nav(`/stock/${link.id}`);
    else if (link.type === "topic") nav(`/topic/${link.id}`);
    else if (link.type === "portfolio") nav("/portfolio");
  };

  const portfolio = data?.portfolioSnapshot || {
    hasHoldings: false, holdingCount: 0, dailyChange: null, lastCheckupDate: null,
  };
  const pulse = data?.marketPulse || {
    statusLabel: "收盘", statusLabelEn: "Close", asOf: data?.dataDate,
    indices: [], turnover: { value: null, change: null, available: false, note: "" },
  };
  const turnover = pulse.turnover || { value: null, change: null, available: false, note: "" };
  const daily = data?.daily || [];
  const review = data?.review || {};
  const topics = data?.topics || [];
  const learn = data?.learn || {};

  return (
    <div className="page home-page">
      <header className="home-head">
        <div className="home-row">
          <div>
            <h1>{t("下午好，", "Good afternoon, ")}{displayName}</h1>
            <p>
              {data?.dataDate || "2026-10-23"} ·{" "}
              {data?.isDemo ? t("演示数据", "Demo data") : market === "US" ? (data?.dataSource || "Public EOD (US)") : t("公开 EOD", "Public EOD")}
            </p>
          </div>
          <div className="home-actions">
            <LocaleToggle />
            <button className="round-btn" aria-label={t("通知", "Notifications")} onClick={() => nav("/notifications")}>
              <Bell size={20} />
              <i className="notice-dot" />
            </button>
            <button className="avatar" onClick={() => nav("/me")} aria-label={t("我的", "Me")}>
              {(displayName || t("演", "D")).slice(0, 1)}
            </button>
          </div>
        </div>
        <div className="home-search-row">
          <button className="searchbar home-search" onClick={() => nav("/search")}>
            <Search size={18} />
            <span>{market === "US" ? (usUnavailable ? t("美股搜索暂不可用", "US search unavailable") : t("搜索美股代码，如 AAPL", "Search US ticker, e.g. AAPL")) : t("搜索股票 / 行业 / 主题", "Search stocks / industries / themes")}</span>
          </button>
          <button className="home-spark" aria-label={t("AI 管家", "AI assistant")} onClick={() => nav("/ai")}>
            <Sparkles size={18} />
          </button>
        </div>
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
              <section className="today-card">
                <div className="today-mine">
                  <div className="today-head">
                    <span>{t("今日", "Today")}</span>
                    <span className="today-status">{locale === "en" ? pulse.statusLabelEn : pulse.statusLabel}</span>
                  </div>
                  {portfolio.hasHoldings ? (
                    <button className="today-mine-row" onClick={() => nav("/portfolio")}>
                      <div className="today-mine-main">
                        <span>{t("我的", "Mine")}</span>
                        <b className={Number(portfolio.dailyChange) >= 0 ? "today-up" : "today-down"}>
                          {portfolio.dailyChange == null ? "—" : fmtPct(portfolio.dailyChange)}
                        </b>
                      </div>
                      <div className="today-checkup">
                        <span>{t("上次体检", "Last checkup")}</span>
                        <b>{mmdd(portfolio.lastCheckupDate)}</b>
                      </div>
                      <ChevronRight size={17} />
                    </button>
                  ) : (
                    <button className="today-build" onClick={() => nav("/portfolio")}>
                      <div>
                        <b>{t("建立组合", "Build your portfolio")}</b>
                        <span>{t("导入持仓后看今日收益", "Import holdings to see today's return")}</span>
                      </div>
                      <ChevronRight size={17} />
                    </button>
                  )}
                </div>

                <div className="today-market">
                  <div className="today-market-head">
                    <span>{t("市场", "Market")}</span>
                    <span>{pulse.asOf}</span>
                  </div>
                  {(pulse.indices || []).length ? (
                    <div className="today-grid">
                      {(pulse.indices || []).map((item: any) => (
                        <div className={`today-cell ${item.available ? "" : "missing"}`} key={item.code || item.label}>
                          <span>{locale === "en" ? item.label_en || item.label : item.label}</span>
                          <b>{item.available ? fmtIndex(item.value) : "—"}</b>
                          <em className={!item.available ? "muted" : Number(item.change) >= 0 ? "up" : "down"}>
                            {item.available && item.change != null ? fmtPct(item.change) : ""}
                          </em>
                        </div>
                      ))}
                      <div className={`today-cell ${turnover.available ? "" : "missing"}`}>
                        <span>{t("两市成交", "Turnover")}</span>
                        <b>{turnover.available ? fmtTurnover(turnover.value) : "—"}</b>
                        <em className={turnover.available && Number(turnover.change) >= 0 ? "up" : "down"}>
                          {turnover.available && turnover.change != null
                            ? t(`较昨 ${fmtPct(turnover.change)}`, `${fmtPct(turnover.change)} vs prior`)
                            : turnover.note || ""}
                        </em>
                      </div>
                    </div>
                  ) : (
                    <div className="today-market-empty">
                      <b>{t("市场指数暂不可用", "Market indices are unavailable")}</b>
                      <span>{t("当前无法获取指数行情，不影响其他内容。", "Index quotes are currently unavailable; the rest of the page is unaffected.")}</span>
                    </div>
                  )}
                  {turnover.available && turnover.basisLabel ? (
                    <p className="today-basis">
                      {locale === "en" ? turnover.basisLabelEn || turnover.basisLabel : turnover.basisLabel}
                    </p>
                  ) : null}
                </div>
              </section>

              {daily.length ? (
                <section className="home-overview">
                  <div className="home-section-head">
                    <div>
                      <h2>{t("今日概览", "Today's brief")}</h2>
                      <span>
                        {aiLine
                          ? t("AI 生成 · 规则校验", "AI-generated · rule-checked")
                          : aiPending
                            ? t("AI 生成中 · 规则摘要", "AI generating · rule-based summary")
                            : t("规则生成 · 非投资建议", "Rule-based · not investment advice")}
                      </span>
                    </div>
                    <button className="link-btn" onClick={() => setReportOpen(true)}>
                      {t("查看完整日报", "Full brief")} <ChevronRight size={14} />
                    </button>
                  </div>
                  {aiLine || review.line ? <p className="overview-line">{aiLine || review.line}</p> : null}
                  <div className="overview-list">
                    {daily.slice(0, 3).map((item: any, idx: number) => {
                      const body = (
                        <>
                          <span className={`overview-dot dot-${item.source || (idx === 0 ? "stock" : idx === 1 ? "portfolio" : "market")}`} />
                          <span className="overview-text">
                            <b>{item.title}</b>
                            <span>{item.detail}</span>
                          </span>
                          {item.link ? <ChevronRight size={15} className="overview-arrow" /> : null}
                        </>
                      );
                      return item.link ? (
                        <button className="overview-row" key={`${item.title}-${idx}`} onClick={() => openLink(item.link)}>{body}</button>
                      ) : (
                        <div className="overview-row" key={`${item.title}-${idx}`}>{body}</div>
                      );
                    })}
                  </div>
                </section>
              ) : null}

              {topics.length ? (
                <section className="home-topics">
                  <div className="home-section-head">
                    <div>
                      <h2>{t("今日热点", "Today's themes")}</h2>
                      <span>{t("按热度排序 · 每条带风险提示", "Ranked by heat · every row carries a risk flag")}</span>
                    </div>
                    <button className="link-btn" onClick={() => nav("/topics")}>
                      {t("全部", "All")} <ChevronRight size={14} />
                    </button>
                  </div>
                  <div className="hot-list">
                    {topics.slice(0, 3).map((topic: any) => {
                      const fallbackValue = topic.valuationPercentile ?? topic.turnoverPercentile;
                      const tags = topic.riskTags?.length
                        ? topic.riskTags
                        : [{
                            label: fallbackValue != null
                              ? `估值分位 ${Number(fallbackValue).toFixed(0)}%`
                              : `热度 ${Number(topic.heat || 0).toFixed(0)}`,
                            label_en: fallbackValue != null
                              ? `Valuation percentile ${Number(fallbackValue).toFixed(0)}%`
                              : `Heat ${Number(topic.heat || 0).toFixed(0)}`,
                            tone: "gray",
                          }];
                      return (
                        <button className="hot-row" key={topic.id} onClick={() => nav(`/topic/${topic.id}`)}>
                          <div className="hot-top">
                            <b>{topic.name}</b>
                            <span className="hot-heat">{t("热度", "Heat")} {Number(topic.heat || 0).toFixed(0)}</span>
                          </div>
                          <p>{topic.summary}</p>
                          <div className="hot-tags">
                            {tags.map((tag: any) => (
                              <Tag key={tag.label} tone={tag.tone || "gray"}>
                                {locale === "en" ? tag.label_en || tag.label : tag.label}
                              </Tag>
                            ))}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ) : null}

              <button className="home-learn-row" onClick={() => nav(learn.link || "/learn")}>
                <BookOpen size={16} />
                <span>{locale === "en" ? learn.titleEn || "Valuation percentile: expensive versus what?" : learn.title || "估值分位：贵不贵，跟什么比？"}</span>
                <ChevronRight size={17} />
              </button>
            </>
          )}

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

          <Sheet
            open={reportOpen}
            onClose={() => setReportOpen(false)}
            title={t("今日日报", "Today's brief")}
            sub={data.dataDate}
          >
            <div className="home-report">
              {daily.map((item: any, idx: number) => (
                <div className="report-row" key={`${item.title}-${idx}`}>
                  <span className={`overview-dot dot-${item.source || "market"}`} />
                  <div>
                    <b>{item.title}</b>
                    <p>{item.detail}</p>
                  </div>
                </div>
              ))}
              {review.summary ? <p className="report-summary">{review.summary}</p> : null}
              {review.facts?.length ? (
                <ul className="fact-list">
                  {review.facts.map((f: string, i: number) => <li key={i}>{f}</li>)}
                </ul>
              ) : null}
              <p className="hint">{t("规则生成 · 历史 EOD 数据 · 不构成投资建议", "Rule-based · historical EOD data · not investment advice")}</p>
            </div>
          </Sheet>
        </>
      ) : null}
    </div>
  );
}
