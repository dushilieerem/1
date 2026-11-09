import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, ShieldAlert, X } from "lucide-react";
import { instApi, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";

type StageSummary = {
  status: string;
  reviewed?: number;
  required?: number;
  total?: number;
  decision?: string | null;
  comment?: string | null;
  conditions?: string[];
  decided_at?: string | null;
};

type ApprovalItem = {
  step?: string;
  approver_member_id?: number;
  approver_name?: string;
  decision?: string;
  comment?: string;
  conditions?: string[];
  decided_at?: string;
};

type RiskCheck = { key: string; label: string; value?: string; status: string };

type SixDim = {
  key: string;
  title?: string;
  summary?: string;
  rating?: number | null;
  confidence?: number | null;
  gate?: string | null;
};

type DebateArg = {
  id?: number;
  side?: string;
  round?: number;
  claim?: string;
  confidence?: number;
  falsifier?: string;
};

type ResearchDebate = {
  version_no?: number;
  status?: string;
  industry_analysis?: { summary?: string } | null;
  six_dim?: SixDim[];
  memo?: { summary?: string; decision?: string } | null;
  debate?: {
    conclusion?: string;
    arguments?: DebateArg[];
    evidence_checks?: unknown[];
  } | null;
};

type AgentMemo = {
  summary?: string;
  verdict?: string;
  decision?: string;
  recommendation?: string;
  risks?: string[];
  open_questions?: string[];
  conditions?: Array<string | { text?: string; condition?: string; detail?: string }>;
  evidence?: string[];
  engine?: string;
};

type ProposalListItem = {
  id: number;
  status: string;
  direction: string;
  target_weight: number;
  company_name: string;
  symbol: string;
  market: string;
  version_no?: number;
  updated_at?: string;
  current_version_no?: number;
};

type ProposalDetail = ProposalListItem & {
  case_id?: number;
  current_version?: { id: number; version_no: number; snapshot?: Record<string, unknown> };
  progress?: { partner: StageSummary; risk_precheck: StageSummary; chairman: StageSummary };
  risk_checks?: RiskCheck[];
  approval_chain?: ApprovalItem[];
  my_decision?: { decision?: string; comment?: string; conditions?: string[] } | null;
  authorization?: { id: number; status: string; issued_at?: string } | null;
  research_debate?: ResearchDebate | null;
  risk_stage?: StageSummary;
};

const STEPS = [
  { name: "议案提交", sub: "全公司概览" },
  { name: "合伙人", sub: "研究质量 / 上会" },
  { name: "风控", sub: "六项硬约束" },
  { name: "Chairman", sub: "资本配置" },
  { name: "授权", sub: "AUTH 快照" },
];

const DECISION_LABEL: Record<string, string> = {
  approve: "通过",
  conditional: "附条件",
  return: "退回",
  pass: "放行",
  veto: "否决",
  block: "否决",
  reject: "拒绝",
};

function parseProposalId(key: string | null): number | null {
  const m = String(key || "").match(/proposal:(\d+)/);
  return m ? Number(m[1]) : null;
}

function gateTone(gate?: string | null): string {
  if (gate === "pass") return "ok";
  if (gate === "fail") return "bad";
  return "warn";
}

function ResearchDebateSummary({ data }: { data?: ResearchDebate | null }) {
  if (!data) {
    return (
      <section className="v3-card">
        <div className="v3-card-head"><div><h2>研究与辩论摘要</h2><p>只读引用 02/03 锁定版本。</p></div></div>
        <div className="v3-empty">当前议案还没有可引用的研究/辩论记录。</div>
      </section>
    );
  }
  const args = data.debate?.arguments || [];
  const bull = args.filter((x) => x.side === "bull").slice(0, 2);
  const bear = args.filter((x) => x.side === "bear").slice(0, 2);
  const dims = data.six_dim || [];
  return (
    <section className="v3-card">
      <div className="v3-card-head">
        <div><h2>研究与辩论摘要</h2><p>只读引用锁定版本；不在此页改数或重跑 Agent。</p></div>
        <span className="v3-chip">R{data.version_no || "—"} · {data.status || "—"}</span>
      </div>
      <dl>
        <div className="v3-kv"><dt>辩论结论</dt><dd>{data.debate?.conclusion || "—"}</dd></div>
        <div className="v3-kv"><dt>证据核验</dt><dd>{(data.debate?.evidence_checks || []).length} 条</dd></div>
        <div className="v3-kv"><dt>一页纸结论</dt><dd>{data.memo?.decision ? `${data.memo.decision} · ` : ""}{data.memo?.summary || "未生成"}</dd></div>
      </dl>
      {data.industry_analysis?.summary ? (
        <div className="v3-note" style={{ marginTop: 8 }}>行业底图：{data.industry_analysis.summary}</div>
      ) : null}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 6, marginTop: 10 }}>
        {dims.map((d) => (
          <div key={d.key} className="v3-note" style={{ padding: "7px 8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
              <b style={{ fontSize: 10 }}>{d.title || d.key}</b>
              <span className={`v3-chip ${gateTone(d.gate)}`}>{d.gate || "—"}</span>
            </div>
            <div style={{ fontSize: 9.5, lineHeight: 1.55, color: "#746b7c", marginTop: 4 }}>
              {d.summary || "—"}
            </div>
            {d.rating != null ? <div style={{ fontSize: 9.5, color: "#9b92a1", marginTop: 3 }}>评级 {d.rating}/5{d.confidence != null ? ` · 置信 ${Number(d.confidence).toFixed(2)}` : ""}</div> : null}
          </div>
        ))}
      </div>
      {bull.length || bear.length ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 8, marginTop: 10 }}>
          <div>
            <div className="v3-eyebrow">多方要点</div>
            {bull.map((a) => (
              <div key={a.id} className="v3-claim" style={{ marginTop: 5 }}>
                <div className="who">第 {a.round || 1} 轮 · 置信 {a.confidence?.toFixed?.(2) ?? "—"}</div>
                <p>{a.claim}</p>
              </div>
            ))}
            {!bull.length ? <div className="v3-empty" style={{ padding: "10px 4px" }}>暂无</div> : null}
          </div>
          <div>
            <div className="v3-eyebrow">空方要点</div>
            {bear.map((a) => (
              <div key={a.id} className="v3-claim" style={{ marginTop: 5 }}>
                <div className="who">第 {a.round || 1} 轮 · 置信 {a.confidence?.toFixed?.(2) ?? "—"}</div>
                <p>{a.claim}</p>
                {a.falsifier ? <div className="fs">证伪：{a.falsifier}</div> : null}
              </div>
            ))}
            {!bear.length ? <div className="v3-empty" style={{ padding: "10px 4px" }}>暂无</div> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function statusTone(status: string): string {
  if (["executed", "authorized"].includes(status)) return "ok";
  if (["frozen", "rejected"].includes(status)) return "bad";
  if (["draft", "partner_review", "risk_precheck", "chairman_review"].includes(status)) return "warn";
  return "info";
}

export function InstV3ApprovalsPage() {
  const session = useInstSession();
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<ProposalListItem[]>([]);
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [viewStep, setViewStep] = useState(session.role === "manager" ? 0 : session.role === "partner" ? 1 : session.role === "risk" ? 2 : session.role === "chairman" ? 3 : 0);
  const [comment, setComment] = useState("");
  const [conditions, setConditions] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [memo, setMemo] = useState<AgentMemo | null>(null);
  const [memoMeta, setMemoMeta] = useState<{ cached?: boolean; stale?: boolean } | null>(null);
  const [memoBusy, setMemoBusy] = useState(false);
  const [memoError, setMemoError] = useState<string | null>(null);

  const selectedId = parseProposalId(params.get("key"));
  const role = session.role;
  const canApprove = ["partner", "risk", "chairman"].includes(role);
  const memoPath = role === "partner" ? "partner-memo" : role === "risk" ? "risk-review" : role === "chairman" ? "chairman-memo" : null;
  const memoAgent = role === "partner" ? "合伙人 Agent · 审批建议" : role === "risk" ? "风控 Agent · 审批建议" : role === "chairman" ? "Chairman Agent · 决策建议" : null;
  const memoDuty = role === "partner"
    ? "判断研究质量、上会资格与议案合理性；建议不替代本人意见。"
    : role === "risk"
      ? "只看六项硬约束与组合影响；有阻断项就建议否决。"
      : "看资本配置与机会成本；建议不替代 Chairman 表决。";

  const loadList = async () => {
    const pending = await instApi<{ items: ProposalListItem[] }>("/proposals?scope=pending");
    let rows = pending.items || [];
    if (role === "manager") {
      const reviewed = await instApi<{ items: ProposalListItem[] }>("/proposals?scope=reviewed");
      const seen = new Set(rows.map((x) => x.id));
      rows = rows.concat((reviewed.items || []).filter((x) => !seen.has(x.id)));
    }
    setItems(rows);
    return rows;
  };

  const loadDetail = async (id: number) => {
    const d = await instApi<ProposalDetail>(`/proposals/${id}`);
    setDetail(d);
    setComment("");
    setConditions("");
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadList()
      .then(async (rows) => {
        if (!alive) return;
        const id = selectedId || rows[0]?.id || null;
        if (id) {
          if (!selectedId) setParams({ key: `proposal:${id}` }, { replace: true });
          else await loadDetail(id);
        }
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    setMemo(null);
    setMemoMeta(null);
    setMemoError(null);
    if (!detail?.id || !memoPath) return;
    let alive = true;
    instApi<{ memo: AgentMemo | null; cached?: boolean; stale?: boolean }>(
      `/proposals/${detail.id}/ai/${memoPath}?cached_only=true`,
    )
      .then((res) => {
        if (!alive) return;
        if (res.memo) {
          setMemo(res.memo);
          setMemoMeta({ cached: res.cached, stale: res.stale });
        }
      })
      .catch(() => {
        // 建议是辅助信息；读取失败不阻塞审批页。
      });
    return () => { alive = false; };
  }, [detail?.id, memoPath]);

  const generateMemo = async (refresh: boolean) => {
    if (!detail?.id || !memoPath) return;
    setMemoBusy(true);
    setMemoError(null);
    try {
      const res = await instApi<{ memo: AgentMemo | null; cached?: boolean; stale?: boolean }>(
        `/proposals/${detail.id}/ai/${memoPath}`,
        { method: "POST", body: { refresh } },
      );
      setMemo(res.memo);
      setMemoMeta({ cached: res.cached, stale: res.stale });
    } catch (e) {
      setMemoError(e instanceof Error ? e.message : String(e));
    } finally {
      setMemoBusy(false);
    }
  };

  const selectProposal = (id: number) => {
    setParams({ key: `proposal:${id}` });
    loadDetail(id).catch((e: Error) => setError(e.message));
  };

  const act = async (kind: "partner" | "risk" | "chairman", decision: string) => {
    if (!detail) return;
    if (decision === "conditional" && !conditions.trim()) {
      setError("附条件必须填写条件（每行一条）");
      return;
    }
    setBusy(kind + decision);
    setError(null);
    try {
      const path = kind === "risk" ? `/proposals/${detail.id}/risk-check` : `/proposals/${detail.id}/${kind}`;
      await instApi(path, {
        method: "POST",
        body: {
          decision,
          comment: comment.trim() || null,
          conditions: conditions.split("\n").map((x) => x.trim()).filter(Boolean),
        },
      });
      if (kind === "chairman" && (decision === "approve" || decision === "conditional")) {
        await instApi(`/proposals/${detail.id}/authorize`, { method: "POST" });
        setViewStep(4);
      }
      await loadList();
      await loadDetail(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const progress = detail?.progress;
  const riskChecks = detail?.risk_checks || [];
  const stageForRole: Record<string, string> = { partner: "partner_review", risk: "risk_precheck", chairman: "chairman_review" };
  const canAct = (kind: "partner" | "risk" | "chairman") =>
    role === kind && detail?.status === stageForRole[kind];
  const chain = detail?.approval_chain || [];
  const snapshot = (detail?.current_version?.snapshot || {}) as Record<string, unknown>;
  const auth = detail?.authorization;
  const myPending = useMemo(() => items.filter((x) => ["draft", "partner_review", "risk_precheck", "chairman_review"].includes(x.status)).length, [items]);

  if (loading) return <div className="v3-loading">正在加载投委会审批…</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">DECISION / 04</div>
          <h1>投委会审批</h1>
          <p>合伙人 → 独立风控 → Chairman，顺序固定；每一关只看自己该看的字段，风控否决终局。</p>
        </div>
        <span className="v3-chip info">{session.role_label_cn} · 按登录角色</span>
      </div>

      <div className="v3-stepper">
        {STEPS.map((s, i) => (
          <button key={s.name} className={`v3-step${i < viewStep ? " done" : i === viewStep ? " now" : ""}`} onClick={() => setViewStep(i)} style={{ background: "none", borderTop: 0, borderLeft: 0, borderBottom: 0, cursor: "pointer" }}>
            <span className="dot">{i}</span>
            <div><span className="lb">{s.name}</span><span className="sb">{s.sub}</span></div>
          </button>
        ))}
      </div>

      <div className="v3-workspace-grid">
        <div className="v3-project-list">
          <div className="pl-head"><span>{role === "manager" ? "我的议案" : "待我审"}</span><span>{items.length}</span></div>
          {items.map((p) => (
            <button key={p.id} className={`pl-item${p.id === detail?.id ? " on" : ""}`} onClick={() => selectProposal(p.id)}>
              <b>{p.company_name}</b>
              <span>{p.symbol} · {p.direction} {fmtPct(p.target_weight)} · {p.status}</span>
            </button>
          ))}
          {!items.length ? <div className="v3-empty" style={{ padding: "18px 8px" }}>当前没有待你处理的议案。</div> : null}
        </div>

        <div className="v3-work-main">
          {error ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{error}</div> : null}

          {viewStep === 0 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>议案提交总览</h2><p>全公司已提交议案；点一条进入它当前所在关卡。</p></div><span className="v3-chip">{items.length} 份</span></div>
              <div className="v3-kpis" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
                <div className="v3-kpi"><div className="k">已提交</div><div className="v">{items.length}</div></div>
                <div className="v3-kpi"><div className="k">审批中</div><div className="v">{myPending}</div></div>
                <div className="v3-kpi"><div className="k">已授权</div><div className="v">{items.filter((x) => ["authorized", "executed"].includes(x.status)).length}</div></div>
              </div>
            </section>
          ) : null}

          {viewStep !== 0 && detail ? (
            <>
              <section className="v3-card">
                <div className="v3-card-head">
                  <div><h2>{detail.company_name} <span className="font-mono text-[11px] font-normal text-[#9b92a1]">{detail.symbol}</span></h2><p>v{detail.current_version_no || detail.version_no || "—"} · {detail.direction} {fmtPct(detail.target_weight)} · {detail.status}</p></div>
                  <span className={`v3-chip ${statusTone(detail.status)}`}>{detail.status}</span>
                </div>
                <dl>
                  <div className="v3-kv"><dt>方向 / 目标仓位</dt><dd>{detail.direction} · {fmtPct(detail.target_weight)}</dd></div>
                  <div className="v3-kv"><dt>价格区间</dt><dd>{snapshot.price_low != null ? `${snapshot.price_low} – ${snapshot.price_high}` : "—"}</dd></div>
                  <div className="v3-kv"><dt>资金来源 / 有效期</dt><dd>{String(snapshot.funding_source || "—")} · {String(snapshot.valid_until || "—")}</dd></div>
                  <div className="v3-kv"><dt>投资意见</dt><dd style={{ maxWidth: "70%" }}>{String(snapshot.investment_opinion || "—")}</dd></div>
                </dl>
              </section>

              {viewStep === 1 ? (
                <>
                <ResearchDebateSummary data={detail.research_debate} />
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>合伙人复核</h2><p>研究质量、上会资格、议案合理性与机会成本；不看风控六项明细。</p></div><span className="v3-chip">{progress?.partner?.status || "—"}</span></div>
                  <p style={{ fontSize: 11, lineHeight: 1.7, color: "#746b7c" }}>研究与辩论摘要由 02/03 锁定版本提供；合伙人只判断是否值得上会。提案人不能审批自己的议案。</p>
                  {role === "partner" && !canAct("partner") ? (
                    <div className="v3-note">当前议案状态为 {detail.status}，合伙人环节已结束或尚未轮到，不能再操作。</div>
                  ) : null}
                  {role === "partner" && canAct("partner") ? (
                    <>
                      <div className="v3-form-grid" style={{ marginTop: 10 }}>
                        <div className="v3-field span-2"><label>审批意见</label><textarea value={comment} onChange={(e) => setComment(e.target.value)} /></div>
                        <div className="v3-field span-2"><label>附加条件（附条件时必填，每行一条）</label><textarea value={conditions} onChange={(e) => setConditions(e.target.value)} /></div>
                      </div>
                      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <button className="v3-btn primary" disabled={!!busy} onClick={() => act("partner", "approve")}><Check className="h-3.5 w-3.5" />复核通过</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("partner", "conditional")}>附条件</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("partner", "return")}>退回</button>
                      </div>
                    </>
                  ) : null}
                  {role !== "partner" ? <div className="v3-note">当前登录角色为 {session.role_label_cn}，只能查看；合伙人账号可操作。</div> : null}
                </section>
                </>
              ) : null}

              {viewStep === 2 ? (
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>六项硬约束核查</h2><p>任何一项否决，议案即时终止；Chairman 不能越过。</p></div><span className="v3-chip">{riskChecks.length} 项</span></div>
                  {riskChecks.map((c) => (
                    <div className="v3-kv" key={c.key}><dt>{c.label}</dt><dd>{c.value || "—"} <span className={`v3-chip ${c.status === "pass" ? "ok" : c.status === "warn" ? "warn" : "bad"}`}>{c.status}</span></dd></div>
                  ))}
                  {!riskChecks.length ? <div className="v3-empty">当前议案还没有风控核查数据。</div> : null}
                  {role === "risk" && !canAct("risk") ? (
                    <div className="v3-note">当前议案状态为 {detail.status}，风控环节尚未轮到或已结束，不能操作。</div>
                  ) : null}
                  {role === "risk" && canAct("risk") ? (
                    <>
                      <div className="v3-form-grid" style={{ marginTop: 10 }}>
                        <div className="v3-field span-2"><label>风控意见</label><textarea value={comment} onChange={(e) => setComment(e.target.value)} /></div>
                        <div className="v3-field span-2"><label>附条件（有条件放行时必填，每行一条）</label><textarea value={conditions} onChange={(e) => setConditions(e.target.value)} /></div>
                      </div>
                      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <button className="v3-btn primary" disabled={!!busy} onClick={() => act("risk", "pass")}><Check className="h-3.5 w-3.5" />放行</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("risk", "conditional")}>有条件放行</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("risk", "veto")}><X className="h-3.5 w-3.5" />否决（终局）</button>
                      </div>
                    </>
                  ) : null}
                  {role !== "risk" ? <div className="v3-note">当前登录角色为 {session.role_label_cn}，只能查看；独立风控账号可操作。</div> : null}
                </section>
              ) : null}

              {viewStep === 3 ? (
                <>
                <ResearchDebateSummary data={detail.research_debate} />
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>风控结论</h2><p>独立风控六项硬约束的结论与附加条件；详细核查值不回传 Chairman。</p></div><span className="v3-chip">{detail.risk_stage?.status || "—"}</span></div>
                  <dl>
                    <div className="v3-kv"><dt>结论</dt><dd>{detail.risk_stage?.decision || "—"}</dd></div>
                    <div className="v3-kv"><dt>意见</dt><dd>{detail.risk_stage?.comment || "—"}</dd></div>
                    <div className="v3-kv"><dt>附加条件</dt><dd>{detail.risk_stage?.conditions?.length ? detail.risk_stage.conditions.join("；") : "无"}</dd></div>
                    <div className="v3-kv"><dt>表决进度</dt><dd>{detail.risk_stage?.reviewed ?? 0}/{detail.risk_stage?.total ?? "—"}</dd></div>
                  </dl>
                </section>
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>完整审批链</h2><p>合伙人 → 风控 → Chairman；按人留痕，风控否决不可越过。</p></div><span className="v3-chip">{progress?.chairman?.status || "—"}</span></div>
                  {chain.length ? chain.map((a, i) => (
                    <div className="v3-kv" key={`${a.step}-${i}`}><dt>{a.step} · {a.approver_name || a.approver_member_id || "—"}</dt><dd>{DECISION_LABEL[a.decision || ""] || a.decision || "待审"}{a.comment ? ` · ${a.comment}` : ""}</dd></div>
                  )) : <div className="v3-empty">还没有审批记录。</div>}
                  {role === "chairman" && !canAct("chairman") ? (
                    <div className="v3-note">当前议案状态为 {detail.status}，Chairman 环节尚未轮到或已结束，不能操作。</div>
                  ) : null}
                  {role === "chairman" && canAct("chairman") ? (
                    <>
                      <div className="v3-form-grid" style={{ marginTop: 10 }}>
                        <div className="v3-field span-2"><label>Chairman 意见</label><textarea value={comment} onChange={(e) => setComment(e.target.value)} /></div>
                        <div className="v3-field span-2"><label>附条件（附条件时必填，每行一条）</label><textarea value={conditions} onChange={(e) => setConditions(e.target.value)} /></div>
                      </div>
                      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <button className="v3-btn primary" disabled={!!busy} onClick={() => act("chairman", "approve")}><Check className="h-3.5 w-3.5" />批准并生成授权</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("chairman", "conditional")}>附条件批准</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("chairman", "return")}>退回</button>
                        <button className="v3-btn ghost" disabled={!!busy} onClick={() => act("chairman", "reject")}>拒绝</button>
                      </div>
                    </>
                  ) : null}
                  {role !== "chairman" ? <div className="v3-note">当前登录角色为 {session.role_label_cn}，只能查看；Chairman 账号可操作。</div> : null}
                </section>
                </>
              ) : null}

              {viewStep === 4 ? (
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>授权文件 AUTH</h2><p>Chairman 批准后生成不可修改的执行依据；05 只按这份授权执行。</p></div><span className={`v3-chip ${auth ? "ok" : "warn"}`}>{auth ? auth.status : "未生成"}</span></div>
                  {auth ? (
                    <>
                      <dl>
                        <div className="v3-kv"><dt>授权 ID</dt><dd>{auth.id}</dd></div>
                        <div className="v3-kv"><dt>状态</dt><dd>{auth.status}</dd></div>
                        <div className="v3-kv"><dt>签发时间</dt><dd>{auth.issued_at || "—"}</dd></div>
                      </dl>
                      <div style={{ marginTop: 10 }}><Link className="v3-btn primary" to={`/inst/execute?key=auth:${auth.id}`}>进入执行成交 <ArrowRight className="h-3.5 w-3.5" /></Link></div>
                    </>
                  ) : <div className="v3-empty">三关全部通过后生成授权。</div>}
                </section>
              ) : null}
            </>
          ) : null}
        </div>

        <aside className="v3-agent-rail">
          {memoPath && memoAgent ? (
            <>
              <div className="ar-kicker">CURRENT AGENT</div>
              <h3>{memoAgent}</h3>
              <p>{memoDuty}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {memo?.engine ? <span className="v3-chip">{memo.engine}</span> : null}
                {memoMeta?.cached ? <span className="v3-chip">缓存建议</span> : null}
                {memoMeta?.stale ? <span className="v3-chip warn">上游有变更</span> : null}
              </div>
              {memo ? (
                <div style={{ marginTop: 8 }}>
                  {memo.verdict || memo.decision || memo.recommendation ? (
                    <div className="v3-note" style={{ marginBottom: 6 }}>{memo.verdict || memo.decision || memo.recommendation}</div>
                  ) : null}
                  <p style={{ fontSize: 10.5, lineHeight: 1.7, color: "#4b4352" }}>{memo.summary || "—"}</p>
                  {memo.risks?.length ? (
                    <div className="ar-row"><b>主要风险</b><br />{memo.risks.slice(0, 3).map((x) => `· ${x}`).join("；")}</div>
                  ) : null}
                  {memo.open_questions?.length ? (
                    <div className="ar-row"><b>待确认</b><br />{memo.open_questions.slice(0, 3).map((x) => `· ${x}`).join("；")}</div>
                  ) : null}
                  {memo.evidence?.length ? <div className="ar-row"><b>引用证据</b><br />{memo.evidence.length} 条</div> : null}
                </div>
              ) : <div className="v3-empty" style={{ padding: "10px 2px" }}>还没有 Agent 建议。生成后仅作参考，不改变审批状态。</div>}
              {memoError ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{memoError}</div> : null}
              <button className="v3-btn ghost" style={{ width: "100%", marginTop: 8 }} disabled={memoBusy || !detail} onClick={() => generateMemo(!!memo)}>
                {memoBusy ? "生成中…" : memo ? "重新生成建议" : "生成审批建议"}
              </button>
            </>
          ) : (
            <>
              <div className="ar-kicker">CURRENT GATE</div>
              <h3>{role === "manager" ? "提案人只读" : `${session.role_label_cn} · 审批关`}</h3>
              <p>{role === "manager" ? "提案人只能查看自己的议案与三关进度，不能审批自己的议案。" : "按登录角色只看本关字段；所有动作由服务端校验。"}</p>
            </>
          )}
          <div className="ar-row"><b>进度</b><br />合伙人 {progress?.partner?.reviewed ?? 0}/{progress?.partner?.total ?? "—"} · 风控 {progress?.risk_precheck?.reviewed ?? 0}/{progress?.risk_precheck?.total ?? "—"} · Chairman {progress?.chairman?.reviewed ?? 0}/{progress?.chairman?.total ?? "—"}</div>
          <div className="ar-row"><b>当前议案</b><br />{detail ? `${detail.company_name} · ${detail.status}` : "未选择"}</div>
          <div className="ar-row"><b>硬约束</b><br /><ShieldAlert className="mr-1 inline h-3 w-3" />风控否决终局；提案人回避；顺序不可跳级。</div>
        </aside>
      </div>
    </>
  );
}
