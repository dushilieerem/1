import { researchFetch as fetch } from "./researchClient";
/** 用户自建策略库（与内置策略库同级） */

import { authHeaders, assertAuthConsistency } from "./researchClient";

export type UserStrategyLibrary = {
  id: number;
  name: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  strategyCount?: number;
};

export type UserLibraryStrategy = {
  id: number;
  libraryId: number;
  libraryName: string;
  name: string;
  codeId: string;
  body: string;
  description: string;
  categoryLabel: string;
  sourceRunId?: string;
  hasArchiveReport?: boolean;
  archiveFinishedAt?: string | null;
  /** 首次回测完成时间；空则列表显示「待检测」 */
  detectedAt?: string | null;
  pendingDetect?: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
};

async function apiJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  assertAuthConsistency();
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

export async function listUserStrategyLibraries(): Promise<UserStrategyLibrary[]> {
  const data = await apiJson<{ libraries: UserStrategyLibrary[] }>(
    "/api/strategy/libraries",
  );
  return data.libraries || [];
}

export async function createUserStrategyLibrary(
  name: string,
): Promise<UserStrategyLibrary> {
  const data = await apiJson<{ library: UserStrategyLibrary }>(
    "/api/strategy/libraries",
    { method: "POST", body: JSON.stringify({ name }) },
  );
  return data.library;
}

export async function deleteUserStrategyLibrary(id: number): Promise<void> {
  await apiJson(`/api/strategy/libraries/${id}`, { method: "DELETE" });
}

export async function listStrategyLibraryItems(
  libraryId: number,
): Promise<UserLibraryStrategy[]> {
  const data = await apiJson<{ strategies: UserLibraryStrategy[] }>(
    `/api/strategy/libraries/${libraryId}/strategies`,
  );
  return data.strategies || [];
}

export async function addStrategyToUserLibrary(
  libraryId: number,
  payload: {
    name: string;
    body: string;
    description?: string;
    categoryLabel?: string;
    codeId?: string;
    sourceRunId?: string;
    archiveRequest?: Record<string, unknown>;
    archiveResult?: Record<string, unknown>;
    archiveElapsedSec?: number;
    archiveFinishedAt?: string;
  },
): Promise<UserLibraryStrategy> {
  const data = await apiJson<{ strategy: UserLibraryStrategy }>(
    `/api/strategy/libraries/${libraryId}/strategies`,
    {
      method: "POST",
      body: JSON.stringify({
        name: payload.name,
        body: payload.body,
        description: payload.description || "",
        categoryLabel: payload.categoryLabel || "其他",
        codeId: payload.codeId || "",
        sourceRunId: payload.sourceRunId || "",
        archiveRequest: payload.archiveRequest,
        archiveResult: payload.archiveResult,
        archiveElapsedSec: payload.archiveElapsedSec,
        archiveFinishedAt: payload.archiveFinishedAt || "",
      }),
    },
  );
  return data.strategy;
}

export async function getLibraryStrategyArchive(
  strategyId: number,
): Promise<import("./strategyStore").StrategyRunRecord> {
  const data = await apiJson<{
    run: import("./strategyStore").StrategyRunRecord;
  }>(`/api/strategy/library-strategies/${strategyId}/archive`);
  return data.run;
}

/** 回测成功后清除用户库策略的「待检测」 */
export async function markUserLibraryStrategyDetected(
  strategyId: number,
): Promise<UserLibraryStrategy> {
  const data = await apiJson<{ strategy: UserLibraryStrategy }>(
    `/api/strategy/library-strategies/${strategyId}/mark-detected`,
    { method: "POST", body: "{}" },
  );
  return data.strategy;
}

export async function deleteStrategyFromUserLibrary(
  libraryId: number,
  strategyId: number,
): Promise<void> {
  await apiJson(
    `/api/strategy/libraries/${libraryId}/strategies/${strategyId}`,
    { method: "DELETE" },
  );
}
