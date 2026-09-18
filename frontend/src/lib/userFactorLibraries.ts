/** 用户自建因子库（与「内置因子库」同级的文件夹）+ 库内因子 */

import { authHeaders, assertAuthConsistency } from "./auth";
import type { FactorMeta } from "./factorCatalog";

export type UserFactorLibrary = {
  id: number;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  factorCount?: number;
};

export type UserLibraryFactor = {
  id: number;
  libraryId: number;
  libraryName: string;
  name: string;
  methodName: string;
  body: string;
  description: string;
  categoryLabel: string;
  /** false = 仅元数据、尚无有效公式（黄色） */
  formulaReady?: boolean;
  createdAt?: string;
  updatedAt?: string;
};

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  assertAuthConsistency();
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const text = await res.text();
  let data: T & { error?: string };
  try {
    data = JSON.parse(text) as T & { error?: string };
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}`);
  }
  if (!res.ok) {
    const rawDetail = (data as unknown as { detail?: unknown }).detail;
    const detail =
      (data as { error?: string }).error ||
      (typeof rawDetail === "string" ? rawDetail : undefined);
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data;
}

export async function listUserFactorLibraries(): Promise<UserFactorLibrary[]> {
  const data = await apiJson<{ libraries: UserFactorLibrary[] }>(
    "/api/factor/libraries",
  );
  return data.libraries || [];
}

export async function createUserFactorLibrary(
  name: string,
): Promise<UserFactorLibrary> {
  const data = await apiJson<{ library: UserFactorLibrary }>(
    "/api/factor/libraries",
    {
      method: "POST",
      body: JSON.stringify({ name }),
    },
  );
  return data.library;
}

export async function deleteUserFactorLibrary(id: number): Promise<void> {
  await apiJson(`/api/factor/libraries/${id}`, { method: "DELETE" });
}

export async function listLibraryFactors(
  libraryId: number,
): Promise<UserLibraryFactor[]> {
  const data = await apiJson<{ factors: UserLibraryFactor[] }>(
    `/api/factor/libraries/${libraryId}/factors`,
  );
  return data.factors || [];
}

export async function listAllUserLibraryFactors(): Promise<UserLibraryFactor[]> {
  const data = await apiJson<{ factors: UserLibraryFactor[] }>(
    "/api/factor/libraries/factors",
  );
  return data.factors || [];
}

export async function addFactorToUserLibrary(
  libraryId: number,
  payload: {
    name: string;
    body: string;
    description?: string;
    categoryLabel?: string;
    formulaReady?: boolean;
  },
): Promise<UserLibraryFactor> {
  const data = await apiJson<{ factor: UserLibraryFactor }>(
    `/api/factor/libraries/${libraryId}/factors`,
    {
      method: "POST",
      body: JSON.stringify({
        name: payload.name,
        body: payload.body,
        description: payload.description || "",
        categoryLabel: payload.categoryLabel || "其他",
        formulaReady: payload.formulaReady,
      }),
    },
  );
  return data.factor;
}

export async function updateUserLibraryFactor(
  libraryId: number,
  factorId: number,
  payload: {
    body?: string;
    description?: string;
    categoryLabel?: string;
    formulaReady?: boolean;
  },
): Promise<UserLibraryFactor> {
  const data = await apiJson<{ factor: UserLibraryFactor }>(
    `/api/factor/libraries/${libraryId}/factors/${factorId}`,
    {
      method: "PUT",
      body: JSON.stringify({
        ...(payload.body !== undefined ? { body: payload.body } : {}),
        ...(payload.description !== undefined
          ? { description: payload.description }
          : {}),
        ...(payload.categoryLabel !== undefined
          ? { categoryLabel: payload.categoryLabel }
          : {}),
        ...(payload.formulaReady !== undefined
          ? { formulaReady: payload.formulaReady }
          : {}),
      }),
    },
  );
  return data.factor;
}

export async function deleteFactorFromUserLibrary(
  libraryId: number,
  factorId: number,
): Promise<void> {
  await apiJson(`/api/factor/libraries/${libraryId}/factors/${factorId}`, {
    method: "DELETE",
  });
}

/** 转为与内置因子同结构的 FactorMeta（样式与内置一致） */
export function userLibraryFactorToMeta(f: UserLibraryFactor): FactorMeta {
  const ready =
    f.formulaReady !== undefined
      ? Boolean(f.formulaReady)
      : Boolean((f.body || "").trim());
  return {
    name: f.name,
    methodName: f.methodName || f.name,
    description: f.description || f.name,
    explain: f.description || f.name,
    formula: "",
    params: {},
    library: `user_lib_${f.libraryId}`,
    libraryFile: "",
    libraryLabel: f.categoryLabel || "其他",
    tags: ["user_library"],
    body: f.body,
    formulaReady: ready,
    userLibraryId: f.libraryId,
    userLibraryName: f.libraryName,
    userLibraryFactorId: f.id,
  };
}
