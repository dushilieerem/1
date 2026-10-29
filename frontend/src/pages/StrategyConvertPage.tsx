import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCopy,
  Download,
  FileWarning,
  Loader2,
  Save,
  Sparkles,
  XCircle,
} from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import {
  ygTranscribeStrategy,
  type StrategyTranscriptionResult,
  type TranscriptionEngineMode,
  type TranscriptionIssue,
  type TranscriptionOption,
} from "@/lib/aiStrategyTranscriptionApi";
import {
  createStrategyProjectFromCode,
  openStrategyInNewTab,
} from "@/lib/strategyStore";
import { newUuidV4 } from "@/lib/uuid";

const SAMPLE_EVENT = `# 聚宽：中证500 RSI 反转，每天开盘调仓
def initialize(context):
    g.stocks = get_index_stocks('000905.XSHG')
    set_benchmark('000905.XSHG')
    run_daily(trade, time='open')

def trade(context):
    hist = attribute_history(g.stocks, 20, '1d', ['close'])
    for s in g.stocks:
        closes = hist[s]['close']
        if len(closes) < 20:
            continue
        rsi = calc_rsi(closes)
        pos = context.portfolio.positions[s].total_amount
        if rsi < 30 and pos == 0:
            order_target_percent(s, 0.1)
        elif rsi > 70 and pos > 0:
            order_target_value(s, 0)

def calc_rsi(closes):
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains[-14:]) / 14
    avg_loss = sum(losses[-14:]) / 14
    if avg_loss == 0:
        return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)`;

const SAMPLE_VECTORIZED = `# 聚宽：沪深300 20日动量 Top10，每周一调仓
def initialize(context):
    g.stocks = get_index_stocks('000300.XSHG')
    set_benchmark('000300.XSHG')
    run_weekly(rebalance, 1, '09:30')

def rebalance(context):
    prices = get_price(g.stocks, count=21, frequency='daily', fields=['close'])
    close = prices.pivot(index='time', columns='code', values='close')
    momentum = close.iloc[-1] / close.iloc[0] - 1
    picks = momentum.nlargest(10).index.tolist()
    for s in list(context.portfolio.positions):
        if s not in picks:
            order_target_value(s, 0)
    for s in picks:
        order_target_value(s, context.portfolio.total_value / 10)`;

const SAMPLE_BLOCKED = `# 聚宽：分钟突破 + ROE 选股
def initialize(context):
    set_benchmark('000300.XSHG')
    run_daily(check, time='every_bar')

def check(context):
    q = query(valuation.pe_ratio, indicator.roe).filter(
        valuation.pe_ratio < 20, indicator.roe > 15)
    df = get_fundamentals(q, date=context.current_dt)
    for s in get_index_stocks('000300.XSHG'):
        bars = get_price(s, count=30, frequency='1m', fields=['close'])
        if bars.close.iloc[-1] > bars.close.mean():
            order_target_percent(s, 0.05)`;

const SAMPLES = [
  { id: "event", label: "RSI 轮动", tag: "事件", code: SAMPLE_EVENT },
  { id: "vectorized", label: "动量 Top10", tag: "向量化", code: SAMPLE_VECTORIZED },
  { id: "blocked", label: "分钟 + ROE", tag: "阻断", code: SAMPLE_BLOCKED },
] as const;

