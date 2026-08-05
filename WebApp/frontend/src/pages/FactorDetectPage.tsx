import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, BarChart3, Loader2, Play, Plus, Save, X } from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import { FactorPickerModal } from "@/components/FactorPickerModal";
import {
  buildComboFunction,
  buildYgFactorRequestParts,
  extractEntryName,
  isReBuiltinLib,
} from "@/lib/detectComboCode";
import {
  DETECT_ANALYSIS_LEVEL_OPTIONS,
  DETECT_BENCHMARK_OPTIONS,
  DETECT_PERIOD_OPTIONS,
  DETECT_UNIVERSE_OPTIONS,
  PORTFOLIO_TYPE_OPTIONS,
  clampDateRange,
  defaultCustomRangeDates,
  equalPowers,
  equalWeights,
  getProject,
  peekProject,
  resolveBacktestRange,
  saveDetectRun,
  saveProject,
  type AnalysisLevel,
  type DetectProject,
  type DraftDetectFactor,
  type RangeMode,
  type WeightMode,
} from "@/lib/detectStore";
import {
  builtinCategoryLabelsFromFactors,
  extractMethod,
  loadFactors,
  loadLibrarySource,
  renameMethodDef,
  type FactorMeta,
} from "@/lib/factorCatalog";
import {
  listAllUserLibraryFactors,
  userLibraryFactorToMeta,
} from "@/lib/userFactorLibraries";
import { ygBacktestFactor, type YgBacktestRequest } from "@/lib/ygApi";

const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

