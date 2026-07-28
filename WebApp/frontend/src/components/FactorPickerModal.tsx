import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { filterTabsFromFactors, loadFactors, type FactorMeta } from "@/lib/factorCatalog";

interface Props {
  open: boolean;
  selected: string[];
  onClose: () => void;
  onConfirm: (codes: string[]) => void;
}

function labelOf(code: string, list: FactorMeta[]): string {
  return list.find((f) => f.name === code)?.explain || list.find((f) => f.name === code)?.description || code;
}

export function FactorPickerModal({ open, selected, onClose, onConfirm }: Props) {
  const [factors, setFactors] = useState<FactorMeta[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("全部");
  const [picked, setPicked] = useState<string[]>(selected);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPicked(selected);
    setQuery("");
    setCategory("全部");
    setExpanded([]);
    setLoading(true);
    void loadFactors()
      .then((fs) => {
        setFactors(fs);
        const tabs = filterTabsFromFactors(fs).filter((t) => t !== "全部");
        setExpanded(tabs);
      })
      .catch(() => setFactors([]))
      .finally(() => setLoading(false));
  }, [open, selected]);

  const categoryTabs = useMemo(() => filterTabsFromFactors(factors), [factors]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return factors.filter((f) => {
      if (category !== "全部" && f.libraryLabel !== category) return false;
      if (!q) return true;
      return (
        f.name.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.explain.toLowerCase().includes(q)
      );
    });
  }, [factors, query, category]);

  const grouped = useMemo(() => {
    const map = new Map<string, FactorMeta[]>();
    for (const f of filtered) {
      const list = map.get(f.libraryLabel) ?? [];
      list.push(f);
      map.set(f.libraryLabel, list);
    }
    // 与分类 Tab 同序：动量优先，不跟 yaml 原始顺序
    const order = categoryTabs.filter((t) => t !== "全部");
    const rank = (lab: string) => {
      const i = order.indexOf(lab);
      return i >= 0 ? i : order.length + 1;
    };
    return Array.from(map.entries()).sort((a, b) => rank(a[0]) - rank(b[0]));
  }, [filtered, categoryTabs]);

  const toggle = (code: string) => {
    setPicked((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-base font-bold text-slate-900">选择因子</h3>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-4 overflow-hidden p-5 lg:grid-cols-[1fr_220px]">
          <div className="flex min-h-0 flex-col">
            <div className="relative mb-3">
              <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索因子名称、代码…"
                className="w-full rounded-lg border border-slate-200 py-2 pr-3 pl-9 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {categoryTabs.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setCategory(t)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    category === t ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {t === "全部" ? t : t.replace("因子", "")}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50/40">
              {loading ? (
                <p className="p-6 text-center text-sm text-slate-400">加载因子库…</p>
              ) : grouped.length === 0 ? (
                <p className="p-6 text-center text-sm text-slate-400">没有匹配的因子</p>
              ) : (
                grouped.map(([cat, items]) => {
                  const open = expanded.includes(cat);
                  return (
                    <div key={cat} className="border-b border-slate-100 last:border-0">
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded((prev) => (prev.includes(cat) ? prev.filter((x) => x !== cat) : [...prev, cat]))
                        }
                        className="flex w-full items-center justify-between bg-slate-50 px-3 py-2.5 text-left hover:bg-slate-100"
                      >
                        <div>
                          <p className="text-sm font-semibold text-slate-700">{cat}</p>
                          <p className="text-xs text-slate-400">{items.length} 个因子</p>
                        </div>
                        <ChevronDown className={`h-4 w-4 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
                      </button>
                      {open &&
                        items.map((f) => {
                          const on = picked.includes(f.name);
                          return (
                            <button
                              key={`${f.library}:${f.name}`}
                              type="button"
                              onClick={() => toggle(f.name)}
                              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition hover:bg-blue-50/70 ${
                                on ? "bg-blue-50/90" : "bg-white"
                              }`}
                            >
                              <span
                                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                                  on ? "border-blue-600 bg-blue-600" : "border-slate-300 bg-white"
                                }`}
                              >
                                {on && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                              </span>
                              <span className="min-w-0 flex-1 truncate font-medium text-slate-800">
                                {f.explain || f.description}
                              </span>
                              <code className="shrink-0 text-xs text-slate-400">{f.name}</code>
                            </button>
                          );
                        })}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-3">
            <p className="mb-2 text-xs font-semibold text-slate-600">已选 {picked.length} 个</p>
            <div className="max-h-[360px] space-y-2 overflow-y-auto">
              {picked.length === 0 ? (
                <p className="text-xs text-slate-400">点击左侧因子添加</p>
              ) : (
                picked.map((code) => (
                  <div
                    key={code}
                    className="flex items-start justify-between gap-2 rounded-lg bg-white px-2.5 py-2 text-xs shadow-sm ring-1 ring-slate-100"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-800">{labelOf(code, factors)}</div>
                      <code className="text-slate-400">{code}</code>
                    </div>
                    <button type="button" onClick={() => toggle(code)} className="shrink-0 text-slate-400 hover:text-red-500">
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(picked)}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}
