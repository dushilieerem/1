import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, Eye, Telescope } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, DataFreshness, Empty, ErrorBox, HelpTip, Loading, PageHeader, StatusBadge } from "./instUi";

type IdeaQuestions = {
  source?: string;
  why_now: string;
  circle_of_competence: string;
  circle_note?: string;
  data_sufficiency: "sufficient" | "partial" | "missing";
  suggestion: "initiate" | "watch";
  reason: string;
  data_gaps?: string[];
};

type Company = {
  id: number;
  symbol: string;
  name: string;
  market: string;
  industry?: string;
  ref_price?: number;
  data_status?: string;
  pool_status?: string;
  tags?: string[];
  research_points?: string[];
  idea?: IdeaQuestions;
};

type PushItem = Company & {
  pe_ttm?: number;
  pb_mrq?: number;
  last_close?: number;
  momentum?: number;
  momentum_window?: number;
  reason?: string;
};

type PushResponse = {
  strategy: { key: string; name: string; note: string };
  as_of?: string;
  scanned: number;
  qualified: number;
  items: PushItem[];
};

type Position = {
  id: number;
  company_id?: number;
  symbol: string;
  name?: string;
  industry?: string;
  qty: number;
  cost?: number;
  market_value: number;
  weight: number;
  last_close?: number;
  market?: string;
  data_status?: string;
  idea?: IdeaQuestions;
};

type PortfolioData = {
  positions: Position[];
  cash: number;
  nav: number;
  invested: number;
  invested_ratio: number;
};

type TabKey = "push" | "watch" | "holdings";

type DecisionTarget = {
  id: number;
  name: string;
  symbol: string;
  source: TabKey;
  idea: IdeaQuestions;
};

type DecisionSource = {
  id?: number;
  company_id?: number;
  name?: string;
  symbol: string;
  market?: string;
  data_status?: string;
  research_points?: string[];
  reason?: string;
  idea?: IdeaQuestions;
};

function fallbackIdea(company: DecisionSource, source: TabKey): IdeaQuestions {
  if (company.idea) return company.idea;
  const market = String(company.market || "CN").toUpperCase();
  const status = String(company.data_status || "missing");
  const sufficiency: IdeaQuestions["data_sufficiency"] =
    market === "US" || market === "HK"
      ? "missing"
      : status === "real"
        ? "sufficient"
        : status === "partial" || status === "demo"
          ? "partial"
          : "missing";
  const whyNow =
    source === "holdings"
      ? "当前持仓；需要复核原投资论点是否仍成立，以及是否继续持有。"
      : source === "watch"
        ? String(company.research_points?.[0] || "已在观察池，等待新的价格或基本面变化。")
        : String(company.reason || "量化初筛通过，需要说明为什么是现在。");
  const gaps: string[] = [];
  if (market === "US" || market === "HK") gaps.push("美股/港股暂无财务、公告、行业数据源，只有行情");
  if (sufficiency === "partial") gaps.push("财务/公告数据不完整，关键结论需回源核对");
  if (sufficiency === "missing" && market === "CN") gaps.push("核心财务/公告数据缺失");
  return {
    why_now: whyNow,
    circle_of_competence: "unknown",
    circle_note: "需投资经理确认：能否用三句话说清它怎么赚钱？",
    data_sufficiency: sufficiency,
    suggestion: sufficiency === "sufficient" ? "initiate" : "watch",
    reason:
      sufficiency === "sufficient"
        ? "资料齐备，可进入研究；能力圈需投资经理确认。"
        : sufficiency === "partial"
          ? "资料部分缺失，建议先观察并补齐关键数据。"
          : "核心资料缺失，建议观察或放弃，不直接立项。",
    data_gaps: gaps,
  };
}

