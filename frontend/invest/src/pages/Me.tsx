import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Bell, ChevronRight, Download, FileText, Info, LogOut, ShieldCheck, Trash2 } from "lucide-react";
import { api, getToken } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, Kv, PageHeader, Sheet, Tag } from "../components";
import { useToast } from "../toast";

export default function Me() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const [risk, setRisk] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [riskOpen, setRiskOpen] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    api("/api/invest/risk-profile").then(setRisk).catch(() => {});
    api("/api/invest/meta").then(setMeta).catch(() => {});
    api("/api/invest/data-quality").then(setQuality).catch(() => {});
  }, []);

  const exportData = async () => {
    try {
      const token = getToken();
      const res = await fetch("/api/invest/account/export", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(`导出失败（${res.status}）`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "svquant-invest-data.json";
      a.click();
      URL.revokeObjectURL(url);
      toast("已生成数据文件");
    } catch (e: any) {
      toast(e.message || "导出失败");
    }
  };

  const deleteData = async () => {
    if (!window.confirm("删除 Invest 的自选、持仓、事件与风测数据？此操作不可撤销，SVQuant 账号本身不会被删除。")) return;
    try {
      await api("/api/invest/account/data", { method: "DELETE" });
      setRisk(null);
      toast("Invest 数据已删除");
    } catch (e: any) {
      toast(e.message || "删除失败");
    }
  };

  return (
    <div className="page">
      <PageHeader title="我的" sub="账号、数据与合规" />

      <section className="me-card">
        <div className="me-avatar">{(user?.display_name || "演").slice(0, 1)}</div>
        <div className="me-info">
          <h2>{user?.display_name || "演示用户"}</h2>
          <p>@{user?.username} · 复用 SVQuant 账号</p>
          <div className="me-tags"><Tag tone="red">演示环境</Tag><Tag tone="gray">独立 H5 会话</Tag></div>
        </div>
      </section>

      <section className="card">
        <div className="card-title-row"><h2>风险测评</h2><span className="hint">用于组合体检展示</span></div>
        {risk?.level ? (
          <>
            <div className="risk-profile-row">
              <div><span>风险等级</span><b>{risk.level}</b></div>
              <div><span>风险分</span><b>{risk.score}</b></div>
            </div>
            <button className="btn btn-ghost w100" onClick={() => setRiskOpen(true)}>重新测评</button>
          </>
        ) : (
          <button className="btn btn-primary w100" onClick={() => setRiskOpen(true)}>开始测评</button>
        )}
      </section>

      <section className="card">
        <div className="card-title-row"><h2>数据与口径</h2><Tag tone={meta?.isDemo ? "amber" : "green"}>{meta?.isDemo ? "演示数据" : "公开 EOD"}</Tag></div>
        <Kv k="数据日期" v={meta?.dataDate || "2026-10-23"} />
        <Kv k="数据来源" v={meta?.source || "本地演示数据"} />
        <Kv k="更新时间" v={meta?.updatedAt || "2026-10-26 18:30"} />
        <Kv k="行情口径" v="前复权 · 收盘快照 · 非实时" />
        <Kv k="质量检查" v={quality ? (quality.ok ? (quality.checks?.some?.((c: any) => c.status === "warn") ? "通过（有提醒）" : "通过") : "有异常") : "检查中"} />
        <Kv k="数据新鲜度" v={meta ? (meta.isStale ? `已 ${meta.ageDays} 天未更新` : "T-0 / 正常") : "检查中"} />
        {meta?.disabledModules?.length ? <Kv k="模块状态" v={`临时关闭：${meta.disabledModules.join("、")}`} /> : null}
        <div className="hint">
          {meta?.isDemo
            ? "当前为演示数据，不代表真实行情；公开运行前需逐源核对数据条款。"
            : "行情/财务/估值来自公开 EOD；主题为成分股等权代理，公告/研报/要闻为公开标题。"}
        </div>
      </section>

      <div className="menu">
        <button className="menu-item" onClick={() => nav("/quant")}>
          <FileText size={18} /><span>量化研究</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => nav("/notifications")}>
          <Bell size={18} /><span>消息通知</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => setPrivacyOpen(true)}>
          <ShieldCheck size={18} /><span>隐私与协议</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => setAboutOpen(true)}>
          <Info size={18} /><span>关于 SVQuant Invest</span><ChevronRight size={16} />
        </button>
        <button className="menu-item" onClick={() => window.open("/support", "_blank", "noopener")}>
          <FileText size={18} /><span>客服与工单</span><ChevronRight size={16} />
        </button>
      </div>

      <div className="menu">
        <button className="menu-item" onClick={exportData}>
          <Download size={18} /><span>导出 Invest 数据</span><ChevronRight size={16} />
        </button>
        <button className="menu-item danger" onClick={deleteData}>
          <Trash2 size={18} /><span>删除 Invest 数据</span><ChevronRight size={16} />
        </button>
      </div>

      <div className="menu">
        <button className="menu-item danger" onClick={() => setDeleteOpen(true)}>
          <Trash2 size={18} /><span>注销 SVQuant 账号</span><ChevronRight size={16} />
        </button>
      </div>

      <button className="btn btn-ghost w100 logout" onClick={logout}>
        <LogOut size={16} /> 退出登录
      </button>

      <div className="callout">
        <AlertTriangle size={15} /><span><b>边界：</b>本产品只提供信息与教育内容，不提供买卖建议、目标价、收益承诺，不代客理财，不自动调仓。</span>
      </div>
      <Disclaimer>演示环境 · 不接券商 · 不产生真实委托</Disclaimer>

      <AccountDeleteSheet
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onDone={() => { setDeleteOpen(false); logout(); nav("/login", { replace: true }); }}
      />
      <RiskSheet open={riskOpen} onClose={() => setRiskOpen(false)} onSaved={(next) => { setRisk(next); setRiskOpen(false); toast("测评已保存"); }} />
      <PrivacySheet open={privacyOpen} onClose={() => setPrivacyOpen(false)} onOpenFull={() => { setPrivacyOpen(false); nav("/privacy"); }} />
      <Sheet open={aboutOpen} onClose={() => setAboutOpen(false)} title="关于" sub="SVQuant Invest · MVP">
        <p className="muted small">
          独立手机版 H5，复用 SVQuant 账号。当前为收盘后数据与规则解读，不含 AI 生成内容、不含实时行情、不含推送。
        </p>
        <div className="divider" />
        <Kv k="版本" v="0.1.0-demo" />
        <Kv k="数据" v="本地演示数据" />
        <Kv k="合规" v="非投资建议 / 非实时" />
      </Sheet>
    </div>
  );
}

