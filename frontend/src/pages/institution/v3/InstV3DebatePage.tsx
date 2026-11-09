import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Play, Send } from "lucide-react";
import { instApi } from "@/lib/instApi";
import { InstV3AgentRail, type AgentPanelDef } from "@/components/institution/v3/InstV3AgentRail";

type Arg = {
  id: number;
  side: "bull" | "bear" | "chair" | string;
  round: number;
  claim: string;
  claim_type?: string;
  evidence_ids?: number[];
  confidence?: number;
  falsifier?: string;
};

type Debate = {
  id: number;
  status: string;
  conclusion?: string;
  arguments?: Arg[];
  evidence_checks?: Array<{ claim_id?: string; status?: string; grade?: string; issues?: string[] }>;
};

type Version = {
  id: number;
  version_no: number;
  status: string;
  conclusion?: string;
  valuation?: Record<string, unknown> | null;
  six_dim?: Array<{ key: string; title?: string; summary?: string; rating?: number | null }>;
};

type Proposal = { id: number; status: string; direction?: string; target_weight?: number };

type CaseItem = {
  id: number;
  case_no: string;
  stage: string;
  stage_no?: number;
  symbol: string;
  company_name: string;
  industry?: string;
  ref_price?: number;
  versions?: Version[];
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
  proposals?: Proposal[];
};

const STEPS = [
  { name: "多空立论", sub: "各 3 条 · 带证伪", agent: "多头 / 空头研究员", duty: "多头只找买入理由，空头只打最弱假设；每条带证据与证伪条件。" },
  { name: "交叉质询", sub: "主持逼分歧 · 证据核验", agent: "研究经理 / 主持", duty: "把双方 claim 逐条对齐，标出已回应/未回应/证据不足，不投票、不取平均。" },
  { name: "估值复核", sub: "确定性 DCF · 非 AI", agent: "估值计算服务", duty: "DCF、敏感性、反向 DCF 只算数；AI 只解释假设，不生成数字。" },
  { name: "议案", sub: "投资意见 · 锁定 P3", agent: "交易员 + 投资经理", duty: "交易员生成骨架，投资经理补意见、仓位、价格带、有效期与监控，锁定后提交三关。" },
];

function currentCaseId(key: string | null): number | null {
  const m = String(key || "").match(/case:(\d+)/);
  return m ? Number(m[1]) : null;
}

/** 把长段 claim 压成一句可扫读的论点；完整原文放在 title 里备查。 */
function claimHeadline(value?: string): string {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  if (!clean) return "—";
  const first = clean.split(/[；;。：:]/)[0].trim() || clean;
  const noTail = first.replace(/[，,]+$/, "");
  return noTail.length > 40 ? `${noTail.slice(0, 40)}…` : noTail;
}

