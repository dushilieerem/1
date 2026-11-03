import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronDown, Info, Upload } from "lucide-react";
import { api } from "../api";
import { BarRow, Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, RiskRing, Sheet, Tag } from "../components";
import { fmtPct, fmtSignedMoney, fmtWan } from "../lib";
import { useToast } from "../toast";
import AiPanel from "../components/AiPanel";

type RangeKey = "1m" | "3m" | "1y";
type TabKey = "holdings" | "checkup";

type NavData = {
  dates: string[];
  portfolio: Array<number | null>;
  benchmark: Array<number | null>;
  coveragePct?: number;
  note?: string;
};

const RANGE_LABEL: Record<RangeKey, string> = { "1m": "近1月", "3m": "近3月", "1y": "近1年" };
const TONE_COLOR: Record<string, string> = {
  green: "var(--green)",
  amber: "var(--amber)",
  orange: "#ea580c",
  red: "var(--red)",
};
const TONE_TAG: Record<string, "green" | "amber" | "orange" | "red"> = {
  green: "green",
  amber: "amber",
  orange: "orange",
  red: "red",
};

function signedPctPoints(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}pct`;
}

function toneClass(value: number | null | undefined) {
  if (value === null || value === undefined || value === 0) return "muted";
  return value > 0 ? "up" : "down";
}

function Curve({ nav, loading }: { nav: NavData | null; loading: boolean }) {
  if (loading) return <div className="pf-curve-empty">曲线加载中…</div>;
  const dates = nav?.dates || [];
  const portfolio = nav?.portfolio || [];
  const benchmark = nav?.benchmark || [];
  if (dates.length < 2) return <div className="pf-curve-empty">净值曲线待补充</div>;

  const all = [...portfolio, ...benchmark].filter((v): v is number => v !== null && v !== undefined);
  const min = Math.min(0, ...all);
  const max = Math.max(0, ...all);
  const span = max - min || 1;
  const W = 320;
  const H = 150;
  const P = 8;
  const x = (i: number) => P + (i / (dates.length - 1)) * (W - P * 2);
  const y = (v: number) => H - P - ((v - min) / span) * (H - P * 2);

  const path = (values: Array<number | null>) => {
    let d = "";
    let open = false;
    values.forEach((v, i) => {
      if (v === null || v === undefined) {
        open = false;
        return;
      }
      d += `${open ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      open = true;
    });
    return d;
  };
  const zeroY = y(0);
  return (
    <svg className="pf-curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="我的组合与沪深300净值曲线">
      {min < 0 && max > 0 ? (
        <line x1={P} x2={W - P} y1={zeroY} y2={zeroY} className="pf-zero" />
      ) : null}
      <path d={path(benchmark)} className="pf-line-bench" fill="none" />
      <path d={path(portfolio)} className="pf-line-mine" fill="none" />
    </svg>
  );
}

function TargetSheet({
  open,
  holdings,
  onClose,
  onDone,
}: {
  open: boolean;
  holdings: any[];
  onClose: () => void;
  onDone: (data: any) => void;
}) {
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValues(Object.fromEntries(holdings.map((h) => [h.code, String(h.targetWeight || 0)])));
  }, [open, holdings]);

  const total = holdings.reduce((sum, h) => sum + (Number(values[h.code]) || 0), 0);
  const allZero = holdings.every((h) => (Number(values[h.code]) || 0) === 0);
  const valid = allZero || Math.abs(total - 100) <= 0.1;

  const submit = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      const data = await api("/api/invest/portfolio/targets", {
        method: "POST",
        body: JSON.stringify({
          targets: holdings.map((h) => ({ code: h.code, targetWeight: Number(values[h.code]) || 0 })),
        }),
      });
      onDone(data);
      toast(allZero ? "已清除目标配置" : "目标配置已保存");
    } catch (e: any) {
      toast(e.message || "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="设定目标配置"
      sub="目标合计需为 100%；全部为 0 表示清除目标"
      footer={
        <button className="btn btn-primary w100" onClick={submit} disabled={busy || !valid}>
          {busy ? "保存中…" : `保存目标（合计 ${total.toFixed(1)}%）`}
        </button>
      }
    >
      <div className="target-list">
        {holdings.map((h) => (
          <div className="target-row" key={h.code}>
            <div>
              <b>{h.name}</b>
              <span>{h.code} · 当前 {h.weight}%</span>
            </div>
            <div className="target-input">
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={values[h.code] ?? ""}
                onChange={(e) => setValues({ ...values, [h.code]: e.target.value })}
                aria-label={`${h.name} 目标权重`}
              />
              <span>%</span>
            </div>
          </div>
        ))}
      </div>
      <p className={valid ? "hint" : "hint down"}>
        {allZero ? "全部为 0：保存后清除目标配置。" : `当前合计 ${total.toFixed(1)}%，需为 100%。`}
      </p>
      <div className="callout blue">
        <Info size={15} />
        <span>目标只用于展示偏离，不构成调仓建议；本产品不自动调仓。</span>
      </div>
    </Sheet>
  );
}

