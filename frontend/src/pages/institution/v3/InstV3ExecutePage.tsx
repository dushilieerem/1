import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, Play, RefreshCw } from "lucide-react";
import { instApi } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";

type Authorization = {
  id: number;
  status: string;
  issued_at?: string;
  proposal_id?: number;
  company_id?: number;
  symbol?: string;
  company_name?: string;
  version_no?: number;
  version_snapshot?: Record<string, unknown>;
  snapshot?: Record<string, unknown>;
  revoked_at?: string;
  revoke_reason?: string;
};

type Precheck = {
  ok?: boolean;
  checks?: Array<{ key?: string; label?: string; status?: string; ok?: boolean; detail?: string; value?: string }>;
  blocking?: string[];
  price?: number | null;
  qty?: number | null;
  cash?: number | null;
  position_qty?: number | null;
  duplicate_order?: boolean;
};

type ExecResult = {
  idempotent?: boolean;
  order?: { id: number; qty: number; price: number; side: string; symbol?: string };
  cash?: number;
};

type ReconcileResult = { matched?: boolean; differences?: string[]; order?: Record<string, unknown>; fill?: Record<string, unknown> };

const STEPS = [
  { name: "授权核对", sub: "标的 / 价格 / 仓位" },
  { name: "下单成交", sub: "代码执行 · 幂等" },
  { name: "对账", sub: "成交 vs 授权 vs 余额" },
  { name: "持仓更新", sub: "写入组合 · 建台账" },
];

function parseAuthId(key: string | null): number | null {
  const m = String(key || "").match(/auth:(\d+)/);
  return m ? Number(m[1]) : null;
}