export function InstV3DebatePage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [detail, setDetail] = useState<CaseItem | null>(null);
  const [debate, setDebate] = useState<Debate | null>(null);
  const [step, setStep] = useState(0);
  const [agentId, setAgentId] = useState("bull");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [direction, setDirection] = useState("buy");
  const [target, setTarget] = useState("0.03");
  const [priceLow, setPriceLow] = useState("");
  const [priceHigh, setPriceHigh] = useState("");
  const [funding, setFunding] = useState("现金");
  const [validUntil, setValidUntil] = useState("");
  const [monitoring, setMonitoring] = useState("季度财报后复核\n批价/份额跌破阈值触发复核");
  const [opinion, setOpinion] = useState("");

  const selectedId = currentCaseId(params.get("key"));
  const version = detail?.versions?.[0] || null;
  const latestProposal = detail?.proposals?.[0] || null;

  const loadCases = async () => {
    const res = await instApi<{ items: CaseItem[] }>("/cases");
    const rows = (res.items || []).filter((c) => Number(c.stage_no ?? 1) >= 2 && Number(c.stage_no ?? 1) <= 3);
    setCases(rows);
    return rows;
  };

  const loadDetail = async (id: number) => {
    const d = await instApi<CaseItem>(`/cases/${id}`);
    setDetail(d);
    const session = d.debates?.[0];
    if (session?.id) {
      const full = await instApi<Debate>(`/debates/${session.id}`);
      setDebate(full);
    } else {
      setDebate(null);
    }
    return d;
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadCases()
      .then(async (items) => {
        if (!alive) return;
        const id = selectedId || items[0]?.id || null;
        if (id) {
          if (!selectedId) setParams({ key: `case:${id}` }, { replace: true });
          const d = await loadDetail(id);
          const price = Number(d.ref_price || 0);
          if (price > 0) {
            setPriceLow((price * 0.9).toFixed(2));
            setPriceHigh((price * 1.1).toFixed(2));
          }
          const until = new Date();
          until.setDate(until.getDate() + 30);
          setValidUntil(until.toISOString().slice(0, 10));
        }
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const bull = useMemo(() => (debate?.arguments || []).filter((a) => a.side === "bull"), [debate]);
  const bear = useMemo(() => (debate?.arguments || []).filter((a) => a.side === "bear"), [debate]);

  useEffect(() => {
    setAgentId(step === 0 ? "bull" : step === 1 ? "chair" : step === 2 ? "valuation" : "trader");
  }, [step]);

  const agentDefs = useMemo<AgentPanelDef[]>(() => {
    if (step === 0) {
      return [
        { id: "bull", name: "多头研究员", code: "BULL", model: "多头 Agent", tools: "研究定稿 / 订单 / 估值", output: `${bull.length} 条多头论点`, role: "只找买入理由，不替空头说话。" },
        { id: "bear", name: "空头研究员", code: "BEAR", model: "空头 Agent", tools: "研究定稿 / 应收 / 竞品", output: `${bear.length} 条空头攻击`, role: "只打最弱假设，不重复行业空间。" },
      ];
    }
    if (step === 1) {
      return [{ id: "chair", name: "研究经理 / 主持", code: "CHAIR", model: "主持 Agent", tools: "多空 claim / 证据核验", output: "分歧清单 + 核验结论", role: "只逼分歧、核证据，不投票、不取平均。" }];
    }
    if (step === 2) {
      return [{ id: "valuation", name: "估值计算服务", code: "ENGINE", model: "确定性代码", tools: "DCF / 敏感性 / 反向 DCF", output: "价值区间 + IRR", role: "代码计算，不生成观点。", engine: true }];
    }
    return [{ id: "trader", name: "交易员", code: "TRADER", model: "交易员 Agent", tools: "裁决 / 议案模板 / 组合约束", output: "议案 P3", role: "把裁决写成可审批的议案。" }];
  }, [step, bull.length, bear.length]);

  const activeSide = agentId === "bear" ? bear : bull;
  const sideName = agentId === "bear" ? "空头研究员" : "多头研究员";
  const selectAgent = (id: string) => setAgentId(id);

  const selectCase = (id: number) => {
    setStep(0); setAgentId("bull"); setDebate(null); setParams({ key: `case:${id}` });
  };

  const startDebate = async () => {
    if (!detail) return;
    setBusy("debate");
    setError(null);
    try {
      await instApi(`/cases/${detail.id}/debate`, { method: "POST", body: { use_ai: false } });
      await loadDetail(detail.id);
      setStep(1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const createProposal = async () => {
    if (!detail) return;
    setBusy("proposal");
    setError(null);
    try {
      const created = await instApi<Proposal>(`/cases/${detail.id}/proposals`, {
        method: "POST",
        body: {
          direction,
          target_weight: Number(target),
          price_low: priceLow ? Number(priceLow) : null,
          price_high: priceHigh ? Number(priceHigh) : null,
          funding_source: funding,
          valid_until: validUntil,
          monitoring: monitoring.split("\n").map((x) => x.trim()).filter(Boolean),
          investment_opinion: opinion,
        },
      });
      await instApi(`/proposals/${created.id}/lock`, { method: "POST", body: { allow_warnings: true } });
      navigate(`/inst/approvals?key=${encodeURIComponent(`proposal:${created.id}`)}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  if (loading) return <div className="v3-loading">正在加载多空辩论…</div>;
  if (error && !detail) return <div className="v3-card">加载失败：{error}</div>;
  if (!detail) return <div className="v3-card">暂无可辩论的项目。请先在 02 锁定研究定稿。</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">DEBATE / 03</div>
          <h1>{detail.company_name} · 多空辩论 <span className="font-mono text-[13px] font-normal text-[#9b92a1]">{detail.symbol}</span></h1>
          <p>多头与空头各 3 条，主持逼分歧、核证据，估值复核只算数，议案 P3 锁定后进入审批。</p>
        </div>
        <Link className="v3-btn ghost" to={`/inst/pipeline/result?key=${encodeURIComponent(`case:${detail.id}`)}`}>查看结果页</Link>
      </div>

      <div className="v3-stepper">
        {STEPS.map((s, i) => (
          <button key={s.name} className={`v3-step${i < step ? " done" : i === step ? " now" : ""}`} onClick={() => setStep(i)} style={{ background: "none", borderTop: 0, borderLeft: 0, borderBottom: 0, cursor: "pointer" }}>
            <span className="dot">{i < step ? "✓" : i + 1}</span>
            <div><span className="lb">{s.name}</span><span className="sb">{s.sub}</span></div>
          </button>
        ))}
      </div>

      <div className="v3-workspace-grid">
        <div className="v3-project-list">
          <div className="pl-head"><span>待辩论 / 审批中</span><span>{cases.length}</span></div>
          {cases.map((c) => (
            <button key={c.id} className={`pl-item${c.id === detail.id ? " on" : ""}`} onClick={() => selectCase(c.id)}>
              <b>{c.company_name}</b>
              <span>{c.symbol} · {c.proposals?.[0]?.status || (c.debates?.[0] ? "辩论完成" : "待辩论")}</span>
            </button>
          ))}
        </div>

        <div className="v3-work-main">
          {error ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{error}</div> : null}

          {step === 0 ? (
            <section className="v3-card">
              <div className="v3-card-head">
                <div><h2>多空立论</h2><p>多头 / 空头各 3 条，逐条带证据 ID 与证伪条件；空头不重复行业空间。</p></div>
                {!debate ? <button className="v3-btn primary" disabled={!!busy} onClick={startDebate}><Play className="h-3.5 w-3.5" />{busy === "debate" ? "辩论生成中…" : "开始多空辩论"}</button> : <span className="v3-chip ok">已完成</span>}
              </div>
              {debate ? (
                <div>
                  <div className="v3-side-switch">
                    <button className={agentId === "bear" ? "" : "on"} onClick={() => setAgentId("bull")}>
                      多头 Agent <b>{bull.length} 条</b>
                    </button>
                    <button className={agentId === "bear" ? "on" : ""} onClick={() => setAgentId("bear")}>
                      空头 Agent <b>{bear.length} 条</b>
                    </button>
                  </div>
                  <div className="v3-eyebrow">{agentId === "bear" ? "空方 · 空头研究员 Agent" : "多方 · 多头研究员 Agent"}</div>
                  {activeSide.map((a) => (
                    <div className="v3-claim" key={a.id}>
                      <div className="who">第 {a.round} 轮</div>
                      <p className="claim-t" title={a.claim}>{claimHeadline(a.claim)}</p>
                      <div className="claim-meta">
                        <span className="v3-chip">证据 {a.evidence_ids?.length || 0} 条</span>
                        <span className="v3-chip">置信 {a.confidence?.toFixed?.(2) ?? "—"}</span>
                      </div>
                      {a.falsifier ? <div className="fs">证伪：{a.falsifier}</div> : null}
                    </div>
                  ))}
                  {!activeSide.length ? <div className="v3-empty" style={{ marginTop: 8 }}>暂无{sideName}论点</div> : null}
                </div>
              ) : <div className="v3-empty">还没有辩论记录。点击右上角开始；结论不投票，只保留分歧。</div>}
            </section>
          ) : null}

          {step === 1 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>交叉质询</h2><p>主持把双方 claim 逐条对齐，标出已回应 / 未回应 / 证据不足。</p></div><span className="v3-chip">{debate?.evidence_checks?.length || 0} 条核验</span></div>
              {debate ? (
                <>
                  <div className="v3-note">{debate.conclusion || "主持结论待生成。"}</div>
                  {(debate.evidence_checks || []).slice(0, 12).map((c, i) => (
                    <div className="v3-claim" key={`${c.claim_id}-${i}`}><div className="who">{c.claim_id || "claim"} · {c.grade || "—"}</div><p>{c.status || "—"} {c.issues?.length ? `· ${c.issues.join("；")}` : ""}</p></div>
                  ))}
                  {!debate.evidence_checks?.length ? <div className="v3-empty" style={{ marginTop: 8 }}>暂无证据核验明细；辩论记录仍保留在案。</div> : null}
                </>
              ) : <div className="v3-empty">先完成多空立论。</div>}
            </section>
          ) : null}

          {step === 2 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>估值复核</h2><p>数字来自确定性计算；AI 只解释假设，不生成数字。</p></div><span className="v3-chip">R{version?.version_no || "—"}</span></div>
              {version?.valuation ? (
                <dl>
                  {Object.entries(version.valuation).slice(0, 10).map(([k, v]) => (
                    <div className="v3-kv" key={k}><dt>{k}</dt><dd>{typeof v === "object" ? JSON.stringify(v).slice(0, 120) : String(v)}</dd></div>
                  ))}
                </dl>
              ) : <div className="v3-empty">研究版本里没有估值复核数据。</div>}
            </section>
          ) : null}

          {step === 3 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>议案 · 锁定 P3</h2><p>补齐投资意见、仓位、价格带、资金、有效期与监控条件；锁定后审批角色只读。</p></div>{latestProposal ? <span className="v3-chip ok">{latestProposal.status}</span> : <span className="v3-chip warn">待创建</span>}</div>
              {latestProposal && latestProposal.status !== "draft" ? (
                <div>
                  <div className="v3-note">议案已锁定并进入审批：{latestProposal.status}</div>
                  <div style={{ marginTop: 10 }}><Link className="v3-btn primary" to={`/inst/approvals?key=${encodeURIComponent(`proposal:${latestProposal.id}`)}`}>进入投委会审批 <ArrowRight className="h-3.5 w-3.5" /></Link></div>
                </div>
              ) : (
                <>
                  <div className="v3-form-grid">
                    <div className="v3-field"><label>方向</label><select value={direction} onChange={(e) => setDirection(e.target.value)}><option value="buy">买入</option><option value="sell">卖出</option><option value="exit">退出</option></select></div>
                    <div className="v3-field"><label>目标仓位（0-1）</label><input data-testid="inst-proposal-target" value={target} onChange={(e) => setTarget(e.target.value)} /></div>
                    <div className="v3-field"><label>价格下限（CNY）</label><input data-testid="inst-price-low" value={priceLow} onChange={(e) => setPriceLow(e.target.value)} /></div>
                    <div className="v3-field"><label>价格上限（CNY）</label><input data-testid="inst-price-high" value={priceHigh} onChange={(e) => setPriceHigh(e.target.value)} /></div>
                    <div className="v3-field"><label>资金来源</label><select value={funding} onChange={(e) => setFunding(e.target.value)}><option>现金</option><option>减仓换仓</option></select></div>
                    <div className="v3-field"><label>有效期</label><input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></div>
                    <div className="v3-field span-2"><label>投资意见</label><textarea data-testid="inst-investment-opinion" value={opinion} onChange={(e) => setOpinion(e.target.value)} placeholder="写清为什么投、关键假设、最担心什么、什么情况下改变判断。" /></div>
                    <div className="v3-field span-2"><label>监控 / 退出条件</label><textarea value={monitoring} onChange={(e) => setMonitoring(e.target.value)} /></div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
                    <button data-testid="inst-proposal-create" className="v3-btn primary" disabled={!!busy || !opinion.trim()} onClick={createProposal}><Send className="h-3.5 w-3.5" />{busy === "proposal" ? "锁定中…" : "锁定议案并提交审批"}</button>
                  </div>
                </>
              )}
            </section>
          ) : null}
        </div>

        <InstV3AgentRail
          agents={agentDefs}
          activeId={agentId}
          onSelect={selectAgent}
          contextRows={[
            { label: "本步产出", value: step === 0 ? "多空论点" : step === 1 ? "分歧清单" : step === 2 ? "估值复核" : "议案 P3" },
            { label: "输入", value: "研究定稿 R3、证据包、FactPack；不引用旧辩论输出作为证据。" },
            { label: "约束", value: "辩论不投票、不取平均；估值数字由代码生成；锁定后审批只读。" },
          ]}
        />
      </div>
    </>
  );
}
