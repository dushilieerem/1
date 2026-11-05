import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ChevronUp, Plus, X } from "lucide-react";
import { Sheet, Tag } from "../components";
import { useLocale } from "../i18n";

export type Condition = {
  key: string;
  label: string;
  label_en?: string;
  op?: string;
  value?: number | string;
  unit?: string;
  text?: string;
  supported?: boolean;
  supported_reason?: string | null;
  bool?: boolean;
};

export type ConditionItem = {
  code: string;
  name: string;
  industry?: string;
  price?: number | null;
  change_pct?: number | null;
  market_cap?: number | null;
  pe_ttm?: number | null;
  pe_percentile?: number | null;
  roe?: number | null;
};

export type RelaxAction = {
  type: "remove" | "widen" | "replace" | "add";
  key?: string;
  value?: number;
  query?: string;
  label: string;
};

export type ConditionResponse = {
  ok?: boolean;
  status?: "needs_input" | "empty" | "too_broad" | "ok";
  query?: string;
  conditions?: Condition[];
  parsed?: {
    conditions?: Condition[];
    unrecognized?: Array<{ text: string; suggestions: string[] }>;
    conflicts?: string[];
    unsupported?: Condition[];
    message?: string;
  };
  items?: ConditionItem[];
  count?: number;
  summary?: string[];
  risk?: string;
  disclaimer?: string;
  industry_distribution?: Array<{ name: string; count: number; pct: number }>;
  followups?: string[];
  diagnostic?: {
    blocking?: string;
    blocking_key?: string;
    suggestion?: string;
    relax_options?: string[];
    relax_actions?: RelaxAction[];
  };
  unrecognized?: Array<{ text: string; suggestions: string[] }>;
  conflicts?: string[];
  unsupported?: Condition[];
  message?: string;
};

export type ConditionPreset = {
  id: string;
  name: { zh: string; en: string };
  sub: { zh: string; en: string };
  query: string;
  dataNote?: { zh: string; en: string };
};

export const CONDITION_PRESETS: ConditionPreset[] = [
  {
    id: "value",
    name: { zh: "低估优选", en: "Quality value" },
    sub: { zh: "低估值 + 稳盈利", en: "Low valuation + steady profit" },
    query: "PE 分位低于 30%，近 3 年净利润连续增长，ROE 大于 10%",
  },
  {
    id: "dividend",
    name: { zh: "高股息防守", en: "Dividend defense" },
    sub: { zh: "低估值 + 高分红", en: "Low valuation + high payout" },
    query: "股息率大于 3%，PE 分位低于 30%，近 1 年最大回撤小于 25%",
  },
  {
    id: "smallcap",
    name: { zh: "小市值弹性", en: "Small-cap beta" },
    sub: { zh: "题材 + 成长 + 资金", en: "Theme + growth + flows" },
    query: "总市值小于 200 亿，近 20 日涨幅大于 10%，近 5 日主力净流入大于 5000 万",
    dataNote: { zh: "资金流数据待补", en: "Fund-flow data pending" },
  },
  {
    id: "inflow",
    name: { zh: "主力连续流入", en: "Persistent inflow" },
    sub: { zh: "资金连续买", en: "Consecutive buying" },
    query: "近 5 日主力净流入合计大于 5000 万，且连续 3 日为正",
    dataNote: { zh: "资金流数据待补", en: "Fund-flow data pending" },
  },
  {
    id: "breakout",
    name: { zh: "放量突破", en: "Volume breakout" },
    sub: { zh: "新高 + 成交放大", en: "New high + volume expansion" },
    query: "收盘价创 60 日新高，成交量大于 5 日均量 1.5 倍，且站上 60 日均线",
  },
  {
    id: "oversold",
    name: { zh: "超跌企稳", en: "Oversold stabilization" },
    sub: { zh: "回撤深 + 企稳", en: "Deep drawdown + stabilization" },
    query: "较 60 日高点回撤大于 25%，近 3 日连续收阳，成交额较前 5 日放大",
  },
];

export function looksLikeCondition(text: string): boolean {
  const q = (text || "").trim();
  if (!q) return false;
  if (/^(什么是|解释|介绍|怎么理解)/.test(q)) return false;
  if (/(选股|筛选|帮我找|找.*股票)/.test(q)) return true;
  return /(PE|ROE|市值|股息率|涨幅|回撤|均线|新高|净流入)/i.test(q)
    && /(大于|小于|低于|高于|不低于|不超过|创|站上|连续)/.test(q);
}

