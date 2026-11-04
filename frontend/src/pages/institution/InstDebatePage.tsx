import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, MessagesSquare, Play } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "./instUi";

type Argument = {
  id: number;
  side: "bull" | "bear" | "chair";
  round: number;
  claim: string;
  evidence_ids?: number[];
  confidence?: number;
  falsifier?: string;
  valid?: boolean;
};

type Debate = {
  id: number;
  status: string;
  agenda_step: number;
  conclusion?: string;
  factpack_hash?: string;
  company_name?: string;
  symbol?: string;
  arguments?: Argument[];
};

type ExitCase = {
  id: number;
  status: string;
  reason_type?: string;
  memo?: string;
  case_id?: number;
  proposal_id?: number;
};

type CaseItem = {
  id: number;
  company_id?: number;
  company_name: string;
  symbol: string;
  stage: string;
  versions?: Array<{ id: number; status: string; version_no: number }>;
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
  proposals?: Array<{ id: number; direction?: string; status?: string }>;
  exit_case?: ExitCase | null;
};

export function InstDebatePage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const caseId = Number(params.get("case") || 0);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [detail, setDetail] = useState<CaseItem | null>(null);
  const [debate, setDebate] = useState<Debate | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState("0.05");
  const [proposalBusy, setProposalBusy] = useState(false);
  const [dcf, setDcf] = useState<Record<string, any> | null>(null);
  const [dcfIn, setDcfIn] = useState({
    base_revenue: "100",
    revenue_growth: "10",
    cashflow_margin: "30",
    discount_rate: "10",
    terminal_growth: "2",
    shares: "",
  });
  const [dcfBusy, setDcfBusy] = useState(false);
  const [dcfError, setDcfError] = useState<string | null>(null);
  const autoStarted = useRef(false);
  const autoProposal = useRef(false);

  const canWrite = (session.permissions.debate || "none") === "write";

  const runDcf = async () => {
    if (!detail?.company_id) return;
    setDcfBusy(true);
    setDcfError(null);
    try {
      const res = await instApi<Record<string, any>>(`/companies/${detail.company_id}/dcf`, {
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
      });
      setDcf(res);
    } catch (e) {
      setDcfError(e instanceof Error ? e.message : String(e));
    } finally {
      setDcfBusy(false);
    }
  };

  const loadCases = () => {
    setLoading(true);
    instApi<{ items: CaseItem[] }>("/cases")
      .then((d) => setCases(d.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const loadDetail = async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await instApi<CaseItem>(`/cases/${id}`);
      setDetail(data);
      const latest = (data.debates || [])[0];
      if (latest) {
        const d = await instApi<Debate>(`/debates/${latest.id}`);
        setDebate(d);
      } else {
        setDebate(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (caseId) loadDetail(caseId);
    else {
      setDetail(null);
      setDebate(null);
      loadCases();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const approvedVersion = useMemo(
    () => (detail?.versions || []).find((v) => v.status === "approved"),
    [detail],
  );
  const hasExitCase = Boolean(detail?.exit_case);

  // 退出案的默认目标是清仓（0），普通研究案默认 5%。
  useEffect(() => {
    setTarget(hasExitCase ? "0" : "0.05");
  }, [hasExitCase]);

  const start = async () => {
    if (!caseId) return;
    setBusy(true);
    setError(null);
    try {
      const d = await instApi<Debate>(`/cases/${caseId}/debate`, {
        method: "POST",
        body: { use_ai: true },
      });
      setDebate(d);
      await loadDetail(caseId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!caseId || !detail || !approvedVersion || debate || !canWrite || autoStarted.current) return;
    autoStarted.current = true;
    void start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, detail, approvedVersion, debate, canWrite]);

  useEffect(() => {
    autoStarted.current = false;
    autoProposal.current = false;
    setDcf(null);
    setDcfError(null);
  }, [caseId]);

  const submitProposal = async (direction: string, targetWeight: number, auto: boolean) => {
    if (!caseId || proposalBusy) return;
    setProposalBusy(true);
    setError(null);
    try {
      const res = await instApi<{ id: number }>(`/cases/${caseId}/proposals`, {
        method: "POST",
        body: {
          direction,
          target_weight: targetWeight,
          config: { price_low: null, price_high: null },
        },
      });
      nav(`/inst/approvals?proposal=${res.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (auto) autoProposal.current = false;
    } finally {
      setProposalBusy(false);
    }
  };

  // 线性流程：辩论完成后自动创建议案（普通案买入 5%；退出案 exit + 0 清仓）。
  useEffect(() => {
    if (!caseId || !detail || !debate || debate.status !== "completed" || !canWrite) return;
    if ((detail.proposals || []).length || autoProposal.current) return;
    autoProposal.current = true;
    void submitProposal(hasExitCase ? "exit" : "buy", hasExitCase ? 0 : 0.05, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, detail, debate, canWrite, hasExitCase]);

  const groups = useMemo(() => {
    const args = debate?.arguments || [];
    return {
      bull: args.filter((a) => a.side === "bull"),
      bear: args.filter((a) => a.side === "bear"),
      chair: args.filter((a) => a.side === "chair"),
    };
  }, [debate]);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="DEBATE / 04" title={t("投资辩论室", "Investment debate")} />
        <Loading label={t("正在加载辩论…", "Loading debate…")} />
      </div>
    );
  }

  if (!caseId) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader
          eyebrow="DEBATE / 04"
          title={t("投资辩论室", "Investment debate")}
          desc={t("先有已审核通过的研究版本，才能开始辩论；进入后 AI 会自动开展正反方独立立论与交叉质询。", "An approved research version is required; once opened, AI automatically runs the bull/bear arguments and cross-examination.")}
        />
        {error ? <ErrorBox message={error} onRetry={loadCases} /> : null}
        {cases.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {cases.map((c) => (
              <Link
                key={c.id}
                to={`/inst/debate?case=${c.id}`}
                className="rounded-xl border border-[#dde5f2] bg-white p-5 transition hover:border-[#7950ba]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-base font-semibold text-[#171923]">{c.company_name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">{c.symbol}</p>
                  </div>
                  <StatusBadge status={c.stage} />
                </div>
                <p className="mt-3 text-xs text-[#68738b]">
                  {c.debates?.length ? t(`已有 ${c.debates.length} 场辩论`, `${c.debates.length} debate(s)`) : t("尚未开始辩论", "No debate yet")}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <Empty>
            <MessagesSquare className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
            {t("还没有研究案。先从「机会发现」进入研究。", "No research cases yet. Start from Discovery.")}
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="DEBATE / 04" title={t("投资辩论室", "Investment debate")} />
        <ErrorBox message={error || t("研究案不存在", "Research case not found")} onRetry={() => loadDetail(caseId)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="DEBATE / 04"
        title={t(
          `${detail.company_name} · ${hasExitCase ? "退出辩论" : "投资辩论"}`,
          `${detail.company_name} · ${hasExitCase ? "Exit debate" : "Investment debate"}`,
        )}
        desc={`${detail.symbol} · ${hasExitCase ? t("退出研究案：结论用于退出议案，方向固定为卖出/退出。", "Exit research case: the conclusion feeds an exit proposal; direction is sell/exit.") : t("正反方独立立论，保留未解决异议；结论只做流程建议，不生成订单。", "Independent bull/bear arguments, with unresolved dissent retained. Conclusions are process suggestions only and never create orders.")}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => nav(`/inst/research?case=${caseId}`)}>
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回研究", "Back to research")}
            </Button>
            <StatusBadge status={detail.stage} />
          </div>
        }
      />

      {error ? <ErrorBox message={error} onRetry={() => loadDetail(caseId)} /> : null}

      {!approvedVersion ? (
        <Card title={t("辩论门禁", "Debate gate")}>
          <p className="text-sm text-[#68738b]">
            {t("研究审核尚未通过，不能进入辩论。请先在研究页确认研究成果。", "Research is not approved yet; confirm it on the research page first.")}
          </p>
          <div className="mt-3">
            <Button variant="gold" onClick={() => nav(`/inst/research?case=${caseId}`)}>
              {t("去研究页审核", "Go to research review")}
            </Button>
          </div>
        </Card>
      ) : !debate ? (
        <Card
          title={t("开始辩论", "Start debate")}
          desc={t(`研究 v${approvedVersion.version_no} 已审核通过；AI 正在自动生成正反方论点与主持结论，也可手动重试。`, `Research v${approvedVersion.version_no} is approved. AI is auto-generating bull/bear arguments and the chair conclusion; manual retry is available.`)}
        >
          <Button variant="gold" disabled={!canWrite || busy} onClick={start}>
            <Play className="mr-1 h-4 w-4" />
            {busy ? t("辩论生成中…", "Generating…") : t("开始两轮辩论", "Start two-round debate")}
          </Button>
          <p className="mt-3 text-[11px] leading-relaxed text-[#77718c]">
            {t("论点必须引用证据 ID；AI 不可用时使用规则模板并标注。辩论不产生买卖建议。", "Arguments must cite evidence IDs; when AI is unavailable, rule templates are used and labeled. Debate produces no trade advice.")}
          </p>
        </Card>
      ) : (
        <>
          <Card
            title={t("辩论记录", "Debate record")}
            desc={`${t("场次", "Session")} #${debate.id} · ${t("事实包指纹", "Fact pack hash")} ${String(debate.factpack_hash || "").slice(0, 12)}…`}
            actions={<StatusBadge status={debate.status} />}
          >
            <div className="mb-4 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] px-4 py-3 text-sm text-[#b42345]">
              {t("主持结论", "Chair conclusion")}：<b>{debate.conclusion || t("待定", "TBD")}</b>
              <span className="ml-2 text-[11px]">{t("（流程建议，不构成投资建议）", "(process suggestion, not investment advice)")}</span>
            </div>
            <p className="mb-3 text-[11px] leading-relaxed text-[#77718c]">
              {t(
                "证据 ID 对应研究页「证据与反证」中的编号；没有有效证据引用的论点不计入裁决。",
                "Evidence IDs refer to the numbers in the research page's Evidence & counter-evidence card; arguments without valid citations are excluded from the verdict.",
              )}
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {[
                { key: "bull", title: t("正方 · 看多", "Bull case"), tone: "green" as const, items: groups.bull },
                { key: "bear", title: t("反方 · 看空", "Bear case"), tone: "red" as const, items: groups.bear },
              ].map((col) => (
                <div key={col.key} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-[#171923]">{col.title}</h3>
                    <Badge tone={col.tone}>{col.items.length} {t("条", "items")}</Badge>
                  </div>
                  {col.items.length ? (
                    <ul className="space-y-3">
                      {col.items.map((a) => (
                        <li key={a.id} className="rounded-lg border border-white bg-white p-3">
                          <div className="flex items-center justify-between gap-2">
                            <Badge>{locale === "en" ? `Round ${a.round}` : `第 ${a.round} 轮`}</Badge>
                            <span className="font-mono text-[10px] text-[#77718c]">
                              {t("置信度", "Confidence")} {a.confidence?.toFixed?.(2) ?? "—"}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-relaxed text-[#505369]">{a.claim}</p>
                          {a.evidence_ids?.length ? (
                            <p className="mt-2 font-mono text-[10px] text-[#77718c]">
                              {t("证据", "Evidence")}：{a.evidence_ids.join(", ")}
                            </p>
                          ) : (
                            <p className="mt-2 text-[10px] text-amber-600">{t("无有效证据引用，不计入裁决", "No valid evidence citation; excluded from the verdict")}</p>
                          )}
                          {a.falsifier ? (
                            <p className="mt-2 text-[11px] leading-relaxed text-[#68738b]">
                              {t("可证伪条件", "Falsifier")}：{a.falsifier}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <Empty>{t("该方暂无有效论点。", "No valid arguments on this side.")}</Empty>
                  )}
                </div>
              ))}
            </div>
          </Card>

          {detail.company_id ? (
            <Card
              title={t("估值复核：五年 DCF", "Valuation check: five-year DCF")}
              desc={t(
                "辩论中的确定性估值复核：按固定假设推演五年现金流并折现，用来检查正反方对价格的假设是否离谱；不是目标价，也不预测股价。",
                "A deterministic valuation check for the debate: projects five years of cash flow from fixed assumptions and discounts them, to test whether either side's price assumption is unreasonable. Not a target price and not a price forecast.",
              )}
            >
              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
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
                      className="w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] px-2 py-1.5 text-xs text-[#252533] outline-none focus:border-[#7950ba]"
                    />
                  </label>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button variant="ghost" disabled={dcfBusy} onClick={() => void runDcf()}>
                  {dcfBusy ? t("计算中…", "Calculating…") : t("计算估值区间", "Calculate range")}
                </Button>
                <span className="text-[10px] text-[#77718c]">
                  {t("输入为演示假设，可按辩论中的情景调整。", "Inputs are illustrative assumptions and can be adjusted to the debate scenario.")}
                </span>
              </div>
              {dcfError ? (
                <p className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-700">
                  {dcfError}
                </p>
              ) : null}
              {dcf?.range ? (
                <div className="mt-3 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs leading-relaxed text-[#5a3d85]">
                  <p>
                    {t("区间", "Range")}：{fmtNum(dcf.range.low, 2)} – {fmtNum(dcf.range.high, 2)}
                    {dcf.range.base_per_share != null
                      ? `；${t("每股", "per share")} ${fmtNum(dcf.range.low_per_share, 2)} / ${fmtNum(dcf.range.base_per_share, 2)} / ${fmtNum(dcf.range.high_per_share, 2)}`
                      : ""}
                  </p>
                  {Array.isArray(dcf.limits) && dcf.limits.length ? (
                    <p className="mt-1 text-[10px] leading-relaxed text-[#77718c]">{dcf.limits.join("；")}</p>
                  ) : null}
                </div>
              ) : null}
            </Card>
          ) : null}

          <Card title={t("主持与裁决", "Chair & ruling")} desc={t("主持只做流程建议：推进审议 / 补充研究 / 继续观察 / 拒绝。", "The chair only recommends: proceed / supplement research / keep watching / reject.")}>
            {groups.chair.length ? (
              <ul className="space-y-2">
                {groups.chair.map((a) => (
                  <li key={a.id} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3 text-xs leading-relaxed text-[#505369]">
                    {a.claim}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("暂无主持记录。", "No chair record.")}</Empty>
            )}
            {hasExitCase ? (
              <div className="mt-4 rounded-xl border border-[#b42345]/30 bg-[#fbe9ef] px-4 py-3 text-xs leading-relaxed text-[#a31f42]">
                {t(
                  "这是退出研究案：只能创建退出议案（方向 sell/exit），目标仓位默认 0（清仓），不能创建买入议案。",
                  "This is an exit research case: only sell/exit proposals are allowed, target weight defaults to 0 (full exit), and buy proposals are rejected.",
                )}
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-[#68738b]">
                {hasExitCase
                  ? t("目标仓位（0 = 清仓）", "Target weight (0 = full exit)")
                  : t("目标仓位（占净值）", "Target weight (of NAV)")}
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  data-testid="inst-proposal-target"
                  className="ml-2 w-24 rounded-lg border border-[#dde5f2] bg-white px-2 py-1.5 text-xs text-[#252533] outline-none"
                  placeholder={hasExitCase ? "0" : "0.05"}
                />
              </label>
              <Button
                variant="primary"
                testId="inst-proposal-create"
                disabled={!canWrite || busy || proposalBusy || Boolean(detail.proposals?.length)}
                onClick={async () => {
                  const parsed = Number(target);
                  if (target.trim() === "" || !Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
                    setError(
                      t(
                        "目标仓位必须是 0-1 之间的数字；空值不会按 0 清仓处理。",
                        "Target weight must be a number between 0 and 1; blank is not treated as a full exit.",
                      ),
                    );
                    return;
                  }
                  if (!hasExitCase && parsed <= 0) {
                    setError(t("买入议案的目标仓位必须大于 0。", "A buy proposal needs a target weight above 0."));
                    return;
                  }
                  if (
                    hasExitCase &&
                    parsed === 0 &&
                    !window.confirm(
                      t(
                        "目标仓位为 0，表示全部清仓。确认创建退出议案？",
                        "Target weight 0 means a full exit. Create the exit proposal?",
                      ),
                    )
                  ) {
                    return;
                  }
                  await submitProposal(hasExitCase ? "exit" : "buy", parsed, false);
                }}
              >
                {proposalBusy
                  ? t("创建中…", "Creating…")
                  : hasExitCase
                    ? t("创建退出议案", "Create exit proposal")
                    : t("创建议案", "Create proposal")}
              </Button>
              <Button variant="ghost" onClick={() => nav("/inst/debate")}>
                {t("返回辩论列表", "Back to debate list")}
              </Button>
            </div>
            {detail.proposals?.length ? (
              <p className="mt-2 text-[11px] leading-relaxed text-[#7950ba]">
                {t("已创建议案", "Proposal created")} #{detail.proposals[0].id} ·{" "}
                <Link className="underline underline-offset-2" to={`/inst/approvals?proposal=${detail.proposals[0].id}`}>
                  {t("去审批", "Go to approval")}
                </Link>
              </p>
            ) : null}
            <p className="mt-2 text-[11px] leading-relaxed text-[#77718c]">
              {t(
                "辩论完成后自动创建议案：普通研究案默认买入 5%，退出研究案默认 exit + 0（清仓）；合伙人复核时可调整目标仓位。之后进入 Chairman 审批 → 风控 → 自动模拟成交。",
                "A proposal is created automatically after the debate: 5% buy by default, or exit + 0 for an exit case; the partner can adjust the target. It then goes through Chairman approval → risk → automatic simulated fill.",
              )}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
