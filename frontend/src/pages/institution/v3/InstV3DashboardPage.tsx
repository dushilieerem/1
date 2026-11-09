import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Bell, LayoutDashboard, ListChecks, PieChart } from "lucide-react";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { fetchV3Pipeline, type V3Pipeline } from "@/lib/instV3Api";

type Overview = {
  companies: number;
  active_cases: number;
  pending_approvals: number;
  my_pending: number;
  risk_blocks: number;
  monitor_alerts: number;
  data_date?: string;
  portfolio: { nav: number; cash: number; invested_ratio: number };
  policy: { max_single_weight: number; min_cash_ratio: number; nav: number; policy_version: string };
};

export function InstV3DashboardPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [pipeline, setPipeline] = useState<V3Pipeline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([instApi<Overview>("/overview"), fetchV3Pipeline()])
      .then(([overview, flow]) => {
        if (!alive) return;
        setData(overview);
        setPipeline(flow);
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const todos = useMemo(() => {
    if (!pipeline) return [];
    const items = [
      ...(pipeline.stages[3]?.items || []).slice(0, 3).map((x) => ({
        key: x.key, name: x.company_name || x.symbol || "—", stage: "投委会审批", note: `${x.stage_name} · ${x.gate}`, tone: "gold",
      })),
      ...(pipeline.stages[1]?.items || []).slice(0, 1).map((x) => ({
        key: x.key, name: x.company_name || x.symbol || "—", stage: "价值分析", note: `${x.stage_name} · ${x.gate}`, tone: "info",
      })),
      ...(pipeline.stages[4]?.items || []).slice(0, 1).map((x) => ({
        key: x.key, name: x.company_name || x.symbol || "—", stage: "执行成交", note: `${x.stage_name} · ${x.gate}`, tone: "violet",
      })),
    ];
    return items.slice(0, 4);
  }, [pipeline]);

  const flowProjects = useMemo(
    () => (pipeline ? [1, 2, 3, 4, 5].flatMap((n) => pipeline.stages[n]?.items || []).slice(0, 3) : []),
    [pipeline],
  );

  if (loading) return <div className="v3-loading">正在加载投资工作台…</div>;
  if (error || !data || !pipeline) return <div className="v3-card">加载失败：{error || "数据不可用"}</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">INVESTMENT OFFICE / 00</div>
          <h1>投资工作台</h1>
          <p>今天 {todos.length} 件事待处理；{data.monitor_alerts} 只持仓预警，{data.pending_approvals} 件议案在审批中。</p>
        </div>
        <Link className="v3-btn primary" to="/inst-v3/pipeline">进入项目流水线 <ArrowRight className="h-3.5 w-3.5" /></Link>
      </div>

      <section className="v3-hero">
        <div>
          <div className="v3-eyebrow">SUBJECTIVE INVESTMENT / V3</div>
          <h2>从一条线索，到一笔<em>可追溯</em>的资本配置。</h2>
          <p>AI 负责分析、计算与核查，人只在五个环节拍板。每一步的结论定稿归档，再交给下一步。</p>
          <div className="v3-hero-tags">
            <span className="v3-chip info">6 个环节</span>
            <span className="v3-chip gold">5 个人工决策点</span>
            <span className="v3-chip">1 个自动环节</span>
            <span className="v3-chip ok">证据可回溯</span>
          </div>
        </div>
        <div className="v3-hero-right">
          <span className="date">{data.data_date || "—"}</span>
          <span className="big">{pipeline.total}<small>个项目在流程中</small></span>
          <span className="note">{todos.length} 项待你拍板 · {data.monitor_alerts} 只持仓预警</span>
        </div>
      </section>

      <section className="v3-kpis">
        <div className="v3-kpi"><div className="k">组合净值（CNY）</div><div className="v">{fmtMoney(data.portfolio?.nav)}</div><div className="d">现金 {fmtMoney(data.portfolio?.cash)} · 仓位 {fmtPct(data.portfolio?.invested_ratio)}</div></div>
        <div className="v3-kpi"><div className="k">在研研究案</div><div className="v">{data.active_cases}<small>个</small></div><div className="d">公司池 {data.companies} 家</div></div>
        <div className="v3-kpi"><div className="k">待审批 / 风控阻断</div><div className="v">{data.pending_approvals} / {data.risk_blocks}</div><div className="d">任一阻断都不能生成授权</div></div>
        <div className="v3-kpi"><div className="k">监控预警</div><div className="v">{data.monitor_alerts}<small>条</small></div><div className="d">单股上限 {fmtPct(data.policy?.max_single_weight)}</div></div>
      </section>

      <div className="v3-home-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <section className="v3-card">
            <div className="v3-card-head"><div><h2><ListChecks className="mr-1 inline h-4 w-4" />今天要处理</h2><p>按当前登录角色汇总流程中的待办。</p></div><span className="v3-chip">{todos.length} 件</span></div>
            {todos.length ? todos.map((t) => (
              <Link key={t.key} to={`/inst-v3/pipeline/result?key=${encodeURIComponent(t.key)}`} className="flex items-center gap-3 border-b border-[#f0eaf3] py-2.5 last:border-0">
                <span className={`v3-chip ${t.tone}`}>{t.stage}</span>
                <span className="min-w-0 flex-1">
                  <b className="block text-[12px] font-medium text-[#2b2533]">{t.name}</b>
                  <span className="block text-[10px] text-[#9b92a1]">{t.note}</span>
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-[#b7afbc]" />
              </Link>
            )) : <div className="v3-empty">今天没有待办，可以查看项目流水线或组合。</div>}
          </section>

          <section className="v3-card">
            <div className="v3-card-head"><div><h2><LayoutDashboard className="mr-1 inline h-4 w-4" />在流程中的项目</h2><p>卡在哪、谁在等、下一步是什么。</p></div><Link className="v3-btn ghost" to="/inst-v3/pipeline">全部 {pipeline.total} 个</Link></div>
            {flowProjects.map((p) => (
              <Link key={p.key} to={`/inst-v3/pipeline/result?key=${encodeURIComponent(p.key)}`} className="flex items-center gap-3 border-b border-[#f0eaf3] py-2.5 last:border-0">
                <span className="flex h-7 w-7 items-center justify-center rounded bg-[#f8edf3] text-[11px] font-semibold text-[#a03a5c]">{(p.company_name || p.symbol || "?").slice(0, 1)}</span>
                <span className="min-w-0 flex-1">
                  <b className="block text-[12px] font-medium text-[#2b2533]">{p.company_name || p.symbol}</b>
                  <span className="block text-[10px] text-[#9b92a1]">{p.stage_name} · {p.gate} · {p.symbol}</span>
                </span>
                <span className="v3-chip">{p.stage_name}</span>
              </Link>
            ))}
            {!flowProjects.length ? <div className="v3-empty">还没有在流程中的项目。</div> : null}
          </section>
        </div>

        <section className="v3-card">
          <div className="v3-card-head"><div><h2><PieChart className="mr-1 inline h-4 w-4" />组合概览</h2><p>净值、现金、仓位与预警。</p></div><Link className="v3-btn ghost" to="/inst-v3/manage">投资管理</Link></div>
          <div className="v3-kpis" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="v3-kpi"><div className="k">组合净值</div><div className="v">{fmtMoney(data.portfolio?.nav)}</div><div className="d">参考净值 {fmtMoney(data.policy?.nav)}</div></div>
            <div className="v3-kpi"><div className="k">现金</div><div className="v">{fmtPct(data.portfolio?.cash ? data.portfolio.cash / (data.portfolio.nav || 1) : null)}</div><div className="d">下限 {fmtPct(data.policy?.min_cash_ratio)}</div></div>
            <div className="v3-kpi"><div className="k">仓位</div><div className="v">{fmtPct(data.portfolio?.invested_ratio)}</div><div className="d">已投资 / 净值</div></div>
            <div className="v3-kpi"><div className="k">预警</div><div className="v" style={{ color: data.monitor_alerts ? "#ab3a37" : "#1c7a52" }}>{data.monitor_alerts}<small> 条</small></div><div className="d"><Bell className="mr-1 inline h-3 w-3" />监控 Agent</div></div>
          </div>
        </section>
      </div>
    </>
  );
}
