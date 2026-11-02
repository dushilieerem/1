import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Download, FileSearch, Loader2, Lock, Sparkles } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { getInstToken } from "@/lib/instAuth";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "./instUi";

type Dim = {
  key: string;
  title: string;
  question?: string;
  status?: string;
  summary?: string;
  checks?: string[];
  counter?: string[];
  evidence_ids?: number[];
  open_questions?: string[];
  data_gaps?: string[];
  confidence?: number;
  engine?: string;
  agent?: string;
  agent_error?: string;
};

type Version = {
  id: number;
  version_no: number;
  status: string;
  conclusion?: string;
  six_dim?: Dim[];
  valuation?: Record<string, unknown> | null;
  assumptions?: unknown;
  counter_evidence?: string[];
  open_questions?: string[];
  evidence_ids?: number[];
};

type CaseItem = {
  id: number;
  company_id?: number;
  case_no: string;
  stage: string;
  symbol: string;
  company_name: string;
  market: string;
  industry?: string;
  data_status?: string;
  ref_price?: number;
  versions?: Version[];
  evidence?: Array<{ id: number; title: string; quote?: string; source: string; as_of?: string }>;
  tasks?: Array<{
    id: number;
    task_key?: string;
    title: string;
    status: string;
    progress: number;
    result?: { summary?: string; engine?: string; agent_error?: string };
  }>;
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
};

const AGENT_TITLES: Array<[string, string]> = [
  ["industry", "商业与产业"],
  ["business_model", "公司商业模式"],
  ["moat", "护城河"],
  ["financial", "财务质量"],
  ["governance", "CEO 与治理"],
  ["valuation", "估值与价格"],
];

