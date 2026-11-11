import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Play, Send } from "lucide-react";
import { dedupeBy, latestByKey } from "@/lib/instDedupe";
import { latestAiJob, waitAiJob } from "@/lib/instV3Api";
import { instApi } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { InstV3AgentRail, type AgentPanelDef } from "@/components/institution/v3/InstV3AgentRail";
import InstV3AgentProgress from "./InstV3AgentProgress";

type Arg = {
  id: number;
  claim_id?: string;
  side: "bull" | "bear" | "chair" | string;
  round: number;
  claim: string;
  claim_type?: string;
  evidence_ids?: number[];
  confidence?: number;
  falsifier?: string;
};

type EvidenceCheck = {
  id?: number;
  claim_id?: string;
  evidence_id?: number;
  status?: string;
  grade?: string;
  issues?: string[];
};

type ChairReview = {
  schema_version?: string;
  agent_tier?: string;
  role_title?: string;
  verdict?: "support_proposal" | "supplement_research" | string;
  chair_call?: string;
  consensus?: string[];
  unresolved?: Array<{
    issue?: string;
    bull_view?: string;
    bear_view?: string;
    why_unresolved?: string;
    data_needed?: string;
  }>;
  accepted_claims?: Array<{ side?: string; claim_id?: string; claim?: string; reason?: string }>;
  rejected_claims?: Array<{ side?: string; claim_id?: string; claim?: string; reason?: string }>;
  what_would_change?: string[];
  chief_confidence?: number;
  chief_fields_fallback?: boolean;
};

type Debate = {
  id: number;
  status: string;
  conclusion?: string;
  started_at?: string;
  ended_at?: string;
  factpack?: { engine?: string; chief_review?: ChairReview } | string | null;
  arguments?: Arg[];
  evidence_checks?: EvidenceCheck[];
};

type Version = {
  id: number;
  version_no: number;
  status: string;
  conclusion?: string;
  valuation?: Record<string, unknown> | null;
  six_dim?: Array<{ key: string; title?: string; summary?: string; rating?: number | null }>;
};

type ProposalAdvice = {
  available?: boolean;
  scores?: Array<{
    key?: string;
    title?: string;
    score_10?: number | null;
    rating_benchmark?: string | null;
    gate?: string | null;
  }>;
  overall_score?: number | null;
  debate?: {
    conclusion?: string;
    bull_count?: number;
    bear_count?: number;
    status?: string;
  };
  recommendation?: "buy" | "sell" | "hold" | "avoid";
  recommendation_label?: string;
  rationale?: string;
  held?: boolean;
  framework?: {
    direction?: string;
    target_weight?: number;
    price_low?: number | null;
    price_high?: number | null;
    funding_source?: string;
    valid_until?: string;
    monitoring?: string[];
    investment_opinion?: string;
  };
  engine?: string;
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
  version_no?: number | null;
  version_status?: string | null;
  updated_at?: string | null;
  versions?: Version[];
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
  proposals?: Proposal[];
};

const STEPS = [
  { name: "多空立论", sub: "多空论点", agent: "多头 / 空头研究员", duty: "多头只找买入理由，空头只打最弱假设；每条带证据。" },
  { name: "交叉质询", sub: "主持逼分歧 · 证据核验", agent: "研究经理 / 主持", duty: "把双方 claim 逐条对齐，标出已回应/未回应/证据不足，不投票、不取平均。" },
  { name: "估值复核", sub: "确定性 DCF · 非 AI", agent: "估值计算服务", duty: "DCF、敏感性、反向 DCF 只算数；AI 只解释假设，不生成数字。" },
  { name: "议案", sub: "投资意见 · 锁定议案", agent: "交易员 + 投资经理", duty: "交易员生成骨架，投资经理补意见、仓位、价格带、有效期与监控，锁定后提交三关。" },
];

const CHECK_STATUS: Record<string, { label: string; tone: string }> = {
  verified: { label: "已核验", tone: "ok" },
  partially_verified: { label: "部分核验", tone: "warn" },
  unverified: { label: "未核验", tone: "bad" },
  insufficient: { label: "证据不足", tone: "bad" },
  contradicted: { label: "证据矛盾", tone: "bad" },
};

