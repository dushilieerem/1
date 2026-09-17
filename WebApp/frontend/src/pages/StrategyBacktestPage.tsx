import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  Loader2,
  Play,
  Save,
} from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import { StrategySignalFactorsPanel } from "@/components/StrategySignalFactorsPanel";
import { useConfirm } from "@/components/ConfirmDialog";
import { configFromRunRequest } from "@/lib/strategyLibraryApi";
import { ygBacktestStrategy } from "@/lib/ygApi";
import {
  applyParamsToCode,
  DEFAULT_EVENT_STRATEGY_CODE,
  DEFAULT_STRATEGY_CODE,
  parseParamsFromCode,
} from "@/lib/strategyCodeSync";
import {
  FACTORS_BEGIN,
  FACTORS_END,
  applySignalFactorsToCode,
  hydrateSignalSelection,
  normalizeSignalPowers,
  normalizeSignalWeights,
  resolveStrategyFactorBodies,
  usesFactorPortfolioTemplate,
  type StrategyWeightMode,
} from "@/lib/strategyFactorSync";
import {
  STRATEGY_DRAFT_ID,
  clearStrategyCloneDraft,
  createStrategyProject,
  getStrategyProject,
  getStrategyRun,
  normalizeStrategyConfig,
  peekStrategyCloneDraft,
  resolveStrategyRange,
  saveStrategyProject,
  saveStrategyRun,
  stashStrategyCloneDraft,
  STRATEGY_BENCHMARK_OPTIONS,
  STRATEGY_PERIOD_OPTIONS,
  STRATEGY_UNIVERSE_OPTIONS,
  clampDateRange,
  defaultCustomRangeDates,
  type StrategyEngineMode,
  type StrategyProject,
  type StrategyProjectConfig,
} from "@/lib/strategyStore";

function fieldClass(extra = "") {
  return `h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200 ${extra}`;
}

function syncParams(cfg: StrategyProjectConfig) {
  const range = resolveStrategyRange(cfg);
  return {
    universe: cfg.universe,
    benchmark: cfg.benchmark,
    commission_rate: cfg.commission_rate,
    stamp_tax: cfg.stamp_tax,
    slippage_rate: cfg.slippage_rate,
    initial_capital: cfg.initial_capital,
    top_n: cfg.top_n,
    rebalance_days: cfg.rebalance_days,
    range_mode: cfg.rangeMode === "custom" ? ("custom" as const) : ("period" as const),
    backtest_period: cfg.backtestPeriod || "10y",
    start_date: range.start || cfg.startDate || "",
    end_date: range.end || cfg.endDate || "",
  };
}

function syncCodeFromLeft(cfg: StrategyProjectConfig): string {
  return applyParamsToCode(cfg.strategy_code, syncParams(cfg));
}

