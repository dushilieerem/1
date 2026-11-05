import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Activity, AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { instApi, fmtDateTime, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge, industryLabel } from "./instUi";
import { InstKlineCard } from "./InstKlineCard";

type Position = {
  id: number;
  company_id?: number;
  symbol: string;
  name?: string;
  industry?: string;
  market?: string;
  qty: number;
  cost?: number;
  market_value: number;
  weight: number;
  as_of?: string;
};

type Thesis = {
  id: number;
  company_id?: number;
  company_name?: string;
  symbol: string;
  thesis: string;
  key_assumptions?: string[];
  kpis?: Array<{ name: string; target?: number }>;
  falsifiers?: string[];
  review_due?: string;
  status: string;
  review_count?: number;
  updated_at?: string;
};

type Event = {
  id: number;
  company_id?: number;
  symbol?: string;
  type: string;
  severity: string;
  status: string;
  detail?: { text?: string };
  created_at: string;
};

type ExitCase = {
  id: number;
  company_id?: number;
  symbol: string;
  reason_type: string;
  status: string;
  case_id?: number;
  proposal_id?: number;
  proposal_status?: string;
};

type MonitorData = {
  events: Event[];
  exits: ExitCase[];
  theses: Thesis[];
};

type PortfolioData = {
  positions: Position[];
};

const REASON: Record<string, [string, string]> = {
  thesis_invalid: ["论点失效", "Thesis broken"],
  valuation: ["估值透支", "Valuation stretched"],
  better_allocation: ["更优资本配置", "Better allocation"],
  portfolio_constraint: ["组合/资金约束", "Portfolio constraint"],
  other: ["其他", "Other"],
};

const EVENT_TYPE: Record<string, [string, string]> = {
  manual: ["投资经理记录", "Manager note"],
  price: ["价格异动", "Price move"],
  valuation: ["估值变化", "Valuation"],
  governance: ["治理事件", "Governance"],
  thesis: ["论点复核", "Thesis review"],
};

const THESIS_STATUS: Record<string, [string, string]> = {
  active: ["正常", "Active"],
  reviewed: ["已复核", "Reviewed"],
  invalidated: ["已失效", "Invalidated"],
  closed: ["已关闭", "Closed"],
};

