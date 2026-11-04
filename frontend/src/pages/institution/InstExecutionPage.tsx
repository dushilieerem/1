import { useEffect, useState } from "react";
import { ArrowLeftRight, PlayCircle, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtNum, fmtPct, fmtDateTime } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge, industryLabel } from "./instUi";

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

const DIRECTION_LABEL: Record<string, [string, string]> = {
  buy: ["买入", "Buy"],
  sell: ["卖出", "Sell"],
  exit: ["退出", "Exit"],
};

const EXCEPTION_TYPE: Record<string, [string, string]> = {
  suspended_or_st: ["停牌或 ST", "Suspended / ST"],
  price_invalid: ["无有效价格", "No valid price"],
  manual: ["手工登记", "Manual"],
  reconciliation: ["对账差异", "Reconciliation mismatch"],
};

type PortfolioData = {
  cash: number;
  nav: number;
  invested: number;
  invested_ratio: number;
  positions: Array<{
    id: number;
    symbol: string;
    name?: string;
    industry?: string;
    qty: number;
    cost?: number;
    market_value: number;
    weight: number;
  }>;
};

export function InstExecutionPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const [items, setItems] = useState<Authorization[]>([]);
  const [pf, setPf] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [prechecks, setPrechecks] = useState<Record<number, Record<string, any>>>({});
  const [exceptions, setExceptions] = useState<Array<Record<string, any>>>([]);

  const canWrite = (session.permissions.execution || "none") === "write";

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      instApi<{ items: Authorization[] }>("/authorizations?status=qualified"),
      instApi<PortfolioData>("/portfolio"),
      instApi<{ items: Array<Record<string, any>> }>("/execution/exceptions?status=open").catch(
        () => ({ items: [] as Array<Record<string, any>> }),
      ),
    ])
      .then(([a, p, ex]) => {
        setItems(a.items || []);
        setPf(p);
        setExceptions(ex.items || []);
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
      const fillMsg = res.idempotent
        ? t("该授权已执行过，返回原执行结果（幂等拦截）。", "Already executed; the original result is returned (idempotent).")
        : `${t("模拟成交", "Simulated fill")}：${res.order?.side === "buy" ? t("买入", "Buy") : t("卖出", "Sell")} ${fmtMoney(res.order?.qty)} @ ${fmtNum(res.order?.price, 2)}`;
      let recMsg = "";
      try {
        const rec = await instApi<{ matched: boolean; differences?: string[] }>(
          `/authorizations/${id}/reconcile`,
          { method: "POST" },
        );
        recMsg = rec.matched
          ? ` · ${t("对账一致", "reconciled")}`
          : ` · ${t("对账差异", "reconciliation mismatch")}：${(rec.differences || []).join("；")}`;
      } catch {
        /* 对账失败不覆盖成交结果 */
      }
      setMessage(`${fillMsg}${recMsg}`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const check = async (id: number) => {
    setError(null);
    try {
      const res = await instApi<Record<string, any>>(`/authorizations/${id}/precheck`);
      setPrechecks((prev) => ({ ...prev, [id]: res }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const resolveException = async (id: number) => {
    setError(null);
    try {
      await instApi(`/execution/exceptions/${id}/resolve`, {
        method: "POST",
        body: { status: "resolved", resolution: t("已人工核对", "Checked manually") },
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm text-emerald-700">
          {message}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          [t("可执行授权（个）", "Qualified authorizations"), String(items.length)],
          [t("组合现金（CNY）", "Portfolio cash (CNY)"), fmtMoney(pf?.cash)],
          [t("组合净值（CNY）", "Portfolio NAV (CNY)"), fmtMoney(pf?.nav)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-[#dde5f2] bg-white p-5">
            <p className="text-xs text-[#68738b]">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-[#171923]">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <Card title={t("可执行授权", "Executable authorizations")} desc={t("只显示 qualified 授权；重复提交由服务端幂等拦截。", "Only qualified authorizations; duplicate submissions are idempotent at the server.")}>
          {items.length ? (
            <div className="space-y-3">
              {items.map((a) => {
                const s = a.snapshot || {};
                return (
                  <article key={a.id} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-semibold text-[#171923]">{a.company_name}</h3>
                        <p className="mt-0.5 text-[11px] text-[#68738b]">
                          {t("授权", "Authorization")} #{a.id} · {a.symbol} · {t("议案", "Proposal")} #{a.proposal_id}
                        </p>
                      </div>
                      <StatusBadge status={a.status} />
                    </div>
                    <div className="mt-3 grid gap-x-6 sm:grid-cols-2">
                      <Field
                        label={t("方向", "Direction")}
                        value={
                          DIRECTION_LABEL[String(s.direction)]
                            ? locale === "en"
                              ? DIRECTION_LABEL[String(s.direction)][1]
                              : DIRECTION_LABEL[String(s.direction)][0]
                            : String(s.direction || "—")
                        }
                      />
                      <Field label={t("目标仓位（占净值）", "Target weight (of NAV)")} value={fmtPct(s.target_weight)} />
                      <Field
                        label={t("价格区间（CNY）", "Price range (CNY)")}
                        value={
                          s.price_low == null && s.price_high == null ? (
                            <span className="text-[#a9a4bd]" title={t("未设置价格区间，执行时不按价格区间校验。", "No price range set; execution will not check price bounds.")}>
                              {t("未设置（不校验价格）", "Not set (no price check)")}
                            </span>
                          ) : (
                            `${fmtNum(s.price_low, 2)} - ${fmtNum(s.price_high, 2)}`
                          )
                        }
                      />
                      <Field
                        label={t("账户", "Account")}
                        value={s.account ? t(`模拟账户 ${s.account}`, `Sim account ${s.account}`) : t("未指定", "Not specified")}
                      />
                      <Field label={t("有效期", "Valid until")} value={String(s.valid_until || t("未设置", "Not set"))} />
                    </div>
                    {s.price_low == null && s.price_high == null ? (
                      <p className="mt-2 text-[10px] leading-relaxed text-[#77718c]">
                        {t(
                          "价格区间未设置：执行时不校验成交价上下限。",
                          "No price range: execution does not enforce price bounds.",
                        )}
                      </p>
                    ) : null}
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <p className="text-[11px] text-[#77718c]">{t("执行前会再次校验授权、版本、现金与价格。", "Authorization, version, cash and price are re-checked before execution.")}</p>
                      <div className="flex gap-2">
                        <Button variant="ghost" onClick={() => check(a.id)}>
                          {t("执行前校验", "Pre-check")}
                        </Button>
                        <Button variant="gold" disabled={!canWrite || busy === a.id} onClick={() => execute(a.id)}>
                          <PlayCircle className="mr-1 h-4 w-4" />
                          {busy === a.id ? t("执行中…", "Executing…") : t("模拟执行", "Simulate fill")}
                        </Button>
                      </div>
                    </div>
                    {prechecks[a.id] ? (
                      <ul className="mt-2 space-y-1 rounded-lg bg-white p-2 text-[11px]">
                        {(prechecks[a.id].checks || []).map((c: Record<string, any>) => (
                          <li key={c.key} className={c.ok ? "text-[#68738b]" : "text-red-600"}>
                            {c.ok ? "✓" : "✕"} {c.label}：{c.detail}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                );
              })}
            </div>
          ) : (
            <Empty>
              <ArrowLeftRight className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
              {t("没有可执行授权。完成合伙人、Chairman 与风控复核后生成授权。", "No executable authorizations. Complete partner, Chairman and risk reviews first.")}
            </Empty>
          )}
        </Card>

        <Card title={t("执行约束", "Execution constraints")} desc={t("执行角色不得修改标的、方向、仓位与价格范围。", "Execution may not change symbol, direction, size or price range.")}>
          <Field label={t("单股仓位上限", "Single-name cap")} value="15%" />
          <Field label={t("交易后现金下限", "Post-trade cash floor")} value="10%" />
          <Field
            label={t("重复提交", "Duplicate submission")}
            value={t("返回同一订单，不重复成交", "Same order returned; no double fill")}
          />
          <Field label={t("异常处理", "Exception handling")} value={t("待对账 / 人工处置", "Reconciliation / manual")} />
          <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-[#77718c]">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" />
            {t("SimBroker 只在服务端生成纸面订单与成交；未配置真实适配时不能真实下单。", "SimBroker only creates paper orders/fills server-side; without a real adapter no live order is sent.")}
          </p>
        </Card>
      </div>

      <Card title={t("执行异常", "Execution exceptions")} desc={t("执行被阻断或对账不一致时自动登记；需人工核对后关闭。", "Recorded when execution is blocked or reconciliation mismatches; close after manual review.")}>
        {exceptions.length ? (
          <ul className="space-y-2">
            {exceptions.map((ex) => (
              <li key={ex.id} className="rounded-xl border border-red-100 bg-red-50/40 p-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-red-700">
                    {EXCEPTION_TYPE[String(ex.type)]
                      ? locale === "en"
                        ? EXCEPTION_TYPE[String(ex.type)][1]
                        : EXCEPTION_TYPE[String(ex.type)][0]
                      : String(ex.type)}
                  </span>
                  <Button variant="ghost" onClick={() => void resolveException(Number(ex.id))}>
                    {t("标记已处理", "Resolve")}
                  </Button>
                </div>
                <p className="mt-1 text-[#68738b]">{String(ex.detail || "—")}</p>
                <p className="mt-1 text-[10px] text-[#77718c]">
                  {t("授权", "Authorization")} #{String(ex.authorization_id ?? "—")} ·{" "}
                  {fmtDateTime(String(ex.created_at || ""))}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>{t("没有待处理的执行异常。", "No open execution exceptions.")}</Empty>
        )}
      </Card>

      <Card title={t("当前持仓", "Current positions")}>
        {pf?.positions?.length ? (
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
                {pf.positions.map((p) => (
                  <tr key={p.id} className="border-b border-[#eef1f8] last:border-0">
                    <td className="py-2.5">
                      <p className="font-medium text-[#252533]">{p.name || p.symbol}</p>
                      <p className="font-mono text-[10px] text-[#77718c]">{p.symbol}</p>
                    </td>
                    <td className="py-2.5 text-xs text-[#68738b]">{industryLabel(p.industry, locale)}</td>
                    <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.qty)}</td>
                    <td className="py-2.5 text-right font-mono text-xs">
                      {p.cost == null ? (
                        <span className="text-[#a9a4bd]" title={t("缺少成本价，无法计算收益。", "Cost basis missing; return cannot be computed.")}>
                          {t("待补充", "TBD")}
                        </span>
                      ) : (
                        fmtMoney(p.cost, 2)
                      )}
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs">{fmtMoney(p.market_value)}</td>
                    <td className="py-2.5 text-right font-mono text-xs">
                      {p.weight == null ? t("待补充", "TBD") : fmtPct(p.weight)}
                    </td>
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
