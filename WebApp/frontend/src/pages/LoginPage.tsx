import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { clearSession, login } from "@/lib/auth";
import { clearDetectClientCache, migrateLegacyRunsOnBoot } from "@/lib/detectStore";
import { SoftMeshBackground } from "@/components/landing/LandingVisuals";

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
      <SoftMeshBackground />

      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-lg flex-col justify-center px-4 py-10 sm:px-6 sm:py-16">
        <div className="mb-8 text-center sm:mb-10">
          <p className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            SVQuant
          </p>
          <p className="mt-2 text-sm text-slate-500 sm:mt-3 sm:text-base">从想法到回测</p>
        </div>

        <div className="rounded-2xl border border-white/90 bg-white/85 p-5 shadow-[0_30px_80px_-40px_rgba(15,23,42,0.28)] backdrop-blur-md sm:p-9">
          <h1 className="font-display text-2xl font-semibold text-slate-900">登录</h1>

          <form className="mt-7 space-y-4" onSubmit={onSubmit}>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">用户名</span>
              <input
                className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-red-400 focus:ring-2 focus:ring-red-100"
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
                className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-red-400 focus:ring-2 focus:ring-red-100"
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
              className="landing-wiggle-hover w-full rounded-xl bg-red-600 py-3 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-60"
            >
              {loading ? "登录中…" : "登录"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            还没有账号？{" "}
            <Link to="/register" className="font-semibold text-red-600 hover:text-red-700">
              注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
