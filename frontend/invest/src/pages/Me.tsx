import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Bell, ChevronRight, Download, FileText, Info, LogOut, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { api, getToken } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, Kv, PageHeader, Sheet, Tag } from "../components";
import { humanizeEnum } from "../lib";
import { useToast } from "../toast";
import { useLocale, withMarket } from "../i18n";

export default function Me() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const { t, market } = useLocale();
  const displayName = user?.display_name === "演示用户"
    ? t("演示用户", "Demo user")
    : user?.display_name || t("演示用户", "Demo user");
  const [risk, setRisk] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [riskOpen, setRiskOpen] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [aiMemory, setAiMemory] = useState<any>(() => {
    try {
      return JSON.parse(localStorage.getItem("svq_ai_memory") || "{}");
    } catch {
      return {};
    }
  });

  useEffect(() => {
    api("/api/invest/risk-profile").then(setRisk).catch(() => {});
    api(withMarket("/api/invest/meta", market)).then(setMeta).catch(() => {});
    api("/api/invest/data-quality").then(setQuality).catch(() => {});
  }, [market]);

  const exportData = async () => {
    try {
      const token = getToken();
      const res = await fetch("/api/invest/account/export", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(t(`导出失败（${res.status}）`, `Export failed (${res.status})`));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "svquant-invest-data.json";
      a.click();
      URL.revokeObjectURL(url);
      toast(t("已生成数据文件", "Data file generated"));
    } catch (e: any) {
      toast(e.message || t("导出失败", "Export failed"));
    }
  };

  const deleteData = async () => {
    if (!window.confirm(t("删除 Invest 的自选、持仓、事件与风测数据？此操作不可撤销，SVQuant 账号本身不会被删除。", "Delete Invest watchlist, holdings, events, and risk-profile data? This cannot be undone. Your SVQuant account itself will not be deleted."))) return;
    try {
      await api("/api/invest/account/data", { method: "DELETE" });
      setRisk(null);
      toast(t("Invest 数据已删除", "Invest data deleted"));
    } catch (e: any) {
      toast(e.message || t("删除失败", "Delete failed"));
    }
  };

  return (
    <div className="page">
      <PageHeader title={t("我的", "Me")} sub={t("账号、数据与合规", "Account, data & compliance")} />

      <section className="me-card">
        <div className="me-avatar">{(displayName || t("演", "D")).slice(0, 1)}</div>
        <div className="me-info">
          <h2>{displayName}</h2>
          <p>@{user?.username} · {t("复用 SVQuant 账号", "uses your SVQuant account")}</p>
          <div className="me-tags"><Tag tone="red">{t("演示环境", "Demo environment")}</Tag><Tag tone="gray">{t("独立 H5 会话", "Separate H5 session")}</Tag></div>
        </div>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>{t("风险测评", "Risk profile")}</h2><span className="hint">{t("用于组合体检展示", "Shown in portfolio checkups")}</span></div>
        {risk?.level ? (
          <>
            <div className="risk-profile-row">
              <div><span>{t("风险等级", "Risk level")}</span><b>{humanizeEnum(risk.level)}</b></div>
              <div><span>{t("风险分", "Risk score")}</span><b>{risk.score}</b></div>
            </div>
            <button className="btn btn-ghost w100" onClick={() => setRiskOpen(true)}>{t("重新测评", "Retake assessment")}</button>
          </>
        ) : (
          <button className="btn btn-primary w100" onClick={() => setRiskOpen(true)}>{t("开始测评", "Start assessment")}</button>
        )}
      </section>

      <section className="card">
        <div className="card-title-row"><h2>{t("数据与口径", "Data & definitions")}</h2><Tag tone={meta?.isDemo ? "amber" : "green"}>{meta?.isDemo ? t("演示数据", "Demo data") : t("公开 EOD", "Public EOD")}</Tag></div>
        <Kv k={t("数据日期", "Data date")} v={meta?.dataDate || "2026-10-23"} />
        <Kv k={t("数据来源", "Data source")} v={meta?.source ? humanizeEnum(meta.source) : t("本地演示数据", "Local demo data")} />
        <Kv k={t("更新时间", "Updated at")} v={meta?.updatedAt || "2026-10-26 18:30"} />
        <Kv k={t("行情口径", "Quote basis")} v={t("前复权 · 收盘快照 · 非实时", "Forward-adjusted · close snapshot · not real-time")} />
        <Kv k={t("质量检查", "Quality check")} v={quality ? (quality.ok ? (quality.checks?.some?.((c: any) => c.status === "warn") ? t("通过（有提醒）", "Passed (with warnings)") : t("通过", "Passed")) : t("有异常", "Issues found")) : t("检查中", "Checking")} />
        <Kv k={t("数据新鲜度", "Data freshness")} v={meta ? (meta.isStale ? t(`落后 ${meta.ageTradingDays ?? meta.ageDays} 个交易日`, `${meta.ageTradingDays ?? meta.ageDays} trading day(s) behind`) : t("T-0 / 正常", "T-0 / Normal")) : t("检查中", "Checking")} />
        {meta?.disabledModules?.length ? <Kv k={t("模块状态", "Module status")} v={t(`临时关闭：${meta.disabledModules.join("、")}`, `Temporarily disabled: ${meta.disabledModules.join(", ")}`)} /> : null}
        {!quality ? (
          <p className="hint">
            {t(
              "正在检查数据质量，不阻塞页面其他内容。",
              "Checking data quality; the rest of the page stays available.",
            )}
          </p>
        ) : null}
        {quality && !quality.ok ? (
          <p className="hint">
            {t(
              "数据质量检查有异常：当页缺失字段不会填 0，会显示 — 或「待补充」；具体修复由数据平台跟进。",
              "The data quality check found issues. Missing fields are not filled with 0; they show — or “pending”. The data platform owns the fix.",
            )}
          </p>
        ) : null}
        {quality?.checks?.length ? (
          <div className="quality-list">
            {quality.checks.map((c: any) => (
              <div className="quality-row" key={c.key || c.label}>
                <div>
                  <b>{c.label}</b>
                  <span>{c.detail}</span>
                </div>
                <Tag tone={c.status === "pass" ? "green" : c.status === "warn" ? "amber" : "red"}>
                  {c.status === "pass" ? t("通过", "Passed") : c.status === "warn" ? t("提醒", "Warning") : t("异常", "Failed")}
                </Tag>
              </div>
            ))}
          </div>
        ) : null}
        <div className="hint">
          {meta?.isDemo
            ? t("当前为演示数据，不代表真实行情；公开运行前需逐源核对数据条款。", "Currently using demo data, not real market quotes; source terms must be verified before public launch.")
            : t("行情/财务/估值来自公开 EOD；主题为成分股等权代理，公告/研报/要闻为公开标题。", "Quotes/financials/valuation come from public EOD data; themes are equal-weight proxies of constituents; filings/research/news are public headlines.")}
        </div>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>{t("AI 记忆", "AI memory")}</h2><span className="hint">{t("仅存本机", "Stored locally only")}</span></div>
        <p className="muted small">
          {aiMemory?.lastStock
            ? t(`上一标的：${aiMemory.lastStock.name || aiMemory.lastStock.code}（${aiMemory.lastStock.code}）`, `Last symbol: ${aiMemory.lastStock.name || aiMemory.lastStock.code} (${aiMemory.lastStock.code})`)
            : t("暂无会话记忆；AI 不会保留跨会话推断。", "No session memory; AI does not keep inferences across sessions.")}
        </p>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            try {
              localStorage.removeItem("svq_ai_memory");
            } catch {
              /* ignore */
            }
            setAiMemory({});
            toast(t("AI 会话记忆已清除", "AI session memory cleared"));
          }}
        >
          <Trash2 size={14} /> {t("清除 AI 记忆", "Clear AI memory")}
        </button>
      </section>

      <div className="menu">
        <button className="menu-item" onClick={() => nav("/quant")}>
          <FileText size={18} /><span>{t("量化研究", "Quant research")}</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => nav("/paper")}>
          <FileText size={18} /><span>{t("模拟盘", "Paper trading")}</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => nav("/notifications")}>
          <Bell size={18} /><span>{t("消息通知", "Notifications")}</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => setPrivacyOpen(true)}>
          <ShieldCheck size={18} /><span>{t("隐私与协议", "Privacy & terms")}</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => setAboutOpen(true)}>
          <Info size={18} /><span>{t("关于 SVQuant Invest", "About SVQuant Invest")}</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => window.open("/support", "_blank", "noopener")}>
          <FileText size={18} /><span>{t("客服与工单", "Support & tickets")}</span><ChevronRight size={16} />
        </button>
      </div>

      <div className="menu">
        <button className="menu-item" onClick={exportData}>
          <Download size={18} /><span>{t("导出 Invest 数据", "Export Invest data")}</span><ChevronRight size={16} />
        </button>
        <button className="menu-item danger" onClick={deleteData}>
          <Trash2 size={18} /><span>{t("删除 Invest 数据", "Delete Invest data")}</span><ChevronRight size={16} />
        </button>
      </div>

      <div className="menu">
        <button className="menu-item danger" onClick={() => setDeleteOpen(true)}>
          <Trash2 size={18} /><span>{t("注销 SVQuant 账号", "Delete SVQuant account")}</span><ChevronRight size={16} />
        </button>
      </div>

      <button className="btn btn-ghost w100 logout" onClick={logout}>
        <LogOut size={16} /> {t("退出登录", "Log out")}
      </button>

      <div className="callout">
        <AlertTriangle size={15} /><span><b>{t("边界：", "Boundary: ")}</b>{t("本产品只提供信息与教育内容，不提供买卖建议、目标价、收益承诺，不代客理财，不自动调仓。", "This product provides information and education only. It offers no buy/sell advice, target prices, or return promises, does not manage money, and does not rebalance automatically.")}</span>
      </div>
      <Disclaimer>{t("演示环境 · 不接券商 · 不产生真实委托", "Demo environment · no broker connection · no real orders")}</Disclaimer>

      <AccountDeleteSheet
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onDone={() => { setDeleteOpen(false); logout(); nav("/login", { replace: true }); }}
      />
      <RiskSheet open={riskOpen} onClose={() => setRiskOpen(false)} onSaved={(next) => { setRisk(next); setRiskOpen(false); toast(t("测评已保存", "Assessment saved")); }} />
      <PrivacySheet open={privacyOpen} onClose={() => setPrivacyOpen(false)} onOpenFull={() => { setPrivacyOpen(false); nav("/privacy"); }} />
      <Sheet open={aboutOpen} onClose={() => setAboutOpen(false)} title={t("关于", "About")} sub="SVQuant Invest · MVP">
        <p className="muted small">
          {t("独立手机版 H5，复用 SVQuant 账号。当前为收盘后数据与规则解读，不含 AI 生成内容、不含实时行情、不含推送。", "A standalone mobile H5 that reuses your SVQuant account. It currently offers post-close data and rule-based interpretation, with no AI-generated content, no real-time quotes, and no push notifications.")}
        </p>
        <div className="divider" />
        <Kv k={t("版本", "Version")} v="0.1.0-demo" />
        <Kv k={t("数据", "Data")} v={t("本地演示数据", "Local demo data")} />
        <Kv k={t("合规", "Compliance")} v={t("非投资建议 / 非实时", "Not investment advice / not real-time")} />
      </Sheet>
    </div>
  );
}

