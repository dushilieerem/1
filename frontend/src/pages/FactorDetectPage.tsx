import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BarChart3, Loader2, Play, Plus, Save, X } from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import { FactorPickerModal } from "@/components/FactorPickerModal";
import {
  buildComboFunction,
  buildYgFactorRequestParts,
  extractEntryName,
  isReBuiltinLib,
  resolveFactorMeta,
} from "@/lib/detectComboCode";
import {
  bodiesForScriptDisplay,
  buildDetectScript,
  parseDetectScript,
  renameComboDef,
  resolveDetectEntryName,
  type DetectScriptBodies,
} from "@/lib/detectScriptSync";
import {
  DETECT_ANALYSIS_LEVEL_OPTIONS,
  DETECT_BENCHMARK_OPTIONS,
  DETECT_GROUP_OPTIONS,
  EXECUTION_TIMING_OPTIONS,
  DETECT_PERIOD_OPTIONS,
  DETECT_UNIVERSE_OPTIONS,
  PORTFOLIO_TYPE_OPTIONS,
  applyDetectRunSnapshotToConfig,
  buildDetectRunUiSnapshot,
  clampDateRange,
  cleanDetectDisplayName,
  defaultCustomRangeDates,
  equalPowers,
  equalWeights,
  formatDetectRunFactorsLabel,
  getProject,
  getRun,
  listDraftFactors,
  listRuns,
  peekProject,
  consumeDetectProjectSeed,
  readDetectRunUiSnapshot,
  resolveBacktestRange,
  saveDetectRun,
  saveProject,
  type AnalysisLevel,
  type ExecutionTiming,
  normalizeDetectGroups,
  normalizeExecutionTiming,
  type DetectProject,
  type DraftDetectFactor,
  type RangeMode,
  type WeightMode,
} from "@/lib/detectStore";
import { buildFactorDetectRequest } from "@/lib/backtestRequests";
import { sourceFromRequest, sourceRequestParts } from "@/lib/detectSource";
import {
  extractMethod,
  factorExplainText,
  factorTitle,
  loadFactors,
  loadLibrarySource,
  renameMethodDef,
  type FactorMeta,
} from "@/lib/factorCatalog";
import {
  listAllUserLibraryFactors,
  userLibraryFactorToMeta,
} from "@/lib/userFactorLibraries";
import {
  emptyFactorBodyTemplate,
  isFormulaPending,
  persistFormulaAfterDetect,
} from "@/lib/factorLifecycle";
import { ygBacktestFactor, type YgBacktestRequest } from "@/lib/ygApi";

