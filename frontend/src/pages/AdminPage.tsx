import { useEffect, useState } from "react";
import { ShieldCheck, Users } from "lucide-react";
import { getStoredUser, subscribeAuth, type AuthUser } from "@/lib/auth";
import {
  listAdminUsers,
  resetAdminUserPassword,
  setAdminUserRole,
  setAdminUserStatus,
  type AdminUser,
} from "@/lib/adminUsersApi";
import { MeSystemLogsPanel } from "@/pages/MeSystemLogsPanel";

function fmt(v?: string | null) {
  return v ? v.slice(0, 19).replace("T", " ") : "—";
}

export default function AdminPage() {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  useEffect(() => subscribeAuth(() => setUser(getStoredUser())), []);
  const [tab, setTab] = useState<"users" | "logs">("users");
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    listAdminUsers({ q, status, role, limit: 100 })
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(load, [status, role]);

  if (!user || user.role !== "admin") {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <ShieldCheck className="mx-auto h-8 w-8 text-slate-300" />
        <h1 className="mt-3 text-lg font-semibold text-slate-900">需要管理员权限</h1>
        <p className="mt-2 text-sm text-slate-500">当前账号无权访问管理后台。</p>
      </div>
    );
  }

  const act = async (id: number, fn: () => Promise<void>) => {
    setBusy(id);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header className="rounded-2xl border border-slate-200 bg-white p-6">
        <p className="text-[11px] tracking-[0.18em] text-red-600">ADMIN</p>
        <h1 className="mt-1 text-2xl font-semibold text-slate-900">管理后台</h1>
        <p className="mt-2 text-sm text-slate-500">
          用户管理、角色/状态、重置密码与系统审计。所有写操作写入审计日志。
        </p>
      </header>

      <div className="flex gap-2">
        {[
          ["users", "用户管理", Users],
          ["logs", "系统日志", ShieldCheck],
        ].map(([key, label, Icon]) => {
          const I = Icon as typeof Users;
          return (
            <button
              key={key as string}
              type="button"
              onClick={() => setTab(key as "users" | "logs")}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                tab === key ? "border-red-200 bg-red-50 text-red-600" : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              <I className="h-4 w-4" />
              {label as string}
            </button>
          );
        })}
      </div>

      {error ? <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

      {tab === "logs" ? <MeSystemLogsPanel /> : (
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="用户名 / 邮箱 / 昵称"
              className="min-w-[220px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-2 text-sm">
              <option value="">全部状态</option>
              <option value="active">active</option>
              <option value="disabled">disabled</option>
            </select>
            <select value={role} onChange={(e) => setRole(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-2 text-sm">
              <option value="">全部角色</option>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
            <button type="button" onClick={load} className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
              查询
            </button>
            <span className="text-xs text-slate-400">共 {total} 个用户</span>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-[11px] text-slate-400">
                  <th className="py-2">ID</th>
                  <th className="py-2">用户名</th>
                  <th className="py-2">昵称</th>
                  <th className="py-2">邮箱</th>
                  <th className="py-2">角色</th>
                  <th className="py-2">状态</th>
                  <th className="py-2">创建时间</th>
                  <th className="py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <tr key={u.id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2.5 font-mono text-xs text-slate-400">{u.id}</td>
                    <td className="py-2.5 font-medium text-slate-800">{u.username}</td>
                    <td className="py-2.5 text-slate-600">{u.display_name || "—"}</td>
                    <td className="py-2.5 text-xs text-slate-500">{u.email || "—"}</td>
                    <td className="py-2.5">
                      <span className={`rounded px-1.5 py-0.5 text-[11px] ${u.role === "admin" ? "bg-red-50 text-red-600" : "bg-slate-100 text-slate-600"}`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="py-2.5">
                      <span className={`rounded px-1.5 py-0.5 text-[11px] ${u.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
                        {u.status}
                      </span>
                    </td>
                    <td className="py-2.5 text-xs text-slate-400">{fmt(u.created_at)}</td>
                    <td className="py-2.5">
                      <div className="flex flex-wrap justify-end gap-1">
                        <button
                          type="button"
                          disabled={busy === u.id}
                          onClick={() => act(u.id, () => setAdminUserStatus(u.id, u.status === "active" ? "disabled" : "active"))}
                          className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 disabled:opacity-50"
                        >
                          {u.status === "active" ? "禁用" : "启用"}
                        </button>
                        <button
                          type="button"
                          disabled={busy === u.id}
                          onClick={() => act(u.id, () => setAdminUserRole(u.id, u.role === "admin" ? "user" : "admin"))}
                          className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 disabled:opacity-50"
                        >
                          {u.role === "admin" ? "降为用户" : "设为管理员"}
                        </button>
                        <button
                          type="button"
                          disabled={busy === u.id}
                          onClick={() => {
                            const pwd = window.prompt(`重置 ${u.username} 的密码（至少 6 位）`);
                            if (pwd) act(u.id, () => resetAdminUserPassword(u.id, pwd));
                          }}
                          className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 disabled:opacity-50"
                        >
                          重置密码
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
