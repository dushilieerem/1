import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { clearSession, login } from "@/lib/auth";
import { clearDetectClientCache, migrateLegacyRunsOnBoot } from "@/lib/detectStore";

export function LoginPage() {
  const [params] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      clearSession();
      clearDetectClientCache();
      migrateLegacyRunsOnBoot();
      await login(username.trim(), password);
      const next = params.get("next") || "/";
      window.location.assign(next.startsWith("/") ? next : "/");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
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
      <div className="pointer-events-none absolute -left-20 top-10 h-72 w-72 rounded-full bg-cyan-300/25 blur-3xl" aria-hidden />
      <div className="pointer-events-none absolute bottom-0 right-0 h-80 w-80 rounded-full bg-sky-400/20 blur-3xl" aria-hidden />

      <div className="relative mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-6xl flex-col items-stretch gap-8 px-4 py-10 lg:flex-row lg:items-center lg:gap-12 lg:px-8">
        <div className="flex flex-1 flex-col justify-center lg:pr-4">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700/80">
            Research Engine · Factor Lab
          </p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl lg:text-[2.75rem] lg:leading-tight">
            SVQuant
            <span className="mt-2 block text-lg font-semibold text-slate-600 sm:text-xl">
              可验证的因子研究工作台
            </span>
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-600 sm:text-base">
            因子库 · 面板对比 · 一键检测。
          </p>
        </div>

        <div className="w-full max-w-md shrink-0 lg:ml-auto">
          <div className="rounded-2xl border border-white/70 bg-white/85 p-8 shadow-[0_20px_60px_-24px_rgba(14,116,144,0.35)] backdrop-blur-md">
            <h2 className="text-xl font-bold tracking-tight text-slate-900">登录账号</h2>

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
                  autoComplete="current-password"
                  required
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
                {loading ? "登录中…" : "登录"}
              </button>
            </form>

            <p className="mt-5 text-center text-sm text-slate-500">
              还没有账号？{" "}
              <Link to="/register" className="font-semibold text-sky-700 hover:underline">
                注册
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