function RiskSheet({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: (r: any) => void }) {
  const toast = useToast();
  const { t } = useLocale();
  const [horizon, setHorizon] = useState("3-5年");
  const [loss, setLoss] = useState("10%");
  const [experience, setExperience] = useState("3年以上");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const score = Math.min(95, 25 + (horizon === "3-5年" ? 25 : horizon === "5年以上" ? 35 : 15) + (loss === "20%" ? 25 : loss === "10%" ? 18 : 10) + (experience === "3年以上" ? 20 : experience === "1-3年" ? 13 : 6));
      const level = score >= 75 ? "进取型" : score >= 55 ? "稳健型" : "保守型";
      const data = await api("/api/invest/risk-profile", { method: "POST", body: JSON.stringify({ level, score, answers: { horizon, loss, experience } }) });
      onSaved(data);
    } catch (e: any) {
      toast(e.message || t("保存失败", "Save failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("风险测评", "Risk profile")} sub={t("3 个问题 · 自报结果", "3 questions · self-reported")} footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy}>{busy ? t("保存中…", "Saving…") : t("保存测评", "Save assessment")}</button>}>
      <label className="field"><span>{t("投资期限", "Investment horizon")}</span><select value={horizon} onChange={(e) => setHorizon(e.target.value)}><option value="1年以内">{t("1年以内", "Within 1 year")}</option><option value="1-3年">{t("1-3年", "1–3 years")}</option><option value="3-5年">{t("3-5年", "3–5 years")}</option><option value="5年以上">{t("5年以上", "5+ years")}</option></select></label>
      <label className="field"><span>{t("可承受最大亏损", "Maximum acceptable loss")}</span><select value={loss} onChange={(e) => setLoss(e.target.value)}><option value="5%">5%</option><option value="10%">10%</option><option value="20%">20%</option><option value="30%以上">{t("30%以上", "30%+")}</option></select></label>
      <label className="field"><span>{t("投资经验", "Investment experience")}</span><select value={experience} onChange={(e) => setExperience(e.target.value)}><option value="1年以内">{t("1年以内", "Within 1 year")}</option><option value="1-3年">{t("1-3年", "1–3 years")}</option><option value="3年以上">{t("3年以上", "3+ years")}</option></select></label>
      <div className="callout blue"><b>{t("说明：", "Note: ")}</b>{t("测评只用于组合体检文案与风险提示，不构成适当性结论；公开版需接合规适当性流程。", "This assessment is used only for portfolio checkup copy and risk warnings; it is not a suitability conclusion. The public version must integrate a compliant suitability process.")}</div>
    </Sheet>
  );
}

function AccountDeleteSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t } = useLocale();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/auth/account/delete", {
        method: "POST",
        body: JSON.stringify({ password, confirm }),
      });
      onDone();
    } catch (e: any) {
      setMsg(e.message || t("注销失败", "Account deletion failed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("注销 SVQuant 账号", "Delete SVQuant account")}
      sub={t("不可恢复 · 同时影响主站与 H5", "Irreversible · affects both the main site and H5")}
      footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy || !password || !confirm}>{busy ? t("注销中…", "Deleting…") : t("确认注销", "Confirm deletion")}</button>}
    >
      <div className="callout">
        <AlertTriangle size={15} />
        <span>{t("个人数据（自选、组合、模拟盘、策略、因子、通知等）会被删除；已发布的帖子和评论保留并显示为「已注销用户」。账号不可恢复。", "Personal data (watchlist, portfolios, paper accounts, strategies, factors, notifications, etc.) will be deleted; published posts and comments are retained and shown as “deleted user”. The account cannot be restored.")}</span>
      </div>
      <label className="field"><span>{t("登录密码", "Login password")}</span><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("输入登录密码", "Enter your login password")} /></label>
      <label className="field"><span>{t("确认词", "Confirmation")}</span><input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={t("输入用户名或「注销」确认", "Enter your username or \"DELETE\" to confirm")} /></label>
      {msg ? <div className="callout">{msg}</div> : null}
    </Sheet>
  );
}

