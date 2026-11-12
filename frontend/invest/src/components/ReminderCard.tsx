import { Bell, CheckCircle2, ExternalLink } from "lucide-react";
import { Sheet, Tag } from "../components";
import { useLocale } from "../i18n";

export type ReminderItem = {
  symbol: string;
  name: string;
  type: string;
  type_label?: string;
  condition: string;
  threshold?: number | null;
  unit?: string;
  note: string;
  end_date?: string | null;
  term?: string;
};

export type ReminderSuggestion = {
  label: string;
  text: string;
  index?: number;
};

export type ReminderParse = {
  ok?: boolean;
  status: "ready" | "needs_input" | "blocked";
  reminders?: ReminderItem[];
  missing?: string[];
  suggestions?: ReminderSuggestion[];
  confirm_text?: string;
  question?: string;
  notice?: string;
  compliance?: string | null;
  duplicate_note?: string;
  scope_note?: string;
  warnings?: string[];
  duplicates?: number[];
  type_availability?: Record<string, { label: string; label_en: string; available: boolean; note?: string }>;
};

export type ReminderCreateResult = {
  ok?: boolean;
  created?: Array<ReminderItem & { id?: number; code?: string; term?: string }>;
  skipped?: Array<{ name?: string; symbol?: string; reason?: string }>;
  errors?: string[];
  count?: number;
  watchlist_count?: number;
};

function itemLine(item: ReminderItem & { code?: string }, t: (zh: string, en: string) => string) {
  const code = item.symbol || item.code || "";
  return `${item.name}${code ? `（${code}）` : ""} · ${item.note} · ${item.term || t("长期有效", "No end date")}`;
}

export default function ReminderCard({
  data,
  result,
  busy,
  addedWatch,
  onConfirm,
  onSuggestion,
  onEdit,
  onOpenWatch,
  onAddWatch,
}: {
  data: ReminderParse;
  result: ReminderCreateResult | null;
  busy: boolean;
  addedWatch?: Set<string>;
  onConfirm: () => void;
  onSuggestion: (text: string) => void;
  onEdit: () => void;
  onOpenWatch: (id?: number) => void;
  onAddWatch: (code: string) => void;
}) {
  const { t } = useLocale();
  const reminders = data.reminders || [];
  const missingSymbol = data.missing?.includes("symbol");
  const missingThreshold = data.missing?.includes("threshold");
  const unavailable = data.type_availability
    ? Object.values(data.type_availability).filter((x) => !x.available)
    : [];
  const unWatchlisted = (result?.created || []).filter(
    (item) => item.symbol && !(addedWatch?.has(item.symbol)),
  );

  if (result) {
    return (
      <section className="card reminder-card" aria-label={t("创建提醒结果", "Reminder created")}>
        <div className="reminder-head">
          <CheckCircle2 size={16} />
          <b>{t("已创建", "Created")}</b>
          <Tag tone="green">{t("生效中", "Active")}</Tag>
        </div>
        <ul className="reminder-created-list">
          {(result.created || []).map((item, i) => (
            <li key={`${item.symbol || item.code}-${i}`}>{itemLine(item, t)}</li>
          ))}
        </ul>
        {result.skipped?.length ? (
          <p className="hint">
            {t("这条已经有了，未重复创建：", "Already exists, not duplicated: ")}
            {result.skipped.map((x) => x.name || x.symbol || "").join("、")}
          </p>
        ) : null}
        {result.errors?.length ? <p className="hint">{result.errors.join("；")}</p> : null}
        <div className="reminder-sync">
          <span>
            {t(`已同步到「自选与提醒」— 共 ${result.count ?? 0} 条提醒`, `Synced to Watchlist & reminders — ${result.count ?? 0} reminder(s) in total`)}
          </span>
          <button type="button" className="link-btn" onClick={() => onOpenWatch(result.created?.[0]?.id)}>
            {t("查看提醒", "View reminders")} <ExternalLink size={12} />
          </button>
        </div>
        {unWatchlisted.length ? (
          <div className="callout">
            <b>{t("要不要顺便加入自选？", "Add to watchlist too?")}</b>
            <div className="reminder-watch-actions">
              {unWatchlisted.map((item) => {
                const code = item.symbol || item.code || "";
                return (
                  <button
                    key={code}
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={busy || addedWatch?.has(code)}
                    onClick={() => onAddWatch(code)}
                  >
                    {addedWatch?.has(code)
                      ? t("已加入", "Added")
                      : t(`加入 ${item.name}`, `Add ${item.name}`)}
                  </button>
                );
              })}
            </div>
            <p className="hint">{t("加自选是你的动作，不会自动替你做。", "Adding names is your call; we do not do it automatically.")}</p>
          </div>
        ) : null}
        <p className="reminder-foot">{data.notice || t("价格提醒按收盘价判断，盘中不推送。", "Price reminders are checked on closing prices; no intraday push.")}</p>
      </section>
    );
  }

  return (
    <section className="card reminder-card" aria-label={t("创建提醒确认", "Confirm reminder")}>
      <div className="reminder-head">
        <Bell size={16} />
        <b>{t("创建提醒", "Create reminder")}</b>
        <Tag tone="amber">{t("确认后创建", "Confirm to create")}</Tag>
      </div>

      {data.confirm_text ? (
        <p className="reminder-confirm-text">{data.confirm_text}</p>
      ) : (
        <ul className="reminder-created-list">
          {reminders.map((item, i) => <li key={`${item.symbol}-${i}`}>{itemLine(item, t)}</li>)}
        </ul>
      )}

      {data.scope_note ? <p className="hint">{data.scope_note}</p> : null}
      {data.compliance ? <div className="callout">{data.compliance}</div> : null}

      {data.question ? <p className="reminder-question">{data.question}</p> : null}

      {missingThreshold ? (
        <div className="reminder-suggestions">
          {(data.suggestions || []).map((item, i) => (
            <button key={`${item.label}-${i}`} type="button" className="chip" onClick={() => onSuggestion(item.text)} disabled={busy}>
              {item.label}
            </button>
          ))}
        </div>
      ) : null}

      {missingSymbol ? (
        <div className="reminder-suggestions">
          <button type="button" className="chip" onClick={onEdit}>{t("输入标的名称或代码", "Enter a name or code")}</button>
        </div>
      ) : null}

      {data.warnings?.length ? (
        <div className="condition-alert">
          <b>{t("⚠️ 注意：", "⚠️ Note:")}</b>
          <ul>{data.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      ) : null}

      {data.duplicate_note ? <p className="hint">{data.duplicate_note}</p> : null}

      {unavailable.length ? (
        <p className="hint">
          {t("数据待接入，暂不能创建：", "Data not connected yet: ")}
          {unavailable.map((x) => t(x.label, x.label_en)).join("、")}
        </p>
      ) : null}

      {data.status === "ready" ? (
        <div className="reminder-actions">
          <button type="button" className="btn btn-primary btn-sm" onClick={onConfirm} disabled={busy}>
            {busy ? t("创建中…", "Creating…") : t("确认创建", "Confirm")}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onEdit} disabled={busy}>
            {t("改一下", "Edit")}
          </button>
        </div>
      ) : data.status === "needs_input" ? (
        <div className="reminder-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onEdit} disabled={busy}>
            {t("改一下", "Edit")}
          </button>
        </div>
      ) : (
        <div className="reminder-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onEdit}>{t("换个提醒类型", "Change type")}</button>
        </div>
      )}

      <p className="reminder-foot">
        {data.notice || t("价格提醒按收盘价判断，盘中不推送。", "Price reminders are checked on closing prices; no intraday push.")}
      </p>
    </section>
  );
}

