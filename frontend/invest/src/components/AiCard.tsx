import { Sparkles } from "lucide-react";

export type AiSection = {
  key?: string;
  title?: string;
  type?: string;
  body?: string;
  items?: Array<{ k?: string; v?: string; tone?: string }>;
};

export type AiCardData = {
  card?: { summary?: string; sections?: AiSection[]; disclaimer?: string; meta?: { dataSource?: string } };
  blocked?: boolean;
};

export function AiCard({ data, title = "AI 解读" }: { data: AiCardData; title?: string }) {
  const card = data.card;
  if (!card?.summary && !card?.sections?.length) return null;
  return (
    <section className="card ai-panel">
      <div className="card-title-row">
        <h2 className="row gap6"><Sparkles size={15} /> {title}</h2>
        <span className="hint">AI 生成 · 非投资建议</span>
      </div>
      {data.blocked ? <div className="ai-blocked">{card.summary}</div> : <p className="ai-summary">{card.summary}</p>}
      {(card.sections || []).map((s, i) => (
        <div key={s.key || i} className="ai-section">
          {s.title ? <b>{s.title}</b> : null}
          {s.body ? <p>{s.body}</p> : null}
          {s.items?.length ? (
            <ul>
              {s.items.map((it, k) => (
                <li key={k}>
                  {it.k ? <span>{it.k}：</span> : null}
                  {it.v}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
      <p className="hint">{card.disclaimer || "AI 生成 · 非投资建议"}</p>
    </section>
  );
}
