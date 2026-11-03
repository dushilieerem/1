import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronDown, Info, Upload } from "lucide-react";
import { api } from "../api";
import { BarRow, Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, RiskRing, Sheet, Tag } from "../components";
import { displayIndustry, fmtPct, fmtSignedMoney, fmtWan } from "../lib";
import { useToast } from "../toast";
import { useLocale } from "../i18n";
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

const RANGE_LABEL: Record<RangeKey, { zh: string; en: string }> = {
  "1m": { zh: "近1月", en: "1M" },
  "3m": { zh: "近3月", en: "3M" },
  "1y": { zh: "近1年", en: "1Y" },
};
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
const RISK_LABEL_EN: Record<string, string> = {
  分散: "Diversified",
  偏集中: "Moderately concentrated",
  较集中: "Concentrated",
  高度集中: "Highly concentrated",
};
const KPI_LABEL_EN: Record<string, string> = {
  总资产: "Total assets",
  前三大持仓: "Top 3 weight",
  最大行业暴露: "Largest sector",
  历史最大回撤: "Max drawdown",
};
const STATUS_EN: Record<string, string> = {
  达标: "On target",
  超配: "Overweight",
  低配: "Underweight",
};
const STRESS_NAME_EN: Record<string, string> = {
  "沪深 300 −10%": "CSI 300 −10%",
  "利率 +50bp": "Rates +50bp",
  "新能源 −15%": "New energy −15%",
  "消费 −10%": "Consumption −10%",
};
const METHOD_LABEL_EN: Record<string, string> = {
  集中度: "Concentration",
  行业集中: "Sector concentration",
  "ETF 穿透": "ETF look-through",
  相关性: "Correlation",
  估值分位: "Valuation percentile",
  换手成本: "Turnover cost",
};
const DIAG_TITLE_EN: Record<string, string> = {
  单票集中: "Single-name concentration",
  前三大持仓偏高: "Top-3 concentration",
  行业集中度偏高: "Sector concentration",
  穿透后集中度更高: "Higher look-through concentration",
  持仓相关性偏高: "High holding correlation",
  低流动性持仓偏高: "Illiquid holdings",
  估值分位偏高: "High valuation percentile",
  换手成本偏高: "High turnover cost",
};

function localized(map: Record<string, string>, value: string, locale: string) {
  return locale === "en" ? map[value] || value : value;
}

function kpiValue(value: string, locale: string) {
  if (locale !== "en") return value;
  const text = String(value || "");
  if (text.endsWith(" 万")) return `${(Number.parseFloat(text) * 10).toFixed(0)}K`;
  if (text.endsWith(" 亿")) return `${(Number.parseFloat(text) / 10).toFixed(2)}B`;
  return text;
}

