import { useEffect, useState } from "react";
import { PieChart, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "./instUi";

type Position = {
  id: number;
  symbol: string;
  name?: string;
  industry?: string;
  market?: string;
  qty: number;
  cost: number;
  market_value: number;
  weight: number;
  as_of: string;
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
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    instApi<PortfolioData>("/portfolio")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
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

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="PORTFOLIO / 05"
        title={t("投资组合", "Portfolio")}
        desc={`${session.org.name_cn} · ${locale === "en" ? session.role_label_en : session.role_label_cn} · ${t("展示批准后的持仓与敞口；未成交的批准不计入持仓。", "Approved positions and exposures; unexecuted approvals are not positions.")}`}
        actions={<Badge tone="gold">{pf?.base_currency || "CNY"} 基准</Badge>}
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          [t("组合净值", "NAV"), fmtMoney(data?.nav)],
          [t("现金", "Cash"), fmtMoney(data?.cash)],
          [t("已投资", "Invested"), fmtMoney(data?.invested)],
          [t("仓位", "Exposure"), fmtPct(data?.invested_ratio)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-[#e7e3d8] bg-white p-5">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card
          title={t("持仓明细", "Positions")}
          desc={t("按最新持仓快照展示；持仓只在确认成交后更新。", "Latest position snapshot; positions update only after a confirmed fill.")}
          actions={<Badge>{positions.length} 只</Badge>}
        >
          {positions.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[#f0ece2] text-[11px] text-slate-400">
                    <th className="py-2">标的</th>
                    <th className="py-2">行业</th>
                    <th className="py-2 text-right">数量</th>
                    <th className="py-2 text-right">成本</th>
                    <th className="py-2 text-right">市值</th>
                    <th className="py-2 text-right">权重</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id} className="border-b border-[#f7f4ec] last:border-0">
                      <td className="py-2.5">
                        <p className="font-medium text-slate-800">{p.name || p.symbol}</p>
                        <p className="font-mono text-[10px] text-slate-400">{p.symbol}</p>
                      </td>
                      <td className="py-2.5 text-xs text-slate-500">{p.industry || "—"}</td>
                      <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.qty)}</td>
                      <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.cost, 2)}</td>
                      <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.market_value)}</td>
                      <td className="py-2.5 text-right font-mono text-xs">{fmtPct(p.weight)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>
              <PieChart className="mx-auto mb-2 h-6 w-6 text-slate-300" />
              还没有持仓。授权并执行后，持仓才会出现。
            </Empty>
          )}
        </Card>

        <div className="space-y-4">
          <Card title={t("组合约束", "Portfolio constraints")} desc={t("内部演示政策，不是监管限额。", "Internal demo policy, not a regulatory limit.")}>
            <Field label={t("单股仓位上限", "Single-name cap")} value="15%" />
            <Field label={t("最低现金储备", "Minimum cash")} value="10%" />
            <Field label={t("参考净值", "Reference NAV")} value={fmtMoney(pf?.nav)} />
            <Field label={t("组合状态", "Status")} value={<StatusBadge status={positions.length ? "qualified" : "draft"} />} />
            <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-slate-400">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />
              风控硬阻断不可由 Chairman 或 AI 绕过；解除冻结须独立风控重新核验。
            </p>
          </Card>

          <Card title={t("行业敞口", "Sector exposure")}>
            {exposure.length ? (
              <div className="space-y-2">
                {exposure.map(([name, weight]) => (
                  <div key={name}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="text-slate-600">{name}</span>
                      <span className="font-mono text-slate-900">{fmtPct(weight)}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#f0ece2]">
                      <div
                        className="h-full rounded-full bg-[#c9a15e]"
                        style={{ width: `${Math.min(100, Number(weight) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty>{t("暂无行业敞口。", "No sector exposure.")}</Empty>
            )}
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-slate-400">
        组合数据为演示账本；A 股价格来自公开 EOD 数据。配置与偏离只做展示，不自动调仓。
      </p>
    </div>
  );
}