export function InstV3ExecutePage() {
  const session = useInstSession();
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<Authorization[]>([]);
  const [selected, setSelected] = useState<Authorization | null>(null);
  const [precheck, setPrecheck] = useState<Precheck | null>(null);
  const [execResult, setExecResult] = useState<ExecResult | null>(null);
  const [reconcile, setReconcile] = useState<ReconcileResult | null>(null);
  const [step, setStep] = useState(0);
  const [price, setPrice] = useState("");
  const [conditionsMet, setConditionsMet] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const selectedId = parseAuthId(params.get("key"));
  const canExecute = session.role === "execution";
  const snapshot = ((selected?.snapshot || selected?.version_snapshot || {}) as Record<string, unknown>);
  const approvalConditions = (snapshot.approval_conditions || []) as unknown[];

  const load = async () => {
    const qualified = await instApi<{ items: Authorization[] }>("/authorizations?status=qualified");
    let rows = qualified.items || [];
    if (!rows.length) {
      const all = await instApi<{ items: Authorization[] }>("/authorizations");
      rows = all.items || [];
    }
    setItems(rows);
    return rows;
  };

  const loadDetail = async (auth: Authorization) => {
    setSelected(auth);
    setExecResult(null);
    setReconcile(null);
    try {
      const pre = await instApi<Precheck>(`/authorizations/${auth.id}/precheck`);
      setPrecheck(pre);
      if (pre.price != null) setPrice(String(pre.price));
    } catch (e) {
      setPrecheck(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    load()
      .then(async (rows) => {
        if (!alive) return;
        const id = selectedId || rows[0]?.id || null;
        const auth = rows.find((x) => x.id === id) || null;
        if (auth) {
          if (!selectedId) setParams({ key: `auth:${auth.id}` }, { replace: true });
          else await loadDetail(auth);
        }
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const selectAuth = (a: Authorization) => {
    setParams({ key: `auth:${a.id}` });
    loadDetail(a).catch((e: Error) => setError(e.message));
  };

  const execute = async () => {
    if (!selected) return;
    setBusy("execute");
    setError(null);
    try {
      const res = await instApi<ExecResult>(`/authorizations/${selected.id}/execute`, {
        method: "POST",
        body: { price: price ? Number(price) : null, conditions_met: conditionsMet },
      });
      setExecResult(res);
      setStep(2);
      const rows = await load();
      const next = rows.find((x) => x.id === selected.id);
      if (next) setSelected(next);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const runReconcile = async () => {
    if (!selected) return;
    setBusy("reconcile");
    setError(null);
    try {
      const res = await instApi<ReconcileResult>(`/authorizations/${selected.id}/reconcile`, { method: "POST" });
      setReconcile(res);
      setStep(3);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const executed = Boolean(execResult?.order) || selected?.status === "filled";
  const summary = useMemo(() => {
    if (!precheck) return [];
    return precheck.checks || [];
  }, [precheck]);

  if (loading) return <div className="v3-loading">正在加载执行成交…</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">EXECUTION / 05</div>
          <h1>执行成交</h1>
          <p>确定性代码按授权执行：核对、下单、对账、更新持仓；不调用模型，不手工改单。</p>
        </div>
        <span className="v3-chip info">{session.role_label_cn} · {canExecute ? "可执行" : "只读"}</span>
      </div>

      <div className="v3-stepper">
        {STEPS.map((s, i) => (
          <button key={s.name} className={`v3-step${i < step ? " done" : i === step ? " now" : ""}`} onClick={() => setStep(i)} style={{ background: "none", borderTop: 0, borderLeft: 0, borderBottom: 0, cursor: "pointer" }}>
            <span className="dot">{i < step ? "✓" : i}</span>
            <div><span className="lb">{s.name}</span><span className="sb">{s.sub}</span></div>
          </button>
        ))}
      </div>

      <div className="v3-workspace-grid">
        <div className="v3-project-list">
          <div className="pl-head"><span>授权队列</span><span>{items.length}</span></div>
          {items.map((a) => (
            <button key={a.id} className={`pl-item${a.id === selected?.id ? " on" : ""}`} onClick={() => selectAuth(a)}>
              <b>{a.company_name || a.symbol}</b>
              <span>#{a.id} · {a.status} · v{a.version_no || "—"}</span>
            </button>
          ))}
          {!items.length ? <div className="v3-empty" style={{ padding: "18px 8px" }}>暂无授权。三关审批通过后生成 AUTH。</div> : null}
        </div>

        <div className="v3-work-main">
          {error ? <div className="v3-note" style={{ borderColor: "#eed2d0", background: "#fbeeed", color: "#ab3a37" }}>{error}</div> : null}
          {!selected ? <div className="v3-card"><div className="v3-empty">请选择一份授权。</div></div> : (
            <>
              <section className="v3-card">
                <div className="v3-card-head"><div><h2>授权文件 AUTH-{selected.id}</h2><p>{selected.company_name || selected.symbol} · {selected.status}</p></div><span className={`v3-chip ${selected.status === "filled" ? "ok" : selected.status === "revoked" ? "bad" : "warn"}`}>{selected.status}</span></div>
                <dl>
                  <div className="v3-kv"><dt>标的 / 方向</dt><dd>{selected.symbol} · {String(snapshot.direction || "—")}</dd></div>
                  <div className="v3-kv"><dt>目标仓位</dt><dd>{snapshot.target_weight != null ? `${(Number(snapshot.target_weight) * 100).toFixed(1)}%` : "—"}</dd></div>
                  <div className="v3-kv"><dt>价格区间</dt><dd>{snapshot.price_low != null ? `${snapshot.price_low} – ${snapshot.price_high}` : "—"}</dd></div>
                  <div className="v3-kv"><dt>账户 / 有效期</dt><dd>{String(snapshot.account || "—")} · {String(snapshot.valid_until || "—")}</dd></div>
                </dl>
                {approvalConditions.length ? <div className="v3-note" style={{ marginTop: 10 }}>审批附加条件：{approvalConditions.map((x) => typeof x === "object" ? JSON.stringify(x) : String(x)).join("；")}</div> : null}
              </section>

              {step === 0 ? (
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>授权核对</h2><p>标的、方向、价格、仓位、账户、有效期逐项比对；不一致立即停下。</p></div><button className="v3-btn ghost" disabled={!!busy} onClick={() => loadDetail(selected)}><RefreshCw className="h-3.5 w-3.5" />重新核对</button></div>
                  {summary.map((c, i) => (
                    <div className="v3-kv" key={`${c.key}-${i}`}><dt>{c.label || c.key || "检查"}</dt><dd>{c.detail || c.value || "—"} <span className={`v3-chip ${c.ok === true ? "ok" : c.ok === false ? "bad" : "warn"}`}>{c.ok === true ? "通过" : c.ok === false ? "阻断" : (c.status || "—")}</span></dd></div>
                  ))}
                  {!summary.length ? <div className="v3-empty">暂无核对明细。</div> : null}
                  {precheck?.ok === false ? <div className="v3-note" style={{ marginTop: 10 }}>核对未通过：{precheck.blocking?.join("；") || "请检查授权要素"}</div> : null}
                  <div style={{ marginTop: 10 }}><button className="v3-btn primary" disabled={!canExecute || precheck?.ok !== true} onClick={() => setStep(1)}>继续下单 <ArrowRight className="h-3.5 w-3.5" /></button></div>
                </section>
              ) : null}

              {step === 1 ? (
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>下单成交</h2><p>同一授权只执行一次；成交不确定时停止重试，避免重复下单。</p></div><span className="v3-chip">幂等</span></div>
                  <div className="v3-form-grid">
                    <div className="v3-field"><label>成交价（CNY）</label><input value={price} onChange={(e) => setPrice(e.target.value)} disabled={!canExecute} /></div>
                    <div className="v3-field"><label>预计数量</label><input value={precheck?.qty ?? "—"} readOnly /></div>
                    <div className="v3-field span-2">
                      <label><input type="checkbox" checked={conditionsMet} onChange={(e) => setConditionsMet(e.target.checked)} disabled={!canExecute} /> 审批附加条件已确认满足</label>
                    </div>
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <button className="v3-btn primary" disabled={!canExecute || !!busy || executed} onClick={execute}><Play className="h-3.5 w-3.5" />{busy === "execute" ? "执行中…" : executed ? "已成交" : "执行成交"}</button>
                    {!canExecute ? <span className="ml-2 text-[10px] text-[#9b92a1]">仅交易执行角色可下单；其他角色只读。</span> : null}
                  </div>
                </section>
              ) : null}

              {step === 2 ? (
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>对账</h2><p>成交 vs 授权 vs 账户余额三方核对；有偏差登记异常，不自动覆盖。</p></div><span className={`v3-chip ${reconcile?.matched ? "ok" : "warn"}`}>{reconcile ? (reconcile.matched ? "0 偏差" : "有差异") : "待对账"}</span></div>
                  {execResult?.order ? (
                    <dl>
                      <div className="v3-kv"><dt>订单</dt><dd>#{execResult.order.id} · {execResult.order.side} {execResult.order.qty} 股 · {execResult.order.price}</dd></div>
                      <div className="v3-kv"><dt>幂等</dt><dd>{execResult.idempotent ? "重复执行返回原订单" : "首次执行"}</dd></div>
                    </dl>
                  ) : <div className="v3-empty">请先完成下单成交。</div>}
                  <div style={{ marginTop: 10 }}><button className="v3-btn primary" disabled={!executed || !!busy} onClick={runReconcile}><RefreshCw className="h-3.5 w-3.5" />{busy === "reconcile" ? "对账中…" : "执行对账"}</button></div>
                  {reconcile ? <div className="v3-note" style={{ marginTop: 10 }}>{reconcile.matched ? "成交与授权一致，0 偏差。" : `差异：${(reconcile.differences || []).join("；")}`}</div> : null}
                </section>
              ) : null}

              {step === 3 ? (
                <section className="v3-card">
                  <div className="v3-card-head"><div><h2>持仓更新</h2><p>对账通过后持仓写入组合，并自动建立买入论点台账。</p></div><span className={`v3-chip ${executed ? "ok" : "warn"}`}>{executed ? "已成交" : "待成交"}</span></div>
                  <p style={{ fontSize: 11, lineHeight: 1.7, color: "#746b7c" }}>{executed ? "持仓已更新；进入 06 投资管理继续跟踪论点、事件与退出。" : "只有成交回报回来、对账完成，持仓才算数。"}</p>
                  <div style={{ marginTop: 10 }}><Link className="v3-btn primary" to="/inst-v3/manage">进入投资管理 <ArrowRight className="h-3.5 w-3.5" /></Link></div>
                </section>
              ) : null}
            </>
          )}
        </div>

        <aside className="v3-agent-rail">
          <div className="ar-kicker">EXECUTION ENGINE</div>
          <h3>确定性代码 · 无 LLM</h3>
          <p>只核对授权、下单、对账、更新持仓；不读研究、不改价格、不手工改单。</p>
          <div className="ar-row"><b>本步</b><br />{STEPS[step].name} · {STEPS[step].sub}</div>
          <div className="ar-row"><b>异常</b><br />不一致/不足/超时/部分成交/对账差异一律停下上报。</div>
          <div className="ar-row"><b>状态</b><br />{selected ? `${selected.symbol} · ${selected.status}` : "未选择授权"}</div>
        </aside>
      </div>
    </>
  );
}
