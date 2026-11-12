import { Sparkles } from "lucide-react";
import { useLocale } from "../i18n";

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

export function AiCard({
  data,
  title,
  onRegenerate,
  busy = false,
}: {
  data: AiCardData;
  title?: string;
  onRegenerate?: () => void;
  busy?: boolean;
}) {
  const { t } = useLocale();
  const resolvedTitle = title ?? t("AI 解读", "AI insights");
  const card = data.card;
  const summary = card?.summary
    || (card?.sections || []).find((s) => s.body)?.body
    || "";
  if (!summary) return null;
  return (
    <section className="card ai-panel">
      <div className="card-title-row">
        <h2 className="row gap6"><Sparkles size={15} /> {resolvedTitle}</h2>
        <span className="hint">{t("AI 生成 · 非投资建议", "AI-generated · Not investment advice")}</span>
      </div>
      {data.blocked ? <div className="ai-blocked">{summary}</div> : <p className="ai-summary">{summary}</p>}
      <div className="row gap6">
        <p className="hint" style={{ flex: 1 }}>{card.disclaimer || t("AI 生成 · 非投资建议", "AI-generated · Not investment advice")}</p>
        {onRegenerate ? (
          <button className="btn btn-ghost btn-sm" onClick={onRegenerate} disabled={busy}>
            {busy ? t("生成中…", "Generating…") : t("重新生成", "Regenerate")}
          </button>
        ) : null}
      </div>
    </section>
  );
}
