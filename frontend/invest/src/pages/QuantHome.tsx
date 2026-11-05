import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Calculator,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  History,
  Info,
  LineChart,
  Users,
  WalletCards,
} from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";
import type { FocusItem, Overview } from "../quant";

const ICONS: Record<string, typeof Calculator> = {
  factors: Calculator,
  strategies: LineChart,
  backtests: History,
  papers: WalletCards,
  community: Users,
};

const TYPE_LABEL: Record<string, [string, string]> = {
  strategy: ["策略", "Strategy"],
  paper: ["模拟盘", "Paper"],
  factor: ["因子", "Factor"],
  todo: ["待办", "To-do"],
};

const SEVERITY_TONE: Record<string, "red" | "amber" | "blue" | "gray"> = {
  strategy: "red",
  paper: "amber",
  factor: "amber",
  todo: "gray",
};

export default function QuantHome() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openFocus, setOpenFocus] = useState(false);

  const load = () => {
    setError(null);
    api<Overview>("/api/invest/quant/overview")
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, []);

  const openItem = (item: FocusItem) => {
    nav(item.link);
  };

  return (
    <div className="page quant-page">
      <PageHeader
        title={t("量化研究", "Quant research")}
        sub={t("因子、策略、回测、模拟盘与社区 · 只做研究与记账", "Factors, strategies, backtests, paper trading and community · research and bookkeeping only")}
      />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <>
          <section className="quant-focus">
            <button
              className="quant-focus-bar"
              onClick={() => {
                if (data.focus.count > 0) setOpenFocus((v) => !v);
              }}
              aria-expanded={openFocus}
            >
              <span className={`focus-dot ${data.focus.count ? "on" : ""}`} />
              <b>
                {data.focus.count
                  ? t(`今天 ${data.focus.count} 条待关注`, `${data.focus.count} item(s) to review today`)
                  : data.focus.empty_text}
              </b>
              {data.focus.count ? (
                openFocus ? <ChevronUp size={16} /> : <ChevronDown size={16} />
              ) : null}
            </button>
            {openFocus && data.focus.count ? (
              <div className="quant-focus-list">
                {data.focus.items.map((item, i) => (
                  <button className="quant-focus-item" key={`${item.type}-${item.id}-${i}`} onClick={() => openItem(item)}>
                    <div>
                      <div className="row gap6">
                        <Tag tone={SEVERITY_TONE[item.type] || "gray"}>{t(...(TYPE_LABEL[item.type] || [item.type, item.type]))}</Tag>
                        <b>{locale === "en" ? item.title_en || item.title : item.title}</b>
                      </div>
                      <p>{locale === "en" ? item.detail_en || item.detail : item.detail}</p>
                    </div>
                    <ChevronRight size={15} />
                  </button>
                ))}
              </div>
            ) : null}
          </section>

          <div className="quant-entries">
            {data.entries.map((entry) => {
              const Icon = ICONS[entry.key] || Info;
              return (
                <button className="quant-entry" key={entry.key} onClick={() => nav(entry.link)}>
                  <span className="entry-icon"><Icon size={19} /></span>
                  <span className="entry-text">
                    <b>{locale === "en" ? entry.title_en : entry.title}</b>
                    <small>{locale === "en" ? entry.status_en : entry.status}</small>
                  </span>
                  <ChevronRight size={17} className="entry-arrow" />
                </button>
              );
            })}
          </div>

          <div className="callout blue quant-note">
            <Info size={15} />
            <span>
              {t(
                "量化研究只提供规则计算、历史回测与模拟记录，不提供买卖点、目标价、仓位建议或收益承诺；模拟盘不接券商、不产生真实委托。",
                "Quant research provides rule-based calculations, historical backtests and simulated records only. It offers no entry/exit levels, target prices, position advice or return promises; paper accounts are not connected to a broker and place no real orders.",
              )}
            </span>
          </div>
          <p className="quant-foot">{data.disclaimer}</p>
        </>
      ) : null}
    </div>
  );
}
