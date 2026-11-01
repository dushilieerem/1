import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Database, LineChart, ShieldCheck } from "lucide-react";
import { useAuth } from "../auth";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as any;
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo1234");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const registerUrl = (import.meta as any).env?.VITE_REGISTER_URL as string | undefined;
  const forgotUrl =
    ((import.meta as any).env?.VITE_FORGOT_URL as string | undefined) ||
    `${window.location.protocol}//${window.location.hostname}:9530/forgot-password`;

  useEffect(() => {
    if (user) nav(loc.state?.from || "/", { replace: true });
  }, [user, nav, loc.state]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      nav(loc.state?.from || "/", { replace: true });
    } catch (ex: any) {
      setError(ex?.message || "登录失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-hero">
        <div className="brand-mark">SV</div>
        <div className="login-kicker">SVQUANT INVEST</div>
        <h1>先看懂，<em>再决定</em>。</h1>
        <p>收盘后的行情、财务、估值与组合体检。只给信息与风险提示，不构成投资建议。</p>
        <div className="login-badges">
          <span><Database size={14} /> 收盘数据</span>
          <span><LineChart size={14} /> 规则解读</span>
          <span><ShieldCheck size={14} /> 非实时</span>
        </div>
      </div>

      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">
          <h2>登录</h2>
          <span>复用 SVQuant 账号</span>
        </div>
        <label className="field">
          <span>用户名</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="SVQuant 用户名" />
        </label>
        <label className="field">
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            placeholder="密码"
          />
        </label>
        {error ? <div className="form-error">{error}</div> : null}
        <button className="btn btn-primary w100" disabled={busy} type="submit">
          {busy ? "登录中…" : "进入 Invest"} <ArrowRight size={18} />
        </button>
        <div className="demo-hint">
          <b>演示账号</b>
          <code>demo / demo1234</code>
        </div>
        <p className="login-note">
          账号复用 SVQuant，但 H5 是独立会话，需要单独登录。公开运行前需完成 ICP、隐私政策与数据源条款确认。
        </p>
        <div className="login-legal">
          <Link to="/privacy">隐私政策</Link>
          <span>·</span>
          <Link to="/terms">用户协议</Link>
          <span>·</span>
          <a href={forgotUrl} target="_blank" rel="noreferrer">忘记密码</a>
        </div>
        <p className="login-note">
          {registerUrl
            ? <a className="login-register" href={registerUrl}>去 SVQuant 主站注册</a>
            : <Link className="login-register" to="/register">创建 Invest 账号</Link>}
          <span> · 已有账号直接登录</span>
        </p>
      </form>
      <div className="login-foot">SVQuant Invest · 收盘数据 · 非实时 · 不构成投资建议</div>
    </div>
  );
}
