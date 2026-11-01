import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, ClipboardList } from "lucide-react";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
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

const REASON: Record<string, string> = {
  thesis_invalid: "论点失效",
  valuation: "估值透支",
  better_allocation: "更优资本配置",
  portfolio_constraint: "组合/资金约束",
  other: "其他",
};

export function InstMonitorPage() {
  const session = useInstSession();
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
      setError("请选择持仓标的");
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
      setError("请选择标的并填写买入论点");
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
        body: { kpi_status: kpiStatus, conclusion, note: "投后复核" },
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const submitExitReview = async () => {
    if (!reviewExitId) {
      setError("请选择退出案");
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
        <PageHeader eyebrow="MONITOR / 08" title="投后与退出" />
        <Loading label="正在加载投后数据…" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="MONITOR / 08" title="投后与退出" />
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
        title="投后与退出"
        desc="跟踪持仓、集中度、经营预警与原始论点复核；退出必须重新走研究、辩论、审批与风控。"
        actions={<Badge tone={openAlerts ? "amber" : "green"}>{openAlerts} 条待处理预警</Badge>}
      />

      {error ? <ErrorBox message={error} onRetry={load} /> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["组合净值", fmtMoney(pf?.nav)],
          ["现金", fmtMoney(pf?.cash)],
          ["仓位", fmtPct(pf?.invested_ratio)],
          ["持仓数", `${positions.length}`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-[#e7e3d8] bg-white p-5">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-2 font-mono text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <Card title="持仓与论点台账" desc="每笔持仓应有买入理由、关键假设、KPI、复核时间与推翻条件。">
            {positions.length ? (
              <div className="space-y-3">
                {positions.map((p) => (
                  <div key={p.id} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{p.name || p.symbol}</p>
                        <p className="mt-0.5 font-mono text-[11px] text-slate-500">{p.symbol}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge>{p.industry || "行业待补充"}</Badge>
                        <Badge tone="gold">{fmtPct(p.weight)}</Badge>
                      </div>
                    </div>
                    <div className="mt-2 grid gap-x-6 sm:grid-cols-2">
                      <Field label="数量" value={fmtMoney(p.qty)} />
                      <Field label="市值" value={fmtMoney(p.market_value)} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty>
                <ClipboardList className="mx-auto mb-2 h-6 w-6 text-slate-300" />
                暂无持仓台账。执行成交后自动出现。
              </Empty>
            )}
          </Card>

          <Card
            title="买入论点台账"
            desc="每笔持仓的买入理由、关键假设、KPI、复核时间与推翻条件；到期需复核。"
          >
            <div className="mb-4 space-y-2 rounded-xl border border-[#f0ece2] p-3">
              <select
                value={thesisCompany}
                onChange={(e) => setThesisCompany(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                <option value="">选择持仓标的</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.company_id}>
                    {p.name || p.symbol}（{p.symbol}）
                  </option>
                ))}
              </select>
              <textarea
                value={thesisText}
                onChange={(e) => setThesisText(e.target.value)}
                placeholder="买入论点：为什么买、赚什么钱"
                className="min-h-[64px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
              />
              <input
                type="date"
                value={thesisDue}
                onChange={(e) => setThesisDue(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              />
              <textarea
                value={thesisFalsifiers}
                onChange={(e) => setThesisFalsifiers(e.target.value)}
                placeholder="推翻条件，每行一条"
                className="min-h-[52px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
              />
              <textarea
                value={thesisKpis}
                onChange={(e) => setThesisKpis(e.target.value)}
                placeholder="KPI，每行一条，如：毛利率:0.45"
                className="min-h-[52px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
              />
              <Button variant="gold" disabled={!canWrite || thesisBusy} onClick={createThesis}>
                {thesisBusy ? "保存中…" : "登记论点"}
              </Button>
            </div>
            {data?.theses?.length ? (
              <ul className="space-y-2">
                {data?.theses?.map((t) => (
                  <li key={t.id} className="rounded-xl border border-[#f0ece2] bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium text-slate-800">
                        {t.company_name || t.symbol}
                      </span>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={t.status} />
                        {t.review_due ? <Badge tone="gold">复核 {t.review_due}</Badge> : null}
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-slate-600">{t.thesis}</p>
                    {t.falsifiers?.length ? (
                      <p className="mt-1 text-[11px] text-amber-700">推翻条件：{t.falsifiers.join("；")}</p>
                    ) : null}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-[10px] text-slate-400">复核 {t.review_count || 0} 次</span>
                      {canWrite ? (
                        <>
                          <Button variant="ghost" onClick={() => void reviewThesisEntry(t.id, "hold")}>
                            维持
                          </Button>
                          <Button variant="ghost" onClick={() => void reviewThesisEntry(t.id, "reduce")}>
                            减仓
                          </Button>
                          <Button variant="ghost" onClick={() => void reviewThesisEntry(t.id, "invalidate")}>
                            论点失效
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>还没有论点台账。为每笔持仓补上买入理由与推翻条件。</Empty>
            )}
          </Card>

          <Card title="监控事件" desc="预警只陈述发生了什么与为什么，不自动卖出。">
            {events.length ? (
              <ul className="space-y-2">
                {events.map((e) => (
                  <li key={e.id} className="rounded-xl border border-[#f0ece2] bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge tone={e.severity === "critical" ? "red" : e.severity === "warning" ? "amber" : "slate"}>
                          {e.severity}
                        </Badge>
                        <span className="text-sm font-medium text-slate-800">{e.company_name || e.symbol || e.type}</span>
                      </div>
                      <StatusBadge status={e.status} />
                    </div>
                    <p className="mt-1 text-xs text-slate-600">{e.detail?.text || "—"}</p>
                    <p className="mt-1 font-mono text-[10px] text-slate-400">{e.created_at}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <Activity className="mx-auto mb-2 h-6 w-6 text-slate-300" />
                暂无监控事件。
              </Empty>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="记录预警" desc="手动记录经营/估值/治理预警，进入待复核队列。">
            <div className="space-y-2">
              <select
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                <option value="">选择持仓标的</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.company_id}>
                    {p.name || p.symbol}（{p.symbol}）
                  </option>
                ))}
              </select>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                <option value="info">提示</option>
                <option value="warning">警告</option>
                <option value="critical">严重</option>
              </select>
              <textarea
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                placeholder="发生了什么、为什么需要复核"
                className="min-h-[72px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
              />
              <Button variant="gold" disabled={!canWrite || busy} onClick={createEvent}>
                {busy ? "提交中…" : "记录预警"}
              </Button>
            </div>
          </Card>

          <Card title="退出研究" desc="退出议案必须重新走研究、辩论、审批与风控；不得复用旧批准。">
            <div className="mb-4 space-y-2 rounded-xl border border-[#f0ece2] p-3">
              <select
                value={exitCompany}
                onChange={(e) => setExitCompany(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                <option value="">选择持仓标的</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.company_id}>
                    {p.name || p.symbol}（{p.symbol}）
                  </option>
                ))}
              </select>
              <select
                value={exitReason}
                onChange={(e) => setExitReason(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                {Object.entries(REASON).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
              <textarea
                value={exitMemo}
                onChange={(e) => setExitMemo(e.target.value)}
                placeholder="退出理由：比较继续持有 / 部分减持 / 全部退出"
                className="min-h-[64px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
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
                {exitBusy ? "提交中…" : "发起退出研究"}
              </Button>
              <p className="text-[10px] leading-relaxed text-slate-400">
                发起退出研究会撤销该标的仍有效的旧授权，并新建退出研究案；后续重新走研究、辩论、审批与风控。
              </p>
            </div>
            {exits.length ? (
              <ul className="space-y-2">
                {exits.map((x) => (
                  <li key={x.id} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-slate-800">{x.company_name}</span>
                      <StatusBadge status={x.status} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{REASON[x.reason_type] || x.reason_type}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-slate-300" />
                暂无退出研究。退出原因分为论点失效、估值透支、更优配置与组合约束。
              </Empty>
            )}
          </Card>

          <Card title="退出复盘" desc="记录已实现收益、持有天数、论点对错与教训，供下次研究复用。">
            <div className="mb-4 space-y-2 rounded-xl border border-[#f0ece2] p-3">
              <select
                value={reviewExitId}
                onChange={(e) => setReviewExitId(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                <option value="">选择退出案</option>
                {exits.map((x) => (
                  <option key={x.id} value={x.id}>
                    EX-{x.id} {x.company_name}
                  </option>
                ))}
              </select>
              <select
                value={verdict}
                onChange={(e) => setVerdict(e.target.value)}
                className="w-full rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
              >
                <option value="right">论点正确</option>
                <option value="mixed">对错参半</option>
                <option value="wrong">论点错误</option>
              </select>
              <div className="flex gap-2">
                <input
                  value={realized}
                  onChange={(e) => setRealized(e.target.value)}
                  placeholder="已实现收益 %"
                  className="w-1/2 rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
                />
                <input
                  value={holdingDays}
                  onChange={(e) => setHoldingDays(e.target.value)}
                  placeholder="持有天数"
                  className="w-1/2 rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs"
                />
              </div>
              <textarea
                value={lessons}
                onChange={(e) => setLessons(e.target.value)}
                placeholder="复盘教训：哪些假设错了、下次怎么验证"
                className="min-h-[64px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
              />
              <Button variant="gold" disabled={!canWrite || reviewBusy} onClick={submitExitReview}>
                {reviewBusy ? "保存中…" : "保存复盘"}
              </Button>
            </div>
            {data?.exit_reviews?.length ? (
              <ul className="space-y-2">
                {data?.exit_reviews?.map((r) => (
                  <li key={r.id} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-slate-700">EX-{r.exit_case_id}</span>
                      <Badge tone={r.thesis_verdict === "right" ? "green" : r.thesis_verdict === "wrong" ? "red" : "amber"}>
                        {r.thesis_verdict}
                      </Badge>
                    </div>
                    <p className="mt-1 text-slate-500">
                      收益 {r.realized_return != null ? fmtPct(r.realized_return) : "—"} · 持有{" "}
                      {r.holding_days ?? "—"} 天
                    </p>
                    {r.lessons ? <p className="mt-1 text-slate-600">{r.lessons}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>还没有退出复盘记录。</Empty>
            )}
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-slate-400">
        投后预警与退出建议不构成卖出指令；Agent 不得临时扩权。演示数据不得进入真实审批。
      </p>
    </div>
  );
}
