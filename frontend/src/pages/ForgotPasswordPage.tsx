import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
  return data as T;
}

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const requestReset = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const data = await post<{ ok: boolean; message: string; reset_token?: string }>(
        "/api/auth/forgot-password",
        { identifier },
      );
      setMsg(data.message);
      if (data.reset_token) {
        setToken(data.reset_token);
        setMsg(`${data.message}（开发环境已返回 token，可直接重置）`);
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  };

  const doReset = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await post("/api/auth/reset-password", { token, password });
      setMsg("密码已重置，请返回登录。");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md py-10">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">找回密码</h1>
        <p className="mt-2 text-sm text-slate-500">
          输入用户名或绑定邮箱。生产环境会通过邮件发送重置方式；未接 SMTP 时由管理员在后台重置。
        </p>

        {msg ? <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{msg}</div> : null}
        {err ? <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{err}</div> : null}

        <form onSubmit={requestReset} className="mt-5 space-y-3">
          <input
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            placeholder="用户名或邮箱"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            required
          />
          <button type="submit" disabled={busy} className="w-full rounded-lg bg-slate-900 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
            {busy ? "提交中…" : "申请重置"}
          </button>
        </form>

        {token ? (
          <form onSubmit={doReset} className="mt-5 space-y-3 border-t border-slate-100 pt-5">
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="重置 token"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs"
              required
            />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              placeholder="新密码（至少 6 位）"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              required
            />
            <button type="submit" disabled={busy} className="w-full rounded-lg bg-red-600 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
              {busy ? "重置中…" : "重置密码"}
            </button>
          </form>
        ) : null}

        <p className="mt-5 text-center text-sm text-slate-500">
          <Link to="/login" className="text-red-600 hover:text-red-700">返回登录</Link>
        </p>
      </div>
    </div>
  );
}