const VALUATION_LABELS: Record<string, string> = {
  method: "估值方法",
  note: "口径说明",
  low: "悲观情景每股价值",
  base: "基准情景每股价值",
  high: "乐观情景每股价值",
  per_share: "每股价值",
  assumptions: "关键假设",
  equity_value: "股权价值",
  enterprise_value: "企业价值",
  net_debt_proxy: "净债务桥",
  discount_rate: "折现率",
  revenue_growth: "收入增速",
  terminal_growth: "永续增长率",
  cash_flow_margin: "现金流利润率",
};

const METHOD_LABELS: Record<string, string> = {
  relative_only: "相对估值（PB / ROE）",
  owner_earnings_proxy_net_debt: "所有者收益 + 净债务桥",
  dcf: "现金流折现（DCF）",
  unavailable: "暂不可估值",
};

function sanitizeText(value: unknown): string {
  // 原样展示后端返回的口径与限制，不再把“演示/简易测算”改写成“研究”。
  return String(value ?? "").trim();
}

function pctValue(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "未提供";
  return `${(Math.abs(n) <= 1 ? n * 100 : n).toFixed(1)}%`;
}

function yuanValue(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(2)} 元` : "未提供";
}

function yiValue(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n / 1e8).toFixed(2)} 亿元` : "未提供";
}

function valuationRows(value: Record<string, unknown>): Array<{ label: string; text: string }> {
  const rows: Array<{ label: string; text: string }> = [];
  const method = String(value.method || "");
  if (method) rows.push({ label: VALUATION_LABELS.method, text: METHOD_LABELS[method] || "综合估值" });
  const unavailableReason = String(value.reason || value.error || "").trim();
  if (unavailableReason) rows.push({ label: "不可用原因", text: sanitizeText(unavailableReason) });
  for (const key of ["low", "base", "high", "per_share"] as const) {
    if (value[key] != null) rows.push({ label: VALUATION_LABELS[key], text: yuanValue(value[key]) });
  }
  if (value.assumptions && typeof value.assumptions === "object" && !Array.isArray(value.assumptions)) {
    const parts = Object.entries(value.assumptions as Record<string, unknown>)
      .filter(([key]) => ["discount_rate", "revenue_growth", "terminal_growth", "cash_flow_margin"].includes(key))
      .map(([key, val]) => `${VALUATION_LABELS[key]} ${key === "cash_flow_margin" ? (val == null ? "未提供" : pctValue(val)) : pctValue(val)}`);
    if (parts.length) rows.push({ label: VALUATION_LABELS.assumptions, text: parts.join("；") });
  }
  if (value.equity_value != null) rows.push({ label: VALUATION_LABELS.equity_value, text: yiValue(value.equity_value) });
  if (value.enterprise_value != null) rows.push({ label: VALUATION_LABELS.enterprise_value, text: yiValue(value.enterprise_value) });
  if (value.net_debt_proxy && typeof value.net_debt_proxy === "object" && !Array.isArray(value.net_debt_proxy)) {
    const nd = value.net_debt_proxy as Record<string, unknown>;
    const label = sanitizeText(nd.label || "净债务口径");
    const text = nd.applicable === false ? label : `${label}：${yiValue(nd.value)}`;
    rows.push({ label: VALUATION_LABELS.net_debt_proxy, text });
  }
  if (value.note) rows.push({ label: VALUATION_LABELS.note, text: sanitizeText(value.note) });
  return rows;
}

function currentCaseId(key: string | null): number | null {
  const m = String(key || "").match(/case:(\d+)/);
  return m ? Number(m[1]) : null;
}

/** 展示完整论点，不截断。 */
function claimHeadline(value?: string): string {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  return clean || "—";
}

