import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { AiCard } from "../components/AiCard";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { fmtMoney } from "../lib";

type Account = {
  id: number;
  name: string;
  status: string;
  projectName?: string;
  totalEquity?: number;
  cash?: number;
  positionCount?: number;
  lastSettledDate?: string;
};

export default function Paper() {
  const nav = useNavigate();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    api<any>("/api/paper/accounts")
      .then((d) => setAccounts(d.accounts || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const open = async (account: Account) => {
    setAi(null);
    try {
      setDetail(await api<any>(`/api/paper/accounts/${account.id}`));
    } catch (e: any) {
      setError(e.message);
    }
  };

  const review = async (account: Account) => {
    setBusy(account.id);
    setError(null);
    try {
      const data = await api<any>("/api/invest/ai/paper", {
        method: "POST",
        body: JSON.stringify({ account_id: account.id }),
      });
      setDetail(await api<any>(`/api/paper/accounts/${account.id}`));
      setAi({ card: data.card, blocked: data.blocked });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="page">
      <PageHeader title="模拟盘" sub="日终撮合 · AI 只解释，不调仓" back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={2} /> : null}
      {!loading && !accounts.length ? (
        <EmptyState title="还没有模拟盘账户" detail="在桌面端策略项目里创建模拟盘后，这里会显示。" />
      ) : null}
      {accounts.map((account) => (
        <section className="card" key={account.id}>
          <div className="card-title-row">
            <h2>{account.name}</h2>
            <Tag tone={account.status === "active" ? "green" : "amber"}>{account.status}</Tag>
          </div>
          <p className="hint">{account.projectName || "策略项目"} · 最近结算 {account.lastSettledDate || "—"}</p>
          <div className="kpi-grid">
            <div className="kpi"><span>总权益</span><b>{fmtMoney(account.totalEquity || 0)}</b></div>
            <div className="kpi"><span>现金</span><b>{fmtMoney(account.cash || 0)}</b></div>
            <div className="kpi"><span>持仓</span><b>{detail?.account?.id === account.id ? detail.positions?.length ?? 0 : "—"}</b></div>
          </div>
          <div className="row gap6">
            <button className="btn btn-ghost btn-sm" onClick={() => void open(account)}>查看持仓</button>
            <button className="btn btn-primary btn-sm" onClick={() => void review(account)} disabled={busy === account.id}>
              <Sparkles size={14} /> {busy === account.id ? "生成中…" : "AI 点评"}
            </button>
          </div>
          {detail?.account?.id === account.id ? (
            <div className="hold-list">
              {(detail.positions || []).map((p: any) => (
                <div className="hold-row" key={p.symbol}>
                  <div><b>{p.symbol}</b><span>成本 {p.averageCost}</span></div>
                  <div className="hold-right"><b>{p.quantity}</b><span>{fmtMoney(p.marketValue || 0)}</span></div>
                </div>
              ))}
              {!(detail.positions || []).length ? <div className="empty-inline">当前空仓。</div> : null}
            </div>
          ) : null}
          {ai ? <AiCard data={ai} title="AI 模拟盘点评" /> : null}
        </section>
      ))}
      <Disclaimer>模拟盘为日终撮合，非真实成交；AI 不构成投资建议。</Disclaimer>
    </div>
  );
}
