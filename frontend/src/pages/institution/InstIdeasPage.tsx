import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, Eye, Telescope } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, DataFreshness, Empty, ErrorBox, HelpTip, Loading, PageHeader, StatusBadge } from "./instUi";

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
};

type PortfolioData = {
  positions: Position[];
  cash: number;
  nav: number;
  invested: number;
  invested_ratio: number;
};

type TabKey = "push" | "watch" | "holdings";

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

  const canWrite = (session.permissions.ideas || "none") === "write";

  const industryText = (value?: string) => {
    const v = String(value || "").trim();
    // 全市场同步进来的行业有时是 801120.SI 这类指数代码，不适合直接展示。
    return v && !/^\d{6}\./.test(v) ? v : t("行业待补充", "Sector TBD");
  };

  const initiateBlocked = (company: { market?: string; data_status?: string }) =>
    ["US", "HK"].includes(String(company.market || "CN").toUpperCase()) ||
    String(company.data_status || "missing") === "missing";

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

  const initiateResearch = async (companyId: number, source: TabKey) => {
    if (!canWrite || busy === companyId) return;
    setBusy(companyId);
    setError(null);
    try {
      const res = await instApi<{ case_id?: number }>(`/ideas/${companyId}/decision`, {
        method: "POST",
        body: {
          source,
          action: "initiate",
          reason: t("机会发现页直接立项", "Initiated from Discovery"),
          circle_confirmed: true,
        },
      });
      if (res.case_id) {
        nav(`/inst/research?case=${res.case_id}`);
      } else {
        setReloadKey((v) => v + 1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const rejectCompany = async (companyId: number, source: TabKey, name: string) => {
    if (!canWrite || busy === companyId) return;
    const reason = window.prompt(
      t(`放弃「${name}」的理由（必填）：`, `Reason for rejecting ${name} (required):`),
      "",
    );
    if (reason === null) return;
    if (!reason.trim()) {
      setError(t("放弃必须填写理由，避免以后只记得投对过的。", "A rejection reason is required."));
      return;
    }
    setBusy(companyId);
    setError(null);
    try {
      await instApi(`/ideas/${companyId}/decision`, {
        method: "POST",
        body: {
          source,
          action: "reject",
          reason: reason.trim(),
          circle_confirmed: false,
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
                        disabled={!canWrite || busy === c.id || initiateBlocked(c)}
                        title={
                          initiateBlocked(c)
                            ? t("核心资料缺失或暂无数据源，不能立项。", "Core data or a data source is missing; research cannot start.")
                            : undefined
                        }
                        onClick={() => void initiateResearch(c.id, "push")}
                      >
                        {busy === c.id ? t("处理中…", "Working…") : t("进入研究", "Enter research")}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!canWrite || busy === c.id}
                        onClick={() => void rejectCompany(c.id, "push", c.name)}
                      >
                        {t("放弃", "Reject")}
                      </Button>
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
            "已加入观察池的标的。可以直接进入研究，或放弃并留下理由。",
            "Names in the watch pool. Start research directly, or reject with a reason.",
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
                      disabled={!canWrite || busy === c.id || initiateBlocked(c)}
                      title={
                        initiateBlocked(c)
                          ? t("核心资料缺失或暂无数据源，不能立项。", "Core data or a data source is missing; research cannot start.")
                          : undefined
                      }
                      onClick={() => void initiateResearch(c.id, "watch")}
                    >
                      {busy === c.id ? t("处理中…", "Working…") : t("进入研究", "Enter research")}
                    </Button>
                    <Button
                      variant="danger"
                      disabled={!canWrite || busy === c.id}
                      onClick={() => void rejectCompany(c.id, "watch", c.name)}
                    >
                      {t("放弃", "Reject")}
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
                        <>
                          <Button
                            variant="primary"
                            disabled={!canWrite || busy === p.company_id || initiateBlocked(p)}
                            title={
                              initiateBlocked(p)
                                ? t("核心资料缺失或暂无数据源，不能立项。", "Core data or a data source is missing; research cannot start.")
                                : undefined
                            }
                            onClick={() => void initiateResearch(Number(p.company_id), "holdings")}
                          >
                            {busy === p.company_id
                              ? t("处理中…", "Working…")
                              : t("进入研究", "Enter research")}
                          </Button>
                          <Button
                            variant="danger"
                            disabled={!canWrite || busy === p.company_id}
                            onClick={() =>
                              void rejectCompany(Number(p.company_id), "holdings", p.name || p.symbol)
                            }
                          >
                            {t("放弃", "Reject")}
                          </Button>
                        </>
                      ) : null}
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

    </div>
  );
}
