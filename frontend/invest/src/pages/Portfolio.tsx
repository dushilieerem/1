import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronRight, Info, Upload } from "lucide-react";
import { api } from "../api";
import { BarRow, Disclaimer, EmptyState, ErrorState, Kv, LoadingCards, PageHeader, RiskRing, Sheet, Tag } from "../components";
import { fmtMoney, fmtPct } from "../lib";
import { useToast } from "../toast";
import AiPanel from "../components/AiPanel";

export default function Portfolio() {
  const nav = useNavigate();
  const toast = useToast();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const load = () => {
    setError(null);
    api("/api/invest/portfolio").then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  if (data && data.holdings.length === 0) {
    return (
      <div className="page">
        <PageHeader
          title="组合体检"
          sub="尚未导入持仓"
          right={<button className="round-btn" onClick={() => setImportOpen(true)} aria-label="导入持仓"><Upload size={18} /></button>}
        />
        <EmptyState
          title="还没有组合"
          detail="导入 CSV 或手工持仓，才能做集中度、行业暴露、配置偏离与压力测试。"
          action={<button className="btn btn-primary" onClick={() => setImportOpen(true)}>导入持仓</button>}
        />
        <ImportSheet open={importOpen} onClose={() => setImportOpen(false)} onDone={(next) => { setData(next); setImportOpen(false); toast("持仓已更新"); }} />
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader
        title="组合体检"
        sub={data ? `${data.holdings.length} 个持仓 · ${data.dataDate}` : "示例组合"}
        right={<button className="round-btn" onClick={() => setImportOpen(true)} aria-label="导入持仓"><Upload size={18} /></button>}
      />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <>
          <section className="card ring-card">
            <RiskRing score={data.riskScore} />
            <div className="ring-copy">
              <h2>{data.riskLabel} <Tag tone="amber">需关注</Tag></h2>
              <p>{data.summary}</p>
              <span className={data.dailyChange >= 0 ? "up" : "down"}>今日 {fmtPct(data.dailyChange, 1)}</span>
            </div>
          </section>

          <div className="kpi-grid">
            {data.kpis.map((k: any) => (
              <div className="kpi" key={k.label}><span>{k.label}</span><b>{k.value}</b></div>
            ))}
          </div>

          <AiPanel
            title="AI 组合诊断"
            subtitle="基于当前持仓、集中度与行业暴露生成；只说明风险来源，不给调仓指令。"
            endpoint="/api/invest/ai/portfolio"
            buttonLabel="生成 AI 诊断"
          />

          <section className="card">
            <div className="card-title-row"><h2>诊断报告</h2><span className="hint">{data.diagnosis.length} 个待关注</span></div>
            <div className="diag-list">
              {data.diagnosis.map((d: any, i: number) => (
                <div className="diag-item" key={i}>
                  <AlertTriangle size={18} />
                  <div>
                    <b>{d.title}</b>
                    <span>{d.detail}</span>
                    <em>{d.evidence}</em>
                    <small>{d.risk}</small>
                  </div>
                </div>
              ))}
              {!data.diagnosis.length ? <div className="empty-inline">暂未触发诊断规则。</div> : null}
            </div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>行业暴露</h2><span className="hint">按当前市值</span></div>
            {data.exposure.map((e: any) => (
              <BarRow key={e.name} label={e.name} value={e.weight} width={e.weight * 2.2} />
            ))}
            <div className="hint">仅直接持仓；ETF 穿透与重叠识别暂未纳入。</div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>持仓明细</h2><span className="hint">{data.holdings.length} 个</span></div>
            <div className="hold-list">
              {data.holdings.map((h: any) => (
                <button className="hold-row" key={h.code} onClick={() => h.code !== "CASH" && nav(`/stock/${h.code}`)}>
                  <div><b>{h.name}</b><span>{h.code} · {h.industry}</span></div>
                  <div className="hold-right"><b>{h.weight}%</b><span>{fmtMoney(h.value)}</span></div>
                </button>
              ))}
            </div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>配置偏离</h2><span className="hint">只展示，不调仓</span></div>
            <div className="dev-list">
              {data.deviation.map((d: any) => (
                <div className="dev-row" key={d.name}>
                  <span>{d.name}</span>
                  <span>目标 {d.target}% · 当前 {d.current}%</span>
                  <b className={d.diff > 0 ? "up" : d.diff < 0 ? "down" : "muted"}>{fmtPct(d.diff, 0)}</b>
                  <Tag tone={d.status === "达标" ? "green" : "amber"}>{d.status}</Tag>
                </div>
              ))}
            </div>
            <div className="callout blue"><Info size={15} /><span>偏离只用于理解组合，不构成调仓建议；本产品不自动调仓。</span></div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>压力测试</h2><span className="hint">假设冲击 · 非预测</span></div>
            {data.stress.map((s: any) => (
              <div className="stress-row" key={s.name}><span>{s.name}</span><b className={s.value < 0 ? "down" : "up"}>{fmtPct(s.value, 1)}</b></div>
            ))}
            <div className="hint">简化假设，未考虑相关性变化与流动性冲击。</div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>成本与换手</h2><span className="hint">别让费用吃掉收益</span></div>
            <Kv k="预估再平衡交易成本" v={`约 ${data.costs.tradeCostPct}%`} />
            <Kv k="示例年化换手率" v={`${data.costs.annualTurnover}%`} />
            <Kv k="单次调仓冲击成本" v={`约 ${data.costs.impactCostPct}%`} />
            <div className="hint">频繁调仓会侵蚀收益；年换手若升至 100%，额外成本约 +0.5%/年。</div>
          </section>

          <div className="callout">
            <b>组合体检边界：</b>只给风险来源与可核对数据，不推荐具体标的，不构成投资建议。
          </div>
          <Disclaimer>示例持仓 · 收盘数据 · 非实时 · 不构成投资建议</Disclaimer>
        </>
      ) : null}

      <ImportSheet open={importOpen} onClose={() => setImportOpen(false)} onDone={(next) => { setData(next); setImportOpen(false); toast("持仓已更新"); }} />
    </div>
  );
}

function ImportSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (data: any) => void }) {
  const toast = useToast();
  const [text, setText] = useState("600036,4845,38.20\n300750,894,252.00\n600519,116,1620.00\n510300,46046,3.95\nCASH,86400,1");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const holdings = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
        const [code, shares, cost] = line.split(",").map((x) => x.trim());
        return { code, shares: Number(shares), cost: Number(cost) };
      });
      if (holdings.some((h) => !h.code || !Number.isFinite(h.shares))) throw new Error("格式：代码,数量,成本；CASH 的数量即金额");
      const data = await api("/api/invest/portfolio/import", { method: "POST", body: JSON.stringify({ holdings }) });
      onDone(data);
    } catch (e: any) {
      toast(e.message || "导入失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="导入持仓" sub="本地解析 · 不上传券商密码" footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy}>{busy ? "导入中…" : "导入并体检"}</button>}>
      <p className="muted small">每行：代码,数量,成本。现金用 <code>CASH,金额,1</code>。示例数据可直接修改。</p>
      <textarea className="csv-input" rows={7} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="callout blue"><Info size={15} /><span>持仓只用于组合体检；公开版还需补注册、找回密码、客服与正式合规流程。</span></div>
    </Sheet>
  );
}
