import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bookmark,
  ChevronRight,
  FolderOpen,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useConfirm } from "@/components/ConfirmDialog";
import { PageJump } from "@/components/PageJump";
import {
  getStoredUser,
  subscribeAuth,
} from "@/lib/auth";
import {
  bareCode,
  fetchIndexConstituents,
  fetchMarketIndices,
  fetchMarketSymbols,
  formatSymbolLabel,
  symbolMatchesQuery,
  type MarketIndex,
  type MarketSymbol,
} from "@/lib/marketDataApi";
import {
  addWatchlistSymbol,
  addWatchlistSymbolsBatch,
  createWatchlist,
  deleteWatchlist,
  deleteWatchlistSymbol,
  listWatchlistSymbols,
  listWatchlists,
  renameWatchlist,
  type Watchlist,
  type WatchlistSymbol,
} from "@/lib/watchlistApi";
import {
  BOARD_OPTIONS,
  filterByBoard,
  LEVEL1_OPTIONS,
  LEVEL2_STOCK_OPTIONS,
  type BoardKey,
  type BrowseLevel1,
  type BrowseLevel2,
} from "@/lib/watchlistUniverse";

const BROWSE_KEY = "__browse__";
const PAGE_SIZE = 20;

type Mode = "list" | "browse";

export function WatchlistPage() {
  const confirm = useConfirm();
  const [user, setUser] = useState(getStoredUser());
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [activeKey, setActiveKey] = useState<string>(BROWSE_KEY);
  const [mode, setMode] = useState<Mode>("browse");
  const [symbols, setSymbols] = useState<WatchlistSymbol[]>([]);
  const [market, setMarket] = useState<MarketSymbol[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Watchlist | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameErr, setRenameErr] = useState<string | null>(null);

  /** 加入目标组合（浏览选股时仍可记住左侧选过的组合） */
  const [targetWlId, setTargetWlId] = useState<number | null>(null);
  const [pickOpen, setPickOpen] = useState(false);
  const [pickDraftId, setPickDraftId] = useState<number | null>(null);
  const [pendingAdd, setPendingAdd] = useState<MarketSymbol[] | null>(null);

  const [l1, setL1] = useState<BrowseLevel1 | null>("stock");
  const [l2, setL2] = useState<BrowseLevel2 | null>("market");
  const [board, setBoard] = useState<BoardKey | null>(null);
  /** RE 股指 code，如 000300.SH */
  const [indexKey, setIndexKey] = useState<string | null>(null);
  const [indices, setIndices] = useState<MarketIndex[]>([]);
  const [indicesErr, setIndicesErr] = useState<string | null>(null);
  const [indexPool, setIndexPool] = useState<MarketSymbol[]>([]);
  const [indexLoading, setIndexLoading] = useState(false);
  const [indexErr, setIndexErr] = useState<string | null>(null);

  const activeWlId =
    activeKey !== BROWSE_KEY && Number.isFinite(Number(activeKey))
      ? Number(activeKey)
      : null;

  const reloadLists = async () => {
    setErr(null);
    try {
      if (!getStoredUser()) {
        setWatchlists([]);
        setSymbols([]);
        return;
      }
      const wls = await listWatchlists();
      setWatchlists(wls);
      setTargetWlId((prev) => {
        if (prev != null && wls.some((w) => w.id === prev)) return prev;
        return wls[0]?.id ?? null;
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const notify = async (message: string, title = "提示") => {
    await confirm({ title, message, alert: true, confirmLabel: "确定" });
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      await reloadLists();
      try {
        const list = await fetchMarketSymbols();
        if (!cancelled) setMarket(list);
      } catch (e) {
        if (!cancelled) {
          setMarket([]);
          setErr(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
      try {
        const idx = await fetchMarketIndices();
        if (!cancelled) {
          setIndices(idx);
          setIndicesErr(null);
        }
      } catch (e) {
        if (!cancelled) {
          setIndices([]);
          setIndicesErr(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (mode !== "browse" || l2 !== "index" || !indexKey) {
      setIndexPool([]);
      setIndexErr(null);
      setIndexLoading(false);
      return;
    }
    let cancelled = false;
    setIndexLoading(true);
    setIndexErr(null);
    void fetchIndexConstituents(indexKey)
      .then((rows) => {
        if (!cancelled) setIndexPool(rows);
      })
      .catch((e) => {
        if (!cancelled) {
          setIndexPool([]);
          setIndexErr(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setIndexLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, l2, indexKey]);

  useEffect(() => {
    return subscribeAuth(() => {
      setUser(getStoredUser());
      void reloadLists();
    });
  }, []);

  useEffect(() => {
    if (activeWlId == null) {
      setSymbols([]);
      return;
    }
    let cancelled = false;
    void listWatchlistSymbols(activeWlId)
      .then((rows) => {
        if (!cancelled) setSymbols(rows);
      })
      .catch((e) => {
        if (!cancelled) {
          setSymbols([]);
          setErr(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeWlId]);

  useEffect(() => {
    setPage(1);
    setSelected(new Set());
  }, [query, board, indexKey, l2, l1, mode, activeKey]);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2500);
  };

  const openCreate = () => {
    if (!user) {
      window.location.href = "/login?next=/data/watchlist";
      return;
    }
    setCreateName("");
    setCreateErr(null);
    setCreateOpen(true);
  };

  const openRename = (wl: Watchlist) => {
    setRenameTarget(wl);
    setRenameName(wl.name);
    setRenameErr(null);
    setRenameOpen(true);
  };

  const confirmRename = async () => {
    if (!renameTarget) return;
    const title = renameName.trim();
    if (!title) {
      setRenameErr("请填写组合名称");
      return;
    }
    setBusy(true);
    setRenameErr(null);
    try {
      const wl = await renameWatchlist(renameTarget.id, title);
      setWatchlists((prev) =>
        prev.map((x) => (x.id === wl.id ? { ...x, ...wl } : x)),
      );
      setRenameOpen(false);
      setRenameTarget(null);
      showToast(`已改名为「${wl.name}」`);
    } catch (e) {
      setRenameErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const confirmCreate = async () => {
    const title = createName.trim();
    if (!title) {
      setCreateErr("请填写组合名称");
      return;
    }
    setBusy(true);
    setCreateErr(null);
    try {
      const wl = await createWatchlist(title);
      setWatchlists((prev) => [wl, ...prev.filter((x) => x.id !== wl.id)]);
      setActiveKey(String(wl.id));
      setTargetWlId(wl.id);
      setMode("list");
      setCreateOpen(false);
    } catch (e) {
      setCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDeleteWl = async (wl: Watchlist) => {
    const ok = await confirm({
      title: "删除自选组合",
      message: `确认删除「${wl.name}」？组内标的将一并移除。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteWatchlist(wl.id);
      setWatchlists((prev) => prev.filter((x) => x.id !== wl.id));
      if (activeKey === String(wl.id)) {
        setActiveKey(BROWSE_KEY);
        setMode("browse");
      }
      setTargetWlId((prev) => (prev === wl.id ? null : prev));
    } catch (e) {
      void notify(e instanceof Error ? e.message : String(e));
    }
  };

  const onRemoveSymbol = async (row: WatchlistSymbol) => {
    if (activeWlId == null) return;
    const ok = await confirm({
      title: "移出自选",
      message: `从当前组合移除「${formatSymbolLabel(row.symbol, row.name) || row.symbol}」？`,
      confirmLabel: "移除",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteWatchlistSymbol(activeWlId, row.symbol);
      setSymbols((prev) => prev.filter((x) => x.symbol !== row.symbol));
      setWatchlists((prev) =>
        prev.map((w) =>
          w.id === activeWlId
            ? { ...w, symbolCount: Math.max(0, (w.symbolCount || 1) - 1) }
            : w,
        ),
      );
    } catch (e) {
      void notify(e instanceof Error ? e.message : String(e));
    }
  };

  const labelOf = (s: { symbol: string; name?: string | null }) => {
    const sym = String(s.symbol || "").trim();
    const name = String(s.name || "").trim();
    return name ? `${sym} ${name}` : sym;
  };

  const commitAdd = async (wlId: number, items: MarketSymbol[]) => {
    if (!items.length) {
      await notify("请先勾选股票");
      return;
    }
    setBusy(true);
    try {
      if (items.length === 1) {
        const item = items[0];
        await addWatchlistSymbol(wlId, item.symbol, item.name || "");
        showToast(`已加入 ${labelOf(item)}`);
      } else {
        const res = await addWatchlistSymbolsBatch(
          wlId,
          items.map((x) => ({ symbol: x.symbol, name: x.name || "" })),
        );
        setSelected(new Set());
        showToast(`已加入 ${res.added} 只（跳过 ${res.skipped}）`);
      }
      const rows = await listWatchlistSymbols(wlId);
      if (activeWlId === wlId) setSymbols(rows);
      setWatchlists((prev) =>
        prev.map((w) =>
          w.id === wlId ? { ...w, symbolCount: rows.length } : w,
        ),
      );
      setTargetWlId(wlId);
    } catch (e) {
      void notify(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const beginAdd = async (items: MarketSymbol[]) => {
    if (!user) {
      window.location.href = "/login?next=/data/watchlist";
      return;
    }
    if (!items.length) {
      await notify("请先勾选股票");
      return;
    }
    if (watchlists.length === 0) {
      await notify("请先在左侧新建一个自选组合，再添加股票。");
      return;
    }
    setPendingAdd(items);
    setPickDraftId(
      targetWlId != null && watchlists.some((w) => w.id === targetWlId)
        ? targetWlId
        : watchlists[0].id,
    );
    setPickOpen(true);
  };

  const confirmPick = async () => {
    if (pickDraftId == null || !pendingAdd?.length) {
      setPickOpen(false);
      setPendingAdd(null);
      return;
    }
    setPickOpen(false);
    const items = pendingAdd;
    setPendingAdd(null);
    await commitAdd(pickDraftId, items);
  };

  const browsePool: MarketSymbol[] = useMemo(() => {
    if (mode !== "browse" || l1 !== "stock") return [];
    if (l2 === "market" && board) return filterByBoard(market, board);
    if (l2 === "index" && indexKey) return indexPool;
    return [];
  }, [mode, l1, l2, board, market, indexKey, indexPool]);

  const searchHits: MarketSymbol[] = useMemo(() => {
    const q = query.trim();
    if (!q) return [];
    return market.filter((s) => symbolMatchesQuery(s, q)).slice(0, 200);
  }, [market, query]);

  const listFiltered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return symbols;
    return symbols.filter((s) => {
      const name = (s.name || "").toLowerCase();
      const sym = s.symbol.toLowerCase();
      const bare = bareCode(s.symbol).toLowerCase();
      return name.includes(q) || sym.includes(q) || bare.includes(q);
    });
  }, [symbols, query]);

  const poolSource =
    mode === "browse" && query.trim()
      ? searchHits
      : mode === "browse"
        ? browsePool
        : [];

  const totalPages = Math.max(1, Math.ceil(
    (mode === "list" ? listFiltered.length : poolSource.length) / PAGE_SIZE,
  ));
  const pageSafe = Math.min(page, totalPages);
  const pageSlice = (mode === "list" ? listFiltered : poolSource).slice(
    (pageSafe - 1) * PAGE_SIZE,
    pageSafe * PAGE_SIZE,
  );

  const activeTitle =
    activeKey === BROWSE_KEY
      ? "浏览选股"
      : watchlists.find((w) => String(w.id) === activeKey)?.name || "自选组合";

  const indexLabel =
    indices.find((x) => x.code === indexKey)?.name || indexKey || "板块 / 指数";

  const indexEmpty =
    mode === "browse" &&
    l1 === "stock" &&
    l2 === "index" &&
    indexKey != null &&
    !indexLoading &&
    !query.trim() &&
    indexPool.length === 0;

  const toggleSelect = (symbol: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  };

  const browsePageRows =
    mode === "browse" ? (pageSlice as MarketSymbol[]) : [];
  const browsePageAllSelected =
    browsePageRows.length > 0 &&
    browsePageRows.every((r) => selected.has(r.symbol));
  const browsePageSomeSelected =
    browsePageRows.some((r) => selected.has(r.symbol)) &&
    !browsePageAllSelected;

  const toggleSelectPage = () => {
    const syms = browsePageRows.map((r) => r.symbol);
    setSelected((prev) => {
      const next = new Set(prev);
      if (browsePageAllSelected) {
        for (const s of syms) next.delete(s);
      } else {
        for (const s of syms) next.add(s);
      }
      return next;
    });
  };

  const selectedItems = poolSource.filter((s) => selected.has(s.symbol));

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1440px] px-6 py-8">
        <div className="relative mb-6 overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
          <div className="relative flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-600 text-white shadow">
                <Bookmark className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-900">自选股组合</h1>
                {err ? <p className="mt-1 text-sm text-red-500">{err}</p> : null}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2">
                <Search className="h-4 w-4 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索代码 / 名称…"
                  className="w-48 bg-transparent text-sm outline-none sm:w-56"
                />
                {query ? (
                  <button type="button" onClick={() => setQuery("")}>
                    <X className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                ) : null}
              </div>
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
              >
                <Plus className="h-4 w-4" />
                新建组合
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          {/* sidebar */}
          <aside className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm">
            <button
              type="button"
              onClick={() => {
                setActiveKey(BROWSE_KEY);
                setMode("browse");
              }}
              className={`mb-2 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-semibold ${
                activeKey === BROWSE_KEY
                  ? "bg-cyan-50 text-cyan-800"
                  : "text-slate-700 hover:bg-slate-50"
              }`}
            >
              <Search className="h-4 w-4 shrink-0" />
              浏览选股
            </button>
            <div className="mb-2 flex items-center justify-between px-2 pt-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                我的组合
              </span>
              <button
                type="button"
                onClick={openCreate}
                className="text-slate-400 hover:text-cyan-700"
                title="新建"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            {!user ? (
              <p className="px-3 py-2 text-xs text-slate-500">
                <Link className="text-cyan-700 underline" to="/login?next=/data/watchlist">
                  登录
                </Link>
                后可管理自选
              </p>
            ) : watchlists.length === 0 ? (
              <p className="px-3 py-2 text-xs text-slate-400">暂无组合，点击上方新建</p>
            ) : (
              <ul className="space-y-0.5">
                {watchlists.map((wl) => (
                  <li key={wl.id} className="group flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveKey(String(wl.id));
                        setTargetWlId(wl.id);
                        setMode("list");
                      }}
                      className={`flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2 text-left text-sm ${
                        activeKey === String(wl.id) ||
                        (mode === "browse" && targetWlId === wl.id)
                          ? "bg-cyan-50 font-semibold text-cyan-900"
                          : "text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <FolderOpen className="h-4 w-4 shrink-0 text-slate-400" />
                      <span className="truncate">{wl.name}</span>
                      <span className="ml-auto shrink-0 text-xs text-slate-400">
                        {wl.symbolCount ?? 0}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="rounded-lg p-1.5 text-slate-300 opacity-0 hover:bg-slate-100 hover:text-cyan-700 group-hover:opacity-100"
                      onClick={() => openRename(wl)}
                      title="改名"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      className="rounded-lg p-1.5 text-slate-300 opacity-0 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                      onClick={() => void onDeleteWl(wl)}
                      title="删除组合"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          {/* main */}
          <section className="rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
              <div className="font-semibold text-slate-900">{activeTitle}</div>
              {mode === "browse" && (query.trim() || board || indexKey) ? (
                <button
                  type="button"
                  disabled={busy || selectedItems.length === 0}
                  onClick={() => void beginAdd(selectedItems)}
                  className="rounded-xl bg-cyan-600 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50"
                >
                  批量加入（{selectedItems.length}）
                </button>
              ) : null}
            </div>

            {mode === "browse" && !query.trim() ? (
              <div className="border-b border-slate-100 px-4 py-4">
                <div className="mb-3 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
                  <span className={l1 ? "font-medium text-slate-800" : ""}>
                    {LEVEL1_OPTIONS.find((x) => x.key === l1)?.label || "资产"}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
                  <span className={l2 ? "font-medium text-slate-800" : "text-slate-400"}>
                    {LEVEL2_STOCK_OPTIONS.find((x) => x.key === l2)?.label ||
                      "分类"}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
                  <span
                    className={
                      board || indexKey
                        ? "font-medium text-slate-800"
                        : "text-slate-400"
                    }
                  >
                    {BOARD_OPTIONS.find((x) => x.key === board)?.label ||
                      (board || indexKey ? indexLabel : "板块 / 指数")}
                  </span>
                </div>

                <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                  <div className="grid grid-cols-1 divide-y divide-slate-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                    <div className="min-h-[200px] p-1.5">
                      <ul className="space-y-0.5">
                        {LEVEL1_OPTIONS.map((opt) => {
                          const on = l1 === opt.key;
                          return (
                            <li key={opt.key}>
                              <button
                                type="button"
                                disabled={!opt.enabled}
                                title={opt.hint}
                                onClick={() => {
                                  if (!opt.enabled) return;
                                  setL1(opt.key);
                                  setL2(opt.key === "stock" ? "market" : null);
                                  setBoard(null);
                                  setIndexKey(null);
                                }}
                                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition ${
                                  on
                                    ? "bg-slate-100 font-medium text-slate-900"
                                    : opt.enabled
                                      ? "text-slate-600 hover:bg-slate-50"
                                      : "cursor-not-allowed text-slate-300"
                                }`}
                              >
                                <span
                                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold ${
                                    on
                                      ? "bg-slate-200/80 text-slate-700"
                                      : "bg-slate-50 text-slate-400"
                                  }`}
                                >
                                  {opt.key === "stock"
                                    ? "股"
                                    : opt.key === "etf"
                                      ? "E"
                                      : "期"}
                                </span>
                                <span className="flex-1">{opt.label}</span>
                                {on ? (
                                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                                ) : null}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>

                    <div className="min-h-[200px] p-1.5">
                      {l1 === "stock" ? (
                        <ul className="space-y-0.5">
                          {LEVEL2_STOCK_OPTIONS.map((opt) => {
                            const on = l2 === opt.key;
                            return (
                              <li key={opt.key}>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setL2(opt.key);
                                    setBoard(null);
                                    setIndexKey(null);
                                  }}
                                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition ${
                                    on
                                      ? "bg-slate-100 font-medium text-slate-900"
                                      : "text-slate-600 hover:bg-slate-50"
                                  }`}
                                >
                                  <span
                                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                                      on ? "bg-slate-500" : "bg-slate-300"
                                    }`}
                                  />
                                  <span className="flex-1">{opt.label}</span>
                                  {on ? (
                                    <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                                  ) : null}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <div className="flex h-full items-center justify-center px-3 py-8 text-sm text-slate-400">
                          选择左侧资产类型
                        </div>
                      )}
                    </div>

                    <div className="min-h-[200px] max-h-[200px] overflow-y-auto p-1.5">
                      {l1 === "stock" && l2 === "market" ? (
                        <ul className="space-y-0.5">
                          {BOARD_OPTIONS.map((opt) => {
                            const on = board === opt.key;
                            return (
                              <li key={opt.key}>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setBoard(opt.key);
                                    setIndexKey(null);
                                  }}
                                  className={`flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm transition ${
                                    on
                                      ? "bg-slate-100 font-medium text-slate-900"
                                      : "text-slate-600 hover:bg-slate-50"
                                  }`}
                                >
                                  {opt.label}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      ) : l1 === "stock" && l2 === "index" ? (
                        indicesErr ? (
                          <div className="px-3 py-6 text-sm leading-relaxed text-slate-500">
                            股指列表暂不可用：{indicesErr}
                          </div>
                        ) : indices.length === 0 ? (
                          <div className="px-3 py-8 text-center text-sm text-slate-400">
                            暂无可用股指
                          </div>
                        ) : (
                          <ul className="space-y-0.5">
                            {indices.map((opt) => {
                              const on = indexKey === opt.code;
                              return (
                                <li key={opt.code}>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setIndexKey(opt.code);
                                      setBoard(null);
                                    }}
                                    className={`flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm transition ${
                                      on
                                        ? "bg-slate-100 font-medium text-slate-900"
                                        : "text-slate-600 hover:bg-slate-50"
                                    }`}
                                  >
                                    {opt.name}
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )
                      ) : (
                        <div className="flex h-full items-center justify-center px-3 py-8 text-sm text-slate-400">
                          选择中间分类
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            <div className="px-2 py-2 sm:px-4">
              {loading ? (
                <p className="px-3 py-10 text-center text-sm text-slate-400">加载中…</p>
              ) : mode === "list" ? (
                listFiltered.length === 0 ? (
                  <p className="px-3 py-10 text-center text-sm text-slate-400">
                    {activeWlId == null ? "请选择左侧自选组合" : "组合为空"}
                  </p>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {(pageSlice as WatchlistSymbol[]).map((row) => (
                      <li
                        key={row.symbol}
                        className="flex items-center gap-3 px-3 py-3 hover:bg-slate-50/80"
                      >
                        <div className="min-w-0 flex-1">
                          <Link
                            to={`/data/symbol/${encodeURIComponent(row.symbol)}?from=watchlist`}
                            className="font-semibold text-slate-900 hover:text-cyan-700"
                          >
                            {labelOf(row)}
                          </Link>
                        </div>
                        <button
                          type="button"
                          onClick={() => void onRemoveSymbol(row)}
                          className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                          title="移除"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              ) : mode === "browse" && !query.trim() && !board && !indexKey ? (
                <p className="px-3 py-10 text-center text-sm text-slate-400">
                  请选择三级分类
                </p>
              ) : mode === "browse" &&
                l2 === "index" &&
                indexKey &&
                indexLoading &&
                !query.trim() ? (
                <p className="px-3 py-10 text-center text-sm text-slate-400">
                  加载成分股…
                </p>
              ) : mode === "browse" &&
                l2 === "index" &&
                indexKey &&
                indexErr &&
                !query.trim() ? (
                <div className="px-3 py-10 text-center text-sm leading-relaxed text-slate-500">
                  成分股暂不可用：{indexErr}
                </div>
              ) : poolSource.length === 0 && !(indexEmpty && !query.trim()) ? (
                <p className="px-3 py-10 text-center text-sm text-slate-400">
                  {query.trim() ? "无匹配标的" : "该分类暂无标的"}
                </p>
              ) : indexEmpty ? (
                <div className="px-3 py-12 text-center text-sm text-slate-400">
                  该指数暂无成分
                </div>
              ) : mode === "list" ? null : (
                <div>
                  <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
                    <label className="flex cursor-pointer items-center gap-2.5 text-sm text-slate-600">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-300"
                        checked={browsePageAllSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = browsePageSomeSelected;
                        }}
                        onChange={toggleSelectPage}
                      />
                      <span>全选当前页</span>
                      <span className="text-slate-400">
                        （{browsePageRows.length}）
                      </span>
                    </label>
                  </div>
                  <ul className="divide-y divide-slate-100">
                    {browsePageRows.map((row) => {
                      const checked = selected.has(row.symbol);
                      return (
                        <li
                          key={row.symbol}
                          className="flex items-stretch hover:bg-slate-50/80"
                        >
                          <div
                            role="button"
                            tabIndex={0}
                            onClick={() => toggleSelect(row.symbol)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                toggleSelect(row.symbol);
                              }
                            }}
                            className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 py-2.5"
                          >
                            <input
                              type="checkbox"
                              className="pointer-events-none h-4 w-4 shrink-0 rounded border-slate-300"
                              checked={checked}
                              readOnly
                              tabIndex={-1}
                              aria-hidden
                            />
                            <Link
                              to={`/data/symbol/${encodeURIComponent(row.symbol)}?from=watchlist`}
                              onClick={(e) => e.stopPropagation()}
                              className="shrink-0 font-medium text-slate-900 hover:text-cyan-700"
                            >
                              {labelOf(row)}
                            </Link>
                            <div className="min-h-[1.25rem] flex-1" aria-hidden />
                          </div>
                          <div className="flex shrink-0 items-center pr-3">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void beginAdd([row])}
                              className="rounded-lg border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-800 hover:bg-cyan-100 disabled:opacity-50"
                            >
                              加入
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {totalPages > 1 ? (
                <div className="flex flex-wrap items-center justify-center gap-2 py-3 text-sm">
                  <button
                    type="button"
                    disabled={pageSafe <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-slate-200 px-3 py-1 disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <span className="text-slate-500">
                    {pageSafe} / {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={pageSafe >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-lg border border-slate-200 px-3 py-1 disabled:opacity-40"
                  >
                    下一页
                  </button>
                  <PageJump
                    page={pageSafe}
                    totalPages={totalPages}
                    onJump={setPage}
                  />
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-slate-900">新建自选组合</h2>
            <input
              className="mt-4 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100"
              placeholder="组合名称"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void confirmCreate();
              }}
              autoFocus
            />
            {createErr ? (
              <p className="mt-2 text-sm text-red-500">{createErr}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-xl px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                onClick={() => setCreateOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50"
                onClick={() => void confirmCreate()}
              >
                创建
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {renameOpen && renameTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-slate-900">修改组合名称</h2>
            <input
              className="mt-4 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-100"
              placeholder="组合名称"
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void confirmRename();
              }}
              autoFocus
            />
            {renameErr ? (
              <p className="mt-2 text-sm text-red-500">{renameErr}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-xl px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                onClick={() => {
                  setRenameOpen(false);
                  setRenameTarget(null);
                }}
              >
                取消
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50"
                onClick={() => void confirmRename()}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {pickOpen ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-900/40 px-4">
          <div
            role="dialog"
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl"
          >
            <h2 className="text-base font-semibold text-slate-900">加入到组合</h2>
            <p className="mt-1 text-sm text-slate-500">
              选择要加入的自选组合（{pendingAdd?.length || 0} 只）
            </p>
            <ul className="mt-4 max-h-64 space-y-1 overflow-y-auto">
              {watchlists.map((wl) => (
                <li key={wl.id}>
                  <button
                    type="button"
                    onClick={() => setPickDraftId(wl.id)}
                    className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm ${
                      pickDraftId === wl.id
                        ? "bg-cyan-50 font-semibold text-cyan-900 ring-1 ring-cyan-200"
                        : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <FolderOpen className="h-4 w-4 text-slate-400" />
                    <span className="truncate">{wl.name}</span>
                    <span className="ml-auto text-xs text-slate-400">
                      {wl.symbolCount ?? 0}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-xl px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                onClick={() => {
                  setPickOpen(false);
                  setPendingAdd(null);
                }}
              >
                取消
              </button>
              <button
                type="button"
                disabled={busy || pickDraftId == null}
                className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50"
                onClick={() => void confirmPick()}
              >
                确定加入
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {toast ? (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-slate-900 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