const label = (c: Condition, en: boolean) => (en ? c.label_en || c.label : c.label);
const fmtPrice = (v?: number | null) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(2));
const fmtPct = (v?: number | null) => {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
};

export function ConditionPicker({
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
      title={t("选股方向", "Screening direction")}
      sub={t("点一个方向，整句会填进输入框；数字和条件都可以改。", "Pick a direction to fill the full sentence into the input; edit numbers or conditions as needed.")}
    >
      <div className="condition-preset-list">
        {CONDITION_PRESETS.map((p) => (
          <button key={p.id} className="condition-preset" onClick={() => onSelect(p.query)}>
            <div>
              <b>{t(p.name.zh, p.name.en)}</b>
              <span>{t(p.sub.zh, p.sub.en)}</span>
            </div>
            {p.dataNote ? <Tag tone="gray">{t(p.dataNote.zh, p.dataNote.en)}</Tag> : null}
          </button>
        ))}
        <button className="condition-preset self" onClick={() => onSelect("")}>
          <div><b>{t("自己写", "Write my own")}</b><span>{t("从空白输入框开始", "Start from a blank input")}</span></div>
          <span className="hint">{t("可多行", "Multi-line")}</span>
        </button>
      </div>
    </Sheet>
  );
}

function IndustryBars({ rows }: { rows: Array<{ name: string; count: number; pct: number }> }) {
  const { t } = useLocale();
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="condition-industry">
      <div className="condition-subhead">{t("行业分布 · 申万一级", "Industry mix · SW level 1")}</div>
      {rows.slice(0, 8).map((r) => (
        <div className="industry-row" key={r.name}>
          <span className="industry-name">{r.name}</span>
          <span className="industry-bar"><i style={{ width: `${(r.count / max) * 100}%` }} /></span>
          <b>{r.count}</b>
          <em>{r.pct.toFixed(0)}%</em>
        </div>
      ))}
      {rows.length > 8 ? <p className="hint">{t(`其余 ${rows.length - 8} 个行业已省略`, `${rows.length - 8} more industries hidden`)}</p> : null}
    </div>
  );
}

