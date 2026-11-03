import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, ClipboardList } from "lucide-react";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "./instUi";

type Position = {
  id: number;
  company_id?: number;
  symbol: string;
  name?: string;
  industry?: string;
  qty: number;
  market_value: number;
  weight: number;
};

type Event = {
  id: number;
  company_id?: number;
  company_name?: string;
  symbol?: string;
  type: string;
  severity: string;
  status: string;
  detail?: { text?: string };
  created_at: string;
};

type ExitCase = {
  id: number;
  company_name: string;
  symbol: string;
  reason_type: string;
  status: string;
  memo?: string;
  case_id?: number;
  case_no?: string;
  proposal_id?: number;
  proposal_status?: string;
  proposal_direction?: string;
  authorization_status?: string;
};

type Thesis = {
  id: number;
  company_name?: string;
  symbol: string;
  thesis: string;
  kpis?: Array<{ name: string; target?: number }>;
  falsifiers?: string[];
  key_assumptions?: string[];
  review_due?: string;
  status: string;
  review_count?: number;
};

type ExitReview = {
  id: number;
  exit_case_id: number;
  realized_return?: number;
  holding_days?: number;
  thesis_verdict: string;
  lessons?: string;
};

type MonitorData = {
  portfolio: {
    cash: number;
    nav: number;
    invested: number;
    invested_ratio: number;
    positions: Position[];
    industry_exposure: Record<string, number>;
  };
  events: Event[];
  exits: ExitCase[];
  theses?: Thesis[];
  exit_reviews?: ExitReview[];
};

const REASON: Record<string, [string, string]> = {
  thesis_invalid: ["论点失效", "Thesis broken"],
  valuation: ["估值透支", "Valuation stretched"],
  better_allocation: ["更优资本配置", "Better allocation"],
  portfolio_constraint: ["组合/资金约束", "Portfolio constraint"],
  other: ["其他", "Other"],
};

