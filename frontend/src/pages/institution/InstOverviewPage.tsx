import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { Badge, ErrorBox, Loading } from "./instUi";

type Overview = {
  companies: number;
  active_cases: number;
  pending_approvals: number;
  my_pending: number;
  risk_blocks: number;
  monitor_alerts: number;
  data_date?: string;
  portfolio: {
    nav: number;
    cash: number;
    invested_ratio: number;
  };
  policy: {
    max_single_weight: number;
    min_cash_ratio: number;
    nav: number;
    policy_version: string;
  };
};

const WORKFLOW = [
  ["机会发现", "立项 / 观察 / 放弃"],
  ["公司研究", "六维研究 · 资料包"],
  ["投资辩论", "两轮 · 保留异议"],
  ["组合配置", "合伙人提案"],
  ["两级审批", "Chairman · 独立风控"],
  ["执行与投后", "授权 · 台账 · 退出"],
];

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-2xl border border-[#e7e3d8] bg-white p-5">
      <p className="text-xs tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold text-slate-900">{value}</p>
      <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{note}</p>
    </div>
  );
}

export function InstOverviewPage() {
  const session = useInstSession();
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const allowed = (key: string) => (session.permissions[key] || "none") !== "none";

  const load = () => {
    setLoading(true);
    setError(null);
    instApi<Overview>("/overview")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <Loading label="正在加载驾驶舱…" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <ErrorBox message={error || "驾驶舱数据不可用"} onRetry={load} />
      </div>
    );
  }

  const attention = [
    { label: "待我处理的议案", count: data.my_pending ?? data.pending_approvals, to: "/inst/approvals", key: "approvals" },
    { label: "风控硬性阻断", count: data.risk_blocks, to: "/inst/approvals", key: "approvals" },
    { label: "监控预警", count: data.monitor_alerts, to: "/inst/monitor", key: "monitor" },
    { label: "在研研究案", count: data.active_cases, to: "/inst/research", key: "research" },
  ].filter((item) => allowed(item.key));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="rounded-2xl border border-[#e7e3d8] bg-white px-6 py-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] tracking-[0.18em] text-[#8a6a2f]">INVESTMENT OFFICE / 01</p>
            <h1 className="mt-2 font-display text-2xl font-semibold text-slate-900 sm:text-3xl">
              以企业为起点，以证据做决策
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
              发现卓越企业，让每一项投资判断都经得起反方检验。当前为
              <span className="mx-1 font-medium text-slate-800">{session.org.name_cn}</span>
              · {session.role_label_cn}视图。
            </p>
          </div>
          <div className="rounded-xl border border-[#c9a15e]/40 bg-[#fbf6ea] px-3 py-2 text-[11px] leading-relaxed text-[#8a6a2f]">
            模拟环境 · 无真实交易
            <br />
            数据日 {data.data_date || "—"} · 不构成投资建议
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="模拟资产净值 · CNY"
          value={fmtMoney(data.portfolio?.nav)}
          note={`现金 ${fmtMoney(data.portfolio?.cash)} · 仓位 ${fmtPct(data.portfolio?.invested_ratio)}`}
        />
        <Metric label="在研研究案" value={String(data.active_cases).padStart(2, "0")} note={`研究对象 ${data.companies} 个`} />
        <Metric
          label="待审批 / 风控阻断"
          value={`${String(data.pending_approvals).padStart(2, "0")} / ${String(data.risk_blocks).padStart(2, "0")}`}
          note="跨市场共享同一研究流程"
        />
        <Metric
          label="监控预警"
          value={String(data.monitor_alerts).padStart(2, "0")}
          note={`独立风控 · 单股上限 ${fmtPct(data.policy?.max_single_weight)}`}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-[#e7e3d8] bg-white p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-slate-900">今天需要关注</h2>
            <button type="button" onClick={load} className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-600">
              <RefreshCw className="h-3 w-3" /> 刷新
            </button>
          </div>
          {attention.length ? (
            <ul className="mt-4 divide-y divide-[#f0ece2]">
              {attention.map((item) => (
                <li key={item.label}>
                  <Link
                    to={item.to}
                    className="flex items-center justify-between gap-3 py-3 text-sm text-slate-700 transition-colors hover:text-slate-900"
                  >
                    <span>{item.label}</span>
                    <span className="flex items-center gap-2">
                      <span className={`font-mono text-sm ${item.count > 0 ? "text-[#8a6a2f]" : "text-slate-400"}`}>
                        {String(item.count).padStart(2, "0")}
                      </span>
                      <ArrowUpRight className="h-3.5 w-3.5 text-slate-300" aria-hidden />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 rounded-lg bg-[#faf8f2] px-3 py-6 text-center text-sm text-slate-500">
              当前角色没有需要处理的审批或监控事项。
            </p>
          )}
          <p className="mt-4 text-[11px] leading-relaxed text-slate-400">
            驾驶舱只汇总待办与状态；审批、风控与执行分别在对应工作区完成。
          </p>
        </div>

        <div className="rounded-2xl border border-[#e7e3d8] bg-white p-6">
          <h2 className="font-display text-lg font-semibold text-slate-900">组合约束</h2>
          <dl className="mt-4 space-y-3 text-sm">
            {[
              ["单股仓位上限", fmtPct(data.policy?.max_single_weight)],
              ["最低现金储备", fmtPct(data.policy?.min_cash_ratio)],
              ["参考净值", fmtMoney(data.policy?.nav)],
              ["政策版本", data.policy?.policy_version || "—"],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-[#f0ece2] pb-3">
                <dt className="text-slate-500">{k}</dt>
                <dd className="font-mono text-slate-900">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-slate-400">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" aria-hidden />
            以上为内部演示政策，不是监管限额；正式政策按基金合同、账户与市场分别配置。
          </p>
        </div>
      </section>

      <section className="rounded-2xl border border-[#e7e3d8] bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg font-semibold text-slate-900">投资工作流</h2>
          <Badge tone="gold">九工作区已接入首版闭环</Badge>
        </div>
        <ol className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {WORKFLOW.map(([title, desc], index) => (
            <li key={title} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-4">
              <span className="font-mono text-[11px] text-[#8a6a2f]">{String(index + 1).padStart(2, "0")}</span>
              <p className="mt-1 text-sm font-medium text-slate-800">{title}</p>
              <p className="mt-1 text-[11px] text-slate-500">{desc}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
