import { useState } from "react";
import { ArrowRight, Database, ShieldCheck } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { LocaleToggle, useLocale } from "../i18n";

export default function Register() {
  const { register } = useAuth();
  const { t } = useLocale();
  const nav = useNavigate();
  const loc = useLocation() as any;
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username.trim() || password.length < 8) {
      setError(t("用户名不能为空，密码至少 8 位。", "Username is required and the password must be at least 8 characters."));
      return;
    }
    if (password !== confirm) {
      setError(t("两次输入的密码不一致。", "The passwords do not match."));
      return;
    }
    setBusy(true);
    try {
      await register({
        username: username.trim(),
        password,
        email: email.trim() || undefined,
        display_name: displayName.trim() || username.trim(),
      });
      nav(loc.state?.from || "/", { replace: true });
    } catch (ex: any) {
      setError(ex?.message || t("注册失败", "Registration failed"));
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
        <p>{t("用 SVQuant 账号进入收盘数据、规则摘要与组合体检。公开运行前需完成 ICP 与数据源条款确认。", "Use your SVQuant account for post-close data, rule summaries, and portfolio checkups. Before public launch, ICP registration and data source terms must be finalized.")}</p>
        <div className="login-badges">
          <span><Database size={14} /> {t("收盘数据", "EOD data")}</span>
          <span><ShieldCheck size={14} /> {t("非实时", "Not real-time")}</span>
        </div>
      </div>

      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">
          <h2>{t("创建账号", "Create account")}</h2>
          <span>{t("由 SVQuant 主站创建", "Created via the SVQuant main site")}</span>
        </div>
        <label className="field">
          <span>{t("用户名", "Username")}</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder={t("登录用户名", "Login username")} />
        </label>
        <label className="field">
          <span>{t("显示名（可选）", "Display name (optional)")}</span>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="nickname" placeholder={t("例如：小朱", "e.g. Alex")} />
        </label>
        <label className="field">
          <span>{t("邮箱（可选）", "Email (optional)")}</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder={t("用于找回密码", "Used for password recovery")} />
        </label>
        <label className="field">
          <span>{t("密码", "Password")}</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" placeholder={t("至少 8 位", "At least 8 characters")} />
        </label>
        <label className="field">
          <span>{t("确认密码", "Confirm password")}</span>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" placeholder={t("再输一次", "Enter it again")} />
        </label>
        {error ? <div className="form-error">{error}</div> : null}
        <button className="btn btn-primary w100" disabled={busy} type="submit">
          {busy ? t("创建中…", "Creating…") : t("创建并进入", "Create and enter")} <ArrowRight size={18} />
        </button>
        <p className="login-note">
          {t("演示环境默认不开放注册；设置 ", "Registration is disabled by default in the demo; configuring ")}
          <code>SVQUANT_API_BASE</code>
          {t(" 后代理主站注册。已有账号？", " proxies sign-up to the main site. Already have an account? ")}
          <Link to="/login" className="login-register">{t("返回登录", "Back to login")}</Link>
        </p>
        <div className="login-legal">
          <Link to="/privacy">{t("隐私政策", "Privacy Policy")}</Link>
          <span>·</span>
          <Link to="/terms">{t("用户协议", "Terms of Service")}</Link>
        </div>
      </form>
      <div className="login-foot">{t("SVQuant Invest · 收盘数据 · 非实时 · 不构成投资建议", "SVQuant Invest · EOD data · not real-time · not investment advice")}</div>
    </div>
  );
}
