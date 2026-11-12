import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Plus, Search, Trash2, X } from "lucide-react";
import { api } from "../api";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, SectionHead, Sheet, Tag } from "../components";
import { displayIndustry, fmtPct, formatPrice } from "../lib";
import { useToast } from "../toast";
import { useLocale, withMarket } from "../i18n";

export default function Watch() {
  const nav = useNavigate();
  const toast = useToast();
  const { t, market } = useLocale();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const load = () => {
    setError(null);
    api(withMarket("/api/invest/watchlist", market)).then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, [market]);

  const remove = async (code: string) => {
    try {
      const next = await api(withMarket(`/api/invest/watchlist/${code}`, market), { method: "DELETE" });
      setData(next);
      toast(t("已移出自选", "Removed from watchlist"));
    } catch (e: any) {
      toast(e.message || t("操作失败", "Action failed"));
    }
  };

  const count = data?.groups?.reduce((n: number, g: any) => n + g.items.length, 0) || 0;
  const usUnavailable = market === "US" && data?.available === false;

  return (
    <div className="page">
      <PageHeader
        title={t("自选", "Watchlist")}
        sub={
          market === "US"
            ? t(`${count} 只 · 美股行情`, `${count} name(s) · US quotes`)
            : t(`${count} 只 · ${data?.events?.length || 0} 条关注事件`, `${count} name(s) · ${data?.events?.length || 0} watch event(s)`)
        }
        right={<button className="round-btn" onClick={() => setAddOpen(true)} aria-label={t("添加", "Add")}><Plus size={20} /></button>}
      />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <>
          {count === 0 ? (
            <EmptyState
              title={t("还没有自选", "No watchlist names yet")}
              detail={usUnavailable ? t("当前数据视图只有 A 股覆盖，美股自选暂不可用。切换到中文查看 A 股。", "The current data view only covers A-shares; US watchlists are unavailable. Switch to 中文 for A-share coverage.") : market === "US" ? t("搜索美股代码并加入自选，查看美股行情。", "Search a US ticker and add it to the watchlist to track US quotes.") : t("搜索股票并加入自选，收盘后查看事件日志。", "Search a stock and add it to the watchlist; events refresh after the close.")}
              action={usUnavailable ? undefined : <button className="btn btn-primary" onClick={() => setAddOpen(true)}>{t("添加自选", "Add to watchlist")}</button>}
            />
          ) : (
            data.groups.map((g: any) => (
              <section className="card list-card" key={g.name}>
                <div className="card-title-row"><h2>{g.name}</h2><span className="hint">{t(`${g.items.length} 只`, `${g.items.length} name(s)`)}</span></div>
                {g.items.map((s: any) => (
                  <div className="stock-row with-action" key={s.code}>
                    <button className="stock-main" onClick={() => nav(`/stock/${s.code}`)}>
                      <div><b>{s.name}</b><span>{s.code} · {displayIndustry(s.industry)}</span></div>
                      <div className="stock-price">
                        <b>{formatPrice(s.price)}</b>
                        <em className={s.changePct >= 0 ? "up" : "down"}>{fmtPct(s.changePct)}</em>
                      </div>
                    </button>
                    <button className="row-action" aria-label={t(`移除 ${s.name}`, `Remove ${s.name}`)} onClick={() => remove(s.code)}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </section>
            ))
          )}

          {market === "CN" ? (
            <>
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
            </>
          ) : null}

          <div className="callout">
            <b>{t("口径说明：", "Scope:")}</b>
            {t("收盘后更新，不提供实时提醒；事件只记录“发生了什么 + 为什么”，不推送买卖指令。", "Refreshes after the close; no real-time alerts. Events only record what happened and why, never buy/sell instructions.")}
          </div>
          <Disclaimer>{market === "US" ? t("美股行情 · 非实时 · 不构成投资建议", "US quotes · not real-time · not investment advice") : t("演示数据 · 非实时 · 不构成投资建议", "Demo data · not real-time · not investment advice")}</Disclaimer>
        </>
      ) : null}

      <AddWatchSheet market={market} open={addOpen} onClose={() => setAddOpen(false)} onDone={() => { setAddOpen(false); load(); }} />
    </div>
  );
}

function AddWatchSheet({
  open,
  onClose,
  onDone,
  market,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  market: "CN" | "US";
}) {
  const toast = useToast();
  const { t } = useLocale();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [type, setType] = useState("价格");
  const [condition, setCondition] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      api<any>(withMarket(`/api/invest/search?q=${encodeURIComponent(q || (market === "US" ? "AAPL" : "宁德"))}`, market))
        .then((d) => setItems(d.results.filter((x: any) => x.type === "stock")))
        .catch(() => setItems([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [q, open, market]);

  const submit = async () => {
    if (!selected) {
      toast(t("先选择标的", "Pick a name first"));
      return;
    }
    setBusy(true);
    try {
      await api(withMarket("/api/invest/watchlist", market), { method: "POST", body: JSON.stringify({ code: selected.id }) });
      if (market === "CN") {
        await api("/api/invest/events", { method: "POST", body: JSON.stringify({ code: selected.id, type, condition: condition || `${type}条件` }) });
      }
      toast(market === "US" ? t("已加入自选", "Added to watchlist") : t("已加入自选并创建关注事件", "Added to watchlist and created a watch event"));
      setCondition("");
      onDone();
    } catch (e: any) {
      toast(e.message || t("创建失败", "Failed to create"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={market === "US" ? t("添加美股自选", "Add US ticker") : t("添加自选 / 关注事件", "Add to watchlist / event")}
      sub={t("收盘后检查 · 非实时", "Checked after the close · not real-time")}
      footer={<button className="btn btn-primary w100" onClick={submit} disabled={busy}>{busy ? t("创建中…", "Creating…") : t("创建", "Create")}</button>}
    >
      <label className="field">
        <span>{t("搜索标的", "Search")}</span>
        <div className="input-with-icon">
          <Search size={16} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={market === "US" ? t("美股代码，如 AAPL", "US ticker, e.g. AAPL") : t("名称 / 代码 / 拼音", "Name / code / pinyin")}
          />
        </div>
      </label>
      <div className="search-results">
        {items.map((it: any) => (
          <button className={`search-result ${selected?.id === it.id ? "on" : ""}`} key={it.id} onClick={() => setSelected(it)}>
            <div><b>{it.name}</b><span>{it.sub}</span></div>
            <div className="search-price"><b>{formatPrice(it.price)}</b><em className={it.changePct >= 0 ? "up" : "down"}>{fmtPct(it.changePct)}</em></div>
          </button>
        ))}
        {!items.length ? <div className="empty-inline">{t("没有匹配标的。", "No matching names.")}</div> : null}
      </div>
      {market === "CN" ? (
        <>
          <label className="field">
            <span>事件类型</span>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option>价格</option><option>财报</option><option>公告</option><option>热度</option><option>舆情异常</option><option>估值分位</option>
            </select>
          </label>
          <label className="field">
            <span>条件（可选）</span>
            <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="例如：收盘价跌破 220 元" />
          </label>
          <div className="callout">
            <b>注意：</b>没有推送通道，事件只在收盘后记录日志；不推送“买/卖”指令。
          </div>
        </>
      ) : (
        <div className="callout">
          <b>{t("注意：", "Note:")}</b>
          {t("美股版只加入自选，不创建关注事件。", "US mode only adds the ticker to the watchlist; watch events are not available.")}
        </div>
      )}
    </Sheet>
  );
}
