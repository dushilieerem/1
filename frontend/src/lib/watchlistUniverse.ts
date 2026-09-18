/** 浏览选股树：股指成分来自 RE；市场类可筛项由本机按后缀/代码段得出 */

import { bareCode, type MarketSymbol } from "./marketDataApi";

export type BrowseLevel1 = "stock" | "etf" | "futures";
export type BrowseLevel2 = "market" | "index";

export type BoardKey =
  | "all"
  | "sh_all"
  | "sz_all"
  | "sh_main"
  | "sz_main"
  | "chinext"
  | "star";

export const LEVEL1_OPTIONS: {
  key: BrowseLevel1;
  label: string;
  enabled: boolean;
  hint?: string;
}[] = [
  { key: "stock", label: "股票", enabled: true },
  {
    key: "etf",
    label: "ETF",
    enabled: false,
    hint: "待同事提供 ETF 池接口",
  },
  {
    key: "futures",
    label: "期货",
    enabled: false,
    hint: "待同事提供期货池接口",
  },
];

export const LEVEL2_STOCK_OPTIONS: {
  key: BrowseLevel2;
  label: string;
}[] = [
  { key: "market", label: "市场类" },
  { key: "index", label: "股指类" },
];

/** ready=false：占位展示，列表暂空 */
export const BOARD_OPTIONS: {
  key: BoardKey;
  label: string;
  ready: boolean;
}[] = [
  { key: "all", label: "A股全市场", ready: true },
  { key: "sh_all", label: "上证全A", ready: true },
  { key: "sz_all", label: "深证全A", ready: true },
  { key: "sh_main", label: "上证主板", ready: false },
  { key: "sz_main", label: "深证主板", ready: false },
  { key: "chinext", label: "创业板", ready: false },
  { key: "star", label: "科创板", ready: false },
];

export function filterByBoard(
  list: MarketSymbol[],
  board: BoardKey,
): MarketSymbol[] {
  const opt = BOARD_OPTIONS.find((b) => b.key === board);
  if (!opt?.ready) return [];

  return list.filter((s) => {
    const sym = String(s.symbol || "").trim().toUpperCase();
    if (!sym || sym.endsWith(".BJ")) return false;
    if (board === "all") return true;
    if (board === "sh_all") return sym.endsWith(".SH");
    if (board === "sz_all") return sym.endsWith(".SZ");
    return false;
  });
}

/** 预留：四板块有数据源后再启用；当前未使用 */
export function classifyBoard(symbol: string): BoardKey | null {
  const sym = String(symbol || "").trim().toUpperCase();
  if (!sym || sym.endsWith(".BJ")) return null;
  const code = bareCode(sym);
  if (!/^\d{6}$/.test(code)) return null;
  if (sym.endsWith(".SH")) {
    if (code.startsWith("688")) return "star";
    if (code.startsWith("60")) return "sh_main";
    return null;
  }
  if (sym.endsWith(".SZ")) {
    if (code.startsWith("300") || code.startsWith("301")) return "chinext";
    if (
      code.startsWith("000") ||
      code.startsWith("001") ||
      code.startsWith("002") ||
      code.startsWith("003")
    ) {
      return "sz_main";
    }
  }
  return null;
}