export default function Portfolio() {
  const nav = useNavigate();
  const toast = useToast();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [tab, setTab] = useState<TabKey>("holdings");
  const [range, setRange] = useState<RangeKey>("1m");
  const [navData, setNavData] = useState<NavData | null>(null);
  const [navLoading, setNavLoading] = useState(false);
  const [methodOpen, setMethodOpen] = useState(false);
  const [targetOpen, setTargetOpen] = useState(false);
  const [costOpen, setCostOpen] = useState(false);
  const navCache = useRef<Record<string, NavData>>({});

  const load = () => {
    setError(null);
    api("/api/invest/portfolio").then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  useEffect(() => {
    if (!data?.holdings?.length) return;
    let cancelled = false;
    if (navCache.current[range]) {
      setNavData(navCache.current[range]);
      return;
    }
    setNavLoading(true);
    api<NavData>(`/api/invest/portfolio/nav?range=${range}`)
      .then((d) => {
        navCache.current[range] = d;
        if (!cancelled) setNavData(d);
      })
      .catch(() => {
        if (!cancelled) setNavData(null);
      })
      .finally(() => {
        if (!cancelled) setNavLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range, data?.holdings?.length]);

  const switchTab = (next: TabKey) => {
    setTab(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleImported = (next: any) => {
    setData(next);
    navCache.current = {};
    setNavData(null);
    setImportOpen(false);
    toast("持仓已更新");
    if (next?.holdings?.length) {
      setNavLoading(true);
      api<NavData>(`/api/invest/portfolio/nav?range=${range}`)
        .then((d) => {
          navCache.current[range] = d;
          setNavData(d);
        })
        .catch(() => setNavData(null))
        .finally(() => setNavLoading(false));
    }
  };

  if (data && data.holdings.length === 0) {
    return (
      <div className="page">
        <PageHeader
          title="组合"
          sub="尚未导入持仓"
          right={<button className="round-btn" onClick={() => setImportOpen(true)} aria-label="导入持仓"><Upload size={18} /></button>}
        />
        <EmptyState
          title="还没有组合"
          detail="导入 CSV 或手工持仓，才能看收益、归因、集中度、行业暴露与压力测试。"
          action={<button className="btn btn-primary" onClick={() => setImportOpen(true)}>导入持仓</button>}
        />
        <ImportSheet open={importOpen} onClose={() => setImportOpen(false)} onDone={handleImported} />
      </div>
    );
  }

  const attribution = data?.attribution || { items: [], total: 0, needReview: false, summary: "" };
  const holdings = data?.holdings || [];
  const exposure = data?.exposure || [];
  const maxWeight = Math.max(1, ...exposure.map((e: any) => Number(e.weight) || 0));
  const diagnosis = data?.diagnosis || [];
  const stress = data?.stress || [];
  const costs = data?.costs || {};
  const riskMethod = data?.riskMethod || { items: [], coveragePct: 0 };
  const penetration = data?.penetration;
  const targetConfigured = Boolean(data?.targetConfigured);
  const riskTone = data?.riskTone || "amber";

  return (
    <div className="page">
      <PageHeader
        title="组合"
        sub={data ? `${data.holdings.length} 个持仓 · ${data.dataDate}` : "加载中"}
        right={<button className="round-btn" onClick={() => setImportOpen(true)} aria-label="导入持仓"><Upload size={18} /></button>}
      />

      <div className="seg" role="tablist" aria-label="组合视图">
        <button className={`seg-btn ${tab === "holdings" ? "on" : ""}`} role="tab" aria-selected={tab === "holdings"} onClick={() => switchTab("holdings")}>持仓</button>
        <button className={`seg-btn ${tab === "checkup" ? "on" : ""}`} role="tab" aria-selected={tab === "checkup"} onClick={() => switchTab("checkup")}>体检</button>
      </div>

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data && tab === "holdings" ? (
        <>
          <section className="card pf-overview">
            <div className="pf-total-label">总资产（元）</div>
            <div className="pf-total">{fmtWan(data.totalValue)}</div>
            <div className="pf-returns">
              <div className="pf-ret">
                <span>今日</span>
                <b className={toneClass(data.dailyChange)}>{fmtPct(data.dailyChange)}</b>
                <em className={toneClass(data.dailyPnl)}>{fmtSignedMoney(data.dailyPnl)}</em>
              </div>
              <div className="pf-ret">
                <span>累计</span>
                <b className={toneClass(data.totalPnlPct)}>{fmtPct(data.totalPnlPct)}</b>
                <em className={toneClass(data.totalPnl)}>{fmtSignedMoney(data.totalPnl)}</em>
              </div>
            </div>
            <div className="pf-range" role="group" aria-label="曲线区间">
              {(["1m", "3m", "1y"] as RangeKey[]).map((r) => (
                <button key={r} className={range === r ? "on" : ""} onClick={() => setRange(r)}>{RANGE_LABEL[r]}</button>
              ))}
            </div>
            <div className="pf-legend">
              <span><i className="pf-dot mine" />我的组合</span>
              <span><i className="pf-dot bench" />沪深300</span>
            </div>
            <Curve nav={navData} loading={navLoading} />
            <p className="hint">按当前持仓回溯，买入并持有假设；不代表真实历史成交。</p>
          </section>

          <section className="card">
            <div className="card-title-row">
              <h2>今日归因</h2>
              <span className="hint">贡献 = 权重 × 涨跌</span>
            </div>
            {attribution.items.length ? (
              <div className="attr-list">
                <div className="attr-row attr-head"><span>标的</span><span>当日</span><span>贡献</span></div>
                {attribution.items.map((it: any) => (
                  <div className="attr-row" key={it.code}>
                    <span className="attr-name">{it.name}</span>
                    <span className={toneClass(it.changePct)}>{it.isCash ? "0.00%" : fmtPct(it.changePct)}</span>
                    <b className={toneClass(it.contributionPct)}>{signedPctPoints(it.contributionPct)}</b>
                  </div>
                ))}
                <div className="attr-row attr-total">
                  <b>合计</b>
                  <span className="muted">—</span>
                  <b className={toneClass(attribution.total)}>{signedPctPoints(attribution.total)}</b>
                </div>
              </div>
            ) : (
              <div className="empty-inline">暂无归因数据。</div>
            )}
            <div className="attr-summary">
              {attribution.needReview ? <Tag tone="amber">归因待核</Tag> : null}
              <span>{attribution.summary}</span>
            </div>
          </section>

          <section className="card">
            <div className="card-title-row">
              <h2>持仓</h2>
              <span className="hint">{holdings.length} 个 · 按权重</span>
            </div>
            <div className="hold-head">
              <span>名称</span><span>权重</span><span>市值</span><span>今日</span><span>浮盈亏</span>
            </div>
            <div className="hold-list">
              {holdings.map((h: any) => (
                <div
                  className={`hold-grid ${h.isCash ? "cash" : ""}`}
                  key={h.code}
                  role={h.isCash ? undefined : "button"}
                  tabIndex={h.isCash ? undefined : 0}
                  onClick={() => !h.isCash && nav(`/stock/${h.code}`)}
                  onKeyDown={(e) => {
                    if (!h.isCash && (e.key === "Enter" || e.key === " ")) nav(`/stock/${h.code}`);
                  }}
                >
                  <div className="hold-name">
                    <b>{h.name}</b>
                    <span title={h.industryFull || h.industry}>{h.isCash ? "—" : `${h.code} · ${h.industry}`}</span>
                  </div>
                  <span className="hold-cell">{h.weight}%</span>
                  <span className="hold-cell">{fmtWan(h.value)}</span>
                  <span className={`hold-cell ${h.isCash ? "muted" : toneClass(h.todayPct)}`}>
                    {h.isCash ? "—" : fmtPct(h.todayPct)}
                  </span>
                  <div className="hold-pnl">
                    <b className={h.isCash ? "muted" : toneClass(h.pnlPct)}>{h.isCash ? "—" : fmtPct(h.pnlPct)}</b>
                    {!h.isCash && h.pnlAmount !== null ? (
                      <small className={toneClass(h.pnlAmount)}>{fmtSignedMoney(h.pnlAmount)}</small>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>行业暴露</h2><span className="hint">按市值权重</span></div>
            {exposure.map((e: any) => (
              <BarRow key={e.name} label={e.name} value={e.weight} width={(e.weight / maxWeight) * 100} />
            ))}
            <div className="hint">直接持仓口径；ETF 穿过后在「体检」页查看。</div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>最近调仓</h2><span className="hint">最近 5 条 · 权重变化 / 金额</span></div>
            {data.recentTrades?.length ? (
              <div className="trade-list">
                {data.recentTrades.map((t: any, i: number) => (
                  <div className="trade-row" key={`${t.code}-${t.date}-${i}`}>
                    <span className="trade-date">{t.date.slice(5)}</span>
                    <span className="trade-name">{t.name}</span>
                    <b className={toneClass(t.weightDelta)}>{fmtPct(t.weightDelta, 0)}</b>
                    <b className={toneClass(t.amount)}>{fmtSignedMoney(t.amount)}</b>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-inline">更新持仓后，这里会记录权重变化。</div>
            )}
            <p className="hint">金额按调仓当日市值折算；只记录权重变化，不区分买入 / 卖出，也不构成建议。</p>
          </section>

          <div className="callout">
            <b>组合边界：</b>只给风险来源与可核对数据，不推荐具体标的，不构成投资建议。
          </div>
          <Disclaimer>收盘数据 · 非实时 · 不构成投资建议</Disclaimer>
        </>
      ) : null}

      {data && tab === "checkup" ? (
        <>
          <section className="card ring-card">
            <RiskRing score={data.riskScore ?? 0} color={TONE_COLOR[riskTone]} />
            <div className="ring-copy">
              <h2 className="row gap6">
                {data.riskLabel}
                <Tag tone={TONE_TAG[riskTone] || "amber"}>{data.riskScore > 40 ? "需关注" : "结构分散"}</Tag>
              </h2>
              <p>{data.riskSummary}</p>
              <p className="hint">{data.riskNote}</p>
              <button className="link-btn" onClick={() => setMethodOpen(true)}>风险分怎么算 →</button>
            </div>
          </section>

          <div className="kpi-grid">
            {(data.kpis || []).map((k: any) => (
              <div className="kpi" key={k.label}><span>{k.label}</span><b>{k.value}</b></div>
            ))}
          </div>

          <section className="card">
            <div className="card-title-row">
              <h2>诊断结论</h2>
              {diagnosis.length ? <Tag tone="amber">{diagnosis.length} 个待关注</Tag> : <span className="hint">未发现越线项</span>}
            </div>
            <div className="diag-list">
              {diagnosis.map((d: any) => (
                <div className={`diag-item diag-${d.level}`} key={d.id}>
                  <AlertTriangle size={18} />
                  <div>
                    <b>{d.title}</b>
                    <span>{d.evidence}</span>
                    <em>{d.impact}</em>
                  </div>
                </div>
              ))}
              {!diagnosis.length ? <div className="empty-inline">未发现越线项。</div> : null}
            </div>
            {data.diagnosisHidden ? <p className="hint">另有 {data.diagnosisHidden} 项未展开，按严重度优先展示前 5 项。</p> : null}
            {penetration ? (
              <p className="hint">
                ETF 穿透覆盖 {penetration.coveragePct ?? 0}%
                {penetration.unmapped?.length ? `；未覆盖：${penetration.unmapped.map((x: any) => x.name).join("、")}` : ""}
                。未覆盖部分不计为 0。
              </p>
            ) : null}
          </section>

          <AiPanel
            title="AI 深度解读"
            subtitle="在诊断结论之上，逐项展开风险来源、历史对照与需要留意的变量。约 1–2 分钟。"
            endpoint="/api/invest/ai/portfolio/deep"
            buttonLabel="生成深度解读"
          />

          <section className="card">
            <div className="card-title-row"><h2>配置偏离</h2><span className="hint">目标 vs 当前</span></div>
            {targetConfigured ? (
              <>
                <div className="dev-list">
                  {(data.deviation || []).map((d: any) => (
                    <div className="dev-row" key={d.code}>
                      <span>{d.name}</span>
                      <span>目标 {d.target}% · 当前 {d.current}%</span>
                      <b className={toneClass(d.diff)}>{fmtPct(d.diff, 0)}</b>
                      <Tag tone={d.status === "达标" ? "green" : "amber"}>{d.status}</Tag>
                    </div>
                  ))}
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => setTargetOpen(true)}>调整目标配置</button>
              </>
            ) : (
              <div className="target-empty">
                <b>还没有设定目标配置</b>
                <p className="hint">设定后才能看到目标与当前的偏离；不会把当前权重自动当成目标。</p>
                <button className="btn btn-primary btn-sm" onClick={() => setTargetOpen(true)}>设定目标配置</button>
              </div>
            )}
            <div className="callout blue"><Info size={15} /><span>偏离只用于理解组合，不构成调仓建议；本产品不自动调仓。</span></div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>压力测试与成本</h2><span className="hint">假设冲击 · 非预测</span></div>
            {stress.map((s: any) => (
              <div className="stress-row" key={s.key || s.name}>
                <span>{s.name}</span>
                {s.value === null || s.value === undefined ? (
                  <span className="muted">无相关暴露</span>
                ) : (
                  <b className={toneClass(s.value)}>{fmtPct(s.value, 1)}</b>
                )}
              </div>
            ))}
            <p className="hint">情景是假设不是预测，未考虑相关性变化与流动性冲击。</p>
            <button className="cost-toggle" onClick={() => setCostOpen((v) => !v)} aria-expanded={costOpen}>
              成本明细 <ChevronDown size={15} className={costOpen ? "rot" : ""} />
            </button>
            {costOpen ? (
              <div className="cost-list">
                <div className="kv"><span>预估再平衡交易成本</span><b>约 {costs.tradeCostPct}%</b></div>
                <div className="kv"><span>示例年化换手率</span><b>{costs.annualTurnover}%</b></div>
                <div className="kv"><span>单次调仓冲击成本</span><b>约 {costs.impactCostPct}%</b></div>
                <div className="kv"><span>年化换手成本</span><b>{costs.turnoverCostPct}%</b></div>
              </div>
            ) : null}
          </section>

          <div className="callout">
            <b>体检边界：</b>分数只反映持仓结构，不预测盈亏；只给风险来源与可核对数据。
          </div>
          <Disclaimer>收盘数据 · 非实时 · 不构成投资建议</Disclaimer>
        </>
      ) : null}

      <ImportSheet open={importOpen} onClose={() => setImportOpen(false)} onDone={handleImported} />
      <TargetSheet
        open={targetOpen}
        holdings={holdings}
        onClose={() => setTargetOpen(false)}
        onDone={(next) => {
          setData(next);
          setTargetOpen(false);
        }}
      />

      <Sheet open={methodOpen} onClose={() => setMethodOpen(false)} title="风险分怎么算" sub="6 项加权 · 分数越高，代表风险越集中">
        <div className="method-list">
          {riskMethod.items?.map((it: any) => (
            <div className="method-row" key={it.key}>
              <div>
                <b>{it.label}</b>
                <span>{it.detail}</span>
              </div>
              <div className="method-score">
                <b>{it.available ? Math.round(it.score) : "待补充"}</b>
                <small>权重 {it.weight}%</small>
              </div>
            </div>
          ))}
        </div>
        <p className="hint">本次覆盖率 {riskMethod.coveragePct}%；缺失项不参与计算。</p>
        <div className="callout blue">
          <Info size={15} />
          <span>分数只反映持仓结构，不预测盈亏；数据缺失时结论可信度下降，页面会标注「待补充」。</span>
        </div>
      </Sheet>
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