export function InstMonitorPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const nav = useNavigate();
  const [data, setData] = useState<MonitorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companyId, setCompanyId] = useState("");
  const [severity, setSeverity] = useState("warning");
  const [detail, setDetail] = useState("");
  const [exitCompany, setExitCompany] = useState("");
  const [exitReason, setExitReason] = useState("thesis_invalid");
  const [exitMemo, setExitMemo] = useState("");
  const [exitBusy, setExitBusy] = useState(false);
  const [thesisCompany, setThesisCompany] = useState("");
  const [thesisText, setThesisText] = useState("");
  const [thesisDue, setThesisDue] = useState("");
  const [thesisFalsifiers, setThesisFalsifiers] = useState("");
  const [thesisKpis, setThesisKpis] = useState("");
  const [thesisBusy, setThesisBusy] = useState(false);
  const [reviewExitId, setReviewExitId] = useState("");
  const [verdict, setVerdict] = useState("mixed");
  const [realized, setRealized] = useState("");
  const [holdingDays, setHoldingDays] = useState("");
  const [lessons, setLessons] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);

  const canWrite = ["write"].includes(session.permissions.monitor || "none");

  const load = () => {
    setLoading(true);
    setError(null);
    instApi<MonitorData>("/monitor")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const createEvent = async () => {
    if (!companyId) {
      setError(t("请选择持仓标的", "Select a holding"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await instApi("/monitor/events", {
        method: "POST",
        body: { company_id: Number(companyId), type: "manual", severity, detail },
      });
      setDetail("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const createThesis = async () => {
    if (!thesisCompany || !thesisText.trim()) {
      setError(t("请选择标的并填写买入论点", "Select a symbol and enter a thesis"));
      return;
    }
    setThesisBusy(true);
    setError(null);
    try {
      const kpis = thesisKpis
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [name, target] = line.split(/[:：]/);
          const n = Number(target);
          return { name: name.trim(), target: Number.isFinite(n) ? n : undefined };
        });
      await instApi("/theses", {
        method: "POST",
        body: {
          company_id: Number(thesisCompany),
          thesis: thesisText,
          review_due: thesisDue || undefined,
          falsifiers: thesisFalsifiers
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean),
          kpis,
        },
      });
      setThesisText("");
      setThesisFalsifiers("");
      setThesisKpis("");
      setThesisDue("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setThesisBusy(false);
    }
  };

  const reviewThesisEntry = async (id: number, conclusion: "hold" | "reduce" | "invalidate") => {
    setError(null);
    try {
      const kpiStatus = conclusion === "hold" ? "on_track" : conclusion === "reduce" ? "at_risk" : "broken";
      await instApi(`/theses/${id}/review`, {
        method: "POST",
        body: { kpi_status: kpiStatus, conclusion, note: t("投后复核", "Post-investment review") },
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const submitExitReview = async () => {
    if (!reviewExitId) {
      setError(t("请选择退出案", "Select an exit case"));
      return;
    }
    setReviewBusy(true);
    setError(null);
    try {
      await instApi(`/monitor/exits/${reviewExitId}/review`, {
        method: "POST",
        body: {
          thesis_verdict: verdict,
          realized_return: realized ? Number(realized) / 100 : undefined,
          holding_days: holdingDays ? Number(holdingDays) : undefined,
          lessons,
        },
      });
      setLessons("");
      setRealized("");
      setHoldingDays("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReviewBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="MONITOR / 08" title={t("投后与退出", "Monitoring & exit")} />
        <Loading label={t("正在加载投后数据…", "Loading post-investment data…")} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="MONITOR / 08" title={t("投后与退出", "Monitoring & exit")} />
        <ErrorBox message={error} onRetry={load} />
      </div>
    );
  }

  const pf = data?.portfolio;
  const positions = pf?.positions || [];
  const events = data?.events || [];
  const exits = data?.exits || [];
  const openAlerts = events.filter((e) => e.status === "open").length;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="MONITOR / 08"
        title={t("投后与退出", "Monitoring & exit")}
        desc={t("跟踪持仓、集中度、经营预警与原始论点复核；退出必须重新走研究、辩论、审批与风控。", "Track positions, concentration, operating alerts and thesis reviews; exits must go through research, debate, approval and risk again.")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={openAlerts ? "amber" : "green"}>{openAlerts} {t("条待处理预警", "open alerts")}</Badge>
            <Link to="/inst/audit">
              <Button variant="ghost">{t("审计日志", "Audit log")}</Button>
            </Link>
          </div>
        }
      />

      {error ? <ErrorBox message={error} onRetry={load} /> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          [t("组合净值", "Portfolio NAV"), fmtMoney(pf?.nav)],
          [t("现金", "Cash"), fmtMoney(pf?.cash)],
          [t("仓位", "Exposure"), fmtPct(pf?.invested_ratio)],
          [t("持仓数", "Positions"), String(positions.length)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-[#dde5f2] bg-white p-5">
            <p className="text-xs text-[#68738b]">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-[#171923]">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <Card title={t("持仓与论点台账", "Holdings & thesis ledger")} desc={t("每笔持仓应有买入理由、关键假设、KPI、复核时间与推翻条件。", "Every holding needs a thesis, assumptions, KPIs, review date and falsifiers.")}>
            {positions.length ? (
              <div className="space-y-3">
                {positions.map((p) => (
                  <div key={p.id} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-[#171923]">{p.name || p.symbol}</p>
                        <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">{p.symbol}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge>{p.industry || t("行业待补充", "Industry n/a")}</Badge>
                        <Badge tone="gold">{fmtPct(p.weight)}</Badge>
                      </div>
                    </div>
                    <div className="mt-2 grid gap-x-6 sm:grid-cols-2">
                      <Field label={t("数量", "Qty")} value={fmtMoney(p.qty)} />
                      <Field label={t("市值", "Value")} value={fmtMoney(p.market_value)} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty>
                <ClipboardList className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
                {t("暂无持仓台账。执行成交后自动出现。", "No holdings yet; they appear after a fill.")}
              </Empty>
            )}
          </Card>

          <Card
            title={t("买入论点台账", "Investment thesis ledger")}
            desc={t("每笔持仓的买入理由、关键假设、KPI、复核时间与推翻条件；到期需复核。", "Buy thesis, key assumptions, KPIs, review date and falsifiers; due reviews must be completed.")}
          >
            <div className="mb-4 space-y-2 rounded-xl border border-[#e3eaf8] p-3">
              <select
                value={thesisCompany}
                onChange={(e) => setThesisCompany(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                <option value="">{t("选择持仓标的", "Select holding")}</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.company_id}>
                    {p.name || p.symbol}（{p.symbol}）
                  </option>
                ))}
              </select>
              <textarea
                value={thesisText}
                onChange={(e) => setThesisText(e.target.value)}
                placeholder={t("买入论点：为什么买、赚什么钱", "Thesis: why buy and where the return comes from")}
                className="min-h-[64px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
              />
              <input
                type="date"
                value={thesisDue}
                onChange={(e) => setThesisDue(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              />
              <textarea
                value={thesisFalsifiers}
                onChange={(e) => setThesisFalsifiers(e.target.value)}
                placeholder={t("推翻条件，每行一条", "Falsifiers, one per line")}
                className="min-h-[52px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
              />
              <textarea
                value={thesisKpis}
                onChange={(e) => setThesisKpis(e.target.value)}
                placeholder={t("KPI，每行一条，如：毛利率:0.45", "KPIs, one per line, e.g. gross_margin:0.45")}
                className="min-h-[52px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
              />
              <Button variant="gold" disabled={!canWrite || thesisBusy} onClick={createThesis}>
                {thesisBusy ? t("保存中…", "Saving…") : t("登记论点", "Add thesis")}
              </Button>
            </div>
            {data?.theses?.length ? (
              <ul className="space-y-2">
                {data?.theses?.map((ledger) => (
                  <li key={ledger.id} className="rounded-xl border border-[#e3eaf8] bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium text-[#252533]">
                        {ledger.company_name || ledger.symbol}
                      </span>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={ledger.status} />
                        {ledger.review_due ? <Badge tone="gold">{t("复核", "Review")} {ledger.review_due}</Badge> : null}
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-[#68738b]">{ledger.thesis}</p>
                    {ledger.falsifiers?.length ? (
                      <p className="mt-1 text-[11px] text-amber-700">{t("推翻条件", "Falsifiers")}：{ledger.falsifiers.join("；")}</p>
                    ) : null}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-[10px] text-[#77718c]">{t("复核", "Reviews")} {ledger.review_count || 0}</span>
                      {canWrite ? (
                        <>
                          <Button variant="ghost" onClick={() => void reviewThesisEntry(ledger.id, "hold")}>
                            {t("维持", "Hold")}
                          </Button>
                          <Button variant="ghost" onClick={() => void reviewThesisEntry(ledger.id, "reduce")}>
                            {t("减仓", "Reduce")}
                          </Button>
                          <Button variant="ghost" onClick={() => void reviewThesisEntry(ledger.id, "invalidate")}>
                            {t("论点失效", "Thesis broken")}
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("还没有论点台账。为每笔持仓补上买入理由与推翻条件。", "No theses yet. Add a thesis and falsifiers for each holding.")}</Empty>
            )}
          </Card>

          <Card title={t("监控事件", "Monitoring events")} desc={t("预警只陈述发生了什么与为什么，不自动卖出。", "Alerts state what happened and why; nothing is sold automatically.")}>
            {events.length ? (
              <ul className="space-y-2">
                {events.map((e) => (
                  <li key={e.id} className="rounded-xl border border-[#e3eaf8] bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge tone={e.severity === "critical" ? "red" : e.severity === "warning" ? "amber" : "slate"}>
                          {e.severity}
                        </Badge>
                        <span className="text-sm font-medium text-[#252533]">{e.company_name || e.symbol || e.type}</span>
                      </div>
                      <StatusBadge status={e.status} />
                    </div>
                    <p className="mt-1 text-xs text-[#68738b]">{e.detail?.text || "—"}</p>
                    <p className="mt-1 font-mono text-[10px] text-[#77718c]">{e.created_at}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <Activity className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
                {t("暂无监控事件。", "No monitoring events.")}
              </Empty>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title={t("记录预警", "Log alert")} desc={t("手动记录经营/估值/治理预警，进入待复核队列。", "Manually log operating, valuation or governance alerts for review.")}>
            <div className="space-y-2">
              <select
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                <option value="">{t("选择持仓标的", "Select holding")}</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.company_id}>
                    {p.name || p.symbol}（{p.symbol}）
                  </option>
                ))}
              </select>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                <option value="info">{t("提示", "Info")}</option>
                <option value="warning">{t("警告", "Warning")}</option>
                <option value="critical">{t("严重", "Critical")}</option>
              </select>
              <textarea
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                placeholder={t("发生了什么、为什么需要复核", "What happened and why it needs review")}
                className="min-h-[72px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
              />
              <Button variant="gold" disabled={!canWrite || busy} onClick={createEvent}>
                {busy ? t("提交中…", "Submitting…") : t("记录预警", "Log alert")}
              </Button>
            </div>
          </Card>

          <Card title={t("退出研究", "Exit research")} desc={t("退出议案必须重新走研究、辩论、审批与风控；不得复用旧批准。", "An exit must pass research, debate, approval and risk again; old approvals cannot be reused.")}>
            <div className="mb-4 space-y-2 rounded-xl border border-[#e3eaf8] p-3">
              <select
                value={exitCompany}
                onChange={(e) => setExitCompany(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                <option value="">{t("选择持仓标的", "Select holding")}</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.company_id}>
                    {p.name || p.symbol}（{p.symbol}）
                  </option>
                ))}
              </select>
              <select
                value={exitReason}
                onChange={(e) => setExitReason(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                {Object.entries(REASON).map(([k, v]) => (
                  <option key={k} value={k}>
                    {locale === "en" ? v[1] : v[0]}
                  </option>
                ))}
              </select>
              <textarea
                value={exitMemo}
                onChange={(e) => setExitMemo(e.target.value)}
                placeholder={t("退出理由：比较继续持有 / 部分减持 / 全部退出", "Rationale: hold vs reduce vs full exit")}
                className="min-h-[64px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
              />
              <Button
                variant="danger"
                disabled={!canWrite || exitBusy || !exitCompany}
                onClick={async () => {
                  setExitBusy(true);
                  setError(null);
                  try {
                    const res = await instApi<{ case_id?: number }>("/monitor/exits", {
                      method: "POST",
                      body: { company_id: Number(exitCompany), reason_type: exitReason, memo: exitMemo },
                    });
                    setExitMemo("");
                    if (res.case_id) {
                      nav(`/inst/research?case=${res.case_id}`);
                      return;
                    }
                    load();
                  } catch (e) {
                    setError(e instanceof Error ? e.message : String(e));
                  } finally {
                    setExitBusy(false);
                  }
                }}
              >
                {exitBusy ? t("提交中…", "Submitting…") : t("发起退出研究", "Start exit research")}
              </Button>
              <p className="text-[10px] leading-relaxed text-[#77718c]">
                {t("发起退出研究会撤销该标的仍有效的旧授权，并新建退出研究案；后续重新走研究、辩论、审批与风控。", "Starting exit research revokes still-valid authorizations for the symbol and opens a new exit case; it then follows research, debate, approval and risk again.")}
              </p>
            </div>
            {exits.length ? (
              <ul className="space-y-2">
                {exits.map((x) => (
                  <li key={x.id} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-[#252533]">{x.company_name}</span>
                      <StatusBadge status={x.status} />
                    </div>
                    <p className="mt-1 text-xs text-[#68738b]">
                      {REASON[x.reason_type] ? (locale === "en" ? REASON[x.reason_type][1] : REASON[x.reason_type][0]) : x.reason_type}
                      {" · "}EX-{x.id}
                      {x.case_no ? ` · ${x.case_no}` : ""}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                      {x.case_id ? (
                        <Link
                          to={`/inst/research?case=${x.case_id}`}
                          className="rounded-md border border-[#dde5f2] px-2 py-1 text-[#7950ba] transition hover:border-[#7950ba]"
                        >
                          {t("退出研究案", "Exit research")} #{x.case_id}
                        </Link>
                      ) : null}
                      {x.proposal_id ? (
                        <Link
                          to={`/inst/approvals?proposal=${x.proposal_id}`}
                          className="rounded-md border border-[#dde5f2] px-2 py-1 text-[#7950ba] transition hover:border-[#7950ba]"
                        >
                          {t("退出议案", "Exit proposal")} #{x.proposal_id}
                        </Link>
                      ) : (
                        <span className="text-[#77718c]">{t("尚未创建议案", "No proposal yet")}</span>
                      )}
                      {x.proposal_status ? <StatusBadge status={x.proposal_status} /> : null}
                      {x.authorization_status ? <StatusBadge status={x.authorization_status} /> : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
                {t("暂无退出研究。退出原因分为论点失效、估值透支、更优配置与组合约束。", "No exit cases. Reasons: thesis broken, valuation stretched, better allocation, portfolio constraint.")}
              </Empty>
            )}
          </Card>

          <Card title={t("退出复盘", "Exit post-mortem")} desc={t("记录已实现收益、持有天数、论点对错与教训，供下次研究复用。", "Record realized return, holding days, thesis verdict and lessons for future research.")}>
            <div className="mb-4 space-y-2 rounded-xl border border-[#e3eaf8] p-3">
              <select
                value={reviewExitId}
                onChange={(e) => setReviewExitId(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                <option value="">{t("选择退出案", "Select exit case")}</option>
                {exits.map((x) => (
                  <option key={x.id} value={x.id}>
                    EX-{x.id} {x.company_name}
                  </option>
                ))}
              </select>
              <select
                value={verdict}
                onChange={(e) => setVerdict(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
              >
                <option value="right">{t("论点正确", "Thesis right")}</option>
                <option value="mixed">{t("对错参半", "Mixed")}</option>
                <option value="wrong">{t("论点错误", "Thesis wrong")}</option>
              </select>
              <div className="flex gap-2">
                <input
                  value={realized}
                  onChange={(e) => setRealized(e.target.value)}
                  placeholder={t("已实现收益 %", "Realized return %")}
                  className="w-1/2 rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
                />
                <input
                  value={holdingDays}
                  onChange={(e) => setHoldingDays(e.target.value)}
                  placeholder={t("持有天数", "Holding days")}
                  className="w-1/2 rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs"
                />
              </div>
              <textarea
                value={lessons}
                onChange={(e) => setLessons(e.target.value)}
                placeholder={t("复盘教训：哪些假设错了、下次怎么验证", "Lessons: which assumption failed and how to verify next time")}
                className="min-h-[64px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
              />
              <Button variant="gold" disabled={!canWrite || reviewBusy} onClick={submitExitReview}>
                {reviewBusy ? t("保存中…", "Saving…") : t("保存复盘", "Save post-mortem")}
              </Button>
            </div>
            {data?.exit_reviews?.length ? (
              <ul className="space-y-2">
                {data?.exit_reviews?.map((r) => (
                  <li key={r.id} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[#505369]">EX-{r.exit_case_id}</span>
                      <Badge tone={r.thesis_verdict === "right" ? "green" : r.thesis_verdict === "wrong" ? "red" : "amber"}>
                        {r.thesis_verdict}
                      </Badge>
                    </div>
                    <p className="mt-1 text-[#68738b]">
                      {t("收益", "Return")} {r.realized_return != null ? fmtPct(r.realized_return) : "—"} · {t("持有", "Held")}{" "}
                      {r.holding_days ?? "—"} {t("天", "days")}
                    </p>
                    {r.lessons ? <p className="mt-1 text-[#68738b]">{r.lessons}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("还没有退出复盘记录。", "No exit post-mortems yet.")}</Empty>
            )}
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t("投后预警与退出建议不构成卖出指令；Agent 不得临时扩权。演示数据不得进入真实审批。", "Post-investment alerts and exit notes are not sell instructions; agents cannot escalate privileges. Demo data must not enter real approvals.")}
      </p>
    </div>
  );
}