export function InstIdeasPage() {
  const session = useInstSession();
  const { locale, market, t } = useInstLocale();
  const nav = useNavigate();
  const [tab, setTab] = useState<TabKey>("push");
  const [push, setPush] = useState<PushResponse | null>(null);
  const [watch, setWatch] = useState<Company[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [decision, setDecision] = useState<DecisionTarget | null>(null);
  const [decisionAction, setDecisionAction] = useState<"initiate" | "watch" | "reject">("initiate");
  const [decisionReason, setDecisionReason] = useState("");
  const [circleConfirmed, setCircleConfirmed] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const canWrite = (session.permissions.ideas || "none") === "write";

  const industryText = (value?: string) => {
    const v = String(value || "").trim();
    // 全市场同步进来的行业有时是 801120.SI 这类指数代码，不适合直接展示。
    return v && !/^\d{6}\./.test(v) ? v : t("行业待补充", "Sector TBD");
  };

  const suffLabel = (value: IdeaQuestions["data_sufficiency"]) =>
    value === "sufficient"
      ? t("资料齐备", "Data sufficient")
      : value === "partial"
        ? t("部分缺失", "Data partial")
        : t("核心缺失", "Data missing");
  const suffTone = (value: IdeaQuestions["data_sufficiency"]) =>
    value === "sufficient" ? ("green" as const) : value === "partial" ? ("amber" as const) : ("red" as const);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    Promise.all([
      instApi<PushResponse>("/ideas/push?limit=12"),
      instApi<{ items: Company[] }>(
        `/companies?market=${market}&pool_status=watch&limit=60&offset=0`,
      ),
      instApi<PortfolioData>("/portfolio"),
    ])
      .then(([pushData, watchData, portfolioData]) => {
        if (!alive) return;
        setPush(pushData);
        setWatch(watchData.items || []);
        setPortfolio(portfolioData);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [market, reloadKey]);

  const openDecision = (company: DecisionSource, source: TabKey) => {
    if (!canWrite) return;
    const id = Number(company.id ?? company.company_id ?? 0);
    if (!id) return;
    const idea = fallbackIdea(company, source);
    setDecision({
      id,
      name: String(company.name || company.symbol),
      symbol: company.symbol,
      source,
      idea,
    });
    setDecisionAction(idea.suggestion);
    setDecisionReason("");
    setCircleConfirmed(false);
    setDecisionError(null);
  };

  const submitDecision = async (action: "initiate" | "watch" | "reject") => {
    if (!decision) return;
    const reason = decisionReason.trim();
    if (!reason) {
      setDecisionError(t("请填写决策理由。", "A decision reason is required."));
      return;
    }
    if (action === "initiate" && !circleConfirmed) {
      setDecisionError(
        t("立项前请确认能力圈：能否用三句话说清它怎么赚钱。", "Confirm the circle of competence before initiating: can you explain how it makes money in three sentences?"),
      );
      return;
    }
    setDecisionBusy(true);
    setDecisionError(null);
    try {
      const res = await instApi<{ case_id?: number }>(`/ideas/${decision.id}/decision`, {
        method: "POST",
        body: {
          source: decision.source,
          action,
          reason,
          circle_confirmed: circleConfirmed,
        },
      });
      setDecision(null);
      if (action === "initiate" && res.case_id) {
        nav(`/inst/research?case=${res.case_id}`);
      } else {
        setReloadKey((v) => v + 1);
      }
    } catch (e) {
      setDecisionError(e instanceof Error ? e.message : String(e));
    } finally {
      setDecisionBusy(false);
    }
  };

  const setPool = async (companyId: number, pool_status: "watch" | "research" | "dropped") => {
    if (!canWrite) return;
    setBusy(companyId);
    setError(null);
    try {
      await instApi(`/companies/${companyId}/pool`, {
        method: "POST",
        body: {
          pool_status,
          reason:
            pool_status === "dropped"
              ? t("未入选：待补充研究理由", "Not selected: research rationale pending")
              : null,
        },
      });
      setReloadKey((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const counts: Record<TabKey, number> = {
    push: push?.items.length || 0,
    watch: watch.length,
    holdings: (portfolio?.positions || []).filter((p) => Number(p.qty) > 0).length,
  };
  const tabs: Array<{ key: TabKey; label: string; icon: typeof Telescope }> = [
    { key: "push", label: t("量化策略推送", "Quant signals"), icon: Telescope },
    { key: "watch", label: t("关注与自选", "Watchlist"), icon: Eye },
    { key: "holdings", label: t("当前持仓", "Holdings"), icon: Briefcase },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="DISCOVERY / 02"
        title={t("机会发现", "Discovery")}
        desc={t(
          "三个入口看机会：量化策略推送、关注与自选、当前持仓。推送与筛选结果不是投资建议。",
          "Three ways to find ideas: quant signals, watchlist and current holdings. Signals are not investment advice.",
        )}
      />

      <div className="flex flex-wrap gap-2">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
              tab === key
                ? "border-[#b42345] bg-[#fbe9ef] text-[#a31f42]"
                : "border-[#dde5f2] bg-white text-[#68738b] hover:border-[#7950ba]"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
            <span className="rounded-full bg-white/70 px-1.5 py-0.5 text-[10px]">{counts[key]}</span>
          </button>
        ))}
      </div>

      {error ? <ErrorBox message={error} onRetry={() => setReloadKey((v) => v + 1)} /> : null}
      {loading ? <Loading label={t("正在加载…", "Loading…")} /> : null}

      {!loading && tab === "push" ? (
        <>
          <Card
            title={t("量化策略推送", "Quant signals")}
            desc={
              push?.strategy
                ? t(
                    `策略：${push.strategy.name}（仅 A 股）。${push.strategy.note}`,
                    `Strategy: ${push.strategy.name} (A-shares only). ${push.strategy.note}`,
                  )
                : t("收盘后按动量与估值初筛。", "Screened after close by momentum and valuation.")
            }
            actions={
              <div className="flex flex-wrap gap-1.5">
                <Badge tone="gold">{t("扫描", "Scanned")} {push?.scanned ?? 0}</Badge>
                <Badge tone="green">{t("符合", "Qualified")} {push?.qualified ?? 0}</Badge>
                <DataFreshness date={push?.as_of} label={t("行情", "Market")} />
              </div>
            }
          >
            {push?.items.length ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {push.items.map((c) => (
                  <article key={c.id} className="flex flex-col rounded-xl border border-[#dde5f2] bg-white p-5">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-display text-base font-semibold text-[#171923]">{c.name}</h3>
                        <p
                          className="mt-0.5 font-mono text-[11px] text-[#68738b]"
                          title={t(
                            "行业优先取公司池或申万分类中文名；缺失时显示“行业待补充”，不影响动量与估值初筛。",
                            "Industry uses the pool/SW Chinese name when available; missing values show 'Sector TBD' and do not affect the screen.",
                          )}
                        >
                          {c.symbol} · {industryText(c.industry)}
                        </p>
                      </div>
                      <StatusBadge status={c.data_status} />
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[#68738b]">
                      <div>
                        <p>{t("参考价", "Reference")}</p>
                        <p className="font-mono text-[#252533]">
                          {c.ref_price == null ? (
                            <span
                              className="text-[#a9a4bd]"
                              title={t("该标的暂无参考价；不影响其他初筛字段。", "No reference price; other screen fields are unaffected.")}
                            >
                              {t("待补充", "TBD")}
                            </span>
                          ) : (
                            fmtNum(c.ref_price, 2)
                          )}
                        </p>
                      </div>
                      <div>
                        <p className="flex items-center gap-1">
                          {t("近 N 日动量", "Momentum")}
                          <HelpTip
                            text={t(
                              "最近 N 个交易日的收盘价涨幅；数据不足时 N 自动缩短，生产环境最多 20 日。",
                              "Close-to-close return over the latest N trading days; N shrinks when history is short, up to 20 days in production.",
                            )}
                          />
                        </p>
                        <p className="font-mono text-emerald-700">
                          +{((c.momentum || 0) * 100).toFixed(1)}%
                          <span className="ml-1 text-[10px] text-[#77718c]">
                            {c.momentum_window ?? "—"} {t("日", "d")}
                          </span>
                        </p>
                      </div>
                      <div>
                        <p className="flex items-center gap-1">
                          PE TTM
                          <HelpTip text={t("滚动市盈率 = 市值 / 最近 12 个月净利润；初筛要求 0-100。", "Trailing P/E = market cap / last 12 months net profit; screen requires 0-100.")} />
                        </p>
                        <p className="font-mono text-[#252533]">{fmtNum(c.pe_ttm, 2)}</p>
                      </div>
                      <div>
                        <p className="flex items-center gap-1">
                          PB MRQ
                          <HelpTip text={t("市净率 = 市值 / 最近一期净资产；初筛要求为正。", "Price-to-book = market cap / latest book value; screen requires positive.")} />
                        </p>
                        <p className="font-mono text-[#252533]">{fmtNum(c.pb_mrq, 2)}</p>
                      </div>
                    </div>
                    <p className="mt-3 rounded-lg bg-[#f8faff] px-2 py-1.5 text-[11px] leading-relaxed text-[#505369]">
                      <span className="font-medium">{t("为什么推它", "Why it is here")}：</span>
                      {c.reason || t("动量与估值初筛通过", "Passed momentum and valuation screen")}
                    </p>
                    {(c.tags || []).length ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {(c.tags || []).slice(0, 4).map((tag) => (
                          <Badge key={tag}>{tag}</Badge>
                        ))}
                      </div>
                    ) : null}
                    {(c.research_points || [])[0] ? (
                      <p className="mt-2 text-[11px] leading-relaxed text-[#68738b]">
                        {t("研究关注点", "Research focus")}：{(c.research_points || [])[0]}
                      </p>
                    ) : null}
                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#e3eaf8] pt-3">
                      <Button
                        variant="primary"
                        disabled={!canWrite || busy === c.id}
                        onClick={() => openDecision(c, "push")}
                      >
                        {t("立项评估", "Assess idea")}
                      </Button>
                      <Badge tone={suffTone((c.idea || fallbackIdea(c, "push")).data_sufficiency)}>
                        {suffLabel((c.idea || fallbackIdea(c, "push")).data_sufficiency)}
                      </Badge>
                      {c.pool_status === "watch" ? (
                        <Badge tone="amber">{t("已在关注", "Watching")}</Badge>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty>
                <Telescope className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
                {t(
                  "当前没有正动量且估值通过的标的。可以到下方「关注与自选」查看已有对象。",
                  "No positive-momentum names passed the valuation screen right now. Check the watchlist tab.",
                )}
              </Empty>
            )}
          </Card>
          <p className="text-[11px] leading-relaxed text-[#77718c]">
            {t(
              "推送为收盘后规则初筛：A 股、未放弃、近 2-20 个交易日动量为正，PE TTM 0-100、PB 为正；不是实时信号，不构成投资建议。",
              "Signals are rule-based after close: A-shares, not dropped, positive momentum over 2-20 trading days, PE TTM 0-100 and positive PB; not real-time and not investment advice.",
            )}
          </p>
        </>
      ) : null}

      {!loading && tab === "watch" ? (
        <Card
          title={t("关注与自选", "Watchlist")}
          desc={t(
            "已加入观察池的标的。可以从这里进入研究，或移出关注。",
            "Names in the watch pool. Start research or remove them from the watchlist.",
          )}
          actions={<Badge tone="amber">{watch.length} {t("个对象", "names")}</Badge>}
        >
          {watch.length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {watch.map((c) => (
                <article key={c.id} className="flex flex-col rounded-xl border border-[#dde5f2] bg-white p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-display text-base font-semibold text-[#171923]">{c.name}</h3>
                      <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">
                        {c.symbol} · {c.industry || t("行业待补充", "Sector TBD")}
                      </p>
                    </div>
                    <StatusBadge status={c.data_status} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <Badge>{c.market}</Badge>
                    {c.market !== "CN" ? (
                      <Badge
                        tone="amber"
                        title={t(
                          "美股/港股暂无财务、公告、行业与指数数据源；只有行情，研究结论会标记数据缺口。",
                          "No fundamental, filing, industry or index data source for US/HK; prices only, and research marks data gaps.",
                        )}
                      >
                        {t("暂无数据源", "No data source")}
                      </Badge>
                    ) : null}
                    {(c.tags || []).slice(0, 3).map((tag) => (
                      <Badge key={tag} tone="gold">{tag}</Badge>
                    ))}
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-[#505369]">
                    {(c.research_points || [])[0] || t("研究关注点待补充", "Research focus pending")}
                  </p>
                  <p className="mt-2 text-xs text-[#68738b]">
                    {t("参考价", "Reference")}：
                    <span className="ml-1 font-mono text-[#252533]">
                      {c.ref_price == null ? (
                        <span
                          className="text-[#a9a4bd]"
                          title={t("该标的暂无参考价；美股/港股行情未接入时常见。", "No reference price; common when US/HK market data is not ingested.")}
                        >
                          {t("待补充", "TBD")}
                        </span>
                      ) : (
                        fmtNum(c.ref_price, 2)
                      )}
                    </span>
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#e3eaf8] pt-3">
                    <Button
                      variant="primary"
                      disabled={!canWrite || busy === c.id}
                      onClick={() => openDecision(c, "watch")}
                    >
                      {t("立项评估", "Assess idea")}
                    </Button>
                    <Badge tone={suffTone((c.idea || fallbackIdea(c, "watch")).data_sufficiency)}>
                      {suffLabel((c.idea || fallbackIdea(c, "watch")).data_sufficiency)}
                    </Badge>
                    <Button
                      variant="ghost"
                      disabled={!canWrite || busy === c.id}
                      onClick={() => void setPool(c.id, "research")}
                    >
                      {t("取消关注", "Unwatch")}
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty>
              <Eye className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
              {t(
                "还没有关注对象。可以在「量化策略推送」里点「关注」。",
                "No watchlist names yet. Add them from the Quant signals tab.",
              )}
            </Empty>
          )}
        </Card>
      ) : null}

      {!loading && tab === "holdings" ? (
        <Card
          title={t("当前持仓", "Current holdings")}
          desc={t(
            "组合当前持仓与权重。研究、审批与执行流程仍按机构端规则运行。",
            "Current positions and weights. Research, approval and execution still follow the institution workflow.",
          )}
          actions={
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="green">{t("净值", "NAV")} {fmtNum(portfolio?.nav, 0)}</Badge>
              <Badge>{t("现金", "Cash")} {fmtNum(portfolio?.cash, 0)}</Badge>
            </div>
          }
        >
          {(portfolio?.positions || []).filter((p) => Number(p.qty) > 0).length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {(portfolio?.positions || [])
                .filter((p) => Number(p.qty) > 0)
                .map((p) => (
                  <article key={p.id} className="flex flex-col rounded-xl border border-[#dde5f2] bg-white p-5">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-display text-base font-semibold text-[#171923]">
                          {p.name || p.symbol}
                        </h3>
                        <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">
                          {p.symbol} · {industryText(p.industry)}
                        </p>
                      </div>
                      <Badge tone="gold">{t("持仓", "Held")}</Badge>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-[#68738b]">
                      <div>
                        <dt>{t("数量", "Qty")}</dt>
                        <dd className="font-mono text-[#252533]">{fmtNum(p.qty, 0)}</dd>
                      </div>
                      <div>
                        <dt>{t("成本", "Cost")}</dt>
                        <dd className="font-mono text-[#252533]">{fmtNum(p.cost, 2)}</dd>
                      </div>
                      <div>
                        <dt>{t("市值", "Market value")}</dt>
                        <dd className="font-mono text-[#252533]">{fmtNum(p.market_value, 2)}</dd>
                      </div>
                      <div>
                        <dt>{t("权重", "Weight")}</dt>
                        <dd className="font-mono text-[#252533]">{fmtNum((p.weight || 0) * 100, 2)}%</dd>
                      </div>
                    </dl>
                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#e3eaf8] pt-3">
                      {p.company_id ? (
                        <Button
                          variant="primary"
                          disabled={!canWrite || busy === p.company_id}
                          onClick={() =>
                            openDecision(
                              {
                                id: Number(p.company_id),
                                name: p.name,
                                symbol: p.symbol,
                                market: p.market,
                                data_status: p.data_status,
                                idea: p.idea,
                              },
                              "holdings",
                            )
                          }
                        >
                          {t("复核立项", "Review idea")}
                        </Button>
                      ) : null}
                      <Button variant="ghost" onClick={() => nav("/inst/monitor")}>
                        {t("去投后管理", "Post-investment")}
                      </Button>
                    </div>
                  </article>
                ))}
            </div>
          ) : (
            <Empty>
              <Briefcase className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
              {t("当前没有持仓。", "No current holdings.")}
            </Empty>
          )}
        </Card>
      ) : null}

      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t(
          `研究范围为 A 股全市场；当前语言环境为 ${locale === "zh" ? "中文" : "英文"}。推送、关注与持仓展示都不是投资建议。`,
          `Research scope is the A-share market; current locale is ${locale === "zh" ? "Chinese" : "English"}. Signals, watchlist and holdings are not investment advice.`,
        )}
      </p>
      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t(
          "数据状态说明：真实数据 = 行情/财务较完整；待补充 = 部分数据缺失；无数据 = 尚未接入。缺失数据会影响研究深度，但不会把缺失当成 0。",
          "Data status: Real = prices/financials are fairly complete; Partial = some data missing; No data = not ingested. Missing data limits research depth and is never treated as zero.",
        )}
      </p>

      {decision ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#171923]/45 p-3 sm:p-6"
          role="presentation"
          onClick={() => {
            if (!decisionBusy) setDecision(null);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="idea-decision-title"
            className="my-4 w-full max-w-2xl rounded-2xl bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e3eaf8] px-5 py-4">
              <div>
                <p className="text-[11px] tracking-[0.18em] text-[#b42345]">{t("立项三问", "IDEA CHECK")}</p>
                <h2 id="idea-decision-title" className="mt-1 font-display text-lg font-semibold text-[#171923]">
                  {decision.name}
                </h2>
                <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">
                  {decision.symbol} ·{" "}
                  {decision.source === "push"
                    ? t("量化推送", "Quant signal")
                    : decision.source === "watch"
                      ? t("关注与自选", "Watchlist")
                      : t("当前持仓", "Holding")}
                </p>
              </div>
              <Button variant="ghost" disabled={decisionBusy} onClick={() => setDecision(null)}>
                {t("关闭", "Close")}
              </Button>
            </div>

            <div className="space-y-3 px-5 py-4">
              <div className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                <p className="text-xs font-semibold text-[#505369]">1. {t("为什么现在", "Why now")}</p>
                <p className="mt-1 text-xs leading-relaxed text-[#68738b]">{decision.idea.why_now}</p>
              </div>
              <div className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                <p className="text-xs font-semibold text-[#505369]">2. {t("能力圈", "Circle of competence")}</p>
                <p className="mt-1 text-xs leading-relaxed text-[#68738b]">
                  {decision.idea.circle_note || decision.idea.circle_of_competence}
                </p>
                <label className="mt-2 flex items-start gap-2 text-[11px] leading-relaxed text-[#505369]">
                  <input
                    type="checkbox"
                    checked={circleConfirmed}
                    onChange={(e) => setCircleConfirmed(e.target.checked)}
                    className="mt-0.5"
                  />
                  {t("我确认能用三句话说清它怎么赚钱。", "I can explain how it makes money in three sentences.")}
                </label>
              </div>
              <div className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-[#505369]">3. {t("资料齐备", "Data sufficiency")}</p>
                  <Badge tone={suffTone(decision.idea.data_sufficiency)}>
                    {suffLabel(decision.idea.data_sufficiency)}
                  </Badge>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-[#68738b]">{decision.idea.reason}</p>
                {decision.idea.data_gaps?.length ? (
                  <ul className="mt-1 space-y-0.5 text-[11px] text-amber-700">
                    {decision.idea.data_gaps.map((gap) => (
                      <li key={gap}>· {gap}</li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={decision.idea.suggestion === "initiate" ? "green" : "amber"}>
                  {t("规则建议", "Rule suggestion")}：
                  {decision.idea.suggestion === "initiate" ? t("可立项", "Initiate") : t("先观察", "Watch")}
                </Badge>
                <span className="text-[10px] text-[#77718c]">
                  {t("这是规则初筛，不是 AI 结论；最终由你拍板。", "Rule-based screen, not an AI conclusion; the decision is yours.")}
                </span>
              </div>

              <label className="block text-xs text-[#68738b]">
                {t("决策理由（必填）", "Decision reason (required)")}
                <textarea
                  value={decisionReason}
                  onChange={(e) => setDecisionReason(e.target.value)}
                  placeholder={
                    decisionAction === "initiate"
                      ? t("为什么现在立项？关键假设和下一步核验是什么？", "Why initiate now? What are the key assumptions and next checks?")
                      : t("为什么观察或放弃？保留理由，避免只记成功案例。", "Why watch or reject? Keep the reason so only successes are not remembered.")
                  }
                  className="mt-1 min-h-[76px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
                />
              </label>
              {decisionError ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-700">
                  {decisionError}
                </p>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-[#e3eaf8] px-5 py-4">
              <Button
                variant="primary"
                disabled={decisionBusy || decision.idea.data_sufficiency === "missing"}
                onClick={() => void submitDecision("initiate")}
              >
                {t("立项并进入研究", "Initiate & research")}
              </Button>
              <Button variant="ghost" disabled={decisionBusy} onClick={() => void submitDecision("watch")}>
                {t("加入观察", "Watch")}
              </Button>
              <Button variant="danger" disabled={decisionBusy} onClick={() => void submitDecision("reject")}>
                {t("放弃", "Reject")}
              </Button>
              {decision.idea.data_sufficiency === "missing" ? (
                <span className="text-[10px] text-amber-700">
                  {t("资料不足，立项不可用；可先观察或放弃。", "Data missing: initiate is unavailable; watch or reject instead.")}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
