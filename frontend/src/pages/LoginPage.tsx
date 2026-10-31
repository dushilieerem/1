import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { clearSession, login } from "@/lib/auth";
import { instLogin } from "@/lib/instAuth";
import { clearDetectClientCache, migrateLegacyRunsOnBoot } from "@/lib/detectStore";
import { SoftMeshBackground } from "@/components/landing/LandingVisuals";

type Mode = "personal" | "inst";

/** 仅开发环境展示的机构端演示账号；生产构建不会出现 */
const DEMO_ACCOUNTS: [string, string][] = [
  ["inst_manager", "投资经理"],
  ["inst_partner", "合伙人"],
  ["inst_chairman", "Chairman"],
  ["inst_risk", "独立风控"],
  ["inst_execution", "交易执行"],
  ["inst_monitoring", "组合监控"],
];
const DEMO_PASSWORD = "inst123456";

export function LoginPage() {
  const [params] = useSearchParams();
  const [mode, setMode] = useState<Mode>(params.get("mode") === "inst" ? "inst" : "personal");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    setMode(next);
    setErr(null);
    setUsername("");
    setPassword("");
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      if (mode === "inst") {
        await instLogin(username.trim(), password);
        const next = params.get("next") || "/inst";
        window.location.assign(next.startsWith("/inst") ? next : "/inst");
        return;
      }
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

  const isInst = mode === "inst";

  return (
    <div className="relative min-h-[calc(100vh-3.5rem)] overflow-hidden">
      <SoftMeshBackground />

      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-lg flex-col justify-center px-4 py-10 sm:px-6 sm:py-16">
        <div className="mb-8 text-center sm:mb-10">
          <p className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            {isInst ? "旸谷资本" : "SVQuant"}
          </p>
          <p className="mt-2 text-sm text-slate-500 sm:mt-3 sm:text-base">
            {isInst ? "SVQuant 机构端 · 主观价值投资" : "从想法到回测"}
          </p>
        </div>

        <div className="rounded-2xl border border-white/90 bg-white/85 p-5 shadow-[0_30px_80px_-40px_rgba(15,23,42,0.28)] backdrop-blur-md sm:p-9">
          <div className="mb-6 grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={!isInst}
              onClick={() => switchMode("personal")}
              className={`rounded-lg py-2 text-sm font-medium transition ${
                isInst ? "text-slate-500 hover:text-slate-700" : "bg-white text-slate-900 shadow-sm"
              }`}
            >
              个人版
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isInst}
              onClick={() => switchMode("inst")}
              className={`rounded-lg py-2 text-sm font-medium transition ${
                isInst
                  ? "bg-[#0b1220] text-[#e8c98a] shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              机构端
            </button>
          </div>

          <h1 className="font-display text-2xl font-semibold text-slate-900">
            {isInst ? "机构端登录" : "登录"}
          </h1>
          {isInst ? (
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              机构身份与个人版账号通用，权限由机构角色决定；演示环境不产生真实交易。
            </p>
          ) : null}

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
              className={`w-full rounded-xl py-3 text-sm font-semibold text-white transition disabled:opacity-60 ${
                isInst ? "bg-[#0b1220] hover:bg-[#16233a]" : "bg-red-600 hover:bg-red-700"
              }`}
            >
              {loading ? "登录中…" : isInst ? "进入机构端" : "登录"}
            </button>
          </form>

          {isInst && import.meta.env.DEV ? (
            <div className="mt-6 rounded-xl border border-[#e7e3d8] bg-[#faf9f5] p-4">
              <p className="text-[11px] font-medium text-[#8a6a2f]">
                开发环境演示账号（密码 {DEMO_PASSWORD}）
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {DEMO_ACCOUNTS.map(([name, label]) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => {
                      setUsername(name);
                      setPassword(DEMO_PASSWORD);
                      setErr(null);
                    }}
                    className="rounded-lg border border-[#e7e3d8] bg-white px-2 py-1 text-[11px] text-slate-600 transition hover:border-[#c9a15e] hover:text-slate-900"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <p className="mt-6 text-center text-sm text-slate-500">
            {isInst ? (
              "机构账号由管理员开通，不开放自助注册"
            ) : (
              <>
                还没有账号？{" "}
                <Link to="/register" className="font-semibold text-red-600 hover:text-red-700">
                  注册
                </Link>
                <span className="mx-1 text-slate-300">·</span>
                <Link to="/forgot-password" className="font-semibold text-red-600 hover:text-red-700">
                  忘记密码
                </Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
