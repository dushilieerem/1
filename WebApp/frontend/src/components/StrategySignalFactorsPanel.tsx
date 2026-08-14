import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { FactorPickerModal } from "@/components/FactorPickerModal";
import { loadFactors, type FactorMeta } from "@/lib/factorCatalog";
import {
  equalPowers,
  normalizeSignalPowers,
  normalizeSignalWeights,
  type StrategyWeightMode,
} from "@/lib/strategyFactorSync";
import {
  listLibraryFactors,
  listUserFactorLibraries,
  userLibraryFactorToMeta,
  type UserFactorLibrary,
} from "@/lib/userFactorLibraries";

type Props = {
  factorIds: string[];
  weights: number[];
  powers: number[];
  weightMode: StrategyWeightMode;
  tempLabels?: Record<string, string>;
  syncing?: boolean;
  onChange: (next: {
    ids: string[];
    weights: number[];
    powers: number[];
    weightMode: StrategyWeightMode;
    tempLabels?: Record<string, string>;
    /** 切换模式时是否强制重写 @signal（含切到自定义时的提示模板） */
    forceRewriteSignal?: boolean;
  }) => void;
};

function factorLabel(
  code: string,
  catalog: FactorMeta[],
  tempLabels: Record<string, string>,
): string {
  if (tempLabels[code]) return tempLabels[code];
  const f = catalog.find((x) => x.name === code);
  if (f?.explain || f?.description) return f.explain || f.description || code;
  return code;
}

function isCatalogFactor(code: string, catalogNames: Set<string>): boolean {
  return catalogNames.has(code);
}

