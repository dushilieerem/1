import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { PieChart, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtPct, fmtDateTime } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, DataFreshness, Empty, ErrorBox, Field, Loading, PageHeader, industryLabel } from "./instUi";

type Position = {
  id: number;
  symbol: string;
  name?: string;
  industry?: string;
  market?: string;
  qty: number;
  cost?: number;
  market_value: number;
  weight: number;
  as_of: string;
};

type ExecutionException = {
  id: number;
  type: string;
  detail?: { text?: string } | string;
  authorization_id?: number;
  created_at?: string;
};

const EXCEPTION_TYPE: Record<string, [string, string]> = {
  suspended_or_st: ["停牌或 ST", "Suspended / ST"],
  price_invalid: ["无有效价格", "No valid price"],
  manual: ["手工登记", "Manual"],
  reconciliation: ["对账差异", "Reconciliation mismatch"],
};

type PortfolioData = {
  portfolio: {
    id: number;
    code: string;
    name: string;
    base_currency: string;
    nav: number;
    cash: number;
    invested: number;
    invested_ratio: number;
  } | null;
  positions: Position[];
  cash: number;
  nav: number;
  invested: number;
  invested_ratio: number;
  industry_exposure: Record<string, number>;
};

export function InstPortfolioPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const location = useLocation();
  const flash = (location.state as { flash?: string } | null)?.flash;
  const [data, setData] = useState<PortfolioData | null>(null);
  const [exceptions, setExceptions] = useState<ExecutionException[]>([]);
  const [resolving, setResolving] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      instApi<PortfolioData>("/portfolio"),
      instApi<{ items: ExecutionException[] }>("/execution/exceptions?status=open").catch(
        () => ({ items: [] as ExecutionException[] }),
      ),
    ])
      .then(([portfolio, ex]) => {
        setData(portfolio);
        setExceptions(ex.items || []);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const resolveException = async (id: number) => {
    setResolving(id);
    setError(null);
    try {
      await instApi(`/execution/exceptions/${id}/resolve`, {
        method: "POST",
        body: { status: "resolved", resolution: t("已人工核对", "Checked manually") },
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResolving(null);
    }
  };

  useEffect(load, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="PORTFOLIO / 05" title={t("投资组合", "Portfolio")} />
        <Loading label={t("正在加载组合…", "Loading portfolio…")} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="PORTFOLIO / 05" title={t("投资组合", "Portfolio")} />
        <ErrorBox message={error} onRetry={load} />
      </div>
    );
  }

  const pf = data?.portfolio;
  const positions = data?.positions || [];
  const exposure = Object.entries(data?.industry_exposure || {}).sort((a, b) => b[1] - a[1]);
  const snapshotDate = positions[0]?.as_of;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="PORTFOLIO / 05"
        title={t("投资组合", "Portfolio")}
        desc={`${session.org.name_cn} · ${locale === "en" ? session.role_label_en : session.role_label_cn} · ${t("展示批准后的持仓与敞口；未成交的批准不计入持仓。", "Approved positions and exposures; unexecuted approvals are not positions.")}`}
        actions={<Badge tone="gold">{pf?.base_currency || "CNY"} {t("基准", "base")}</Badge>}
      />

      {flash ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm text-emerald-700">
          {flash}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          [t("组合净值（CNY）", "NAV (CNY)"), fmtMoney(data?.nav)],
          [t("现金（CNY）", "Cash (CNY)"), fmtMoney(data?.cash)],
          [t("已投资（CNY）", "Invested (CNY)"), fmtMoney(data?.invested)],
          [t("仓位（已投资/净值）", "Exposure (invested/NAV)"), fmtPct(data?.invested_ratio)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-[#dde5f2] bg-white p-5">
            <p className="text-xs text-[#68738b]">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-[#171923]">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Card
          title={t("持仓明细", "Positions")}
          desc={t("按最新持仓快照展示；持仓只在确认成交后更新。成本为快照成本，权重按市值/净值计算。", "Latest position snapshot; positions update only after a confirmed fill. Cost is snapshot cost; weight = market value / NAV.")}
          actions={
            <div className="flex flex-wrap gap-1.5">
              <Badge>{positions.length} {t("只", "names")}</Badge>
              <DataFreshness date={snapshotDate} label={t("快照", "Snapshot")} />
            </div>
          }
        >
          {positions.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[#e3eaf8] text-[11px] text-[#77718c]">
                    <th className="py-2">{t("标的", "Symbol")}</th>
                    <th className="py-2">{t("行业", "Industry")}</th>
                    <th className="py-2 text-right">{t("数量（股）", "Qty (shares)")}</th>
                    <th className="py-2 text-right">{t("成本（CNY/股）", "Cost (CNY/sh)")}</th>
                    <th className="py-2 text-right">{t("市值（CNY）", "Value (CNY)")}</th>
                    <th className="py-2 text-right">{t("权重（占净值）", "Weight (of NAV)")}</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id} className="border-b border-[#eef1f8] last:border-0">
                      <td className="py-2.5">
                        <p className="font-medium text-[#252533]">{p.name || p.symbol}</p>
                        <p className="font-mono text-[10px] text-[#77718c]">{p.symbol}</p>
                        {p.market && p.market !== "CN" ? (
                          <p
                            className="text-[10px] text-amber-700"
                            title={t("美股/港股暂无财务、公告、行业与指数数据源；只有行情。", "No fundamental, filing, industry or index data source for US/HK; prices only.")}
                          >
                            {t("暂无数据源", "No data source")}
                          </p>
                        ) : null}
                      </td>
                      <td className="py-2.5 text-xs text-[#68738b]">{industryLabel(p.industry, locale)}</td>
                      <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.qty)}</td>
                      <td className="py-2.5 text-right font-mono text-xs">
                        {p.cost == null ? (
                          <span className="text-[#a9a4bd]" title={t("缺少成本价，无法计算已实现/未实现收益。", "Cost basis missing; realized/unrealized return cannot be computed.")}>
                            {t("成本待补充", "Cost TBD")}
                          </span>
                        ) : (
                          fmtMoney(p.cost, 2)
                        )}
                      </td>
                      <td className="py-2.5 text-right font-mono text-xs">
                        {p.market_value == null ? t("待补充", "TBD") : fmtMoney(p.market_value)}
                      </td>
                      <td className="py-2.5 text-right font-mono text-xs">
                        {p.weight == null ? (
                          <span className="text-[#a9a4bd]" title={t("缺少市值或净值，无法计算权重。", "Weight cannot be computed without market value or NAV.")}>
                            {t("权重待补充", "Weight TBD")}
                          </span>
                        ) : (
                          fmtPct(p.weight)
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>
              <PieChart className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
              {t("还没有持仓。授权并执行后，持仓才会出现。", "No positions yet; they appear after an authorization is executed.")}
            </Empty>
          )}
        </Card>

        <div className="space-y-4">
          <Card title={t("组合约束", "Portfolio constraints")} desc={t("内部演示政策，不是监管限额。", "Internal demo policy, not a regulatory limit.")}>
            <Field label={t("单股仓位上限", "Single-name cap")} value="15%" />
            <Field label={t("最低现金储备", "Minimum cash")} value="10%" />
            <Field label={t("参考净值（CNY）", "Reference NAV (CNY)")} value={fmtMoney(pf?.nav)} />
            <Field
              label={t("组合状态", "Status")}
              value={
                <Badge tone={positions.length ? "green" : "slate"}>
                  {positions.length ? t(`有持仓 ${positions.length} 只`, `${positions.length} held`) : t("空仓", "Empty")}
                </Badge>
              }
            />
            <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-[#77718c]">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" />
              {t("风控硬阻断不可由 Chairman 或 AI 绕过；解除冻结须独立风控重新核验。", "Hard risk blocks cannot be bypassed by Chairman or AI; unfreezing requires a fresh independent risk review.")}
            </p>
          </Card>

          <Card title={t("行业敞口", "Sector exposure")}>
            {exposure.length ? (
              <div className="space-y-2">
                {exposure.map(([name, weight]) => (
                  <div key={name}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="text-[#68738b]">
                        {name === "未分类" ? t("行业待补充", "Sector TBD") : name}
                      </span>
                      <span className="font-mono text-[#171923]">{fmtPct(weight)}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#eef3ff]">
                      <div
                        className="h-full rounded-full bg-[#7950ba]"
                        style={{ width: `${Math.min(100, Number(weight) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
                <p className="pt-1 text-[10px] leading-relaxed text-[#77718c]">
                  {t(
                    "“行业待补充”表示持仓缺少行业映射，仍计入总仓位；不是零敞口。",
                    "'Sector TBD' means the holding lacks an industry mapping; it is still included in total exposure, not zero.",
                  )}
                </p>
                <p className="text-[10px] leading-relaxed text-[#77718c]">
                  {t(
                    "指数/ETF 成分权重已在数据平台（index_membership，含空权重与 0 的区分），等待 PG 服务层同步；展示时空权重显示“权重待补充”，不按 0 计入。",
                    "Index/ETF constituent weights exist in the data platform (index_membership, with null vs 0 distinguished) and await PG service-layer sync; missing weights show 'Weight TBD' and are not treated as zero.",
                  )}
                </p>
              </div>
            ) : (
              <Empty>{t("暂无行业敞口。", "No sector exposure.")}</Empty>
            )}
          </Card>
        </div>
      </div>

      <Card
        title={t("执行异常", "Execution exceptions")}
        desc={t(
          "审批通过后会自动模拟成交；停牌、无有效价格或对账差异会登记在这里，人工核对后关闭。",
          "Approvals auto-execute; trading halts, missing prices or reconciliation mismatches are recorded here and closed after manual review.",
        )}
        actions={
          <Badge tone={exceptions.length ? "red" : "green"}>
            {exceptions.length} {t("条待处理", "open")}
          </Badge>
        }
      >
        {exceptions.length ? (
          <ul className="space-y-2">
            {exceptions.map((ex) => (
              <li key={ex.id} className="rounded-xl border border-red-100 bg-red-50/40 p-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-red-700">
                    {EXCEPTION_TYPE[ex.type] ? (locale === "en" ? EXCEPTION_TYPE[ex.type][1] : EXCEPTION_TYPE[ex.type][0]) : ex.type}
                  </span>
                  <Button
                    variant="ghost"
                    disabled={resolving === ex.id}
                    onClick={() => void resolveException(ex.id)}
                  >
                    {resolving === ex.id ? t("处理中…", "Resolving…") : t("标记已处理", "Resolve")}
                  </Button>
                </div>
                <p className="mt-1 text-[#68738b]">
                  {typeof ex.detail === "string" ? ex.detail : ex.detail?.text || "—"}
                </p>
                <p className="mt-1 text-[10px] text-[#77718c]">
                  {t("授权", "Authorization")} #{ex.authorization_id ?? "—"} · {fmtDateTime(ex.created_at)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>{t("没有待处理的执行异常。", "No open execution exceptions.")}</Empty>
        )}
      </Card>

      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t("组合数据为演示账本；A 股价格来自公开 EOD 数据。审批通过后自动模拟成交，持仓随成交更新；配置与偏离只做展示，不自动调仓。", "Portfolio is a demo ledger; A-share prices come from public EOD data. Approvals auto-execute and positions update with fills; allocation and deviation are display-only, with no auto rebalancing.")}
      </p>
    </div>
  );
}