export function ReminderListCard({
  items,
  onOpenWatch,
}: {
  items: Array<ReminderItem & { detail?: string; status?: string; status_label?: string; id?: number }>;
  onOpenWatch: () => void;
}) {
  const { t } = useLocale();
  return (
    <section className="card reminder-card" aria-label={t("我的提醒", "My reminders")}>
      <div className="reminder-head">
        <Bell size={16} />
        <b>{t("我的提醒", "My reminders")}</b>
        <Tag tone="gray">{t(`${items.length} 条`, `${items.length} reminder(s)`)}</Tag>
      </div>
      {items.length === 0 ? (
        <p className="hint">{t("还没有提醒，可以直接说「宁德时代跌破 220 提醒我」。", "No reminders yet. Try “remind me when CATL falls below 220”.")}</p>
      ) : (
        <ul className="reminder-created-list">
          {items.map((item) => (
            <li key={item.id ?? `${item.symbol}-${item.note}`}>
              <b>{item.name} · {item.type_label}</b>
              <span className="hint"> {item.detail || item.note} · {item.status_label || t("生效中", "Active")}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="reminder-sync">
        <span>{t("修改、暂停或删除请在「自选与提醒」操作。", "Edit, pause or delete from Watchlist & reminders.")}</span>
        <button type="button" className="link-btn" onClick={onOpenWatch}>
          {t("去管理", "Manage")} <ExternalLink size={12} />
        </button>
      </div>
      <p className="reminder-foot">{t("收盘后检查，不提供盘中实时推送。", "Checked after the close; no intraday push.")}</p>
    </section>
  );
}

const PICKER_EXAMPLES = [
  { label: { zh: "价格", en: "Price" }, text: { zh: "宁德时代跌破 220 元提醒我", en: "Remind me when CATL falls below 220" } },
  { label: { zh: "财报", en: "Earnings" }, text: { zh: "宁德时代财报前 3 天提醒我", en: "Remind me 3 days before CATL reports" } },
  { label: { zh: "事件", en: "Event" }, text: { zh: "宁德时代有公告提醒我", en: "Remind me on CATL filings" } },
  { label: { zh: "估值", en: "Valuation" }, text: { zh: "宁德时代 PE 分位跌到 20% 以下提醒我", en: "Remind me when CATL PE percentile drops below 20%" } },
  { label: { zh: "资金", en: "Fund flow" }, text: { zh: "宁德时代主力连续 3 天净流出提醒我", en: "Remind me when CATL sees 3 straight days of main outflow" } },
  { label: { zh: "热度 / 舆情", en: "Heat / news" }, text: { zh: "宁德时代热度进 90 分位提醒我", en: "Remind me when CATL heat hits the 90th percentile" } },
];

export function ReminderPicker({
  onSelect,
  onClose,
}: {
  onSelect: (query: string) => void;
  onClose: () => void;
}) {
  const { t } = useLocale();
  return (
    <Sheet
      open
      onClose={onClose}
      title={t("创建提醒", "Create reminder")}
      sub={t("点一个类型，整句会填进输入框；标的、价格和时间都可以改。", "Pick a type to fill a sentence; edit the name, price or date.")}
    >
      <div className="reminder-picker-list">
        {PICKER_EXAMPLES.map((item) => (
          <button key={item.label.zh} type="button" className="reminder-picker-row" onClick={() => onSelect(t(item.text.zh, item.text.en))}>
            <b>{t(item.label.zh, item.label.en)}</b>
            <span>{t(item.text.zh, item.text.en)}</span>
          </button>
        ))}
      </div>
      <div className="callout">
        <b>{t("说明：", "Note:")}</b>
        {t("只做提醒，不代下单；价格类按收盘价判断，盘中不推送。", "Reminders only — no orders. Price alerts are checked on closing prices, not intraday.")}
      </div>
    </Sheet>
  );
}
