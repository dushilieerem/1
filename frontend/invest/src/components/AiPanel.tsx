import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { ErrorState } from "../components";

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
  title = "AI 解读",
  subtitle = "AI 只做数据解读与风险提示，不构成投资建议",
  endpoint,
  body,
  buttonLabel = "生成 AI 解读",
}: {
  title?: string;
  subtitle?: string;
  endpoint: string;
  body?: Record<string, unknown>;
  buttonLabel?: string;
}) {
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
          <Sparkles size={15} /> {title}
        </h2>
        <span className="hint">AI 生成 · 非投资建议</span>
      </div>
      <p className="ai-sub">{subtitle}</p>
      {!card && !error ? (
        <button className="btn btn-primary btn-sm ai-run" onClick={run} disabled={loading}>
          {loading ? "生成中…" : buttonLabel}
        </button>
      ) : null}
      {loading ? <div className="ai-loading">正在基于当前数据生成，通常需要 5–30 秒…</div> : null}
      {error ? <ErrorState message={error} onRetry={run} /> : null}
      {data?.blocked ? (
        <div className="ai-blocked">
          {card?.summary || "该请求涉及买卖点/目标价/收益承诺，已按合规规则拦截。"}
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
            {card.disclaimer || "AI 生成 · 非投资建议"} · {card.meta?.dataSource || "数据口径见页面"}
          </p>
          <button className="btn btn-ghost btn-sm" onClick={run} disabled={loading}>
            重新生成
          </button>
        </div>
      ) : null}
    </section>
  );
}