export function InstResearchPage() {
  const session = useInstSession();
  const { t } = useInstLocale();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const caseId = Number(params.get("case") || 0);
  const [items, setItems] = useState<CaseItem[]>([]);
  const [detail, setDetail] = useState<CaseItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [memo, setMemo] = useState<Record<string, any> | null>(null);
  const autoRan = useRef(false);
  const memoRan = useRef(false);
  const [dcf, setDcf] = useState<Record<string, any> | null>(null);
  const [dcfIn, setDcfIn] = useState({
    base_revenue: "100",
    revenue_growth: "10",
    cashflow_margin: "30",
    discount_rate: "10",
    terminal_growth: "2",
    shares: "",
  });
  const runDcf = () => {
    if (!detail?.company_id) return;
    setBusy("dcf");
    setError(null);
    instApi<Record<string, any>>(`/companies/${detail.company_id}/dcf`, {
      method: "POST",
      body: {
        base_revenue: Number(dcfIn.base_revenue),
        revenue_growth: Number(dcfIn.revenue_growth) / 100,
        cashflow_margin: Number(dcfIn.cashflow_margin) / 100,
        discount_rate: Number(dcfIn.discount_rate) / 100,
        terminal_growth: Number(dcfIn.terminal_growth) / 100,
        shares_outstanding: dcfIn.shares ? Number(dcfIn.shares) : undefined,
        years: 5,
      },
    })
      .then(setDcf)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(null));
  };

  const canWrite = (session.permissions.research || "none") === "write";

  const exportReport = async () => {
    setBusy("export");
    setError(null);
    try {
      const token = getInstToken();
      const res = await fetch(`/api/inst/cases/${caseId}/report`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        let message = `${t("导出失败", "Export failed")}（${res.status}）`;
        try {
          const data = await res.json();
          message = String((data as { detail?: string } | null)?.detail || message);
        } catch {
          /* 非 JSON 错误体，保留默认提示 */
        }
        throw new Error(message);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${detail?.symbol || "research"}-${t("研究简报", "research-report")}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const loadList = () => {
    setLoading(true);
    setError(null);
    instApi<{ items: CaseItem[] }>("/cases")
      .then((data) => setItems(data.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const loadDetail = (id: number) => {
    setLoading(true);
    setError(null);
    instApi<CaseItem>(`/cases/${id}`)
      .then(setDetail)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (caseId) loadDetail(caseId);
    else {
      setDetail(null);
      loadList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const version = useMemo<Version | null>(() => {
    const list = detail?.versions || [];
    return list.length ? list[0] : null;
  }, [detail]);

  const evidenceMap = useMemo(() => {
    const map = new Map<number, { title: string; quote?: string; source: string; as_of?: string }>();
    for (const ev of detail?.evidence || []) map.set(ev.id, ev);
    return map;
  }, [detail]);

  const loadMemo = async () => {
    const res = await instApi<{ memo: Record<string, any> }>(`/cases/${caseId}/ai/memo`, { method: "POST" });
    setMemo(res.memo);
  };

  const autopilot = async () => {
    setBusy("auto");
    setError(null);
    try {
      await instApi(`/cases/${caseId}/research`, { method: "POST", body: { mode: "full" } });
      const next = await instApi<CaseItem>(`/cases/${caseId}`);
      setDetail(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!caseId || !detail || !canWrite || version || autoRan.current) return;
    autoRan.current = true;
    void autopilot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, detail, version, canWrite]);

  useEffect(() => {
    if (!caseId || !detail || !version || memo || memoRan.current || !canWrite) return;
    memoRan.current = true;
    void loadMemo().catch(() => {
      /* 自动摘要失败时保留手动按钮 */
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, detail, version, memo, canWrite]);

  useEffect(() => {
    if (busy !== "auto" || !caseId) return;
    let alive = true;
    const timer = window.setInterval(() => {
      instApi<CaseItem>(`/cases/${caseId}`)
        .then((next) => {
          if (alive) setDetail(next);
        })
        .catch(() => {
          /* 轮询失败不打断主请求 */
        });
    }, 2000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [busy, caseId]);

  const taskByKey = useMemo(() => {
    const map = new Map<string, NonNullable<CaseItem["tasks"]>[number]>();
    for (const t of detail?.tasks || []) {
      if (t.task_key) map.set(t.task_key, t);
    }
    return map;
  }, [detail]);
  const hasLiveTasks = (detail?.tasks || []).some((t) => t.status === "pending" || t.status === "running");

  const approveAndDebate = async () => {
    if (!version) return;
    setBusy("approve");
    setError(null);
    try {
      await instApi(`/research/${version.id}/review`, {
        method: "POST",
        body: { decision: "approve", comment },
      });
      nav(`/inst/debate?case=${caseId}&autostart=1`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
      if (caseId) loadDetail(caseId);
      else loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="RESEARCH / 03" title={t("公司研究", "Company research")} />
        <Loading label={t("正在加载研究案…", "Loading research case…")} />
      </div>
    );
  }

  if (!caseId) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader
          eyebrow="RESEARCH / 03"
          title={t("公司研究", "Company research")}
          desc={t("6 个 Agent 分别从产业、商业模式、护城河、财务、治理、估值独立分析，汇总后生成 AI 一页纸；审核通过后自动开始 AI 辩论。", "Six agents analyze industry, business model, moat, financials, governance and valuation independently, then an AI memo is generated; approval auto-starts the AI debate.")}
        />
        {error ? <ErrorBox message={error} onRetry={loadList} /> : null}
        {items.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((c) => (
              <Link
                key={c.id}
                to={`/inst/research?case=${c.id}`}
                className="rounded-xl border border-[#dde5f2] bg-white p-5 transition hover:border-[#7950ba]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-base font-semibold text-[#171923]">{c.company_name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">
                      {c.symbol} · {c.case_no}
                    </p>
                  </div>
                  <StatusBadge status={c.stage} />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone="gold">{c.industry || t("行业待补充", "Industry n/a")}</Badge>
                  <StatusBadge status={c.data_status} />
                </div>
                <p className="mt-3 text-xs text-[#68738b]">
                  {t("点击进入研究案，生成六维结论、资料包与审核记录。", "Open the case to generate six dimensions, the evidence pack and reviews.")}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <Empty>
            <FileSearch className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
            {t("还没有研究案。先到「机会发现」选择一家公司并进入研究。", "No research cases yet. Pick a company in Discovery and start research.")}
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="RESEARCH / 03" title={t("公司研究", "Company research")} />
        <ErrorBox message={error || t("研究案不存在", "Research case not found")} onRetry={() => loadDetail(caseId)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="RESEARCH / 03"
        title={detail.company_name}
        desc={`${detail.symbol} · ${detail.industry || t("行业待补充", "Industry n/a")} · ${detail.case_no}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => nav("/inst/research")}>
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回列表", "Back to list")}
            </Button>
            <Button variant="ghost" disabled={!!busy} onClick={exportReport}>
              <Download className="mr-1 h-4 w-4" />
              {busy === "export" ? t("导出中…", "Exporting…") : t("导出简报", "Export report")}
            </Button>
            <StatusBadge status={detail.stage} />
          </div>
        }
      />

      {error ? <ErrorBox message={error} onRetry={() => loadDetail(caseId)} /> : null}

      {busy === "auto" || hasLiveTasks ? (
        <Card
          title={t("6 个 Agent 实时进度", "6 agents live progress")}
          desc={t("每个 Agent 独立分析，完成后立即显示该维结论；全部完成后再生成 AI 一页纸。", "Each agent analyzes independently; its conclusion appears as soon as it finishes, followed by the AI memo.")}
        >
          <div className="grid gap-2 sm:grid-cols-2">
            {AGENT_TITLES.map(([key, label]) => {
              const task = taskByKey.get(key);
              const status = task?.status || "pending";
              const running = status === "running";
              const done = status === "done" || status === "needs_review";
              return (
                <div key={key} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-xs font-medium text-[#252533]">
                      {running ? <Loader2 className="h-3.5 w-3.5 animate-spin text-[#7950ba]" /> : null}
                      {label}
                    </span>
                    <StatusBadge status={status} />
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-[#68738b]">
                    {done && task?.result?.summary
                      ? task.result.summary
                      : status === "failed"
                        ? task?.result?.agent_error || t("该 Agent 失败，稍后回退规则模板", "Agent failed; fallback will be used")
                        : running
                          ? t("分析中…", "Analyzing…")
                          : t("等待启动…", "Waiting…")}
                  </p>
                </div>
              );
            })}
          </div>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.55fr_1fr]">
        <div className="space-y-4">
          <Card
            title={t("巴菲特六维分析", "Buffett six-dimension analysis")}
            desc={t("每维包含核心问题、数据检查、反证条件与证据 ID；数据不足显示「待补充」，不补造数字。", "Each dimension includes the core question, data checks, falsifiers and evidence IDs. Missing data is marked TBD, never fabricated.")}
            actions={
              <Button
                variant="gold"
                disabled={!canWrite || !!busy}
                onClick={() => void autopilot()}
              >
                <Sparkles className="mr-1 h-4 w-4" />
                {busy === "auto" ? t("6 个 Agent 分析中…", "6 agents analyzing…") : t("自动开展巴菲特六维分析", "Run Buffett six-dimension analysis")}
              </Button>
            }
          >
            {version?.six_dim?.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {version.six_dim.map((dim) => (
                  <article key={dim.key} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-4">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-semibold text-[#171923]">{dim.title}</h3>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <StatusBadge status={dim.status} />
                        <Badge tone={dim.engine === "agent" ? "gold" : "slate"}>
                          {dim.engine === "agent" ? `AI Agent${dim.confidence != null ? ` · ${dim.confidence.toFixed(2)}` : ""}` : t("规则兜底", "Rule fallback")}
                        </Badge>
                      </div>
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-[#68738b]">{dim.question}</p>
                    <p className="mt-2 text-xs leading-relaxed text-[#505369]">{dim.summary || t("待补充", "TBD")}</p>
                    {dim.checks?.length ? (
                      <ul className="mt-2 space-y-1 text-[11px] text-[#68738b]">
                        {dim.checks.map((x) => (
                          <li key={x}>· {x}</li>
                        ))}
                      </ul>
                    ) : null}
                    {dim.counter?.length ? (
                      <p className="mt-2 text-[11px] text-amber-700">{t("反证", "Falsifier")}：{dim.counter[0]}</p>
                    ) : null}
                    {dim.data_gaps?.length ? (
                      <p className="mt-2 text-[11px] text-[#68738b]">{t("数据缺口", "Data gaps")}：{dim.data_gaps.join("；")}</p>
                    ) : null}
                    {dim.agent_error ? (
                      <p className="mt-2 text-[11px] text-red-600">{t("Agent 失败", "Agent failed")}：{dim.agent_error}</p>
                    ) : null}
                    {dim.evidence_ids?.length ? (
                      <p className="mt-2 font-mono text-[10px] text-[#77718c]">
                        {t("证据 ID", "Evidence IDs")}：{dim.evidence_ids.join(", ")}
                      </p>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <Empty>{t("正在自动开展六维分析；如未开始，可点击右上角。", "Six-dimension analysis starts automatically; use the top-right button if needed.")}</Empty>
            )}
          </Card>

          <Card title={t("证据与反证", "Evidence & counter-evidence")} desc={t("重大结论必须可回源；无证据 ID 的结论不能进入审批包。", "Material conclusions must be traceable; conclusions without evidence IDs cannot enter the approval package.")}>
            {detail.evidence?.length ? (
              <ul className="divide-y divide-[#e3eaf8]">
                {detail.evidence.map((ev) => (
                  <li key={ev.id} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-[#252533]">
                          #{ev.id} {ev.title}
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-[#68738b]">{ev.quote || "—"}</p>
                      </div>
                      <div className="shrink-0 text-right">
                        <Badge>{ev.source}</Badge>
                        <p className="mt-1 text-[10px] text-[#77718c]">{ev.as_of || "—"}</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("还没有证据。生成研究会写入行情、估值与财务证据。", "No evidence yet; generating research writes price, valuation and financial evidence.")}</Empty>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title={t("版本与审核", "Version & review")}>
            {version ? (
              <>
                <Field label={t("版本", "Version")} value={`v${version.version_no}`} />
                <Field label={t("状态", "Status")} value={<StatusBadge status={version.status} />} />
                <Field label={t("结论", "Conclusion")} value={version.conclusion || t("待补充", "TBD")} />
                <Field label={t("证据数", "Evidence")} value={`${version.evidence_ids?.length || 0} ${t("条", "items")}`} />
                <div className="mt-3">
                  <Button
                    variant="ghost"
                    disabled={!!busy || !detail.evidence?.length}
                    onClick={() =>
                      run("memo", async () => {
                        const res = await instApi<{ memo: Record<string, any> }>(`/cases/${caseId}/ai/memo`, {
                          method: "POST",
                        });
                        setMemo(res.memo);
                      })
                    }
                  >
                    {busy === "memo" ? t("生成中…", "Generating…") : t("AI 研究一页纸", "AI research memo")}
                  </Button>
                </div>
                {memo ? (
                  <div className="mt-3 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs leading-relaxed text-[#b42345]">
                    <p className="font-medium">{t("AI 摘要（非投资建议）", "AI summary (not investment advice)")}</p>
                    <p className="mt-1">{memo.summary || "—"}</p>
                    {Array.isArray(memo.risks) && memo.risks.length ? (
                      <ul className="mt-2 list-disc pl-4">
                        {memo.risks.map((x: string) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : null}
                    {Array.isArray(memo.open_questions) && memo.open_questions.length ? (
                      <p className="mt-2">{t("待核验", "To verify")}：{memo.open_questions.join("；")}</p>
                    ) : null}
                  </div>
                ) : null}
                {version.valuation ? (
                  <div className="mt-3 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs text-[#b42345]">
                    <p className="font-medium">{t("估值口径", "Valuation basis")}</p>
                    <p className="mt-1 leading-relaxed">
                      {String((version.valuation as Record<string, unknown>).note || t("演示口径，不是目标价。", "Demo basis, not a target price."))}
                    </p>
                  </div>
                ) : null}
                {detail.company_id ? (
                  <div className="mt-3 rounded-xl border border-[#dde5f2] bg-white p-3">
                    <p className="text-xs font-semibold text-[#505369]">
                      {t("五年 DCF（确定性计算 · 不是目标价）", "Five-year DCF (deterministic, not a target price)")}
                    </p>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                      {[
                        ["base_revenue", t("基期收入", "Base revenue")],
                        ["revenue_growth", t("增长率 %", "Growth %")],
                        ["cashflow_margin", t("现金流率 %", "Cash-flow margin %")],
                        ["discount_rate", t("折现率 %", "Discount rate %")],
                        ["terminal_growth", t("永续 %", "Terminal %")],
                        ["shares", t("股本（可选）", "Shares (optional)")],
                      ].map(([key, label]) => (
                        <label key={key} className="space-y-1 text-[#68738b]">
                          <span>{label}</span>
                          <input
                            value={(dcfIn as Record<string, string>)[key]}
                            onChange={(e) => setDcfIn((v) => ({ ...v, [key]: e.target.value }))}
                            inputMode="decimal"
                            className="w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] px-2 py-1 text-xs text-[#252533] outline-none focus:border-[#7950ba]"
                          />
                        </label>
                      ))}
                    </div>
                    <div className="mt-2">
                      <Button variant="ghost" disabled={!!busy} onClick={runDcf}>
                        {busy === "dcf" ? t("计算中…", "Calculating…") : t("计算估值区间", "Calculate range")}
                      </Button>
                    </div>
                    {dcf?.range ? (
                      <div className="mt-2 text-xs leading-relaxed text-[#68738b]">
                        <p>
                          {t("区间", "Range")}：{fmtNum(dcf.range.low, 2)} – {fmtNum(dcf.range.high, 2)}
                          {dcf.range.base_per_share != null
                            ? `；${t("每股", "per share")} ${fmtNum(dcf.range.low_per_share, 2)} / ${fmtNum(dcf.range.base_per_share, 2)} / ${fmtNum(dcf.range.high_per_share, 2)}`
                            : ""}
                        </p>
                        {Array.isArray(dcf.limits) ? (
                          <p className="mt-1 text-[11px] text-[#77718c]">{dcf.limits.join("；")}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {version.status === "pending_review" ? (
                  <div className="mt-4 space-y-2">
                    <textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder={t("审核意见（退回时必须填写）", "Review comment (required when returning)")}
                      className="min-h-[72px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
                    />
                    <div className="flex gap-2">
                      <Button
                        variant="gold"
                        disabled={!canWrite || !!busy}
                        onClick={() => void approveAndDebate()}
                      >
                        {busy === "approve" ? t("提交中…", "Submitting…") : t("审核通过", "Approve")}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!canWrite || !!busy}
                        onClick={() =>
                          run("return", () =>
                            instApi(`/research/${version.id}/review`, {
                              method: "POST",
                              body: { decision: "return", comment: comment || t("退回补充研究", "Return for more research") },
                            }),
                          )
                        }
                      >
                        {t("退回", "Return")}
                      </Button>
                    </div>
                  </div>
                ) : null}
                {version.status === "approved" ? (
                  <div className="mt-4">
                    <div className="mb-2 flex items-center gap-2 text-[11px] text-emerald-700">
                      <Lock className="h-3.5 w-3.5" /> {t("已冻结审核版本，可进入辩论", "Approved version is frozen; debate can start")}
                    </div>
                    <Button
                      variant="primary"
                      disabled={!canWrite || !!busy}
                      onClick={() => nav(`/inst/debate?case=${caseId}`)}
                    >
                      {t("进入投资辩论", "Enter debate")}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : (
              <Empty>{t("还没有研究版本。", "No research versions yet.")}</Empty>
            )}
          </Card>

          <Card title={t("研究任务", "Research tasks")} desc={t("任务状态与进度由研究生成流程写入。", "Task status and progress are written by the research pipeline.")}>
            {detail.tasks?.length ? (
              <ul className="space-y-2">
                {detail.tasks.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-[#505369]">{t.title}</span>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-[11px] text-[#77718c]">{t.progress}%</span>
                      <StatusBadge status={t.status} />
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("生成研究后自动创建六维任务。", "Six-dimension tasks appear after research is generated.")}</Empty>
            )}
          </Card>

          <Card title={t("公司信息", "Company")}>
            <Field label={t("代码", "Symbol")} value={<span className="font-mono">{detail.symbol}</span>} />
            <Field label={t("市场", "Market")} value={detail.market} />
            <Field label={t("行业", "Industry")} value={detail.industry || t("待补充", "TBD")} />
            <Field label={t("数据状态", "Data status")} value={<StatusBadge status={detail.data_status} />} />
            <Field label={t("参考价", "Reference price")} value={fmtNum(detail.ref_price, 2)} />
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t("研究结论由数据与规则生成，AI 仅提供解释与反证建议；估值口径为演示，不是目标价。数据不足时显示「待补充」，不构成投资建议。", "Conclusions come from data and rules; AI only explains and suggests falsifiers. Valuation is illustrative, not a target price. Missing data shows TBD. Not investment advice.")}
      </p>
    </div>
  );
}
