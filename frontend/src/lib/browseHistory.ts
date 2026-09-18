/** 本机浏览历史（资讯 / 社区），按登录用户隔离，避免账号间串数据。 */

import { getStoredUser } from "@/lib/auth";

export type BrowseKind = "news" | "community";

export type BrowseHistoryItem = {
  kind: BrowseKind;
  id: number | string;
  title: string;
  href: string;
  at: number;
  subtitle?: string;
};

const LEGACY_KEY = "svquant.browse.history.v1";
const KEY_PREFIX = "svquant.browse.history.v2:";
const MAX = 80;

function dropLegacyShared() {
  try {
    localStorage.removeItem(LEGACY_KEY);
  } catch {
    /* ignore */
  }
}

/** 当前登录用户的存储键；未登录不写、不读（避免 guest 串到账号）。 */
export function browseHistoryUserKey(): string | null {
  const u = getStoredUser();
  if (!u?.id) return null;
  return `u${u.id}`;
}

function storageKey(userKey: string) {
  return `${KEY_PREFIX}${userKey}`;
}

function readAll(userKey: string): BrowseHistoryItem[] {
  dropLegacyShared();
  try {
    const raw = localStorage.getItem(storageKey(userKey));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as BrowseHistoryItem[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (x) =>
        x &&
        (x.kind === "news" || x.kind === "community") &&
        x.id != null &&
        typeof x.title === "string" &&
        typeof x.href === "string",
    );
  } catch {
    return [];
  }
}

function writeAll(userKey: string, items: BrowseHistoryItem[]) {
  dropLegacyShared();
  try {
    localStorage.setItem(storageKey(userKey), JSON.stringify(items.slice(0, MAX)));
  } catch {
    /* quota */
  }
}

export function pushBrowseHistory(
  item: Omit<BrowseHistoryItem, "at"> & { at?: number },
) {
  const userKey = browseHistoryUserKey();
  if (!userKey) return; // 未登录不记，避免串号

  const next: BrowseHistoryItem = {
    kind: item.kind,
    id: item.id,
    title: (item.title || "").trim() || "（无标题）",
    href: item.href,
    subtitle: item.subtitle,
    at: item.at ?? Date.now(),
  };
  const prev = readAll(userKey).filter(
    (x) => !(x.kind === next.kind && String(x.id) === String(next.id)),
  );
  writeAll(userKey, [next, ...prev]);
}

export function listBrowseHistory(kind?: BrowseKind): BrowseHistoryItem[] {
  const userKey = browseHistoryUserKey();
  if (!userKey) return [];
  const all = readAll(userKey);
  if (!kind) return all;
  return all.filter((x) => x.kind === kind);
}

export function clearBrowseHistory(kind?: BrowseKind) {
  const userKey = browseHistoryUserKey();
  if (!userKey) return;
  if (!kind) {
    writeAll(userKey, []);
    return;
  }
  writeAll(
    userKey,
    readAll(userKey).filter((x) => x.kind !== kind),
  );
}

/** 删除单条浏览历史 */
export function removeBrowseHistoryItem(kind: BrowseKind, id: number | string) {
  const userKey = browseHistoryUserKey();
  if (!userKey) return;
  writeAll(
    userKey,
    readAll(userKey).filter(
      (x) => !(x.kind === kind && String(x.id) === String(id)),
    ),
  );
}
