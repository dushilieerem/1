import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Database, LineChart, ShieldCheck } from "lucide-react";
import { useAuth } from "../auth";
import { LocaleToggle, useLocale } from "../i18n";

export default function Login() {
  const { user, login } = useAuth();
  const { t } = useLocale();
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
      setError(ex?.message || t("登录失败", "Login failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div style={{ position: "fixed", top: "calc(12px + env(safe-area-inset-top))", right: 14, zIndex: 10 }}>
        <LocaleToggle />
      </div>
      <div className="login-hero">
        <div className="brand-mark">SV</div>
        <div className="login-kicker">SVQUANT INVEST</div>
        <h1>{t("先看懂，", "Understand first, ")}<em>{t("再决定", "decide after")}</em>{t("。", ".")}</h1>
        <p>{t("收盘后的行情、财务、估值与组合体检。只给信息与风险提示，不构成投资建议。", "Post-close quotes, financials, valuation, and portfolio checkups. Information and risk disclosure only—not investment advice.")}</p>
        <div className="login-badges">
          <span><Database size={14} /> {t("收盘数据", "EOD data")}</span>
          <span><LineChart size={14} /> {t("规则解读", "Rule-based insight")}</span>
          <span><ShieldCheck size={14} /> {t("非实时", "Not real-time")}</span>
        </div>
      </div>

      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">
          <h2>{t("登录", "Log in")}</h2>
          <span>{t("复用 SVQuant 账号", "Use your SVQuant account")}</span>
        </div>
        <label className="field">
          <span>{t("用户名", "Username")}</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder={t("SVQuant 用户名", "SVQuant username")} />
        </label>
        <label className="field">
          <span>{t("密码", "Password")}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            placeholder={t("密码", "Password")}
          />
        </label>
        {error ? <div className="form-error">{error}</div> : null}
        <button className="btn btn-primary w100" disabled={busy} type="submit">
          {busy ? t("登录中…", "Logging in…") : t("进入 Invest", "Enter Invest")} <ArrowRight size={18} />
        </button>
        <div className="demo-hint">
          <b>{t("演示账号", "Demo account")}</b>
          <code>demo / demo1234</code>
        </div>
        <p className="login-note">
          {t("账号复用 SVQuant，但 H5 是独立会话，需要单独登录。公开运行前需完成 ICP、隐私政策与数据源条款确认。", "Your account is shared with SVQuant, but H5 runs a separate session and requires its own login. Before public launch, ICP registration, privacy policy, and data source terms must be finalized.")}
        </p>
        <div className="login-legal">
          <Link to="/privacy">{t("隐私政策", "Privacy Policy")}</Link>
          <span>·</span>
          <Link to="/terms">{t("用户协议", "Terms of Service")}</Link>
          <span>·</span>
          <a href={forgotUrl} target="_blank" rel="noreferrer">{t("忘记密码", "Forgot password")}</a>
        </div>
        <p className="login-note">
          {registerUrl
            ? <a className="login-register" href={registerUrl}>{t("去 SVQuant 主站注册", "Sign up on the SVQuant main site")}</a>
            : <Link className="login-register" to="/register">{t("创建 Invest 账号", "Create an Invest account")}</Link>}
          <span> · {t("已有账号直接登录", "Already have an account? Log in")}</span>
        </p>
      </form>
      <div className="login-foot">{t("SVQuant Invest · 收盘数据 · 非实时 · 不构成投资建议", "SVQuant Invest · EOD data · not real-time · not investment advice")}</div>
    </div>
  );
}
