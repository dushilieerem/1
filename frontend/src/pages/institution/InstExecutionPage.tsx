import { useEffect, useState } from "react";
import { ArrowLeftRight, PlayCircle, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtNum, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
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
          ? "该授权已执行过，返回原执行结果（幂等拦截）。"
          : `模拟成交：${res.order?.side === "buy" ? "买入" : "卖出"} ${fmtMoney(res.order?.qty)} 股 @ ${fmtNum(res.order?.price, 2)}`,
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
        <PageHeader eyebrow="EXECUTION / 07" title="交易执行" />
        <Loading label="正在加载授权…" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="EXECUTION / 07"
        title="交易执行"
        desc="只执行有效授权；批准不等于成交，只有确认成交才更新持仓。默认为 SimBroker 纸面执行。"
        actions={<Badge tone="gold">SimBroker · 无真实交易</Badge>}
      />

      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {message ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm text-emerald-700">
          {message}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ["授权可用", `${items.length} 笔`],
          ["组合现金", fmtMoney(pf?.cash)],
          ["组合净值", fmtMoney(pf?.nav)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-[#e7e3d8] bg-white p-5">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Card title="可执行授权" desc="只显示 qualified 授权；重复提交由服务端幂等拦截。">
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
                          AUTH-{a.id} · {a.symbol} · 议案 #{a.proposal_id}
                        </p>
                      </div>
                      <StatusBadge status={a.status} />
                    </div>
                    <div className="mt-3 grid gap-x-6 sm:grid-cols-2">
                      <Field label="目标仓位" value={fmtPct(s.target_weight)} />
                      <Field label="价格区间" value={`${fmtNum(s.price_low, 2)} - ${fmtNum(s.price_high, 2)}`} />
                      <Field label="账户" value={String(s.account || "—")} />
                      <Field label="有效期" value={String(s.valid_until || "—")} />
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <p className="text-[11px] text-slate-400">执行前会再次校验授权、版本、现金与价格。</p>
                      <Button variant="gold" disabled={!canWrite || busy === a.id} onClick={() => execute(a.id)}>
                        <PlayCircle className="mr-1 h-4 w-4" />
                        {busy === a.id ? "执行中…" : "模拟执行"}
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <Empty>
              <ArrowLeftRight className="mx-auto mb-2 h-6 w-6 text-slate-300" />
              没有可执行授权。完成合伙人、Chairman 与风控复核后生成授权。
            </Empty>
          )}
        </Card>

        <Card title="执行约束" desc="执行角色不得修改标的、方向、仓位与价格范围。">
          <Field label="单股仓位上限" value="15%" />
          <Field label="交易后现金下限" value="10%" />
          <Field label="重复提交" value="幂等拦截" />
          <Field label="异常处理" value="待对账 / 人工处置" />
          <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-slate-400">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />
            SimBroker 只在服务端生成纸面订单与成交；未配置真实适配时不能真实下单。
          </p>
        </Card>
      </div>

      <Card title="当前持仓">
        {pf?.positions?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[#f0ece2] text-[11px] text-slate-400">
                  <th className="py-2">标的</th>
                  <th className="py-2 text-right">数量</th>
                  <th className="py-2 text-right">市值</th>
                  <th className="py-2 text-right">权重</th>
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
          <Empty>暂无持仓。</Empty>
        )}
      </Card>
    </div>
  );
}
