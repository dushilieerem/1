import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Bot, ChevronDown, ChevronUp, ShieldAlert } from "lucide-react";
import { InstApiError, instApi, fmtDateTime, fmtNum, fmtPct } from "@/lib/instApi";
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
  created_at?: string;
  updated_at?: string;
  authorization_id?: number;
  authorization_status?: string;
};

type Dim = {
  key?: string;
  title?: string;
  summary?: string;
  rating?: number | null;
  gate?: string | null;
  status?: string;
  analysis_md?: string;
};

type DebateArgument = {
  side: string;
  claim: string;
  falsifier?: string;
  round?: number;
  evidence_ids?: number[];
};

type ResearchDebate = {
  version_no?: number;
  status?: string;
  industry_analysis?: Dim | null;
  six_dim?: Dim[];
  memo?: Record<string, any> | null;
  debate?: {
    id: number;
    conclusion?: string;
    arguments?: DebateArgument[];
    evidence_checks?: Array<{ claim_id?: string; status?: string }>;
  } | null;
};

type StageSummary = {
  status: string;
  reviewed: number;
  total: number;
  decision?: string | null;
  comment?: string | null;
  conditions?: string[];
  decided_at?: string | null;
  items?: ApprovalItem[];
};

type ApprovalItem = {
  approver_member_id?: number;
  approver_name?: string;
  approver_role?: string;
  decision?: string;
  comment?: string;
  conditions?: string[];
  decided_at?: string;
};

type RiskCheck = {
  key: string;
  label: string;
  value?: string;
  status: string;
};

type ProposalDetail = ProposalListItem & {
  case_id?: number;
  current_version?: { id: number; version_no: number; status: string; snapshot: Record<string, any> };
  progress?: {
    partner: StageSummary;
    risk_precheck: StageSummary;
    chairman: StageSummary;
  };
  research_debate?: ResearchDebate | null;
  risk_checks?: RiskCheck[];
  partner_stage?: StageSummary;
  risk_stage?: StageSummary;
  approval_chain?: ApprovalItem[];
  my_decision?: { decision?: string; comment?: string; conditions?: string[]; decided_at?: string } | null;
  authorization?: { id: number; status: string; issued_at?: string; valid_until?: string } | null;
  exit_case?: { id: number; status: string; case_id?: number; reason_type?: string } | null;
};

const STEP_LABEL: Record<string, [string, string]> = {
  partner: ["合伙人审批", "Partner review"],
  risk_precheck: ["风控审批", "Risk review"],
  chairman: ["Chairman 审批", "Chairman approval"],
};

const DECISION_LABEL: Record<string, [string, string]> = {
  approve: ["通过", "Approve"],
  conditional: ["附条件", "Conditional"],
  return: ["退回", "Return"],
  pass: ["放行", "Pass"],
  veto: ["否决", "Veto"],
  block: ["否决", "Veto"],
  reject: ["拒绝", "Reject"],
};

const REASON_LABEL: Record<string, [string, string]> = {
  thesis_invalid: ["论点失效", "Thesis broken"],
  valuation: ["估值透支", "Valuation stretched"],
  better_allocation: ["更优资本配置", "Better allocation"],
  portfolio_constraint: ["组合/资金约束", "Portfolio constraint"],
  other: ["其他", "Other"],
};

const APPROVER_ROLES = new Set(["partner", "risk", "chairman"]);

