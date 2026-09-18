import { getStoredUser } from "./auth";
import type { IdeaItem } from "./ideaApi";
import type { BacktestReport, EvalResult, FactorDraftBundle } from "./agentChain";

const MAX = 12;

export type FactorHistoryEntry = {
  draft_id: string;
  title: string;
  factor_name: string;
  finishedAt: string;
  idea: IdeaItem;
  pack_id?: string;
  bundle_id?: string;
  draft: FactorDraftBundle;
};

export type BacktestHistoryEntry = {
  report_id: string;
  factor_name: string;
  window: string;
  finishedAt: string;
  report: BacktestReport;
};

export type EvalHistoryEntry = {
  eval_id: string;
  report_id: string;
  verdict: string;
  note: string;
  finishedAt: string;
  eval: EvalResult;
};

function uid(): string {
  const u = getStoredUser();
  return u?.id != null ? String(u.id) : "anon";
}

function readList<T>(key: string): T[] {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return [];
    const arr = JSON.parse(raw) as T[];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function writeList<T>(key: string, rows: T[]) {
  sessionStorage.setItem(key, JSON.stringify(rows.slice(0, MAX)));
}

const factorHistKey = () => `svquant.factor.history.v1.u${uid()}`;
const backtestHistKey = () => `svquant.backtest.history.v1.u${uid()}`;
const evalHistKey = () => `svquant.eval.history.v1.u${uid()}`;
const evalLastKey = () => `svquant.chain.eval.v1.u${uid()}`;

export function loadFactorHistory(): FactorHistoryEntry[] {
  return readList<FactorHistoryEntry>(factorHistKey());
}

export function pushFactorHistory(entry: FactorHistoryEntry) {
  const prev = loadFactorHistory().filter((x) => x.draft_id !== entry.draft_id);
  writeList(factorHistKey(), [entry, ...prev]);
}

export function loadBacktestHistory(): BacktestHistoryEntry[] {
  return readList<BacktestHistoryEntry>(backtestHistKey());
}

export function pushBacktestHistory(entry: BacktestHistoryEntry) {
  const prev = loadBacktestHistory().filter((x) => x.report_id !== entry.report_id);
  writeList(backtestHistKey(), [entry, ...prev]);
}

export function loadEvalHistory(): EvalHistoryEntry[] {
  return readList<EvalHistoryEntry>(evalHistKey());
}

export function pushEvalHistory(entry: EvalHistoryEntry) {
  const prev = loadEvalHistory().filter((x) => x.eval_id !== entry.eval_id);
  writeList(evalHistKey(), [entry, ...prev]);
}

export function saveLastEval(row: EvalResult) {
  sessionStorage.setItem(evalLastKey(), JSON.stringify(row));
}

export function loadLastEval(): EvalResult | null {
  try {
    const raw = sessionStorage.getItem(evalLastKey());
    if (!raw) return null;
    return JSON.parse(raw) as EvalResult;
  } catch {
    return null;
  }
}