function draftBodyTemplate(name: string, description: string): string {
  const doc = (description || name).replace(/\\/g, "\\\\").replace(/"""/g, "'''");
  return `def ${name}(self):\n    """${doc}"""\n    return self.close.pct_change(5)\n`;
}

/** 自定义组合编辑器：展示「因子实现 + 组合」；写回时只抽出组合部分 */
function extractCustomCombineFromEditor(
  full: string,
  factorCodes: string[],
  methodBodies: string[],
): string {
  const text = (full || "").replace(/\r\n/g, "\n");
  const methods = methodBodies.map((m) => m.trim()).filter(Boolean).join("\n\n");
  if (methods) {
    const trimmed = text.trimStart();
    if (trimmed.startsWith(methods)) {
      return trimmed.slice(methods.length).replace(/^\n+/, "");
    }
  }
  const factorSet = new Set(factorCodes);
  const re = /^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (!factorSet.has(m[1])) {
      return text.slice(m.index);
    }
  }
  return text.trim();
}

export function FactorDetectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<DetectProject | null | undefined>(() =>
    projectId ? peekProject(projectId) ?? undefined : undefined,
  );
  const [catalog, setCatalog] = useState<FactorMeta[]>([]);
  const [methodBodies, setMethodBodies] = useState<string[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createCategory, setCreateCategory] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [runError, setRunError] = useState<string | null>(null);
  const [savedHint, setSavedHint] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const tickRef = useRef<number | null>(null);

  const cfg = project?.config;
  const draftFactor = cfg?.draftFactor ?? null;
  const isDraftMode = Boolean(draftFactor?.name);

  const pushLog = useCallback((line: string) => {
    const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setLogs((prev) => [...prev.slice(-80), `[${ts}] ${line}`]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const cached = peekProject(projectId);
    if (cached) {
      setProject(cached);
      setLogs((prev) =>
        prev.length
          ? prev
          : [`[${new Date().toLocaleTimeString("zh-CN", { hour12: false })}] 已加载项目：${cached.name}`],
      );
    } else {
      setProject(undefined);
    }
    void (async () => {
      const p = await getProject(projectId);
      if (cancelled) return;
      if (!p) {
        setProject(null);
        return;
      }
      setProject(p);
      const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
      setLogs((prev) => (prev.length ? prev : [`[${ts}] 已加载项目：${p.name}`]));
      void Promise.all([
        loadFactors().catch(() => [] as FactorMeta[]),
        listAllUserLibraryFactors()
          .then((rows) => rows.map(userLibraryFactorToMeta))
          .catch(() => [] as FactorMeta[]),
      ]).then(([builtin, userFs]) => {
        if (cancelled) return;
        const byName = new Map<string, FactorMeta>();
        for (const f of builtin) {
          if (f.library !== "custom_lib") byName.set(f.name, f);
        }
        for (const f of userFs) byName.set(f.name, f);
        setCatalog([...byName.values()]);
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // 已入库的草稿：去掉琥珀色，按普通库因子展示
  useEffect(() => {
    const draftName = project?.config?.draftFactor?.name;
    if (!draftName || !catalog.length) return;
    const inUserLib = catalog.some(
      (f) => f.name === draftName && f.library.startsWith("user_lib_"),
    );
    if (!inUserLib) return;
    setProject((prev) => {
      if (!prev?.config?.draftFactor?.name) return prev;
      if (prev.config.draftFactor.name !== draftName) return prev;
      const name = prev.config.draftFactor.name;
      const codes = prev.config.factorCodes.length
        ? prev.config.factorCodes
        : [name];
      const next = {
        ...prev,
        config: {
          ...prev.config,
          draftFactor: null,
          factorCodes: codes,
          weightMode: "sum" as const,
          weights: equalWeights(codes.length),
          powers: equalPowers(codes.length),
        },
      };
      void saveProject(next);
      return next;
    });
  }, [catalog, project?.config?.draftFactor?.name, project?.id]);

  const categoryOptions = useMemo(() => {
    const cats = builtinCategoryLabelsFromFactors(
      catalog.filter((f) => !f.library.startsWith("user_lib_")),
    );
    return [...cats, "其他"];
  }, [catalog]);

  const factorLabel = useCallback(
    (code: string) => {
      if (draftFactor && draftFactor.name === code) {
        return draftFactor.description || draftFactor.name;
      }
      const f = catalog.find((x) => x.name === code);
      return f?.explain || f?.description || code;
    },
    [catalog, draftFactor],
  );

  useEffect(() => {
    if (isDraftMode && draftFactor) {
      setMethodBodies([draftFactor.body || ""]);
      return;
    }
    if (!cfg?.factorCodes.length) {
      setMethodBodies([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const fs = catalog.length ? catalog : await loadFactors();
        const byName = new Map(fs.map((f) => [f.name, f]));
        const bodies: string[] = [];
        const fileCache = new Map<string, string>();
        for (const code of cfg.factorCodes) {
          const meta = byName.get(code);
          if (!meta) {
            bodies.push(`# 未找到因子 ${code}`);
            continue;
          }
          if (meta.body) {
            bodies.push(renameMethodDef(meta.body, code));
            continue;
          }
          if (isReBuiltinLib(meta.library)) {
            bodies.push(
              `# RE库 ${meta.library} · ${code}（由 library_name 加载完整库，含私有辅助）`,
            );
            continue;
          }
          let src = fileCache.get(meta.libraryFile);
          if (!src) {
            src = await loadLibrarySource(meta.libraryFile);
            fileCache.set(meta.libraryFile, src);
          }
          bodies.push(renameMethodDef(extractMethod(src, meta.methodName || code), code));
        }
        if (!cancelled) setMethodBodies(bodies);
      } catch (e) {
        if (!cancelled) {
          setMethodBodies([]);
          pushLog(`加载因子源码失败：${e instanceof Error ? e.message : String(e)}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cfg?.factorCodes, catalog, pushLog, isDraftMode, draftFactor]);

  const comboFn = useMemo(() => {
    if (!cfg) return "";
    return buildComboFunction({
      mode: cfg.weightMode,
      factorCodes: cfg.factorCodes,
      weights: cfg.weights,
      powers: cfg.powers,
      customCombine: cfg.customCombine,
      entryName: "combo_factor",
      title: project?.name || "组合因子",
    });
  }, [cfg, project?.name]);

  const methodsText = methodBodies.join("\n\n");

  /** 多于 1 个因子才显示合成参数 */
  const showSynthesis = !isDraftMode && (cfg?.factorCodes.length ?? 0) > 1;

  /** 右侧统一代码区：单因子只看因子函数；多因子看实现+组合；自定义=实现(只读前缀)+可编辑组合 */
  const unifiedCode = useMemo(() => {
    if (!cfg) return "";
    if (isDraftMode && draftFactor) return draftFactor.body || "";
    const methods = methodsText.trim();
    if (cfg.weightMode === "custom") {
      const combo = (cfg.customCombine || "").trim();
      if (!methods) return combo || "# 请先选择因子，再写组合函数";
      return combo ? `${methods}\n\n${combo}` : `${methods}\n\n# 请在下方编写组合函数 combo_factor`;
    }
    const n = cfg.factorCodes.length;
    if (n === 0) return "# 请先选择因子";
    if (n === 1) {
      const body = methodBodies[0]?.trim() || "";
      if (body.startsWith("# RE库")) {
        return `${body}\n# 提交时走 library_name，不传 factor_code`;
      }
      return body || `# 未找到因子 ${cfg.factorCodes[0]}`;
    }
    const combo = comboFn.trim();
    return [methods, combo].filter(Boolean).join("\n\n");
  }, [cfg, isDraftMode, draftFactor, methodBodies, methodsText, comboFn]);

  const codeEditable =
    Boolean(isDraftMode && draftFactor) || cfg?.weightMode === "custom";

  const patchConfig = (partial: Partial<NonNullable<DetectProject["config"]>>) => {
    setProject((prev) => {
      if (!prev) return prev;
      return { ...prev, config: { ...prev.config, ...partial } };
    });
  };

  const applyFactors = (codes: string[]) => {
    setProject((prev) => {
      if (!prev) return prev;
      const mode = prev.config.weightMode;
      const weights = mode === "sum" ? equalWeights(codes.length) : codes.map((_, i) => prev.config.weights[i] ?? 0);
      const powers = mode === "product" ? equalPowers(codes.length) : codes.map((_, i) => prev.config.powers[i] ?? 1);
      let customCombine = prev.config.customCombine;
      if (mode === "custom" && codes.length) {
        const mentionsAny = codes.some((c) => customCombine.includes(`self.${c}()`));
        if (!mentionsAny) {
          if (codes.length === 1) {
            customCombine = `def combo_factor(self):\n    """${prev.name}"""\n    return self.${codes[0]}()`;
          } else {
            const expr = codes.map((c) => `self.${c}()`).join(" * ");
            customCombine = `def combo_factor(self):\n    """${prev.name} · 自定义组合"""\n    return ${expr}`;
          }
        }
      }
      return {
        ...prev,
        factorName: codes.length === 1 ? codes[0] : "combo_factor",
        config: {
          ...prev.config,
          factorCodes: codes,
          weights,
          powers,
          customCombine,
          draftFactor: null,
        },
      };
    });
  };

  const removeFactor = (code: string) => {
    if (!cfg) return;
    if (draftFactor && draftFactor.name === code) {
      setProject((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          factorName: "combo_factor",
          config: {
            ...prev.config,
            factorCodes: [],
            weights: [],
            powers: [],
            draftFactor: null,
          },
        };
      });
      return;
    }
    applyFactors(cfg.factorCodes.filter((c) => c !== code));
  };

  const confirmCreateFactor = () => {
    setCreateErr(null);
    const name = createName.trim();
    const description = createDesc.trim();
    const category = createCategory.trim();
    if (!name) {
      setCreateErr("请填写因子代码名");
      return;
    }
    if (!NAME_RE.test(name)) {
      setCreateErr("代码名须为字母开头的标识符（字母/数字/下划线）");
      return;
    }
    if (!description) {
      setCreateErr("请填写中文解释");
      return;
    }
    if (!category) {
      setCreateErr("请选择分类");
      return;
    }
    if (catalog.some((f) => f.name === name)) {
      setCreateErr(`因子「${name}」已存在，请换一个代码名`);
      return;
    }
    const draft: DraftDetectFactor = {
      name,
      description,
      category,
      body: draftBodyTemplate(name, description),
    };
    setProject((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        factorName: name,
        config: {
          ...prev.config,
          factorCodes: [name],
          weights: [100],
          powers: [1],
          weightMode: "sum",
          draftFactor: draft,
        },
      };
    });
    setCreateOpen(false);
    setCreateName("");
    setCreateDesc("");
    setCreateCategory("其他");
    pushLog(`已新建自定义因子：${name}（检测后可入库）`);
  };

  const setWeightMode = (mode: WeightMode) => {
    setProject((prev) => {
      if (!prev) return prev;
      const n = prev.config.factorCodes.length;
      return {
        ...prev,
        config: {
          ...prev.config,
          weightMode: mode,
          weights: mode === "sum" ? equalWeights(n) : prev.config.weights,
          powers: mode === "product" ? equalPowers(n) : prev.config.powers,
        },
      };
    });
  };

  const persist = () => {
    if (!project) return;
    void saveProject(project).then((saved) => {
      setProject(saved);
      setSavedHint("已保存");
      window.setTimeout(() => setSavedHint(""), 1500);
      pushLog("项目配置已保存");
    });
  };

  const onRun = useCallback(async () => {
    if (!project || !cfg) return;
    setRunError(null);
    const draft = cfg.draftFactor;
    const customOnly =
      cfg.weightMode === "custom" && Boolean(cfg.customCombine?.trim());
    if (!cfg.factorCodes.length && !customOnly && !draft) {
      const msg = "请先在上方添加因子，或使用自定义组合函数";
      setRunError(msg);
      pushLog(msg);
      return;
    }
    if (draft) {
      const body = (draft.body || "").trim();
      if (!body) {
        const msg = "请先编写因子代码";
        setRunError(msg);
        pushLog(msg);
        return;
      }
    }
    const catalogForBuild: FactorMeta[] = draft
      ? [
          ...catalog,
          {
            name: draft.name,
            methodName: draft.name,
            description: draft.description,
            explain: draft.description,
            formula: "",
            params: {},
            library: "draft_lib",
            libraryFile: "",
            libraryLabel: draft.category,
            body: draft.body,
          },
        ]
      : catalog;
    const bodiesForBuild = draft ? [draft.body] : methodBodies;
    const combo = buildComboFunction({
      mode: draft ? "sum" : cfg.weightMode,
      factorCodes: draft ? [draft.name] : cfg.factorCodes,
      weights: draft ? [100] : cfg.weights,
      powers: draft ? [1] : cfg.powers,
      customCombine: cfg.customCombine,
      entryName: "combo_factor",
      title: project.name,
    });
    const entryName = extractEntryName(combo, project.factorName || "combo_factor");
    const parts = buildYgFactorRequestParts({
      factors: catalogForBuild,
      factorCodes: draft ? [draft.name] : cfg.factorCodes,
      methodBodies: bodiesForBuild,
      comboFn: combo,
      entryName,
    });
    if (!parts.factor_code && !parts.library_name) {
      const msg = "因子代码为空，无法检测";
      setRunError(msg);
      pushLog(msg);
      return;
    }

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setRunning(true);
    setElapsed(0);
    const t0 = Date.now();
    tickRef.current = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 400);
    saveProject(project);
    pushLog("开始检测 · 调用 ResearchEngine 因子回测");
    const entryHint = parts.library_name
      ? `入口 ${parts.factor_name} · RE 库 ${
          Array.isArray(parts.library_name)
            ? parts.library_name.join(", ")
            : parts.library_name
        }${parts.factor_code ? " + 本地源码" : ""}`
      : `入口 ${parts.factor_name} · 仅本地/自定义源码`;
    pushLog(entryHint);
    try {
      const { start, end } = resolveBacktestRange(cfg);
      const req: YgBacktestRequest = {
        ...parts,
        portfolio_type: cfg.portfolioType,
        universe: cfg.universe,
        start,
        end,
        filter_limit_up: cfg.filterLimitUp,
        filter_suspended: cfg.filterSuspended,
        benchmark: cfg.benchmark,
        groups: Math.min(5, Math.max(1, cfg.groups || 5)),
        rebalance_days: cfg.rebalanceDays,
        commission_rate: cfg.commissionRate,
        stamp_tax: cfg.stampTax,
        slippage_rate: cfg.slippageRate,
        analysis_level: cfg.analysisLevel || "core",
      };
      pushLog(
        `区间 ${start} → ${end} · 池 ${cfg.universe} · 深度 ${req.analysis_level}`,
      );
      const res = await ygBacktestFactor(req, ac.signal);
      const elapsedSec = Math.floor((Date.now() - t0) / 1000);
      if (res.error) {
        const msg = res.error;
        setRunError(msg);
        pushLog(`检测失败（代码/执行错误）: ${msg}`);
        pushLog("不会跳转报告页 · 请改组合函数或单因子代码后重试");
        return;
      }
      const saveReq = {
        ...req,
        ...(draft ? { _svquantDraftFactor: draft } : {}),
      } as YgBacktestRequest & { _svquantDraftFactor?: DraftDetectFactor };
      const rec = await saveDetectRun({
        projectId: project.id,
        factorName: parts.factor_name,
        description: project.name,
        request: saveReq,
        result: res,
        finishedAt: new Date().toISOString(),
        elapsedSec,
        draftFactor: draft || null,
      });
      pushLog(`完成 ${elapsedSec}s，跳转报告`);
      navigate(`/factor/detect/report/${rec.id}`);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        const msg = e instanceof Error ? e.message : String(e);
        // 旧版 localStorage 配额错误：给可操作提示
        if (/quota|setItem|Storage/i.test(msg)) {
          const tip =
            "浏览器本地缓存已满（检测结果含大序列）。已切换 IndexedDB 存储，请刷新页面后再点一次检测。";
          setRunError(tip);
          pushLog(`浏览器异常: ${msg}`);
          pushLog(tip);
          try {
            localStorage.removeItem("svquant_detect_runs_v2");
          } catch {
            /* ignore */
          }
        } else {
          setRunError(msg);
          pushLog(`请求异常: ${msg}`);
        }
      }
    } finally {
      if (tickRef.current) window.clearInterval(tickRef.current);
      setRunning(false);
      setElapsed(Math.floor((Date.now() - t0) / 1000));
    }
  }, [project, cfg, methodBodies, catalog, navigate, pushLog]);

  if (project === undefined) {
    return <div className="p-10 text-center text-slate-400">加载中…</div>;
  }

  if (!project || !cfg) {
    return (
      <div className="p-10 text-center">
        <p className="text-slate-600">项目不存在</p>
        <Link to="/factor/detect" className="mt-3 inline-block text-blue-600 underline">
          返回列表
        </Link>
      </div>
    );
  }

  const portfolioHint =
    PORTFOLIO_TYPE_OPTIONS.find((p) => p.code === cfg.portfolioType)?.hint || "";

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col bg-[#f0f2f5]">
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Link to="/factor/detect" className="text-slate-400 hover:text-slate-700">
            因子算法
          </Link>
          <span className="text-slate-300">/</span>
          <Link to={`/factor/detect/${projectId}/history`} className="text-slate-400 hover:text-slate-700">
            检测列表
          </Link>
          <span className="text-slate-300">/</span>
          <span className="truncate font-semibold text-slate-900">{project.name}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={persist}
            className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50"
          >
            <span className="inline-flex items-center gap-1">
              <Save className="h-3.5 w-3.5" />
              保存{savedHint ? ` · ${savedHint}` : ""}
            </span>
          </button>
          <button
            type="button"
            disabled={
              running ||
              (!cfg.factorCodes.length &&
                !(cfg.weightMode === "custom" && cfg.customCombine?.trim()))
            }
            onClick={() => void onRun()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {running ? `检测中 ${elapsed}s` : "进行检测"}
          </button>
          <Link
            to={`/factor/detect/${projectId}/history`}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            检测报告
          </Link>
          <Link to="/factor/detect" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
            <ArrowLeft className="h-3.5 w-3.5" />
            列表
          </Link>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[1.35fr_0.65fr]">
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5 text-sm">
            {/* 1. 添加因子 */}
            <section>
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 className="text-sm font-bold text-blue-600">1. 添加因子</h2>
                {!isDraftMode ? (
                  <button
                    type="button"
                    onClick={() => {
                      setCreateErr(null);
                      setCreateName("");
                      setCreateDesc("");
                      setCreateCategory("");
                      setCreateOpen(true);
                    }}
                    className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-100"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    新建因子
                  </button>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                {isDraftMode && draftFactor ? (
                  <span
                    className="inline-flex max-w-[260px] items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs shadow-sm"
                    title={draftFactor.name}
                  >
                    <span className="truncate font-medium text-amber-900">
                      {draftFactor.description || draftFactor.name}
                    </span>
                    <code className="shrink-0 text-[10px] text-amber-700/80">
                      {draftFactor.name}
                    </code>
                    <button
                      type="button"
                      onClick={() => removeFactor(draftFactor.name)}
                      className="shrink-0 text-amber-600 hover:text-red-500"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ) : (
                  <>
                    {cfg.factorCodes.map((c) => (
                      <span
                        key={c}
                        className="inline-flex max-w-[220px] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-sm"
                        title={factorLabel(c)}
                      >
                        <span className="truncate font-medium text-slate-800">
                          {factorLabel(c)}
                        </span>
                        <button
                          type="button"
                          onClick={() => removeFactor(c)}
                          className="shrink-0 text-slate-400 hover:text-red-500"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </span>
                    ))}
                    <button
                      type="button"
                      onClick={() => setPickerOpen(true)}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-dashed border-blue-300 bg-blue-50/50 text-blue-600 transition hover:border-blue-400 hover:bg-blue-50"
                    >
                      <Plus className="h-5 w-5" />
                    </button>
                  </>
                )}
              </div>
            </section>

            {/* 2. 权重（多因子才显示） */}
            {showSynthesis ? (
            <section>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-bold text-blue-600">2. 因子合成参数设置</h2>
                <div className="flex flex-wrap gap-1.5">
                  {(
                    [
                      { id: "sum" as const, label: "赋权相加" },
                      { id: "product" as const, label: "赋幂相乘" },
                      { id: "custom" as const, label: "自定义组合" },
                    ] as const
                  ).map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setWeightMode(m.id)}
                      className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold ${
                        cfg.weightMode === m.id
                          ? "bg-slate-900 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              {cfg.weightMode !== "custom" ? (
                <div className="overflow-hidden rounded-xl border border-slate-200">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs text-slate-500">
                      <tr>
                        <th className="px-3 py-2.5 font-medium">因子名称</th>
                        <th className="min-w-[5.5rem] px-3 py-2.5 font-medium">
                          {cfg.weightMode === "sum" ? "因子权重" : "幂次"}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {cfg.factorCodes.map((c, i) => (
                        <tr key={c}>
                          <td className="px-3 py-2.5">
                            <div className="font-medium text-slate-800">{factorLabel(c)}</div>
                            <code className="text-xs text-slate-400">{c}</code>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1">
                              <input
                                type="number"
                                min={0}
                                max={cfg.weightMode === "sum" ? 100 : undefined}
                                step={cfg.weightMode === "sum" ? 1 : 0.1}
                                value={cfg.weightMode === "sum" ? (cfg.weights[i] ?? 0) : (cfg.powers[i] ?? 1)}
                                onChange={(e) => {
                                  const v = Number(e.target.value);
                                  if (cfg.weightMode === "sum") {
                                    const weights = [...cfg.weights];
                                    weights[i] = Math.max(0, Math.min(100, v));
                                    patchConfig({ weights });
                                  } else {
                                    const powers = [...cfg.powers];
                                    powers[i] = v;
                                    patchConfig({ powers });
                                  }
                                }}
                                className="min-w-[3.5rem] w-16 rounded border border-slate-200 px-2 py-1 text-right text-sm tabular-nums"
                              />
                              {cfg.weightMode === "sum" && <span className="text-xs text-slate-400">%</span>}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!cfg.factorCodes.length && (
                        <tr>
                          <td colSpan={2} className="px-3 py-6 text-center text-xs text-slate-400">
                            请先在上方添加因子
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-3 py-3 text-xs leading-relaxed text-slate-500">
                  自定义组合：先在上方添加因子（上方「对应函数」会自动出现），右侧只写如何合成已选因子。全新因子请先写入因子库再选。
                  {cfg.factorCodes.length > 0 && (
                    <>
                      {" "}
                      可用：{cfg.factorCodes.map((c) => `self.${c}()`).join("、")}
                    </>
                  )}
                </p>
              )}
            </section>
            ) : null}

            {/* 3. 组合构建 */}
            <section>
              <h2 className="mb-3 text-sm font-bold text-blue-600">
                {showSynthesis ? "3" : "2"}. 组合构建
              </h2>
              <label className="block text-xs text-slate-500">
                组合类型 portfolio_type
                <select
                  value={cfg.portfolioType}
                  onChange={(e) => patchConfig({ portfolioType: e.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                >
                  {PORTFOLIO_TYPE_OPTIONS.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{portfolioHint}</p>
            </section>

            {/* 4. 参数设置 */}
            <section>
              <h2 className="mb-3 text-sm font-bold text-blue-600">
                {showSynthesis ? "4" : "3"}. 参数设置
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <label className={`text-xs text-slate-500 ${cfg.rangeMode === "custom" ? "col-span-2" : ""}`}>
                  回测区间
                  <select
                    value={cfg.rangeMode}
                    onChange={(e) => {
                      const mode = e.target.value as RangeMode;
                      if (mode === "custom") {
                        const fill = defaultCustomRangeDates(cfg.backtestPeriod || "10y");
                        patchConfig({
                          rangeMode: mode,
                          startDate: cfg.startDate || fill.startDate,
                          endDate: cfg.endDate || fill.endDate,
                        });
                      } else {
                        patchConfig({ rangeMode: mode });
                      }
                    }}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  >
                    <option value="period">预设周期</option>
                    <option value="custom">自定义区间</option>
                  </select>
                </label>
                {cfg.rangeMode === "period" ? (
                  <label className="text-xs text-slate-500">
                    预设时长
                    <select
                      value={cfg.backtestPeriod}
                      onChange={(e) => patchConfig({ backtestPeriod: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                    >
                      {DETECT_PERIOD_OPTIONS.map((p) => (
                        <option key={p.code} value={p.code}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <>
                    <label className="text-xs text-slate-500">
                      开始日期
                      <input
                        type="date"
                        value={cfg.startDate}
                        max={cfg.endDate || undefined}
                        onChange={(e) => {
                          const startDate = e.target.value;
                          patchConfig(clampDateRange(startDate, cfg.endDate, "start"));
                        }}
                        className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                      />
                    </label>
                    <label className="text-xs text-slate-500">
                      结束日期
                      <input
                        type="date"
                        value={cfg.endDate}
                        min={cfg.startDate || undefined}
                        onChange={(e) => {
                          const endDate = e.target.value;
                          patchConfig(clampDateRange(cfg.startDate, endDate, "end"));
                        }}
                        className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                      />
                    </label>
                  </>
                )}
                <label className="text-xs text-slate-500">
                  股票池
                  <select
                    value={cfg.universe}
                    onChange={(e) => patchConfig({ universe: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  >
                    {DETECT_UNIVERSE_OPTIONS.map((u) => (
                      <option key={u.code} value={u.code}>
                        {u.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-slate-500">
                  基准指数
                  <select
                    value={cfg.benchmark}
                    onChange={(e) => patchConfig({ benchmark: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  >
                    {DETECT_BENCHMARK_OPTIONS.map((b) => (
                      <option key={b.code} value={b.code}>
                        {b.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-slate-500">
                  因子分组
                  <select
                    value={Math.min(5, Math.max(1, cfg.groups))}
                    onChange={(e) => patchConfig({ groups: Number(e.target.value) })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  >
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n} value={n}>
                        {n} 组
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-slate-500">
                  调仓周期（交易日）
                  <input
                    type="number"
                    min={5}
                    max={60}
                    value={cfg.rebalanceDays}
                    onChange={(e) => patchConfig({ rebalanceDays: Number(e.target.value) || 20 })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  />
                </label>
                <label className="text-xs text-slate-500">
                  佣金率
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    value={cfg.commissionRate}
                    onChange={(e) =>
                      patchConfig({ commissionRate: Number(e.target.value) || 0 })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  />
                </label>
                <label className="text-xs text-slate-500">
                  印花税
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    value={cfg.stampTax}
                    onChange={(e) => patchConfig({ stampTax: Number(e.target.value) || 0 })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  />
                </label>
                <label className="text-xs text-slate-500">
                  滑点率
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    value={cfg.slippageRate}
                    onChange={(e) =>
                      patchConfig({ slippageRate: Number(e.target.value) || 0 })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  />
                </label>
                <label className="col-span-2 text-xs text-slate-500">
                  分析深度
                  <select
                    value={cfg.analysisLevel || "core"}
                    onChange={(e) =>
                      patchConfig({ analysisLevel: e.target.value as AnalysisLevel })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-2 text-sm"
                  >
                    {DETECT_ANALYSIS_LEVEL_OPTIONS.map((o) => (
                      <option key={o.code} value={o.code}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="mt-3 flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={cfg.filterLimitUp}
                    onChange={(e) => patchConfig({ filterLimitUp: e.target.checked })}
                  />
                  过滤涨停
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={cfg.filterSuspended}
                    onChange={(e) => patchConfig({ filterSuspended: e.target.checked })}
                  />
                  过滤停牌
                </label>
              </div>
            </section>
          </div>
        </aside>

        <div className="flex min-h-0 flex-col gap-3">
          <section
            className={`flex min-h-0 flex-[4] flex-col overflow-hidden rounded-xl border bg-white shadow-sm ${
              isDraftMode ? "border-amber-200" : "border-slate-200"
            }`}
          >
            <div
              className={`flex items-center justify-between border-b px-4 py-2 ${
                isDraftMode
                  ? "border-amber-100 bg-amber-50/60"
                  : "border-slate-100"
              }`}
            >
              <span
                className={`text-xs font-semibold ${
                  isDraftMode ? "text-amber-900" : "text-slate-600"
                }`}
              >
                {isDraftMode && draftFactor
                  ? `因子代码 · ${draftFactor.name}`
                  : cfg.weightMode === "custom" || cfg.factorCodes.length > 1
                    ? "因子代码（实现 + 组合）"
                    : "因子代码"}
              </span>
              {cfg.weightMode === "custom" ? (
                <span className="text-[11px] text-slate-400">
                  上方因子实现自动带入 · 请改组合函数
                </span>
              ) : !codeEditable ? (
                <span className="text-[11px] text-slate-400">自动生成 · 只读</span>
              ) : null}
            </div>
            <div className="min-h-0 flex-1 p-2">
              <FactorCodeEditor
                value={unifiedCode}
                onChange={(v) => {
                  if (isDraftMode && draftFactor) {
                    patchConfig({ draftFactor: { ...draftFactor, body: v } });
                  } else if (cfg.weightMode === "custom") {
                    patchConfig({
                      customCombine: extractCustomCombineFromEditor(
                        v,
                        cfg.factorCodes,
                        methodBodies,
                      ),
                    });
                  }
                }}
                readOnly={!codeEditable}
                height="100%"
              />
            </div>
          </section>

          <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
              <span className="text-xs font-semibold text-slate-600">运行日志</span>
              {runError && (
                <button
                  type="button"
                  onClick={() => setRunError(null)}
                  className="text-[11px] text-red-500 hover:underline"
                >
                  清除提示
                </button>
              )}
            </div>
            {runError && (
              <div className="border-b border-red-100 bg-red-50 px-4 py-2.5 text-xs leading-relaxed text-red-700">
                <span className="font-semibold">检测未通过：</span>
                {runError}
                <span className="mt-1 block text-red-500/90">
                  ResearchEngine 返回成功但带 error 时不会跳转报告；请改代码后重新点「进行检测」。
                </span>
              </div>
            )}
            <div className="flex-1 overflow-auto bg-slate-950 px-4 py-3 font-mono text-[12px] leading-relaxed text-slate-200">
              {logs.length === 0 ? (
                <p className="text-slate-500">等待运行…</p>
              ) : (
                logs.map((l, i) => {
                  const isErr = /失败|异常|错误|未通过|无法检测|请先/.test(l);
                  return (
                    <div
                      key={i}
                      className={`whitespace-pre-wrap ${isErr ? "text-red-400" : ""}`}
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

      <FactorPickerModal
        open={pickerOpen}
        selected={cfg.factorCodes}
        onClose={() => setPickerOpen(false)}
        onConfirm={(codes) => {
          applyFactors(codes);
          setPickerOpen(false);
          pushLog(`已选择 ${codes.length} 个因子`);
        }}
      />

      {createOpen ? (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">新建因子</h3>
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <label className="block text-xs text-slate-500">
                因子代码名
                <input
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                中文解释
                <input
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                分类
                <select
                  value={createCategory}
                  onChange={(e) => setCreateCategory(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                >
                  <option value="">请选择</option>
                  {categoryOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              {createErr ? <p className="text-xs text-red-600">{createErr}</p> : null}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmCreateFactor}
                className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
