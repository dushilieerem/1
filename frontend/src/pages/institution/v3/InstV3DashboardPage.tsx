import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Bell, LayoutDashboard, ListChecks, PieChart } from "lucide-react";
import { dedupeBy } from "@/lib/instDedupe";
import { instApi, fmtMoney, fmtPct } from "@/lib/instApi";
import { fetchV3Pipeline, type V3Pipeline } from "@/lib/instV3Api";
import { useInstSession } from "@/components/institution/instSessionContext";

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
  const session = useInstSession();
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
    const stageMeta: Record<number, { label: string; tone: string; limit: number }> = {
      1: { label: "价值分析", tone: "info", limit: 1 },
      3: { label: "投委会审批", tone: "gold", limit: 3 },
      4: { label: "执行成交", tone: "violet", limit: 1 },
      5: { label: "投资管理", tone: "info", limit: 2 },
    };
    const roleStages: Record<string, number[]> = {
      manager: [3, 1],
      partner: [3],
      risk: [3],
      chairman: [3],
      execution: [4],
      monitoring: [5],
    };
    const stages = roleStages[session.role] || [];
    const items = stages.flatMap((no) => {
      const meta = stageMeta[no];
      if (!meta) return [];
      return (pipeline.stages[no]?.items || []).slice(0, meta.limit).map((x) => ({
        key: x.key,
        name: x.company_name || x.symbol || "—",
        stage: meta.label,
        note: `${x.stage_name} · ${x.gate} · 版本 ${x.version_no ?? "—"}`,
        tone: meta.tone,
      }));
    });
    return dedupeBy(items, (x) => x.key).slice(0, 4);
  }, [pipeline, session.role]);

  const flowProjects = useMemo(
    () => (pipeline ? dedupeBy([1, 2, 3, 4, 5].flatMap((n) => pipeline.stages[n]?.items || []), (x) => x.key).slice(0, 3) : []),
    [pipeline],
  );

  if (loading) return <div className="v3-loading">正在加载投资工作台…</div>;
  if (error || !data || !pipeline) return <div className="v3-card">加载失败：{error || "数据不可用"}</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">INVESTMENT OFFICE</div>
          <h1>投资工作台</h1>
          <p>今天 {todos.length} 件事待处理；{data.monitor_alerts} 只持仓预警，{data.pending_approvals} 件议案在审批中。</p>
        </div>
        <Link className="v3-btn primary" to="/inst/pipeline">进入项目流水线 <ArrowRight className="h-3.5 w-3.5" /></Link>
      </div>

      <section className="v3-hero">
        <div>
          <div className="v3-eyebrow">SUBJECTIVE INVESTMENT</div>
          <h2>从一条线索，到一笔<em>可追溯</em>的资本配置。</h2>
          <p>AI 负责分析、计算与核查，人只在关键环节拍板。每一步的结论定稿归档，再交给下一步。</p>
          <div className="v3-hero-tags">
            <span className="v3-chip info">全流程可追溯</span>
            <span className="v3-chip gold">人工拍板</span>
            <span className="v3-chip">自动执行</span>
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
              <Link key={t.key} to={`/inst/pipeline/result?key=${encodeURIComponent(t.key)}`} className="flex items-center gap-3 border-b border-[#f0eaf3] py-3 last:border-0">
                <span className={`v3-chip ${t.tone}`}>{t.stage}</span>
                <span className="min-w-0 flex-1">
                  <b className="block text-[14px] font-medium text-[#2b2533]">{t.name}</b>
                  <span className="block text-[12px] text-[#6b6370]">{t.note}</span>
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-[#6b6370]" />
              </Link>
            )) : <div className="v3-empty">今天没有待办，可以查看项目流水线或组合。</div>}
          </section>

          <section className="v3-card">
            <div className="v3-card-head"><div><h2><LayoutDashboard className="mr-1 inline h-4 w-4" />在流程中的项目</h2><p>卡在哪、谁在等、下一步是什么。</p></div><Link className="v3-btn ghost" to="/inst/pipeline">全部 {pipeline.total} 个</Link></div>
            {flowProjects.map((p) => (
              <Link key={p.key} to={`/inst/pipeline/result?key=${encodeURIComponent(p.key)}`} className="flex items-center gap-3 border-b border-[#f0eaf3] py-3 last:border-0">
                <span className="flex h-7 w-7 items-center justify-center rounded bg-[#f8edf3] text-[12px] font-semibold text-[#a03a5c]">{(p.company_name || p.symbol || "?").slice(0, 1)}</span>
                <span className="min-w-0 flex-1">
                  <b className="block text-[14px] font-medium text-[#2b2533]">{p.company_name || p.symbol}</b>
                  <span className="block text-[12px] text-[#6b6370]">{p.stage_name} · {p.gate} · {p.symbol} · 版本 {p.version_no ?? "—"}</span>
                </span>
                <span className="v3-chip">{p.stage_name}</span>
              </Link>
            ))}
            {!flowProjects.length ? <div className="v3-empty">还没有在流程中的项目。</div> : null}
          </section>
        </div>

        <section className="v3-card">
          <div className="v3-card-head"><div><h2><PieChart className="mr-1 inline h-4 w-4" />组合概览</h2><p>净值、现金、仓位与预警。</p></div><Link className="v3-btn ghost" to="/inst/manage">投资管理</Link></div>
          <div className="v3-kpis" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" }}>
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
