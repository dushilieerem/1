import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  Loader2,
  Play,
  Save,
} from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import { ygBacktestStrategy } from "@/lib/ygApi";
import {
  applyParamsToCode,
  parseParamsFromCode,
} from "@/lib/strategyCodeSync";
import {
  STRATEGY_DRAFT_ID,
  clearStrategyCloneDraft,
  createStrategyProject,
  getStrategyProject,
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
  type StrategyProject,
  type StrategyProjectConfig,
} from "@/lib/strategyStore";

function fieldClass(extra = "") {
  return `h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200 ${extra}`;
}

function syncParams(cfg: StrategyProjectConfig) {
  return {
    universe: cfg.universe,
    benchmark: cfg.benchmark,
    commission_rate: cfg.commission_rate,
    stamp_tax: cfg.stamp_tax,
    slippage_rate: cfg.slippage_rate,
    initial_capital: cfg.initial_capital,
    top_n: cfg.top_n,
    rebalance_days: cfg.rebalance_days,
  };
}

export function StrategyBacktestPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const isDraft = projectId === STRATEGY_DRAFT_ID;
  const [project, setProject] = useState<StrategyProject | null>(null);
  const [cfg, setCfg] = useState<StrategyProjectConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [savedHint, setSavedHint] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const syncLock = useRef<"left" | "right" | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
        strategy_code: applyParamsToCode(config.strategy_code, {
          universe: config.universe,
          benchmark: config.benchmark,
          commission_rate: config.commission_rate,
          stamp_tax: config.stamp_tax,
          slippage_rate: config.slippage_rate,
          initial_capital: config.initial_capital,
          top_n: config.top_n,
          rebalance_days: config.rebalance_days,
        }),
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

    void getStrategyProject(projectId)
      .then((p) => {
        if (cancelled) return;
        const config = normalizeStrategyConfig(p.config);
        // 旧项目代码块缺印花税/基准时，用表单默认值写回一次
        const synced = {
          ...config,
          strategy_code: applyParamsToCode(config.strategy_code, {
            universe: config.universe,
            benchmark: config.benchmark,
            commission_rate: config.commission_rate,
            stamp_tax: config.stamp_tax,
            slippage_rate: config.slippage_rate,
            initial_capital: config.initial_capital,
            top_n: config.top_n,
            rebalance_days: config.rebalance_days,
          }),
        };
        setProject({ ...p, config: synced });
        setCfg(synced);
      })
      .catch((e) => {
        if (!cancelled) setLoadErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [projectId, isDraft]);

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
          strategy_code: applyParamsToCode(next.strategy_code, syncParams(next)),
        };
        queueMicrotask(() => {
          syncLock.current = null;
        });
      }
      return next;
    });
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

  const onRun = async () => {
    if (!project || !cfg || running) return;
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
    pushLog("开始策略回测…");
    const ac = new AbortController();
    abortRef.current = ac;
    const t0 = performance.now();
    const req = {
      strategy_code: code,
      universe: cfg.universe,
      start: range.start,
      end: range.end,
      benchmark: cfg.benchmark,
      commission_rate: cfg.commission_rate,
      stamp_tax: cfg.stamp_tax,
      slippage_rate: cfg.slippage_rate,
      initial_capital: cfg.initial_capital,
      include_positions: false,
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
        request: req,
        result,
        elapsedSec: sec,
      });
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
    <div className="flex h-[calc(100vh-4rem)] flex-col bg-[#f0f2f5]">
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Link to="/strategy/research" className="text-slate-400 hover:text-slate-700">
            策略研究
          </Link>
          <span className="text-slate-300">/</span>
          <span className="truncate font-semibold text-slate-900">{project.name}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => void persist()}
            className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50"
          >
            <span className="inline-flex items-center gap-1">
              <Save className="h-3.5 w-3.5" />
              保存{savedHint ? ` · ${savedHint}` : ""}
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
          <Link
            to={`/strategy/research/${projectId}/history`}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            回测报告
          </Link>
          <Link
            to="/strategy/research"
            className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            列表
          </Link>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[1.1fr_1fr]">
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 text-sm">
            <section>
              <h2 className="mb-3 text-sm font-bold text-blue-600">参数设置</h2>
              <div className="grid gap-3 sm:grid-cols-2">
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
                        { top_n: Math.max(1, Math.round(Number(e.target.value) || 1)) },
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
            </section>
          </div>
        </aside>

        <div className="flex min-h-0 flex-col gap-3">
          <section className="flex min-h-0 flex-[3] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-4 py-2">
              <span className="text-xs font-semibold text-slate-600">策略代码</span>
            </div>
            <div className="min-h-0 flex-1 p-2">
              <FactorCodeEditor
                value={cfg.strategy_code}
                onChange={onCodeChange}
                height="100%"
                variant="light"
                className="h-full"
              />
            </div>
          </section>
          <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
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