export function InstHoldingPage() {
  const { symbol: rawSymbol = "" } = useParams();
  const symbol = decodeURIComponent(rawSymbol);
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const nav = useNavigate();
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [monitor, setMonitor] = useState<MonitorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opinion, setOpinion] = useState("");
  const [reason, setReason] = useState("thesis_invalid");

  const canWrite = ["write"].includes(session.permissions.monitor || "none");
  const canExit = ["manager", "partner", "monitoring"].includes(session.role);

  const load = async (scan: boolean) => {
    setLoading(true);
    setError(null);
    try {
      if (scan && canWrite) {
        await instApi("/monitor/scan", { method: "POST" }).catch(() => null);
      }
      const [p, m] = await Promise.all([
        instApi<PortfolioData>("/portfolio"),
        instApi<MonitorData>("/monitor"),
      ]);
      setPortfolio(p);
      setMonitor(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // 进入页面只读；自动扫描会写事件，必须由有写权限的用户显式点「重新扫描」。
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  const position = useMemo(
    () => (portfolio?.positions || []).find((p) => p.symbol === symbol),
    [portfolio, symbol],
  );
  const companyId = Number(position?.company_id || 0);
  const theses = useMemo(
    () =>
      (monitor?.theses || [])
        .filter((x) => (companyId ? x.company_id === companyId : x.symbol === symbol))
        .sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))),
    [monitor, companyId, symbol],
  );
  const thesis = theses[0];
  const events = useMemo(
    () =>
      (monitor?.events || []).filter((x) =>
        companyId ? x.company_id === companyId : x.symbol === symbol,
      ),
    [monitor, companyId, symbol],
  );
  const exits = useMemo(
    () => (monitor?.exits || []).filter((x) => x.symbol === symbol),
    [monitor, symbol],
  );
  const openCritical = events.some((e) => e.status === "open" && e.severity === "critical");
  const thesisState = !thesis
    ? t("未建台账", "No ledger")
    : thesis.status === "invalidated" || openCritical
      ? t("已失效", "Invalidated")
      : events.some((e) => e.status === "open" && e.severity === "warning")
        ? t("有风险", "At risk")
        : t("正常", "Normal");

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
      await load(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const refreshThesis = () => {
    if (!companyId) return;
    void act("thesis", () =>
      instApi("/monitor/theses/refresh", { method: "POST", body: { company_id: companyId } }),
    );
  };

  const recordOpinion = () => {
    if (!companyId) return;
    const text = opinion.trim();
    if (!text) {
      setError(t("请先写下意见，再记录或提交。", "Write your opinion first."));
      return;
    }
    const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
    void act("event", () =>
      instApi("/monitor/events", {
        method: "POST",
        body: {
          company_id: companyId,
          type: "manual",
          severity: "warning",
          detail: `[${stamp}] ${text}`,
        },
      }),
    );
  };

  const submitExit = () => {
    if (!companyId) return;
    const text = opinion.trim();
    if (!text) {
      setError(t("退出审理必须写明时间点、发生了什么、为什么值得复核。", "Explain what happened and why it needs review."));
      return;
    }
    void act("exit", async () => {
      const res = await instApi<{ case_id: number }>("/monitor/exits", {
        method: "POST",
        body: { company_id: companyId, reason_type: reason, memo: text },
      });
      nav(`/inst/research?case=${res.case_id}`);
    });
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="PORTFOLIO / 05" title={t("盘中管理", "Intraday management")} />
        <Loading label={t("正在加载持仓与监控…", "Loading holding and monitoring…")} />
      </div>
    );
  }

  if (error && !position) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="PORTFOLIO / 05" title={t("盘中管理", "Intraday management")} />
        <ErrorBox message={error} onRetry={() => void load(true)} />
      </div>
    );
  }

  if (!position) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="PORTFOLIO / 05" title={t("盘中管理", "Intraday management")} />
        <Empty>
          {t("该标的不在持仓中，无法进入盘中管理。", "This symbol is not held; intraday management is unavailable.")}
        </Empty>
        <Link to="/inst/portfolio" className="text-sm text-[#7950ba] hover:underline">
          ← {t("返回投资管理", "Back to investment management")}
        </Link>
      </div>
    );
  }

  const exitOpen = exits.find((x) => !["closed", "rejected"].includes(x.status));

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="PORTFOLIO / 05 · INTRADAY"
        title={`${position.name || symbol} · ${t("盘中管理", "Intraday management")}`}
        desc={t(
          "页面已锁定这一只持仓：看事件 → 核论点 → 写意见 → 上投委会。卖出理由只认论点失效、估值透支、更优配置、组合约束。",
          "This page is locked to one holding: events → thesis → opinion → IC. Valid sell reasons are thesis broken, valuation stretched, better allocation, or portfolio constraint.",
        )}
        actions={
          <Link to="/inst/portfolio" className="inline-flex items-center gap-1 text-xs text-[#7950ba] hover:underline">
            <ArrowLeft className="h-3.5 w-3.5" />
            {t("返回投资管理", "Back")}
          </Link>
        }
      />

      {error ? <ErrorBox message={error} onRetry={() => void load(false)} /> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Field label={t("标的", "Symbol")} value={`${position.name || symbol} · ${symbol}`} />
        <Field label={t("行业", "Industry")} value={position.industry ? industryLabel(position.industry, locale) : t("待补充", "TBD")} />
        <Field label={t("数量 / 成本", "Qty / cost")} value={`${fmtMoney(position.qty)} / ${position.cost == null ? t("待补充", "TBD") : fmtMoney(position.cost, 2)}`} />
        <Field
          label={t("市值 / 权重", "Value / weight")}
          value={`${fmtMoney(position.market_value)} / ${fmtPct(position.weight)}`}
        />
      </div>

      <InstKlineCard companyId={companyId} symbol={symbol} />

      <Card
        title={t("买入论点台账", "Buy thesis ledger")}
        desc={t(
          "保留上一次结论，不自动覆盖；情况真的变了才重新生成。台账来自最近一笔买入议案与研究版本。",
          "Keeps the last conclusion unless you regenerate it; built from the latest buy proposal and research version.",
        )}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={thesis?.status === "invalidated" ? "red" : thesisState === t("有风险", "At risk") ? "amber" : "green"}>
              {thesisState}
            </Badge>
            {canWrite ? (
              <Button variant="ghost" disabled={!!busy} onClick={refreshThesis}>
                <RefreshCw className={`mr-1 h-3.5 w-3.5 ${busy === "thesis" ? "animate-spin" : ""}`} />
                {busy === "thesis" ? t("生成中…", "Generating…") : t("重新生成台账", "Regenerate")}
              </Button>
            ) : null}
          </div>
        }
      >
        {thesis ? (
          <div className="space-y-3 text-xs text-[#505369]">
            <p className="whitespace-pre-wrap leading-relaxed">{thesis.thesis}</p>
            {thesis.key_assumptions?.length ? (
              <div>
                <p className="font-medium text-[#252533]">{t("关键假设", "Key assumptions")}</p>
                <ul className="mt-1 list-disc pl-4">
                  {thesis.key_assumptions.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {thesis.falsifiers?.length ? (
              <div>
                <p className="font-medium text-[#252533]">{t("推翻条件", "Falsifiers")}</p>
                <ul className="mt-1 list-disc pl-4">
                  {thesis.falsifiers.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-[#77718c]">
              <span>
                {t("复核时间", "Review due")}：{thesis.review_due || t("未设置", "Not set")}
              </span>
              <span>
                {t("历史版本", "Versions")}：{theses.length}
              </span>
              {thesis.updated_at ? (
                <span>
                  {t("更新时间", "Updated")}：{fmtDateTime(thesis.updated_at)}
                </span>
              ) : null}
            </div>
          </div>
        ) : (
          <Empty>{t("还没有买入论点台账；可点「重新生成台账」从买入议案生成。", "No thesis ledger yet; regenerate from the buy proposal.")}</Empty>
        )}
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Card
          title={t("监控事件与论点核对", "Monitoring events & thesis check")}
          desc={t(
            "系统按复核到期与价格异常自动登记事件；也可手动记录。状态：正常 / 有风险 / 已失效。",
            "Events are auto-recorded for overdue reviews and price anomalies; manual notes are also kept.",
          )}
          actions={
            canWrite ? (
              <Button variant="ghost" disabled={!!busy} onClick={() => void load(true)}>
                <Activity className="mr-1 h-3.5 w-3.5" />
                {t("重新扫描", "Rescan")}
              </Button>
            ) : null
          }
        >
          {events.length ? (
            <ul className="space-y-2 text-xs">
              {events.slice(0, 12).map((e) => (
                <li key={e.id} className="rounded-lg border border-[#e3eaf8] px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-[#505369]">
                      {(locale === "en" ? EVENT_TYPE[e.type]?.[1] : EVENT_TYPE[e.type]?.[0]) || e.type}
                    </span>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={e.severity} />
                      <StatusBadge status={e.status} />
                    </div>
                  </div>
                  {e.detail?.text ? <p className="mt-1 leading-relaxed text-[#68738b]">{e.detail.text}</p> : null}
                  <p className="mt-1 text-[10px] text-[#a9a4bd]">{fmtDateTime(e.created_at)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>{t("暂无监控事件。", "No monitoring events yet.")}</Empty>
          )}
          {openCritical ? (
            <p className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-[11px] text-red-700">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {t("存在未关闭的严重事件，论点需优先复核。", "An open critical event requires immediate thesis review.")}
            </p>
          ) : null}
        </Card>

        <Card
          title={t("投资经理意见", "Manager opinion")}
          desc={t(
            "记录时间点 + 一句意见；提交退出审理后进入投委会（合伙人 → 风控 → Chairman）。",
            "Record the time and one clear opinion; exit review goes through the IC (partner → risk → chairman).",
          )}
        >
          <div className="space-y-3">
            <textarea
              value={opinion}
              onChange={(e) => setOpinion(e.target.value)}
              placeholder={t(
                "哪天、发生了什么、为什么值得复核；这次是否预警、理由是什么。",
                "When, what happened, and why it matters; whether you are warning this time and why.",
              )}
              className="min-h-[96px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
            />
            <label className="block space-y-1 text-[11px] text-[#68738b]">
              {t("退出理由", "Exit reason")}
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-lg border border-[#dde5f2] bg-white px-2 py-1.5 text-xs text-[#252533] outline-none"
              >
                {Object.entries(REASON).map(([key, [zh, en]]) => (
                  <option key={key} value={key}>
                    {locale === "en" ? en : zh}
                  </option>
                ))}
              </select>
            </label>
            {canWrite ? (
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" disabled={!!busy} onClick={recordOpinion}>
                  {busy === "event" ? t("记录中…", "Saving…") : t("记录意见并继续持有", "Record & keep holding")}
                </Button>
                {canExit ? (
                  <Button variant="danger" disabled={!!busy || Boolean(exitOpen)} onClick={submitExit}>
                    {busy === "exit"
                      ? t("提交中…", "Submitting…")
                      : exitOpen
                        ? t("已有在途退出审理", "Exit review in progress")
                        : t("提交减仓 / 清仓审理", "Submit trim / exit review")}
                  </Button>
                ) : null}
              </div>
            ) : (
              <p className="text-[11px] text-[#77718c]">{t("当前角色只读。", "Read-only for this role.")}</p>
            )}
            {exitOpen ? (
              <p className="text-[11px] text-amber-700">
                {t("已有退出审理在途：", "Exit review in progress: ")}
                {exitOpen.case_id ? (
                  <Link className="underline" to={`/inst/research?case=${exitOpen.case_id}`}>
                    {t("查看研究案", "Open research case")} #{exitOpen.case_id}
                  </Link>
                ) : (
                  `#${exitOpen.id}`
                )}
                {exitOpen.proposal_id ? (
                  <>
                    {" · "}
                    <Link className="underline" to={`/inst/approvals?proposal=${exitOpen.proposal_id}`}>
                      {t("查看议案", "Open proposal")} #{exitOpen.proposal_id}
                    </Link>
                  </>
                ) : null}
              </p>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
