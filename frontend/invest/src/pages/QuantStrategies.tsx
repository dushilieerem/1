import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Bookmark, Copy, FlaskConical, Play, RotateCcw, Save, Sparkles, Trash2 } from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Sheet, Sparkline, Tag } from "../components";
import QuantChart from "../components/QuantChart";
import { useLocale } from "../i18n";
import {
  curveValues,
  directionLabel,
  factorFormula,
  factorName,
  fmtSignedPct,
  metric,
  trendClass,
  universeLabel,
  type Backtest,
  type Draft,
  type FactorBoard,
  type FactorMeta,
  type PlazaDetail,
  type PlazaItem,
  type QuantFactor,
  type Strategy,
} from "../quant";

type Tab = "quick" | "mine" | "drafts" | "plaza";

const UNIVERSE_OPTIONS = ["hs300", "zz500", "all"];
const METRIC_ROWS: Array<[string, string, string, "pct" | "pctu" | "num" | "int"]> = [
  ["cumulative", "累计收益", "Total return", "pct"],
  ["annual_return", "年化收益", "Annualized", "pct"],
  ["max_drawdown", "最大回撤", "Max drawdown", "pct"],
  ["sharpe", "夏普", "Sharpe", "num"],
  ["win_rate", "胜率", "Win rate", "pctu"],
  ["trade_count", "交易次数", "Trades", "int"],
];

function parsePreset(raw: string | null): QuantFactor[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => {
      const [key, direction] = part.split(":");
      return key ? ({ key, direction: direction === "low" ? "low" : "high" } as QuantFactor) : null;
    })
    .filter(Boolean) as QuantFactor[];
}

