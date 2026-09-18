import { useCallback, useEffect, useState, Fragment } from "react";
import { ChevronDown, ChevronRight, Download, RefreshCw, Search } from "lucide-react";
import {
  listAdminAuditLogs,
  type AuditLogItem,
  type AuditLogQuery,
} from "@/lib/adminAuditApi";
import { PageJump } from "@/components/PageJump";

const MODULES = [
  "",
  "auth",
  "kh",
  "community",
  "factor",
  "strategy",
  "detect",
  "agent",
  "ai",
  "news",
  "watchlists",
  "re",
  "admin",
  "api",
  "other",
];

type StatusFilter = "" | "4xx" | "5xx" | "exact";
type TimePreset = "" | "1h" | "today";
type QuickFilter = "" | "errors" | "login" | "writes";

function statusClass(code?: number | null) {
  if (code == null) return "text-slate-500";
  if (code >= 500) return "text-rose-600";
  if (code >= 400) return "text-amber-600";
  return "text-emerald-600";
}

function fmtTime(iso?: string | null) {
  if (!iso) return "—";
  return iso.slice(0, 19).replace("T", " ");
}

function startOfTodayIso(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function hoursAgoIso(h: number): string {
  return new Date(Date.now() - h * 3600_000).toISOString();
}

function csvEscape(v: string): string {
  if (/[",\n\r]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

/** 管理仓 · 系统日志：准实时刷新，仅 admin 可见 */
export function MeSystemLogsPanel() {
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [module, setModule] = useState("");
  const [username, setUsername] = useState("");
  const [path, setPath] = useState("");
  const [action, setAction] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [statusExact, setStatusExact] = useState("");
  const [timePreset, setTimePreset] = useState<TimePreset>("");
  const [quick, setQuick] = useState<QuickFilter>("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const limit = 40;

  const queryBase = useCallback((): AuditLogQuery => {
    const q: AuditLogQuery = {
      module: module || undefined,
      username: username.trim() || undefined,
      path: path.trim() || undefined,
      action: action.trim() || undefined,
    };

    if (timePreset === "1h") q.since = hoursAgoIso(1);
    else if (timePreset === "today") q.since = startOfTodayIso();

    if (quick === "errors") {
      q.statusMin = 400;
    } else if (quick === "login") {
      q.action = "auth.login";
      q.module = q.module || "auth";
    } else if (quick === "writes") {
      q.writeOnly = true;
    }

    if (quick !== "errors") {
      if (statusFilter === "4xx") {
        q.statusMin = 400;
        q.statusMax = 499;
      } else if (statusFilter === "5xx") {
        q.statusMin = 500;
        q.statusMax = 599;
      } else if (statusFilter === "exact") {
        const n = Number(statusExact);
        if (Number.isFinite(n) && n > 0) q.statusCode = n;
      }
    }

    return q;
  }, [
    module,
    username,
    path,
    action,
    statusFilter,
    statusExact,
    timePreset,
    quick,
  ]);

  const reload = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await listAdminAuditLogs({
        ...queryBase(),
        limit,
        offset,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [queryBase, offset]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = window.setInterval(() => {
      void reload();
    }, 8000);
    return () => window.clearInterval(t);
  }, [autoRefresh, reload]);

  const pages = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;

  const applyQuick = (next: QuickFilter) => {
    setOffset(0);
    setQuick(next);
    if (next === "errors") setStatusFilter("");
    if (next === "login") {
      setAction("");
    }
  };

  const exportCsv = async () => {
    try {
      const data = await listAdminAuditLogs({
        ...queryBase(),
        limit: 200,
        offset: 0,
      });
      const header = [
        "时间",
        "用户",
        "角色",
        "动作",
        "模块",
        "方法",
        "路径",
        "状态",
        "耗时ms",
        "IP",
        "说明",
        "请求ID",
      ];
      const lines = [header.join(",")];
      for (const row of data.items) {
        lines.push(
          [
            fmtTime(row.createdAt),
            row.username || "",
            row.role || "",
            row.action || "",
            row.module || "",
            row.method || "",
            row.path || "",
            row.statusCode != null ? String(row.statusCode) : "",
            row.durationMs != null ? String(row.durationMs) : "",
            row.ip || "",
            row.detail || "",
            row.requestId || "",
          ]
            .map((x) => csvEscape(String(x)))
            .join(","),
        );
      }
      const blob = new Blob(["\uFEFF" + lines.join("\n")], {
        type: "text/csv;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `系统日志_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-slate-50/80 p-3">
        <label className="text-xs text-slate-600">
          模块
          <select
            className="mt-1 block rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={module}
            onChange={(e) => {
              setOffset(0);
              setModule(e.target.value);
            }}
          >
            <option value="">全部</option>
            {MODULES.filter(Boolean).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-600">
          用户名
          <input
            className="mt-1 block w-32 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={username}
            placeholder="用户名"
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setOffset(0);
                void reload();
              }
            }}
          />
        </label>
        <label className="text-xs text-slate-600">
          动作包含
          <input
            className="mt-1 block w-36 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={action}
            placeholder="动作"
            onChange={(e) => setAction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setOffset(0);
                void reload();
              }
            }}
          />
        </label>
        <label className="text-xs text-slate-600">
          路径包含
          <input
            className="mt-1 block w-40 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={path}
            placeholder="路径"
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setOffset(0);
                void reload();
              }
            }}
          />
        </label>
        <label className="text-xs text-slate-600">
          状态码
          <select
            className="mt-1 block rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={statusFilter}
            onChange={(e) => {
              setOffset(0);
              setQuick("");
              setStatusFilter(e.target.value as StatusFilter);
            }}
          >
            <option value="">全部</option>
            <option value="4xx">4xx</option>
            <option value="5xx">5xx</option>
            <option value="exact">指定</option>
          </select>
        </label>
        {statusFilter === "exact" ? (
          <label className="text-xs text-slate-600">
            指定码
            <input
              className="mt-1 block w-20 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
              value={statusExact}
              placeholder="502"
              onChange={(e) => setStatusExact(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setOffset(0);
                  void reload();
                }
              }}
            />
          </label>
        ) : null}
        <label className="text-xs text-slate-600">
          时间
          <select
            className="mt-1 block rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={timePreset}
            onChange={(e) => {
              setOffset(0);
              setTimePreset(e.target.value as TimePreset);
            }}
          >
            <option value="">全部</option>
            <option value="1h">近 1 小时</option>
            <option value="today">今天</option>
          </select>
        </label>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-lg bg-[var(--brand,#0f766e)] px-3 py-1.5 text-sm text-white"
          onClick={() => {
            setOffset(0);
            void reload();
          }}
        >
          <Search className="h-3.5 w-3.5" />
          查询
        </button>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700"
          onClick={() => void reload()}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700"
          onClick={() => void exportCsv()}
        >
          <Download className="h-3.5 w-3.5" />
          导出 CSV
        </button>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          每 8 秒自动刷新
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["", "全部"],
            ["errors", "仅错误"],
            ["login", "仅登录"],
            ["writes", "仅写操作"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={label}
            type="button"
            className={`rounded-lg border px-2.5 py-1 text-xs ${
              quick === key
                ? "border-[var(--brand,#0f766e)] bg-teal-50 text-teal-800"
                : "border-slate-200 bg-white text-slate-600"
            }`}
            onClick={() => applyQuick(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <p className="text-sm text-slate-600">共 {total} 条</p>

      {err ? <p className="text-sm text-rose-600">{err}</p> : null}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[960px] text-left text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>
              <th className="w-8 px-2 py-2" />
              <th className="whitespace-nowrap px-3 py-2 font-medium">时间</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">用户</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">动作</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">模块</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">路径</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">状态</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">耗时</th>
              <th className="whitespace-nowrap px-3 py-2 font-medium">IP</th>
              <th className="px-3 py-2 font-medium">说明</th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-3 py-10 text-center text-slate-400">
                  加载中…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-3 py-10 text-center text-slate-400">
                  暂无日志（登录或做一次写操作后再看）
                </td>
              </tr>
            ) : (
              items.map((row) => {
                const open = expanded === row.id;
                return (
                  <Fragment key={row.id}>
                    <tr className="border-t border-slate-100 hover:bg-slate-50/80">
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          aria-label={open ? "收起" : "展开"}
                          onClick={() => setExpanded(open ? null : row.id)}
                        >
                          {open ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </button>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                        {fmtTime(row.createdAt)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        <span className="font-medium text-slate-800">
                          {row.username || "游客"}
                        </span>
                        {row.role && row.role !== row.username ? (
                          <span className="ml-1 text-[10px] text-slate-400">
                            {row.role}
                          </span>
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-700">
                        {row.action}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-600">
                        {row.module || "—"}
                      </td>
                      <td
                        className="max-w-[220px] truncate px-3 py-2 font-mono text-xs text-slate-600"
                        title={row.path || ""}
                      >
                        {row.method ? `${row.method} ` : ""}
                        {row.path || "—"}
                      </td>
                      <td
                        className={`whitespace-nowrap px-3 py-2 font-mono text-xs ${statusClass(row.statusCode)}`}
                      >
                        {row.statusCode ?? "—"}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                        {row.durationMs != null ? `${row.durationMs}ms` : "—"}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                        {row.ip || "—"}
                      </td>
                      <td
                        className="max-w-[180px] truncate px-3 py-2 text-xs text-slate-500"
                        title={row.detail || ""}
                      >
                        {row.detail || "—"}
                      </td>
                    </tr>
                    {open ? (
                      <tr className="border-t border-slate-50 bg-slate-50/60">
                        <td colSpan={10} className="px-4 py-3 text-xs text-slate-600">
                          <div className="grid gap-1 sm:grid-cols-2">
                            <div>
                              <span className="text-slate-400">完整路径：</span>
                              <span className="font-mono break-all">
                                {row.method ? `${row.method} ` : ""}
                                {row.path || "—"}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400">说明：</span>
                              {row.detail || "—"}
                            </div>
                            <div>
                              <span className="text-slate-400">资源：</span>
                              <span className="font-mono break-all">
                                {row.resource || "—"}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400">用户 ID：</span>
                              {row.userId != null ? row.userId : "—"}
                            </div>
                            <div>
                              <span className="text-slate-400">请求 ID：</span>
                              <span className="font-mono">
                                {row.requestId || "—"}
                              </span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {total > limit ? (
        <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
          <button
            type="button"
            disabled={offset <= 0 || loading}
            className="rounded border border-slate-200 px-2 py-1 disabled:opacity-40"
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            上一页
          </button>
          <span className="px-1 text-xs tabular-nums text-slate-500">
            {page} / {pages}
          </span>
          <button
            type="button"
            disabled={offset + limit >= total || loading}
            className="rounded border border-slate-200 px-2 py-1 disabled:opacity-40"
            onClick={() => setOffset(offset + limit)}
          >
            下一页
          </button>
          <PageJump
            page={page}
            totalPages={pages}
            onJump={(p) => setOffset((p - 1) * limit)}
          />
        </div>
      ) : null}
    </div>
  );
}