export function InstV3DebatePage() {
  const navigate = useNavigate();
  const session = useInstSession();
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
  const [advice, setAdvice] = useState<ProposalAdvice | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState<string | null>(null);

  const detailSeq = useRef(0);
  const autoDebateRef = useRef<string | null>(null);
  const selectedId = currentCaseId(params.get("key"));
  const version = detail?.versions?.[0] || null;
  const latestProposal = detail?.proposals?.[0] || null;

  const loadCases = async () => {
    const res = await instApi<{ items: CaseItem[] }>("/cases");
    const rows = (res.items || []).filter((c) => Number(c.stage_no ?? 1) === 2);
    setCases(latestByKey(rows, (c) => c.symbol, (c) => `${c.updated_at || ""}|${String(c.id).padStart(12, "0")}`));
    return rows;
  };

  const loadDetail = async (id: number) => {
    const seq = ++detailSeq.current;
    const d = await instApi<CaseItem>(`/cases/${id}`);
    if (seq !== detailSeq.current) return d;
    setDetail(d);
    const session = d.debates?.[0];
    if (session?.id) {
      const full = await instApi<Debate>(`/debates/${session.id}`);
      if (seq !== detailSeq.current) return d;
      setDebate(full);
    } else {
      setDebate(null);
    }
    return d;
  };

  /** 进入辩论模块：研究已锁定但没有完成辩论时，自动跑多空/主持/估值。 */
  const ensureDebate = async (id: number) => {
    if (session.role !== "manager") return;
    const key = `case:${id}`;
    if (autoDebateRef.current === key) return;
    autoDebateRef.current = key;
    try {
      const d = await instApi<CaseItem>(`/cases/${id}`);
      if (d.debates?.[0]?.status === "completed") return;
      const running = await latestAiJob(id, "debate");
      setBusy("auto-debate");
      if (running?.status === "running") {
        await waitAiJob(id, "debate");
      } else {
        await instApi(`/cases/${id}/debate`, { method: "POST", body: { use_ai: true, background: true } });
        await waitAiJob(id, "debate");
      }
      await loadDetail(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
      autoDebateRef.current = null;
    }
  };

  useEffect(() => {
    if (!detail?.id) return;
    const id = detail.id;
    let alive = true;
    (async () => {
      try {
        const job = await latestAiJob(id, "debate");
        if (!alive || !job || job.status !== "running") return;
        setBusy("auto-debate");
        await waitAiJob(id, "debate");
        if (alive) {
          await loadDetail(id);
          setStep(1);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setBusy(null);
      }
    })();
    return () => { alive = false; };
  }, [detail?.id]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadCases()
      .then(async (items) => {
        if (!alive) return;
        const id = selectedId || items[0]?.id || null;
        if (id) {
          if (!selectedId) {
            setParams({ key: `case:${id}` }, { replace: true });
            return;
          }
          const d = await loadDetail(id);
          void ensureDebate(id);
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

  const bull = useMemo(() => dedupeBy((debate?.arguments || []).filter((a) => a.side === "bull"), (a) => a.claim_id || a.id), [debate]);
  const bear = useMemo(() => dedupeBy((debate?.arguments || []).filter((a) => a.side === "bear"), (a) => a.claim_id || a.id), [debate]);
  const chiefReview = useMemo<ChairReview | null>(() => {
    const fp = debate?.factpack;
    if (!fp) return null;
    if (typeof fp !== "string") return fp.chief_review || null;
    try {
      return (JSON.parse(fp) as { chief_review?: ChairReview }).chief_review || null;
    } catch {
      return null;
    }
  }, [debate]);

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
    return [{ id: "trader", name: "交易员", code: "TRADER", model: "交易员 Agent", tools: "六维评分 / 辩论结论 / 组合约束", output: "议案建议 + 框架", role: "根据六维评分与辩论结论，给出买入/卖出结论、建议仓位与议案框架。" }];
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
      await instApi(`/cases/${detail.id}/debate`, { method: "POST", body: { use_ai: true, background: true } });
      await waitAiJob(detail.id, "debate");
      await loadDetail(detail.id);
      setStep(1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  useEffect(() => {
    if (!detail?.id || step !== 3) return;
    let alive = true;
    setAdviceLoading(true);
    setAdviceError(null);
    instApi<ProposalAdvice>(`/cases/${detail.id}/proposal-advice`)
      .then((data) => { if (alive) setAdvice(data.available === false ? null : data); })
      .catch((e: Error) => { if (alive) setAdviceError(e.message); })
      .finally(() => { if (alive) setAdviceLoading(false); });
    return () => { alive = false; };
  }, [detail?.id, step]);

  useEffect(() => {
    const f = advice?.framework;
    if (!f) return;
    if (f.price_low != null) setPriceLow((v) => v || String(f.price_low));
    if (f.price_high != null) setPriceHigh((v) => v || String(f.price_high));
    if (f.valid_until) setValidUntil((v) => v || String(f.valid_until));
    if (f.funding_source) setFunding((v) => v || String(f.funding_source));
    if (f.investment_opinion) setOpinion((v) => v || String(f.investment_opinion));
  }, [advice]);

  const proposalMissing = useMemo(() => {
    const out: string[] = [];
    if (!direction) out.push("方向");
    if (direction === "buy" && !(Number(target) > 0)) out.push("目标仓位");
    if (!priceLow.trim()) out.push("价格下限");
    if (!priceHigh.trim()) out.push("价格上限");
    if (!funding.trim()) out.push("资金来源");
    if (!validUntil.trim()) out.push("有效期");
    if (!monitoring.trim()) out.push("监控条件");
    if (!opinion.trim()) out.push("投资意见");
    return out;
  }, [direction, target, priceLow, priceHigh, funding, validUntil, monitoring, opinion]);

  const adoptAdvice = () => {
    const f = advice?.framework;
    if (!f) return;
    const nextDirection = String(f.direction || "");
    if (["buy", "sell", "exit"].includes(nextDirection)) setDirection(nextDirection);
    if (f.target_weight != null && Number(f.target_weight) > 0) setTarget(String(f.target_weight));
    setPriceLow(f.price_low != null ? String(f.price_low) : "");
    setPriceHigh(f.price_high != null ? String(f.price_high) : "");
    if (f.funding_source) setFunding(f.funding_source);
    if (f.valid_until) setValidUntil(f.valid_until);
    if (f.monitoring?.length) setMonitoring(f.monitoring.join("\n"));
    if (f.investment_opinion) setOpinion(f.investment_opinion);
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
  if (!detail) return <div className="v3-card">暂无可辩论的项目。请先锁定研究定稿。</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">DEBATE</div>
          <h1>{detail.company_name} · 多空辩论 <span className="font-mono text-[12px] font-normal text-[#6b6370]">{detail.symbol}</span></h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="v3-chip info">版本 {version?.version_no ?? detail.version_no ?? "—"}</span>
          <Link className="v3-btn ghost" to={`/inst/pipeline/result?key=${encodeURIComponent(`case:${detail.id}`)}`}>查看结果页</Link>
        </div>
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
              <span>{c.symbol} · 版本 {c.version_no ?? c.versions?.[0]?.version_no ?? "—"} · {c.proposals?.[0]?.status || (c.debates?.[0] ? "辩论完成" : "待辩论")}</span>
            </button>
          ))}
          {!cases.length ? <div className="v3-empty" style={{ padding: "16px" }}>暂无可辩论项目</div> : null}
        </div>

        <div className="v3-work-main">
          {error ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{error}</div> : null}

          {step === 0 ? (
            <section className="v3-card">
              <div className="v3-card-head">
                <div><h2>多空立论</h2><p>多头 / 空头逐条带证据；空头不重复行业空间。</p></div>
                {!debate ? <button className="v3-btn primary" disabled={!!busy} onClick={startDebate}><Play className="h-3.5 w-3.5" />{busy === "debate" ? "辩论生成中…" : "开始多空辩论"}</button> : <div className="flex items-center gap-2"><span className="v3-chip ok">已完成</span><button className="v3-btn ghost" disabled={!!busy} onClick={startDebate}>{busy === "debate" ? "生成中…" : "重新生成辩论"}</button></div>}
              </div>
              <InstV3AgentProgress
                active={busy === "debate" || busy === "auto-debate"}
                title="多头 / 空头 Agent 正在生成论点"
                detail="多头找买入理由，空头打最弱假设；每条论点完成前会持续显示进度。"
              />
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
                      </div>
                    </div>
                  ))}
                  {!activeSide.length ? <div className="v3-empty" style={{ marginTop: 8 }}>暂无{sideName}论点</div> : null}
                </div>
              ) : busy === "debate" ? null : <div className="v3-empty">还没有辩论记录。点击右上角开始；结论不投票，只保留分歧。</div>}
            </section>
          ) : null}

          {step === 1 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>交叉质询</h2><p>主持把双方 claim 逐条对齐，标出已回应 / 未回应 / 证据不足。</p></div><span className="v3-chip">{debate?.evidence_checks?.length || 0} 条核验</span></div>
              <InstV3AgentProgress
                active={busy === "debate" || busy === "auto-debate"}
                title="主持 Agent 正在交叉质询"
                detail="逐条核对多空论点与证据；完成后自动刷新质询记录。"
              />
              {debate ? (
                <>
                  {chiefReview ? (
                    <div style={{ marginTop: 8 }}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`v3-chip ${chiefReview.verdict === "support_proposal" ? "ok" : "warn"}`}>
                          {chiefReview.verdict === "support_proposal" ? "支持进入议案" : "补充研究"}
                        </span>
                        {chiefReview.chief_fields_fallback ? <span className="v3-chip warn">服务端补齐</span> : null}
                      </div>
                      <p style={{ marginTop: 8, lineHeight: 1.75, color: "#2b2533", fontWeight: 600 }}>
                        {chiefReview.chair_call || debate.conclusion || "主持结论待生成。"}
                      </p>
                      {chiefReview.consensus?.length ? (
                        <div style={{ marginTop: 8 }}>
                          <div className="v3-eyebrow">已达成共识</div>
                          <ul className="v3-rule-list" style={{ marginTop: 4 }}>{chiefReview.consensus.map((x) => <li key={x}>{x}</li>)}</ul>
                        </div>
                      ) : null}
                      {chiefReview.unresolved?.length ? (
                        <div style={{ marginTop: 8 }}>
                          <div className="v3-eyebrow">未决分歧</div>
                          {chiefReview.unresolved.map((u, i) => (
                            <div className="v3-claim" key={`${u.issue || "unresolved"}-${i}`}>
                              <div className="who">{u.issue || "未决问题"}</div>
                              {u.bull_view || u.bear_view ? <p>多：{u.bull_view || "—"}<br />空：{u.bear_view || "—"}</p> : null}
                              {u.why_unresolved ? <div className="fs">未决原因：{u.why_unresolved}</div> : null}
                              {u.data_needed ? <div className="fs">待补：{u.data_needed}</div> : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {(chiefReview.accepted_claims?.length || chiefReview.rejected_claims?.length) ? (
                        <div style={{ marginTop: 8 }}>
                          <div className="v3-eyebrow">采纳与不采纳</div>
                          {[...(chiefReview.accepted_claims || []), ...(chiefReview.rejected_claims || [])].map((c, i) => {
                            const claimText = c.claim || (debate?.arguments || []).find((a) => a.claim_id === c.claim_id)?.claim || "";
                            return (
                              <div className="v3-claim" key={`${c.claim_id || c.claim || "claim"}-${i}`}>
                                <div className="who">{c.side === "bull" ? "多方" : c.side === "bear" ? "空方" : c.side || "—"} {c.claim_id || ""}</div>
                                {claimText ? <p>{claimText}</p> : null}
                                {c.reason ? <div className="fs">{c.reason}</div> : null}
                              </div>
                            );
                          })}
                        </div>
                      ) : null}
                      {chiefReview.what_would_change?.length ? (
                        <div style={{ marginTop: 8 }}>
                          <div className="v3-eyebrow">什么会改变裁决</div>
                          <ul className="v3-rule-list" style={{ marginTop: 4 }}>{chiefReview.what_would_change.map((x) => <li key={x}>{x}</li>)}</ul>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="v3-note"><b>主持结论：</b>{debate.conclusion || "主持结论待生成。"}</div>
                  )}
                  {(() => {
                    const checks = dedupeBy(debate.evidence_checks || [], (c) => `${c.claim_id || ""}:${c.evidence_id || ""}`);
                    const verified = checks.filter((c) => c.status === "verified").length;
                    const pending = checks.length - verified;
                    const claimText = new Map(
                      (debate.arguments || []).filter((a) => a.claim_id).map((a) => [a.claim_id as string, a.claim]),
                    );
                    const groups = new Map<string, EvidenceCheck[]>();
                    for (const c of checks.slice(0, 12)) {
                      const key = c.claim_id || "未关联论点";
                      groups.set(key, [...(groups.get(key) || []), c]);
                    }
                    return (
                      <>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                          <span className="v3-chip">核验 {checks.length} 条</span>
                          <span className="v3-chip ok">已核验 {verified} 条</span>
                          <span className="v3-chip warn">待处理 {pending} 条</span>
                        </div>
                        {[...groups.entries()].map(([claimId, items]) => (
                          <div className="v3-claim" key={claimId}>
                            <div className="who">{claimId} · {claimHeadline(claimText.get(claimId))}</div>
                            {items.map((c, i) => {
                              const meta = CHECK_STATUS[String(c.status || "")] || { label: "待核验", tone: "warn" };
                              return (
                                <div className="v3-kv" key={`${claimId}-${c.evidence_id}-${i}`}>
                                  <dt>证据 #{c.evidence_id || "—"} · {c.grade || "—"} 级</dt>
                                  <dd>
                                    <span className={`v3-chip ${meta.tone}`}>{meta.label}</span>
                                    {c.issues?.length ? ` ${c.issues.join("；")}` : ""}
                                  </dd>
                                </div>
                              );
                            })}
                          </div>
                        ))}
                        {!checks.length ? <div className="v3-empty" style={{ marginTop: 8 }}>暂无证据核验明细；完成多空立论后会自动生成。</div> : null}
                      </>
                    );
                  })()}
                </>
              ) : <div className="v3-empty">先完成多空立论。</div>}
            </section>
          ) : null}

          {step === 2 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>估值复核</h2><p>数字来自确定性计算；AI 只解释假设，不生成数字。</p></div></div>
              {version?.valuation ? (() => {
                const rows = valuationRows(version.valuation);
                return rows.length ? (
                  <dl>
                    {rows.map((row) => (
                      <div className="v3-kv" key={row.label}><dt>{row.label}</dt><dd>{row.text}</dd></div>
                    ))}
                  </dl>
                ) : <div className="v3-empty">估值服务未返回可读字段。</div>;
              })() : (
                <div className="v3-empty">
                  该研究版本未产出估值数据。常见原因：自由现金流/净利为负、缺少总股本或行情价格；
                  请在价值分析页重跑“估值与价格”维度后再看。
                  <div style={{ marginTop: 8 }}>
                    <Link className="v3-btn ghost" to={`/inst/research?key=${encodeURIComponent(`case:${detail.id}`)}`}>
                      去价值分析重跑估值
                    </Link>
                  </div>
                </div>
              )}
            </section>
          ) : null}

          {step === 3 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>议案 · 锁定</h2><p>补齐投资意见、仓位、价格带、资金、有效期与监控条件；锁定后审批角色只读。</p></div>{latestProposal ? <span className="v3-chip ok">{latestProposal.status}</span> : <span className="v3-chip warn">待创建</span>}</div>
              {adviceLoading ? (
                <InstV3AgentProgress active title="交易员 Agent 正在生成议案建议" detail="汇总六维评分、辩论结论与仓位约束，完成后自动填入下方表单。" />
              ) : adviceError ? (
                <div className="v3-note">议案建议加载失败：{adviceError}</div>
              ) : advice ? (
                <div className="v3-advice">
                  <div className="v3-advice-top">
                    <div>
                      <div className="v3-eyebrow">TRADER AGENT</div>
                      <h3>议案建议</h3>
                      <p>{advice.rationale}</p>
                    </div>
                    <div className={`v3-advice-reco ${advice.recommendation || "avoid"}`}>
                      <b>{advice.recommendation_label || "暂不买入"}</b>
                      <span>建议仓位 {((advice.framework?.target_weight || 0) * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="v3-advice-scores">
                    {(advice.scores || []).map((s) => (
                      <div key={s.key || s.title}>
                        <span>{s.title || s.key}</span>
                        <b>{s.score_10 != null ? `${Number(s.score_10).toFixed(1)}/10` : "未评分"}</b>
                      </div>
                    ))}
                  </div>
                  <div className="v3-kv">
                    <dt>多空辩论最终结论</dt>
                    <dd>{advice.debate?.conclusion || "尚未形成结论"}（多 {advice.debate?.bull_count || 0} / 空 {advice.debate?.bear_count || 0}）</dd>
                  </div>
                  <div className="v3-kv">
                    <dt>综合得分</dt>
                    <dd>{advice.overall_score != null ? `${Number(advice.overall_score).toFixed(1)}/10` : "未评分"}</dd>
                  </div>
                  <div className="v3-advice-framework">
                    <div className="v3-eyebrow">议案框架</div>
                    <dl>
                      <div className="v3-kv"><dt>方向</dt><dd>{({ buy: "买入", sell: "卖出", hold: "持有", exit: "退出" } as Record<string, string>)[advice.framework?.direction || "buy"] || advice.framework?.direction}</dd></div>
                      <div className="v3-kv"><dt>目标仓位</dt><dd>{((advice.framework?.target_weight || 0) * 100).toFixed(1)}%</dd></div>
                      <div className="v3-kv"><dt>价格区间</dt><dd>{advice.framework?.price_low != null ? `${advice.framework.price_low} – ${advice.framework.price_high}` : "—"}</dd></div>
                      <div className="v3-kv"><dt>资金来源 / 有效期</dt><dd>{advice.framework?.funding_source || "现金"} · {advice.framework?.valid_until || "—"}</dd></div>
                      <div className="v3-kv"><dt>监控条件</dt><dd>{advice.framework?.monitoring?.join("；") || "—"}</dd></div>
                    </dl>
                    <div className="v3-note" style={{ marginTop: 8 }}>投资意见：{advice.framework?.investment_opinion || "—"}</div>
                  </div>
                  {advice.recommendation === "avoid" || advice.recommendation === "hold" ? (
                    <div className="v3-note" style={{ marginTop: 8 }}>
                      主持裁决为“补充研究”，AI 建议暂不买入。采纳只填入价格带、监控条件和投资意见；方向与仓位由投资经理自行判断后提交。
                    </div>
                  ) : null}
                  <button className="v3-btn primary" style={{ marginTop: 8 }} disabled={!advice} onClick={adoptAdvice}>
                    采用建议填入议案
                  </button>
                </div>
              ) : null}
              {latestProposal && latestProposal.status !== "draft" ? (
                <div>
                  <div className="v3-note">议案已锁定并进入审批：{latestProposal.status}</div>
                  <div style={{ marginTop: 8 }}><Link className="v3-btn primary" to={`/inst/approvals?key=${encodeURIComponent(`proposal:${latestProposal.id}`)}`}>进入投委会审批 <ArrowRight className="h-3.5 w-3.5" /></Link></div>
                </div>
              ) : (
                <>
                  <div className="v3-form-grid">
                    <div className="v3-field"><label>方向</label><select value={direction} onChange={(e) => setDirection(e.target.value)}><option value="buy">买入</option><option value="sell">卖出</option><option value="exit">退出</option></select></div>
                    <div className="v3-field"><label>目标仓位</label><input data-testid="inst-proposal-target" value={target} onChange={(e) => setTarget(e.target.value)} /></div>
                    <div className="v3-field"><label>价格下限（CNY）</label><input data-testid="inst-price-low" value={priceLow} onChange={(e) => setPriceLow(e.target.value)} /></div>
                    <div className="v3-field"><label>价格上限（CNY）</label><input data-testid="inst-price-high" value={priceHigh} onChange={(e) => setPriceHigh(e.target.value)} /></div>
                    <div className="v3-field"><label>资金来源</label><select value={funding} onChange={(e) => setFunding(e.target.value)}><option>现金</option><option>减仓换仓</option></select></div>
                    <div className="v3-field"><label>有效期</label><input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></div>
                    <div className="v3-field span-2"><label>投资意见</label><textarea data-testid="inst-investment-opinion" value={opinion} onChange={(e) => setOpinion(e.target.value)} placeholder="写清为什么投、关键假设、最担心什么、什么情况下改变判断。" /></div>
                    <div className="v3-field span-2"><label>监控 / 退出条件</label><textarea value={monitoring} onChange={(e) => setMonitoring(e.target.value)} /></div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, marginTop: 8 }}>
                    {proposalMissing.length ? <span className="v3-note" style={{ margin: 0 }}>还需填写：{proposalMissing.join("、")}</span> : null}
                    <button data-testid="inst-proposal-create" className="v3-btn primary" disabled={!!busy || proposalMissing.length > 0} onClick={createProposal}><Send className="h-3.5 w-3.5" />{busy === "proposal" ? "锁定中…" : "锁定议案并提交审批"}</button>
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
            { label: "本步产出", value: step === 0 ? "多空论点" : step === 1 ? "分歧清单" : step === 2 ? "估值复核" : "议案" },
            { label: "输入", value: "研究定稿、证据包、FactPack；不引用旧辩论输出作为证据。" },
            { label: "约束", value: "辩论不投票、不取平均；估值数字由代码生成；锁定后审批只读。" },
          ]}
        />
      </div>
    </>
  );
}