function localizedRiskSummary(value: string, locale: string) {
  if (locale !== "en" || !value) return value;
  if (value.startsWith("风险主要来自「")) {
    const inner = value.slice("风险主要来自「".length, value.indexOf("」"));
    const labels = inner
      .split(" + ")
      .map((x) => METHOD_LABEL_EN[x] || x)
      .join(" + ");
    return `Risk mainly comes from "${labels}", not broad market moves.`;
  }
  if (value.startsWith("持仓结构相对分散")) {
    return "The portfolio structure is relatively diversified; the main uncertainty comes from broad market moves.";
  }
  return value;
}

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
  const { t } = useLocale();
  if (loading) return <div className="pf-curve-empty">{t("曲线加载中…", "Loading chart…")}</div>;
  const dates = nav?.dates || [];
  const portfolio = nav?.portfolio || [];
  const benchmark = nav?.benchmark || [];
  if (dates.length < 2) return <div className="pf-curve-empty">{t("净值曲线待补充", "NAV curve not yet available")}</div>;

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
    <svg className="pf-curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("我的组合与沪深300净值曲线", "My portfolio vs CSI 300 NAV curve")}>
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
  const { t } = useLocale();
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
      toast(allZero ? t("已清除目标配置", "Target allocation cleared") : t("目标配置已保存", "Target allocation saved"));
    } catch (e: any) {
      toast(e.message || t("保存失败", "Save failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("设定目标配置", "Set target allocation")}
      sub={t("目标合计需为 100%；全部为 0 表示清除目标", "Targets must sum to 100%; all zeros clears the target")}
      footer={
        <button className="btn btn-primary w100" onClick={submit} disabled={busy || !valid}>
          {busy ? t("保存中…", "Saving…") : `${t("保存目标", "Save targets")}${t("（", " (")}${t("合计", "total")} ${total.toFixed(1)}%${t("）", ")")}`}
        </button>
      }
    >
      <div className="target-list">
        {holdings.map((h) => (
          <div className="target-row" key={h.code}>
            <div>
              <b>{h.name}</b>
              <span>{h.code} · {t("当前", "Current")} {h.weight}%</span>
            </div>
            <div className="target-input">
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={values[h.code] ?? ""}
                onChange={(e) => setValues({ ...values, [h.code]: e.target.value })}
                aria-label={`${h.name} ${t("目标权重", "target weight")}`}
              />
              <span>%</span>
            </div>
          </div>
        ))}
      </div>
      <p className={valid ? "hint" : "hint down"}>
        {allZero
          ? t("全部为 0：保存后清除目标配置。", "All zeros: saving clears the target allocation.")
          : t(`当前合计 ${total.toFixed(1)}%，需为 100%。`, `Current total ${total.toFixed(1)}%; must equal 100%.`)}
      </p>
      <div className="callout blue">
        <Info size={15} />
        <span>{t("目标只用于展示偏离，不构成调仓建议；本产品不自动调仓。", "Targets are for showing deviations only and are not rebalancing advice; this product never trades automatically.")}</span>
      </div>
    </Sheet>
  );
}

export default function Portfolio() {
  const { t, locale } = useLocale();
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
    toast(t("持仓已更新", "Holdings updated"));
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
          title={t("组合", "Portfolio")}
          sub={t("尚未导入持仓", "No holdings imported yet")}
          right={<button className="round-btn" onClick={() => setImportOpen(true)} aria-label={t("导入持仓", "Import holdings")}><Upload size={18} /></button>}
        />
        <EmptyState
          title={t("还没有组合", "No portfolio yet")}
          detail={t("导入 CSV 或手工持仓，才能看收益、归因、集中度、行业暴露与压力测试。", "Import a CSV or enter holdings manually to see returns, attribution, concentration, sector exposure and stress tests.")}
          action={<button className="btn btn-primary" onClick={() => setImportOpen(true)}>{t("导入持仓", "Import holdings")}</button>}
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
        title={t("组合", "Portfolio")}
        sub={data ? `${data.holdings.length} ${t("个持仓", "holdings")} · ${data.dataDate}` : t("加载中", "Loading")}
        right={<button className="round-btn" onClick={() => setImportOpen(true)} aria-label={t("导入持仓", "Import holdings")}><Upload size={18} /></button>}
      />

      <div className="pf-seg" role="tablist" aria-label={t("组合视图", "Portfolio view")}>
        <button className={`pf-seg-btn ${tab === "holdings" ? "on" : ""}`} role="tab" aria-selected={tab === "holdings"} onClick={() => switchTab("holdings")}>{t("持仓", "Holdings")}</button>
        <button className={`pf-seg-btn ${tab === "checkup" ? "on" : ""}`} role="tab" aria-selected={tab === "checkup"} onClick={() => switchTab("checkup")}>{t("体检", "Checkup")}</button>
      </div>

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data && tab === "holdings" ? (
        <>
          <section className="card pf-overview">
            <div className="pf-total-label">{t("总资产（元）", "Total assets (CNY)")}</div>
            <div className="pf-total">{fmtWan(data.totalValue)}</div>
            <div className="pf-returns">
              <div className="pf-ret">
                <span>{t("今日", "Today")}</span>
                <b className={toneClass(data.dailyChange)}>{fmtPct(data.dailyChange)}</b>
                <em className={toneClass(data.dailyPnl)}>{fmtSignedMoney(data.dailyPnl)}</em>
              </div>
              <div className="pf-ret">
                <span>{t("累计", "Total")}</span>
                <b className={toneClass(data.totalPnlPct)}>{fmtPct(data.totalPnlPct)}</b>
                <em className={toneClass(data.totalPnl)}>{fmtSignedMoney(data.totalPnl)}</em>
              </div>
            </div>
            <div className="pf-range" role="group" aria-label={t("曲线区间", "Chart range")}>
              {(["1m", "3m", "1y"] as RangeKey[]).map((r) => (
                <button key={r} className={range === r ? "on" : ""} onClick={() => setRange(r)}>{t(RANGE_LABEL[r].zh, RANGE_LABEL[r].en)}</button>
              ))}
            </div>
            <div className="pf-legend">
              <span><i className="pf-dot mine" />{t("我的组合", "My portfolio")}</span>
              <span><i className="pf-dot bench" />{t("沪深300", "CSI 300")}</span>
            </div>
            <Curve nav={navData} loading={navLoading} />
            <p className="hint">{t("按当前持仓回溯，买入并持有假设；不代表真实历史成交。", "Backtested from current holdings under a buy-and-hold assumption; not actual historical trades.")}</p>
          </section>

          <section className="card">
            <div className="card-title-row">
              <h2>{t("今日归因", "Today's attribution")}</h2>
              <span className="hint">{t("贡献 = 权重 × 涨跌", "Contribution = weight × change")}</span>
            </div>
            {attribution.items.length ? (
              <div className="attr-list">
                <div className="attr-row attr-head"><span>{t("标的", "Asset")}</span><span>{t("当日", "Today")}</span><span>{t("贡献", "Contribution")}</span></div>
                {attribution.items.map((it: any) => (
                  <div className="attr-row" key={it.code}>
                    <span className="attr-name">{it.name}</span>
                    <span className={toneClass(it.changePct)}>{it.isCash ? "0.00%" : fmtPct(it.changePct)}</span>
                    <b className={toneClass(it.contributionPct)}>{signedPctPoints(it.contributionPct)}</b>
                  </div>
                ))}
                <div className="attr-row attr-total">
                  <b>{t("合计", "Total")}</b>
                  <span className="muted">—</span>
                  <b className={toneClass(attribution.total)}>{signedPctPoints(attribution.total)}</b>
                </div>
              </div>
            ) : (
              <div className="empty-inline">{t("暂无归因数据。", "No attribution data yet.")}</div>
            )}
            <div className="attr-summary">
              {attribution.needReview ? <Tag tone="amber">{t("归因待核", "Attribution pending")}</Tag> : null}
              <span>{attribution.summary}</span>
            </div>
          </section>

          <section className="card">
            <div className="card-title-row">
              <h2>{t("持仓", "Holdings")}</h2>
              <span className="hint">{holdings.length} {t("个 · 按权重", "positions · by weight")}</span>
            </div>
            <div className="hold-head">
              <span>{t("名称", "Name")}</span><span>{t("权重", "Weight")}</span><span>{t("市值", "Value")}</span><span>{t("今日", "Today")}</span><span>{t("浮盈亏", "P&L")}</span>
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
                    <span title={h.industryFull || h.industry}>{h.isCash ? "—" : `${h.code} · ${displayIndustry(h.industry)}`}</span>
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
            <div className="card-title-row"><h2>{t("行业暴露", "Sector exposure")}</h2><span className="hint">{t("按市值权重", "By market value weight")}</span></div>
            {exposure.map((e: any) => (
              <BarRow key={e.name} label={displayIndustry(e.name)} value={e.weight} width={(e.weight / maxWeight) * 100} />
            ))}
            <div className="hint">{t("直接持仓口径；ETF 穿过后在「体检」页查看。", "Direct holdings only; see the Checkup tab for ETF look-through.")}</div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("最近调仓", "Recent trades")}</h2><span className="hint">{t("最近 5 条 · 权重变化 / 金额", "Last 5 · weight change / amount")}</span></div>
            {data.recentTrades?.length ? (
              <div className="trade-list">
                {data.recentTrades.map((trade: any, i: number) => (
                  <div className="trade-row" key={`${trade.code}-${trade.date}-${i}`}>
                    <span className="trade-date">{trade.date.slice(5)}</span>
                    <span className="trade-name">{trade.name}</span>
                    <b className={toneClass(trade.weightDelta)}>{fmtPct(trade.weightDelta, 0)}</b>
                    <b className={toneClass(trade.amount)}>{fmtSignedMoney(trade.amount)}</b>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-inline">{t("更新持仓后，这里会记录权重变化。", "Weight changes will appear here after you update holdings.")}</div>
            )}
            <p className="hint">{t("金额按调仓当日市值折算；只记录权重变化，不区分买入 / 卖出，也不构成建议。", "Amounts are converted at the market value on the trade date; only weight changes are recorded, buys and sells are not distinguished, and this is not advice.")}</p>
          </section>

          <div className="callout">
            <b>{t("组合边界：", "Portfolio scope: ")}</b>{t("只给风险来源与可核对数据，不推荐具体标的，不构成投资建议。", "We only surface risk sources and verifiable data; we do not recommend specific securities and this is not investment advice.")}
          </div>
          <Disclaimer>{t("收盘数据 · 非实时 · 不构成投资建议", "Closing data · Not real-time · Not investment advice")}</Disclaimer>
        </>
      ) : null}

      {data && tab === "checkup" ? (
        <>
          <section className="card ring-card">
            <RiskRing score={data.riskScore ?? 0} color={TONE_COLOR[riskTone]} />
            <div className="ring-copy">
              <h2 className="row gap6">
                {localized(RISK_LABEL_EN, data.riskLabel, locale)}
                <Tag tone={TONE_TAG[riskTone] || "amber"}>{data.riskScore > 40 ? t("需关注", "Needs attention") : t("结构分散", "Diversified")}</Tag>
              </h2>
              <p>{localizedRiskSummary(data.riskSummary, locale)}</p>
              <p className="hint">{locale === "en" ? "The score reflects portfolio structure only and does not forecast returns; higher means more concentrated." : data.riskNote}</p>
              <button className="link-btn" onClick={() => setMethodOpen(true)}>{t("风险分怎么算 →", "How is the risk score calculated →")}</button>
            </div>
          </section>

          <div className="kpi-grid">
            {(data.kpis || []).map((k: any) => (
              <div className="kpi" key={k.label}><span>{localized(KPI_LABEL_EN, k.label, locale)}</span><b>{kpiValue(k.value, locale)}</b></div>
            ))}
          </div>

          <section className="card">
            <div className="card-title-row">
              <h2>{t("诊断结论", "Diagnosis")}</h2>
              {diagnosis.length ? <Tag tone="amber">{diagnosis.length} {t("个待关注", "flagged")}</Tag> : <span className="hint">{t("未发现越线项", "No breaches found")}</span>}
            </div>
            <div className="diag-list">
              {diagnosis.map((d: any) => (
                <div className={`diag-item diag-${d.level}`} key={d.id}>
                  <AlertTriangle size={18} />
                  <div>
                    <b>{localized(DIAG_TITLE_EN, d.title, locale)}</b>
                    <span>{d.evidence}</span>
                    <em>{d.impact}</em>
                  </div>
                </div>
              ))}
              {!diagnosis.length ? <div className="empty-inline">{t("未发现越线项。", "No breaches found.")}</div> : null}
            </div>
            {data.diagnosisHidden ? <p className="hint">{t(`另有 ${data.diagnosisHidden} 项未展开，按严重度优先展示前 5 项。`, `${data.diagnosisHidden} more items are hidden; the top 5 by severity are shown.`)}</p> : null}
            {penetration ? (
              <p className="hint">
                {t("ETF 穿透覆盖", "ETF look-through coverage")} {penetration.coveragePct ?? 0}%
                {penetration.unmapped?.length ? t(`；未覆盖：${penetration.unmapped.map((x: any) => x.name).join("、")}`, `; uncovered: ${penetration.unmapped.map((x: any) => x.name).join(", ")}`) : ""}
                {t("。未覆盖部分不计为 0。", ". Uncovered positions are not counted as zero.")}
              </p>
            ) : null}
          </section>

          <AiPanel
            title={t("AI 深度解读", "AI deep dive")}
            subtitle={t("在诊断结论之上，逐项展开风险来源、历史对照与需要留意的变量。约 1–2 分钟。", "Builds on the diagnosis to unpack each risk source, historical comparison and variables to watch. About 1–2 minutes.")}
            endpoint="/api/invest/ai/portfolio/deep"
            buttonLabel={t("生成深度解读", "Generate deep dive")}
          />

          <section className="card">
            <div className="card-title-row"><h2>{t("配置偏离", "Allocation drift")}</h2><span className="hint">{t("目标 vs 当前", "Target vs current")}</span></div>
            {targetConfigured ? (
              <>
                <div className="dev-list">
                  {(data.deviation || []).map((d: any) => (
                    <div className="dev-row" key={d.code}>
                      <span>{d.name}</span>
                      <span>{t("目标", "Target")} {d.target}% · {t("当前", "Current")} {d.current}%</span>
                      <b className={toneClass(d.diff)}>{fmtPct(d.diff, 0)}</b>
                      <Tag tone={d.status === "达标" ? "green" : "amber"}>{localized(STATUS_EN, d.status, locale)}</Tag>
                    </div>
                  ))}
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => setTargetOpen(true)}>{t("调整目标配置", "Adjust targets")}</button>
              </>
            ) : (
              <div className="target-empty">
                <b>{t("还没有设定目标配置", "No target allocation set")}</b>
                <p className="hint">{t("设定后才能看到目标与当前的偏离；不会把当前权重自动当成目标。", "Set targets to see target-vs-current drift; current weights are never treated as targets automatically.")}</p>
                <button className="btn btn-primary btn-sm" onClick={() => setTargetOpen(true)}>{t("设定目标配置", "Set target allocation")}</button>
              </div>
            )}
            <div className="callout blue"><Info size={15} /><span>{t("偏离只用于理解组合，不构成调仓建议；本产品不自动调仓。", "Drift is for understanding the portfolio only and is not rebalancing advice; this product never trades automatically.")}</span></div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("压力测试与成本", "Stress tests & costs")}</h2><span className="hint">{t("假设冲击 · 非预测", "Hypothetical shocks · Not forecasts")}</span></div>
            {stress.map((s: any) => (
              <div className="stress-row" key={s.key || s.name}>
                <span>{localized(STRESS_NAME_EN, s.name, locale)}</span>
                {s.value === null || s.value === undefined ? (
                  <span className="muted">{t("无相关暴露", "No exposure")}</span>
                ) : (
                  <b className={toneClass(s.value)}>{fmtPct(s.value, 1)}</b>
                )}
              </div>
            ))}
            <p className="hint">{t("情景是假设不是预测，未考虑相关性变化与流动性冲击。", "Scenarios are hypothetical, not forecasts, and do not account for correlation shifts or liquidity shocks.")}</p>
            <button className="cost-toggle" onClick={() => setCostOpen((v) => !v)} aria-expanded={costOpen}>
              {t("成本明细", "Cost breakdown")} <ChevronDown size={15} className={costOpen ? "rot" : ""} />
            </button>
            {costOpen ? (
              <div className="cost-list">
                <div className="kv"><span>{t("预估再平衡交易成本", "Estimated rebalancing cost")}</span><b>{t("约", "~")} {costs.tradeCostPct}%</b></div>
                <div className="kv"><span>{t("示例年化换手率", "Example annual turnover")}</span><b>{costs.annualTurnover}%</b></div>
                <div className="kv"><span>{t("单次调仓冲击成本", "One-time market impact cost")}</span><b>{t("约", "~")} {costs.impactCostPct}%</b></div>
                <div className="kv"><span>{t("年化换手成本", "Annual turnover cost")}</span><b>{costs.turnoverCostPct}%</b></div>
              </div>
            ) : null}
          </section>

          <div className="callout">
            <b>{t("体检边界：", "Checkup scope: ")}</b>{t("分数只反映持仓结构，不预测盈亏；只给风险来源与可核对数据。", "Scores reflect portfolio structure only and do not predict profit or loss; we only surface risk sources and verifiable data.")}
          </div>
          <Disclaimer>{t("收盘数据 · 非实时 · 不构成投资建议", "Closing data · Not real-time · Not investment advice")}</Disclaimer>
        </>
      ) : null}

      {locale === "en" ? (
        <p className="hint">{t("英文版组合页仍展示 A 股持仓；美股暂不支持组合导入。", "The English build still shows A-share holdings; US portfolio import is not supported yet.")}</p>
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

      <Sheet open={methodOpen} onClose={() => setMethodOpen(false)} title={t("风险分怎么算", "How the risk score works")} sub={t("6 项加权 · 分数越高，代表风险越集中", "6 weighted factors · The higher the score, the more concentrated the risk")}>
        <div className="method-list">
          {riskMethod.items?.map((it: any) => (
            <div className="method-row" key={it.key}>
              <div>
                <b>{localized(METHOD_LABEL_EN, it.label, locale)}</b>
                <span>{it.detail}</span>
              </div>
              <div className="method-score">
                <b>{it.available ? Math.round(it.score) : t("待补充", "Pending")}</b>
                <small>{t("权重", "Weight")} {it.weight}%</small>
              </div>
            </div>
          ))}
        </div>
        <p className="hint">{t("本次覆盖率", "Coverage this run")} {riskMethod.coveragePct}%{t("；缺失项不参与计算。", "; missing items are excluded from the calculation.")}</p>
        <div className="callout blue">
          <Info size={15} />
          <span>{t("分数只反映持仓结构，不预测盈亏；数据缺失时结论可信度下降，页面会标注「待补充」。", "The score reflects portfolio structure only and does not predict profit or loss; when data is missing, confidence drops and the page marks it as \"Pending\".")}</span>
        </div>
      </Sheet>
    </div>
  );
}

function ImportSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (data: any) => void }) {
  const { t } = useLocale();
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
      if (holdings.some((h) => !h.code || !Number.isFinite(h.shares))) throw new Error(t("格式：代码,数量,成本；CASH 的数量即金额", "Format: code,shares,cost; for CASH the shares column is the amount"));
      const data = await api("/api/invest/portfolio/import", { method: "POST", body: JSON.stringify({ holdings }) });
      onDone(data);
    } catch (e: any) {
      toast(e.message || t("导入失败", "Import failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("导入持仓", "Import holdings")} sub={t("本地解析 · 不上传券商密码", "Parsed locally · Broker password never uploaded")} footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy}>{busy ? t("导入中…", "Importing…") : t("导入并体检", "Import & run checkup")}</button>}>
      <p className="muted small">{t("每行：代码,数量,成本。现金用", "Each line: code,shares,cost. Use")} <code>CASH,{t("金额", "amount")},1</code>{t("。示例数据可直接修改。", ". You can edit the sample data directly.")}</p>
      <textarea className="csv-input" rows={7} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="callout blue"><Info size={15} /><span>{t("持仓只用于组合体检；公开版还需补注册、找回密码、客服与正式合规流程。", "Holdings are used only for the portfolio checkup; the public release still needs sign-up, password recovery, support and formal compliance flows.")}</span></div>
    </Sheet>
  );
}
