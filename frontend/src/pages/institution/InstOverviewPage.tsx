import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
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

const WORKFLOW: Array<[string, string, string, string]> = [
  ["机会发现", "Idea discovery", "立项 / 观察 / 放弃", "Origination / watch / drop"],
  ["公司研究", "Company research", "六维研究 · 资料包", "Six dimensions · evidence pack"],
  ["投资辩论", "Investment debate", "两轮 · 保留异议", "Two rounds · dissent kept"],
  ["组合配置", "Portfolio sizing", "合伙人提案", "Partner proposal"],
  ["两级审批", "Two-level approval", "Chairman · 独立风控", "Chairman · independent risk"],
  ["执行与投后", "Execution & monitoring", "授权 · 台账 · 退出", "Authorization · ledger · exit"],
];

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-xl border border-[#dde5f2] bg-white p-5">
      <p className="text-xs tracking-wide text-[#68738b]">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold text-[#171923]">{value}</p>
      <p className="mt-2 text-[11px] leading-relaxed text-[#77718c]">{note}</p>
    </div>
  );
}

/** 按工作日估算数据落后几天；不是交易所日历，只用于提示“数据不是最新”。 */
function tradingDaysLag(dateStr?: string): number | null {
  if (!dateStr) return null;
  const start = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(start.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let count = 0;
  const cur = new Date(start);
  while (cur < today) {
    cur.setDate(cur.getDate() + 1);
    const day = cur.getDay();
    if (day !== 0 && day !== 6 && cur <= today) count += 1;
  }
  return count;
}

export function InstOverviewPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
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
        <Loading label={t("正在加载驾驶舱…", "Loading cockpit…")} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <ErrorBox message={error || t("驾驶舱数据不可用", "Cockpit data unavailable")} onRetry={load} />
      </div>
    );
  }

  const lag = tradingDaysLag(data.data_date);
  const attention = [
    { label: t("待我处理的议案", "Proposals awaiting me"), count: data.my_pending ?? data.pending_approvals, to: "/inst/approvals", key: "approvals" },
    { label: t("风控硬性阻断", "Hard risk blocks"), count: data.risk_blocks, to: "/inst/approvals", key: "approvals" },
    { label: t("监控预警", "Monitoring alerts"), count: data.monitor_alerts, to: "/inst/monitor", key: "monitor" },
    { label: t("在研研究案", "Active research cases"), count: data.active_cases, to: "/inst/research", key: "research" },
  ].filter((item) => allowed(item.key));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="relative overflow-hidden rounded-xl border-0 bg-[#f4f0ff] px-6 py-8">
        <span aria-hidden className="pointer-events-none absolute -top-7 right-8 select-none font-serif text-[150px] leading-none text-[#dfd5fa]">
          旸
        </span>
        <div className="relative z-10 flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-[11px] tracking-[0.18em] text-[#b42345]">INVESTMENT OFFICE / 01</p>
            <h1 className="mt-2 font-display text-2xl font-semibold text-[#171923] sm:text-[26px]">
              {t("以企业为起点，以证据做决策", "Start with the business, decide with evidence")}
            </h1>
            <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-[#68738b]">
              {t("发现卓越企业，让每一项投资判断都经得起反方检验。当前为", "Find exceptional businesses; every call must survive the bear case. Current view:")}
              <span className="mx-1 font-medium text-[#252533]">{session.org.name_cn}</span>
              · {locale === "en" ? session.role_label_en : session.role_label_cn}
            </p>
            <Link
              to="/inst/ideas"
              className="mt-4 inline-flex items-center gap-1 rounded-md bg-[#b42345] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#a31f42]"
            >
              {t("发现投资机会", "Discover opportunities")} <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <div className="relative z-10 rounded-xl border border-[#d9c8f0] bg-white/70 px-3 py-2 text-[11px] leading-relaxed text-[#7950ba]">
            {t("模拟环境 · 无真实交易", "Simulated environment · no real trading")}
            <br />
            {t("数据日", "Data date")} {data.data_date || "—"}
            {lag !== null
              ? ` · ${lag > 0 ? t(`约落后 ${lag} 个交易日`, `~${lag} trading days behind`) : t("最新", "Latest")}`
              : ""}
            <br />
            {t("不构成投资建议", "Not investment advice")}
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label={t("模拟资产净值（CNY）", "Simulated NAV (CNY)")}
          value={fmtMoney(data.portfolio?.nav)}
          note={`${t("现金", "Cash")} ${fmtMoney(data.portfolio?.cash)} · ${t("仓位（已投资/净值）", "Exposure (invested/NAV)")} ${fmtPct(data.portfolio?.invested_ratio)}`}
        />
        <Metric
          label={t("在研研究案（个）", "Active research cases")}
          value={String(data.active_cases)}
          note={`${t("公司池", "Universe")} ${Number(data.companies).toLocaleString("zh-CN")} ${t("家", "names")}`}
        />
        <Metric
          label={t("待审批 / 风控阻断（件）", "Pending approvals / risk blocks")}
          value={`${data.pending_approvals} / ${data.risk_blocks}`}
          note={t("任一阻断都不能生成授权", "Any block prevents authorization")}
        />
        <Metric
          label={t("监控预警（条）", "Monitoring alerts")}
          value={String(data.monitor_alerts)}
          note={`${t("独立风控 · 单股上限", "Independent risk · single-name cap")} ${fmtPct(data.policy?.max_single_weight)}`}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-[#dde5f2] bg-white p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-[#171923]">{t("今天需要关注", "Needs attention")}</h2>
            <button type="button" onClick={load} className="inline-flex items-center gap-1 text-[11px] text-[#77718c] hover:text-[#68738b]">
              <RefreshCw className="h-3 w-3" /> {t("刷新", "Refresh")}
            </button>
          </div>
          {attention.length ? (
            <ul className="mt-4 divide-y divide-[#e3eaf8]">
              {attention.map((item) => (
                <li key={item.label}>
                  <Link
                    to={item.to}
                    className="flex items-center justify-between gap-3 py-3 text-sm text-[#505369] transition-colors hover:text-[#171923]"
                  >
                    <span>{item.label}</span>
                    <span className="flex items-center gap-2">
                      <span className={`font-mono text-sm ${item.count > 0 ? "text-[#b42345]" : "text-[#77718c]"}`}>
                        {item.count}
                      </span>
                      <ArrowUpRight className="h-3.5 w-3.5 text-[#a9a4bd]" aria-hidden />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 rounded-lg bg-[#f5f0ff] px-3 py-6 text-center text-sm text-[#68738b]">
              {t("当前角色没有需要处理的审批或监控事项。", "Nothing awaiting this role.")}
            </p>
          )}
          <p className="mt-4 text-[11px] leading-relaxed text-[#77718c]">
            {t("驾驶舱只汇总待办与状态；审批、风控与执行分别在对应工作区完成。", "The cockpit only aggregates to-dos and status; approvals, risk and execution happen in their workspaces.")}
          </p>
        </div>

        <div className="rounded-xl border border-[#dde5f2] bg-white p-6">
          <h2 className="font-display text-lg font-semibold text-[#171923]">{t("组合约束", "Portfolio constraints")}</h2>
          <dl className="mt-4 space-y-3 text-sm">
            {[
              [t("单股仓位上限", "Single-name cap"), fmtPct(data.policy?.max_single_weight)],
              [t("最低现金储备", "Minimum cash"), fmtPct(data.policy?.min_cash_ratio)],
              [t("参考净值（CNY）", "Reference NAV (CNY)"), fmtMoney(data.policy?.nav)],
              [
                t("政策版本", "Policy version"),
                data.policy?.policy_version === "demo-v1"
                  ? t("演示政策 v1", "Demo policy v1")
                  : data.policy?.policy_version || "—",
              ],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-[#e3eaf8] pb-3">
                <dt className="text-[#68738b]">{k}</dt>
                <dd className="font-mono text-[#171923]">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-[#77718c]">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" aria-hidden />
            {t("以上为内部演示政策，不是监管限额；正式政策按基金合同、账户与市场分别配置。", "Internal demo policy, not a regulatory limit; production policy is set per mandate, account and market.")}
          </p>
        </div>
      </section>

      <section className="rounded-xl border border-[#dde5f2] bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg font-semibold text-[#171923]">{t("投资工作流", "Investment workflow")}</h2>
          <Badge tone="gold">{t("九工作区已接入首版闭环", "Nine workspaces wired end to end")}</Badge>
        </div>
        <ol className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {WORKFLOW.map(([zh, en, descZh, descEn], index) => (
            <li key={zh} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-4">
              <span className="font-mono text-[11px] text-[#b42345]">{String(index + 1).padStart(2, "0")}</span>
              <p className="mt-1 text-sm font-medium text-[#252533]">{locale === "en" ? en : zh}</p>
              <p className="mt-1 text-[11px] text-[#68738b]">{locale === "en" ? descEn : descZh}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