/** 策略研究页：对齐因子检测的「添加因子 + 三种合成」 */
export function StrategySignalFactorsPanel({
  factorIds,
  weights,
  powers,
  weightMode,
  tempLabels = {},
  syncing,
  onChange,
}: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [catalog, setCatalog] = useState<FactorMeta[]>([]);
  const [catalogReady, setCatalogReady] = useState(false);
  const w = normalizeSignalWeights(factorIds, weights);
  const p = normalizeSignalPowers(factorIds, powers);
  const catalogNames = useMemo(
    () => new Set(catalog.map((f) => f.name)),
    [catalog],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [fs, libs] = await Promise.all([
          loadFactors(),
          listUserFactorLibraries().catch(() => [] as UserFactorLibrary[]),
        ]);
        let userMetas: FactorMeta[] = [];
        if (libs.length) {
          const rows = await Promise.all(
            libs.map((lib) =>
              listLibraryFactors(lib.id).catch(() => [] as Awaited<
                ReturnType<typeof listLibraryFactors>
              >),
            ),
          );
          userMetas = rows.flat().map(userLibraryFactorToMeta);
        }
        if (!cancelled) {
          const byName = new Map<string, FactorMeta>();
          for (const f of fs) byName.set(f.name, f);
          for (const f of userMetas) byName.set(f.name, f);
          setCatalog([...byName.values()]);
          setCatalogReady(true);
        }
      } catch {
        if (!cancelled) {
          setCatalog([]);
          setCatalogReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** 目录未就绪时不当作临时，避免库因子先闪色 */
  const isTempFactor = (code: string) =>
    catalogReady &&
    (Boolean(tempLabels[code]) || !isCatalogFactor(code, catalogNames));

  const pruneTempLabels = (
    ids: string[],
    labels: Record<string, string>,
  ): Record<string, string> => {
    const next: Record<string, string> = {};
    for (const id of ids) {
      if (labels[id]) next[id] = labels[id];
    }
    return next;
  };

  const emitFactors = (
    ids: string[],
    labels: Record<string, string> = tempLabels,
  ) => {
    const prevW = new Map(factorIds.map((id, i) => [id, w[i]]));
    const prevP = new Map(factorIds.map((id, i) => [id, p[i]]));
    onChange({
      ids,
      weights: normalizeSignalWeights(
        ids,
        ids.map((id) => prevW.get(id) ?? 0),
      ),
      powers: normalizeSignalPowers(
        ids,
        ids.map((id) => prevP.get(id) ?? 1),
      ),
      weightMode,
      tempLabels: pruneTempLabels(ids, labels),
    });
  };

  const chipClass = (temp: boolean) =>
    temp
      ? "inline-flex max-w-[220px] items-center gap-1.5 rounded-lg border border-teal-300 bg-teal-50 px-2.5 py-1.5 text-xs shadow-sm"
      : "inline-flex max-w-[220px] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-sm";

  const chipTextClass = (temp: boolean) =>
    temp
      ? "truncate font-medium text-teal-900"
      : "truncate font-medium text-slate-800";

  return (
    <>
      <section>
        <h2 className="mb-3 text-sm font-bold text-blue-600">1. 添加因子</h2>
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 p-3">
          {factorIds.map((c) => {
            const temp = isTempFactor(c);
            return (
              <span
                key={c}
                className={chipClass(temp)}
                title={
                  temp
                    ? `临时因子 · ${c}`
                    : factorLabel(c, catalog, tempLabels)
                }
              >
                <span className={chipTextClass(temp)}>
                  {factorLabel(c, catalog, tempLabels)}
                </span>
                {temp ? (
                  <span className="shrink-0 rounded bg-teal-200/80 px-1 py-0.5 text-[10px] font-medium text-teal-900">
                    临时
                  </span>
                ) : null}
                <button
                  type="button"
                  disabled={syncing}
                  onClick={() => emitFactors(factorIds.filter((x) => x !== c))}
                  className={`shrink-0 disabled:opacity-40 ${
                    temp
                      ? "text-teal-500 hover:text-red-500"
                      : "text-slate-400 hover:text-red-500"
                  }`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </span>
            );
          })}
          <button
            type="button"
            disabled={syncing}
            onClick={() => setPickerOpen(true)}
            title="从因子库选择 / 新增临时因子"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-dashed border-blue-300 bg-blue-50/50 text-blue-600 transition hover:border-blue-400 hover:bg-blue-50 disabled:opacity-40"
          >
            {syncing ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Plus className="h-5 w-5" />
            )}
          </button>
        </div>
      </section>

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
                disabled={syncing}
                onClick={() =>
                  onChange({
                    ids: factorIds,
                    weights: w,
                    powers:
                      weightMode === "product"
                        ? p
                        : equalPowers(factorIds.length),
                    weightMode: m.id,
                    tempLabels,
                    forceRewriteSignal: true,
                  })
                }
                className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold disabled:opacity-40 ${
                  weightMode === m.id
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {weightMode === "custom" ? (
          <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-3 py-3 text-xs leading-relaxed text-slate-500">
            自定义组合：请在右侧{" "}
            <code className="text-slate-600">@signal</code>{" "}
            中自行编写合成逻辑
            {factorIds.length > 0 ? (
              <>
                （可用：
                {factorIds.map((c) => `self.${c}()`).join("、")}）
              </>
            ) : (
              "；也可不选因子，完全在代码里手写。"
            )}
            左侧改因子只会更新 <code className="text-slate-600">@factor</code>
            ，不会覆盖你手写的 signal。
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2.5 font-medium">因子名称</th>
                  <th className="min-w-[5.5rem] px-3 py-2.5 font-medium">
                    {weightMode === "sum" ? "因子权重" : "幂次"}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {factorIds.map((c, i) => {
                  const temp = isTempFactor(c);
                  return (
                    <tr key={c}>
                      <td className="px-3 py-2.5">
                        <div
                          className={`font-medium ${
                            temp ? "text-teal-900" : "text-slate-800"
                          }`}
                        >
                          {factorLabel(c, catalog, tempLabels)}
                          {temp ? (
                            <span className="ml-1.5 rounded bg-teal-100 px-1 py-0.5 text-[10px] font-medium text-teal-800">
                              临时
                            </span>
                          ) : null}
                        </div>
                        <code
                          className={`text-xs ${
                            temp ? "text-teal-700/80" : "text-slate-400"
                          }`}
                        >
                          {c}
                        </code>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min={0}
                            max={weightMode === "sum" ? 100 : undefined}
                            step={weightMode === "sum" ? 1 : 0.1}
                            disabled={syncing}
                            value={
                              weightMode === "sum" ? (w[i] ?? 0) : (p[i] ?? 1)
                            }
                            onChange={(e) => {
                              const v = Number(e.target.value);
                              if (weightMode === "sum") {
                                const next = [...w];
                                next[i] = Math.max(0, Math.min(100, v || 0));
                                onChange({
                                  ids: factorIds,
                                  weights: next,
                                  powers: p,
                                  weightMode,
                                  tempLabels,
                                });
                              } else {
                                const next = [...p];
                                next[i] = v;
                                onChange({
                                  ids: factorIds,
                                  weights: w,
                                  powers: next,
                                  weightMode,
                                  tempLabels,
                                });
                              }
                            }}
                            className="min-w-[3.5rem] w-16 rounded border border-slate-200 px-2 py-1 text-right text-sm tabular-nums disabled:opacity-40"
                          />
                          {weightMode === "sum" ? (
                            <span className="text-xs text-slate-400">%</span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!factorIds.length && (
                  <tr>
                    <td
                      colSpan={2}
                      className="px-3 py-6 text-center text-xs text-slate-400"
                    >
                      可不选。在「选择因子」中添加库因子或临时因子后可在此分配权重。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <FactorPickerModal
        open={pickerOpen}
        selected={factorIds}
        tempLabels={tempLabels}
        allowTempFactor
        onClose={() => setPickerOpen(false)}
        onConfirm={(codes, labels) => {
          emitFactors(codes, labels);
          setPickerOpen(false);
        }}
      />
    </>
  );
}