function PrivacySheet({ open, onClose, onOpenFull }: { open: boolean; onClose: () => void; onOpenFull: () => void }) {
  const { t } = useLocale();
  return (
    <Sheet open={open} onClose={onClose} title={t("隐私与协议", "Privacy & terms")} sub={t("MVP 草案 · 公开前需法务确认", "MVP draft · legal review required before launch")}>
      <div className="legal">
        <h4>{t("我们收集什么", "What we collect")}</h4>
        <p>{t("账号标识、用户名、自选、持仓（你主动导入）、关注事件与使用日志。持仓属于敏感数据，仅用于组合体检。", "Account identifiers, username, watchlist, holdings (that you import), watch events, and usage logs. Holdings are sensitive data and are used only for portfolio checkups.")}</p>
        <h4>{t("如何使用", "How we use it")}</h4>
        <p>{t("用于生成组合诊断、关注事件日志与产品改进；不用于公共模型训练，不向第三方出售。", "Used to generate portfolio diagnostics, watch event logs, and product improvements; not used for public model training and not sold to third parties.")}</p>
        <h4>{t("保存与删除", "Retention & deletion")}</h4>
        <p>{t("你可以在「我的」导出或删除 Invest 数据，也可以直接注销 SVQuant 账号；注销会删除个人数据，社区内容保留并匿名化。", "You can export or delete Invest data under “Me”, or delete your SVQuant account directly; deletion removes personal data while community content is retained and anonymized.")}</p>
        <h4>{t("数据来源", "Data sources")}</h4>
        <p>{t("当前为本地演示数据；公开版需逐项核实行情、财务、新闻源条款，并标注来源与延迟。", "Currently using local demo data; the public version must verify terms for each quotes, financials, and news source, and label sources and delays.")}</p>
        <h4>{t("风险提示", "Risk disclosure")}</h4>
        <p>{t("本产品不提供投资建议、目标价或收益承诺；行情可能延迟或有误，请独立判断。", "This product does not provide investment advice, target prices, or return promises; quotes may be delayed or inaccurate—please make your own judgment.")}</p>
      </div>
      <button className="btn btn-ghost w100" onClick={onOpenFull}>{t("查看完整隐私政策 / 用户协议", "View full privacy policy / terms of service")}</button>
    </Sheet>
  );
}
