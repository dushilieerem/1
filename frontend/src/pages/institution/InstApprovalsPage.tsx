import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BadgeCheck, ShieldAlert, Stamp } from "lucide-react";
import { instApi, fmtNum, fmtPct, fmtDateTime } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "./instUi";

type ProposalListItem = {
  id: number;
  status: string;
  direction: string;
  target_weight: number;
  company_name: string;
  symbol: string;
  market: string;
  version_no?: number;
  authorization_id?: number;
  authorization_status?: string;
  updated_at?: string;
};

type Approval = {
  id: number;
  step: string;
  decision: string;
  comment?: string;
  decided_at?: string;
};

type ExitCase = {
  id: number;
  status: string;
  reason_type?: string;
  memo?: string;
  case_id?: number;
};

type ProposalDetail = ProposalListItem & {
  current_version?: { id: number; version_no: number; status: string; snapshot: Record<string, any> };
  versions?: Array<{ id: number; version_no: number; status: string; snapshot: Record<string, any> }>;
  approvals?: Approval[];
  authorizations?: Array<{ id: number; status: string; issued_at: string; snapshot: Record<string, any> }>;
  exit_case?: ExitCase | null;
};

const STEP_LABEL_ZH: Record<string, string> = {
  partner: "合伙人复核",
  chairman: "Chairman 审批",
  risk_precheck: "执行前风控复核",
};
const STEP_LABEL_EN: Record<string, string> = {
  partner: "Partner review",
  chairman: "Chairman approval",
  risk_precheck: "Pre-execution risk check",
};

const EXIT_REASON: Record<string, [string, string]> = {
  thesis_invalid: ["论点失效", "Thesis broken"],
  valuation: ["估值透支", "Valuation stretched"],
  better_allocation: ["更优资本配置", "Better allocation"],
  portfolio_constraint: ["组合/资金约束", "Portfolio constraint"],
  other: ["其他", "Other"],
};

