import { useEffect, useState } from "react";
import { api } from "./api";
import { Sheet } from "./components";

export default function GlossarySheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [items, setItems] = useState<Array<{ term: string; text: string }>>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api<{ items: Array<{ term: string; text: string }> }>("/api/invest/glossary")
      .then((d) => setItems(d.items))
      .catch((e) => setError(e.message));
  }, [open]);

  return (
    <Sheet open={open} onClose={onClose} title="术语库" sub="通俗口径 · 非投资建议">
      {error ? <div className="form-error">{error}</div> : null}
      <div className="gloss-list">
        {items.map((it) => (
          <div className="gloss-item" key={it.term}>
            <b>{it.term}</b>
            <p>{it.text}</p>
          </div>
        ))}
      </div>
      <div className="hint">术语解释为通俗口径，正式定义以监管或教材为准。</div>
    </Sheet>
  );
}
