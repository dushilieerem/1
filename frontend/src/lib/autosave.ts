/** P2-04：本地自动保存草稿（按用户+资源隔离，带保存时间）。 */

export type DraftEnvelope<T> = {
  v: 1;
  savedAt: string;
  data: T;
};

function scopedKey(key: string): string {
  let uid = "anon";
  try {
    const raw =
      localStorage.getItem("svquant_user") || sessionStorage.getItem("svquant_user");
    const user = raw ? JSON.parse(raw) : null;
    if (user?.id != null) uid = String(user.id);
  } catch {
    /* ignore */
  }
  return `${key}.u${uid}`;
}

export function saveDraft<T>(key: string, data: T): string | null {
  try {
    const savedAt = new Date().toISOString();
    const payload: DraftEnvelope<T> = { v: 1, savedAt, data };
    localStorage.setItem(scopedKey(key), JSON.stringify(payload));
    return savedAt;
  } catch {
    return null;
  }
}

export function loadDraft<T>(key: string): DraftEnvelope<T> | null {
  try {
    const raw = localStorage.getItem(scopedKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DraftEnvelope<T>;
    if (!parsed || parsed.v !== 1 || !parsed.savedAt) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearDraft(key: string): void {
  try {
    localStorage.removeItem(scopedKey(key));
  } catch {
    /* ignore */
  }
}

/** 草稿是否比服务端版本更新（用于冲突提示）。 */
export function draftNewerThan(
  draft: DraftEnvelope<unknown> | null,
  serverUpdatedAt?: string | null,
): boolean {
  if (!draft) return false;
  if (!serverUpdatedAt) return true;
  const server = Date.parse(serverUpdatedAt);
  const local = Date.parse(draft.savedAt);
  if (Number.isNaN(server) || Number.isNaN(local)) return true;
  return local > server;
}
