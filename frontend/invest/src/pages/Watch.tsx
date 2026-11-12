import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Bell, Pause, Play, Plus, Search, Trash2 } from "lucide-react";
import { api } from "../api";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, SectionHead, Sheet, Tag } from "../components";
import { displayIndustry, fmtPct, formatPrice } from "../lib";
import { useToast } from "../toast";
import { useLocale, withMarket } from "../i18n";

export default function Watch() {
  const nav = useNavigate();
  const toast = useToast();
  const { t, market } = useLocale();
  const [params] = useSearchParams();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = () => {
    setError(null);
    api(withMarket("/api/invest/watchlist", market)).then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, [market]);

  const highlight = Number(params.get("highlight") || 0);
  const reminders: any[] = market === "CN" ? data?.events || [] : [];
  const reminderCount = data?.reminder_count ?? reminders.length;

  useEffect(() => {
    if (!data || !highlight) return;
    const el = document.getElementById(`reminder-${highlight}`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [data, highlight]);

  const remove = async (code: string) => {
    try {
      const next = await api(withMarket(`/api/invest/watchlist/${code}`, market), { method: "DELETE" });
      setData(next);
      toast(t("已移出自选", "Removed from watchlist"));
    } catch (e: any) {
      toast(e.message || t("操作失败", "Action failed"));
    }
  };

  const toggleReminder = async (reminder: any) => {
    setBusyId(reminder.id);
    try {
      const res = await api<{ status: string }>(`/api/invest/reminders/${reminder.id}/toggle`, { method: "POST" });
      toast(res.status === "paused" ? t("已暂停该提醒", "Reminder paused") : t("已恢复该提醒", "Reminder resumed"));
      load();
    } catch (e: any) {
      toast(e.message || t("操作失败", "Action failed"));
    } finally {
      setBusyId(null);
    }
  };

  const addWatch = async (code: string) => {
    try {
      await api(withMarket("/api/invest/watchlist", market), { method: "POST", body: JSON.stringify({ code }) });
      toast(t("已加入自选", "Added to watchlist"));
      load();
    } catch (e: any) {
      toast(e.message || t("加入自选失败", "Failed to add to watchlist"));
    }
  };

  const saveReminder = async (payload: Record<string, unknown>) => {
    if (!editing) return;
    setBusyId(editing.id);
    try {
      await api(`/api/invest/reminders/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      toast(t("提醒已更新", "Reminder updated"));
      setEditing(null);
      load();
    } catch (e: any) {
      toast(e.message || t("保存失败", "Save failed"));
    } finally {
      setBusyId(null);
    }
  };

  const deleteReminder = async (reminder: any) => {
    if (!window.confirm(t(`删除「${reminder.name} · ${reminder.type_label}」？`, `Delete “${reminder.name} · ${reminder.type_label}”?`))) return;
    setBusyId(reminder.id);
    try {
      await api(`/api/invest/reminders/${reminder.id}`, { method: "DELETE" });
      toast(t("提醒已删除", "Reminder deleted"));
      setEditing(null);
      load();
    } catch (e: any) {
      toast(e.message || t("删除失败", "Delete failed"));
    } finally {
      setBusyId(null);
    }
  };

  const count = data?.groups?.reduce((n: number, g: any) => n + g.items.length, 0) || 0;
  const usUnavailable = market === "US" && data?.available === false;
  const statusTone = (status: string) => (status === "active" ? "green" : status === "triggered" ? "amber" : "gray");
  const statusText = (reminder: any) => reminder.status_label || t("生效中", "Active");

  return (
    <div className="page">
      <PageHeader
        title={t("自选", "Watchlist")}
        sub={
          market === "US"
            ? t(`${count} 只 · 美股行情`, `${count} name(s) · US quotes`)
            : t(`${count} 只 · ${reminderCount} 条提醒`, `${count} name(s) · ${reminderCount} reminder(s)`)
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
          <SectionHead
            title="提醒"
            sub={t(`收盘后检查 · 不提供盘中实时推送 · ${reminderCount} 条`, `Checked after the close · no intraday push · ${reminderCount} reminder(s)`)}
            action={<button className="link-btn" onClick={() => setAddOpen(true)}><Plus size={14} /> {t("新建", "New")}</button>}
          />
          <section className="card list-card">
            {reminders.length === 0 ? (
              <div className="empty-inline">{t("还没有提醒。", "No reminders yet.")}</div>
            ) : reminders.map((e: any) => (
              <div
                className={`reminder-row ${highlight === Number(e.id) ? "reminder-highlight" : ""}`}
                id={`reminder-${e.id}`}
                key={e.id}
              >
                <span className="event-icon"><Bell size={15} /></span>
                <button className="reminder-main" onClick={() => setEditing(e)}>
                  <span className="reminder-title">
                    <b>{e.name || e.code} · {e.type_label || t("价格提醒", "Price reminder")}</b>
                    {e.source_label ? <Tag tone="blue">{e.source_label}</Tag> : null}
                    {e.watchlisted === false ? <Tag tone="gray">{t("未加自选", "Not watched")}</Tag> : null}
                  </span>
                  <span className="reminder-detail">{e.detail || e.note}</span>
                </button>
                <div className="reminder-side">
                  <Tag tone={statusTone(e.status)}>{statusText(e)}</Tag>
                  <button
                    type="button"
                    className="reminder-toggle"
                    aria-label={e.status === "active" ? t(`暂停 ${e.name} 的提醒`, `Pause ${e.name}`) : t(`恢复 ${e.name} 的提醒`, `Resume ${e.name}`)}
                    disabled={busyId === e.id}
                    onClick={() => void toggleReminder(e)}
                  >
                    {e.status === "active" ? <Pause size={13} /> : <Play size={13} />}
                  </button>
                </div>
              </div>
            ))}
            {reminders.some((e: any) => e.watchlisted === false) ? (
              <div className="reminder-unwatched">
                <span>{t("有提醒的标的未在自选。", "Some reminders are on names not in your watchlist.")}</span>
                {reminders.filter((e: any) => e.watchlisted === false).slice(0, 3).map((e: any) => (
                  <button key={e.code} type="button" className="link-btn" onClick={() => void addWatch(e.code)}>
                    {t(`加入 ${e.name}`, `Add ${e.name}`)}
                  </button>
                ))}
              </div>
            ) : null}
            <p className="reminder-section-foot">{t("价格提醒按收盘价判断；事件类在事件发生时记录。", "Price reminders use closing prices; event reminders are logged when the event occurs.")}</p>
          </section>

          <SectionHead title="触发日志" sub={t("近 7 天 · 打开时刷新", "Last 7 days · refreshed on open")} />
          <section className="card list-card" id="trigger-log">
            {(data.logs || []).length === 0 ? (
              <div className="empty-inline">{t("还没有触发记录。", "No triggered records yet.")}</div>
            ) : data.logs.map((l: any) => (
              <div className="log-row" key={l.id}>
                <div>
                  <b>{l.title}</b>
                  <span>{l.detail} · {l.triggered_at}</span>
                </div>
                <div className="log-tags">
                  {l.source_label ? <Tag tone="blue">{l.source_label}</Tag> : null}
                  <Tag tone={l.read ? "gray" : "amber"}>{l.read ? t("已读", "Read") : t("待关注", "Unread")}</Tag>
                </div>
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

      {editing ? (
        <EditReminderSheet
          key={editing.id}
          reminder={editing}
          busy={busyId === editing.id}
          onClose={() => setEditing(null)}
          onSave={(payload) => void saveReminder(payload)}
          onDelete={() => void deleteReminder(editing)}
          onOpenLogs={() => {
            setEditing(null);
            document.getElementById("trigger-log")?.scrollIntoView({ block: "start", behavior: "smooth" });
          }}
        />
      ) : null}

      <AddWatchSheet market={market} open={addOpen} onClose={() => setAddOpen(false)} onDone={() => { setAddOpen(false); load(); }} />
    </div>
  );
}

function EditReminderSheet({
  reminder,
  busy,
  onClose,
  onSave,
  onDelete,
  onOpenLogs,
}: {
  reminder: any;
  busy: boolean;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => void;
  onDelete: () => void;
  onOpenLogs: () => void;
}) {
  const { t } = useLocale();
  const [threshold, setThreshold] = useState(reminder.threshold == null ? "" : String(reminder.threshold));
  const [endDate, setEndDate] = useState(reminder.end_date || "");
  const [note, setNote] = useState(reminder.note || "");
  const unit = reminder.unit || "";
  const numberType = reminder.type === "event";
  return (
    <Sheet
      open
      onClose={onClose}
      title={t("修改提醒", "Edit reminder")}
      sub={`${reminder.name} · ${reminder.type_label || ""} · ${reminder.term || t("长期有效", "No end date")}`}
      footer={
        <div className="reminder-sheet-actions">
          <button type="button" className="btn btn-ghost" onClick={onDelete} disabled={busy}>
            <Trash2 size={14} /> {t("删除", "Delete")}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => onSave({
              threshold: numberType ? undefined : threshold === "" ? undefined : Number(threshold),
              end_date: endDate || null,
              note,
            })}
          >
            {busy ? t("保存中…", "Saving…") : t("保存修改", "Save")}
          </button>
        </div>
      }
    >
      <div className="reminder-edit-detail">
        <b>{t("当前条件", "Current condition")}</b>
        <span>{reminder.detail || reminder.note}</span>
      </div>
      {numberType ? null : (
        <label className="field">
          <span>{t("阈值", "Threshold")}{unit ? `（${unit}）` : ""}</span>
          <input
            type="number"
            inputMode="decimal"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            placeholder={reminder.threshold == null ? t("请输入阈值", "Enter a threshold") : String(reminder.threshold)}
          />
        </label>
      )}
      <label className="field">
        <span>{t("截止日期（留空为长期有效）", "End date (blank = no end date)")}</span>
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
      </label>
      <label className="field">
        <span>{t("描述", "Description")}</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={reminder.note} />
      </label>
      <button type="button" className="link-btn" onClick={onOpenLogs}>{t("查看触发记录", "View trigger log")}</button>
      <div className="callout">
        <b>{t("说明：", "Note:")}</b>
        {t("修改只影响之后的判断；已触发的记录不会回滚。只做提醒，不代下单。", "Edits apply to future checks only; triggered logs are kept. Reminders never place orders.")}
      </div>
    </Sheet>
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
  const [type, setType] = useState("价格提醒");
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
      toast(market === "US" ? t("已加入自选", "Added to watchlist") : t("已加入自选并创建提醒", "Added to watchlist and created a reminder"));
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
      title={market === "US" ? t("添加美股自选", "Add US ticker") : t("添加自选 / 提醒", "Add to watchlist / reminder")}
      sub={t("收盘后检查 · 不提供盘中实时推送", "Checked after the close · no intraday push")}
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
            <span>{t("提醒类型", "Reminder type")}</span>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option>价格提醒</option><option>财报提醒</option><option>事件提醒</option>
              <option>估值提醒</option><option>资金提醒</option><option>热度提醒</option>
            </select>
          </label>
          <label className="field">
            <span>{t("条件（可选）", "Condition (optional)")}</span>
            <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder={t("例如：收盘价跌破 220 元", "e.g. close below 220")} />
          </label>
          <div className="callout">
            <b>{t("注意：", "Note:")}</b>
            {t("收盘后检查，不提供盘中实时推送；只做提醒，不推送买卖指令。", "Checked after the close; no intraday push. Reminders only, never buy/sell instructions.")}
          </div>
        </>
      ) : (
        <div className="callout">
          <b>{t("注意：", "Note:")}</b>
          {t("美股版只加入自选，不创建提醒。", "US mode only adds the ticker to the watchlist; reminders are not available.")}
        </div>
      )}
    </Sheet>
  );
}