export function InstApprovalsPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const stepLabel = (step: string) => (locale === "en" ? STEP_LABEL_EN[step] : STEP_LABEL_ZH[step]) || step;
  const directionLabel = (direction?: string) =>
    direction === "buy"
      ? t("买入", "Buy")
      : direction === "sell"
        ? t("卖出", "Sell")
        : direction === "exit"
          ? t("退出", "Exit")
          : direction || "—";
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const selectedId = Number(params.get("proposal") || 0);
  const [items, setItems] = useState<ProposalListItem[]>([]);
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [target, setTarget] = useState("");
  const [riskMemo, setRiskMemo] = useState<Record<string, any> | null>(null);
  const [chairMemo, setChairMemo] = useState<Record<string, any> | null>(null);
  const [chairmanMode, setChairmanMode] = useState<Record<string, any> | null>(null);
  const autoAiKey = useRef("");
  const [handoverNote, setHandoverNote] = useState("");

  const role = session.role;
  const canWrite = (session.permissions.approvals || "none") === "write";

  const loadList = () => {
    setLoading(true);
    setError(null);
    instApi<{ items: ProposalListItem[] }>("/proposals")
      .then((d) => setItems(d.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const loadDetail = (id: number) => {
    setLoading(true);
    setError(null);
    instApi<ProposalDetail>(`/proposals/${id}`)
      .then((d) => {
        setDetail(d);
        setTarget(String(d.target_weight ?? d.current_version?.snapshot?.target_weight ?? ""));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
    else {
      setDetail(null);
      loadList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    const versionId = detail?.current_version?.id;
    if (!selectedId || !versionId) return;
    const key = `${selectedId}:${versionId}`;
    if (autoAiKey.current === key) return;
    autoAiKey.current = key;
    setRiskMemo(null);
    setChairMemo(null);
    const loadOne = async (path: string, set: (value: Record<string, any>) => void) => {
      try {
        const res = await instApi<{ memo: Record<string, any> }>(path, {
          method: "POST",
          body: { refresh: false },
        });
        if (res.memo) set(res.memo);
      } catch {
        /* AI 未配置时不阻断审批；按钮仍可重试 */
      }
    };
    void loadOne(`/proposals/${selectedId}/ai/risk-review`, setRiskMemo);
    void loadOne(`/proposals/${selectedId}/ai/chairman-memo`, setChairMemo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, detail?.current_version?.id]);

  const approvalMap = useMemo(() => {
    const map = new Map<string, Approval>();
    for (const a of detail?.approvals || []) map.set(a.step, a);
    return map;
  }, [detail]);

  const canAuthorize =
    approvalMap.get("partner")?.decision === "approve" &&
    ["approve", "conditional"].includes(approvalMap.get("chairman")?.decision || "") &&
    approvalMap.get("risk_precheck")?.decision === "pass";
  // 方案 B：最后一关由 Chairman/风控完成，通过即授权并模拟成交。
  const canAutoExecute = canAuthorize && (role === "chairman" || role === "risk");

  const act = async (label: string, fn: () => Promise<unknown>) => {
    if (!selectedId) return;
    setBusy(label);
    setError(null);
    try {
      await fn();
      setComment("");
      loadDetail(selectedId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const approveAndExecute = async () => {
    if (!selectedId) return;
    setBusy("approve-execute");
    setError(null);
    try {
      const res = await instApi<{ authorization_id: number }>(
        `/proposals/${selectedId}/approve-and-execute`,
        { method: "POST" },
      );
      nav("/inst/portfolio", {
        state: {
          flash: t(
            `议案 #${selectedId} 已通过并模拟成交（授权 #${res.authorization_id}），持仓已更新。`,
            `Proposal #${selectedId} approved and simulated fill completed (authorization #${res.authorization_id}); positions updated.`,
          ),
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      loadDetail(selectedId);
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="APPROVALS / 06" title={t("投委会与审批", "IC & approvals")} />
        <Loading label={t("正在加载议案…", "Loading proposals…")} />
      </div>
    );
  }

  if (!selectedId) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader
          eyebrow="APPROVALS / 06"
          title={t("投委会与审批", "IC & approvals")}
          desc={t("议案版本、合伙人复核、Chairman 审批、独立风控与不可变授权快照。任一步拒绝或阻断都不能跳级。", "Proposal versions, partner review, Chairman approval, independent risk and immutable authorization snapshots. No step can be skipped.")}
        />
        {error ? <ErrorBox message={error} onRetry={loadList} /> : null}
        {items.length ? (
          <div className="space-y-3">
            {items.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setParams({ proposal: String(p.id) })}
                className="w-full rounded-xl border border-[#dde5f2] bg-white p-5 text-left transition hover:border-[#7950ba]"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-display text-base font-semibold text-[#171923]">{p.company_name}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">
                      #{p.id} · {p.symbol} · {directionLabel(p.direction)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="gold" title={t("目标仓位 = 目标持仓市值 / 组合净值", "Target weight = target position value / NAV")}>
                      {t("目标仓位", "Target")} {fmtPct(p.target_weight)}
                    </Badge>
                    <StatusBadge status={p.status} />
                    {p.authorization_status ? <StatusBadge status={p.authorization_status} /> : null}
                  </div>
                </div>
                <p className="mt-3 text-xs text-[#68738b]">
                  {t("当前版本", "Current version")} v{p.version_no || 1} · {t("点击进入审批详情", "Open approval detail")}
                </p>
              </button>
            ))}
          </div>
        ) : (
          <Empty>
            <BadgeCheck className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
            {t("还没有议案。完成研究与辩论后，经理可在议案页创建。", "No proposals yet. After research and debate, a manager can create one.")}
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="APPROVALS / 06" title={t("议案详情", "Proposal")} />
        <ErrorBox message={error || t("议案不存在", "Proposal not found")} onRetry={() => loadDetail(selectedId)} />
      </div>
    );
  }

  const snapshot = detail.current_version?.snapshot || {};
  const hasPriceRange = snapshot.price_low != null || snapshot.price_high != null;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="APPROVALS / 06"
        title={`${detail.company_name} · ${t("议案", "Proposal")} #${detail.id}`}
        desc={`${detail.symbol} · ${directionLabel(detail.direction)} · ${t("当前版本", "Current version")} v${detail.current_version?.version_no || 1}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => setParams({})}>
              {t("返回列表", "Back to list")}
            </Button>
            <StatusBadge status={detail.status} />
          </div>
        }
      />

      {error ? <ErrorBox message={error} onRetry={() => loadDetail(selectedId)} /> : null}

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <Card title={t("议案快照", "Proposal snapshot")} desc={t("授权绑定研究版本、议案版本、配置、批准人与有效期。", "Authorization binds research version, proposal version, configuration, approver and validity.")}>
            <div className="grid gap-x-6 sm:grid-cols-2">
              <Field label={t("议案版本", "Proposal version")} value={`v${detail.current_version?.version_no || 1}`} />
              <Field label={t("研究版本", "Research version")} value={String(snapshot.research_version_no || snapshot.research_version_id || "—")} />
              <Field label={t("方向", "Direction")} value={directionLabel(detail.direction)} />
              <Field label={t("目标仓位（占净值）", "Target weight (of NAV)")} value={fmtPct(snapshot.target_weight ?? detail.target_weight)} />
              <Field
                label={t("价格区间（CNY）", "Price range (CNY)")}
                value={
                  hasPriceRange ? (
                    `${fmtNum(snapshot.price_low, 2)} - ${fmtNum(snapshot.price_high, 2)}`
                  ) : (
                    <span className="text-[#a9a4bd]" title={t("未设置价格区间，执行时不按价格区间校验。", "No price range set; execution will not check price bounds.")}>
                      {t("未设置", "Not set")}
                    </span>
                  )
                }
              />
              <Field
                label={t("账户", "Account")}
                value={snapshot.account ? t(`模拟账户 ${snapshot.account}`, `Sim account ${snapshot.account}`) : t("未指定", "Not specified")}
              />
              <Field
                label={t("资金来源", "Funding source")}
                value={String(snapshot.funding_source || t("未指定", "Not specified"))}
              />
              <Field
                label={t("币种 / 汇率", "Currency / FX")}
                value={`${snapshot.currency === "CNY" || !snapshot.currency ? t("人民币（CNY）", "CNY") : snapshot.currency} / ${snapshot.fx_rate ?? "—"}`}
              />
              <Field label={t("有效期", "Valid until")} value={String(snapshot.valid_until || t("未设置", "Not set"))} />
            </div>
            {!hasPriceRange ? (
              <p className="mt-2 text-[10px] leading-relaxed text-[#77718c]">
                {t(
                  "价格区间未设置：执行时不按价格区间校验；如需限价，请在议案配置中补充。",
                  "No price range: execution will not enforce price bounds. Add one in the proposal config if a limit is required.",
                )}
              </p>
            ) : null}
            {snapshot.investment_opinion ? (
              <div className="mt-3 rounded-xl border border-[#dde5f2] bg-[#f8faff] p-3 text-xs leading-relaxed text-[#505369]">
                <p className="font-medium text-[#b42345]">{t("投资经理意见", "Investment manager opinion")}</p>
                <p className="mt-1 whitespace-pre-wrap">{String(snapshot.investment_opinion)}</p>
              </div>
            ) : null}
            {Array.isArray(snapshot.monitoring) && snapshot.monitoring.length ? (
              <div className="mt-3 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs text-[#b42345]">
                <p className="font-medium">{t("监控条件", "Monitoring conditions")}</p>
                <ul className="mt-1 list-disc pl-4">
                  {snapshot.monitoring.map((x: string) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {detail.exit_case ? (
              <div className="mt-3 rounded-xl border border-[#b42345]/30 bg-[#fbe9ef] p-3 text-xs text-[#a31f42]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">
                    {t("退出案", "Exit case")} EX-{detail.exit_case.id}
                  </p>
                  <StatusBadge status={detail.exit_case.status} />
                </div>
                <p className="mt-1">
                  {t("退出原因", "Reason")}：
                  {EXIT_REASON[detail.exit_case.reason_type || ""]
                    ? locale === "en"
                      ? EXIT_REASON[detail.exit_case.reason_type || ""][1]
                      : EXIT_REASON[detail.exit_case.reason_type || ""][0]
                    : detail.exit_case.reason_type || "—"}
                </p>
                {detail.exit_case.memo ? <p className="mt-1">{detail.exit_case.memo}</p> : null}
                {detail.exit_case.case_id ? (
                  <Link
                    className="mt-2 inline-block text-[#b42345] underline underline-offset-2"
                    to={`/inst/research?case=${detail.exit_case.case_id}`}
                  >
                    {t("查看退出研究案", "Open exit research case")} →
                  </Link>
                ) : null}
              </div>
            ) : null}
          </Card>

          <Card title={t("审批链", "Approval chain")} desc={t("职责分离：提案人不得批准自己的议案；风控否决终局。", "Separation of duties: proposers cannot approve their own proposal; risk veto is final.")}>
            <div className="space-y-3">
              {(["partner", "chairman", "risk_precheck"] as const).map((step) => {
                const a = approvalMap.get(step);
                return (
                  <div key={step} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[#e3eaf8] bg-[#f8faff] px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-[#252533]">{stepLabel(step)}</p>
                      <p className="mt-1 text-xs text-[#68738b]">
                        {a ? a.comment || t("无审批意见", "No comment") : t("尚未处理", "Pending")}
                      </p>
                      {a?.decided_at ? (
                        <p className="mt-1 text-[10px] text-[#77718c]">
                          {t("处理时间", "Decided at")}：{fmtDateTime(a.decided_at)}
                        </p>
                      ) : null}
                    </div>
                    <StatusBadge status={a?.decision || "pending"} />
                  </div>
                );
              })}
            </div>

            {canWrite ? (
              <div className="mt-4 space-y-3 rounded-xl border border-[#e3eaf8] p-4">
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder={t("审批意见（通过/拒绝/退回均建议填写）", "Review comment (recommended for approve/reject/return)")}
                  className="min-h-[72px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
                />
                <div className="flex flex-wrap gap-2">
                  {role === "partner" ? (
                    <>
                      <input
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                        placeholder={t("目标仓位，如 0.05", "Target weight, e.g. 0.05")}
                        className="w-36 rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs outline-none"
                      />
                      <Button
                        variant="gold"
                        disabled={!!busy}
                        onClick={() =>
                          act("partner", () =>
                            instApi(`/proposals/${selectedId}/partner`, {
                              method: "POST",
                              body: {
                                decision: "approve",
                                comment,
                                updates: target ? { target_weight: Number(target) } : {},
                              },
                            }),
                          )
                        }
                      >
                        {busy === "partner" ? t("提交中…", "Submitting…") : t("合伙人复核通过", "Partner approve")}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!!busy}
                        onClick={() =>
                          act("return", () =>
                            instApi(`/proposals/${selectedId}/partner`, {
                              method: "POST",
                              body: { decision: "return", comment: comment || t("退回补充", "Return for more") },
                            }),
                          )
                        }
                      >
                        {t("退回", "Return")}
                      </Button>
                    </>
                  ) : null}

                  {role === "chairman" ? (
                    <>
                      <Button
                        variant="gold"
                        disabled={!!busy}
                        onClick={() =>
                          act("chairman", () =>
                            instApi(`/proposals/${selectedId}/chairman`, {
                              method: "POST",
                              body: { decision: "approve", comment },
                            }),
                          )
                        }
                      >
                        {busy === "chairman" ? t("提交中…", "Submitting…") : t("Chairman 批准", "Chairman approve")}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!!busy}
                        onClick={() =>
                          act("reject", () =>
                            instApi(`/proposals/${selectedId}/chairman`, {
                              method: "POST",
                              body: { decision: "reject", comment: comment || t("不同意", "Reject") },
                            }),
                          )
                        }
                      >
                        {t("拒绝", "Reject")}
                      </Button>
                    </>
                  ) : null}

                  {role === "risk" ? (
                    <Button
                      variant="primary"
                      disabled={!!busy}
                      onClick={() =>
                        act("risk", () =>
                          instApi(`/proposals/${selectedId}/risk-check`, {
                            method: "POST",
                            body: { comment: comment || t("执行前风控复核", "Pre-execution risk review") },
                          }),
                        )
                      }
                    >
                      {busy === "risk" ? t("复核中…", "Checking…") : t("执行前风控复核", "Pre-execution risk check")}
                    </Button>
                  ) : null}

                  {canAutoExecute && ["risk_precheck", "authorized"].includes(detail.status) ? (
                    <Button
                      variant="gold"
                      disabled={!!busy}
                      onClick={() => void approveAndExecute()}
                    >
                      {busy === "approve-execute"
                        ? t("成交中…", "Executing…")
                        : detail.status === "authorized"
                          ? t("重试模拟成交", "Retry simulated fill")
                          : t("批准并模拟成交", "Approve & simulate fill")}
                    </Button>
                  ) : detail.status === "executed" ? (
                    <p className="w-full text-[11px] leading-relaxed text-emerald-700">
                      {t("该议案已通过并模拟成交，持仓已更新。", "This proposal is approved and simulated-filled; positions are updated.")}
                    </p>
                  ) : detail.status === "authorized" ? (
                    <p className="w-full text-[11px] leading-relaxed text-amber-700">
                      {t(
                        "授权已生成但成交未完成；请由 Chairman/风控重试，或到投资组合查看执行异常。",
                        "Authorization created but the fill is incomplete; Chairman/Risk can retry, or check Portfolio for execution exceptions.",
                      )}
                    </p>
                  ) : canAuthorize ? (
                    <p className="w-full text-[11px] leading-relaxed text-[#77718c]">
                      {t(
                        "等待 Chairman/风控完成最后一步；通过后自动模拟成交。",
                        "Waiting for Chairman/Risk to complete the final step; it will auto-fill on approval.",
                      )}
                    </p>
                  ) : null}
                </div>
                <p className="text-[11px] leading-relaxed text-[#77718c]">
                  {t(
                    "方案 B：最后一关通过后自动生成授权并模拟成交，持仓随后出现在投资组合；风控阻断后不能批准。",
                    "Flow B: the final approval creates the authorization and simulated fill automatically; the position then appears in Portfolio. A risk block prevents approval.",
                  )}
                </p>
              </div>
            ) : null}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title={t("风控检查", "Risk checks")} desc={t("硬性阻断：单股 >15%、交易后现金 <10%、版本不一致、无有效批准。", "Hard blocks: single name >15%, post-trade cash <10%, version mismatch, no valid approval.")}>
            {detail.approvals?.length ? (
              <ul className="space-y-2 text-xs">
                {detail.approvals.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 rounded-lg border border-[#e3eaf8] px-3 py-2">
                    <span className="text-[#68738b]">{stepLabel(a.step)}</span>
                    <StatusBadge status={a.decision} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("尚未产生审批记录。", "No approval records yet.")}</Empty>
            )}
            {detail.approvals?.some((a) => a.decision === "block" || a.decision === "veto") ? (
              <p className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-[11px] text-red-700">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {t("风控已阻断。需整改并由独立风控重新核验，Chairman 不能绕过。", "Risk has blocked this proposal. Remediate and obtain a fresh independent risk review; Chairman cannot bypass.")}
              </p>
            ) : null}
          </Card>

          <Card title={t("AI 审议辅助", "AI review support")} desc={t("进入议案后自动生成并落库；AI 只读议案、审批与风控检查，不改变状态；不提供目标价或买卖指令。", "Generated automatically on entry and persisted; AI only reads the proposal, approvals and risk checks, never changes state or gives target prices/trade instructions.")}>
            <div className="space-y-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="ghost"
                    disabled={!!busy}
                    onClick={() =>
                      act("ai-risk", async () => {
                        const res = await instApi<{ memo: Record<string, any> }>(
                          `/proposals/${selectedId}/ai/risk-review`,
                          { method: "POST", body: { refresh: true } },
                        );
                        setRiskMemo(res.memo);
                      })
                    }
                  >
                    {busy === "ai-risk"
                      ? t("生成中…", "Generating…")
                      : riskMemo
                        ? t("重新生成风控意见", "Regenerate risk opinion")
                        : t("AI 风控意见", "AI risk opinion")}
                  </Button>
                  <Badge tone="slate">{t("只读建议", "Read-only")}</Badge>
                </div>
                {riskMemo ? (
                  <div className="mt-2 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs leading-relaxed text-[#b42345]">
                    <p className="font-medium">{t("AI 风控意见（非投资建议，需真人确认）", "AI risk opinion (not advice; human confirmation required)")}</p>
                    <p className="mt-1">{riskMemo.summary || "—"}</p>
                    {Array.isArray(riskMemo.risks) && riskMemo.risks.length ? (
                      <ul className="mt-2 list-disc pl-4">
                        {riskMemo.risks.map((x: string) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : null}
                    {Array.isArray(riskMemo.open_questions) && riskMemo.open_questions.length ? (
                      <p className="mt-2">{t("待核验", "To verify")}：{riskMemo.open_questions.join("；")}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="ghost"
                    disabled={!!busy}
                    onClick={() =>
                      act("ai-chair", async () => {
                        const res = await instApi<{ memo: Record<string, any> }>(
                          `/proposals/${selectedId}/ai/chairman-memo`,
                          { method: "POST", body: { refresh: true } },
                        );
                        setChairMemo(res.memo);
                      })
                    }
                  >
                    {busy === "ai-chair"
                      ? t("生成中…", "Generating…")
                      : chairMemo
                        ? t("重新生成 Chairman 摘要", "Regenerate Chairman memo")
                        : t("AI Chairman 摘要", "AI Chairman memo")}
                  </Button>
                  <Badge tone="slate">{t("只读建议", "Read-only")}</Badge>
                </div>
                {chairMemo ? (
                  <div className="mt-2 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs leading-relaxed text-[#b42345]">
                    <p className="font-medium">{t("AI Chairman 摘要（非投资建议，需真人确认）", "AI Chairman memo (not advice; human confirmation required)")}</p>
                    <p className="mt-1">{chairMemo.summary || "—"}</p>
                    {Array.isArray(chairMemo.risks) && chairMemo.risks.length ? (
                      <ul className="mt-2 list-disc pl-4">
                        {chairMemo.risks.map((x: string) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : null}
                    {Array.isArray(chairMemo.open_questions) && chairMemo.open_questions.length ? (
                      <p className="mt-2">{t("待核验", "To verify")}：{chairMemo.open_questions.join("；")}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </Card>

          <Card
            title={t("AI Chairman 模式", "AI Chairman mode")}
            desc={t("预检查与模拟批准只读议案，不写审批、不改状态；最终由真人 Chairman 表决。", "Pre-check and simulated approval are read-only; the human Chairman makes the binding decision.")}
          >
            <div className="flex flex-wrap gap-2">
              <Button
                variant="ghost"
                disabled={!!busy}
                onClick={() =>
                  act("chair-pre", async () => {
                    const res = await instApi<Record<string, any>>(
                      `/proposals/${selectedId}/ai/chairman-precheck`,
                    );
                    setChairmanMode(res);
                  })
                }
              >
                {busy === "chair-pre" ? t("检查中…", "Checking…") : t("预检查", "Pre-check")}
              </Button>
              <Button
                variant="ghost"
                disabled={!!busy}
                onClick={() =>
                  act("chair-sim", async () => {
                    const res = await instApi<Record<string, any>>(
                      `/proposals/${selectedId}/ai/chairman-simulate`,
                      { method: "POST" },
                    );
                    setChairmanMode(res);
                  })
                }
              >
                {busy === "chair-sim" ? t("模拟中…", "Simulating…") : t("模拟批准", "Simulate approval")}
              </Button>
            </div>
            {chairmanMode ? (
              <div className="mt-3 space-y-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={chairmanMode.ready ? "green" : "red"}>
                    {chairmanMode.ready ? t("预检查通过", "Pre-check passed") : t("需人工处理", "Human required")}
                  </Badge>
                  <span className="text-[#68738b]">
                    {t("建议", "Recommendation")}：{chairmanMode.recommendation}
                  </span>
                  {chairmanMode.mode === "ai_simulated" ? (
                    <span className="text-amber-700">
                      {t("模拟结论", "Simulated")}：{chairmanMode.simulated_decision}（{t("不构成批准", "not binding")}）
                    </span>
                  ) : null}
                </div>
                <ul className="space-y-1">
                  {(chairmanMode.checks || []).map((c: Record<string, any>) => (
                    <li key={c.key} className={c.ok ? "text-[#68738b]" : c.severity === "block" ? "text-red-600" : "text-amber-700"}>
                      {c.ok ? "✓" : "✕"} {c.label}：{c.detail}
                    </li>
                  ))}
                </ul>
                <div className="flex flex-wrap gap-2 pt-1">
                  <input
                    value={handoverNote}
                    onChange={(e) => setHandoverNote(e.target.value)}
                    placeholder={t("移交备注（可选）", "Handover note (optional)")}
                    className="w-56 rounded-lg border border-[#dde5f2] bg-white px-2 py-2 text-xs outline-none"
                  />
                  <Button
                    variant="ghost"
                    disabled={!!busy}
                    onClick={() =>
                      act("chair-handover", async () => {
                        await instApi(`/proposals/${selectedId}/ai/chairman-handover`, {
                          method: "POST",
                          body: { note: handoverNote },
                        });
                        setHandoverNote("");
                        setChairmanMode(null);
                      })
                    }
                  >
                    {busy === "chair-handover" ? t("移交中…", "Handing over…") : t("人工移交", "Hand over")}
                  </Button>
                </div>
              </div>
            ) : null}
          </Card>

          <Card title={t("授权记录", "Authorizations")} desc={t("授权是不可变快照；撤销写新记录，不覆盖旧记录。", "Authorizations are immutable snapshots; revocation writes a new record.")}>
            {detail.authorizations?.length ? (
              <ul className="space-y-2">
                {detail.authorizations.map((a) => (
                  <li key={a.id} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-[#505369]">{t("授权", "Authorization")} #{a.id}</span>
                      <StatusBadge status={a.status} />
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-[#68738b]">
                      {directionLabel(String(a.snapshot?.direction || detail.direction))} · {t("目标仓位", "Target")}{" "}
                      {fmtPct(a.snapshot?.target_weight ?? detail.target_weight)} · {t("有效期", "Valid until")}{" "}
                      {String(a.snapshot?.valid_until || "—")}
                    </p>
                    <p className="mt-1 text-[10px] text-[#77718c]">
                      {t("签发时间", "Issued at")}：{fmtDateTime(a.issued_at)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <Stamp className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
                {t("尚未生成授权。完成合伙人、Chairman 与风控复核后可生成。", "No authorization yet. Generate it after partner, Chairman and risk reviews.")}
              </Empty>
            )}
          </Card>

          <Card title={t("版本历史", "Version history")}>
            {detail.versions?.length ? (
              <ul className="space-y-2">
                {detail.versions.map((v) => (
                  <li key={v.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-[#68738b]">v{v.version_no}</span>
                    <StatusBadge status={v.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{t("暂无版本记录。", "No version history.")}</Empty>
            )}
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t("审批记录与授权快照写入领域审计；演示环境无真实交易，任何批准都不代表成交。", "Approvals and authorization snapshots are written to the audit trail; demo environment has no real trading and approval is not a fill.")}
      </p>
    </div>
  );
}
