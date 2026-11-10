import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, RefreshCw, Sparkles } from "lucide-react";
import { dedupeBy, latestByKey } from "@/lib/instDedupe";
import { useInstSession } from "@/components/institution/instSessionContext";
import { instApi } from "@/lib/instApi";
import { InstV3AgentRail, type AgentPanelDef } from "@/components/institution/v3/InstV3AgentRail";

type Dim = {
  key: string;
  title?: string;
  agent_tier?: string;
  role_title?: string;
  question?: string;
  summary?: string;
  impact?: string;
  data_used?: string[];
  status?: string;
  rating?: number | null;
  score_10?: number | null;
  rating_benchmark?: string | null;
  rating_note?: string | null;
  confidence?: number | null;
  gate?: string | null;
  checks?: string[];
  counter?: string[];
  data_gaps?: string[];
  evidence_ids?: number[];
  data_completeness?: { level?: string; have?: string[]; missing?: string[]; gate_cap?: string };
  analysis_md?: string;
  engine?: string;
};

type DimReview = {
  decision?: string;
  comment?: string | null;
  reviewer_member_id?: number;
  at?: string;
};

type Version = {
  id: number;
  version_no: number;
  status: string;
  conclusion?: string;
  six_dim?: Dim[];
  dim_reviews?: Record<string, DimReview>;
  industry_analysis?: Dim | null;
  valuation?: Record<string, unknown> | null;
  evidence_ids?: number[];
  content_hash?: string;
  frozen_at?: string;
  locked_at?: string;
};

type GateCheck = { key: string; label: string; status: string; detail: string };
type ResearchGate = { status: string; checks: GateCheck[] };

type Memo = {
  summary?: string;
  decision?: string;
  schema_version?: string;
  agent_tier?: string;
  role_title?: string;
  chief_call?: string;
  chief_reasons?: Array<{
    agent_key?: string;
    agent_name?: string;
    reason?: string;
    evidence_ids?: Array<number | string>;
    data?: string;
  }>;
  strongest_counterpoint?: {
    point?: string;
    response?: string;
    evidence_ids?: Array<number | string>;
    overturns?: boolean;
  } | string | null;
  key_assumptions?: string[];
  what_would_change?: string[];
  professional_coverage?: Array<{
    key?: string;
    name?: string;
    role_title?: string;
    tier?: string;
    score_10?: number | null;
    rating_benchmark?: string | null;
    gate?: string | null;
    confidence?: number | null;
    verdict?: string;
  }>;
  chief_confidence?: number | null;
  decision_original?: string | null;
  decision_note?: string | null;
  chief_fields_fallback?: boolean;
  agent_trace?: Array<{ tool?: string; args?: Record<string, unknown>; ok?: boolean; summary?: string }>;
  legacy?: boolean;
  overall_score?: number | null;
  six_dim_scores?: Array<{ key: string; score: number; confidence?: number; note?: string }>;
  conflicts?: string[];
  key_variables?: string[];
  risks?: string[];
  open_questions?: string[];
  price_range?: { low?: number; base?: number; high?: number } | null;
  metrics?: Array<{ label: string; value: string; note?: string }>;
  engine?: string;
  data_gate_note?: string;
};

type CaseItem = {
  id: number;
  case_no: string;
  stage: string;
  stage_no?: number;
  stage_key?: string;
  symbol: string;
  company_name: string;
  industry?: string;
  data_status?: string;
  ref_price?: number;
  version_no?: number | null;
  version_status?: string | null;
  updated_at?: string | null;
  overall_score?: number | null;
  versions?: Version[];
};

function dimScore(dim?: Dim | null): number | null {
  if (!dim) return null;
  if (dim.score_10 != null) return Number(dim.score_10);
  if (dim.rating != null) return Math.round(Number(dim.rating) * 20) / 10;
  if (dim.engine === "rule") {
    const base = dim.gate === "pass" ? 8.0 : dim.gate === "fail" ? 3.0 : 5.5;
    const confidence = dim.confidence;
    const adjusted =
      typeof confidence === "number" ? base + (confidence - 0.5) * 2 : base;
    return Math.round(Math.max(0, Math.min(10, adjusted)) * 10) / 10;
  }
  return null;
}

