import { useState } from "react";
import { ArrowRight, Database, ShieldCheck } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Register() {
  const { register } = useAuth();
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
      setError("用户名不能为空，密码至少 8 位。");
      return;
    }
    if (password !== confirm) {
      setError("两次输入的密码不一致。");
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
      setError(ex?.message || "注册失败");
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
        <p>用 SVQuant 账号进入收盘数据、规则摘要与组合体检。公开运行前需完成 ICP 与数据源条款确认。</p>
        <div className="login-badges">
          <span><Database size={14} /> 收盘数据</span>
          <span><ShieldCheck size={14} /> 非实时</span>
        </div>
      </div>

      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">
          <h2>创建账号</h2>
          <span>由 SVQuant 主站创建</span>
        </div>
        <label className="field">
          <span>用户名</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="登录用户名" />
        </label>
        <label className="field">
          <span>显示名（可选）</span>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="nickname" placeholder="例如：小朱" />
        </label>
        <label className="field">
          <span>邮箱（可选）</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="用于找回密码" />
        </label>
        <label className="field">
          <span>密码</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" placeholder="至少 8 位" />
        </label>
        <label className="field">
          <span>确认密码</span>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" placeholder="再输一次" />
        </label>
        {error ? <div className="form-error">{error}</div> : null}
        <button className="btn btn-primary w100" disabled={busy} type="submit">
          {busy ? "创建中…" : "创建并进入"} <ArrowRight size={18} />
        </button>
        <p className="login-note">
          演示环境默认不开放注册；设置 <code>SVQUANT_API_BASE</code> 后代理主站注册。已有账号？<Link to="/login" className="login-register">返回登录</Link>
        </p>
        <div className="login-legal">
          <Link to="/privacy">隐私政策</Link>
          <span>·</span>
          <Link to="/terms">用户协议</Link>
        </div>
      </form>
      <div className="login-foot">SVQuant Invest · 收盘数据 · 非实时 · 不构成投资建议</div>
    </div>
  );
}
