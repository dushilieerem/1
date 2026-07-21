import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "@/lib/auth";

export function RegisterPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      await register({
        username: username.trim(),
        password,
        email: email.trim() || undefined,
      });
      navigate("/", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-[calc(100vh-3.5rem)] overflow-hidden">
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url(/login-tech-bg.png)" }}
        aria-hidden
      />
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(15,23,42,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.04) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
        aria-hidden
      />
      <div className="absolute inset-0 bg-gradient-to-br from-sky-50/80 via-white/55 to-cyan-50/70" aria-hidden />

      <div className="relative mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-lg items-center px-4 py-10">
        <div className="w-full rounded-2xl border border-white/70 bg-white/85 p-8 shadow-[0_20px_60px_-24px_rgba(14,116,144,0.35)] backdrop-blur-md">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">创建账号</h1>
          <p className="mt-1.5 text-sm text-slate-500">
            用户名 3–32 位字母数字下划线；密码至少 6 位。
          </p>

          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">用户名</span>
              <input
                className="w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2.5 text-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">密码</span>
              <input
                type="password"
                className="w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2.5 text-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={6}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">邮箱（可选）</span>
              <input
                type="email"
                className="w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2.5 text-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </label>

            {err && (
              <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
                {err}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-gradient-to-r from-sky-600 to-cyan-600 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:from-sky-500 hover:to-cyan-500 disabled:opacity-60"
            >
              {loading ? "提交中…" : "注册并登录"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-slate-500">
            已有账号？{" "}
            <Link to="/login" className="font-semibold text-sky-700 hover:underline">
              去登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