export function StrategyBacktestPage() {
  const { projectId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const isDraft = projectId === STRATEGY_DRAFT_ID;
  const snapshotRunId = searchParams.get("runId")?.trim() || "";
  const [project, setProject] = useState<StrategyProject | null>(null);
  const [cfg, setCfg] = useState<StrategyProjectConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [savedHint, setSavedHint] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const [factorSyncing, setFactorSyncing] = useState(false);
  const [mobilePane, setMobilePane] = useState<"config" | "code">("config");
  const syncLock = useRef<"left" | "right" | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const factorSyncGen = useRef(0);

  const pushLog = (msg: string) => {
    const t = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setLogs((prev) => [...prev.slice(-200), `[${t}] ${msg}`]);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadErr(null);

    if (isDraft) {
      const draft = peekStrategyCloneDraft();
      if (!draft) {
        setLoadErr("克隆草稿已失效，请从社区重新「克隆到策略研究」");
        setLoading(false);
        return;
      }
      const now = new Date().toISOString();
      const config = normalizeStrategyConfig({
        strategy_code: draft.strategy_code,
      });
      const synced = {
        ...config,
        strategy_code: syncCodeFromLeft(config),
      };
      if (!cancelled) {
        setProject({
          id: STRATEGY_DRAFT_ID,
          name: draft.name,
          description: draft.description || draft.name,
          createdAt: now,
          updatedAt: now,
          runCount: 0,
          config: synced,
        });
        setCfg(synced);
        setLoading(false);
      }
      return () => {
        cancelled = true;
        abortRef.current?.abort();
      };
    }

    void (async () => {
      try {
        const p = await getStrategyProject(projectId);
        if (cancelled) return;
        const projectConfig = normalizeStrategyConfig(p.config);
        let config = projectConfig;
        if (snapshotRunId) {
          const run = await getStrategyRun(snapshotRunId);
          if (cancelled) return;
          if (run.projectId !== p.id) {
            throw new Error("该回测不属于当前检测项目");
          }
          // 历史快照优先；代码/@factor 与落库 _svquant_ui 都空时回退到项目已保存因子
          config = hydrateSignalSelection(
            normalizeStrategyConfig(configFromRunRequest(run.request)),
            projectConfig,
          );
        } else {
          // 旧项目可能只在代码里有 @factor，config 未写 signal_factor_ids
          config = hydrateSignalSelection(projectConfig);
        }
        const synced = {
          ...config,
          strategy_code: syncCodeFromLeft(config),
        };
        setProject({ ...p, config: synced });
        setCfg(synced);
      } catch (e) {
        if (!cancelled) setLoadErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [projectId, isDraft, snapshotRunId]);

  useEffect(() => {
    if (!running) return;
    setElapsed(0);
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [running]);

  const patchCfg = (patch: Partial<StrategyProjectConfig>, from: "left" | "right") => {
    setCfg((prev) => {
      if (!prev) return prev;
      let next = { ...prev, ...patch };
      if (from === "left") {
        syncLock.current = "left";
        next = {
          ...next,
          strategy_code: syncCodeFromLeft(next),
        };
        queueMicrotask(() => {
          syncLock.current = null;
        });
      }
      return next;
    });
  };

  /** 选因子 / 改权重 / 改合成模式：拉全库源码 → 重写 @factor（及可选 @signal） */
  const applySignalFactorSelection = (next: {
    ids: string[];
    weights: number[];
    powers: number[];
    weightMode: StrategyWeightMode;
    tempLabels?: Record<string, string>;
    forceRewriteSignal?: boolean;
  }) => {
    const ids = next.ids;
    const w = normalizeSignalWeights(ids, next.weights);
    const powers = normalizeSignalPowers(ids, next.powers);
    const mode = next.weightMode;
    const labels = next.tempLabels ?? cfg?.signal_temp_labels ?? {};
    const idsKey = ids.join("\0");
    const prevIdsKey = (cfg?.signal_factor_ids || []).join("\0");
    const idsUnchanged = idsKey === prevIdsKey && ids.length > 0;
    const rewriteSignal =
      next.forceRewriteSignal === true || mode !== "custom";

    setCfg((prev) =>
      prev
        ? {
            ...prev,
            signal_factor_ids: ids,
            signal_factor_weights: w,
            signal_factor_powers: powers,
            signal_weight_mode: mode,
            signal_temp_labels: labels,
          }
        : prev,
    );

    const gen = ++factorSyncGen.current;
    setFactorSyncing(true);
    void (async () => {
      try {
        let bodies: string;
        if (idsUnchanged && cfg?.strategy_code && !next.forceRewriteSignal) {
          const marked = cfg.strategy_code.match(
            new RegExp(
              `${FACTORS_BEGIN.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[\\s\\S]*?${FACTORS_END.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`,
            ),
          );
          if (marked) {
            bodies = marked[0]
              .replace(FACTORS_BEGIN, "")
              .replace(FACTORS_END, "")
              .replace(/^\n|\n$/g, "");
          } else {
            bodies = await resolveStrategyFactorBodies(ids, {
              fallbackCode: cfg?.strategy_code,
              tempLabels: labels,
            });
          }
        } else {
          bodies = await resolveStrategyFactorBodies(ids, {
            fallbackCode: cfg?.strategy_code,
            tempLabels: labels,
          });
        }
        if (gen !== factorSyncGen.current) return;
        setCfg((prev) => {
          if (!prev) return prev;
          syncLock.current = "left";
          const nextCfg = {
            ...prev,
            signal_factor_ids: ids,
            signal_factor_weights: w,
            signal_factor_powers: powers,
            signal_weight_mode: mode,
            signal_temp_labels: labels,
          };
          const code = applyParamsToCode(
            applySignalFactorsToCode(prev.strategy_code, ids, w, bodies, {
              mode,
              powers,
              rewriteSignal,
            }),
            syncParams(nextCfg),
          );
          queueMicrotask(() => {
            syncLock.current = null;
          });
          return { ...nextCfg, strategy_code: code };
        });
        if (!idsUnchanged) {
          pushLog(`已同步 ${ids.length} 个信号因子到代码`);
        } else if (next.forceRewriteSignal) {
          pushLog(
            mode === "custom"
              ? "已切换自定义组合 · 请在右侧 @signal 中编写合成逻辑"
              : `已切换合成模式：${mode === "product" ? "赋幂相乘" : "赋权相加"}`,
          );
        }
      } catch (e) {
        if (gen !== factorSyncGen.current) return;
        pushLog(`同步因子失败：${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (gen === factorSyncGen.current) setFactorSyncing(false);
      }
    })();
  };

  const onCodeChange = (code: string) => {
    if (syncLock.current === "left") {
      setCfg((prev) => (prev ? { ...prev, strategy_code: code } : prev));
      return;
    }
    syncLock.current = "right";
    const parsed = parseParamsFromCode(code);
    setCfg((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        strategy_code: code,
        universe: parsed.universe ?? prev.universe,
        benchmark: parsed.benchmark ?? prev.benchmark,
        commission_rate: parsed.commission_rate ?? prev.commission_rate,
        stamp_tax: parsed.stamp_tax ?? prev.stamp_tax,
        slippage_rate: parsed.slippage_rate ?? prev.slippage_rate,
        initial_capital: parsed.initial_capital ?? prev.initial_capital,
        top_n: parsed.top_n ?? prev.top_n,
        rebalance_days: parsed.rebalance_days ?? prev.rebalance_days,
        rangeMode: parsed.range_mode ?? prev.rangeMode,
        backtestPeriod: parsed.backtest_period ?? prev.backtestPeriod,
        startDate:
          parsed.start_date !== undefined ? parsed.start_date : prev.startDate,
        endDate: parsed.end_date !== undefined ? parsed.end_date : prev.endDate,
      };
    });
    queueMicrotask(() => {
      syncLock.current = null;
    });
  };

  const persist = async (opts?: {
    /** 草稿态：仅回测成功前创建落库；点「保存」只写 session 草稿 */
    materializeDraft?: boolean;
  }): Promise<StrategyProject | null> => {
    if (!project || !cfg) return null;
    try {
      if (project.id === STRATEGY_DRAFT_ID) {
        if (!opts?.materializeDraft) {
          stashStrategyCloneDraft({
            name: project.name,
            description: project.description || project.name,
            strategy_code: cfg.strategy_code,
          });
          setSavedHint("草稿已更新（回测后才会出现在列表）");
          window.setTimeout(() => setSavedHint(""), 2000);
          return project;
        }
        const created = await createStrategyProject(
          project.name,
          project.description || project.name,
        );
        const saved = await saveStrategyProject({
          ...created,
          name: project.name,
          description: project.description || project.name,
          config: cfg,
        });
        const config = normalizeStrategyConfig(saved.config);
        const next = { ...saved, config };
        setProject(next);
        setCfg(config);
        clearStrategyCloneDraft();
        navigate(`/strategy/research/${saved.id}`, { replace: true });
        return next;
      }
      const saved = await saveStrategyProject({
        ...project,
        config: cfg,
      });
      const config = normalizeStrategyConfig(saved.config);
      const next = { ...saved, config };
      setProject(next);
      setCfg(config);
      setSavedHint("已保存");
      window.setTimeout(() => setSavedHint(""), 1500);
      return next;
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
      return null;
    }
  };

  const switchEngineMode = async (mode: StrategyEngineMode) => {
    if (!cfg || mode === cfg.engine_mode) return;
    const toEvent = mode === "event";
    const ok = await confirm({
      title: "切换执行模式",
      message: toEvent
        ? "切换到事件模式将替换为事件策略模板，并清空因子积木。是否继续？"
        : "切换到向量化模式将替换为组合策略模板，当前代码会被覆盖。是否继续？",
      confirmLabel: "继续切换",
    });
    if (!ok) return;
    const shell = {
      universe: cfg.universe,
      benchmark: cfg.benchmark,
      rangeMode: cfg.rangeMode,
      backtestPeriod: toEvent
        ? cfg.backtestPeriod || "3y"
        : cfg.backtestPeriod || "10y",
      startDate: cfg.startDate,
      endDate: cfg.endDate,
      commission_rate: cfg.commission_rate,
      stamp_tax: cfg.stamp_tax,
      slippage_rate: cfg.slippage_rate,
      initial_capital: cfg.initial_capital,
      top_n: cfg.top_n,
      rebalance_days: cfg.rebalance_days,
      include_rebalance_logs: cfg.include_rebalance_logs,
      library_ref: cfg.library_ref,
    };
    const next = normalizeStrategyConfig({
      ...shell,
      engine_mode: mode,
      strategy_code: toEvent
        ? DEFAULT_EVENT_STRATEGY_CODE
        : DEFAULT_STRATEGY_CODE,
      signal_factor_ids: [],
      signal_factor_weights: [],
      signal_factor_powers: [],
      signal_temp_labels: {},
      signal_weight_mode: "sum",
    });
    setCfg({
      ...next,
      strategy_code: syncCodeFromLeft(next),
    });
  };

  const onRun = async () => {
    if (!project || !cfg || running) return;
    if (factorSyncing) {
      pushLog("因子仍在同步到代码，请稍候再回测");
      return;
    }
    const code = cfg.strategy_code.trim();
    if (!code) {
      pushLog("策略代码为空");
      return;
    }
    const range = resolveStrategyRange(cfg);
    if (cfg.rangeMode === "custom" && (!range.start || !range.end)) {
      pushLog("请填写自定义起止日期");
      return;
    }
    setRunning(true);
    setLogs([]);
    pushLog(
      cfg.engine_mode === "event"
        ? "开始事件策略回测…"
        : "开始策略回测…",
    );
    const ac = new AbortController();
    abortRef.current = ac;
    const t0 = performance.now();
    const req = {
      strategy_code: code,
      engine_mode: cfg.engine_mode,
      universe: cfg.universe,
      start: range.start,
      end: range.end,
      benchmark: cfg.benchmark,
      commission_rate: cfg.commission_rate,
      stamp_tax: cfg.stamp_tax,
      slippage_rate: cfg.slippage_rate,
      initial_capital: cfg.initial_capital,
      include_positions: false,
      include_rebalance_logs: cfg.include_rebalance_logs,
    };
    try {
      // 草稿：回测跑通后再落库；失败则不建策略项目
      const result = await ygBacktestStrategy(req, ac.signal);
      const sec = Math.round((performance.now() - t0) / 1000);
      if (result.error) {
        pushLog(`回测未通过: ${result.error}`);
        return;
      }
      pushLog(
        project.id === STRATEGY_DRAFT_ID
          ? "回测完成，正在创建策略并保存记录…"
          : "回测完成，正在保存记录…",
      );
      const savedProject = await persist({ materializeDraft: true });
      if (!savedProject) {
        pushLog("保存策略失败");
        return;
      }
      const run = await saveStrategyRun({
        projectId: savedProject.id,
        name: savedProject.name,
        description: savedProject.description,
        // _svquant_ui 仅本地落库，方便「返回配置」还原左侧因子；不发给 RE
        request: {
          ...req,
          _svquant_ui: {
            signal_factor_ids: cfg.signal_factor_ids,
            signal_factor_weights: cfg.signal_factor_weights,
            signal_factor_powers: cfg.signal_factor_powers,
            signal_weight_mode: cfg.signal_weight_mode,
            signal_temp_labels: cfg.signal_temp_labels,
          },
        },
        result,
        elapsedSec: sec,
      });
      // 用户库策略：回测成功后去掉「待检测」
      const libRef = String(savedProject.config?.library_ref || "");
      const m = /^userlib:(\d+)$/.exec(libRef);
      if (m) {
        try {
          const { markUserLibraryStrategyDetected } = await import(
            "@/lib/userStrategyLibraries"
          );
          await markUserLibraryStrategyDetected(Number(m[1]));
        } catch {
          /* 非阻断 */
        }
      }
      pushLog(`已保存 · ${sec}s`);
      navigate(`/strategy/research/report/${run.id}`);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") pushLog("已取消");
      else pushLog(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-4rem)] items-center justify-center text-sm text-slate-400">
        加载中…
      </div>
    );
  }

  if (loadErr || !project || !cfg) {
    return (
      <div className="p-10 text-center">
        <p className="text-slate-600">{loadErr || "项目不存在"}</p>
        <Link to="/strategy/research" className="mt-3 inline-block text-blue-600 underline">
          返回列表
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col bg-[#f0f2f5] lg:h-[calc(100vh-4rem)]">
      <div className="flex flex-col gap-2 border-b border-slate-200 bg-white px-3 py-2.5 sm:px-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Link
            to="/strategy/research"
            className="hidden text-slate-400 hover:text-slate-700 sm:inline"
          >
            策略研究
          </Link>
          <span className="hidden text-slate-300 sm:inline">/</span>
          <span className="truncate font-semibold text-slate-900">{project.name}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void persist()}
            className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50"
          >
            <span className="inline-flex items-center gap-1">
              <Save className="h-3.5 w-3.5" />
              <span className="sm:hidden">保存</span>
              <span className="hidden sm:inline">
                保存{savedHint ? ` · ${savedHint}` : ""}
              </span>
            </span>
          </button>
          <button
            type="button"
            disabled={running}
            onClick={() => void onRun()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {running ? `回测中 ${elapsed}s` : "进行回测"}
          </button>
          {running ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="inline-flex items-center justify-center rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
            >
              取消
            </button>
          ) : null}
          <Link
            to={`/strategy/research/${projectId}/history`}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">回测报告</span>
            <span className="sm:hidden">报告</span>
          </Link>
          <Link
            to="/strategy/research"
            className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">列表</span>
          </Link>
        </div>
      </div>

      <nav
        className="flex gap-1.5 border-b border-slate-200 bg-white px-3 py-2 lg:hidden"
        aria-label="研究区分区"
      >
        {(
          [
            { id: "config" as const, label: "配置" },
            { id: "code" as const, label: "代码与日志" },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setMobilePane(item.id)}
            className={`rounded-full px-3 py-1.5 text-xs transition ${
              mobilePane === item.id
                ? "bg-blue-600 font-semibold text-white"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[1.1fr_1fr]">
        <aside
          className={`min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm ${
            mobilePane === "config" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="flex-1 space-y-5 overflow-y-auto px-3 py-4 text-sm sm:px-5 sm:py-5">
            <section>
              <h2 className="mb-2 text-sm font-bold text-blue-600">执行模式</h2>
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    { id: "vectorized" as const, label: "向量化" },
                    { id: "event" as const, label: "事件" },
                  ] as const
                ).map((opt) => {
                  const active = cfg.engine_mode === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => void switchEngineMode(opt.id)}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        active
                          ? opt.id === "event"
                            ? "bg-teal-700 text-white"
                            : "bg-slate-800 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </section>

            {cfg.engine_mode === "event" ? null : usesFactorPortfolioTemplate(
                cfg.strategy_code,
              ) ? (
              <StrategySignalFactorsPanel
                factorIds={cfg.signal_factor_ids}
                weights={cfg.signal_factor_weights}
                powers={cfg.signal_factor_powers}
                weightMode={cfg.signal_weight_mode}
                tempLabels={cfg.signal_temp_labels}
                syncing={factorSyncing}
                onChange={applySignalFactorSelection}
              />
            ) : (
              <section className="rounded-lg border border-dashed border-slate-200 bg-slate-50/60 px-3 py-2.5">
                <h2 className="text-sm font-bold text-slate-400">因子选择 + 权重</h2>
                <p className="mt-1 text-[11px] leading-snug text-slate-400">
                  当前为 <code className="text-slate-500">generate_signals()</code>{" "}
                  自由策略，左侧因子积木已隐藏；请直接改右侧代码。
                  平台策略库已统一为 FactorPortfolio 模板，可从策略库重新打开以刷新。
                </p>
              </section>
            )}

            <section>
              <h2 className="mb-3 text-sm font-bold text-blue-600">
                {cfg.engine_mode === "event" ? "回测参数" : "3. 参数设置"}
              </h2>
              <div className="grid gap-3 lg:grid-cols-2">
                <label className="block text-xs text-slate-500">
                  股票池
                  <select
                    className={fieldClass("mt-1")}
                    value={cfg.universe}
                    onChange={(e) => patchCfg({ universe: e.target.value }, "left")}
                  >
                    {STRATEGY_UNIVERSE_OPTIONS.map((o) => (
                      <option key={o.code} value={o.code}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs text-slate-500">
                  基准
                  <select
                    className={fieldClass("mt-1")}
                    value={cfg.benchmark}
                    onChange={(e) => patchCfg({ benchmark: e.target.value }, "left")}
                  >
                    {STRATEGY_BENCHMARK_OPTIONS.map((o) => (
                      <option key={o.code} value={o.code}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs text-slate-500">
                  回测区间
                  <select
                    className={fieldClass("mt-1")}
                    value={cfg.rangeMode}
                    onChange={(e) => {
                      const mode = e.target.value as "period" | "custom";
                      if (mode === "custom") {
                        const fill = defaultCustomRangeDates(cfg.backtestPeriod || "10y");
                        patchCfg(
                          {
                            rangeMode: mode,
                            startDate: cfg.startDate || fill.startDate,
                            endDate: cfg.endDate || fill.endDate,
                          },
                          "left",
                        );
                      } else {
                        patchCfg({ rangeMode: mode }, "left");
                      }
                    }}
                  >
                    <option value="period">预设周期</option>
                    <option value="custom">自定义区间</option>
                  </select>
                </label>
                {cfg.rangeMode === "period" ? (
                  <label className="block text-xs text-slate-500">
                    回测时长
                    <select
                      className={fieldClass("mt-1")}
                      value={cfg.backtestPeriod}
                      onChange={(e) =>
                        patchCfg({ backtestPeriod: e.target.value }, "left")
                      }
                    >
                      {STRATEGY_PERIOD_OPTIONS.map((o) => (
                        <option key={o.code} value={o.code}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <>
                    <label className="block text-xs text-slate-500">
                      开始日期
                      <input
                        type="date"
                        className={fieldClass("mt-1")}
                        value={cfg.startDate}
                        max={cfg.endDate || undefined}
                        onChange={(e) => {
                          const startDate = e.target.value;
                          const clamped = clampDateRange(
                            startDate,
                            cfg.endDate,
                            "start",
                          );
                          patchCfg(clamped, "left");
                        }}
                      />
                    </label>
                    <label className="block text-xs text-slate-500">
                      结束日期
                      <input
                        type="date"
                        className={fieldClass("mt-1")}
                        value={cfg.endDate}
                        min={cfg.startDate || undefined}
                        onChange={(e) => {
                          const endDate = e.target.value;
                          const clamped = clampDateRange(
                            cfg.startDate,
                            endDate,
                            "end",
                          );
                          patchCfg(clamped, "left");
                        }}
                      />
                    </label>
                  </>
                )}
                {cfg.engine_mode === "event" ? null : (
                  <>
                    <label className="block text-xs text-slate-500">
                      持仓数
                      <input
                        type="number"
                        step="1"
                        min={1}
                        className={fieldClass("mt-1")}
                        value={cfg.top_n}
                        onChange={(e) =>
                          patchCfg(
                            {
                              top_n: Math.max(
                                1,
                                Math.round(Number(e.target.value) || 1),
                              ),
                            },
                            "left",
                          )
                        }
                      />
                    </label>
                    <label className="block text-xs text-slate-500">
                      调仓周期（交易日）
                      <input
                        type="number"
                        step="1"
                        min={1}
                        className={fieldClass("mt-1")}
                        value={cfg.rebalance_days}
                        onChange={(e) =>
                          patchCfg(
                            {
                              rebalance_days: Math.max(
                                1,
                                Math.round(Number(e.target.value) || 1),
                              ),
                            },
                            "left",
                          )
                        }
                      />
                    </label>
                  </>
                )}
                <label className="block text-xs text-slate-500">
                  佣金率
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    className={fieldClass("mt-1")}
                    value={cfg.commission_rate}
                    onChange={(e) =>
                      patchCfg(
                        { commission_rate: Number(e.target.value) || 0 },
                        "left",
                      )
                    }
                  />
                </label>
                <label className="block text-xs text-slate-500">
                  印花税
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    className={fieldClass("mt-1")}
                    value={cfg.stamp_tax}
                    onChange={(e) =>
                      patchCfg({ stamp_tax: Number(e.target.value) || 0 }, "left")
                    }
                  />
                </label>
                <label className="block text-xs text-slate-500">
                  滑点率
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    className={fieldClass("mt-1")}
                    value={cfg.slippage_rate}
                    onChange={(e) =>
                      patchCfg(
                        { slippage_rate: Number(e.target.value) || 0 },
                        "left",
                      )
                    }
                  />
                </label>
                <label className="block text-xs text-slate-500">
                  起始资金
                  <input
                    type="number"
                    step="1000"
                    min={0}
                    className={fieldClass("mt-1")}
                    value={cfg.initial_capital}
                    onChange={(e) =>
                      patchCfg(
                        { initial_capital: Number(e.target.value) || 0 },
                        "left",
                      )
                    }
                  />
                </label>
              </div>
              {cfg.engine_mode === "event" ? null : (
                <label className="mt-3 flex cursor-pointer items-center gap-2.5 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
                    checked={cfg.include_rebalance_logs}
                    onChange={(e) =>
                      patchCfg(
                        { include_rebalance_logs: e.target.checked },
                        "left",
                      )
                    }
                  />
                  <span className="text-xs font-medium text-slate-700">
                    返回调仓日志
                  </span>
                </label>
              )}
            </section>
          </div>
        </aside>

        <div
          className={`min-h-0 flex-col gap-3 ${
            mobilePane === "code" ? "flex" : "hidden lg:flex"
          }`}
        >
          <section className="flex min-h-[50vh] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:min-h-0 lg:flex-[3]">
            <div className="border-b border-slate-100 px-4 py-2">
              <span className="text-xs font-semibold text-slate-600">
                策略代码
                {cfg.engine_mode === "event" ? (
                  <span className="ml-2 rounded bg-teal-50 px-1.5 py-0.5 text-[10px] font-medium text-teal-800">
                    事件
                  </span>
                ) : null}
              </span>
            </div>
            <div className="min-h-0 flex-1 p-2">
              <FactorCodeEditor
                value={cfg.strategy_code}
                onChange={onCodeChange}
                height="100%"
                variant="light"
                className="h-full min-h-[40vh] lg:min-h-0"
              />
            </div>
          </section>
          <section className="flex min-h-[10rem] max-h-56 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:max-h-none lg:min-h-0 lg:flex-1">
            <div className="border-b border-slate-100 px-4 py-2">
              <span className="text-xs font-semibold text-slate-600">运行日志</span>
            </div>
            <div className="flex-1 overflow-auto bg-slate-950 px-4 py-3 font-mono text-[12px] leading-relaxed text-slate-200">
              {logs.length === 0 ? (
                <span className="text-slate-500">等待运行…</span>
              ) : (
                logs.map((l, i) => {
                  const isErr = /失败|异常|错误|未通过|为空|请填/.test(l);
                  return (
                    <div
                      key={`${i}-${l.slice(0, 12)}`}
                      className={isErr ? "text-red-400" : ""}
                    >
                      {l}
                    </div>
                  );
                })
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
