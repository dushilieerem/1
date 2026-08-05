import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "@/lib/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="kh-panel w-full max-w-sm rounded-2xl p-6 kh-fade-in"
      >
        <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-xs font-bold text-white">
          KH
        </div>
        <h1 className="kh-display mt-3 text-xl font-bold text-[var(--kh-ink)]">知识库平台</h1>
        <p className="mt-1 text-sm text-slate-500">使用 SVQuant 管理员账号登录</p>
        <label className="mt-5 block text-xs font-medium text-slate-600">用户名</label>
        <input
          className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[var(--kh-teal)]"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <label className="mt-3 block text-xs font-medium text-slate-600">密码</label>
        <input
          type="password"
          className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[var(--kh-teal)]"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {err ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="kh-btn-primary mt-5 w-full rounded-xl py-2.5 text-sm font-medium disabled:opacity-50"
        >
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
    </div>
  );
}