export function ConditionScreener({
  data,
  busy,
  addedCodes,
  onRemoveCondition,
  onRelax,
  onAdd,
  onSaveGroup,
  onFollowup,
  onOpenStock,
}: {
  data: ConditionResponse;
  busy: boolean;
  addedCodes: Set<string>;
  onRemoveCondition: (key: string) => void;
  onRelax: (action: RelaxAction) => void;
  onAdd: (code: string) => void;
  onSaveGroup: (codes: string[], group: string) => Promise<{ added: number }>;
  onFollowup: (text: string) => void;
  onOpenStock: (code: string) => void;
}) {
  const { t, locale } = useLocale();
  const en = locale === "en";
  const [expanded, setExpanded] = useState(false);
  const [showIndustry, setShowIndustry] = useState(false);
  const [sortRoe, setSortRoe] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [group, setGroup] = useState("条件选股");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const parsed = data.parsed;
  const conditions = data.conditions || parsed?.conditions || [];
  const unrecognized = data.unrecognized || parsed?.unrecognized || [];
  const conflicts = data.conflicts || parsed?.conflicts || [];
  const unsupported = data.unsupported || parsed?.unsupported || [];
  const items = data.items || [];
  const status = data.status || (data.ok ? "ok" : "needs_input");
  const count = data.count ?? items.length;

  useEffect(() => {
    setExpanded(false);
    setShowIndustry(false);
    setSortRoe(false);
    setSaveMsg("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.query, data.status, data.count]);

  const sorted = useMemo(() => {
    if (!sortRoe) return items;
    return [...items].sort((a, b) => (b.roe ?? -999) - (a.roe ?? -999));
  }, [items, sortRoe]);
  const visible = expanded ? sorted : sorted.slice(0, 5);
  const supportedCount = conditions.filter((c) => c.supported !== false).length;

  const tags = (removable: boolean) => (
    <div className="condition-tags">
      {conditions.map((c) => {
        const bad = c.supported === false;
        return (
          <span className={`condition-tag ${bad ? "danger" : ""}`} key={`${c.key}-${c.text || c.label}`} title={bad ? c.supported_reason || t("数据待补", "Data pending") : c.text}>
            {label(c, en)}
            {bad ? <em>{t("数据待补", "Data pending")}</em> : null}
            {removable || bad ? (
              <button aria-label={t(`删除条件 ${label(c, en)}`, `Remove condition ${label(c, en)}`)} disabled={busy} onClick={() => onRemoveCondition(c.key)}>
                <X size={11} />
              </button>
            ) : null}
          </span>
        );
      })}
    </div>
  );

  if (status === "needs_input") {
    return (
      <section className="card condition-card">
        <div className="condition-head">
          <h2>{t("条件选股", "Stock screening")}</h2>
          <Tag tone="gray">{t(`已理解 ${supportedCount} 个条件`, `${supportedCount} conditions understood`)}</Tag>
        </div>
        {tags(false)}
        {unrecognized.map((u, i) => (
          <div className="condition-error" key={`${u.text}-${i}`}>
            <div><b>{u.text}</b> <span>{t("暂时无法识别", "not understood")}</span></div>
            {u.suggestions?.length ? (
              <div className="condition-suggest">
                {t("可换成：", "Try instead: ")}
                {u.suggestions.slice(0, 2).map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      const prefix = conditions.filter((c) => c.supported !== false).map((c) => c.text || c.label).join("，");
                      onFollowup(prefix ? `${prefix}，${s}` : s);
                    }}
                  >{s}</button>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {conflicts.map((c) => <p className="condition-conflict" key={c}>⚠ {c}</p>)}
        {unsupported.length ? (
          <p className="condition-conflict">
            ⚠ {t("资金流数据源暂未接入；点上方红色标签可先去掉该条件，其余条件可继续筛选。", "Fund-flow data is not connected yet. Remove the red condition to screen with the rest.")}
          </p>
        ) : null}
        {data.message ? <p className="hint">{data.message}</p> : null}
        {!conditions.length && !unrecognized.length && !conflicts.length ? <p className="hint">{t("请补充估值、涨幅、ROE、市值等条件。", "Add valuation, return, ROE or market-cap conditions.")}</p> : null}
        <p className="condition-risk">⚠ {data.disclaimer || data.risk || t("历史 EOD 数据 · 不含实时与资金流 · 非投资建议", "Historical EOD data · no intraday or fund flows · not investment advice")}</p>
      </section>
    );
  }

  if (status === "empty") {
    return (
      <section className="card condition-card">
        <div className="condition-head">
          <h2>{t("条件选股", "Stock screening")}</h2>
          <Tag tone="red">{t("0 只", "0 matches")}</Tag>
        </div>
        <p className="condition-lead">
          {t(
            `按你设定的 ${conditions.length} 个条件，没有筛到股票。最可能卡在「${data.diagnostic?.blocking || "条件"}」。`,
            `No stocks matched the ${conditions.length} conditions. The tightest one is likely “${data.diagnostic?.blocking || "your filters"}”.`,
          )}
        </p>
        <div className="condition-relax">
          {(data.diagnostic?.relax_actions || []).map((a) => (
            <button key={`${a.type}-${a.label}`} className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onRelax(a)}>{a.label}</button>
          ))}
        </div>
        <p className="condition-risk">⚠ {data.risk || data.disclaimer || t("历史 EOD 数据 · 非投资建议", "Historical EOD data · not investment advice")}</p>
      </section>
    );
  }

  if (status === "too_broad") {
    return (
      <section className="card condition-card">
        <div className="condition-head">
          <h2>{t("条件选股", "Stock screening")}</h2>
          <Tag tone="amber">{t(`${count} 只 · 条件偏松`, `${count} matches · too broad`)}</Tag>
        </div>
        <p className="condition-lead">{t(`超过 200 只上限，请再补一条条件收窄范围。`, `More than the 200-row limit. Add one more condition to narrow it.`)}</p>
        <p className="hint">{data.diagnostic?.suggestion}</p>
        <div className="condition-relax">
          {(data.diagnostic?.relax_actions || []).map((a) => (
            <button key={a.label} className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onRelax(a)}>{a.label}</button>
          ))}
        </div>
        <p className="condition-risk">⚠ {data.risk || data.disclaimer || t("历史 EOD 数据 · 非投资建议", "Historical EOD data · not investment advice")}</p>
      </section>
    );
  }

  return (
    <section className="card condition-card">
      <div className="condition-head">
        <h2>{t("条件选股", "Stock screening")}</h2>
        <Tag tone="blue">{t(`共 ${count} 只`, `${count} matches`)}</Tag>
      </div>
      <p className="condition-lead">{t(`按你设定的 ${conditions.length} 个条件，共筛出 ${count} 只。`, `${count} stocks match your ${conditions.length} conditions.`)}</p>
      {tags(true)}
      <div className="condition-list">
        {visible.map((item) => {
          const added = addedCodes.has(item.code);
          const change = item.change_pct;
          return (
            <div className="condition-row" key={item.code}>
              <button
                className={`condition-add ${added ? "added" : ""}`}
                aria-label={added ? t(`已加入自选 ${item.name}`, `${item.name} already in watchlist`) : t(`加入自选 ${item.name}`, `Add ${item.name} to watchlist`)}
                disabled={added || busy}
                onClick={() => onAdd(item.code)}
              >
                {added ? <Check size={14} /> : <Plus size={14} />}
              </button>
              <button className="condition-main" onClick={() => onOpenStock(item.code)}>
                <span className="condition-name">{item.name}</span>
                <span className="condition-sub">{item.code} · {item.industry || t("未分类", "Unclassified")}</span>
              </button>
              <div className="condition-quote">
                <b>{fmtPrice(item.price)}</b>
                <span className={Number(change) >= 0 ? "up" : "down"}>{fmtPct(change)}</span>
              </div>
            </div>
          );
        })}
      </div>
      {items.length > 5 ? (
        <button className="condition-more" onClick={() => setExpanded((v) => !v)}>
          {expanded ? t("收起", "Collapse") : t(`查看全部 ${count} 只 →`, `View all ${count} →`)}
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      ) : null}

      {data.summary?.length ? (
        <ul className="condition-summary">
          {data.summary.slice(0, 3).map((s) => <li key={s}>{s}</li>)}
        </ul>
      ) : null}
      <p className="condition-risk">⚠ {data.risk || t("筛选基于历史 EOD 数据；结果非投资建议。", "Based on historical EOD data; not investment advice.")}</p>

      <div className="condition-actions">
        {sortRoe ? <Tag tone="blue">{t("ROE 从高到低", "ROE high to low")}</Tag> : null}
        {!groupOpen ? (
          <button className="btn btn-ghost btn-sm" onClick={() => setGroupOpen(true)}>{t("存成自选分组", "Save as watchlist group")}</button>
        ) : (
          <div className="condition-group-form">
            <input value={group} maxLength={20} onChange={(e) => setGroup(e.target.value)} placeholder={t("分组名", "Group name")} aria-label={t("自选分组名", "Watchlist group name")} />
            <button
              className="btn btn-primary btn-sm"
              disabled={saving || busy || !items.length}
              onClick={async () => {
                setSaving(true);
                setSaveMsg("");
                try {
                  const res = await onSaveGroup(items.map((it) => it.code), group.trim() || "条件选股");
                  setSaveMsg(t(`已保存 ${res.added || items.length} 只到「${group.trim() || "条件选股"}」`, `Saved ${res.added || items.length} to “${group.trim() || "Screening"}”`));
                  setGroupOpen(false);
                } catch (e: any) {
                  setSaveMsg(e?.message || t("保存失败", "Save failed"));
                } finally {
                  setSaving(false);
                }
              }}
            >{saving ? t("保存中…", "Saving…") : t("保存", "Save")}</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setGroupOpen(false)} disabled={saving}>{t("取消", "Cancel")}</button>
          </div>
        )}
        {saveMsg ? <p className="hint">{saveMsg}</p> : null}
      </div>

      <div className="condition-followups">
        <b>{t("继续问", "Ask next")}</b>
        <div className="chips">
          {(data.followups || []).slice(0, 3).map((f) => (
            <button
              key={f}
              className="chip"
              onClick={() => {
                if (/行业/.test(f)) { setShowIndustry((v) => !v); return; }
                if (/ROE/.test(f)) { setSortRoe((v) => !v); setExpanded(true); return; }
                onFollowup(f);
              }}
            >{f}</button>
          ))}
        </div>
      </div>
      {showIndustry && data.industry_distribution?.length ? <IndustryBars rows={data.industry_distribution} /> : null}
    </section>
  );
}