const TONE = {
  emerald: {
    box: "border-emerald-200 bg-emerald-50/70",
    icon: "bg-emerald-100 text-emerald-700",
    tag: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  amber: {
    box: "border-amber-200 bg-amber-50/70",
    icon: "bg-amber-100 text-amber-700",
    tag: "border-amber-200 bg-amber-50 text-amber-700",
  },
  rose: {
    box: "border-rose-200 bg-rose-50/70",
    icon: "bg-rose-100 text-rose-700",
    tag: "border-rose-200 bg-rose-50 text-rose-700",
  },
} as const;

const SEVERITY = {
  blocker: "border-rose-200 bg-rose-50 text-rose-700",
  degraded: "border-amber-200 bg-amber-50 text-amber-700",
  info: "border-sky-200 bg-sky-50 text-sky-700",
} as const;

const IMPACT: Record<string, string> = {
  high: "高影响",
  medium: "中影响",
  low: "低影响",
};

function verdictTone(result: StrategyTranscriptionResult) {
  if (result.verdict === "equivalent") return "emerald" as const;
  if (result.verdict === "degraded") return "amber" as const;
  return "rose" as const;
}

function verdictTitle(result: StrategyTranscriptionResult) {
  if (result.status === "needs_input") return "无法等价转写，需要你确认降级";
  if (result.status === "report_only") {
    return result.verdict === "blocked" ? "仅报告：存在无法等价的阻断项" : "仅报告：已生成差异说明";
  }
  if (result.verdict === "equivalent") return "等价转写";
  if (result.verdict === "degraded") {
    const count = result.issues.filter((i) => i.severity === "degraded").length;
    return `可以运行，但有 ${count} 处语义差异`;
  }
  return "无法等价转写";
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function toMarkdown(result: StrategyTranscriptionResult) {
  const lines: string[] = [];
  lines.push("# 聚宽策略转写报告");
  lines.push("");
  lines.push(`**结论：** ${verdictTitle(result)}`);
  lines.push("");
  lines.push(result.summary);
  lines.push("");
  lines.push(`- 目标引擎：${result.target_engine}`);
  lines.push(`- 映射项：${result.mappings.length}`);
  lines.push(`- 语义差异：${result.issues.filter((i) => i.severity === "degraded").length}`);
  lines.push(`- 阻断项：${result.issues.filter((i) => i.severity === "blocker").length}`);
  lines.push("");
  lines.push("## 差异清单");
  if (!result.issues.length) {
    lines.push("未发现需要披露的差异。");
  } else {
    result.issues.forEach((issue, index) => {
      lines.push("");
      lines.push(`### ${index + 1}. ${issue.title}（${issue.code}，第 ${issue.line} 行）`);
      lines.push("");
      lines.push(`- 位置：聚宽第 ${issue.line || "?"} 行`);
      lines.push(`- 问题码：${issue.code}`);
      lines.push(`- 为什么不行：${issue.why}`);
      lines.push(`- 影响：${issue.effect}`);
      lines.push("- 降级选项：");
      issue.options.forEach((option) =>
        lines.push(`  - ${option.label}：${option.note}${option.recommended ? "（推荐）" : ""}`),
      );
      lines.push(`- 依据：${issue.evidence}`);
    });
  }
  if (result.strategy?.strategy_code) {
    lines.push("");
    lines.push("## 转写代码");
    lines.push("");
    lines.push("```python");
    lines.push(result.strategy.strategy_code);
    lines.push("```");
  }
  lines.push("");
  lines.push("## 校验");
  result.checks.forEach((check) => {
    const label =
      check.status === "pass" ? "通过" : check.status === "warn" ? "警告" : check.status === "fail" ? "失败" : "跳过";
    lines.push(`- ${check.label}：${label}${check.detail ? `（${check.detail}）` : ""}`);
  });
  lines.push("");
  lines.push("> 本报告由 AI 策略转写生成。代码为草稿，不能等价的地方已标注；请逐条确认后使用。仅供研究，不构成投资建议。");
  return lines.join("\n");
}

export function StrategyConvertPage() {
  const [sample, setSample] = useState<string>("event");
  const [code, setCode] = useState(SAMPLE_EVENT);
  const [engineMode, setEngineMode] = useState<TranscriptionEngineMode>("auto");
  const [universe, setUniverse] = useState("CSI500");
  const [benchmark, setBenchmark] = useState("CSI300");
  const [start, setStart] = useState("2020-01-01");
  const [end, setEnd] = useState("2026-08-31");
  const [capital, setCapital] = useState("1000000");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<StrategyTranscriptionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedOptions, setSelectedOptions] = useState<Record<number, string>>({});
  const [ack, setAck] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedHint, setSavedHint] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (result?.strategy) {
      setSaveName(result.strategy.strategy_name);
    }
  }, [result]);

  const tone = result ? verdictTone(result) : "rose";
  const toneClass = TONE[tone];
  const blockerRows = useMemo(
    () =>
      (result?.issues ?? [])
        .map((issue, index) => ({ issue, index }))
        .filter(({ issue }) => issue.severity === "blocker"),
    [result],
  );
  const canApply = blockerRows.length > 0 && blockerRows.every(({ index }) => Boolean(selectedOptions[index]));
  const canSave =
    Boolean(result?.strategy) &&
    result?.status === "ready" &&
    (!result.requires_ack || ack) &&
    Boolean(saveName.trim());

  const loadSample = (item: (typeof SAMPLES)[number]) => {
    setSample(item.id);
    setCode(item.code);
    setResult(null);
    setError(null);
    setSelectedOptions({});
    setAck(false);
    setSavedHint(null);
  };

  const run = async (reportOnly = false) => {
    if (busy) return;
    if (!code.trim()) {
      setError("先粘贴一段聚宽策略代码，或从示例开始。");
      return;
    }
    setBusy(true);
    setError(null);
    setSavedHint(null);
    setAck(false);
    const accepted = Object.values(selectedOptions);
    try {
      const data = await ygTranscribeStrategy({
        code,
        context: {
          target: {
            engine_mode: engineMode,
            universe,
            benchmark,
            start: start || null,
            end: end || null,
            initial_capital: Number(capital) || null,
          },
          accepted_degradations: accepted,
          report_only: reportOnly || accepted.includes("report_only"),
          source_name: "joinquant_strategy.py",
        },
        idempotency_key: newUuidV4(),
      });
      setResult(data);
      if (data.status !== "needs_input") setSelectedOptions({});
      setAck(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const copyCode = async () => {
    const text = result?.strategy?.strategy_code;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("复制失败，请手动选择代码。");
    }
  };

  const save = async () => {
    if (!result?.strategy || !canSave) return;
    setSaving(true);
    setError(null);
    try {
      const project = await createStrategyProjectFromCode({
        name: saveName.trim(),
        description: result.strategy.description || "由聚宽策略转写生成",
        strategyCode: result.strategy.strategy_code,
      });
      setSavedHint(`已保存为策略草稿：${project.name}`);
      openStrategyInNewTab(project.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const issueOptions = (issue: TranscriptionIssue, index: number) => {
    if (result?.status !== "needs_input") {
      const recommended = issue.options.filter((option) => option.recommended);
      const rest = issue.options.filter((option) => !option.recommended);
      return (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {recommended.map((option) => (
            <span key={option.id} className="rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700">
              推荐：{option.label}
            </span>
          ))}
          {rest.map((option) => (
            <span key={option.id} className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-500">
              {option.label}
            </span>
          ))}
        </div>
      );
    }
    return (
      <div className="mt-2 space-y-1.5">
        {issue.options.map((option: TranscriptionOption) => (
          <label
            key={option.id}
            className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
              selectedOptions[index] === option.id
                ? "border-indigo-300 bg-indigo-50/70"
                : "border-slate-200 bg-white hover:bg-slate-50"
            }`}
          >
            <input
              type="radio"
              name={`issue-${index}`}
              checked={selectedOptions[index] === option.id}
              onChange={() => setSelectedOptions((prev) => ({ ...prev, [index]: option.id }))}
              className="mt-1 accent-indigo-600"
            />
            <span className="min-w-0">
              <span className="font-medium text-slate-800">{option.label}</span>
              {option.recommended ? (
                <span className="ml-1.5 rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700">推荐</span>
              ) : null}
              <span className="mt-0.5 block text-xs leading-5 text-slate-500">{option.note}</span>
            </span>
          </label>
        ))}
      </div>
    );
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#f4f6fb]">
      <div className="mx-auto max-w-[1480px] px-4 py-6 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Link to="/strategy/plaza" className="hover:text-indigo-600">策略</Link>
              <span className="text-slate-300">/</span>
              <span>代码转换</span>
            </div>
            <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-bold tracking-tight text-slate-900">
              代码转换
              <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-bold tracking-wide text-indigo-700">
                聚宽 → SVQuant
              </span>
            </h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              粘贴聚宽策略，AI 先做能力核对再转写。不能等价的地方会逐条告诉你：哪里不行、为什么、怎么降级。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500">
              日频 A 股 · 向量化 / 事件
            </span>
            <Link
              to="/strategy/library"
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              策略库
            </Link>
          </div>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[400px_minmax(0,1fr)]">
          <aside className="h-fit overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:sticky lg:top-20">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-800">聚宽策略</h2>
              <span className="text-[11px] text-slate-400">选择示例或粘贴代码</span>
            </div>
            <div className="p-4">
              <div className="flex flex-wrap gap-1.5">
                {SAMPLES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => loadSample(item)}
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                      sample === item.id
                        ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 bg-slate-50 text-slate-500 hover:border-indigo-200 hover:text-indigo-600"
                    }`}
                  >
                    {item.label}
                    <span className="ml-1 text-[10px] opacity-70">{item.tag}</span>
                  </button>
                ))}
              </div>

              <div className="mt-3">
                <FactorCodeEditor
                  value={code}
                  onChange={(value) => {
                    setCode(value);
                    setResult(null);
                    setSelectedOptions({});
                    setAck(false);
                    setSavedHint(null);
                    setError(null);
                  }}
                  variant="dark"
                  height="320px"
                  className="h-[320px]"
                />
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                <span>{code ? code.split("\n").length : 0} 行</span>
                <span>≤ 200,000 字符 · Ctrl/Cmd + Enter 转写</span>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
                {(["auto", "vectorized", "event"] as TranscriptionEngineMode[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setEngineMode(mode)}
                    className={`rounded-md px-2 py-1.5 text-xs font-medium transition ${
                      engineMode === mode ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {mode === "auto" ? "自动" : mode === "vectorized" ? "向量化" : "事件"}
                  </button>
                ))}
              </div>

              <details className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3">
                <summary className="cursor-pointer py-2 text-xs font-medium text-slate-600">回测配置</summary>
                <div className="grid grid-cols-2 gap-2 pb-3">
                  <label className="text-[11px] text-slate-500">
                    股票池
                    <select value={universe} onChange={(e) => setUniverse(e.target.value)} className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-indigo-400">
                      <option value="CSI300">CSI300</option>
                      <option value="CSI500">CSI500</option>
                    </select>
                  </label>
                  <label className="text-[11px] text-slate-500">
                    基准
                    <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)} className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-indigo-400">
                      <option value="CSI300">CSI300</option>
                      <option value="CSI500">CSI500</option>
                    </select>
                  </label>
                  <label className="text-[11px] text-slate-500">
                    开始
                    <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-indigo-400" />
                  </label>
                  <label className="text-[11px] text-slate-500">
                    结束
                    <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-indigo-400" />
                  </label>
                  <label className="col-span-2 text-[11px] text-slate-500">
                    初始资金
                    <input value={capital} onChange={(e) => setCapital(e.target.value)} inputMode="numeric" className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-indigo-400" />
                  </label>
                </div>
              </details>

              <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-500">
                代码只用于本次转写，默认不用于训练；账号、密钥等信息不会进入模型。保存草稿需你确认。
              </p>

              {error ? (
                <div role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {error}
                </div>
              ) : null}

              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(false)}
                  className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {busy ? "转写中…" : "开始转写"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(true)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  仅报告
                </button>
              </div>
            </div>
          </aside>

          <section className="min-w-0 space-y-4" aria-live="polite">
            {busy ? (
              <div className="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                <p className="mt-3 text-sm font-semibold text-slate-800">正在核对能力并转写…</p>
                <p className="mt-1 text-xs text-slate-500">先检查数据/时序/标的差异，再调用模型生成；可能需要 30–60 秒。</p>
              </div>
            ) : !result ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h2 className="mt-4 text-center text-lg font-bold text-slate-900">先粘贴一段聚宽策略</h2>
                <p className="mx-auto mt-1 max-w-xl text-center text-sm text-slate-500">
                  AI 会先做能力核对，再转写。不能等价的地方会逐条标出来，不会静默改写。
                </p>
                <div className="mx-auto mt-6 grid max-w-2xl gap-3 sm:grid-cols-3">
                  {[
                    ["先核对，再转写", "先识别 API、字段和回调，避免模型自由发挥。"],
                    ["不能等价就说", "每条差异都有位置、原因、影响和降级选项。"],
                    ["你确认才保存", "不自动保存、不自动回测、不碰实盘。"],
                  ].map(([title, desc]) => (
                    <div key={title} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                      <p className="text-xs font-semibold text-slate-800">{title}</p>
                      <p className="mt-1 text-[11px] leading-5 text-slate-500">{desc}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-6 text-center text-[11px] text-slate-400">
                  能力基线：日频 A 股 · 向量化 / 事件 · 不支持分钟、期货、两融、实盘
                </p>
              </div>
            ) : (
              <>
                <div className={`rounded-2xl border p-5 shadow-sm ${toneClass.box}`}>
                  <div className="flex items-start gap-3">
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${toneClass.icon}`}>
                      {result.verdict === "equivalent" ? <CheckCircle2 className="h-5 w-5" /> : result.verdict === "degraded" ? <AlertTriangle className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-bold text-slate-900">{verdictTitle(result)}</h2>
                        <span className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold ${toneClass.tag}`}>
                          {result.target_engine === "event" ? "事件策略" : "向量化策略"}
                        </span>
                        {result.requires_ack ? (
                          <span className="rounded-md border border-amber-200 bg-white/70 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                            需确认
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-sm leading-6 text-slate-600">{result.summary}</p>
                      <p className="mt-2 text-[11px] text-slate-500">
                        依据：能力目录 <span className="font-mono">{result.meta.capability_catalog_version}</span> · 数据版本{" "}
                        <span className="font-mono">{result.meta.data_version}</span> · 模型{" "}
                        <span className="font-mono">{result.meta.model_alias}</span>
                      </p>
                    </div>
                  </div>
                  <dl className="mt-4 grid grid-cols-3 gap-2">
                    {[
                      ["可直接映射", result.mappings.filter((m) => m.status === "equivalent" || m.status === "config").length],
                      ["语义差异", result.issues.filter((i) => i.severity === "degraded").length],
                      ["阻断项", result.issues.filter((i) => i.severity === "blocker").length],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-lg border border-white/70 bg-white/70 px-3 py-2">
                        <dt className="text-[10px] text-slate-500">{label}</dt>
                        <dd className="mt-0.5 font-mono text-lg font-bold text-slate-900">{value}<span className="ml-0.5 text-[10px] font-normal text-slate-400">项</span></dd>
                      </div>
                    ))}
                  </dl>
                </div>

                {result.errors.length > 0 ? (
                  <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    <div className="flex items-center gap-2 font-semibold">
                      <FileWarning className="h-4 w-4" />
                      生成未通过校验
                    </div>
                    <ul className="mt-1.5 list-disc space-y-1 pl-5 text-xs leading-5">
                      {result.errors.slice(0, 6).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}

                <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                    <h3 className="text-sm font-semibold text-slate-800">差异清单</h3>
                    <span className="text-[11px] text-slate-400">
                      {result.issues.length ? `${result.issues.length} 条 · 按影响排序` : "未发现需要披露的差异"}
                    </span>
                  </div>
                  <div className="space-y-3 p-4">
                    {!result.issues.length ? (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-5 text-center text-sm text-emerald-800">
                        <CheckCircle2 className="mx-auto mb-1.5 h-5 w-5" />
                        所有调用都有直接对应，未发现数据/时序差异。
                      </div>
                    ) : (
                      result.issues.map((issue, index) => (
                        <article key={`${issue.code}-${index}`} className={`rounded-xl border border-l-4 p-3.5 ${SEVERITY[issue.severity]}`}>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] font-bold">{issue.severity === "blocker" ? "阻断" : issue.severity === "degraded" ? "降级" : "提示"}</span>
                            <span className="font-mono text-[10px] opacity-75">{issue.code}</span>
                            <span className="rounded bg-white/70 px-1.5 py-0.5 text-[10px]">{IMPACT[issue.impact]}</span>
                            <span className="ml-auto text-[11px] text-slate-500">聚宽第 {issue.line || "?"} 行</span>
                          </div>
                          <h4 className="mt-1.5 text-sm font-semibold text-slate-900">{issue.title}</h4>
                          <div className="mt-2 grid gap-3 sm:grid-cols-2">
                            <div>
                              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">为什么不行</p>
                              <p className="mt-0.5 text-xs leading-5 text-slate-600">{issue.why}</p>
                            </div>
                            <div>
                              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">会有什么影响</p>
                              <p className="mt-0.5 text-xs leading-5 text-slate-600">{issue.effect}</p>
                            </div>
                          </div>
                          <div className="mt-2 border-t border-slate-200/60 pt-2">
                            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">怎么降级</p>
                            {issueOptions(issue, index)}
                          </div>
                          <p className="mt-2 text-[10px] leading-4 text-slate-500">依据：{issue.evidence}</p>
                        </article>
                      ))
                    )}
                    {result.status === "needs_input" ? (
                      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3">
                        <p className="text-xs text-indigo-800">先为每个阻断项选择降级方案，再重新转写；不选则不会生成代码。</p>
                        <button
                          type="button"
                          disabled={!canApply || busy}
                          onClick={() => void run(false)}
                          className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
                        >
                          接受所选降级并重新转写
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>

                {result.assumptions.length ? (
                  <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-xs leading-5 text-indigo-800">
                    <span className="font-semibold">已接受的降级：</span>
                    {result.assumptions.join("；")}
                  </div>
                ) : null}

                {result.strategy?.strategy_code ? (
                  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-slate-800">转写代码</h3>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">草稿 · 未保存</span>
                      </div>
                      <button type="button" onClick={() => void copyCode()} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50">
                        <ClipboardCopy className="h-3.5 w-3.5" />
                        {copied ? "已复制" : "复制"}
                      </button>
                    </div>
                    <div className="p-3">
                      <FactorCodeEditor
                        value={result.strategy.strategy_code}
                        onChange={() => undefined}
                        readOnly
                        showPlaceholder={false}
                        variant="dark"
                        height="420px"
                        className="h-[420px]"
                      />
                    </div>
                    {result.strategy.warnings.length ? (
                      <div className="border-t border-slate-100 px-4 py-2.5 text-[11px] leading-5 text-amber-700">
                        {result.strategy.warnings.join("；")}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {result.checks.length ? (
                  <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-slate-800">校验</h3>
                      <span className="text-[11px] text-slate-400">
                        {result.checks.filter((c) => c.status === "pass").length}/{result.checks.length} 项通过
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {result.checks.map((check) => (
                        <div key={check.id} className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                          <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${check.status === "pass" ? "bg-emerald-100 text-emerald-700" : check.status === "warn" ? "bg-amber-100 text-amber-700" : check.status === "fail" ? "bg-rose-100 text-rose-700" : "bg-slate-200 text-slate-500"}`}>
                            {check.status === "pass" ? "✓" : check.status === "warn" ? "!" : check.status === "fail" ? "×" : "–"}
                          </span>
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-slate-700">{check.label}</p>
                            <p className="text-[10px] leading-4 text-slate-500">{check.detail || (check.status === "skipped" ? "未执行" : "通过")}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-center gap-3">
                    {result.strategy ? (
                      <>
                        <label className="min-w-[220px] flex-1 text-[11px] text-slate-500">
                          策略名称
                          <input
                            value={saveName}
                            onChange={(e) => setSaveName(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-400"
                          />
                        </label>
                        <button
                          type="button"
                          disabled={!canSave || saving}
                          onClick={() => void save()}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
                        >
                          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                          {saving ? "保存中…" : "保存为策略草稿"}
                        </button>
                      </>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => downloadText("聚宽策略转写报告.md", toMarkdown(result))}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-600 hover:bg-slate-50"
                    >
                      <Download className="h-4 w-4" />
                      导出报告
                    </button>
                  </div>
                  {result.strategy && result.requires_ack ? (
                    <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-slate-600">
                      <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 accent-indigo-600" />
                      我已知晓：这不是等价迁移，差异会影响回测结果；我接受已披露的降级。
                    </label>
                  ) : null}
                  {savedHint ? <p className="mt-2 text-xs text-emerald-700">{savedHint}</p> : null}
                  <p className="mt-3 text-[10px] leading-4 text-slate-400">
                    仅供研究，不构成投资建议。代码为 AI 草稿，保存前请核对差异；回测请在策略研究中确认后运行。
                  </p>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
