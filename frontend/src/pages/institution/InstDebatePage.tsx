import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, MessagesSquare, Play } from "lucide-react";
import { instApi } from "@/lib/instApi";
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

type CaseItem = {
  id: number;
  company_name: string;
  symbol: string;
  stage: string;
  versions?: Array<{ id: number; status: string; version_no: number }>;
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
};

export function InstDebatePage() {
  const session = useInstSession();
  const { t } = useInstLocale();
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

  const canWrite = (session.permissions.debate || "none") === "write";

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
        <Loading label="正在加载辩论…" />
      </div>
    );
  }

  if (!caseId) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader
          eyebrow="DEBATE / 04"
          title={t("投资辩论室", "Investment debate")}
          desc={t("研究与辩论分离：先有已审核通过的研究版本，才能开始正反方独立立论与交叉质询。", "Research and debate are separate: an approved research version is required before independent bull/bear arguments and cross-examination.")}
        />
        {error ? <ErrorBox message={error} onRetry={loadCases} /> : null}
        {cases.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {cases.map((c) => (
              <Link
                key={c.id}
                to={`/inst/debate?case=${c.id}`}
                className="rounded-2xl border border-[#e7e3d8] bg-white p-5 transition hover:border-[#c9a15e]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-base font-semibold text-slate-900">{c.company_name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-slate-500">{c.symbol}</p>
                  </div>
                  <StatusBadge status={c.stage} />
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  {c.debates?.length ? t(`已有 ${c.debates.length} 场辩论`, `${c.debates.length} debate(s)`) : t("尚未开始辩论", "No debate yet")}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <Empty>
            <MessagesSquare className="mx-auto mb-2 h-6 w-6 text-slate-300" />
            还没有研究案。先从「机会发现」进入研究。
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="DEBATE / 04" title={t("投资辩论室", "Investment debate")} />
        <ErrorBox message={error || "研究案不存在"} onRetry={() => loadDetail(caseId)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="DEBATE / 04"
        title={t(`${detail.company_name} · 投资辩论`, `${detail.company_name} · Investment debate`)}
        desc={`${detail.symbol} · ${t("正反方独立立论，保留未解决异议；结论只做流程建议，不生成订单。", "Independent bull/bear arguments, with unresolved dissent retained. Conclusions are process suggestions only and never create orders.")}`}
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
          <p className="text-sm text-slate-600">
            研究审核尚未通过，不能进入辩论。请先在研究页确认研究成果。
          </p>
        </Card>
      ) : !debate ? (
        <Card
          title={t("开始辩论", "Start debate")}
          desc={t(`研究 v${approvedVersion.version_no} 已审核通过；开始后将生成正反方论点与主持结论。`, `Research v${approvedVersion.version_no} is approved. Starting will generate bull/bear arguments and the chair conclusion.`)}
        >
          <Button variant="gold" disabled={!canWrite || busy} onClick={start}>
            <Play className="mr-1 h-4 w-4" />
            {busy ? t("辩论生成中…", "Generating…") : t("开始两轮辩论", "Start two-round debate")}
          </Button>
          <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
            论点必须引用证据 ID；AI 不可用时使用规则模板并标注。辩论不产生买卖建议。
          </p>
        </Card>
      ) : (
        <>
          <Card
            title={t("辩论记录", "Debate record")}
            desc={`场次 #${debate.id} · 状态 ${debate.status} · FactPack ${String(debate.factpack_hash || "").slice(0, 12)}…`}
            actions={<StatusBadge status={debate.status} />}
          >
            <div className="mb-4 rounded-xl border border-[#c9a15e]/30 bg-[#fbf6ea] px-4 py-3 text-sm text-[#8a6a2f]">
              {t("主持结论", "Chair conclusion")}：<b>{debate.conclusion || t("待定", "TBD")}</b>
              <span className="ml-2 text-[11px]">（流程建议，不构成投资建议）</span>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {[
                { key: "bull", title: t("正方 · 看多", "Bull case"), tone: "green" as const, items: groups.bull },
                { key: "bear", title: t("反方 · 看空", "Bear case"), tone: "red" as const, items: groups.bear },
              ].map((col) => (
                <div key={col.key} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">{col.title}</h3>
                    <Badge tone={col.tone}>{col.items.length} 条</Badge>
                  </div>
                  {col.items.length ? (
                    <ul className="space-y-3">
                      {col.items.map((a) => (
                        <li key={a.id} className="rounded-lg border border-white bg-white p-3">
                          <div className="flex items-center justify-between gap-2">
                            <Badge>第 {a.round} 轮</Badge>
                            <span className="font-mono text-[10px] text-slate-400">
                              置信度 {a.confidence?.toFixed?.(2) ?? "—"}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-relaxed text-slate-700">{a.claim}</p>
                          {a.evidence_ids?.length ? (
                            <p className="mt-2 font-mono text-[10px] text-slate-400">
                              证据：{a.evidence_ids.join(", ")}
                            </p>
                          ) : (
                            <p className="mt-2 text-[10px] text-amber-600">无有效证据引用，不计入裁决</p>
                          )}
                          {a.falsifier ? (
                            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                              可证伪条件：{a.falsifier}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <Empty>该方暂无有效论点。</Empty>
                  )}
                </div>
              ))}
            </div>
          </Card>

          <Card title={t("主持与裁决", "Chair & ruling")} desc={t("主持只做流程建议：推进审议 / 补充研究 / 继续观察 / 拒绝。", "The chair only recommends: proceed / supplement research / keep watching / reject.")}>
            {groups.chair.length ? (
              <ul className="space-y-2">
                {groups.chair.map((a) => (
                  <li key={a.id} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-3 text-xs leading-relaxed text-slate-700">
                    {a.claim}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>暂无主持记录。</Empty>
            )}
            <div className="mt-4 flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-slate-500">
                目标仓位
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  className="ml-2 w-24 rounded-lg border border-[#dcd6c8] bg-white px-2 py-1.5 text-xs text-slate-800 outline-none"
                  placeholder="0.05"
                />
              </label>
              <Button
                variant="primary"
                disabled={!canWrite || busy || proposalBusy}
                onClick={async () => {
                  setProposalBusy(true);
                  setError(null);
                  try {
                    const res = await instApi<{ id: number }>(`/cases/${caseId}/proposals`, {
                      method: "POST",
                      body: {
                        direction: "buy",
                        target_weight: Number(target) || 0.05,
                        config: { price_low: null, price_high: null },
                      },
                    });
                    nav(`/inst/approvals?proposal=${res.id}`);
                  } catch (e) {
                    setError(e instanceof Error ? e.message : String(e));
                  } finally {
                    setProposalBusy(false);
                  }
                }}
              >
                {proposalBusy ? t("创建中…", "Creating…") : t("创建议案", "Create proposal")}
              </Button>
              <Button variant="ghost" onClick={() => nav("/inst/debate")}>
                {t("返回辩论列表", "Back to debate list")}
              </Button>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
              {t("创建议案后进入合伙人复核 → Chairman 审批 → 执行前风控 → 授权。任何一步拒绝都不能跳级。", "A proposal then goes through partner review → Chairman approval → pre-execution risk check → authorization. No step can be skipped.")}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
