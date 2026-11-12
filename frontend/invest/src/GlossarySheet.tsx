import { useEffect, useState } from "react";
import { api } from "./api";
import { Sheet } from "./components";
import { useLocale } from "./i18n";

export default function GlossarySheet({
  open,
  onClose,
  items: provided,
}: {
  open: boolean;
  onClose: () => void;
  items?: Array<{ term: string; text: string }>;
}) {
  const { t } = useLocale();
  const [items, setItems] = useState<Array<{ term: string; text: string }>>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (provided?.length) {
      setItems(provided);
      return;
    }
    api<{ items: Array<{ term: string; text: string }> }>("/api/invest/glossary")
      .then((d) => setItems(d.items))
      .catch((e) => setError(e.message));
  }, [open, provided]);

  return (
    <Sheet open={open} onClose={onClose} title={t("术语库", "Glossary")} sub={t("通俗口径 · 非投资建议", "Plain language · not investment advice")}>
      {error ? <div className="form-error">{error}</div> : null}
      <div className="gloss-list">
        {items.map((it) => (
          <div className="gloss-item" key={it.term}>
            <b>{it.term}</b>
            <p>{it.text}</p>
          </div>
        ))}
      </div>
      <div className="hint">{t("术语解释为通俗口径，正式定义以监管或教材为准。", "Glossary entries are plain-language summaries; formal definitions follow regulators or textbooks.")}</div>
    </Sheet>
  );
}
