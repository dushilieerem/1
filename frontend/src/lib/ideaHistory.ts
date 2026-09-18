import type { IdeaBundle, IdeaPreference } from "./ideaApi";
import { getStoredUser } from "./auth";

const MAX = 12;

export type IdeaHistoryEntry = {
  bundle_id: string;
  pack_id: string;
  topic: string;
  idea_count: number;
  idea_mode?: string;
  finishedAt: string;
  preference?: IdeaPreference;
  bundle: IdeaBundle;
};

function uid(): string {
  const u = getStoredUser();
  return u?.id != null ? String(u.id) : "anon";
}

function histKey() {
  return `svquant.idea.history.v1.u${uid()}`;
}

function lastKey() {
  return `svquant.idea.lastBundle.v1.u${uid()}`;
}

function readList(): IdeaHistoryEntry[] {
  try {
    const raw = sessionStorage.getItem(histKey());
    if (!raw) return [];
    const arr = JSON.parse(raw) as IdeaHistoryEntry[];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function writeList(rows: IdeaHistoryEntry[]) {
  sessionStorage.setItem(histKey(), JSON.stringify(rows.slice(0, MAX)));
}

export function loadIdeaHistory(): IdeaHistoryEntry[] {
  return readList();
}

export function pushIdeaHistory(entry: IdeaHistoryEntry) {
  const prev = readList().filter((x) => x.bundle_id !== entry.bundle_id);
  writeList([entry, ...prev]);
  sessionStorage.setItem(lastKey(), JSON.stringify(entry.bundle));
}

export function loadLastIdeaBundle(): IdeaBundle | null {
  try {
    const raw = sessionStorage.getItem(lastKey());
    if (!raw) return null;
    return JSON.parse(raw) as IdeaBundle;
  } catch {
    return null;
  }
}

export function loadIdeaBundleById(bundleId: string): IdeaBundle | null {
  const id = (bundleId || "").trim();
  if (!id) return null;
  const hit = readList().find((h) => h.bundle_id === id);
  if (hit?.bundle) return hit.bundle;
  const last = loadLastIdeaBundle();
  if (last?.bundle_id === id) return last;
  return null;
}

/** 按 pack 取最近一次生成的 bundle（点资讯回来时用） */
export function loadIdeaBundleByPackId(packId: string): IdeaBundle | null {
  const id = (packId || "").trim();
  if (!id) return null;
  const hit = readList().find((h) => h.pack_id === id);
  if (hit?.bundle) return hit.bundle;
  const last = loadLastIdeaBundle();
  if (last?.pack_id === id) return last;
  return null;
}
