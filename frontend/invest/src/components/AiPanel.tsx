import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { api } from "../api";
import AiCharts, { type AiChartData } from "./AiChart";
import { ErrorState } from "../components";
import { useLocale } from "../i18n";

type Section = {
  key?: string;
  title?: string;
  type?: string;
  body?: string;
  items?: Array<{ k?: string; v?: string; tone?: string }>;
};

type Card = {
  summary?: string;
  sections?: Section[];
  disclaimer?: string;
  meta?: { dataSource?: string; engine?: string };
};

type AiResponse = {
  ok?: boolean;
  card?: Card;
  charts?: AiChartData[];
  engine?: string;
  blocked?: boolean;
  intent?: string;
  need_clarify?: string[];
  detail?: string;
};

export default function AiPanel({
  title,
  subtitle,
  endpoint,
  body,
  hideOnError = false,
  expandable = false,
  defaultExpanded = false,
}: {
  title?: string;
  subtitle?: string;
  endpoint: string;
  body?: Record<string, unknown>;
  hideOnError?: boolean;
  expandable?: boolean;
  defaultExpanded?: boolean;
}) {
  const { t } = useLocale();
  const resolvedTitle = title ?? t("AI 解读", "AI insights");
  const resolvedSubtitle = subtitle ?? t("AI 只做数据解读与风险提示，不构成投资建议", "AI only interprets data and flags risks; it is not investment advice");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AiResponse | null>(null);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const bodyKey = JSON.stringify(body || {});
  const startedKey = useRef("");

  const run = (refresh = false) => {
    setLoading(true);
    setError(null);
    const sep = endpoint.includes("?") ? "&" : "?";
    api<AiResponse>(`${endpoint}${sep}refresh=${refresh ? 1 : 0}`, {
      method: "POST",
      body: bodyKey,
    })
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    const key = `${endpoint}|${bodyKey}`;
    if (startedKey.current === key) return;
    startedKey.current = key;
    setExpanded(defaultExpanded);
    run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, bodyKey]);

  const card = data?.card;
  const engine = data?.engine || card?.meta?.engine;
  const sections = card?.sections || [];
  const charts = data?.charts || [];
  const hasCharts = charts.length > 0;
  if (hideOnError && error) return null;
  return (
    <section className="card ai-panel">
      <div className="card-title-row">
        <h2 className="row gap6">
          <Sparkles size={15} /> {resolvedTitle}
        </h2>
        <span className="hint">
          {engine === "rule"
            ? t("规则生成 · 非投资建议", "Rule-generated · Not investment advice")
            : t("AI 生成 · 非投资建议", "AI-generated · Not investment advice")}
        </span>
      </div>
      <p className="ai-sub">{resolvedSubtitle}</p>
      {loading && !card ? <div className="ai-loading">{t("正在基于当前数据生成，通常需要 5–30 秒…", "Generating from current data; usually takes 5–30 seconds…")}</div> : null}
      {error ? <ErrorState message={error} onRetry={() => run(false)} /> : null}
      {data?.blocked ? (
        <div className="ai-blocked">
          {card?.summary || t("该请求涉及买卖点/目标价/收益承诺，已按合规规则拦截。", "This request involves entry/exit levels, target prices or return promises and was blocked by compliance rules.")}
        </div>
      ) : null}
      {card && !data?.blocked ? (
        <div className="ai-result">
          {card.summary ? <p className="ai-summary">{card.summary}</p> : null}
          <AiCharts charts={charts} />
          {expandable && sections.length ? (
            <button
              type="button"
              className="ai-expand-toggle"
              aria-expanded={expanded}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded
                ? t("收起五维分析", "Collapse 5-dim analysis")
                : t("展开五维分析", "Expand 5-dim analysis")}
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          ) : null}
          {(!expandable || expanded) && sections.map((s, i) => (
            <div className="ai-section" key={s.key || i}>
              {s.title ? <b>{s.title}</b> : null}
              {s.body ? <p>{s.body}</p> : null}
              {!hasCharts && Array.isArray(s.items) && s.items.length ? (
                <div className="ai-metrics">
                  {s.items.map((it, j) => (
                    <span className={`ai-metric ${it.tone || ""}`} key={j}>
                      {it.k ? <em>{it.k}</em> : null}
                      {it.v ? <b>{it.v}</b> : null}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          <p className="ai-disclaimer">
            {card.disclaimer || t("AI 生成 · 非投资建议", "AI-generated · Not investment advice")} · {card.meta?.dataSource || t("数据口径见页面", "See the page for data basis")}
          </p>
          <button className="btn btn-ghost btn-sm" onClick={() => run(true)} disabled={loading}>
            {loading ? t("生成中…", "Generating…") : t("重新生成", "Regenerate")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