function RiskSheet({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: (r: any) => void }) {
  const toast = useToast();
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
      toast(e.message || "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="风险测评" sub="3 个问题 · 自报结果" footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy}>{busy ? "保存中…" : "保存测评"}</button>}>
      <label className="field"><span>投资期限</span><select value={horizon} onChange={(e) => setHorizon(e.target.value)}><option>1年以内</option><option>1-3年</option><option>3-5年</option><option>5年以上</option></select></label>
      <label className="field"><span>可承受最大亏损</span><select value={loss} onChange={(e) => setLoss(e.target.value)}><option>5%</option><option>10%</option><option>20%</option><option>30%以上</option></select></label>
      <label className="field"><span>投资经验</span><select value={experience} onChange={(e) => setExperience(e.target.value)}><option>1年以内</option><option>1-3年</option><option>3年以上</option></select></label>
      <div className="callout blue"><b>说明：</b>测评只用于组合体检文案与风险提示，不构成适当性结论；公开版需接合规适当性流程。</div>
    </Sheet>
  );
}

function AccountDeleteSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
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
      setMsg(e.message || "注销失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="注销 SVQuant 账号"
      sub="不可恢复 · 同时影响主站与 H5"
      footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy || !password || !confirm}>{busy ? "注销中…" : "确认注销"}</button>}
    >
      <div className="callout">
        <AlertTriangle size={15} />
        <span>个人数据（自选、组合、模拟盘、策略、因子、通知等）会被删除；已发布的帖子和评论保留并显示为「已注销用户」。账号不可恢复。</span>
      </div>
      <label className="field"><span>登录密码</span><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="输入登录密码" /></label>
      <label className="field"><span>确认词</span><input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="输入用户名或「注销」确认" /></label>
      {msg ? <div className="callout">{msg}</div> : null}
    </Sheet>
  );
}

function PrivacySheet({ open, onClose, onOpenFull }: { open: boolean; onClose: () => void; onOpenFull: () => void }) {
  return (
    <Sheet open={open} onClose={onClose} title="隐私与协议" sub="MVP 草案 · 公开前需法务确认">
      <div className="legal">
        <h4>我们收集什么</h4>
        <p>账号标识、用户名、自选、持仓（你主动导入）、关注事件与使用日志。持仓属于敏感数据，仅用于组合体检。</p>
        <h4>如何使用</h4>
        <p>用于生成组合诊断、关注事件日志与产品改进；不用于公共模型训练，不向第三方出售。</p>
        <h4>保存与删除</h4>
        <p>你可以在「我的」导出或删除 Invest 数据，也可以直接注销 SVQuant 账号；注销会删除个人数据，社区内容保留并匿名化。</p>
        <h4>数据来源</h4>
        <p>当前为本地演示数据；公开版需逐项核实行情、财务、新闻源条款，并标注来源与延迟。</p>
        <h4>风险提示</h4>
        <p>本产品不提供投资建议、目标价或收益承诺；行情可能延迟或有误，请独立判断。</p>
      </div>
      <button className="btn btn-ghost w100" onClick={onOpenFull}>查看完整隐私政策 / 用户协议</button>
    </Sheet>
  );
}