export function FactorDetectPage() {
  const { projectId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const snapshotRunId = searchParams.get("runId")?.trim() || "";
  const navigate = useNavigate();
  const [project, setProject] = useState<DetectProject | null | undefined>(() => {
    if (!projectId) return undefined;
    // 带 runId 时先别用缓存项目渲染，否则会先闪「最新配置」再盖成历史快照
    if (snapshotRunId) return undefined;
    const seeded = consumeDetectProjectSeed(projectId);
    if (seeded) return seeded;
    return peekProject(projectId) ?? undefined;
  });
  const [catalog, setCatalog] = useState<FactorMeta[]>([]);
  const [catalogReady, setCatalogReady] = useState(false);
  /** 最终脚本算好前不挂载编辑器，避免空值时闪出灰色 placeholder 示例代码 */
  const [scriptReady, setScriptReady] = useState(false);
  const [methodBodies, setMethodBodies] = useState<string[]>([]);
  /** 右侧脚本里编辑过的自定义因子函数体 */
  const [bodyOverrides, setBodyOverrides] = useState<DetectScriptBodies>({});
  const [scriptText, setScriptText] = useState("");
  const syncOriginRef = useRef<"ui" | "code" | null>(null);
  const parseTimerRef = useRef<number | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [runError, setRunError] = useState<string | null>(null);
  const [savedHint, setSavedHint] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [mobilePane, setMobilePane] = useState<"config" | "code">("config");
  /** 本页最近一次检测 / URL 快照对应的报告 id，供顶栏「检测报告」直达 */
  const [reportRunId, setReportRunId] = useState<string>(snapshotRunId);
  const abortRef = useRef<AbortController | null>(null);
  const tickRef = useRef<number | null>(null);
  /** 因子源码/存根是否已按当前 factorCodes 装完 */
  const [bodiesReady, setBodiesReady] = useState(false);

  const cfg = project?.config;
  const drafts = useMemo(() => listDraftFactors(cfg), [cfg]);
  const draftByName = useMemo(() => {
    const m = new Map<string, DraftDetectFactor>();
    for (const d of drafts) m.set(d.name, d);
    return m;
  }, [drafts]);
  const draftFactor = drafts[0] ?? null;
  /** 仅一个临时因子、无库因子 → 右侧编辑因子体；混合克隆则走组合脚本 */
  const isDraftOnlyMode =
    drafts.length > 0 &&
    (cfg?.factorCodes.length ?? 0) > 0 &&
    (cfg?.factorCodes.every((c) => draftByName.has(c)) ?? false) &&
    (cfg?.factorCodes.length ?? 0) === 1;
  const hasDraft = drafts.length > 0;

  /** 用户库主因子（待写或已写）：chips 不展示自身，多因子时作组合入口名 */
  const primaryUserFactor = useMemo(() => {
    const name = (project?.factorName || "").trim();
    if (!name || name === "combo_factor" || name === "custom_combo" || name === "factor")
      return null;
    if (drafts.some((d) => d.name === name)) return null;
    const meta = catalog.find((f) => f.name === name);
    if (!meta) return null;
    const isUser =
      meta.userLibraryId != null ||
      (meta.library || "").startsWith("user_lib_") ||
      (meta.tags || []).includes("user_library");
    if (!isUser) return null;
    return meta;
  }, [project?.factorName, catalog, drafts]);
  /**
   * 主因子名：目录就绪后以用户库为准；
   * 未就绪时若多因子且含项目名，先按主因子隐藏，避免闪出「自己也在 chips 里」。
   */
  const primaryUserName = useMemo(() => {
    if (primaryUserFactor) return primaryUserFactor.name;
    const name = (project?.factorName || "").trim();
    if (!name || name === "combo_factor" || name === "custom_combo" || name === "factor")
      return null;
    if (drafts.some((d) => d.name === name)) return null;
    if (catalogReady) return null;
    const codes = cfg?.factorCodes || [];
    if (codes.length > 1 && codes.includes(name)) return name;
    return null;
  }, [primaryUserFactor, project?.factorName, drafts, catalogReady, cfg?.factorCodes]);
  const authoringPendingFactor = useMemo(() => {
    if (!primaryUserFactor || !isFormulaPending(primaryUserFactor)) return null;
    return primaryUserFactor;
  }, [primaryUserFactor]);
  const authoringPendingName = authoringPendingFactor?.name ?? null;
  const isAuthoringPending = Boolean(authoringPendingFactor);

  /** 兼容旧逻辑：仅待写单因子（codes 里只有它） */
  const pendingUserFactor = useMemo(() => {
    if (!authoringPendingFactor || !cfg?.factorCodes.length) return null;
    if (cfg.factorCodes.length !== 1) return null;
    if (cfg.factorCodes[0] !== authoringPendingFactor.name) return null;
    return authoringPendingFactor;
  }, [authoringPendingFactor, cfg?.factorCodes]);
  const isPendingUserOnlyMode = Boolean(pendingUserFactor);
  const isEditableSingleMode =
    isDraftOnlyMode || isPendingUserOnlyMode;

  /** 全部为同事 RE 内置：不可增减/改函数 */
  const isBuiltinLockedMode = useMemo(() => {
    if (!cfg?.factorCodes.length || drafts.length || primaryUserFactor) return false;
    if (!catalog.length) return false;
    return cfg.factorCodes.every((c) => {
      const meta = resolveFactorMeta(catalog, c);
      return Boolean(meta && isReBuiltinLib(meta.library) && !isFormulaPending(meta));
    });
  }, [cfg?.factorCodes, catalog, drafts.length, primaryUserFactor]);

  /** 「添加因子」区：不展示用户主因子自身 */
  const chipFactorCodes = useMemo(() => {
    if (!cfg?.factorCodes.length) return [] as string[];
    if (!primaryUserName) return cfg.factorCodes;
    return cfg.factorCodes.filter((c) => c !== primaryUserName);
  }, [cfg?.factorCodes, primaryUserName]);

  /** 参与赋权合成的因子（多因子时） */
  const ingredientCodes = useMemo(() => {
    if (!cfg?.factorCodes.length) return [] as string[];
    if (primaryUserName && cfg.factorCodes.length > 1) {
      return cfg.factorCodes.filter((c) => c !== primaryUserName);
    }
    return cfg.factorCodes;
  }, [cfg?.factorCodes, primaryUserName]);

  const detectEntryName = useMemo(
    () => resolveDetectEntryName(primaryUserName || project?.factorName),
    [primaryUserName, project?.factorName],
  );

  /** 多于 1 个参与合成的因子时显示赋权/赋幂/自定义 */
  const showSynthesis = ingredientCodes.length > 1;

  const pushLog = useCallback((line: string) => {
    const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setLogs((prev) => [...prev.slice(-80), `[${ts}] ${line}`]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setScriptReady(false);
    setScriptText("");
    setBodyOverrides({});
    setBodiesReady(false);
    setCatalogReady(false);
    const cached = peekProject(projectId);
    // 有 runId：等快照合并后再 setProject，避免先闪缓存配置
    if (cached && !snapshotRunId) {
      setProject(cached);
      setLogs((prev) =>
        prev.length
          ? prev
          : [`[${new Date().toLocaleTimeString("zh-CN", { hour12: false })}] 已加载项目：${cached.name}`],
      );
    } else if (!snapshotRunId) {
      setProject(undefined);
    }
    void (async () => {
      const p = await getProject(projectId);
      if (cancelled) return;
      if (!p) {
        setProject(null);
        return;
      }
      setCatalogReady(false);
      let next = p;
      if (snapshotRunId) {
        try {
          const run = await getRun(snapshotRunId);
          if (cancelled) return;
          if (run && run.projectId === p.id) {
            const snap = readDetectRunUiSnapshot(run.request);
            if (snap) {
              next = {
                ...p,
                config: applyDetectRunSnapshotToConfig(p.config, snap),
              };
              const label = formatDetectRunFactorsLabel(run);
              const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
              setLogs((prev) => [
                ...prev.slice(-200),
                `[${ts}] 已加载历史快照：${label}（保存后才会写入项目最新配置）`,
              ]);
            }
            // 运行请求保存了实际执行的源码，不能用现在的库公式覆盖历史。
            next = {
              ...next,
              config: { ...next.config, source: sourceFromRequest(run.request) },
            };
          }
        } catch {
          /* 无快照则仍用项目最新配置 */
        }
      }
      setProject(next);
      if (snapshotRunId) {
        setReportRunId(snapshotRunId);
      } else {
        void listRuns(projectId)
          .then((runs) => {
            if (cancelled || !runs.length) return;
            setReportRunId((prev) => prev || runs[0].id);
          })
          .catch(() => undefined);
      }
      if (!snapshotRunId) {
        const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
        setLogs((prev) =>
          prev.length ? prev : [`[${ts}] 已加载项目：${next.name}`],
        );
      }
      void Promise.all([
        loadFactors().catch(() => [] as FactorMeta[]),
        listAllUserLibraryFactors()
          .then((rows) => rows.map(userLibraryFactorToMeta))
          .catch(() => [] as FactorMeta[]),
      ]).then(([builtin, userFs]) => {
        if (cancelled) return;
        // 保留同名多库（如 wvad∈classic/emotion）；解析时用 resolveFactorMeta 优先 RE 库
        const merged = [
          ...builtin.filter((f) => f.library !== "custom_lib"),
          ...userFs,
        ];
        setCatalog(merged);
        setCatalogReady(true);
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, snapshotRunId]);

  // 已入库的草稿：去掉琥珀色，按普通库因子展示
  useEffect(() => {
    const draftNames = listDraftFactors(project?.config).map((d) => d.name);
    if (!draftNames.length || !catalog.length) return;
    const archived = draftNames.filter((name) =>
      catalog.some(
        (f) => f.name === name && f.library.startsWith("user_lib_"),
      ),
    );
    if (!archived.length) return;
    setProject((prev) => {
      if (!prev) return prev;
      const remain = listDraftFactors(prev.config).filter(
        (d) => !archived.includes(d.name),
      );
      if (remain.length === listDraftFactors(prev.config).length) return prev;
      const codes = prev.config.factorCodes.length
        ? prev.config.factorCodes
        : remain.map((d) => d.name);
      const next = {
        ...prev,
        config: {
          ...prev.config,
          draftFactor: remain[0] || null,
          draftFactors: remain.length ? remain : undefined,
          factorCodes: codes,
          weightMode: remain.length ? prev.config.weightMode : ("sum" as const),
          weights: equalWeights(codes.length),
          powers: equalPowers(codes.length),
        },
      };
      void saveProject(next);
      return next;
    });
  }, [catalog, project?.config?.draftFactor?.name, project?.config?.draftFactors, project?.id]);

  const factorLabel = useCallback(
    (code: string) => {
      const draft = draftByName.get(code);
      if (draft) return draft.description || draft.name;
      const meta = catalog.find((f) => f.name === code);
      if (meta) return factorTitle(meta);
      return code;
    },
    [catalog, draftByName],
  );

  const factorChipTitle = useCallback(
    (code: string) => {
      const draft = draftByName.get(code);
      if (draft) return draft.description || draft.name;
      const meta = catalog.find((f) => f.name === code);
      if (meta) {
        const bits = [factorTitle(meta), meta.displayName, factorExplainText(meta)]
          .filter(Boolean)
          .filter((v, i, arr) => arr.indexOf(v) === i);
        return bits.join(" · ");
      }
      return code;
    },
    [catalog, draftByName],
  );

  useEffect(() => {
    if (isDraftOnlyMode && draftFactor) {
      setMethodBodies([draftFactor.body || ""]);
      setBodiesReady(true);
      return;
    }
    if (isAuthoringPending && authoringPendingFactor && (cfg?.factorCodes.length ?? 0) <= 1) {
      const ov = bodyOverrides[authoringPendingFactor.name]?.trim();
      const body =
        ov ||
        (authoringPendingFactor.body || "").trim() ||
        emptyFactorBodyTemplate(
          authoringPendingFactor.name,
          authoringPendingFactor.description || authoringPendingFactor.name,
        );
      setMethodBodies([body]);
      setBodiesReady(true);
      return;
    }
    if (!cfg?.factorCodes.length) {
      setMethodBodies([]);
      setBodiesReady(true);
      return;
    }
    // 等目录就绪再拉 body，避免先用空 catalog 填错存根
    if (!catalogReady) {
      setBodiesReady(false);
      return;
    }
    let cancelled = false;
    setBodiesReady(false);
    void (async () => {
      try {
        const fs = catalog.length ? catalog : await loadFactors();
        const bodies: string[] = [];
        const fileCache = new Map<string, string>();
        for (const code of cfg.factorCodes) {
          const draft = draftByName.get(code);
          if (draft) {
            bodies.push(draft.body || "");
            continue;
          }
          const meta = resolveFactorMeta(fs, code);
          if (!meta) {
            bodies.push(`# 未找到因子 ${code}`);
            continue;
          }
          if ((meta.body || "").trim()) {
            bodies.push(renameMethodDef(meta.body || "", code));
            continue;
          }
          if (isFormulaPending(meta)) {
            bodies.push(
              emptyFactorBodyTemplate(code, meta.description || code),
            );
            continue;
          }
          if (isReBuiltinLib(meta.library)) {
            // 内置不落可展示源码；占位即可，脚本层 commentsOnly 不会输出
            bodies.push("");
            continue;
          }
          let src = fileCache.get(meta.libraryFile);
          if (!src) {
            src = await loadLibrarySource(meta.libraryFile);
            fileCache.set(meta.libraryFile, src);
          }
          bodies.push(renameMethodDef(extractMethod(src, meta.methodName || code), code));
        }
        if (!cancelled) {
          setMethodBodies(bodies);
          setBodiesReady(true);
        }
      } catch (e) {
        if (!cancelled) {
          setMethodBodies([]);
          setBodiesReady(true);
          pushLog(`加载因子源码失败：${e instanceof Error ? e.message : String(e)}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    cfg?.factorCodes,
    catalog,
    catalogReady,
    pushLog,
    isDraftOnlyMode,
    draftFactor,
    draftByName,
    isAuthoringPending,
    authoringPendingFactor,
    bodyOverrides,
  ]);

  /** 目录就绪后回填 factorLibraries（旧项目 / 历史快照可能没有） */
  useEffect(() => {
    if (!cfg?.factorCodes.length || !catalog.length) return;
    const prev = cfg.factorLibraries || {};
    let changed = false;
    const next: Record<string, string> = { ...prev };
    for (const code of cfg.factorCodes) {
      if (draftByName.has(code)) {
        if (next[code] !== "draft_lib") {
          next[code] = "draft_lib";
          changed = true;
        }
        continue;
      }
      if (next[code]) continue;
      const meta = resolveFactorMeta(catalog, code);
      if (meta?.library) {
        next[code] = meta.library;
        changed = true;
      }
    }
    if (!changed) return;
    setProject((p) =>
      p
        ? { ...p, config: { ...p.config, factorLibraries: next } }
        : p,
    );
  }, [catalog, cfg?.factorCodes, cfg?.factorLibraries, draftByName]);

  const catalogByName = useMemo(
    () => new Map(catalog.map((f) => [f.name, f])),
    [catalog],
  );

  const catalogWithDrafts = useMemo(() => {
    const m = new Map(catalogByName);
    for (const d of drafts) {
      m.set(d.name, {
        name: d.name,
        methodName: d.name,
        description: d.description,
        explain: d.description,
        formula: "",
        params: {},
        library: "draft_lib",
        libraryFile: "",
        libraryLabel: d.category,
        body: d.body,
      });
    }
    return m;
  }, [catalogByName, drafts]);

  /** 左侧改配置 → 重建右侧脚本（右侧正在编辑时跳过） */
  useEffect(() => {
    if (!cfg) return;
    if (syncOriginRef.current === "code") {
      syncOriginRef.current = null;
      return;
    }
    // 目录/源码未齐：不挂编辑器、不写中间脚本
    if (!catalogReady || !bodiesReady) {
      setScriptReady(false);
      return;
    }
    const commitScript = (text: string) => {
      setScriptText(text);
      setScriptReady(true);
    };
    if (cfg.source !== undefined) {
      commitScript(cfg.source.code);
      return;
    }
    if (isDraftOnlyMode && draftFactor) {
      commitScript(draftFactor.body || "");
      return;
    }
    // 内置锁定：只展示注释
    if (isBuiltinLockedMode) {
      commitScript(
        buildDetectScript({
          config: cfg,
          catalogByName: catalogWithDrafts,
          commentsOnly: true,
          omitCombo: true,
        }),
      );
      return;
    }
    // 用户主因子单独编辑（未再选其它因子）
    if (
      primaryUserFactor &&
      (cfg.factorCodes.length === 0 ||
        (cfg.factorCodes.length === 1 &&
          cfg.factorCodes[0] === primaryUserFactor.name))
    ) {
      const primary = primaryUserFactor.name;
      const ov = bodyOverrides[primary]?.trim();
      const idx = cfg.factorCodes.indexOf(primary);
      const body =
        ov ||
        (idx >= 0 ? methodBodies[idx] : "") ||
        methodBodies[0] ||
        (primaryUserFactor.body || "").trim() ||
        emptyFactorBodyTemplate(
          primary,
          primaryUserFactor.description || primary,
        );
      commitScript(body);
      return;
    }

    const codes = [...(cfg.factorCodes || [])];
    if (primaryUserName && !codes.includes(primaryUserName)) {
      codes.push(primaryUserName);
    }
    const ordered = primaryUserName
      ? [...codes.filter((c) => c !== primaryUserName), primaryUserName]
      : codes;
    const ingredients = primaryUserName
      ? ordered.filter((c) => c !== primaryUserName)
      : ordered;
    const bodies = bodiesForScriptDisplay({
      factorCodes: ordered,
      catalogByName: catalogWithDrafts,
      methodBodies: ordered.map((c) => {
        const i = cfg.factorCodes.indexOf(c);
        return bodyOverrides[c]?.trim() || methodBodies[i] || "";
      }),
      overrides: bodyOverrides,
    });
    commitScript(
      buildDetectScript({
        config: { ...cfg, factorCodes: ordered },
        projectName: cleanDetectDisplayName(
          project?.description || project?.name || "",
          project?.factorName || "",
        ),
        catalogByName: catalogWithDrafts,
        factorBodies: bodies,
        entryName: detectEntryName,
        ingredientCodes: ingredients,
        omitCombo: ingredients.length === 0,
      }),
    );
  }, [
    cfg,
    catalogWithDrafts,
    methodBodies,
    bodyOverrides,
    isDraftOnlyMode,
    draftFactor,
    isBuiltinLockedMode,
    primaryUserFactor,
    primaryUserName,
    detectEntryName,
    catalogReady,
    bodiesReady,
    project?.name,
    project?.description,
    project?.factorName,
  ]);

  const patchConfig = (partial: Partial<NonNullable<DetectProject["config"]>>) => {
    syncOriginRef.current = "ui";
    setProject((prev) => {
      if (!prev) return prev;
      const formulaChanged = ["weights", "powers", "customCombine", "factorCodes", "weightMode"]
        .some((key) => key in partial);
      return {
        ...prev,
        config: { ...prev.config, ...partial, ...(formulaChanged ? { source: undefined } : {}) },
      };
    });
  };

  const onScriptChange = (v: string) => {
    setScriptText(v);
    const libs = [...new Set((cfg?.factorCodes || [])
      .map((c) => cfg?.factorLibraries?.[c] || resolveFactorMeta(catalog, c)?.library)
      .filter((lib): lib is string => Boolean(lib && isReBuiltinLib(lib))))];
    setProject((prev) => prev ? {
      ...prev,
      config: {
        ...prev.config,
        source: {
          code: v,
          name: prev.config.source?.name || detectEntryName,
          library: prev.config.source?.library ?? (libs.length ? libs : undefined),
        },
      },
    } : prev);
    if (isDraftOnlyMode && draftFactor) {
      syncOriginRef.current = "code";
      setProject((prev) => {
        if (!prev) return prev;
        const remain = listDraftFactors(prev.config).map((d) =>
          d.name === draftFactor.name ? { ...d, body: v } : d,
        );
        return {
          ...prev,
          config: {
            ...prev.config,
            draftFactor: remain[0] || null,
            draftFactors: remain.length ? remain : undefined,
          },
        };
      });
      return;
    }
    if (primaryUserFactor) {
      syncOriginRef.current = "code";
      const primary = primaryUserFactor.name;
      if (cfg && ingredientCodes.length > 1) {
        const parsed = parseDetectScript(v, detectEntryName);
        if (parsed) {
          setBodyOverrides((prev) => ({ ...prev, ...parsed.factorBodies }));
          if (parsed.comboFn) {
            setProject((prev) => {
              if (!prev) return prev;
              if (prev.config.weightMode !== "custom") return prev;
              return {
                ...prev,
                config: {
                  ...prev.config,
                  customCombine: renameComboDef(parsed.comboFn!, detectEntryName),
                },
              };
            });
          }
          const bodies = (cfg.factorCodes || []).map(
            (c) => parsed.factorBodies[c] || bodyOverrides[c] || "",
          );
          setMethodBodies(bodies);
        }
        return;
      }
      setMethodBodies([v]);
      setBodyOverrides((prev) => ({
        ...prev,
        [primary]: v,
      }));
      return;
    }
    if (parseTimerRef.current) window.clearTimeout(parseTimerRef.current);
    parseTimerRef.current = window.setTimeout(() => {
      const parsed = parseDetectScript(v, detectEntryName);
      if (!parsed) return;
      syncOriginRef.current = "code";
      if (Object.keys(parsed.factorBodies).length) {
        setBodyOverrides((prev) => ({ ...prev, ...parsed.factorBodies }));
        // 同步写回临时草稿 body，保证再跑检测用最新代码
        setProject((prev) => {
          if (!prev) return prev;
          const cur = listDraftFactors(prev.config);
          if (!cur.length) return prev;
          let changed = false;
          const nextDrafts = cur.map((d) => {
            const body = parsed.factorBodies[d.name];
            if (body == null) return d;
            changed = true;
            return { ...d, body };
          });
          if (!changed) return prev;
          return {
            ...prev,
            config: {
              ...prev.config,
              draftFactor: nextDrafts[0] || null,
              draftFactors: nextDrafts,
            },
          };
        });
      }
      // 自定义组合模式下，右侧改入口函数写回左侧
      if (parsed.comboFn) {
        setProject((prev) => {
          if (!prev) return prev;
          if (prev.config.weightMode !== "custom") return prev;
          return {
            ...prev,
            config: {
              ...prev.config,
              customCombine: renameComboDef(parsed.comboFn!, detectEntryName),
            },
          };
        });
      }
    }, 320);
  };

  const applyFactors = (
    codes: string[],
    libraries?: Record<string, string>,
  ) => {
    syncOriginRef.current = "ui";
    setProject((prev) => {
      if (!prev) return prev;
      let nextCodes = [...codes];
      const pin = primaryUserName;
      if (pin) {
        nextCodes = nextCodes.filter((c) => c !== pin);
        nextCodes.push(pin);
      }
      const mode = prev.config.weightMode;
      let weights: number[];
      let powers: number[];
      if (mode === "sum") {
        if (pin && nextCodes.length > 1) {
          weights = [...equalWeights(nextCodes.length - 1), 0];
        } else {
          weights = equalWeights(nextCodes.length);
        }
      } else {
        weights = nextCodes.map((_, i) => prev.config.weights[i] ?? 0);
      }
      if (mode === "product") {
        if (pin && nextCodes.length > 1) {
          powers = [...equalPowers(nextCodes.length - 1), 1];
        } else {
          powers = equalPowers(nextCodes.length);
        }
      } else {
        powers = nextCodes.map((_, i) => prev.config.powers[i] ?? 1);
      }
      const entry = resolveDetectEntryName(pin || (nextCodes.length === 1 ? nextCodes[0] : "factor"));
      let customCombine = renameComboDef(prev.config.customCombine, entry);
      if (mode === "custom" && nextCodes.length) {
        const ingredients = pin
          ? nextCodes.filter((c) => c !== pin)
          : nextCodes;
        const mentionsAny = ingredients.some((c) =>
          customCombine.includes(`self.${c}()`),
        );
        if (!mentionsAny) {
          const label = cleanDetectDisplayName(
            prev.description || prev.name,
            entry,
          );
          if (ingredients.length === 1) {
            customCombine = `def ${entry}(self):\n    """${label}"""\n    return self.${ingredients[0]}()`;
          } else if (ingredients.length > 1) {
            const expr = ingredients.map((c) => `self.${c}()`).join(" * ");
            customCombine = `def ${entry}(self):\n    """${label} · 自定义组合"""\n    return ${expr}`;
          } else {
            customCombine = `def ${entry}(self):\n    """${label}"""\n    return self.close.pct_change(5)`;
          }
        }
      }
      const remain = listDraftFactors(prev.config).filter((d) =>
        nextCodes.includes(d.name),
      );
      const prevLibs = prev.config.factorLibraries || {};
      const factorLibraries: Record<string, string> = {};
      for (const code of nextCodes) {
        const draft = remain.find((d) => d.name === code);
        if (draft) {
          factorLibraries[code] = "draft_lib";
          continue;
        }
        const lib =
          libraries?.[code] ||
          prevLibs[code] ||
          resolveFactorMeta(catalog, code)?.library ||
          "";
        if (lib) factorLibraries[code] = lib;
      }
      return {
        ...prev,
        factorName: pin || (nextCodes.length === 1 ? nextCodes[0] : entry),
        config: {
          ...prev.config,
          factorCodes: nextCodes,
          source: undefined,
          factorLibraries,
          weights,
          powers,
          customCombine,
          draftFactor: remain[0] || null,
          draftFactors: remain.length ? remain : undefined,
        },
      };
    });
  };

  const removeFactor = (code: string) => {
    if (!cfg) return;
    if (isBuiltinLockedMode) return;
    if (primaryUserName && code === primaryUserName) return;
    if (draftByName.has(code) && isDraftOnlyMode) {
      setProject((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          factorName: "combo_factor",
          config: {
            ...prev.config,
            factorCodes: [],
            source: undefined,
            weights: [],
            powers: [],
            draftFactor: null,
            draftFactors: undefined,
          },
        };
      });
      return;
    }
    applyFactors(cfg.factorCodes.filter((c) => c !== code));
  };

  const setWeightMode = (mode: WeightMode) => {
    syncOriginRef.current = "ui";
    setProject((prev) => {
      if (!prev) return prev;
      const codes = prev.config.factorCodes;
      const pin = primaryUserName;
      const ingredients =
        pin && codes.length > 1 ? codes.filter((c) => c !== pin) : codes;
      const entry = resolveDetectEntryName(
        pin || (codes.length === 1 ? codes[0] : "factor"),
      );
      let customCombine = prev.config.customCombine;
      if (mode === "custom") {
        if (ingredients.length === 1) {
          customCombine = `def ${entry}(self):\n    """自定义组合"""\n    return self.${ingredients[0]}()`;
        } else if (ingredients.length > 1) {
          const expr = ingredients.map((c) => `self.${c}()`).join(" + ");
          customCombine = `def ${entry}(self):\n    """自定义组合"""\n    return ${expr}`;
        } else {
          customCombine = `def ${entry}(self):\n    """自定义组合"""\n    # 先在左侧添加因子\n    return self.close.pct_change(5)`;
        }
      }
      // 赋权只均分「成分因子」，主因子占位权重为 0（避免 2 个成分显示成 33.3）
      let weights = prev.config.weights;
      let powers = prev.config.powers;
      if (mode === "sum") {
        if (pin && ingredients.length > 0) {
          const ew = equalWeights(ingredients.length);
          weights = codes.map((c) => {
            const ii = ingredients.indexOf(c);
            return ii >= 0 ? ew[ii] : 0;
          });
        } else {
          weights = equalWeights(codes.length);
        }
      }
      if (mode === "product") {
        if (pin && ingredients.length > 0) {
          powers = codes.map((c) => (ingredients.includes(c) ? 1 : 1));
        } else {
          powers = equalPowers(codes.length);
        }
      }
      return {
        ...prev,
        config: {
          ...prev.config,
          weightMode: mode,
          source: undefined,
          weights,
          powers,
          customCombine,
        },
      };
    });
  };

  const persist = async () => {
    if (!project) return;
    try {
      if (!isBuiltinLockedMode) {
        sourceRequestParts({ code: scriptText, name: cfg?.source?.name || detectEntryName });
      }
      if (primaryUserFactor?.userLibraryId != null &&
          primaryUserFactor.userLibraryFactorId != null &&
          (cfg?.factorCodes.length ?? 0) <= 1) {
        const updated = await persistFormulaAfterDetect({
          libraryId: primaryUserFactor.userLibraryId,
          factorId: primaryUserFactor.userLibraryFactorId,
          body: scriptText,
          description: primaryUserFactor.description,
        });
        setCatalog((prev) => prev.map((f) =>
          f.userLibraryFactorId === updated.id ? userLibraryFactorToMeta(updated) : f,
        ));
      }
      const saved = await saveProject(project);
      setProject(saved);
      setSavedHint("已保存");
      window.setTimeout(() => setSavedHint(""), 1500);
      pushLog("代码与项目配置已保存");
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
    }
  };

  const onRun = useCallback(async () => {
    if (!project || !cfg) return;
    setRunError(null);
    if (!scriptReady || !catalogReady) return;
    let sourceParts;
    try {
      if (cfg.source !== undefined) sourceParts = sourceRequestParts(cfg.source);
      else if (!isBuiltinLockedMode && !scriptText.trim()) {
        throw new Error("因子代码不能为空，请编写代码后再检测");
      }
      if (!sourceParts) {
        const missing = cfg.factorCodes.find((code) =>
          !listDraftFactors(cfg).some((d) => d.name === code) && !resolveFactorMeta(catalog, code),
        );
        if (missing) {
          throw new Error(`因子「${missing}」已删除或不可用，且没有可执行的历史代码快照，请重新添加因子`);
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setRunError(msg);
      pushLog(msg);
      return;
    }
    const runDrafts = listDraftFactors(cfg);
    const draftOnly =
      runDrafts.length === 1 &&
      cfg.factorCodes.length === 1 &&
      cfg.factorCodes[0] === runDrafts[0].name;
    const pendingOnly =
      !runDrafts.length &&
      cfg.factorCodes.length === 1 &&
      (() => {
        const meta = resolveFactorMeta(catalog, cfg.factorCodes[0]);
        return Boolean(meta && isFormulaPending(meta));
      })();
    const singleEditable = draftOnly || pendingOnly;
    const customOnly =
      cfg.weightMode === "custom" && Boolean(cfg.customCombine?.trim());
    if (!cfg.factorCodes.length && !customOnly && !runDrafts.length) {
      const msg = "请先在上方添加因子，或使用自定义组合函数";
      setRunError(msg);
      pushLog(msg);
      return;
    }
    for (const d of sourceParts ? [] : runDrafts) {
      if (!(d.body || "").trim()) {
        const msg = `请先编写因子代码：${d.name}`;
        setRunError(msg);
        pushLog(msg);
        return;
      }
    }
    for (const code of sourceParts ? [] : cfg.factorCodes) {
      if (runDrafts.some((d) => d.name === code)) continue;
      const meta = resolveFactorMeta(catalog, code);
      if (!meta || !isFormulaPending(meta)) continue;
      const idx = cfg.factorCodes.indexOf(code);
      const body = (
        bodyOverrides[code]?.trim() ||
        methodBodies[idx] ||
        meta.body ||
        ""
      ).trim();
      if (!body) {
        const msg = `请先编写因子代码：${code}`;
        setRunError(msg);
        pushLog(msg);
        return;
      }
    }
    const catalogForBuild: FactorMeta[] = [
      ...catalog,
      ...runDrafts.map((draft) => ({
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
      })),
    ];
    const codes = cfg.factorCodes.length
      ? cfg.factorCodes
      : runDrafts.map((d) => d.name);
    const bodiesForBuild = codes.map((code, i) => {
      const ov = bodyOverrides[code]?.trim();
      if (ov) return ov;
      const draft = runDrafts.find((d) => d.name === code);
      if (draft) return draft.body || "";
      return methodBodies[i] || "";
    });
    const entry = resolveDetectEntryName(
      primaryUserName || project.factorName || (codes.length === 1 ? codes[0] : "factor"),
    );
    const ingredients =
      primaryUserName && codes.length > 1
        ? codes.filter((c) => c !== primaryUserName)
        : codes;
    const comboCodes = singleEditable
      ? codes
      : ingredients.length
        ? ingredients
        : codes;
    const comboWeights = singleEditable
      ? [100]
      : comboCodes.map((c) => {
          const i = codes.indexOf(c);
          return i >= 0 ? Number(cfg.weights[i] ?? 0) : 0;
        });
    const comboPowers = singleEditable
      ? [1]
      : comboCodes.map((c) => {
          const i = codes.indexOf(c);
          return i >= 0 ? Number(cfg.powers[i] ?? 1) : 1;
        });
    const combo = buildComboFunction({
      mode: singleEditable ? "sum" : cfg.weightMode,
      factorCodes: comboCodes,
      weights: comboWeights,
      powers: comboPowers,
      customCombine: renameComboDef(cfg.customCombine, entry),
      entryName: entry,
      title: cleanDetectDisplayName(
        project.description || project.name || project.factorName,
        project.factorName,
      ),
    });
    const entryName = extractEntryName(combo, entry);
    const parts = sourceParts ?? buildYgFactorRequestParts({
      factors: catalogForBuild,
      factorCodes: codes,
      methodBodies: bodiesForBuild,
      comboFn: combo,
      entryName,
      preferredLibraries: {
        ...(cfg.factorLibraries || {}),
        ...Object.fromEntries(runDrafts.map((d) => [d.name, "draft_lib"])),
      },
    });
    // 内置因子：必须已带 library_name；缺库名宁可不发，避免空 UserFactorLibrary
    for (const code of sourceParts ? [] : codes) {
      if (runDrafts.some((d) => d.name === code)) continue;
      const lib =
        cfg.factorLibraries?.[code] ||
        resolveFactorMeta(catalogForBuild, code)?.library;
      if (!lib) {
        const msg = `因子「${code}」信息未就绪，请稍候再测，或重新添加该因子`;
        setRunError(msg);
        pushLog(msg);
        return;
      }
      if (isReBuiltinLib(lib) && !parts.library_name) {
        const msg = `因子「${code}」无法提交，请重新添加后再检测`;
        setRunError(msg);
        pushLog(msg);
        return;
      }
    }
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
    pushLog("开始检测…");
    const factorLabel = parts.factor_name || "当前组合";
    pushLog(
      parts.library_name
        ? `检测因子：${factorLabel}`
        : `检测因子：${factorLabel}（自定义代码）`,
    );
    try {
      await saveProject(project);
      const { start, end } = resolveBacktestRange(cfg);
      const req = buildFactorDetectRequest(cfg, parts, { start, end });
      const depthLabel =
        req.analysis_level === "full" ? "全量检测" : "快速检测";
      const poolLabel =
        cfg.universe === "CSI300"
          ? "沪深300"
          : cfg.universe === "CSI500"
            ? "中证500"
            : cfg.universe === "CSI800"
              ? "中证800"
              : cfg.universe === "CSI1000"
                ? "中证1000"
                : cfg.universe === "SSE50"
                  ? "上证50"
                  : cfg.universe === "ALL"
                    ? "全A"
                    : String(cfg.universe || "");
      pushLog(`回测区间 ${start} → ${end} · 股票池 ${poolLabel} · ${depthLabel}`);
      const res = await ygBacktestFactor(req, ac.signal, {
        onQueued: () => pushLog("准备中，请稍候…"),
        onStarted: () => pushLog("正在检测，请稍候…"),
      });
      const elapsedSec = Math.floor((Date.now() - t0) / 1000);
      if (res.error) {
        const msg = res.error;
        setRunError(msg);
        pushLog(`检测未通过：${msg}`);
        pushLog("请检查因子代码或参数后重试");
        return;
      }
      const primaryDraft = runDrafts[0] || null;
      const saveReq = {
        ...req,
        _svquant_ui: buildDetectRunUiSnapshot(cfg, (code) => {
          const draft = runDrafts.find((d) => d.name === code);
          if (draft) return (draft.description || draft.name).trim() || code;
          return code;
        }),
        ...(primaryDraft ? { _svquantDraftFactor: primaryDraft } : {}),
        ...(runDrafts.length ? { _svquantDraftFactors: runDrafts } : {}),
      } as YgBacktestRequest & {
        _svquant_ui: ReturnType<typeof buildDetectRunUiSnapshot>;
        _svquantDraftFactor?: DraftDetectFactor;
        _svquantDraftFactors?: DraftDetectFactor[];
      };
      const factorLabelSaved = formatDetectRunFactorsLabel({
        description: "",
        factorName: parts.factor_name || "",
        request: saveReq,
      });
      const rec = await saveDetectRun({
        projectId: project.id,
        factorName: parts.factor_name,
        description: factorLabelSaved || project.name,
        request: saveReq,
        result: res,
        finishedAt: new Date().toISOString(),
        elapsedSec,
        draftFactor: primaryDraft,
        draftFactors: runDrafts.length ? runDrafts : undefined,
      });
      setReportRunId(rec.id);
      // 再次落盘配置，保证下次从因子库点检测仍能看到已选成分因子
      try {
        await saveProject(project);
      } catch {
        /* ignore */
      }
      // 用户库空公式：检测成功后回写正文
      for (let i = 0; i < codes.length; i++) {
        const code = codes[i];
        if (runDrafts.some((d) => d.name === code)) continue;
        const meta = resolveFactorMeta(catalog, code);
        if (
          !meta ||
          meta.userLibraryId == null ||
          meta.userLibraryFactorId == null ||
          !isFormulaPending(meta)
        ) {
          continue;
        }
        const body = (bodiesForBuild[i] || "").trim();
        if (!body) continue;
        try {
          const updated = await persistFormulaAfterDetect({
            libraryId: meta.userLibraryId,
            factorId: meta.userLibraryFactorId,
            body,
            description: meta.description || code,
          });
          setCatalog((prev) =>
            prev.map((f) =>
              f.userLibraryFactorId === updated.id
                ? userLibraryFactorToMeta(updated)
                : f,
            ),
          );
          pushLog(`已将公式写入因子库：${code}`);
        } catch (e) {
          pushLog(
            `公式回写失败（${code}）：${e instanceof Error ? e.message : String(e)}`,
          );
        }
      }
      pushLog(`检测完成（用时 ${elapsedSec} 秒），正在打开报告…`);
      // 跑完回到「最新配置」路由，去掉历史 runId
      if (snapshotRunId) {
        navigate(`/factor/detect/report/${rec.id}`, { replace: false });
      } else {
        navigate(`/factor/detect/report/${rec.id}`);
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        pushLog("已取消检测");
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        // 旧版 localStorage 配额错误：给可操作提示
        if (/quota|setItem|Storage/i.test(msg)) {
          const tip =
            "浏览器本地缓存已满。请刷新页面后再点一次检测。";
          setRunError(tip);
          pushLog(tip);
          try {
            localStorage.removeItem("svquant_detect_runs_v2");
          } catch {
            /* ignore */
          }
        } else {
          // 用户可见：去掉路径/端口等开发细节
          const friendly = msg
            .replace(/POST\s+\/yg-api\/\S+/gi, "计算服务")
            .replace(/\/api\/\S+/g, "接口")
            .replace(/:8766|:9527|ResearchEngine|\bRE\b/gi, "计算服务")
            .replace(/HTTP\s+/gi, "");
          setRunError(friendly);
          pushLog(`检测未通过：${friendly}`);
        }
      }
    } finally {
      if (tickRef.current) window.clearInterval(tickRef.current);
      setRunning(false);
      setElapsed(Math.floor((Date.now() - t0) / 1000));
    }
  }, [project, cfg, methodBodies, bodyOverrides, catalog, navigate, pushLog, snapshotRunId, primaryUserName, scriptText, scriptReady, catalogReady, isBuiltinLockedMode]);

  if (project === undefined) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center bg-[#f0f2f5] text-slate-600">
        <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-slate-200 border-t-red-600" />
        <p className="mt-3 text-sm">正在加载检测项目…</p>
      </div>
    );
  }

  if (!project || !cfg) {
    return (
      <div className="p-10 text-center">
        <p className="text-slate-600">项目不存在</p>
        <Link to="/factor/detect" className="mt-3 inline-block text-blue-600 underline">
          返回检测报告
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col bg-[#f0f2f5] lg:h-[calc(100vh-4rem)]">
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-white px-3 py-2.5 sm:px-4">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between lg:gap-3">
          <div className="flex min-w-0 items-center gap-2 text-sm">
            <Link
              to="/factor/detect"
              className="shrink-0 text-slate-500 hover:text-slate-800"
            >
              检测报告
            </Link>
            <span className="shrink-0 text-slate-300">/</span>
            <span className="min-w-0 truncate font-semibold text-slate-900" title={project.name}>
              {project.name}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 lg:flex lg:flex-wrap lg:items-center">
            <button
              type="button"
              onClick={persist}
              className="inline-flex items-center justify-center gap-1 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 lg:py-1.5"
            >
              <Save className="h-3.5 w-3.5 shrink-0" />
              保存{savedHint ? ` · ${savedHint}` : ""}
            </button>
            <button
              type="button"
              disabled={
                running ||
                (!cfg.factorCodes.length &&
                  !(cfg.weightMode === "custom" && cfg.customCombine?.trim()))
              }
              onClick={() => void onRun()}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 lg:py-1.5"
            >
              {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              {running ? `检测中 ${elapsed}s` : "进行检测"}
            </button>
            <button
              type="button"
              onClick={() => {
                if (reportRunId) {
                  navigate(`/factor/detect/report/${reportRunId}`);
                  return;
                }
                void listRuns(projectId)
                  .then((runs) => {
                    if (runs[0]?.id) {
                      setReportRunId(runs[0].id);
                      navigate(`/factor/detect/report/${runs[0].id}`);
                      return;
                    }
                    window.alert("暂无检测报告，请先点「进行检测」。");
                  })
                  .catch((e) => {
                    window.alert(e instanceof Error ? e.message : String(e));
                  });
              }}
              className={`inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 lg:py-1.5 ${
                running ? "" : "col-span-2 lg:col-span-1"
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              <span className="lg:hidden">报告</span>
              <span className="hidden lg:inline">检测报告</span>
            </button>
            {running ? (
              <button
                type="button"
                onClick={() => abortRef.current?.abort()}
                className="inline-flex items-center justify-center rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 lg:py-1.5"
              >
                取消检测
              </button>
            ) : null}
          </div>
        </div>
      </div>

      <nav
        className="flex gap-1.5 border-b border-slate-200 bg-white px-3 py-2 lg:hidden"
        aria-label="工作台分区"
      >
        {(
          [
            { id: "config" as const, label: "配置" },
            { id: "code" as const, label: "脚本与日志" },
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

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[1.35fr_0.65fr]">
        <aside
          className={`min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm ${
            mobilePane === "config" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4 text-sm sm:px-5 sm:py-5">
            {/* 1. 添加因子 / 当前内置因子 */}
            <section>
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 className="text-sm font-bold text-blue-600">
                  {isBuiltinLockedMode ? "1. 当前内置因子" : "1. 添加因子"}
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                {isDraftOnlyMode && draftFactor ? (
                  <span
                    className="inline-flex w-full max-w-full items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs shadow-sm sm:w-auto sm:max-w-[min(100%,20rem)]"
                    title={draftFactor.name}
                  >
                    <code className="min-w-0 flex-1 truncate font-medium text-amber-900">
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
                  chipFactorCodes.map((c) => {
                    const draft = draftByName.get(c);
                    const meta = catalog.find((f) => f.name === c);
                    const pending = meta ? isFormulaPending(meta) : false;
                    if (draft || pending) {
                      return (
                        <span
                          key={c}
                          className="inline-flex w-full max-w-full items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs shadow-sm sm:w-auto sm:max-w-[min(100%,20rem)]"
                          title={c}
                        >
                          <code className="min-w-0 flex-1 truncate font-medium text-amber-900">
                            {c}
                          </code>
                          {!isBuiltinLockedMode ? (
                            <button
                              type="button"
                              onClick={() => removeFactor(c)}
                              className="shrink-0 text-amber-600 hover:text-red-500"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          ) : null}
                        </span>
                      );
                    }
                    return (
                      <span
                        key={c}
                        className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-sm sm:max-w-[14rem]"
                        title={factorChipTitle(c)}
                      >
                        <span className="truncate font-medium text-slate-800">
                          {factorLabel(c)}
                        </span>
                        {!isBuiltinLockedMode ? (
                          <button
                            type="button"
                            onClick={() => removeFactor(c)}
                            className="shrink-0 text-slate-400 hover:text-red-500"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        ) : null}
                      </span>
                    );
                  })
                )}
                {!isBuiltinLockedMode ? (
                  <button
                    type="button"
                    onClick={() => setPickerOpen(true)}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-dashed border-blue-300 bg-blue-50/50 text-blue-600 transition hover:border-blue-400 hover:bg-blue-50"
                    title="添加因子"
                  >
                    <Plus className="h-5 w-5" />
                  </button>
                ) : null}
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
                      {ingredientCodes.map((c) => {
                        const i = cfg.factorCodes.indexOf(c);
                        return (
                        <tr key={c}>
                          <td className="px-3 py-2.5">
                            <div className="font-medium text-slate-800">{factorLabel(c)}</div>
                            <div className="truncate text-xs text-slate-400" title={factorChipTitle(c)}>
                              {catalog.find((f) => f.name === c)?.displayName || c}
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1">
                              <input
                                type="number"
                                min={0}
                                max={cfg.weightMode === "sum" ? 100 : undefined}
                                step={cfg.weightMode === "sum" ? 1 : 0.1}
                                value={
                                  cfg.weightMode === "sum"
                                    ? (cfg.weights[i] ?? 0)
                                    : (cfg.powers[i] ?? 1)
                                }
                                onChange={(e) => {
                                  const v = Number(e.target.value);
                                  if (i < 0) return;
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
                        );
                      })}
                      {!ingredientCodes.length && (
                        <tr>
                          <td colSpan={2} className="px-3 py-6 text-center text-xs text-slate-400">
                            请先在上方添加因子
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </section>
            ) : null}

            {/* 3. 组合构建 */}
            <section>
              <h2 className="mb-3 text-sm font-bold text-blue-600">
                {showSynthesis ? "3" : "2"}. 组合构建
              </h2>
              <label className="block text-xs text-slate-500">
                组合类型
                <span className="ml-1 hidden font-mono text-[10px] text-slate-400 sm:inline">
                  portfolio_type
                </span>
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
            </section>

            {/* 4. 参数设置 */}
            <section>
              <h2 className="mb-3 text-sm font-bold text-blue-600">
                {showSynthesis ? "4" : "3"}. 参数设置
              </h2>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <label className={`block min-w-0 text-xs text-slate-500 ${cfg.rangeMode === "custom" ? "lg:col-span-2" : ""}`}>
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
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  >
                    <option value="period">预设周期</option>
                    <option value="custom">自定义区间</option>
                  </select>
                </label>
                {cfg.rangeMode === "period" ? (
                  <label className="block min-w-0 text-xs text-slate-500">
                    预设时长
                    <select
                      value={cfg.backtestPeriod}
                      onChange={(e) => patchConfig({ backtestPeriod: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
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
                    <label className="block min-w-0 text-xs text-slate-500">
                      开始日期
                      <input
                        type="date"
                        value={cfg.startDate}
                        max={cfg.endDate || undefined}
                        onChange={(e) => {
                          const startDate = e.target.value;
                          patchConfig(clampDateRange(startDate, cfg.endDate, "start"));
                        }}
                        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                      />
                    </label>
                    <label className="block min-w-0 text-xs text-slate-500">
                      结束日期
                      <input
                        type="date"
                        value={cfg.endDate}
                        min={cfg.startDate || undefined}
                        onChange={(e) => {
                          const endDate = e.target.value;
                          patchConfig(clampDateRange(cfg.startDate, endDate, "end"));
                        }}
                        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                      />
                    </label>
                  </>
                )}
                <label className="block min-w-0 text-xs text-slate-500">
                  股票池
                  <select
                    value={cfg.universe}
                    onChange={(e) => patchConfig({ universe: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  >
                    {DETECT_UNIVERSE_OPTIONS.map((u) => (
                      <option key={u.code} value={u.code}>
                        {u.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block min-w-0 text-xs text-slate-500">
                  基准指数
                  <select
                    value={cfg.benchmark}
                    onChange={(e) => patchConfig({ benchmark: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  >
                    {DETECT_BENCHMARK_OPTIONS.map((b) => (
                      <option key={b.code} value={b.code}>
                        {b.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block min-w-0 text-xs text-slate-500">
                  因子分组
                  <select
                    value={normalizeDetectGroups(cfg.groups)}
                    onChange={(e) => patchConfig({ groups: Number(e.target.value) })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  >
                    {DETECT_GROUP_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n} 组
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block min-w-0 text-xs text-slate-500">
                  调仓周期（交易日）
                  <input
                    type="number"
                    min={5}
                    max={60}
                    value={cfg.rebalanceDays}
                    onChange={(e) => patchConfig({ rebalanceDays: Number(e.target.value) || 1 })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  />
                </label>
                <label className="block min-w-0 text-xs text-slate-500">
                  佣金率
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    value={cfg.commissionRate}
                    onChange={(e) =>
                      patchConfig({ commissionRate: Number(e.target.value) || 0 })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  />
                </label>
                <label className="block min-w-0 text-xs text-slate-500">
                  印花税
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    value={cfg.stampTax}
                    onChange={(e) => patchConfig({ stampTax: Number(e.target.value) || 0 })}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  />
                </label>
                <label className="block min-w-0 text-xs text-slate-500">
                  滑点率
                  <input
                    type="number"
                    step="0.0001"
                    min={0}
                    value={cfg.slippageRate}
                    onChange={(e) =>
                      patchConfig({ slippageRate: Number(e.target.value) || 0 })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  />
                </label>
                <label className="block min-w-0 text-xs text-slate-500 lg:col-span-2">
                  分析深度
                  <select
                    value={cfg.analysisLevel || "core"}
                    onChange={(e) =>
                      patchConfig({ analysisLevel: e.target.value as AnalysisLevel })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  >
                    {DETECT_ANALYSIS_LEVEL_OPTIONS.map((o) => (
                      <option key={o.code} value={o.code}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block min-w-0 text-xs text-slate-500 lg:col-span-2">
                  成交时点
                  <select
                    value={normalizeExecutionTiming(cfg.executionTiming)}
                    onChange={(e) =>
                      patchConfig({
                        executionTiming: e.target.value as ExecutionTiming,
                      })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
                  >
                    {EXECUTION_TIMING_OPTIONS.map((o) => (
                      <option key={o.code} value={o.code}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <span className="mt-1 block text-[11px] leading-relaxed text-slate-400">
                    信号在当日收盘产生：当日收盘价 / 次日收盘价（默认）/ 次日开盘价成交。
                    越靠后越保守，也会改变净值、分层曲线与 IC。
                  </span>
                </label>
              </div>
              <div className="mt-3 flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={cfg.filterSuspended}
                    onChange={(e) => patchConfig({ filterSuspended: e.target.checked })}
                  />
                  过滤停牌
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={cfg.filterSt}
                    onChange={(e) => patchConfig({ filterSt: e.target.checked })}
                  />
                  过滤ST
                </label>
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
                    checked={cfg.filterLimitDown}
                    onChange={(e) => patchConfig({ filterLimitDown: e.target.checked })}
                  />
                  过滤跌停
                </label>
              </div>
            </section>
          </div>
        </aside>

        <div
          className={`min-h-0 flex-col gap-3 ${
            mobilePane === "code" ? "flex" : "hidden lg:flex"
          }`}
        >
          <section
            className={`flex min-h-[50vh] flex-col overflow-hidden rounded-xl border bg-white shadow-sm lg:min-h-0 lg:flex-[4] ${
              isEditableSingleMode ? "border-amber-200" : "border-slate-200"
            }`}
          >
            <div
              className={`flex items-center justify-between border-b px-4 py-2 ${
                isEditableSingleMode
                  ? "border-amber-100 bg-amber-50/60"
                  : "border-slate-100"
              }`}
            >
              <span
                className={`text-xs font-semibold ${
                  isEditableSingleMode ? "text-amber-900" : "text-slate-600"
                }`}
              >
                {isDraftOnlyMode && draftFactor
                  ? `因子代码 · ${draftFactor.name}`
                  : isBuiltinLockedMode
                    ? "内置因子（只读）"
                    : primaryUserFactor && ingredientCodes.length <= 1
                      ? `因子代码 · ${primaryUserFactor.name}`
                      : primaryUserFactor
                        ? `组合脚本 · ${primaryUserFactor.name}`
                        : hasDraft
                          ? "组合脚本（含临时因子）"
                          : "组合脚本"}
              </span>
            </div>
            <div className="min-h-0 flex-1 p-2">
              {!scriptReady ? (
                <div className="flex h-full min-h-[12rem] items-center justify-center rounded-lg border border-slate-100 bg-white">
                  <div className="flex flex-col items-center gap-2 text-slate-400">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span className="text-xs">加载代码…</span>
                  </div>
                </div>
              ) : (
                <FactorCodeEditor
                  value={scriptText}
                  onChange={onScriptChange}
                  readOnly={isBuiltinLockedMode}
                  height="100%"
                  showPlaceholder={false}
                />
              )}
            </div>
          </section>

          <section className="flex min-h-[10rem] max-h-56 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:max-h-none lg:min-h-0 lg:flex-1">
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
                  请修改因子代码或参数后，再点「进行检测」。
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
        selected={primaryUserName ? chipFactorCodes : cfg.factorCodes}
        onClose={() => setPickerOpen(false)}
        onConfirm={(codes, _labels, libraries) => {
          applyFactors(codes, libraries);
          setPickerOpen(false);
          pushLog(
            primaryUserName
              ? `已添加 ${codes.filter((c) => c !== primaryUserName).length} 个因子`
              : `已选择 ${codes.length} 个因子`,
          );
        }}
      />
    </div>
  );
}