export function InstApprovalsPage() {
  const session = useInstSession();
  const { t } = useInstLocale();
  const [params, setParams] = useSearchParams();
  const selectedId = Number(params.get("proposal") || 0);
  const role = session.role;
  const canWrite = (session.permissions.approvals || "none") === "write";
  const isManager = role === "manager";
  const isApprover = APPROVER_ROLES.has(role);

  const [items, setItems] = useState<ProposalListItem[]>([]);
  const [scope, setScope] = useState<"pending" | "reviewed">("pending");
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [conditionsText, setConditionsText] = useState("");
  const [conditionsMet, setConditionsMet] = useState(false);
  const [agentMemo, setAgentMemo] = useState<Record<string, any> | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [agentOpen, setAgentOpen] = useState(true);
  const agentKey = useRef("");

  const stepLabel = (step: string) => {
    const pair = STEP_LABEL[step] || [step, step];
    return t(pair[0], pair[1]);
  };

  const loadList = () => {
    if (!isManager && !isApprover) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    instApi<{ items: ProposalListItem[] }>(`/proposals?scope=${scope}`)
      .then((data) => setItems(data.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const loadDetail = (id: number) => {
    setDetailLoading(true);
    setError(null);
    setDenied(false);
    instApi<ProposalDetail>(`/proposals/${id}`)
      .then((data) => setDetail(data))
      .catch((e: Error) => {
        if (e instanceof InstApiError && e.status === 403) {
          setDenied(true);
          setDetail(null);
        } else {
          setError(e.message);
        }
      })
      .finally(() => setDetailLoading(false));
  };

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
    else setDetail(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, role]);

  // 右侧只放当前角色自己的 Agent，一个角色只放一个。
  const agentPath =
    role === "partner" ? "partner-memo" : role === "risk" ? "risk-review" : role === "chairman" ? "chairman-memo" : "";

  const loadAgent = async (refresh: boolean) => {
    if (!selectedId || !agentPath) return;
    setAgentBusy(true);
    setAgentError(null);
    try {
      const res = refresh
        ? await instApi<{ memo: Record<string, any> }>(`/proposals/${selectedId}/ai/${agentPath}`, {
            method: "POST",
            body: { refresh: true },
          })
        : await instApi<{ memo: Record<string, any> }>(`/proposals/${selectedId}/ai/${agentPath}`);
      setAgentMemo(res.memo);
    } catch (e) {
      setAgentError(e instanceof Error ? e.message : String(e));
    } finally {
      setAgentBusy(false);
    }
  };

  useEffect(() => {
    if (!selectedId || !detail?.current_version?.id || !agentPath) return;
    const key = `${selectedId}:${detail.current_version.id}:${role}`;
    if (agentKey.current === key) return;
    agentKey.current = key;
    setAgentMemo(null);
    setAgentOpen(true);
    void loadAgent(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, detail?.current_version?.id, agentPath, role]);

  const partner = detail?.progress?.partner;
  const risk = detail?.progress?.risk_precheck;
  const chairman = detail?.progress?.chairman;
  const riskVetoed = risk?.status === "vetoed" || Boolean(detail?.risk_stage?.status === "vetoed");
  const canAutoExecute =
    role === "chairman" &&
    detail?.status === "authorized" &&
    partner?.status === "approved" &&
    ["passed", "conditional"].includes(risk?.status || "") &&
    ["approved", "conditional"].includes(chairman?.status || "");
  const conditions = () =>
    conditionsText
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);

  const reload = () => {
    if (selectedId) loadDetail(selectedId);
    loadList();
  };

  const act = async (label: string, fn: () => Promise<unknown>) => {
    if (!selectedId) return;
    setBusy(label);
    setError(null);
    try {
      await fn();
      setComment("");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const requireConditions = (list: string[]) => {
    if (!list.length) {
      setError(t("附条件决策必须填写具体条件（每行一条）。", "Conditional decisions require concrete conditions (one per line)."));
      return false;
    }
    return true;
  };

  const submitPartner = (decision: "approve" | "conditional" | "return") => {
    if (!selectedId) return;
    const list = conditions();
    if (decision === "conditional" && !requireConditions(list)) return;
    void act("partner", () =>
      instApi(`/proposals/${selectedId}/partner`, {
        method: "POST",
        body: { decision, comment, conditions: list },
      }),
    );
  };

  const submitRisk = (decision: "pass" | "conditional" | "veto") => {
    if (!selectedId) return;
    const list = conditions();
    if (decision === "conditional" && !requireConditions(list)) return;
    void act("risk", () =>
      instApi(`/proposals/${selectedId}/risk-check`, {
        method: "POST",
        body: { decision, comment, conditions: list },
      }),
    );
  };

  const submitChairman = (decision: "approve" | "conditional" | "reject" | "return") => {
    if (!selectedId) return;
    const list = conditions();
    if (decision === "conditional" && !requireConditions(list)) return;
    void act("chairman", () =>
      instApi(`/proposals/${selectedId}/chairman`, {
        method: "POST",
        body: { decision, comment, conditions: list },
      }),
    );
  };

  const approveAndExecute = async () => {
    if (!selectedId) return;
    setBusy("execute");
    setError(null);
    try {
      const res = await instApi<{ authorization_id: number }>(
        `/proposals/${selectedId}/approve-and-execute`,
        { method: "POST", body: { conditions_met: conditionsMet } },
      );
      reload();
      setError(
        t(
          `已生成授权 #${res.authorization_id} 并模拟成交，持仓已更新。`,
          `Authorization #${res.authorization_id} created and simulated fill completed.`,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      reload();
    } finally {
      setBusy(null);
    }
  };

  const openProposal = (id: number) => {
    setParams({ proposal: String(id) });
    setComment("");
    setConditionsText("");
    setConditionsMet(false);
    setAgentMemo(null);
    setAgentError(null);
    agentKey.current = "";
  };

  const backToList = () => {
    setParams({});
    setDetail(null);
    setDenied(false);
    loadList();
  };

  if (!isManager && !isApprover) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="APPROVALS / 06" title={t("投委会审批", "IC approvals")} />
        <Empty>
          {t(
            "当前角色没有审批台页面。审批台只提供投资经理（只读）与合伙人、风控、Chairman 四套页面。",
            "This role has no approval workspace. Only the investment manager (read-only), partner, risk and Chairman have approval pages.",
          )}
        </Empty>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <PageHeader
        eyebrow="APPROVALS / 06"
        title={isManager ? t("投委会审批 · 我的议案", "IC approvals · My proposals") : t("投委会审批", "IC approvals")}
        desc={
          isManager
            ? t(
                "只读查看自己提交的议案与三关审批进度；提案人不能审批自己的议案。",
                "Read-only view of your own proposals and the three-stage progress; proposers cannot approve their own proposals.",
              )
            : t(
                "顺序固定：合伙人 → 风控 → Chairman。列表只显示轮到你这一关、且你本人尚未给意见的议案。",
                "Fixed order: partner → risk → Chairman. The list only shows proposals at your stage that you have not yet reviewed.",
              )
        }
        actions={<Badge tone="gold">{session.role_label_cn}</Badge>}
      />

      {error ? <ErrorBox message={error} onRetry={reload} /> : null}

      {!selectedId ? (
        <Card
          title={isManager ? t("我的议案", "My proposals") : t("待审议案", "Pending proposals")}
          desc={
            isManager
              ? t("只显示你本人提交的议案。", "Only proposals you submitted.")
              : t("只显示轮到你这一关、且你本人还没给意见的议案。", "Only proposals at your stage that you have not reviewed.")
          }
          actions={
            isManager ? (
              <Badge tone="slate">{items.length} {t("份", "items")}</Badge>
            ) : (
              <div className="flex gap-1">
                <Button variant={scope === "pending" ? "gold" : "ghost"} onClick={() => setScope("pending")}>
                  {t("待审", "Pending")}
                </Button>
                <Button variant={scope === "reviewed" ? "gold" : "ghost"} onClick={() => setScope("reviewed")}>
                  {t("已审", "Reviewed")}
                </Button>
              </div>
            )
          }
        >
          {loading ? <Loading label={t("正在加载议案…", "Loading proposals…")} /> : null}
          {!loading && !items.length ? (
            <Empty>
              {scope === "reviewed"
                ? t("还没有已审议案。", "No reviewed proposals yet.")
                : t("当前没有待你处理的议案。", "No proposals awaiting your review.")}
            </Empty>
          ) : null}
          {!loading && items.length ? (
            <ul className="divide-y divide-[#eef1f8]">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => openProposal(item.id)}
                    className="flex w-full flex-wrap items-center justify-between gap-3 py-3 text-left transition hover:bg-[#f8faff]"
                  >
                    <div>
                      <p className="text-sm font-semibold text-[#171923]">
                        {item.company_name} <span className="font-mono text-[11px] text-[#68738b]">{item.symbol}</span>
                      </p>
                      <p className="mt-0.5 text-[11px] text-[#77718c]">
                        v{item.version_no ?? "—"} ·{" "}
                        {item.direction === "buy" ? t("买入", "Buy") : item.direction === "sell" ? t("卖出", "Sell") : t("退出", "Exit")}
                        {" · "}
                        {fmtPct(item.target_weight)}
                        {" · "}
                        {t("更新", "Updated")} {fmtDateTime(item.updated_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={item.status} />
                      <span className="text-[11px] text-[#7950ba]">{t("查看", "Open")} →</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : detailLoading ? (
        <Loading label={t("正在加载议案详情…", "Loading proposal…")} />
      ) : denied ? (
        <Card title={t("无权限", "Not permitted")}>
          <p className="text-sm leading-relaxed text-[#505369]">
            {t("该议案不在你当前角色的审批范围。", "This proposal is outside your current role's approval scope.")}
          </p>
          <Button variant="ghost" onClick={backToList}>
            <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回列表", "Back to list")}
          </Button>
        </Card>
      ) : detail ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-4">
            <SummaryBar detail={detail} roleLabel={session.role_label_cn} stepLabel={stepLabel} />
            <ProposalInfo detail={detail} />
            {role === "partner" ? <ResearchDebateCard data={detail.research_debate} /> : null}
            {role === "risk" ? (
              <>
                <RiskChecksCard checks={detail.risk_checks || []} />
                <StageCard title={t("合伙人结论", "Partner conclusion")} stage={detail.partner_stage || partner} step="partner" stepLabel={stepLabel} />
              </>
            ) : null}
            {role === "chairman" ? (
              <>
                <ApprovalChainCard items={detail.approval_chain || []} stepLabel={stepLabel} />
                <StageCard title={t("风控结论", "Risk conclusion")} stage={detail.risk_stage || risk} step="risk_precheck" stepLabel={stepLabel} />
                <ResearchVerdictCard data={detail.research_debate} />
              </>
            ) : null}
            {role === "manager" ? <ManagerProposalNote detail={detail} /> : null}
            {canWrite && !isManager ? (
              <ActionCard
                role={role}
                status={detail.status}
                riskVetoed={riskVetoed}
                busy={busy}
                comment={comment}
                setComment={setComment}
                conditionsText={conditionsText}
                setConditionsText={setConditionsText}
                conditionsMet={conditionsMet}
                setConditionsMet={setConditionsMet}
                conditionsList={(detail.approval_chain || []).flatMap((a) => a.conditions || [])}
                canAutoExecute={canAutoExecute}
                myDecision={detail.my_decision}
                onPartner={submitPartner}
                onRisk={submitRisk}
                onChairman={submitChairman}
                onExecute={() => void approveAndExecute()}
              />
            ) : null}
            {role === "manager" && detail.authorization ? (
              <Card title={t("授权", "Authorization")}>
                <Field label={t("授权编号", "Authorization")} value={`#${detail.authorization.id}`} />
                <Field label={t("授权状态", "Status")} value={<StatusBadge status={detail.authorization.status} />} />
                <Field label={t("有效期", "Valid until")} value={detail.authorization.valid_until || "—"} />
              </Card>
            ) : null}
            <Button variant="ghost" onClick={backToList}>
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回列表", "Back to list")}
            </Button>
          </div>

          <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
            {isManager ? (
              <ProgressCard progress={detail.progress} detail={detail} stepLabel={stepLabel} />
            ) : (
              <AgentCard
                role={role}
                open={agentOpen}
                setOpen={setAgentOpen}
                memo={agentMemo}
                busy={agentBusy}
                error={agentError}
                onRefresh={() => void loadAgent(true)}
                onRetry={() => void loadAgent(false)}
              />
            )}
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function SummaryBar({
  detail,
  roleLabel,
  stepLabel,
}: {
  detail: ProposalDetail;
  roleLabel: string;
  stepLabel: (step: string) => string;
}) {
  const { t } = useInstLocale();
  const stage = detail.status === "authorized" || detail.status === "executed" ? "chairman" : detail.status === "chairman_review" ? "chairman" : detail.status === "risk_precheck" ? "risk_precheck" : "partner";
  return (
    <div className="sticky top-0 z-10 rounded-xl border border-[#dde5f2] bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#171923]">
            {detail.company_name} <span className="font-mono text-[11px] text-[#68738b]">{detail.symbol}</span>
          </p>
          <p className="mt-0.5 text-[11px] text-[#77718c]">
            v{detail.current_version?.version_no ?? detail.version_no ?? "—"} · {t("当前关卡", "Current stage")}：{stepLabel(stage)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={detail.status} />
          <Badge tone="gold">{roleLabel}</Badge>
        </div>
      </div>
    </div>
  );
}

function ProposalInfo({ detail }: { detail: ProposalDetail }) {
  const { t } = useInstLocale();
  const snapshot = detail.current_version?.snapshot || {};
  return (
    <Card title={t("议案详情", "Proposal")} desc={t("投资经理提交时锁死的内容；审批角色只读。", "Locked by the investment manager; read-only for approvers.")}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("方向", "Direction")} value={detail.direction === "buy" ? t("买入", "Buy") : detail.direction === "sell" ? t("卖出", "Sell") : t("退出", "Exit")} />
        <Field label={t("目标仓位", "Target weight")} value={fmtPct(detail.target_weight ?? snapshot.target_weight)} />
        <Field label={t("价格区间", "Price range")} value={`${fmtNum(snapshot.price_low)} – ${fmtNum(snapshot.price_high)}`} />
        <Field label={t("资金来源", "Funding source")} value={String(snapshot.funding_source || t("未指定", "Not specified"))} />
        <Field label={t("有效期", "Valid until")} value={String(snapshot.valid_until || "—")} />
        <Field label={t("议案版本", "Proposal version")} value={`v${detail.current_version?.version_no ?? "—"}`} />
      </div>
      {snapshot.investment_opinion ? (
        <div className="mt-3 rounded-xl border border-[#dde5f2] bg-[#f8faff] p-3 text-xs leading-relaxed text-[#505369]">
          <p className="font-medium text-[#b42345]">{t("投资意见", "Investment opinion")}</p>
          <p className="mt-1 whitespace-pre-wrap">{String(snapshot.investment_opinion)}</p>
        </div>
      ) : null}
      {Array.isArray(snapshot.monitoring) && snapshot.monitoring.length ? (
        <div className="mt-3 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs text-[#505369]">
          <p className="font-medium text-[#b42345]">{t("监控 / 退出条件", "Monitoring / exit conditions")}</p>
          <ul className="mt-1 list-disc pl-4">
            {snapshot.monitoring.map((x: string) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {detail.exit_case ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[#68738b]">
          <Badge tone="amber">
            {t("退出案", "Exit case")} EX-{detail.exit_case.id}
          </Badge>
          {detail.exit_case.reason_type ? (
            <span>
              {t("理由", "Reason")}：{REASON_LABEL[detail.exit_case.reason_type]?.[0] || detail.exit_case.reason_type}
            </span>
          ) : null}
          {detail.exit_case.case_id ? (
            <Link to={`/inst/research?case=${detail.exit_case.case_id}`} className="text-[#7950ba] hover:underline">
              {t("查看退出研究案", "Open exit research case")} →
            </Link>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function ManagerProposalNote({ detail }: { detail: ProposalDetail }) {
  const { t } = useInstLocale();
  const snapshot = detail.current_version?.snapshot || {};
  return (
    <Card title={t("提案人只读", "Read-only proposer view")}>
      <p className="text-xs leading-relaxed text-[#505369]">
        {t(
          "你是提案人，不是审批人。这里只能查看议案信息与三关进度，不能审批自己的议案，也看不到审批角色的工作台、逐项核查和 Agent 建议。需要回看研究/辩论全文，请回价值分析或投资辩论原页面。",
          "You are the proposer, not an approver. You can only view the proposal and the three-stage progress; you cannot approve your own proposal, and you cannot see approver workbenches, itemized checks or agent suggestions. Return to the research or debate pages for the full text.",
        )}
      </p>
      {snapshot.research_version_no ? (
        <p className="mt-2 text-[11px] text-[#77718c]">
          {t("绑定研究版本", "Bound research version")}：v{snapshot.research_version_no}
          {detail.case_id ? (
            <>
              {" · "}
              <Link to={`/inst/research?case=${detail.case_id}`} className="text-[#7950ba] hover:underline">
                {t("回研究页", "Open research")}
              </Link>
            </>
          ) : null}
        </p>
      ) : null}
    </Card>
  );
}

function StageCard({
  title,
  stage,
  step,
  stepLabel,
}: {
  title: string;
  stage?: StageSummary;
  step: string;
  stepLabel: (step: string) => string;
}) {
  const { t } = useInstLocale();
  if (!stage) return null;
  const decided = stage.decision ? DECISION_LABEL[stage.decision] : null;
  return (
    <Card title={title} desc={`${stepLabel(step)} · ${t("已审", "Reviewed")} ${stage.reviewed}/${stage.total}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={stage.status} />
        {decided ? <Badge tone="slate">{t(decided[0], decided[1])}</Badge> : null}
        {stage.decided_at ? <span className="text-[11px] text-[#77718c]">{fmtDateTime(stage.decided_at)}</span> : null}
      </div>
      {stage.comment ? <p className="mt-2 text-xs leading-relaxed text-[#505369]">{stage.comment}</p> : null}
      {stage.conditions?.length ? (
        <div className="mt-2 rounded-lg bg-amber-50 p-2 text-[11px] text-amber-800">
          <span className="font-medium">{t("附加条件", "Conditions")}：</span>
          {stage.conditions.join("；")}
        </div>
      ) : null}
    </Card>
  );
}

function ProgressCard({
  progress,
  detail,
  stepLabel,
}: {
  progress?: ProposalDetail["progress"];
  detail: ProposalDetail;
  stepLabel: (step: string) => string;
}) {
  const { t } = useInstLocale();
  if (!progress) return null;
  const stages: Array<["partner" | "risk_precheck" | "chairman", StageSummary]> = [
    ["partner", progress.partner],
    ["risk_precheck", progress.risk_precheck],
    ["chairman", progress.chairman],
  ];
  return (
    <Card title={t("审批进度", "Approval progress")} desc={t("当前关高亮；后面的关是“还没轮到”，不是“没过”。", "The current stage is highlighted; later stages are not started, not failed.")}>
      <ol className="space-y-3">
        {stages.map(([step, stage]) => {
          const active =
            (detail.status === "draft" || detail.status === "partner_review") && step === "partner"
              ? true
              : detail.status === "risk_precheck" && step === "risk_precheck"
                ? true
                : detail.status === "chairman_review" && step === "chairman"
                  ? true
                  : false;
          return (
            <li
              key={step}
              className={`rounded-xl border px-3 py-2 ${active ? "border-[#b42345] bg-[#fbe9ef]" : "border-[#e3eaf8] bg-white"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-[#252533]">{stepLabel(step)}</span>
                <StatusBadge status={stage.status} />
              </div>
              <p className="mt-1 text-[11px] text-[#77718c]">
                {t("已审", "Reviewed")} {stage.reviewed}/{stage.total}
                {stage.comment ? ` · ${stage.comment}` : ""}
              </p>
              {stage.conditions?.length ? (
                <p className="mt-1 text-[11px] text-amber-700">{t("条件", "Conditions")}：{stage.conditions.join("；")}</p>
              ) : null}
              {stage.decided_at ? <p className="mt-1 text-[10px] text-[#a9a4bd]">{fmtDateTime(stage.decided_at)}</p> : null}
            </li>
          );
        })}
      </ol>
      {detail.authorization ? (
        <p className="mt-3 text-[11px] text-emerald-700">
          {t("授权", "Authorization")} #{detail.authorization.id} · <StatusBadge status={detail.authorization.status} />
          {detail.authorization.valid_until ? ` · ${t("有效期", "valid until")} ${detail.authorization.valid_until}` : ""}
        </p>
      ) : null}
    </Card>
  );
}

function ResearchDebateCard({ data }: { data?: ResearchDebate | null }) {
  const { t } = useInstLocale();
  if (!data) return <Empty>{t("暂无研究与辩论摘要。", "No research or debate summary.")}</Empty>;
  const memo = data.memo || {};
  const industry = data.industry_analysis;
  return (
    <Card title={t("研究与辩论摘要", "Research & debate")} desc={t("行业分析、六维、一页纸与多空裁决；每条可展开看依据。", "Industry, six dimensions, one-pager and debate verdict.")}>
      <div className="space-y-3 text-xs">
        {industry ? (
          <section>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="font-semibold text-[#252533]">{t("行业分析", "Industry")}</h4>
              <div className="flex gap-1">
                {industry.rating != null ? <Badge tone="slate">{t("评级", "Rating")} {industry.rating}/5</Badge> : null}
                {industry.gate ? <Badge tone={industry.gate === "fail" ? "red" : industry.gate === "watch" ? "amber" : "green"}>{industry.gate}</Badge> : null}
              </div>
            </div>
            <p className="mt-1 leading-relaxed text-[#505369]">{industry.summary || t("待补充", "TBD")}</p>
            {industry.analysis_md ? (
              <details className="mt-2 rounded-lg border border-[#e3eaf8] bg-[#f8faff] px-3 py-2">
                <summary className="cursor-pointer text-[11px] text-[#7950ba]">{t("展开行业分析全文", "Full industry analysis")}</summary>
                <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-[#505369]">{industry.analysis_md}</div>
              </details>
            ) : null}
          </section>
        ) : null}

        {data.six_dim?.length ? (
          <section>
            <h4 className="font-semibold text-[#252533]">{t("六维结论", "Six dimensions")}</h4>
            <ul className="mt-1 space-y-1">
              {data.six_dim.map((dim) => (
                <li key={dim.key || dim.title} className="rounded-lg border border-[#e3eaf8] px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-[#505369]">{dim.title || dim.key}</span>
                    <div className="flex gap-1">
                      {dim.rating != null ? <Badge tone="slate">{dim.rating}/5</Badge> : null}
                      {dim.gate ? <Badge tone={dim.gate === "fail" ? "red" : dim.gate === "watch" ? "amber" : "green"}>{dim.gate}</Badge> : null}
                    </div>
                  </div>
                  <p className="mt-1 leading-relaxed text-[#68738b]">{dim.summary || "—"}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {memo.summary ? (
          <section>
            <h4 className="font-semibold text-[#252533]">{t("一页纸裁决", "One-pager")}</h4>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {memo.decision ? (
                <Badge tone={memo.decision === "proceed" ? "green" : memo.decision === "avoid" ? "red" : "amber"}>
                  {memo.decision === "proceed" ? t("推进", "Proceed") : memo.decision === "avoid" ? t("回避", "Avoid") : t("观察", "Watch")}
                </Badge>
              ) : null}
              {memo.price_range ? (
                <span className="font-mono text-[11px] text-[#68738b]">
                  {fmtNum(memo.price_range.low)} – {fmtNum(memo.price_range.high)}
                </span>
              ) : null}
            </div>
            <p className="mt-1 leading-relaxed text-[#505369]">{memo.summary}</p>
            {memo.memo_md ? (
              <details className="mt-2 rounded-lg border border-[#e3eaf8] bg-[#f8faff] px-3 py-2">
                <summary className="cursor-pointer text-[11px] text-[#7950ba]">{t("展开一页纸全文", "Full one-pager")}</summary>
                <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-[#505369]">{memo.memo_md}</div>
              </details>
            ) : null}
          </section>
        ) : null}

        {data.debate ? (
          <section>
            <h4 className="font-semibold text-[#252533]">{t("多空辩论与主持裁决", "Bull / bear debate")}</h4>
            {data.debate.conclusion ? <p className="mt-1 leading-relaxed text-[#505369]">{data.debate.conclusion}</p> : null}
            <ul className="mt-2 space-y-1">
              {(data.debate.arguments || []).map((arg, index) => (
                <li key={`${arg.side}-${index}`} className="rounded-lg border border-[#e3eaf8] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone={arg.side === "bull" ? "green" : arg.side === "bear" ? "red" : "gold"}>
                      {arg.side === "bull" ? t("多头", "Bull") : arg.side === "bear" ? t("空头", "Bear") : t("主持", "Chair")}
                    </Badge>
                    <span className="text-[10px] text-[#a9a4bd]">{t("第", "Round")} {arg.round ?? 1} {t("轮", "")}</span>
                  </div>
                  <p className="mt-1 leading-relaxed text-[#505369]">{arg.claim}</p>
                  {arg.falsifier ? <p className="mt-1 text-[11px] text-amber-700">{t("证伪", "Falsifier")}：{arg.falsifier}</p> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </Card>
  );
}

function RiskChecksCard({ checks }: { checks: RiskCheck[] }) {
  const { t } = useInstLocale();
  return (
    <Card title={t("六项硬约束核查", "Six hard checks")} desc={t("任何一项否决，本议案即时终止，Chairman 也不能批准。", "Any veto terminates the proposal; Chairman cannot override it.")}>
      {checks.length ? (
        <ul className="space-y-2 text-xs">
          {checks.map((check) => (
            <li key={check.key} className="rounded-lg border border-[#e3eaf8] px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-[#505369]">{check.label}</span>
                <StatusBadge status={check.status} />
              </div>
              {check.value ? <p className="mt-1 leading-relaxed text-[#68738b]">{check.value}</p> : null}
            </li>
          ))}
        </ul>
      ) : (
        <Empty>{t("暂无风控检查结果。", "No risk checks available.")}</Empty>
      )}
    </Card>
  );
}

function ApprovalChainCard({ items, stepLabel }: { items: ApprovalItem[]; stepLabel: (step: string) => string }) {
  const { t } = useInstLocale();
  const groups = useMemo(() => {
    const out: Record<string, ApprovalItem[]> = { partner: [], risk_precheck: [], chairman: [] };
    for (const item of items) {
      const role = String(item.approver_role || "");
      const step = role === "partner" ? "partner" : role === "risk" ? "risk_precheck" : role === "chairman" ? "chairman" : "partner";
      out[step].push(item);
    }
    return out;
  }, [items]);
  return (
    <Card title={t("完整审批链", "Approval chain")} desc={t("按人列出前两关结论、时间与条件；风控否决不可被 Chairman 越过。", "Per-approver decisions, timing and conditions; a risk veto cannot be overridden.")}>
      <div className="space-y-3">
        {(Object.keys(groups) as Array<keyof typeof groups>).map((step) => (
          <div key={step} className="rounded-xl border border-[#e3eaf8] px-3 py-2">
            <p className="text-xs font-semibold text-[#252533]">{stepLabel(step)}</p>
            {groups[step].length ? (
              <ul className="mt-1 space-y-2">
                {groups[step].map((item, index) => (
                  <li key={`${step}-${item.approver_member_id}-${index}`} className="text-[11px] leading-relaxed text-[#505369]">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">
                        {item.approver_name || item.approver_role || t("审批人", "Approver")}
                        {item.approver_role && item.approver_name ? ` · ${item.approver_role}` : ""}
                      </span>
                      <StatusBadge status={item.decision || "pending"} />
                    </div>
                    {item.comment ? <p className="mt-1 text-[#68738b]">{item.comment}</p> : null}
                    {item.conditions?.length ? (
                      <p className="mt-1 rounded bg-amber-50 px-2 py-1 text-amber-800">
                        {t("条件", "Conditions")}：{item.conditions.join("；")}
                      </p>
                    ) : null}
                    {item.decided_at ? <p className="mt-1 text-[10px] text-[#a9a4bd]">{fmtDateTime(item.decided_at)}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[11px] text-[#77718c]">{t("尚未处理", "Pending")}</p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function ResearchVerdictCard({ data }: { data?: ResearchDebate | null }) {
  const { t } = useInstLocale();
  if (!data) return <Empty>{t("暂无研究与辩论裁决。", "No research or debate verdict.")}</Empty>;
  const memo = data.memo || {};
  const chair = (data.debate?.arguments || []).filter((a) => a.side === "chair");
  return (
    <Card title={t("研究与辩论裁决", "Research & debate verdict")} desc={t("Chairman 看裁决与关键分歧；完整研究回原页面查看。", "Chairman sees the verdict and key disagreement; full research lives on the original pages.")}>
      <div className="space-y-2 text-xs leading-relaxed text-[#505369]">
        {memo.summary ? <p>{memo.summary}</p> : null}
        {memo.risks?.length ? (
          <div>
            <p className="font-medium text-[#252533]">{t("主要风险", "Key risks")}</p>
            <ul className="mt-1 list-disc pl-4">
              {memo.risks.map((x: string) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {data.debate?.conclusion ? (
          <p>
            <span className="font-medium text-[#252533]">{t("主持裁决", "Chair verdict")}：</span>
            {data.debate.conclusion}
          </p>
        ) : null}
        {chair.length ? (
          <ul className="list-disc pl-4">
            {chair.map((arg, index) => (
              <li key={index}>{arg.claim}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </Card>
  );
}

function AgentCard({
  role,
  open,
  setOpen,
  memo,
  busy,
  error,
  onRefresh,
  onRetry,
}: {
  role: string;
  open: boolean;
  setOpen: (v: boolean) => void;
  memo: Record<string, any> | null;
  busy: boolean;
  error: string | null;
  onRefresh: () => void;
  onRetry: () => void;
}) {
  const { t } = useInstLocale();
  const title =
    role === "partner"
      ? t("合伙人 Agent · 审批建议", "Partner Agent · review")
      : role === "risk"
        ? t("风控 Agent · 审批建议", "Risk Agent · review")
        : t("Chairman Agent · 决策建议", "Chairman Agent · decision");
  const tone = memo?.decision === "reject" || memo?.verdict === "block" || memo?.verdict === "veto" ? "red" : memo?.decision === "conditional" ? "amber" : "green";
  return (
    <Card
      title={title}
      desc={t("只放当前角色的 Agent 建议，不替代你的独立判断。", "Only your role's agent suggestion; not a substitute for independent judgment.")}
      actions={
        <div className="flex gap-1">
          <Button variant="ghost" disabled={busy} onClick={onRefresh}>
            <Bot className="mr-1 h-3.5 w-3.5" />
            {busy ? t("生成中…", "Generating…") : t("重新生成", "Regenerate")}
          </Button>
          <Button variant="ghost" onClick={() => setOpen(!open)}>
            {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </Button>
        </div>
      }
    >
      {open ? (
        <div className="space-y-2 text-xs leading-relaxed text-[#505369]">
          {error ? (
            <div>
              <p className="text-amber-700">{error}</p>
              <Button variant="ghost" onClick={onRetry}>
                {t("重试", "Retry")}
              </Button>
            </div>
          ) : null}
          {!error && !memo ? <p className="text-[#77718c]">{busy ? t("Agent 生成中…", "Agent is generating…") : t("暂无建议。", "No suggestion yet.")}</p> : null}
          {memo ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                {memo.decision || memo.verdict ? <Badge tone={tone}>{String(memo.decision || memo.verdict)}</Badge> : null}
                {memo.stale ? <Badge tone="amber">{t("已持久化", "Persisted")}</Badge> : null}
                {memo.engine === "rule" ? <Badge tone="slate">{t("规则兜底", "Rule fallback")}</Badge> : null}
              </div>
              <p className="whitespace-pre-wrap">{memo.summary || memo.reason || t("待补充", "TBD")}</p>
              {Array.isArray(memo.risks) && memo.risks.length ? (
                <div>
                  <p className="font-medium text-[#252533]">{t("关注点", "Concerns")}</p>
                  <ul className="mt-1 list-disc pl-4">
                    {memo.risks.map((x: string) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {Array.isArray(memo.conditions) && memo.conditions.length ? (
                <div>
                  <p className="font-medium text-[#252533]">{t("建议条件", "Suggested conditions")}</p>
                  <ul className="mt-1 list-disc pl-4">
                    {memo.conditions.map((x: any, index: number) => (
                      <li key={index}>{typeof x === "string" ? x : x.text || JSON.stringify(x)}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {Array.isArray(memo.open_questions) && memo.open_questions.length ? (
                <p>
                  <span className="font-medium">{t("数据缺口 / 待核验", "Data gaps / to verify")}：</span>
                  {memo.open_questions.join("；")}
                </p>
              ) : null}
            </>
          ) : null}
          <p className="pt-1 text-[10px] text-[#a9a4bd]">{t("仅供参考，不替代你的独立判断。", "For reference only; not a substitute for your independent judgment.")}</p>
        </div>
      ) : null}
    </Card>
  );
}

function ActionCard({
  role,
  status,
  riskVetoed,
  busy,
  comment,
  setComment,
  conditionsText,
  setConditionsText,
  conditionsMet,
  setConditionsMet,
  conditionsList,
  canAutoExecute,
  myDecision,
  onPartner,
  onRisk,
  onChairman,
  onExecute,
}: {
  role: string;
  status: string;
  riskVetoed: boolean;
  busy: string | null;
  comment: string;
  setComment: (v: string) => void;
  conditionsText: string;
  setConditionsText: (v: string) => void;
  conditionsMet: boolean;
  setConditionsMet: (v: boolean) => void;
  conditionsList: string[];
  canAutoExecute: boolean;
  myDecision?: { decision?: string; comment?: string; conditions?: string[]; decided_at?: string } | null;
  onPartner: (decision: "approve" | "conditional" | "return") => void;
  onRisk: (decision: "pass" | "conditional" | "veto") => void;
  onChairman: (decision: "approve" | "conditional" | "reject" | "return") => void;
  onExecute: () => void;
}) {
  const { t } = useInstLocale();
  const partnerActive =
    role === "partner" && ["draft", "partner_review"].includes(status) && !myDecision;
  const riskActive =
    role === "risk" && ["risk_precheck", "chairman_review"].includes(status) && !myDecision;
  const chairmanActive =
    role === "chairman" && status === "chairman_review" && !riskVetoed && !myDecision;
  const showActions = partnerActive || riskActive || chairmanActive || (canAutoExecute && role === "chairman");
  if (!showActions) {
    return status === "executed" ? (
      <Card title={t("已执行", "Executed")}>
        <p className="text-xs text-emerald-700">{t("该议案已批准并模拟成交，持仓已更新。", "Approved and simulated-filled; positions updated.")}</p>
      </Card>
    ) : status === "frozen" ? (
      <Card title={t("风控否决", "Risk veto")}>
        <p className="flex items-start gap-2 text-xs text-red-700">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {t("独立风控已否决，议案终止；Chairman 不能批准。", "Risk has vetoed this proposal; Chairman cannot approve.")}
        </p>
      </Card>
    ) : null;
  }
  return (
    <Card title={t("操作区", "Actions")} desc={t("按钮只在这里出现一次；点了会发生什么写在按钮旁。", "Actions appear only once here; the effect is described next to each button.")}>
      <label className="block text-xs text-[#68738b]">
        {t("审批意见", "Comment")}
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className="mt-1 min-h-[72px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
          placeholder={t("写清依据、关注点和结论。", "State your basis, concerns and conclusion.")}
        />
      </label>
      <label className="mt-2 block text-xs text-[#68738b]">
        {t("附加条件（附条件时必填，每行一条）", "Conditions (required for conditional decisions, one per line)")}
        <textarea
          value={conditionsText}
          onChange={(e) => setConditionsText(e.target.value)}
          className="mt-1 min-h-[56px] w-full rounded-lg border border-[#dde5f2] bg-white p-2 text-xs outline-none focus:border-[#7950ba]"
          placeholder={t("例如：现价回到区间内才可执行", "e.g. execute only within the price band")}
        />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        {partnerActive ? (
          <>
            <Button variant="gold" disabled={!!busy} onClick={() => onPartner("approve")}>
              {busy === "partner" ? t("提交中…", "Submitting…") : t("复核通过", "Approve")}
            </Button>
            <Button variant="primary" disabled={!!busy} onClick={() => onPartner("conditional")}>
              {t("附条件", "Conditional")}
            </Button>
            <Button variant="danger" disabled={!!busy} onClick={() => onPartner("return")}>
              {t("退回", "Return")}
            </Button>
          </>
        ) : null}
        {riskActive ? (
          <>
            {status === "risk_precheck" ? (
              <>
                <Button variant="gold" disabled={!!busy} onClick={() => onRisk("pass")}>
                  {busy === "risk" ? t("提交中…", "Submitting…") : t("放行", "Pass")}
                </Button>
                <Button variant="primary" disabled={!!busy} onClick={() => onRisk("conditional")}>
                  {t("有条件放行", "Conditional pass")}
                </Button>
              </>
            ) : null}
            <Button variant="danger" disabled={!!busy} onClick={() => onRisk("veto")}>
              {t("否决", "Veto")}
            </Button>
          </>
        ) : null}
        {chairmanActive ? (
          <>
            <Button variant="gold" disabled={!!busy} onClick={() => onChairman("approve")}>
              {busy === "chairman" ? t("提交中…", "Submitting…") : t("批准", "Approve")}
            </Button>
            <Button variant="primary" disabled={!!busy} onClick={() => onChairman("conditional")}>
              {t("附条件批准", "Conditional approve")}
            </Button>
            <Button variant="danger" disabled={!!busy} onClick={() => onChairman("reject")}>
              {t("拒绝", "Reject")}
            </Button>
            <Button variant="danger" disabled={!!busy} onClick={() => onChairman("return")}>
              {t("退回", "Return")}
            </Button>
          </>
        ) : null}
        {canAutoExecute ? (
          <>
            {conditionsList.length ? (
              <label className="flex items-center gap-2 text-[11px] text-[#505369]">
                <input type="checkbox" checked={conditionsMet} onChange={(e) => setConditionsMet(e.target.checked)} />
                {t("确认附加条件已满足", "Conditions satisfied")}
              </label>
            ) : null}
            <Button
              variant="gold"
              disabled={!!busy || (conditionsList.length > 0 && !conditionsMet)}
              onClick={onExecute}
            >
              {busy === "execute" ? t("成交中…", "Executing…") : t("确认并模拟成交", "Confirm & simulate fill")}
            </Button>
          </>
        ) : null}
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#77718c]">
        {t(
          "退回=打回上游补材料；否决/拒绝=终局；附条件=带条件进入下一关，执行前会校验。",
          "Return sends it upstream; veto/reject is final; conditional moves forward with conditions checked before execution.",
        )}
      </p>
    </Card>
  );
}
