import type { EvidencePack } from "./gatherApi";
import { getStoredUser } from "./auth";

const MAX = 12;

export type GatherHistoryEntry = {
  pack_id: string;
  topic: string;
  themes: string[];
  preset: string;
  max_items: number;
  finishedAt: string;
  digest_mode?: string;
  returned?: number;
  pack: EvidencePack;
};

function uid(): string {
  const u = getStoredUser();
  return u?.id != null ? String(u.id) : "anon";
}

function histKey() {
  return `svquant.gather.history.v1.u${uid()}`;
}

function lastKey() {
  return `svquant.gather.lastPack.v1.u${uid()}`;
}

function readList(): GatherHistoryEntry[] {
  try {
    const raw = sessionStorage.getItem(histKey());
    if (!raw) return [];
    const arr = JSON.parse(raw) as GatherHistoryEntry[];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function writeList(rows: GatherHistoryEntry[]) {
  sessionStorage.setItem(histKey(), JSON.stringify(rows.slice(0, MAX)));
}

export function loadGatherHistory(): GatherHistoryEntry[] {
  return readList();
}

export function pushGatherHistory(entry: GatherHistoryEntry) {
  const prev = readList().filter((x) => x.pack_id !== entry.pack_id);
  writeList([entry, ...prev]);
  sessionStorage.setItem(lastKey(), JSON.stringify(entry.pack));
}

export function loadLastGatherPack(): EvidencePack | null {
  try {
    const raw = sessionStorage.getItem(lastKey());
    if (!raw) return null;
    return JSON.parse(raw) as EvidencePack;
  } catch {
    return null;
  }
}

export function loadGatherPackById(packId: string): EvidencePack | null {
  const id = (packId || "").trim();
  if (!id) return null;
  const hit = readList().find((h) => h.pack_id === id);
  if (hit?.pack) return hit.pack;
  const last = loadLastGatherPack();
  if (last?.pack_id === id) return last;
  return null;
}

/** 供 Idea 页写入「当前工作包」 */
export function setActivePackForIdea(pack: EvidencePack) {
  sessionStorage.setItem(lastKey(), JSON.stringify(pack));
  const prev = readList();
  if (!prev.some((h) => h.pack_id === pack.pack_id)) {
    pushGatherHistory({
      pack_id: pack.pack_id,
      topic: String(pack.query?.topic || pack.digest?.slice(0, 40) || pack.pack_id),
      themes: Array.isArray(pack.query?.themes)
        ? (pack.query!.themes as string[])
        : [],
      preset: String(
        (pack.query?.time_window as { preset?: string } | undefined)?.preset ||
          "7d",
      ),
      max_items: Number(pack.stats?.returned || pack.items?.length || 12),
      finishedAt: new Date().toISOString(),
      digest_mode: pack.stats?.digest_mode,
      returned: pack.stats?.returned ?? pack.items?.length,
      pack,
    });
  }
}
