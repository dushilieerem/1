import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BadgeCheck, ShieldAlert, Stamp } from "lucide-react";
import { instApi, fmtNum, fmtPct } from "@/lib/instApi";
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

type ProposalDetail = ProposalListItem & {
  current_version?: { id: number; version_no: number; status: string; snapshot: Record<string, any> };
  versions?: Array<{ id: number; version_no: number; status: string; snapshot: Record<string, any> }>;
  approvals?: Approval[];
  authorizations?: Array<{ id: number; status: string; issued_at: string; snapshot: Record<string, any> }>;
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

export function InstApprovalsPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const stepLabel = (step: string) => (locale === "en" ? STEP_LABEL_EN[step] : STEP_LABEL_ZH[step]) || step;
  const [params, setParams] = useSearchParams();
  const selectedId = Number(params.get("proposal") || 0);
  const [items, setItems] = useState<ProposalListItem[]>([]);
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [target, setTarget] = useState("");
  const [memo, setMemo] = useState<Record<string, any> | null>(null);

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

  const approvalMap = useMemo(() => {
    const map = new Map<string, Approval>();
    for (const a of detail?.approvals || []) map.set(a.step, a);
    return map;
  }, [detail]);

  const canAuthorize =
    approvalMap.get("partner")?.decision === "approve" &&
    ["approve", "conditional"].includes(approvalMap.get("chairman")?.decision || "") &&
    approvalMap.get("risk_precheck")?.decision === "pass";

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

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="APPROVALS / 06" title={t("投委会与审批", "IC & approvals")} />
        <Loading label="正在加载议案…" />
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
                className="w-full rounded-2xl border border-[#e7e3d8] bg-white p-5 text-left transition hover:border-[#c9a15e]"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-display text-base font-semibold text-slate-900">{p.company_name}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                      #{p.id} · {p.symbol} · {p.direction === "buy" ? "买入" : p.direction === "sell" ? "卖出" : "退出"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="gold">目标 {fmtPct(p.target_weight)}</Badge>
                    <StatusBadge status={p.status} />
                    {p.authorization_status ? <StatusBadge status={p.authorization_status} /> : null}
                  </div>
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  当前版本 v{p.version_no || 1} · 点击进入审批详情
                </p>
              </button>
            ))}
          </div>
        ) : (
          <Empty>
            <BadgeCheck className="mx-auto mb-2 h-6 w-6 text-slate-300" />
            还没有议案。完成研究与辩论后，经理可在议案页创建。
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="APPROVALS / 06" title={t("议案详情", "Proposal")} />
        <ErrorBox message={error || "议案不存在"} onRetry={() => loadDetail(selectedId)} />
      </div>
    );
  }

  const snapshot = detail.current_version?.snapshot || {};

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="APPROVALS / 06"
        title={`${detail.company_name} · 议案 #${detail.id}`}
        desc={`${detail.symbol} · ${detail.direction === "buy" ? t("买入", "Buy") : detail.direction === "sell" ? t("卖出", "Sell") : t("退出", "Exit")} · ${t("当前版本", "Current version")} v${detail.current_version?.version_no || 1}`}
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

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <Card title={t("议案快照", "Proposal snapshot")} desc={t("授权绑定研究版本、议案版本、配置、批准人与有效期。", "Authorization binds research version, proposal version, configuration, approver and validity.")}>
            <div className="grid gap-x-6 sm:grid-cols-2">
              <Field label="议案版本" value={`v${detail.current_version?.version_no || 1}`} />
              <Field label="研究版本" value={String(snapshot.research_version_no || snapshot.research_version_id || "—")} />
              <Field label="方向" value={detail.direction} />
              <Field label="目标仓位" value={fmtPct(snapshot.target_weight ?? detail.target_weight)} />
              <Field label="价格区间" value={`${fmtNum(snapshot.price_low, 2)} - ${fmtNum(snapshot.price_high, 2)}`} />
              <Field label="账户" value={String(snapshot.account || "—")} />
              <Field label="币种 / 汇率" value={`${snapshot.currency || "CNY"} / ${snapshot.fx_rate ?? "—"}`} />
              <Field label="有效期" value={String(snapshot.valid_until || "—")} />
            </div>
            {Array.isArray(snapshot.monitoring) && snapshot.monitoring.length ? (
              <div className="mt-3 rounded-xl border border-[#c9a15e]/30 bg-[#fbf6ea] p-3 text-xs text-[#8a6a2f]">
                <p className="font-medium">监控条件</p>
                <ul className="mt-1 list-disc pl-4">
                  {snapshot.monitoring.map((x: string) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>

          <Card title={t("审批链", "Approval chain")} desc={t("职责分离：提案人不得批准自己的议案；风控否决终局。", "Separation of duties: proposers cannot approve their own proposal; risk veto is final.")}>
            <div className="space-y-3">
              {(["partner", "chairman", "risk_precheck"] as const).map((step) => {
                const a = approvalMap.get(step);
                return (
                  <div key={step} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[#f0ece2] bg-[#faf9f5] px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-800">{stepLabel(step)}</p>
                      <p className="mt-1 text-xs text-slate-500">{a?.comment || "尚未处理"}</p>
                      {a?.decided_at ? <p className="mt-1 text-[10px] text-slate-400">{a.decided_at}</p> : null}
                    </div>
                    <StatusBadge status={a?.decision || "pending"} />
                  </div>
                );
              })}
            </div>

            {canWrite ? (
              <div className="mt-4 space-y-3 rounded-xl border border-[#f0ece2] p-4">
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="审批意见（通过/拒绝/退回均建议填写）"
                  className="min-h-[72px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
                />
                <div className="flex flex-wrap gap-2">
                  {role === "partner" ? (
                    <>
                      <input
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                        placeholder="目标仓位，如 0.05"
                        className="w-36 rounded-lg border border-[#dcd6c8] bg-white px-2 py-2 text-xs outline-none"
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
                              body: { decision: "return", comment: comment || "退回补充" },
                            }),
                          )
                        }
                      >
                        退回
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
                              body: { decision: "reject", comment: comment || "不同意" },
                            }),
                          )
                        }
                      >
                        拒绝
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
                            body: { comment: comment || "执行前风控复核" },
                          }),
                        )
                      }
                    >
                      {busy === "risk" ? t("复核中…", "Checking…") : t("执行前风控复核", "Pre-execution risk check")}
                    </Button>
                  ) : null}

                  {canAuthorize ? (
                    <Button
                      variant="gold"
                      disabled={!!busy}
                      onClick={() =>
                        act("authorize", () =>
                          instApi(`/proposals/${selectedId}/authorize`, { method: "POST" }),
                        )
                      }
                    >
                      {busy === "authorize" ? t("生成中…", "Creating…") : t("生成授权快照", "Create authorization")}
                    </Button>
                  ) : null}
                </div>
                <p className="text-[11px] leading-relaxed text-slate-400">
                  角色校验在服务端执行；按钮显隐只是展示。风控阻断后 Chairman 不能批准。
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
                  <li key={a.id} className="flex items-center justify-between gap-2 rounded-lg border border-[#f0ece2] px-3 py-2">
                    <span className="text-slate-600">{stepLabel(a.step)}</span>
                    <StatusBadge status={a.decision} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>尚未产生审批记录。</Empty>
            )}
            {detail.approvals?.some((a) => a.decision === "block" || a.decision === "veto") ? (
              <p className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-[11px] text-red-700">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                风控已阻断。需整改并由独立风控重新核验，Chairman 不能绕过。
              </p>
            ) : null}
          </Card>

          <Card title={t("AI 审议辅助", "AI review support")} desc={t("AI 只读议案、审批与风控检查，不改变状态；不提供目标价或买卖指令。", "AI only reads the proposal, approvals and risk checks; it never changes state or gives target prices/trade instructions.")}>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="ghost"
                disabled={!!busy}
                onClick={() =>
                  act("ai-risk", async () => {
                    const res = await instApi<{ memo: Record<string, any> }>(
                      `/proposals/${selectedId}/ai/risk-review`,
                      { method: "POST" },
                    );
                    setMemo(res.memo);
                  })
                }
              >
                {busy === "ai-risk" ? t("生成中…", "Generating…") : t("AI 风控意见", "AI risk opinion")}
              </Button>
              <Button
                variant="ghost"
                disabled={!!busy}
                onClick={() =>
                  act("ai-chair", async () => {
                    const res = await instApi<{ memo: Record<string, any> }>(
                      `/proposals/${selectedId}/ai/chairman-memo`,
                      { method: "POST" },
                    );
                    setMemo(res.memo);
                  })
                }
              >
                {busy === "ai-chair" ? t("生成中…", "Generating…") : t("AI Chairman 摘要", "AI Chairman memo")}
              </Button>
            </div>
            {memo ? (
              <div className="mt-3 rounded-xl border border-[#c9a15e]/30 bg-[#fbf6ea] p-3 text-xs leading-relaxed text-[#8a6a2f]">
                <p className="font-medium">AI 摘要（非投资建议，需真人确认）</p>
                <p className="mt-1">{memo.summary || "—"}</p>
                {Array.isArray(memo.risks) && memo.risks.length ? (
                  <ul className="mt-2 list-disc pl-4">
                    {memo.risks.map((x: string) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                ) : null}
                {Array.isArray(memo.open_questions) && memo.open_questions.length ? (
                  <p className="mt-2">待核验：{memo.open_questions.join("；")}</p>
                ) : null}
              </div>
            ) : null}
          </Card>

          <Card title={t("授权记录", "Authorizations")} desc={t("授权是不可变快照；撤销写新记录，不覆盖旧记录。", "Authorizations are immutable snapshots; revocation writes a new record.")}>
            {detail.authorizations?.length ? (
              <ul className="space-y-2">
                {detail.authorizations.map((a) => (
                  <li key={a.id} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs text-slate-700">AUTH-{a.id}</span>
                      <StatusBadge status={a.status} />
                    </div>
                    <p className="mt-1 text-[10px] text-slate-400">{a.issued_at}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <Stamp className="mx-auto mb-2 h-6 w-6 text-slate-300" />
                尚未生成授权。完成合伙人、Chairman 与风控复核后可生成。
              </Empty>
            )}
          </Card>

          <Card title={t("版本历史", "Version history")}>
            {detail.versions?.length ? (
              <ul className="space-y-2">
                {detail.versions.map((v) => (
                  <li key={v.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-slate-600">v{v.version_no}</span>
                    <StatusBadge status={v.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>暂无版本记录。</Empty>
            )}
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-slate-400">
        审批记录与授权快照写入领域审计；演示环境无真实交易，任何批准都不代表成交。
      </p>
    </div>
  );
}