export default function QuantStrategies() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [params] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "quick";
  const [board, setBoard] = useState<FactorBoard | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [plaza, setPlaza] = useState<PlazaItem[]>([]);
  const [plazaSort, setPlazaSort] = useState("followers");
  const [plazaDetail, setPlazaDetail] = useState<PlazaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selected, setSelected] = useState<QuantFactor[]>([]);
  const [universe, setUniverse] = useState("hs300");
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [running, setRunning] = useState(false);
  const [intent, setIntent] = useState("");
  const [parsing, setParsing] = useState(false);

  useEffect(() => {
    setError(null);
    api<FactorBoard>("/api/invest/quant/factors?range=1m")
      .then(setBoard)
      .catch((e) => setError(e.message));
  }, []);

  const presetRaw = params.get("preset");
  useEffect(() => {
    const preset = parsePreset(presetRaw);
    if (preset.length) {
      setSelected(preset.slice(0, 4));
      setStep(preset.length >= 2 ? 2 : 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetRaw]);

  const loadLists = () => {
    setLoading(true);
    Promise.all([
      api<{ items: Strategy[] }>("/api/invest/quant/strategies"),
      api<{ items: Draft[] }>("/api/invest/quant/drafts"),
    ])
      .then(([s, d]) => {
        setStrategies(s.items || []);
        setDrafts(d.items || []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const loadPlaza = (sort: string) => {
    setLoading(true);
    api<{ items: PlazaItem[] }>(`/api/invest/quant/plaza?sort=${sort}`)
      .then((d) => setPlaza(d.items || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (tab === "mine" || tab === "drafts") loadLists();
    else if (tab === "plaza") loadPlaza(plazaSort);
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, plazaSort]);

  const factors = board?.factors || [];
  const selectedMeta = useMemo(
    () =>
      selected
        .map((s) => factors.find((f) => f.key === s.key))
        .filter(Boolean) as FactorMeta[],
    [selected, factors],
  );

  const correlations = useMemo(() => {
    if (!board) return [];
    const out: Array<{ a: string; b: string; r: number }> = [];
    for (let i = 0; i < selected.length; i += 1) {
      for (let j = i + 1; j < selected.length; j += 1) {
        const ia = board.correlation_keys.indexOf(selected[i].key);
        const ib = board.correlation_keys.indexOf(selected[j].key);
        const r = ia >= 0 && ib >= 0 ? board.correlations[ia]?.[ib] : null;
        if (r !== null && r !== undefined && Math.abs(r) > 0.5) {
          out.push({ a: selected[i].key, b: selected[j].key, r });
        }
      }
    }
    return out;
  }, [board, selected]);

  const toggleFactor = (f: FactorMeta) => {
    setSelected((prev) => {
      const exists = prev.find((x) => x.key === f.key);
      if (exists) return prev.filter((x) => x.key !== f.key);
      if (prev.length >= 4) return prev;
      return [...prev, { key: f.key, direction: f.direction }];
    });
  };

  const setDirection = (key: string, direction: "high" | "low") => {
    setSelected((prev) => prev.map((x) => (x.key === key ? { ...x, direction } : x)));
  };

  const parseIntent = async () => {
    if (!intent.trim() || parsing) return;
    setParsing(true);
    setError(null);
    try {
      const data = await api<any>("/api/invest/quant/strategies/parse", {
        method: "POST",
        body: JSON.stringify({ text: intent }),
      });
      if (data.factors?.length >= 2 && !data.need_more) {
        setSelected(data.factors.slice(0, 4));
        setStep(2);
        setNotice(data.understood ? t(`已识别：${data.understood}`, `Interpreted: ${data.understood}`) : null);
      } else {
        setNotice(data.message || t("再多说一个方向，就能生成实验。", "Add one more direction to build the experiment."));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setParsing(false);
    }
  };

  const runBacktest = async () => {
    if (selected.length < 2 || selected.length > 4) {
      setError(t("请选择 2–4 个因子", "Choose 2–4 factors"));
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const data = await api<Backtest>("/api/invest/quant/backtests", {
        method: "POST",
        body: JSON.stringify({ factors: selected, universe }),
      });
      setBacktest(data);
      setStep(3);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const saveDraft = async () => {
    if (!backtest) return;
    try {
      await api("/api/invest/quant/drafts", {
        method: "POST",
        body: JSON.stringify({
          name: backtest.name,
          factors: selected,
          universe,
          last_backtest_id: backtest.id,
        }),
      });
      nav("/quant/strategies?tab=drafts");
    } catch (e: any) {
      setError(e.message);
    }
  };

  const startPaper = async (sourceType: "backtest" | "draft", sourceId: number, name?: string) => {
    try {
      const data = await api<any>("/api/invest/quant/papers", {
        method: "POST",
        body: JSON.stringify({ source_type: sourceType, source_id: sourceId, name }),
      });
      nav(`/quant/papers/${data.id}`);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const deleteDraft = async (id: number) => {
    if (!window.confirm(t("删除这份草稿？", "Delete this draft?"))) return;
    try {
      await api(`/api/invest/quant/drafts/${id}`, { method: "DELETE" });
      setDrafts((prev) => prev.filter((x) => x.id !== id));
    } catch (e: any) {
      setError(e.message);
    }
  };

  const reuseDraft = (draft: Draft) => {
    const next = (draft.factors || []).map((f) => ({
      key: f.key,
      direction: (f.chosen_direction as "high" | "low") || f.direction,
    }));
    setSelected(next.slice(0, 4));
    setUniverse(draft.universe || "hs300");
    setBacktest(null);
    setStep(2);
    nav("/quant/strategies?tab=quick");
  };

  const copyPlaza = async (id: number) => {
    try {
      await api(`/api/invest/quant/plaza/${id}/copy`, { method: "POST" });
      setPlazaDetail(null);
      setNotice(t("已复制到我的草稿", "Copied to my drafts"));
      nav("/quant/strategies?tab=drafts");
    } catch (e: any) {
      setError(e.message);
    }
  };

  const followPlaza = async (item: PlazaItem) => {
    try {
      const data = await api<{ followed: boolean; followers: number }>(`/api/invest/quant/plaza/${item.id}/follow`, {
        method: "POST",
        body: JSON.stringify({ followed: !item.followed }),
      });
      setPlaza((prev) => prev.map((x) => (x.id === item.id ? { ...x, followed: data.followed, followers: data.followers } : x)));
    } catch (e: any) {
      setError(e.message);
    }
  };

  const openPlaza = async (item: PlazaItem) => {
    try {
      const data = await api<PlazaDetail>(`/api/invest/quant/plaza/${item.id}`);
      setPlazaDetail(data);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="page quant-page">
      <PageHeader
        title={t("策略", "Strategies")}
        sub={t("用 2–4 个因子做实验，结果只代表历史", "Experiment with 2–4 factors; results are historical only")}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant")}
      />

      <div className="seg quant-tabs">
        {([
          ["quick", "快速实验", "Quick lab"],
          ["mine", "我的策略", "My strategies"],
          ["drafts", "草稿", "Drafts"],
          ["plaza", "策略广场", "Plaza"],
        ] as Array<[Tab, string, string]>).map(([key, zh, en]) => (
          <button key={key} className={tab === key ? "on" : ""} onClick={() => nav(`/quant/strategies?tab=${key}`)}>
            {t(zh, en)}
          </button>
        ))}
      </div>

      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {notice ? <button className="quant-notice" onClick={() => setNotice(null)}>{notice} ×</button> : null}

      {tab === "quick" ? (
        <>
          {step === 1 ? (
            <>
              <section className="card">
                <div className="card-title-row"><h2>{t("一句话建策略", "One-sentence strategy")}</h2><Tag tone="blue">AI</Tag></div>
                <p className="hint">{t("只把自然语言翻译成因子组合，不推荐股票、不改数值。", "Only translates language into a factor combination; no stock picks or number changes.")}</p>
                <div className="quant-inline-input">
                  <input
                    value={intent}
                    onChange={(e) => setIntent(e.target.value)}
                    placeholder={t("例如：便宜、最近涨得好、别太波动", "e.g. cheap, rising recently, not too volatile")}
                  />
                  <button className="btn btn-primary btn-sm" onClick={() => void parseIntent()} disabled={parsing || !intent.trim()}>
                    <Sparkles size={14} /> {parsing ? t("识别中…", "Parsing…") : t("识别", "Parse")}
                  </button>
                </div>
              </section>

              <section className="card">
                <div className="card-title-row">
                  <h2>{t("选择因子", "Choose factors")}</h2>
                  <span className="hint">{t(`已选 ${selected.length}/4`, `${selected.length}/4 selected`)}</span>
                </div>
                <p className="hint">{t("选 2–4 个因子，同一因子只能出现一次。", "Choose 2–4 unique factors.")}</p>
                <div className="quant-factor-pick">
                  {factors.map((f) => {
                    const picked = selected.find((x) => x.key === f.key);
                    return (
                      <button
                        key={f.key}
                        className={`quant-pick ${picked ? "on" : ""}`}
                        onClick={() => toggleFactor(f)}
                        aria-pressed={!!picked}
                      >
                        <b>{factorName(f, locale)}</b>
                        <small>{factorFormula(f, locale)}</small>
                      </button>
                    );
                  })}
                </div>
                {selectedMeta.length ? (
                  <div className="quant-directions">
                    {selectedMeta.map((f) => {
                      const chosen = selected.find((x) => x.key === f.key)?.direction || f.direction;
                      return (
                        <div className="quant-direction-row" key={f.key}>
                          <b>{factorName(f, locale)}</b>
                          <div className="seg seg-sm">
                            {(["high", "low"] as const).map((dir) => (
                              <button key={dir} className={chosen === dir ? "on" : ""} onClick={() => setDirection(f.key, dir)}>
                                {directionLabel(f, dir, locale)}
                              </button>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                {correlations.length ? (
                  <div className="callout amber quant-corr">
                    {correlations.map((c) => {
                      const a = factors.find((f) => f.key === c.a);
                      const b = factors.find((f) => f.key === c.b);
                      return (
                        <div key={`${c.a}-${c.b}`}>
                          {t(
                            `${a ? factorName(a, locale) : c.a} 与 ${b ? factorName(b, locale) : c.b} 相关性 ${c.r.toFixed(2)}，重复暴露约 ${Math.round(c.r * c.r * 100)}%。`,
                            `${a ? factorName(a, locale) : c.a} and ${b ? factorName(b, locale) : c.b} correlate ${c.r.toFixed(2)}; shared variance about ${Math.round(c.r * c.r * 100)}%.`,
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                <button className="btn btn-primary w100" disabled={selected.length < 2} onClick={() => setStep(2)}>
                  {t("下一步：生成配置", "Next: generate config")} <ArrowRight size={15} />
                </button>
              </section>
            </>
          ) : null}

          {step === 2 ? (
            <section className="card">
              <div className="card-title-row"><h2>{t("回测配置", "Backtest config")}</h2><Tag tone="gray">{t("固定参数", "Fixed params")}</Tag></div>
              <div className="quant-config-factors">
                {selectedMeta.map((f) => {
                  const dir = selected.find((x) => x.key === f.key)?.direction || f.direction;
                  return (
                    <div key={f.key} className="quant-config-row">
                      <b>{factorName(f, locale)}</b>
                      <span>{directionLabel(f, dir, locale)}</span>
                      <small>{t("等权 1/", "Equal weight 1/")}{selected.length}</small>
                    </div>
                  );
                })}
              </div>
              <label className="field">
                <span>{t("股票池", "Universe")}</span>
                <div className="seg">
                  {UNIVERSE_OPTIONS.map((key) => (
                    <button key={key} className={universe === key ? "on" : ""} onClick={() => setUniverse(key)}>
                      {universeLabel(key, t)}
                    </button>
                  ))}
                </div>
              </label>
              <div className="quant-assumptions">
                <div><span>{t("持仓", "Holdings")}</span><b>{t("前 20 只", "Top 20")}</b></div>
                <div><span>{t("调仓", "Rebalance")}</span><b>{t("月度", "Monthly")}</b></div>
                <div><span>{t("成本", "Cost")}</span><b>{t("单边 0.1%", "0.1% one-way")}</b></div>
                <div><span>{t("剔除", "Exclusions")}</span><b>{t("ST / 上市<60 天 / 日均<5000 万", "ST / <60 days / <CNY 50m")}</b></div>
              </div>
              <div className="row gap6">
                <button className="btn btn-ghost btn-sm" onClick={() => setStep(1)}><RotateCcw size={14} /> {t("改因子", "Edit factors")}</button>
                <button className="btn btn-primary btn-sm" onClick={() => void runBacktest()} disabled={running}>
                  <Play size={14} /> {running ? t("回测中…", "Running…") : t("开始回测", "Run backtest")}
                </button>
              </div>
            </section>
          ) : null}

          {step === 3 && backtest ? (
            <section className="card quant-result">
              <div className="card-title-row">
                <h2>{t("回测结果", "Backtest result")}</h2>
                <Tag tone={backtest.shortened ? "amber" : "green"}>{backtest.shortened ? t("已缩短区间", "Shortened range") : t("近 1 年", "Last year")}</Tag>
              </div>
              <p className="hint">{backtest.start_date} ~ {backtest.end_date} · {universeLabel(backtest.universe, t)}</p>
              <div className="kpi-grid quant-kpi-grid">
                {METRIC_ROWS.map(([key, zh, en, style]) => (
                  <div className="kpi" key={key}>
                    <span>{t(zh, en)}</span>
                    <b className={style === "pct" ? trendClass(backtest.metrics[key]) : ""}>{metric(backtest.metrics[key], style)}</b>
                  </div>
                ))}
              </div>
              <QuantChart points={backtest.curve} />
              <div className="quant-bench-rows">
                <div><span>{t("基准收益", "Benchmark")}</span><b className={trendClass(backtest.metrics.benchmark_return)}>{metric(backtest.metrics.benchmark_return, "pct")}</b></div>
                <div><span>{t("超额", "Excess")}</span><b className={trendClass(backtest.metrics.excess)}>{metric(backtest.metrics.excess, "pct")}</b></div>
              </div>
              <div className="quant-actions">
                <button className="btn btn-ghost btn-sm" onClick={() => void saveDraft()}><Save size={14} /> {t("保存草稿", "Save draft")}</button>
                <button className="btn btn-primary btn-sm" disabled={!backtest.id} onClick={() => void startPaper("backtest", backtest.id)}><FlaskConical size={14} /> {t("开模拟盘", "Paper trade")}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setStep(1)}><RotateCcw size={14} /> {t("改因子重跑", "Edit & rerun")}</button>
              </div>
              <p className="quant-foot">{t("历史回测，不代表未来；不构成投资建议。", "Historical backtest, not a forecast; not investment advice.")}</p>
            </section>
          ) : null}
        </>
      ) : null}

      {tab === "mine" ? (
        <>
          {loading ? <LoadingCards rows={3} /> : null}
          {!loading && !strategies.length ? (
            <div className="state-box">
              <div className="empty-dot" />
              <b>{t("还没有跟踪中的策略", "No tracked strategies yet")}</b>
              <p>{t("在快速实验里跑完回测，开一个模拟盘后就会出现在这里。", "Run a backtest in the quick lab and start a paper account to see it here.")}</p>
            </div>
          ) : null}
          {strategies.map((s) => (
            <button className="quant-strategy-card" key={s.id} onClick={() => nav(`/quant/strategies/${s.id}`)}>
              <div className="card-title-row">
                <h2>{s.name}</h2>
                <Tag tone={s.status === "tracking" ? "green" : "amber"}>{locale === "en" ? s.status_label_en : s.status_label}</Tag>
              </div>
              <div className="quant-strategy-kpis">
                <div><span>{t("今日", "Today")}</span><b className={trendClass(s.today)}>{fmtSignedPct(s.today)}</b></div>
                <div><span>{t("当前回撤", "Drawdown")}</span><b>{metric(s.drawdown, "pct")}</b></div>
                <div><span>{t("下次调仓", "Next rebalance")}</span><b>{s.next_rebalance || "—"}</b></div>
              </div>
            </button>
          ))}
        </>
      ) : null}

      {tab === "drafts" ? (
        <>
          {loading ? <LoadingCards rows={3} /> : null}
          {!loading && !drafts.length ? (
            <p className="hint quant-empty-line">{t("在上面的快速实验里跑完一次，就能存成草稿。", "Run the quick lab once and you can save it as a draft.")}</p>
          ) : null}
          {drafts.map((d) => (
            <section className="card" key={d.id}>
              <div className="card-title-row">
                <h2>{d.name}</h2>
                <Tag tone="gray">{t("草稿", "Draft")}</Tag>
              </div>
              <p className="hint">
                {t(`${(d.factors || []).length} 个因子 · ${universeLabel(d.universe, t)} · 保存于 ${(d.created_at || "").slice(0, 10)}`, `${(d.factors || []).length} factors · ${universeLabel(d.universe, t)} · saved ${(d.created_at || "").slice(0, 10)}`)}
              </p>
              <div className="row gap6">
                <button className="btn btn-primary btn-sm" onClick={() => reuseDraft(d)}><Play size={14} /> {t("用这套配置去回测", "Backtest this config")}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => void startPaper("draft", d.id)}><FlaskConical size={14} /> {t("直接开模拟盘", "Paper trade")}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => void deleteDraft(d.id)}><Trash2 size={14} /> {t("删除", "Delete")}</button>
              </div>
            </section>
          ))}
        </>
      ) : null}

      {tab === "plaza" ? (
        <>
          <div className="seg">
            {([["annual", "收益榜", "Return"], ["mdd", "回撤榜", "Drawdown"], ["followers", "关注榜", "Follows"]] as Array<[string, string, string]>).map(([key, zh, en]) => (
              <button key={key} className={plazaSort === key ? "on" : ""} onClick={() => setPlazaSort(key)}>{t(zh, en)}</button>
            ))}
          </div>
          <p className="hint">{t("年化与回撤来自作者回测快照，未做跨策略统一，不能横向比大小。", "Figures come from author snapshots, are not normalized, and cannot be compared across strategies.")}</p>
          {loading ? <LoadingCards rows={3} /> : null}
          {plaza.map((item) => (
            <section className="card quant-plaza-card" key={item.id}>
              <div className="card-title-row">
                <h2>{item.title}</h2>
                {item.is_demo ? <Tag tone="gray">{t("示例", "Demo")}</Tag> : null}
              </div>
              <p className="hint">{item.author} · {universeLabel(item.universe, t)} · {t("关注", "Followers")} {item.followers}</p>
              <div className="quant-plaza-metrics">
                <div><span>{t("年化", "Annual")}</span><b className={trendClass(item.annual_return)}>{metric(item.annual_return, "pct")}</b></div>
                <div><span>{t("最大回撤", "Max DD")}</span><b>{metric(item.max_drawdown, "pct")}</b></div>
                <div><span>{t("夏普", "Sharpe")}</span><b>{metric(item.sharpe, "num")}</b></div>
              </div>
              <div className="row between">
                <Sparkline values={item.curve || []} width={190} height={36} />
                <button className={`link-btn ${item.followed ? "on" : ""}`} onClick={() => void followPlaza(item)}>
                  <Bookmark size={13} /> {item.followed ? t("已关注", "Following") : t("关注", "Follow")}
                </button>
              </div>
              <button className="btn btn-ghost btn-sm w100" onClick={() => void openPlaza(item)}>{t("查看详情", "View details")}</button>
            </section>
          ))}
          <p className="quant-foot">{t("示例策略 · 历史数据不代表未来 · 不构成推荐。", "Demo strategies · past performance is not indicative · not a recommendation.")}</p>
        </>
      ) : null}

      <Sheet
        open={!!plazaDetail}
        onClose={() => setPlazaDetail(null)}
        title={plazaDetail?.title || t("策略详情", "Strategy details")}
        sub={t("作者回测快照 · 非投资建议", "Author snapshot · not investment advice")}
        footer={
          plazaDetail ? (
            <div className="row gap6">
              <button className="btn btn-ghost btn-sm" onClick={() => void followPlaza(plazaDetail as unknown as PlazaItem)}>
                <Bookmark size={14} /> {plazaDetail.followed ? t("已关注", "Following") : t("关注", "Follow")}
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => void copyPlaza(plazaDetail.id)}>
                <Copy size={14} /> {t("复制到我的草稿", "Copy to drafts")}
              </button>
            </div>
          ) : undefined
        }
      >
        {plazaDetail ? (
          <div>
            <div className="kpi-grid quant-kpi-grid">
              <div className="kpi"><span>{t("区间", "Period")}</span><b>{plazaDetail.range}</b></div>
              <div className="kpi"><span>{t("年化", "Annual")}</span><b>{metric(plazaDetail.metrics.annual_return, "pct")}</b></div>
              <div className="kpi"><span>{t("基准", "Benchmark")}</span><b>{metric(plazaDetail.metrics.benchmark_return, "pct")}</b></div>
              <div className="kpi"><span>{t("超额", "Excess")}</span><b>{metric(plazaDetail.metrics.excess, "pct")}</b></div>
              <div className="kpi"><span>{t("最大回撤", "Max DD")}</span><b>{metric(plazaDetail.metrics.max_drawdown, "pct")}</b></div>
              <div className="kpi"><span>{t("夏普", "Sharpe")}</span><b>{metric(plazaDetail.metrics.sharpe, "num")}</b></div>
            </div>
            <QuantChart points={plazaDetail.curve || []} />
            <p className="hint">{plazaDetail.note}</p>
            <p className="hint">{t("因子：", "Factors: ")}{(plazaDetail.factors || []).map((f) => factorName(f, locale)).join(" · ")}</p>
          </div>
        ) : null}
      </Sheet>

      <p className="quant-foot">{t("历史数据，不代表未来；策略状态只描述系统运行，不构成操作指令。", "Historical data does not predict the future; strategy status describes system operation only, not instructions.")}</p>
    </div>
  );
}
