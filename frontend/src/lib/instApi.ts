import { clearInstSession, getInstToken } from "./instAuth";

export class InstApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Init = Omit<RequestInit, "body"> & { body?: unknown };

/** 机构端 API：统一带令牌、错误语义与 401 清理。 */
export async function instApi<T = unknown>(path: string, init: Init = {}): Promise<T> {
  const token = getInstToken();
  const headers = new Headers(init.headers || {});
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`/api/inst${path}`, {
    ...init,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (res.status === 401) {
    clearInstSession();
    window.dispatchEvent(new Event("svq:inst-auth-expired"));
  }
  if (!res.ok) {
    const detail =
      (data as { detail?: string; error?: string } | null)?.detail ||
      (data as { error?: string } | null)?.error ||
      `请求失败（${res.status}）`;
    throw new InstApiError(res.status, String(detail));
  }
  return data as T;
}

export const fmtMoney = (value: number | null | undefined, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
};

export const fmtPct = (value: number | null | undefined, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(digits)}%`;
};

export const fmtNum = (value: number | null | undefined, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
};

/** ISO 时间转本地可读格式；无法解析时保留原文，避免丢信息。 */
export const fmtDateTime = (value: string | null | undefined) => {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
};
