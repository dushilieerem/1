import { useEffect, useState } from "react";
import { Building2, Coins, Users } from "lucide-react";
import { authHeaders } from "@/lib/auth";

type Org = {
  id: number;
  name: string;
  plan_code: string;
  plan_name_cn?: string;
  ai_daily_quota?: number;
  universe_limit?: number;
  credits: number;
  my_role?: string;
  members?: Array<{ user_id: number; username: string; display_name?: string; role: string }>;
};

type Plan = { code: string; name_cn: string; price_cents: number; ai_daily_quota: number; universe_limit: number };

type Credit = { id: number; delta: number; reason: string; created_at?: string };
type Request = { id: number; kind: string; amount_cents: number; note: string; status: string; created_at?: string };

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string; error?: string })?.detail || (data as { error?: string })?.error || `HTTP ${res.status}`);
  return data as T;
}

export default function OrgPage() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selected, setSelected] = useState<Org | null>(null);
  const [credits, setCredits] = useState<Credit[]>([]);
  const [requests, setRequests] = useState<Request[]>([]);
  const [name, setName] = useState("");
  const [memberName, setMemberName] = useState("");
  const [memberRole, setMemberRole] = useState("member");
  const [requestKind, setRequestKind] = useState("topup");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadList = async () => {
    try {
      const [o, p] = await Promise.all([
        call<{ items: Org[] }>("/api/orgs"),
        call<{ items: Plan[] }>("/api/orgs/plans"),
      ]);
      setOrgs(o.items || []);
      setPlans(p.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const open = async (id: number) => {
    try {
      const [detail, credit, reqs] = await Promise.all([
        call<{ org: Org }>(`/api/orgs/${id}`),
        call<{ items: Credit[] }>(`/api/orgs/${id}/credits`),
        call<{ items: Request[] }>(`/api/orgs/${id}/billing/requests`),
      ]);
      setSelected(detail.org);
      setCredits(credit.items || []);
      setRequests(reqs.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void loadList();
  }, []);

  const createOrg = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await call<{ org: Org }>("/api/orgs", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setName("");
      await loadList();
      await open(res.org.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const addMember = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await call(`/api/orgs/${selected.id}/members`, {
        method: "POST",
        body: JSON.stringify({ username: memberName, role: memberRole }),
      });
      setMemberName("");
      await open(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const changePlan = async (planCode: string) => {
    if (!selected) return;
    try {
      await call(`/api/orgs/${selected.id}/plan`, {
        method: "PUT",
        body: JSON.stringify({ plan_code: planCode }),
      });
      await open(selected.id);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const requestBilling = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await call(`/api/orgs/${selected.id}/billing/requests`, {
        method: "POST",
        body: JSON.stringify({
          kind: requestKind,
          amount_cents: Math.round(Number(amount || 0) * 100),
          note,
        }),
      });
      setAmount("");
      setNote("");
      setMessage("申请已提交，等待管理员处理。");
      await open(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const canManage = selected && (selected.my_role === "owner" || selected.my_role === "admin");

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-8">
      <header>
        <p className="text-[11px] tracking-[0.18em] text-red-600">TEAM</p>
        <h1 className="mt-1 flex items-center gap-2 font-display text-2xl font-semibold text-slate-900">
          <Building2 className="h-6 w-6 text-red-500" /> 组织与团队
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          套餐、成员与额度；充值/发票走人工审批（未接在线支付）。
        </p>
      </header>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div> : null}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.4fr]">
        <section className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">新建组织</h2>
            <div className="mt-2 flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="组织名称"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <button
                type="button"
                disabled={busy || !name.trim()}
                onClick={() => void createOrg()}
                className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                创建
              </button>
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">我的组织</h2>
            <ul className="mt-2 divide-y divide-slate-100">
              {orgs.map((org) => (
                <li key={org.id}>
                  <button
                    type="button"
                    onClick={() => void open(org.id)}
                    className="flex w-full items-center justify-between gap-2 py-2.5 text-left text-sm hover:text-red-600"
                  >
                    <span>{org.name}</span>
                    <span className="text-[11px] text-slate-400">
                      {org.plan_name_cn || org.plan_code} · {org.credits} 分
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="space-y-4">
          {selected ? (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-base font-semibold text-slate-900">{selected.name}</h2>
                  <span className="text-xs text-slate-500">{selected.my_role}</span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  <div className="rounded-xl bg-slate-50 p-3 text-sm">
                    <p className="text-xs text-slate-500">套餐</p>
                    <p className="mt-1 font-medium">{selected.plan_name_cn || selected.plan_code}</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3 text-sm">
                    <p className="text-xs text-slate-500">AI 日额度</p>
                    <p className="mt-1 font-medium">{selected.ai_daily_quota ?? "—"}</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3 text-sm">
                    <p className="text-xs text-slate-500">证券池上限</p>
                    <p className="mt-1 font-medium">{selected.universe_limit ?? "—"}</p>
                  </div>
                </div>
                {canManage ? (
                  <select
                    value={selected.plan_code}
                    onChange={(e) => void changePlan(e.target.value)}
                    className="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  >
                    {plans.map((plan) => (
                      <option key={plan.code} value={plan.code}>
                        {plan.name_cn}（{(plan.price_cents / 100).toFixed(0)} 元/月）
                      </option>
                    ))}
                  </select>
                ) : null}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <Users className="h-4 w-4" /> 成员
                </h2>
                <ul className="mt-2 divide-y divide-slate-100">
                  {(selected.members || []).map((m) => (
                    <li key={m.user_id} className="flex items-center justify-between py-2 text-sm">
                      <span>{m.display_name || m.username}</span>
                      <span className="text-[11px] text-slate-400">{m.role}</span>
                    </li>
                  ))}
                </ul>
                {canManage ? (
                  <div className="mt-3 flex gap-2">
                    <input
                      value={memberName}
                      onChange={(e) => setMemberName(e.target.value)}
                      placeholder="用户名"
                      className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                    <select
                      value={memberRole}
                      onChange={(e) => setMemberRole(e.target.value)}
                      className="rounded-lg border border-slate-200 px-2 text-sm"
                    >
                      <option value="member">成员</option>
                      <option value="admin">管理员</option>
                    </select>
                    <button
                      type="button"
                      disabled={busy || !memberName.trim()}
                      onClick={() => void addMember()}
                      className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50"
                    >
                      添加
                    </button>
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <Coins className="h-4 w-4" /> 额度与账单
                </h2>
                <p className="mt-2 text-sm text-slate-600">
                  当前余额：<b>{selected.credits}</b> 分
                </p>
                <div className="mt-3 space-y-2">
                  <div className="flex gap-2">
                    <select
                      value={requestKind}
                      onChange={(e) => setRequestKind(e.target.value)}
                      className="rounded-lg border border-slate-200 px-2 text-sm"
                    >
                      <option value="topup">充值</option>
                      <option value="invoice">发票</option>
                    </select>
                    <input
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      placeholder="金额（元）"
                      className="w-32 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="备注"
                      className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void requestBilling()}
                      className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                    >
                      提交
                    </button>
                  </div>
                  {requests.length ? (
                    <ul className="text-xs text-slate-500">
                      {requests.slice(0, 5).map((r) => (
                        <li key={r.id} className="py-1">
                          {r.kind === "topup" ? "充值" : "发票"} {(r.amount_cents / 100).toFixed(2)} 元 · {r.status}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {credits.length ? (
                    <ul className="text-xs text-slate-400">
                      {credits.slice(0, 5).map((c) => (
                        <li key={c.id}>
                          {c.delta > 0 ? "+" : ""}
                          {c.delta} · {c.reason}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400">选择左侧组织查看成员、套餐与额度。</p>
          )}
        </section>
      </div>
    </div>
  );
}
