import { useEffect, useState } from "react";
import { ArrowLeftRight, PlayCircle, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtNum, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "./instUi";

type Authorization = {
  id: number;
  status: string;
  issued_at: string;
  proposal_id: number;
  symbol: string;
  company_name: string;
  version_no: number;
  snapshot: Record<string, any>;
};

type PortfolioData = {
  cash: number;
  nav: number;
  invested: number;
  invested_ratio: number;
  positions: Array<{ id: number; symbol: string; name?: string; qty: number; market_value: number; weight: number }>;
};

export function InstExecutionPage() {
  const session = useInstSession();
  const { t } = useInstLocale();
  const [items, setItems] = useState<Authorization[]>([]);
  const [pf, setPf] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const canWrite = (session.permissions.execution || "none") === "write";

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      instApi<{ items: Authorization[] }>("/authorizations?status=qualified"),
      instApi<PortfolioData>("/portfolio"),
    ])
      .then(([a, p]) => {
        setItems(a.items || []);
        setPf(p);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const execute = async (id: number) => {
    setBusy(id);
    setError(null);
    setMessage(null);
    try {
      const res = await instApi<{ idempotent: boolean; order: Record<string, any>; cash: number }>(
        `/authorizations/${id}/execute`,
        { method: "POST", body: {} },
      );
      setMessage(
        res.idempotent
          ? t("该授权已执行过，返回原执行结果（幂等拦截）。", "Already executed; the original result is returned (idempotent).")
          : `${t("模拟成交", "Simulated fill")}：${res.order?.side === "buy" ? t("买入", "Buy") : t("卖出", "Sell")} ${fmtMoney(res.order?.qty)} @ ${fmtNum(res.order?.price, 2)}`,
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="EXECUTION / 07" title={t("交易执行", "Execution")} />
        <Loading label={t("正在加载授权…", "Loading authorizations…")} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="EXECUTION / 07"
        title={t("交易执行", "Execution")}
        desc={t("只执行有效授权；批准不等于成交，只有确认成交才更新持仓。默认为 SimBroker 纸面执行。", "Only qualified authorizations are executed; approval is not a fill. Default is SimBroker paper execution.")}
        actions={<Badge tone="gold">{t("SimBroker · 无真实交易", "SimBroker · no real trading")}</Badge>}
      />

      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {message ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm text-emerald-700">
          {message}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          [t("授权可用", "Qualified authorizations"), String(items.length)],
          [t("组合现金", "Portfolio cash"), fmtMoney(pf?.cash)],
          [t("组合净值", "Portfolio NAV"), fmtMoney(pf?.nav)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-[#e7e3d8] bg-white p-5">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Card title={t("可执行授权", "Executable authorizations")} desc={t("只显示 qualified 授权；重复提交由服务端幂等拦截。", "Only qualified authorizations; duplicate submissions are idempotent at the server.")}>
          {items.length ? (
            <div className="space-y-3">
              {items.map((a) => {
                const s = a.snapshot || {};
                return (
                  <article key={a.id} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">{a.company_name}</h3>
                        <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                          AUTH-{a.id} · {a.symbol} · {t("议案", "Proposal")} #{a.proposal_id}
                        </p>
                      </div>
                      <StatusBadge status={a.status} />
                    </div>
                    <div className="mt-3 grid gap-x-6 sm:grid-cols-2">
                      <Field label={t("目标仓位", "Target weight")} value={fmtPct(s.target_weight)} />
                      <Field label={t("价格区间", "Price range")} value={`${fmtNum(s.price_low, 2)} - ${fmtNum(s.price_high, 2)}`} />
                      <Field label={t("账户", "Account")} value={String(s.account || "—")} />
                      <Field label={t("有效期", "Valid until")} value={String(s.valid_until || "—")} />
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <p className="text-[11px] text-slate-400">{t("执行前会再次校验授权、版本、现金与价格。", "Authorization, version, cash and price are re-checked before execution.")}</p>
                      <Button variant="gold" disabled={!canWrite || busy === a.id} onClick={() => execute(a.id)}>
                        <PlayCircle className="mr-1 h-4 w-4" />
                        {busy === a.id ? t("执行中…", "Executing…") : t("模拟执行", "Simulate fill")}
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <Empty>
              <ArrowLeftRight className="mx-auto mb-2 h-6 w-6 text-slate-300" />
              {t("没有可执行授权。完成合伙人、Chairman 与风控复核后生成授权。", "No executable authorizations. Complete partner, Chairman and risk reviews first.")}
            </Empty>
          )}
        </Card>

        <Card title={t("执行约束", "Execution constraints")} desc={t("执行角色不得修改标的、方向、仓位与价格范围。", "Execution may not change symbol, direction, size or price range.")}>
          <Field label={t("单股仓位上限", "Single-name cap")} value="15%" />
          <Field label={t("交易后现金下限", "Post-trade cash floor")} value="10%" />
          <Field label={t("重复提交", "Duplicate submission")} value={t("幂等拦截", "Idempotent")} />
          <Field label={t("异常处理", "Exception handling")} value={t("待对账 / 人工处置", "Reconciliation / manual")} />
          <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-slate-400">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />
            {t("SimBroker 只在服务端生成纸面订单与成交；未配置真实适配时不能真实下单。", "SimBroker only creates paper orders/fills server-side; without a real adapter no live order is sent.")}
          </p>
        </Card>
      </div>

      <Card title={t("当前持仓", "Current positions")}>
        {pf?.positions?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[#f0ece2] text-[11px] text-slate-400">
                  <th className="py-2">{t("标的", "Symbol")}</th>
                  <th className="py-2 text-right">{t("数量", "Qty")}</th>
                  <th className="py-2 text-right">{t("市值", "Value")}</th>
                  <th className="py-2 text-right">{t("权重", "Weight")}</th>
                </tr>
              </thead>
              <tbody>
                {pf.positions.map((p) => (
                  <tr key={p.id} className="border-b border-[#f7f4ec] last:border-0">
                    <td className="py-2.5">
                      <p className="font-medium text-slate-800">{p.name || p.symbol}</p>
                      <p className="font-mono text-[10px] text-slate-400">{p.symbol}</p>
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.qty)}</td>
                    <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.market_value)}</td>
                    <td className="py-2.5 text-right font-mono text-xs">{fmtPct(p.weight)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>{t("暂无持仓。", "No positions.")}</Empty>
        )}
      </Card>
    </div>
  );
}