function paragraphs(text?: string | null): string[] {
  return String(text || "")
    .split(/\n{2,}/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function overallScore(dims?: Dim[] | null, fallback?: number | null): number | null {
  if (fallback != null) return Number(fallback);
  const scores = (dims || []).map((d) => dimScore(d)).filter((n): n is number => n != null);
  if (!scores.length) return null;
  return Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
}

function stripParens(value?: string): string {
  return String(value || "").replace(/[（(][^）)]*[）)]/g, "").trim();
}

const DIMS: Array<[string, string]> = [
  ["industry", "产业研究"],
  ["business_model", "商业模式"],
  ["moat", "护城河"],
  ["financial", "财务质量"],
  ["governance", "CEO 与治理"],
  ["valuation", "估值与价格"],
];

const STEPS = [
  { name: "行业分析", sub: "独立底图 · 不占六维", agent: "行业研究员", duty: "只回答行业本身：空间、增速、格局、产业链与关键变量，为六维提供底图。" },
  { name: "六维结论", sub: "六维研究员并行", agent: "六维研究员", duty: "产业 / 商业模式 / 护城河 / 财务 / 治理 / 估值各管一维；每条结论带证据与证伪。" },
  { name: "一页纸", sub: "研究经理合成 · 三问", agent: "研究经理", duty: "只做裁决：该不该投、什么价投、最可能错在哪；保留矛盾，不做平均数。" },
  { name: "研究定稿", sub: "归档版本 · 移交辩论", agent: "研究经理 + 归档", duty: "确认六维齐全、低置信项已处理、总体得分与证据包；锁定研究定稿，移交辩论。" },
];

function currentCaseId(key: string | null): number | null {
  const m = String(key || "").match(/case:(\d+)/);
  return m ? Number(m[1]) : null;
}

export function InstV3ResearchPage() {
  const [params, setParams] = useSearchParams();
  const session = useInstSession();
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [detail, setDetail] = useState<CaseItem | null>(null);
  const [memo, setMemo] = useState<Memo | null>(null);
  const [step, setStep] = useState(0);
  const [dimKey, setDimKey] = useState("moat");
  const [agentId, setAgentId] = useState("industry");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gate, setGate] = useState<ResearchGate | null>(null);
  const [gateLoading, setGateLoading] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [allowGaps, setAllowGaps] = useState(false);

  const detailSeq = useRef(0);
  const autoRunRef = useRef<string | null>(null);
  const selectedId = currentCaseId(params.get("key"));

  const loadCases = async () => {
    const res = await instApi<{ items: CaseItem[] }>("/cases");
    const eligible = (res.items || []).filter((c) => Number(c.stage_no ?? 1) <= 2);
    setCases(latestByKey(eligible, (c) => c.symbol, (c) => `${c.updated_at || ""}|${String(c.id).padStart(12, "0")}`));
    return eligible;
  };

  const loadDetail = async (id: number) => {
    const seq = ++detailSeq.current;
    setGate(null);
    setGateLoading(true);
    const d = await instApi<CaseItem>(`/cases/${id}`);
    if (seq !== detailSeq.current) return d;
    setDetail(d);
    const version = d.versions?.[0];
    if (version) {
      const found = (version.six_dim || []).find((x) => x.key === dimKey);
      if (!found && version.six_dim?.length) setDimKey(version.six_dim[0].key);
      try {
        const nextGate = await instApi<ResearchGate>(`/research/${version.id}/gate`);
        if (seq === detailSeq.current) setGate(nextGate);
      } catch {
        if (seq === detailSeq.current) setGate(null);
      } finally {
        if (seq === detailSeq.current) setGateLoading(false);
      }
    } else {
      setGate(null);
      setGateLoading(false);
    }
    return d;
  };

  const loadMemo = async (id: number): Promise<Memo | null> => {
    try {
      const res = await instApi<{ memo: Memo | null; missing?: boolean }>(`/cases/${id}/ai/memo`);
      if (res.memo) {
        setMemo(res.memo);
        return res.memo;
      }
    } catch {
      // memo is advisory; ignore peek errors
    }
    return null;
  };

  /** 进入价值分析自动补齐：缺行业/六维先全量生成，缺一页纸再生成并落盘。 */
  const ensureFullFlow = async (id: number) => {
    if (session.role !== "manager") return;
    const key = `case:${id}`;
    if (autoRunRef.current === key) return;
    autoRunRef.current = key;
    try {
      const d = await instApi<CaseItem>(`/cases/${id}`);
      const v = d.versions?.[0];
      const hasDims = Boolean(v?.six_dim?.length);
      const hasIndustry = Boolean(v?.industry_analysis?.summary);
      if (!hasDims || !hasIndustry) {
        setBusy("auto-research");
        await instApi(`/cases/${id}/research`, { method: "POST", body: { mode: "full" } });
        await loadDetail(id);
      }
      const cached = await loadMemo(id);
      if (!cached) {
        setBusy("auto-memo");
        const res = await instApi<{ memo: Memo }>(`/cases/${id}/ai/memo`, {
          method: "POST",
          body: { refresh: false },
        });
        setMemo(res.memo);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
      autoRunRef.current = null;
    }
  };

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
          } else {
            await loadDetail(id);
            await loadMemo(id);
            void ensureFullFlow(id);
          }
        }
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const version = detail?.versions?.[0] || null;
  const overall = overallScore(
    version?.six_dim,
    detail?.overall_score ?? memo?.overall_score ?? null,
  );
  const dims = useMemo(() => dedupeBy(version?.six_dim || [], (d) => d.key), [version]);
  const activeDim = dims.find((d) => d.key === dimKey) || dims[0] || null;
  const counterpoint =
    typeof memo?.strongest_counterpoint === "string"
      ? { point: memo.strongest_counterpoint, response: "", overturns: false }
      : memo?.strongest_counterpoint || null;
  const blockingGateNote =
    memo?.data_gate_note && (memo.data_gate_note.includes("gate=fail") || memo.data_gate_note.includes("门禁未通过"))
      ? memo.data_gate_note
      : "";

  useEffect(() => {
    setAgentId(step === 0 ? "industry" : "manager");
  }, [step]);

  const agentDefs = useMemo<AgentPanelDef[]>(() => {
    if (step === 1) {
      return DIMS.map(([key, label]) => {
        const dim = dims.find((x) => x.key === key);
        return {
          id: key,
          name: label,
          code: "ANALYST",
          model: "六维 Agent",
          tools: "证据库 / 公告 / 财报",
          output: dim ? (dim.status === "skipped" ? "待补数据" : "结论已生成") : "待生成",
          role: `只负责「${label}」这一维，逐条带证据与证伪条件。`,
        };
      });
    }
    if (step === 0) {
      return [{ id: "industry", name: "行业研究员", code: "ANALYST", model: "行业 Agent", tools: "招标 / 协会 / 财报", output: "行业底图", role: "只回答行业空间、增速、格局与关键变量，不占六维。" }];
    }
    if (step === 2) {
      return [{ id: "manager", name: "研究经理", code: "MANAGER", model: "研究经理 Agent", tools: "六维 / 底图 / 模板", output: "一页纸 · 三问裁决", role: "合成六维、裁决矛盾，不重写单维结论。" }];
    }
    return [
      { id: "manager", name: "研究经理", code: "MANAGER", model: "研究经理 Agent", tools: "一页纸 / 未决分歧", output: "研究定稿", role: "确认定稿内容与版本。" },
      { id: "archivist", name: "研究归档", code: "VERSION", model: "确定性服务", tools: "版本 / 总体得分 / 证据包", output: "定稿记录", role: "保存定稿、总体得分与证据对应关系。", engine: true },
    ];
  }, [step, dims]);

  const activeAgentId = step === 1 ? dimKey : agentId;
  const selectAgent = (id: string) => {
    if (step === 1) setDimKey(id);
    else setAgentId(id);
  };

  const selectCase = (id: number) => {
    setStep(0);
    setAgentId("industry");
    setMemo(null);
    setParams({ key: `case:${id}` });
  };

  const runResearch = async (mode: "full" | string, label: string) => {
    if (!detail) return;
    setBusy(label);
    setError(null);
    try {
      await instApi(`/cases/${detail.id}/research`, { method: "POST", body: { mode } });
      await loadDetail(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const runMemo = async (refresh: boolean) => {
    if (!detail) return;
    setBusy("memo");
    setError(null);
    try {
      const res = await instApi<{ memo: Memo }>(`/cases/${detail.id}/ai/memo`, {
        method: "POST",
        body: { refresh },
      });
      setMemo(res.memo);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const lockResearch = async (withGaps = false) => {
    if (!version) return;
    setBusy(withGaps ? "lock-gaps" : "lock");
    setError(null);
    try {
      const res = await instApi<Record<string, unknown>>(`/research/${version.id}/lock`, {
        method: "POST",
        body: withGaps
          ? { allow_gaps: true, comment: "研究经理已确认数据缺口，带缺口锁定研究定稿" }
          : {},
      });
      setDetail(res as unknown as CaseItem);
      setGate(null);
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const reviewLowDimension = async (key: string) => {
    if (!version || !detail) return;
    setBusy(`review:${key}`);
    setError(null);
    try {
      await instApi(`/research/${version.id}/dimensions/${key}/review`, {
        method: "POST",
        body: {
          decision: "approve",
          comment: reviewNote.trim() || "研究经理复核确认：低置信项已处理",
        },
      });
      setReviewNote("");
      await loadDetail(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <div className="v3-loading">正在加载价值分析…</div>;
  if (error && !detail) return <div className="v3-card">加载失败：{error}</div>;
  if (!detail) return <div className="v3-card">暂无可研究的项目。请先在项目流水线完成立项。</div>;

  const locked = Boolean(version?.locked_at || version?.frozen_at);
  const gateBlocked = gate?.status === "block";
  const lowDims = dims.filter(
    (d) =>
      (d.rating != null && Number(d.rating) < 3.3) ||
      (d.confidence != null && Number(d.confidence) < 0.66),
  );
  const unresolvedLow = lowDims.filter(
    (d) => version?.dim_reviews?.[d.key]?.decision !== "approve",
  );

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">RESEARCH</div>
          <h1>{detail.company_name} <span className="font-mono text-[12px] font-normal text-[#6b6370]">{detail.symbol}</span></h1>
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
          <div className="pl-head"><span>在研项目</span><span>{cases.length}</span></div>
          {cases.map((c) => (
            <button key={c.id} className={`pl-item${c.id === detail.id ? " on" : ""}`} onClick={() => selectCase(c.id)}>
              <b>{c.company_name}</b>
              <span>{c.symbol} · 版本 {c.version_no ?? "—"} · {c.stage_no === 2 ? "已定稿" : "价值分析"}</span>
            </button>
          ))}
          {!cases.length ? <div className="v3-empty" style={{ padding: "16px" }}>暂无在研项目</div> : null}
        </div>

        <div className="v3-work-main">
          {error ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{error}</div> : null}

          {step === 0 ? (
            <section className="v3-card">
              <div className="v3-card-head">
                <div><h2>行业分析（独立底图）</h2><p>不属于六维；只回答行业空间、增速、格局与关键变量。</p></div>
                <button className="v3-btn ghost" disabled={!!busy} onClick={() => runResearch("full", "industry")}>
                  <RefreshCw className="h-3.5 w-3.5" />{busy === "industry" ? "生成中…" : version?.industry_analysis ? "重跑行业分析" : "生成行业分析"}
                </button>
              </div>
              {version?.industry_analysis ? (
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="v3-chip ok">已完成</span>
                    <span className="v3-chip">{version.industry_analysis.engine || "AI Agent"}</span>
                  </div>
                  <p style={{ marginTop: 8, lineHeight: 1.75, color: "#4b4352" }}>{version.industry_analysis.summary || "行业分析已生成。"}</p>
                  {paragraphs(version.industry_analysis.analysis_md).map((p, i) => (
                    <p key={`industry-${i}`} style={{ marginTop: 8, lineHeight: 1.85, color: "#4b4352" }}>{p}</p>
                  ))}
                  {version.industry_analysis.impact ? <div className="v3-note" style={{ marginTop: 8 }}>影响：{version.industry_analysis.impact}</div> : null}
                  {version.industry_analysis.checks?.length ? (
                    <div style={{ marginTop: 8 }}>
                      <div className="v3-eyebrow">关键数据</div>
                      <ul className="v3-rule-list" style={{ marginTop: 4 }}>{version.industry_analysis.checks.map((x) => <li key={x}>{x}</li>)}</ul>
                    </div>
                  ) : null}
                  {version.industry_analysis.data_used?.length ? <p style={{ marginTop: 8, fontSize: 12, color: "#6b6370" }}>使用数据：{version.industry_analysis.data_used.join("；")}</p> : null}
                  {version.industry_analysis.counter?.length ? <div className="v3-note" style={{ marginTop: 8 }}>反证：{version.industry_analysis.counter[0]}</div> : null}
                </div>
              ) : (
                <div className="v3-empty">
                  还没有独立行业分析。点击右上角生成，或在六维全量生成时一并产出。
                  <div style={{ marginTop: 8 }}><button className="v3-btn primary" disabled={!!busy} onClick={() => runResearch("full", "full")}>{busy === "full" ? "六维生成中…" : "生成六维分析"}</button></div>
                </div>
              )}
            </section>
          ) : null}

          {step === 1 ? (
            <section className="v3-card">
              <div className="v3-card-head"><div><h2>六维结论</h2><p>六位研究员各管一维；点标签切换，主区只显示当前一维。</p></div><span className="v3-chip">{dims.length} 维</span></div>
              {dims.length ? (
                <>
                  <div className="v3-dim-list">
                    {DIMS.map(([key, label]) => {
                      return <button key={key} className={`v3-dim-btn${activeDim?.key === key ? " on" : ""}`} onClick={() => setDimKey(key)}>{label}</button>;
                    })}
                  </div>
                  {activeDim ? (
                    <div>
                      <div className="v3-dim-head">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`v3-chip ${activeDim.status === "skipped" ? "warn" : "ok"}`}>
                            {activeDim.status === "skipped" ? "未分析" : "已分析"}
                          </span>
                          {activeDim.confidence != null ? <span className="v3-chip">置信度 {activeDim.confidence.toFixed ? activeDim.confidence.toFixed(2) : activeDim.confidence}</span> : null}
                          {version?.dim_reviews?.[activeDim.key]?.decision === "approve" ? <span className="v3-chip ok">低置信已复核</span> : null}
                        </div>
                        {dimScore(activeDim) == null && activeDim.status === "skipped" ? null : (
                          <div className={`v3-dim-score${dimScore(activeDim) == null ? " empty" : ""}`}>
                            <span className="lab">{activeDim.engine === "rule" ? "规则评分" : "Agent 评分"}</span>
                            <span className="num">
                              {dimScore(activeDim) != null ? dimScore(activeDim)!.toFixed(1) : "未评分"}
                              {dimScore(activeDim) != null ? <small>/10</small> : null}
                            </span>
                          </div>
                        )}
                      </div>
                      <p style={{ marginTop: 8, lineHeight: 1.75, color: "#4b4352" }}>{activeDim.summary || "待补充"}</p>
                      {paragraphs(activeDim.analysis_md).map((p, i) => (
                        <p key={`${activeDim.key}-analysis-${i}`} style={{ marginTop: 8, lineHeight: 1.85, color: "#4b4352" }}>{p}</p>
                      ))}
                      {activeDim.impact ? <div className="v3-note" style={{ marginTop: 8 }}>影响：{activeDim.impact}</div> : null}
                      {activeDim.checks?.length ? (
                        <div style={{ marginTop: 8 }}>
                          <div className="v3-eyebrow">关键数据</div>
                          <ul className="v3-rule-list" style={{ marginTop: 4 }}>{activeDim.checks.map((x) => <li key={x}>{x}</li>)}</ul>
                        </div>
                      ) : null}
                      {activeDim.data_used?.length ? <p style={{ marginTop: 8, fontSize: 12, color: "#6b6370" }}>使用数据：{activeDim.data_used.join("；")}</p> : null}
                      {activeDim.counter?.length ? <div className="v3-note" style={{ marginTop: 8 }}>反证：{activeDim.counter[0]}</div> : null}
                      <div style={{ marginTop: 8 }}>
                        <button className="v3-btn ghost" disabled={!!busy || activeDim.status === "skipped"} onClick={() => runResearch(activeDim.key, activeDim.key)}>
                          <RefreshCw className="h-3.5 w-3.5" />
                          {activeDim.status === "skipped" ? "数据补齐后可重跑" : busy === activeDim.key ? "本维生成中…" : "只重跑本维"}
                        </button>
                      </div>
                    </div>
                  ) : <div className="v3-empty">该维还没有结论。</div>}
                </>
              ) : (
                <div className="v3-empty">还没有六维结论。<button className="v3-btn primary" style={{ marginLeft: 8 }} disabled={!!busy} onClick={() => runResearch("full", "full")}>{busy === "full" ? "生成中…" : "生成六维分析"}</button></div>
              )}
            </section>
          ) : null}

          {step === 2 ? (
            <section className="v3-card">
              <div className="v3-card-head">
                <div><h2>AI 一页纸</h2><p>研究经理把六维与行业底图压成一页：该不该投、什么价、最可能错在哪。</p></div>
                <button className="v3-btn ghost" disabled={!!busy} onClick={() => runMemo(!!memo)}>
                  <Sparkles className="h-3.5 w-3.5" />{busy === "memo" ? "生成中…" : memo ? "重新生成一页纸" : "生成一页纸"}
                </button>
              </div>
              {memo ? (
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    {memo.decision ? <span className={`v3-chip ${memo.decision === "proceed" ? "ok" : memo.decision === "avoid" ? "bad" : "warn"}`}>{memo.decision}</span> : null}
                    {memo.engine ? <span className="v3-chip">{memo.engine}</span> : null}
                    {memo.chief_confidence != null ? <span className="v3-chip">置信 {Number(memo.chief_confidence).toFixed(2)}</span> : null}
                    {memo.decision_original ? <span className="v3-chip warn">原判 {memo.decision_original} · 门禁降级</span> : null}
                    {memo.chief_fields_fallback ? <span className="v3-chip warn">服务端补齐</span> : null}
                    <span className="v3-memo-score"><span>六维总分</span><b>{overall != null ? overall.toFixed(1) : "未评分"}</b>{overall != null ? <small>/10</small> : null}<em>六维平均</em></span>
                  </div>
                  <p style={{ marginTop: 8, lineHeight: 1.75, color: "#2b2533", fontWeight: 600 }}>{memo.chief_call || memo.summary || "—"}</p>
                  {memo.agent_trace?.length ? (
                    <div className="v3-note" style={{ marginTop: 8 }}>
                      Agent 查证：{memo.agent_trace.map((x, i) => `${x.tool || "tool"}${x.summary ? `（${x.summary}）` : ""}`).join(" · ")}
                    </div>
                  ) : null}
                  {memo.chief_reasons?.length ? (
                    <div style={{ marginTop: 10 }}>
                      <div className="v3-eyebrow">三条理由</div>
                      {memo.chief_reasons.slice(0, 3).map((r, i) => (
                        <div className="v3-claim" key={`${r.agent_key || "reason"}-${i}`}>
                          <div className="who">{r.agent_name || r.agent_key || `理由 ${i + 1}`}</div>
                          <p>{r.reason || "—"}</p>
                          <div className="claim-meta">
                            {r.evidence_ids?.length ? <span className="v3-chip">证据 {r.evidence_ids.length} 条</span> : <span className="v3-chip warn">无证据 ID</span>}
                            {r.data ? <span className="v3-chip">{r.data}</span> : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {counterpoint?.point ? (
                    <div className="v3-note" style={{ marginTop: 8 }}>
                      <b>最强反证：</b>{counterpoint.point}
                      {counterpoint.response ? ` 回应：${counterpoint.response}` : ""}
                      {counterpoint.overturns ? <span className="v3-chip bad" style={{ marginLeft: 6 }}>足以推翻</span> : null}
                    </div>
                  ) : null}
                  {memo.key_assumptions?.length ? <div style={{ marginTop: 8 }}><div className="v3-eyebrow">关键假设</div><ul className="v3-rule-list" style={{ marginTop: 4 }}>{memo.key_assumptions.map((x) => <li key={x}>{x}</li>)}</ul></div> : null}
                  {memo.what_would_change?.length ? <div style={{ marginTop: 8 }}><div className="v3-eyebrow">什么会改变判断</div><ul className="v3-rule-list" style={{ marginTop: 4 }}>{memo.what_would_change.map((x) => <li key={x}>{x}</li>)}</ul></div> : null}
                  {memo.metrics?.length ? <div className="v3-kpis" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", marginTop: 8 }}>{memo.metrics.slice(0, 4).map((m) => <div className="v3-kpi" key={m.label}><div className="k">{stripParens(m.label)}</div><div className="v">{stripParens(m.value)}</div></div>)}</div> : null}
                  {memo.summary && memo.summary !== memo.chief_call ? <p style={{ marginTop: 8, lineHeight: 1.75, color: "#4b4352" }}>{memo.summary}</p> : null}
                  {memo.conflicts?.length ? <div className="v3-note" style={{ marginTop: 8 }}>保留分歧：{memo.conflicts.join("；")}</div> : null}
                  {memo.risks?.length ? <div style={{ marginTop: 8 }}><div className="v3-eyebrow">核心风险</div><ul className="v3-rule-list" style={{ marginTop: 4 }}>{memo.risks.slice(0, 4).map((x) => <li key={x}>{x}</li>)}</ul></div> : null}
                  {blockingGateNote ? <div className="v3-note" style={{ marginTop: 8 }}>{blockingGateNote}</div> : null}
                </div>
              ) : <div className="v3-empty">还没有一页纸。点击右上角生成；它不会替代六维原始证据。</div>}
            </section>
          ) : null}

          {step === 3 ? (
            <section className="v3-card">
              <div className="v3-card-head">
                <div><h2>研究定稿</h2><p>六维齐全、低置信项已处理、数据门禁通过后锁定研究定稿；锁定后辩论只读这一版。</p></div>
                {locked ? <span className="v3-chip ok">已锁定</span> : gateLoading ? <span className="v3-chip">门禁检查中…</span> : <span className={`v3-chip ${gate?.status === "pass" ? "ok" : gate?.status === "warn" ? "warn" : "bad"}`}>门禁 {gate?.status || "未检查"}</span>}
              </div>
              <div className="v3-final-score">
                <span>总体得分</span>
                <b>{overall != null ? overall.toFixed(1) : "未评分"}</b>
                {overall != null ? <small>/10</small> : null}
                <em>六维平均</em>
              </div>
              <dl>
                <div className="v3-kv"><dt>研究版本</dt><dd>{version ? `R${version.version_no} · ${version.status}` : "—"}</dd></div>
                <div className="v3-kv"><dt>证据条数</dt><dd>{version?.evidence_ids?.length ?? 0}</dd></div>
                <div className="v3-kv"><dt>锁定时间</dt><dd>{version?.locked_at || version?.frozen_at || "—"}</dd></div>
              </dl>

              {gate?.checks?.length ? (
                <div style={{ marginTop: 8 }}>
                  {gate.checks.map((c) => (
                    <div className="v3-kv" key={c.key}>
                      <dt>{c.label}</dt>
                      <dd>{c.detail} <span className={`v3-chip ${c.status === "pass" ? "ok" : c.status === "warn" ? "warn" : "bad"}`}>{c.status}</span></dd>
                    </div>
                  ))}
                </div>
              ) : null}

              {unresolvedLow.length ? (
                <div className="v3-note" style={{ marginTop: 8, borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>
                  <b>低置信项未复核：</b>{unresolvedLow.map((d) => d.title || d.key).join("、")}。逐项复核通过后才能正常锁定；无法补齐时也可在下方显式带缺口锁定。
                  <div className="v3-field" style={{ marginTop: 8 }}>
                    <label>复核说明（写入审计）</label>
                    <input value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="例如：已核对原始公告，置信度低来自披露粒度，不影响结论。" />
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                    {unresolvedLow.map((d) => (
                      <button
                        key={d.key}
                        className="v3-btn ghost"
                        disabled={!!busy}
                        onClick={() => reviewLowDimension(d.key)}
                      >
                        {busy === `review:${d.key}` ? "复核中…" : `复核通过 · ${d.title || d.key}`}
                      </button>
                    ))}
                  </div>
                </div>
              ) : lowDims.length ? (
                <div className="v3-note" style={{ marginTop: 8 }}>低置信项已全部复核通过。</div>
              ) : null}

              {gateBlocked && unresolvedLow.length === 0 ? (
                <div className="v3-note" style={{ marginTop: 8 }}>门禁仍有阻断项；请回上一步补齐六维或重跑对应维度。确实无法补齐时，可显式带缺口锁定并记录。</div>
              ) : null}

              {!locked && !gateLoading && gate === null ? (
                <div className="v3-note" style={{ marginTop: 8 }}>门禁未返回，暂不能锁定；请刷新页面或重新打开该研究案。</div>
              ) : null}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12, alignItems: "center" }}>
                {!locked ? (
                  <>
                    <button
                      data-testid="inst-research-lock"
                      className="v3-btn primary"
                      disabled={!!busy || !version || gateLoading || gate === null || gateBlocked}
                      onClick={() => lockResearch(false)}
                    >
                      {busy === "lock" ? "锁定中…" : "锁定研究定稿"}
                    </button>
                    {gateBlocked ? (
                      <>
                        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#6b6370" }}>
                          <input type="checkbox" checked={allowGaps} onChange={(e) => setAllowGaps(e.target.checked)} />
                          我已确认数据缺口，允许带缺口锁定
                        </label>
                        <button
                          data-testid="inst-research-lock-gaps"
                          className="v3-btn ghost"
                          disabled={!allowGaps || !!busy}
                          onClick={() => lockResearch(true)}
                        >
                          {busy === "lock-gaps" ? "锁定中…" : "带缺口锁定"}
                        </button>
                      </>
                    ) : null}
                  </>
                ) : null}
                {locked ? <Link className="v3-btn primary" to={`/inst/debate?key=${encodeURIComponent(`case:${detail.id}`)}`}>移交多空辩论 <ArrowRight className="h-3.5 w-3.5" /></Link> : null}
                <Link className="v3-btn ghost" to={`/inst/pipeline/result?key=${encodeURIComponent(`case:${detail.id}`)}`}>查看结果页</Link>
              </div>
            </section>
          ) : null}
        </div>

        <InstV3AgentRail
          agents={agentDefs}
          activeId={activeAgentId}
          onSelect={selectAgent}
          contextRows={[
            { label: "本步产出", value: step === 0 ? "行业底图" : step === 1 ? "六维结论" : step === 2 ? "一页纸裁决" : "研究定稿" },
            { label: "输入", value: "FactPack、证据包、上一版研究；缺失数据写入 data_gaps。" },
            { label: "约束", value: "AI 只给建议；门禁、锁定与审批由服务端执行。" },
          ]}
        />
      </div>
    </>
  );
}
