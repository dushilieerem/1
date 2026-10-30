import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Plus, Search, Trash2, X } from "lucide-react";
import { api } from "../api";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, SectionHead, Sheet, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import { useToast } from "../toast";

export default function Watch() {
  const nav = useNavigate();
  const toast = useToast();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const load = () => {
    setError(null);
    api("/api/invest/watchlist").then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  const remove = async (code: string) => {
    try {
      const next = await api(`/api/invest/watchlist/${code}`, { method: "DELETE" });
      setData(next);
      toast("已移出自选");
    } catch (e: any) {
      toast(e.message || "操作失败");
    }
  };

  const count = data?.groups?.reduce((n: number, g: any) => n + g.items.length, 0) || 0;

  return (
    <div className="page">
      <PageHeader
        title="自选"
        sub={`${count} 只 · ${data?.events?.length || 0} 条关注事件`}
        right={<button className="round-btn" onClick={() => setAddOpen(true)} aria-label="添加"><Plus size={20} /></button>}
      />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <>
          {count === 0 ? (
            <EmptyState title="还没有自选" detail="搜索股票并加入自选，收盘后查看事件日志。" action={<button className="btn btn-primary" onClick={() => setAddOpen(true)}>添加自选</button>} />
          ) : (
            data.groups.map((g: any) => (
              <section className="card list-card" key={g.name}>
                <div className="card-title-row"><h2>{g.name}</h2><span className="hint">{g.items.length} 只</span></div>
                {g.items.map((s: any) => (
                  <div className="stock-row with-action" key={s.code}>
                    <button className="stock-main" onClick={() => nav(`/stock/${s.code}`)}>
                      <div><b>{s.name}</b><span>{s.code} · {s.industry}</span></div>
                      <div className="stock-price">
                        <b>{formatPrice(s.price)}</b>
                        <em className={s.changePct >= 0 ? "up" : "down"}>{fmtPct(s.changePct)}</em>
                      </div>
                    </button>
                    <button className="row-action" aria-label={`移除 ${s.name}`} onClick={() => remove(s.code)}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </section>
            ))
          )}

          <SectionHead title="关注事件" sub="收盘后检查 · 不提供实时推送" action={<button className="link-btn" onClick={() => setAddOpen(true)}><Plus size={14} /> 新建</button>} />
          <section className="card list-card">
            {data.events.length === 0 ? (
              <div className="empty-inline">还没有关注事件。</div>
            ) : data.events.map((e: any) => (
              <div className="event-row" key={e.id}>
                <span className="event-icon"><Bell size={15} /></span>
                <div>
                  <b>{e.name || e.code} · {e.type}</b>
                  <span>{e.condition}</span>
                </div>
                <Tag tone={e.status === "active" ? "green" : "gray"}>{e.status === "active" ? "生效中" : "已停止"}</Tag>
              </div>
            ))}
          </section>

          <SectionHead title="触发日志" sub="近 7 天 · 打开时刷新" />
          <section className="card list-card">
            {data.logs.length === 0 ? (
              <div className="empty-inline">还没有触发记录。</div>
            ) : data.logs.map((l: any) => (
              <div className="log-row" key={l.id}>
                <div>
                  <b>{l.title}</b>
                  <span>{l.detail} · {l.triggered_at}</span>
                </div>
                <Tag tone={l.read ? "gray" : "amber"}>{l.read ? "已读" : "待关注"}</Tag>
              </div>
            ))}
          </section>

          <div className="callout">
            <b>口径说明：</b>收盘后更新，不提供实时提醒；事件只记录“发生了什么 + 为什么”，不推送买卖指令。
          </div>
          <Disclaimer>演示数据 · 非实时 · 不构成投资建议</Disclaimer>
        </>
      ) : null}

      <AddWatchSheet open={addOpen} onClose={() => setAddOpen(false)} onDone={() => { setAddOpen(false); load(); }} />
    </div>
  );
}

function AddWatchSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [type, setType] = useState("价格");
  const [condition, setCondition] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      api<any>(`/api/invest/search?q=${encodeURIComponent(q || "宁德")}`)
        .then((d) => setItems(d.results.filter((x: any) => x.type === "stock")))
        .catch(() => setItems([]));
    }, 180);
    return () => window.clearTimeout(t);
  }, [q, open]);

  const submit = async () => {
    if (!selected) {
      toast("先选择标的");
      return;
    }
    setBusy(true);
    try {
      await api("/api/invest/watchlist", { method: "POST", body: JSON.stringify({ code: selected.id }) });
      await api("/api/invest/events", { method: "POST", body: JSON.stringify({ code: selected.id, type, condition: condition || `${type}条件` }) });
      toast("已加入自选并创建关注事件");
      setCondition("");
      onDone();
    } catch (e: any) {
      toast(e.message || "创建失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="添加自选 / 关注事件" sub="收盘后检查 · 非实时" footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy}>{busy ? "创建中…" : "创建"}</button>}>
      <label className="field">
        <span>搜索标的</span>
        <div className="input-with-icon">
          <Search size={16} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="名称 / 代码 / 拼音" />
        </div>
      </label>
      <div className="search-results">
        {items.map((it: any) => (
          <button className={`search-result ${selected?.id === it.id ? "on" : ""}`} key={it.id} onClick={() => setSelected(it)}>
            <div><b>{it.name}</b><span>{it.sub}</span></div>
            <div className="search-price"><b>{formatPrice(it.price)}</b><em className={it.changePct >= 0 ? "up" : "down"}>{fmtPct(it.changePct)}</em></div>
          </button>
        ))}
        {!items.length ? <div className="empty-inline">没有匹配标的。</div> : null}
      </div>
      <label className="field">
        <span>事件类型</span>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option>价格</option><option>财报</option><option>公告</option><option>热度</option><option>估值分位</option>
        </select>
      </label>
      <label className="field">
        <span>条件（可选）</span>
        <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="例如：收盘价跌破 220 元" />
      </label>
      <div className="callout">
        <b>注意：</b>没有推送通道，事件只在收盘后记录日志；不推送“买/卖”指令。
      </div>
    </Sheet>
  );
}
