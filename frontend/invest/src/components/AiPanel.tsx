import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../api";
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
  meta?: { dataSource?: string };
};

type AiResponse = {
  ok?: boolean;
  card?: Card;
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
  buttonLabel,
}: {
  title?: string;
  subtitle?: string;
  endpoint: string;
  body?: Record<string, unknown>;
  buttonLabel?: string;
}) {
  const { t } = useLocale();
  const resolvedTitle = title ?? t("AI 解读", "AI insights");
  const resolvedSubtitle = subtitle ?? t("AI 只做数据解读与风险提示，不构成投资建议", "AI only interprets data and flags risks; it is not investment advice");
  const resolvedButtonLabel = buttonLabel ?? t("生成 AI 解读", "Generate AI insights");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AiResponse | null>(null);

  const run = () => {
    setLoading(true);
    setError(null);
    api<AiResponse>(endpoint, {
      method: "POST",
      body: JSON.stringify(body || {}),
    })
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const card = data?.card;
  return (
    <section className="card ai-panel">
      <div className="card-title-row">
        <h2 className="row gap6">
          <Sparkles size={15} /> {resolvedTitle}
        </h2>
        <span className="hint">{t("AI 生成 · 非投资建议", "AI-generated · Not investment advice")}</span>
      </div>
      <p className="ai-sub">{resolvedSubtitle}</p>
      {!card && !error ? (
        <button className="btn btn-primary btn-sm ai-run" onClick={run} disabled={loading}>
          {loading ? t("生成中…", "Generating…") : resolvedButtonLabel}
        </button>
      ) : null}
      {loading ? <div className="ai-loading">{t("正在基于当前数据生成，通常需要 5–30 秒…", "Generating from current data; usually takes 5–30 seconds…")}</div> : null}
      {error ? <ErrorState message={error} onRetry={run} /> : null}
      {data?.blocked ? (
        <div className="ai-blocked">
          {card?.summary || t("该请求涉及买卖点/目标价/收益承诺，已按合规规则拦截。", "This request involves entry/exit levels, target prices or return promises and was blocked by compliance rules.")}
        </div>
      ) : null}
      {card && !data?.blocked ? (
        <div className="ai-result">
          {card.summary ? <p className="ai-summary">{card.summary}</p> : null}
          {(card.sections || []).map((s, i) => (
            <div className="ai-section" key={s.key || i}>
              {s.title ? <b>{s.title}</b> : null}
              {s.body ? <p>{s.body}</p> : null}
              {Array.isArray(s.items) && s.items.length ? (
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
          <button className="btn btn-ghost btn-sm" onClick={run} disabled={loading}>
            {t("重新生成", "Regenerate")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
