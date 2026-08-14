import { useEffect, useMemo, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import {
  builtinCategoryLabelsFromFactors,
  loadFactors,
  type FactorMeta,
} from "@/lib/factorCatalog";
import { isValidFactorMethodName } from "@/lib/strategyFactorSync";
import {
  listLibraryFactors,
  listUserFactorLibraries,
  userLibraryFactorToMeta,
  type UserFactorLibrary,
} from "@/lib/userFactorLibraries";

const BUILTIN_KEY = "__builtin__";

interface Props {
  open: boolean;
  selected: string[];
  /** 已有临时因子释义（策略研究） */
  tempLabels?: Record<string, string>;
  /** 允许在弹窗内新增临时因子 */
  allowTempFactor?: boolean;
  onClose: () => void;
  onConfirm: (codes: string[], tempLabels: Record<string, string>) => void;
}

function labelOf(
  code: string,
  list: FactorMeta[],
  tempLabels: Record<string, string>,
): string {
  if (tempLabels[code]) return tempLabels[code];
  return (
    list.find((f) => f.name === code)?.explain ||
    list.find((f) => f.name === code)?.description ||
    code
  );
}

function FactorRow({
  f,
  on,
  onToggle,
}: {
  f: FactorMeta;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition hover:bg-blue-50/70 ${
        on ? "bg-blue-50/90" : "bg-white"
      }`}
    >
      <span
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
          on ? "border-blue-600 bg-blue-600" : "border-slate-300 bg-white"
        }`}
      >
        {on ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium text-slate-800">
        {f.explain || f.description}
      </span>
      <code className="shrink-0 text-xs text-slate-400">{f.name}</code>
    </button>
  );
}

export function FactorPickerModal({
  open,
  selected,
  tempLabels: tempLabelsProp = {},
  allowTempFactor = false,
  onClose,
  onConfirm,
}: Props) {
  const [builtinFactors, setBuiltinFactors] = useState<FactorMeta[]>([]);
  const [userLibs, setUserLibs] = useState<UserFactorLibrary[]>([]);
  const [allUserFactors, setAllUserFactors] = useState<FactorMeta[]>([]);
  const [userFactors, setUserFactors] = useState<FactorMeta[]>([]);
  const [activeLib, setActiveLib] = useState<string>(BUILTIN_KEY);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("全部");
  const [picked, setPicked] = useState<string[]>(selected);
  const [tempLabels, setTempLabels] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [tempFormOpen, setTempFormOpen] = useState(false);
  const [tempName, setTempName] = useState("");
  const [tempDesc, setTempDesc] = useState("");
  const [tempErr, setTempErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPicked(selected);
    setTempLabels({ ...tempLabelsProp });
    setQuery("");
    setCategory("全部");
    setActiveLib(BUILTIN_KEY);
    setTempFormOpen(false);
    setTempName("");
    setTempDesc("");
    setTempErr(null);
    setLoadErr(null);
    setLoading(true);
    void Promise.all([
      loadFactors().then((fs) => fs.filter((f) => f.library !== "custom_lib")),
      listUserFactorLibraries().catch(() => [] as UserFactorLibrary[]),
    ])
      .then(async ([fs, libs]) => {
        setBuiltinFactors(fs);
        setUserLibs(libs);
        if (libs.length) {
          const rows = await Promise.all(
            libs.map((lib) =>
              listLibraryFactors(lib.id).catch(() => [] as Awaited<
                ReturnType<typeof listLibraryFactors>
              >),
            ),
          );
          setAllUserFactors(rows.flat().map(userLibraryFactorToMeta));
        } else {
          setAllUserFactors([]);
        }
      })
      .catch((ex) => {
        setBuiltinFactors([]);
        setUserLibs([]);
        setAllUserFactors([]);
        setLoadErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open || activeLib === BUILTIN_KEY) {
      setUserFactors([]);
      return;
    }
    const libId = Number(activeLib);
    if (!Number.isFinite(libId)) return;
    let cancelled = false;
    setLoading(true);
    void listLibraryFactors(libId)
      .then((rows) => {
        if (!cancelled) setUserFactors(rows.map(userLibraryFactorToMeta));
      })
      .catch(() => {
        if (!cancelled) setUserFactors([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, activeLib]);

  const builtinCategories = useMemo(
    () => builtinCategoryLabelsFromFactors(builtinFactors),
    [builtinFactors],
  );

  const categoryTabs = useMemo(() => {
    if (activeLib === BUILTIN_KEY) {
      return ["全部", ...builtinCategories];
    }
    const present = new Set(userFactors.map((f) => f.libraryLabel));
    const ordered = [
      ...builtinCategories.filter((c) => present.has(c)),
      ...(present.has("其他") ? ["其他"] : []),
    ];
    for (const lab of present) {
      if (!ordered.includes(lab)) ordered.push(lab);
    }
    return ["全部", ...ordered];
  }, [activeLib, builtinCategories, userFactors]);

  useEffect(() => {
    if (!categoryTabs.includes(category)) setCategory("全部");
  }, [categoryTabs, category]);

  const sourceFactors = activeLib === BUILTIN_KEY ? builtinFactors : userFactors;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sourceFactors.filter((f) => {
      if (category !== "全部" && f.libraryLabel !== category) return false;
      if (!q) return true;
      return (
        f.name.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.explain.toLowerCase().includes(q)
      );
    });
  }, [sourceFactors, query, category]);

  /** 分组展示但默认全部展开（不再用手风琴折叠） */
  const grouped = useMemo(() => {
    const map = new Map<string, FactorMeta[]>();
    for (const f of filtered) {
      const list = map.get(f.libraryLabel) ?? [];
      list.push(f);
      map.set(f.libraryLabel, list);
    }
    const order = categoryTabs.filter((t) => t !== "全部");
    const rank = (lab: string) => {
      const i = order.indexOf(lab);
      return i >= 0 ? i : order.length + 1;
    };
    return Array.from(map.entries()).sort((a, b) => rank(a[0]) - rank(b[0]));
  }, [filtered, categoryTabs]);

  const allKnown = useMemo(() => {
    const map = new Map<string, FactorMeta>();
    for (const f of builtinFactors) map.set(f.name, f);
    for (const f of allUserFactors) map.set(f.name, f);
    for (const f of userFactors) map.set(f.name, f);
    return [...map.values()];
  }, [builtinFactors, allUserFactors, userFactors]);

  const catalogNames = useMemo(
    () => new Set(allKnown.map((f) => f.name)),
    [allKnown],
  );

  const toggle = (code: string) => {
    setPicked((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  };

  const removePicked = (code: string) => {
    setPicked((prev) => prev.filter((c) => c !== code));
    setTempLabels((prev) => {
      if (!(code in prev)) return prev;
      const next = { ...prev };
      delete next[code];
      return next;
    });
  };

  const confirmTemp = () => {
    const name = tempName.trim();
    const desc = tempDesc.trim();
    if (!name) {
      setTempErr("请填写因子名（函数名）");
      return;
    }
    if (!isValidFactorMethodName(name)) {
      setTempErr("因子名须为合法 Python 标识符（字母/下划线开头）");
      return;
    }
    if (!desc) {
      setTempErr("请填写中文释义");
      return;
    }
    if (catalogNames.has(name)) {
      setTempErr(`「${name}」与因子库重名，请换一个函数名`);
      return;
    }
    if (picked.includes(name)) {
      setTempErr("已选中同名因子");
      return;
    }
    setTempLabels((prev) => ({ ...prev, [name]: desc }));
    setPicked((prev) => [...prev, name]);
    setTempFormOpen(false);
    setTempName("");
    setTempDesc("");
    setTempErr(null);
  };

  const onLibChange = (key: string) => {
    setActiveLib(key);
    setCategory("全部");
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center bg-slate-900/40 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div className="flex h-[min(94dvh,900px)] w-full max-w-5xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl sm:rounded-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3 sm:px-5">
          <h3 className="text-base font-bold text-slate-900">选择因子</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 手机：单列，列表独占剩余高度并可触摸滚动；PC：三栏 */}
        <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[180px_minmax(0,1fr)_220px]">
          {/* 手机：下拉选库；PC：侧栏按钮 */}
          <aside className="shrink-0 border-b border-slate-100 bg-slate-50/80 px-3 py-2.5 lg:flex lg:min-h-0 lg:flex-col lg:border-r lg:border-b-0 lg:px-2 lg:py-3">
            <p className="mb-1.5 text-[11px] font-semibold tracking-wide text-slate-400 uppercase lg:px-1">
              因子库
            </p>
            <label className="block lg:hidden">
              <span className="sr-only">选择因子库</span>
              <select
                value={activeLib}
                onChange={(e) => onLibChange(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-800 outline-none focus:border-blue-400"
              >
                <option value={BUILTIN_KEY}>
                  内置因子库（{builtinFactors.length}）
                </option>
                {userLibs.map((lib) => (
                  <option key={lib.id} value={String(lib.id)}>
                    {lib.name || `库#${lib.id}`}（{lib.factorCount ?? 0}）
                  </option>
                ))}
              </select>
            </label>
            <div className="hidden min-h-0 flex-1 space-y-0.5 overflow-y-auto lg:block">
              <button
                type="button"
                onClick={() => onLibChange(BUILTIN_KEY)}
                className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm font-medium ${
                  activeLib === BUILTIN_KEY
                    ? "bg-slate-900 text-white"
                    : "text-slate-700 hover:bg-white"
                }`}
              >
                <span>内置因子库</span>
                <span
                  className={`text-[10px] tabular-nums ${
                    activeLib === BUILTIN_KEY ? "text-slate-300" : "text-slate-400"
                  }`}
                >
                  {builtinFactors.length}
                </span>
              </button>
              {userLibs.map((lib) => (
                <button
                  key={lib.id}
                  type="button"
                  onClick={() => onLibChange(String(lib.id))}
                  className={`flex w-full items-center justify-between gap-1 rounded-lg px-2.5 py-2 text-left text-sm font-medium ${
                    activeLib === String(lib.id)
                      ? "bg-slate-900 text-white"
                      : "text-slate-700 hover:bg-white"
                  }`}
                >
                  <span className="truncate">{lib.name || `库#${lib.id}`}</span>
                  <span
                    className={`shrink-0 text-[10px] tabular-nums ${
                      activeLib === String(lib.id)
                        ? "text-slate-300"
                        : "text-slate-400"
                    }`}
                  >
                    {lib.factorCount ?? 0}
                  </span>
                </button>
              ))}
            </div>
          </aside>

          <div className="flex min-h-0 flex-col overflow-hidden p-3 sm:p-4">
            <div className="mb-2 flex shrink-0 flex-col gap-2 sm:mb-3 sm:flex-row sm:items-center">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索因子名称、代码…"
                  className="w-full rounded-lg border border-slate-200 py-2 pr-3 pl-9 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              {allowTempFactor ? (
                <button
                  type="button"
                  onClick={() => {
                    setTempFormOpen(true);
                    setTempErr(null);
                  }}
                  className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg border border-teal-300 bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-800 transition hover:bg-teal-100"
                >
                  <Plus className="h-3.5 w-3.5" />
                  新增临时因子
                </button>
              ) : null}
            </div>

            {tempFormOpen && allowTempFactor ? (
              <div className="mb-2 shrink-0 rounded-xl border border-teal-200 bg-teal-50/40 p-3 sm:mb-3">
                <p className="text-xs font-semibold text-teal-900">新增临时因子</p>
                <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
                  <label className="block text-[11px] font-medium text-slate-600">
                    因子名（函数）
                    <input
                      autoFocus
                      value={tempName}
                      onChange={(e) => {
                        setTempName(e.target.value);
                        setTempErr(null);
                      }}
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 bg-white px-2 text-sm outline-none focus:border-teal-400"
                    />
                  </label>
                  <label className="block text-[11px] font-medium text-slate-600">
                    中文释义
                    <input
                      value={tempDesc}
                      onChange={(e) => {
                        setTempDesc(e.target.value);
                        setTempErr(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          confirmTemp();
                        }
                      }}
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 bg-white px-2 text-sm outline-none focus:border-teal-400"
                    />
                  </label>
                </div>
                {tempErr ? (
                  <p className="mt-1.5 text-xs text-red-600">{tempErr}</p>
                ) : null}
                <div className="mt-2.5 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setTempFormOpen(false);
                      setTempErr(null);
                    }}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={confirmTemp}
                    className="rounded-lg bg-teal-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-teal-800"
                  >
                    加入已选
                  </button>
                </div>
              </div>
            ) : null}

            <div className="mb-2 flex shrink-0 gap-1.5 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:mb-3 sm:flex-wrap sm:overflow-visible">
              {categoryTabs.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setCategory(t)}
                  className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${
                    category === t
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {t === "全部" ? t : t.replace("因子", "")}
                </button>
              ))}
            </div>

            {/* 唯一主滚动区：必须有明确高度 + touch 滚动 */}
            <div
              className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain rounded-xl border border-slate-200 bg-slate-50/40 [-webkit-overflow-scrolling:touch]"
              style={{ WebkitOverflowScrolling: "touch" }}
            >
              {loading ? (
                <p className="p-6 text-center text-sm text-slate-400">加载因子库…</p>
              ) : loadErr ? (
                <p className="p-6 text-center text-sm text-red-500">{loadErr}</p>
              ) : grouped.length === 0 ? (
                <p className="p-6 text-center text-sm text-slate-400">
                  {activeLib === BUILTIN_KEY
                    ? sourceFactors.length === 0
                      ? "内置因子目录为空，请稍后重试或让助手同步官方目录"
                      : "没有匹配的因子（可切回「全部」）"
                    : "该因子库暂无因子，可在检测报告中「入库」"}
                </p>
              ) : (
                grouped.map(([cat, items]) => (
                  <div key={cat} className="border-b border-slate-100 last:border-0">
                    {category === "全部" ? (
                      <div className="sticky top-0 z-[1] border-b border-slate-100 bg-slate-100/95 px-3 py-1.5 backdrop-blur">
                        <p className="text-xs font-semibold text-slate-600">
                          {cat}
                          <span className="ml-1.5 font-normal text-slate-400">
                            {items.length} 个
                          </span>
                        </p>
                      </div>
                    ) : null}
                    {items.map((f) => (
                      <FactorRow
                        key={`${f.library}:${f.name}`}
                        f={f}
                        on={picked.includes(f.name)}
                        onToggle={() => toggle(f.name)}
                      />
                    ))}
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="flex max-h-36 shrink-0 flex-col border-t border-slate-100 bg-gradient-to-b from-slate-50 to-white p-3 lg:max-h-none lg:min-h-0 lg:border-t-0 lg:border-l">
            <p className="mb-2 shrink-0 text-xs font-semibold text-slate-600">
              已选 {picked.length} 个
            </p>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain [-webkit-overflow-scrolling:touch]">
              {picked.length === 0 ? (
                <p className="text-xs text-slate-400">点上方列表添加</p>
              ) : (
                picked.map((code) => {
                  const isTemp =
                    allowTempFactor &&
                    (Boolean(tempLabels[code]) || !catalogNames.has(code));
                  return (
                    <div
                      key={code}
                      className={`flex items-start justify-between gap-2 rounded-lg px-2.5 py-2 text-xs shadow-sm ring-1 ${
                        isTemp
                          ? "bg-teal-50 ring-teal-200"
                          : "bg-white ring-slate-100"
                      }`}
                    >
                      <div className="min-w-0">
                        <div
                          className={`truncate font-medium ${
                            isTemp ? "text-teal-900" : "text-slate-800"
                          }`}
                        >
                          {labelOf(code, allKnown, tempLabels)}
                          {isTemp ? (
                            <span className="ml-1 rounded bg-teal-200/80 px-1 py-0.5 text-[10px] font-medium text-teal-900">
                              临时
                            </span>
                          ) : null}
                        </div>
                        <code
                          className={isTemp ? "text-teal-700/80" : "text-slate-400"}
                        >
                          {code}
                        </code>
                      </div>
                      <button
                        type="button"
                        onClick={() => removePicked(code)}
                        className={`shrink-0 ${
                          isTemp
                            ? "text-teal-500 hover:text-red-500"
                            : "text-slate-400 hover:text-red-500"
                        }`}
                      >
                        ×
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-slate-100 px-4 py-3 sm:px-5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => {
              const kept: Record<string, string> = {};
              for (const code of picked) {
                if (tempLabels[code]) kept[code] = tempLabels[code];
              }
              onConfirm(picked, kept);
              onClose();
            }}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}
