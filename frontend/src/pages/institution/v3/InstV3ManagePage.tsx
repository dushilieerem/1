import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { ArrowRight, Activity, AlertTriangle, RefreshCw } from "lucide-react";
import { dedupeBy } from "@/lib/instDedupe";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { InstV3AgentRail, type AgentPanelDef } from "@/components/institution/v3/InstV3AgentRail";
import InstV3AgentProgress from "./InstV3AgentProgress";

type Position = {
  symbol: string;
  name?: string;
  company_id?: number;
  industry?: string;
  qty: number;
  cost?: number;
  market_value: number;
  weight: number;
  last_close?: number;
};

type Portfolio = {
  nav: number;
  cash: number;
  invested: number;
  invested_ratio: number;
  positions: Position[];
  industry_exposure?: Record<string, number>;
};

type Thesis = {
  id?: number;
  thesis?: string;
  status?: string;
  kpis?: Array<{ name?: string; target?: number | string; value?: string; status?: string }>;
  falsifiers?: string[];
  review_due?: string;
  created_at?: string;
};

type MonitorEvent = {
  id?: number;
  type?: string;
  severity?: string;
  detail?: unknown;
  created_at?: string;
};

type ExitCase = {
  id?: number;
  company_id?: number;
  reason_type?: string;
  status?: string;
  memo?: string;
  created_at?: string;
};

type ExitAdvice = { stance: "hold" | "trim" | "exit"; label: string; pm: string; risk: string };

type Holding = {
  symbol: string;
  version_no?: number | null;
  position: Position;
  theses: Thesis[];
  events: MonitorEvent[];
  exits: ExitCase[];
};

type NavPoint = {
  date: string;
  nav: number;
  cash: number;
  invested: number;
  pnl: number;
  pnl_pct: number;
};

type NavHistory = {
  base: number;
  series: NavPoint[];
  latest?: NavPoint | null;
  max_drawdown?: number;
  note?: string;
};

type StockNavPoint = {
  date: string;
  close: number;
  cost: number;
  qty: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
};

type StockNav = {
  symbol: string;
  cost?: number;
  qty?: number;
  series: StockNavPoint[];
  latest?: StockNavPoint | null;
  max_drawdown?: number;
  note?: string;
};

const STEPS = [
  { name: "组合总览", sub: "净值 / 现金 / 敞口" },
  { name: "单票盘中", sub: "论点台账 · 事件" },
  { name: "预警与退出", sub: "四类理由 · 重走审批" },
];

const REASONS: Array<[string, string]> = [
  ["thesis_invalid", "论点失效"],
  ["valuation", "估值透支"],
  ["better_allocation", "更优机会"],
  ["portfolio_constraint", "组合/资金约束"],
];

function textOf(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((x) => textOf(x, "")).filter(Boolean).join("；") || fallback;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const picked = obj.text ?? obj.detail ?? obj.message ?? obj.label ?? obj.value;
    if (picked !== undefined && picked !== null && picked !== value) return textOf(picked, fallback);
    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }
  return String(value);
}

function parseHolding(key: string | null): string | null {
  const m = String(key || "").match(/holding:([A-Za-z0-9.]+)/);
  return m ? m[1] : null;
}

