/** AI 因子/策略生成历史：按登录用户隔离（本机缓存；后续计费对接服务端）。 */

import { getStoredUser } from "./auth";

const LEGACY_SHARED_KEYS = [
  "svquant.aiFactor.history.v1",
  "svquant.aiFactor.history.v2",
  "svquant.aiStrategy.history.v1",
] as const;

export type AiHistoryKind = "factor" | "strategy";

export function currentAiUserId(): number | null {
  const u = getStoredUser();
  return u?.id != null && u.id > 0 ? u.id : null;
}

/** 用户级 key；未登录返回 null（不读写共享桶，避免串台）。 */
export function aiHistoryStorageKey(kind: AiHistoryKind): string | null {
  const uid = currentAiUserId();
  if (uid == null) return null;
  return kind === "factor"
    ? `svquant.aiFactor.history.v3.u${uid}`
    : `svquant.aiStrategy.history.v3.u${uid}`;
}

/** 清掉旧版全局共享历史，防止多账号共用同一列表。 */
export function purgeLegacySharedAiHistory() {
  try {
    for (const k of LEGACY_SHARED_KEYS) {
      localStorage.removeItem(k);
    }
  } catch {
    /* ignore */
  }
}

purgeLegacySharedAiHistory();