export function InstV3ManagePage() {
  const session = useInstSession();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [holding, setHolding] = useState<Holding | null>(null);
  const [step, setStep] = useState(0);
  const [agentId, setAgentId] = useState("pm");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [opinion, setOpinion] = useState("");
  const [warning, setWarning] = useState("");
  const [reason, setReason] = useState("thesis_invalid");
  const [exitMemo, setExitMemo] = useState("");
  const [exitAdvice, setExitAdvice] = useState<ExitAdvice | null>(null);
  const [navHistory, setNavHistory] = useState<NavHistory | null>(null);
  const [stockNav, setStockNav] = useState<StockNav | null>(null);

  const detailSeq = useRef(0);
  const selectedSymbol = parseHolding(params.get("key"));
  const canWrite = ["manager", "partner"].includes(session.role);

  const loadPortfolio = async () => {
    const data = await instApi<Portfolio>("/portfolio");
    setPortfolio(data);
    return data;
  };

  const loadHolding = async (symbol: string) => {
    const seq = ++detailSeq.current;
    const data = await instApi<Holding>(`/holdings/${encodeURIComponent(symbol)}`);
    if (seq !== detailSeq.current) return data;
    setHolding(data);
    return data;
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadPortfolio()
      .then(async (pf) => {
        if (!alive) return;
        const symbol = selectedSymbol || pf.positions?.[0]?.symbol || null;
        if (symbol) {
          if (!selectedSymbol) setParams({ key: `holding:${symbol}` }, { replace: true });
          else await loadHolding(symbol);
        }
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol]);

  const selectHolding = (symbol: string) => {
    setStep(1);
    setHolding(null);
    setParams({ key: `holding:${symbol}` });
  };

  const refreshThesis = async () => {
    if (!holding?.position.company_id) return;
    setBusy("thesis");
    setError(null);
    try {
      await instApi("/monitor/theses/refresh", { method: "POST", body: { company_id: holding.position.company_id } });
      await loadHolding(holding.symbol);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const scan = async () => {
    setBusy("scan");
    setError(null);
    try {
      await instApi("/monitor/scan", { method: "POST" });
      if (holding) await loadHolding(holding.symbol);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const recordWarning = async () => {
    if (!holding?.position.company_id || !warning.trim()) return;
    setBusy("warning");
    setError(null);
    try {
      await instApi("/monitor/events", {
        method: "POST",
        body: { company_id: holding.position.company_id, type: "manual", severity: "warning", detail: warning.trim() },
      });
      setWarning("");
      await loadHolding(holding.symbol);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const submitExit = async () => {
    if (!holding?.position.company_id) return;
    if (!exitMemo.trim()) { setError("退出议案必须写清理由"); return; }
    setBusy("exit");
    setError(null);
    try {
      const created = await instApi<{ id?: number; case_id?: number }>("/monitor/exits", {
        method: "POST",
        body: { company_id: holding.position.company_id, reason_type: reason, memo: exitMemo.trim() },
      });
      await loadPortfolio();
      if (created.case_id) {
        navigate(`/inst/research?key=${encodeURIComponent(`case:${created.case_id}`)}`);
      } else {
        await loadHolding(holding.symbol);
        setStep(2);
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const positions = dedupeBy(portfolio?.positions || [], (p) => p.symbol);
  const activePosition = holding?.position || positions.find((p) => p.symbol === selectedSymbol) || null;
  const exposure = useMemo(() => Object.entries(portfolio?.industry_exposure || {}).sort((a, b) => b[1] - a[1]), [portfolio]);

  useEffect(() => {
    const symbol = activePosition?.symbol;
    if (!symbol) { setExitAdvice(null); return; }
    let alive = true;
    instApi<ExitAdvice>(`/monitor/exit-advice?symbol=${encodeURIComponent(symbol)}`)
      .then((data) => { if (alive) setExitAdvice(data); })
      .catch(() => { if (alive) setExitAdvice(null); });
    return () => { alive = false; };
  }, [activePosition?.symbol]);

  useEffect(() => {
    setAgentId(step === 1 ? "monitor" : "pm");
  }, [step]);

  useEffect(() => {
    let alive = true;
    instApi<NavHistory>("/portfolio/nav-history?days=180")
      .then((data) => { if (alive) setNavHistory(data); })
      .catch(() => { if (alive) setNavHistory(null); });
    return () => { alive = false; };
  }, [portfolio?.nav]);

  useEffect(() => {
    const symbol = activePosition?.symbol;
    if (!symbol) { setStockNav(null); return; }
    let alive = true;
    instApi<StockNav>(`/holdings/${encodeURIComponent(symbol)}/nav-history?days=180`)
      .then((data) => { if (alive) setStockNav(data); })
      .catch(() => { if (alive) setStockNav(null); });
    return () => { alive = false; };
  }, [activePosition?.symbol]);

  const navOption = useMemo(() => {
    const series = navHistory?.series || [];
    const base = navHistory?.base || 0;
    return {
      grid: { left: 48, right: 16, top: 24, bottom: 28 },
      tooltip: {
        trigger: "axis",
        formatter: (items: Array<{ dataIndex: number }>) => {
          const point = series[items[0]?.dataIndex ?? 0];
          if (!point) return "";
          return `${point.date}<br/>净值 ${fmtMoney(point.nav)}<br/>盈亏 ${fmtMoney(point.pnl)}（${point.pnl_pct.toFixed(2)}%）<br/>现金 ${fmtMoney(point.cash)} · 持仓 ${fmtMoney(point.invested)}`;
        },
      },
      xAxis: { type: "category", data: series.map((p) => p.date.slice(5)), axisLabel: { fontSize: 10, color: "#8a8290" }, axisLine: { lineStyle: { color: "#e4dde8" } } },
      yAxis: { type: "value", name: "收益率%", nameTextStyle: { fontSize: 10, color: "#8a8290" }, axisLabel: { fontSize: 10, color: "#8a8290", formatter: "{value}%" }, splitLine: { lineStyle: { color: "#f2ecf4" } } },
      series: [
        {
          type: "line",
          name: "组合收益率",
          data: series.map((p) => Number(p.pnl_pct.toFixed(2))),
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: base ? "#a03a5c" : "#999" },
          areaStyle: {
            color: {
              type: "linear", x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(160,58,92,0.22)" },
                { offset: 1, color: "rgba(160,58,92,0.02)" },
              ],
            },
          },
          markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: "#c9c0cc", type: "dashed" }, label: { show: false } },
        },
      ],
    };
  }, [navHistory]);

  const stockNavOption = useMemo(() => {
    const series = stockNav?.series || [];
    const cost = stockNav?.cost || 0;
    return {
      grid: { left: 48, right: 16, top: 24, bottom: 28 },
      tooltip: {
        trigger: "axis",
        formatter: (items: Array<{ dataIndex: number }>) => {
          const point = series[items[0]?.dataIndex ?? 0];
          if (!point) return "";
          return `${point.date}<br/>收盘 ${point.close.toFixed(2)} · 成本 ${point.cost.toFixed(2)}<br/>盈亏 ${fmtMoney(point.pnl)}（${point.pnl_pct.toFixed(2)}%）`;
        },
      },
      xAxis: { type: "category", data: series.map((p) => p.date.slice(5)), axisLabel: { fontSize: 10, color: "#8a8290" }, axisLine: { lineStyle: { color: "#e4dde8" } } },
      yAxis: { type: "value", scale: true, axisLabel: { fontSize: 10, color: "#8a8290" }, splitLine: { lineStyle: { color: "#f2ecf4" } } },
      series: [
        { type: "line", name: "收盘价", data: series.map((p) => Number(p.close.toFixed(2))), smooth: true, symbol: "none", lineStyle: { width: 2, color: "#a03a5c" }, areaStyle: { color: "rgba(160,58,92,0.08)" } },
        { type: "line", name: "持仓成本", data: series.map(() => Number(cost.toFixed(2))), symbol: "none", lineStyle: { width: 1, type: "dashed", color: "#8a8290" } },
      ],
    };
  }, [stockNav]);

  const agentDefs = useMemo<AgentPanelDef[]>(() => {
    if (step === 1) {
      return [{ id: "monitor", name: "监控 Agent", code: "MONITOR", model: "监控 Agent", tools: "公告 / 行情 / KPI", output: "论点台账 + 事件提醒", role: "扫描事件、核对论点，不替人做卖出决定。" }];
    }
    if (step === 2) {
      return [
        { id: "pm", name: "组合经理", code: "PM", model: "组合经理 Agent", tools: "持仓 / 论点 / 组合约束", output: "持有 / 减仓 / 清仓建议", role: "比较三条路径的代价。", advice: exitAdvice?.pm, adviceTone: exitAdvice?.stance },
        { id: "risk", name: "风控", code: "RISK", model: "风控 Agent", tools: "敞口 / 流动性 / 硬约束", output: "退出可行性意见", role: "检查退出是否触发硬约束。", advice: exitAdvice?.risk, adviceTone: exitAdvice?.stance },
      ];
    }
    return [{ id: "pm", name: "组合经理", code: "PM", model: "组合经理 Agent", tools: "组合 / 约束 / 机会成本", output: "组合概览", role: "看钱在哪、风险在哪。" }];
  }, [step, exitAdvice]);

  if (loading) return <div className="v3-loading">正在加载投资管理…</div>;
  if (error && !portfolio) return <div className="v3-card">加载失败：{error}</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">OWNERSHIP</div>
          <h1>投资管理</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="v3-chip info">版本 {holding?.version_no ?? "—"}</span>
          <span className="v3-chip info">{session.role_label_cn}</span>
        </div>
      </div>

      <div className="v3-stepper">
        {STEPS.map((s, i) => (
          <button key={s.name} className={`v3-step${i < step ? " done" : i === step ? " now" : ""}`} onClick={() => setStep(i)} style={{ background: "none", borderTop: 0, borderLeft: 0, borderBottom: 0, cursor: "pointer" }}>
            <span className="dot">{i}</span>
            <div><span className="lb">{s.name}</span><span className="sb">{s.sub}</span></div>
          </button>
        ))}
      </div>

      <div className="v3-workspace-grid">
        <div className="v3-project-list">
          <div className="pl-head"><span>当前持仓</span><span>{positions.length}</span></div>
          {positions.map((p) => (
            <button key={p.symbol} className={`pl-item${p.symbol === activePosition?.symbol ? " on" : ""}`} onClick={() => selectHolding(p.symbol)}>
              <b>{p.name || p.symbol}</b>
              <span>{p.symbol} · {fmtPct(p.weight)}</span>
            </button>
          ))}
          {!positions.length ? <div className="v3-empty" style={{ padding: "16px" }}>当前没有持仓。</div> : null}
        </div>

        <div className="v3-work-main">
          {error ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{error}</div> : null}

          {step === 0 ? (
            <>
              <section className="v3-kpis">
                <div className="v3-kpi"><div className="k">组合净值（CNY）</div><div className="v">{fmtMoney(portfolio?.nav)}</div><div className="d">现金 {fmtMoney(portfolio?.cash)}</div></div>
                <div className="v3-kpi"><div className="k">仓位</div><div className="v">{fmtPct(portfolio?.invested_ratio)}</div><div className="d">已投资 {fmtMoney(portfolio?.invested)}</div></div>
                <div className="v3-kpi"><div className="k">持仓</div><div className="v">{positions.length}<small> 只</small></div><div className="d">按最新市值计算权重</div></div>
                <div className="v3-kpi"><div className="k">在途退出</div><div className="v">{holding?.exits?.length ?? 0}<small> 个</small></div><div className="d">退出重走审批</div></div>
              </section>
              <section className="v3-card">
                <div className="v3-card-head">
                  <div>
                    <h2>组合净值曲线</h2>
                    <p>从建立组合日起按每日收盘盯市；收益率为相对初始资金 {fmtMoney(navHistory?.base ?? portfolio?.nav)} 的累计盈亏。</p>
                  </div>
                  <span className="v3-chip">
                    {navHistory?.latest ? `累计 ${navHistory.latest.pnl >= 0 ? "+" : ""}${navHistory.latest.pnl_pct.toFixed(2)}%` : "—"}
                  </span>
                </div>
                {navHistory?.series?.length ? (
                  <>
                    <ReactECharts option={navOption} style={{ height: 260 }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
                    <div className="flex flex-wrap gap-x-6 gap-y-1 text-[12px] text-[#6b6370]">
                      <span>当前净值 {fmtMoney(navHistory.latest?.nav)}</span>
                      <span>累计盈亏 {fmtMoney(navHistory.latest?.pnl)}</span>
                      <span>区间最大回撤 {navHistory.max_drawdown?.toFixed(2) ?? "—"}%</span>
                      <span>现金 {fmtMoney(navHistory.latest?.cash)}</span>
                    </div>
                  </>
                ) : (
                  <div className="v3-empty">{navHistory?.note || "成交记录不足，净值曲线需要至少两个交易日的行情。"}</div>
                )}
              </section>
              <section className="v3-card">
                <div className="v3-card-head"><div><h2>持仓明细</h2><p>点任意持仓进入单票盘中；权重按市值/净值。</p></div><span className="v3-chip">{positions.length} 只</span></div>
                <div className="table-wrap" style={{ overflowX: "auto" }}>
                  <table className="v3-table">
                    <thead><tr><th>标的</th><th>数量</th><th>成本</th><th>最新</th><th>市值</th><th>权重</th><th>盘中</th></tr></thead>
                    <tbody>
                      {positions.map((p) => (
                        <tr key={p.symbol}>
                          <td><b>{p.name || p.symbol}</b><span>{p.symbol} · {p.industry || "—"}</span></td>
                          <td>{p.qty}</td><td>{p.cost ? p.cost.toFixed(2) : "—"}</td><td>{p.last_close ? p.last_close.toFixed(2) : "—"}</td>
                          <td>{fmtMoney(p.market_value)}</td><td>{fmtPct(p.weight)}</td>
                          <td><button className="v3-btn ghost" onClick={() => selectHolding(p.symbol)}>盘中 →</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="v3-card">
                <div className="v3-card-head"><div><h2>行业敞口</h2><p>接近上限会标黄；组合约束不可由 AI 或 Chairman 绕过。</p></div></div>
                {exposure.map(([industry, weight]) => (
                  <div key={industry} style={{ marginTop: 8 }}>
                    <div className="flex justify-between text-[12px] text-[#6b6370]"><span>{industry}</span><span>{fmtPct(weight)}</span></div>
                    <div style={{ height: 6, background: "#f0eaf3", borderRadius: 99, marginTop: 4 }}><div style={{ width: `${Math.min(100, weight * 100)}%`, height: "100%", background: "#a03a5c", borderRadius: 99 }} /></div>
                  </div>
                ))}
                {!exposure.length ? <div className="v3-empty">暂无行业敞口数据。</div> : null}
              </section>
            </>
          ) : null}

          {step === 1 && activePosition ? (
            <>
              <section className="v3-card">
                <div className="v3-card-head"><div><h2>{activePosition.name || activePosition.symbol} · 盘中</h2><p>{activePosition.symbol} · {fmtPct(activePosition.weight)} · 成本 {activePosition.cost?.toFixed(2) || "—"} · 现价 {activePosition.last_close?.toFixed(2) || "—"}</p></div><button className="v3-btn ghost" disabled={!!busy} onClick={scan}><Activity className="h-3.5 w-3.5" />{busy === "scan" ? "扫描中…" : "扫描事件"}</button></div>
                <p style={{ lineHeight: 1.7, color: "#5f5766" }}>买入不是结束，而是论点开始接受检验；监控 Agent 只提示，不替你做卖出决定。</p>
              </section>

              <section className="v3-card">
                <div className="v3-card-head">
                  <div>
                    <h2>单票净值曲线</h2>
                    <p>从首次成交日起的收盘价与持仓成本；盈亏按当前持仓数量相对成本计算。</p>
                  </div>
                  <span className="v3-chip">
                    {stockNav?.latest ? `浮盈 ${stockNav.latest.pnl >= 0 ? "+" : ""}${stockNav.latest.pnl_pct.toFixed(2)}%` : "—"}
                  </span>
                </div>
                {stockNav?.series?.length ? (
                  <>
                    <ReactECharts option={stockNavOption} style={{ height: 240 }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
                    <div className="flex flex-wrap gap-x-6 gap-y-1 text-[12px] text-[#6b6370]">
                      <span>成本 {stockNav.cost?.toFixed(2) ?? "—"} · 数量 {stockNav.qty ?? "—"}</span>
                      <span>持仓市值 {fmtMoney(stockNav.latest?.market_value)}</span>
                      <span>浮动盈亏 {fmtMoney(stockNav.latest?.pnl)}</span>
                      <span>区间最大回撤 {stockNav.max_drawdown?.toFixed(2) ?? "—"}%</span>
                    </div>
                  </>
                ) : (
                  <div className="v3-empty">{stockNav?.note || "成交记录不足，单票曲线需要至少两个交易日的行情。"}</div>
                )}
              </section>

              <section className="v3-card">
                <div className="v3-card-head"><div><h2>买入论点台账</h2><p>关键假设、KPI、复核时间与推翻条件。</p></div><button className="v3-btn ghost" disabled={!!busy} onClick={refreshThesis}><RefreshCw className="h-3.5 w-3.5" />{busy === "thesis" ? "生成中…" : "重新生成台账"}</button></div>
                <InstV3AgentProgress active={busy === "thesis"} title="监控 Agent 正在生成买入论点台账" detail="从买入议案提取关键假设、KPI 与复核条件，完成后自动刷新。" />
                {holding?.theses?.length ? dedupeBy(holding.theses, (t) => t.id).map((t, i) => (
                  <div key={t.id || i} className="v3-claim">
                    <div className="who">{t.status || "active"} · 复核 {t.review_due || "—"}</div>
                    <p>{textOf(t.thesis)}</p>
                    {t.kpis?.length ? <div className="fs">KPI：{t.kpis.map((k) => `${k.name || "KPI"} ${textOf(k.target, "")}`).join("；")}</div> : null}
                    {t.falsifiers?.length ? <div className="fs">推翻条件：{t.falsifiers.map((x) => textOf(x, "")).filter(Boolean).join("；")}</div> : null}
                  </div>
                )) : <div className="v3-empty">还没有台账；点“重新生成台账”从买入议案生成。</div>}
              </section>

              <section className="v3-card">
                <div className="v3-card-head"><div><h2>监控事件</h2><p>经营 / 估值 / 治理 / 交易异常；时间点 + 摘要。</p></div><span className="v3-chip">{holding?.events?.length || 0} 条</span></div>
                {holding?.events?.length ? dedupeBy(holding.events, (e) => e.id).slice(0, 8).map((e, i) => (
                  <div className="v3-kv" key={e.id || i}><dt>{e.created_at || "—"} · {e.type || "事件"}</dt><dd>{textOf(e.detail)} <span className="v3-chip warn">{e.severity || "info"}</span></dd></div>
                )) : <div className="v3-empty">暂无监控事件。</div>}
              </section>

              <section className="v3-card">
                <div className="v3-card-head"><div><h2>记录预警</h2><p>时间点 + 一句理由；预警不是卖出，先进入复核。</p></div></div>
                <div className="v3-field"><textarea data-testid="inst-warning" value={warning} onChange={(e) => setWarning(e.target.value)} placeholder="写清触发原因、已核验事实与需要复核的问题。" /></div>
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                  <button data-testid="inst-warning-submit" className="v3-btn primary" disabled={!canWrite || !warning.trim() || !!busy} onClick={recordWarning}><AlertTriangle className="h-3.5 w-3.5" />{busy === "warning" ? "记录中…" : "记录预警"}</button>
                </div>
              </section>
            </>
          ) : null}

          {step === 2 && activePosition ? (
            <>
              {exitAdvice ? (
                <section className={`v3-card v3-hold-advice ${exitAdvice.stance}`}>
                  <div className="v3-eyebrow">持仓建议</div>
                  <div className="v3-hold-advice-label">{exitAdvice.label}</div>
                </section>
              ) : null}
              <section className="v3-card">
                <div className="v3-card-head"><div><h2>预警与退出</h2><p>卖出理由只有四类；创建退出研究案后重走研究、辩论、三关审批。</p></div><span className="v3-chip warn">旧授权作废</span></div>
                <div className="v3-form-grid">
                  <div className="v3-field"><label>卖出理由</label><select data-testid="inst-exit-reason" value={reason} onChange={(e) => setReason(e.target.value)} disabled={!canWrite}>{REASONS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
                  <div className="v3-field"><label>标的</label><input value={`${activePosition.name || ""} ${activePosition.symbol}`} readOnly /></div>
                  <div className="v3-field span-2"><label>退出理由 / 复核意见</label><textarea data-testid="inst-exit-memo" value={exitMemo} onChange={(e) => setExitMemo(e.target.value)} disabled={!canWrite} placeholder="写清触发原因、已核验事实与希望投委会复核的问题。" /></div>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button data-testid="inst-exit-submit" className="v3-btn primary" disabled={!canWrite || !exitMemo.trim() || !!busy} onClick={submitExit}>{busy === "exit" ? "创建中…" : "创建退出研究案并进入研究"}</button>
                  <Link className="v3-btn ghost" to="/inst/pipeline">查看项目流水线</Link>
                </div>
                <div className="v3-note" style={{ marginTop: 8 }}>退出不复用买入授权：创建后进入价值分析，重新定稿、辩论并走合伙人 → 风控 → Chairman；新退出议案获批时旧授权作废。</div>
              </section>

              <section className="v3-card">
                <div className="v3-card-head"><div><h2>在途退出审理</h2><p>按状态跟踪；复核结论保留。</p></div><span className="v3-chip">{holding?.exits?.length || 0} 个</span></div>
                {holding?.exits?.length ? dedupeBy(holding.exits, (e) => e.id).slice(0, 6).map((e, i) => (
                  <div className="v3-kv" key={e.id || i}><dt>#{e.id} · {e.reason_type || "—"}</dt><dd>{e.status || "—"} · {textOf(e.memo)}</dd></div>
                )) : <div className="v3-empty">暂无在途退出。</div>}
              </section>
            </>
          ) : null}
        </div>

        <InstV3AgentRail
          agents={agentDefs}
          activeId={agentId}
          onSelect={setAgentId}
          contextRows={[
            { label: "本步", value: `${STEPS[step].name} · ${STEPS[step].sub}` },
            { label: "卖出四类理由", value: "论点失效 / 估值透支 / 更优机会 / 组合约束。" },
            { label: "约束", value: "退出重走研究、辩论、审批；旧授权不复用。" },
          ]}
        />
      </div>
    </>
  );
}
