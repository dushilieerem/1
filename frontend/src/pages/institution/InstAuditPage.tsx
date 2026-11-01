import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ScrollText } from "lucide-react";
import { instApi } from "@/lib/instApi";
import { useInstLocale } from "@/components/institution/instLocale";
import { Button, Card, Empty, ErrorBox, Loading, PageHeader } from "./instUi";

type AuditRow = {
  id: number;
  action: string;
  object_type?: string;
  object_id?: number;
  actor_member_id?: number;
  policy_version?: string;
  ip?: string;
  created_at?: string;
  after?: Record<string, unknown> | null;
};

function summarise(after: Record<string, unknown> | null | undefined): string {
  if (!after) return "—";
  const parts = Object.entries(after)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .slice(0, 4)
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`);
  return parts.length ? parts.join(" · ") : "—";
}

export function InstAuditPage() {
  const { t } = useInstLocale();
  const [items, setItems] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    instApi<{ items: AuditRow[] }>("/audit?limit=200")
      .then((d) => setItems(d.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="AUDIT"
        title={t("审计日志", "Audit log")}
        desc={t(
          "只增不改的机构端操作记录：时间、角色、动作、对象与结果。",
          "Append-only institutional audit trail: time, actor, action, object and result.",
        )}
        actions={
          <Link to="/inst/overview">
            <Button variant="ghost">
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回驾驶舱", "Back to cockpit")}
            </Button>
          </Link>
        }
      />
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {loading ? (
        <Loading label={t("正在加载审计日志…", "Loading audit log…")} />
      ) : items.length ? (
        <Card title={t("最近 200 条", "Latest 200")} desc={t("按时间倒序；不含业务内容正文。", "Newest first; no business content bodies.")}>
          <ul className="divide-y divide-[#f0ece2]">
            {items.map((row) => (
              <li key={row.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-xs text-slate-800">{row.action}</span>
                  <span className="text-[10px] text-slate-400">{row.created_at || "—"}</span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  {row.object_type || "—"}
                  {row.object_id != null ? ` #${row.object_id}` : ""} · {t("操作人", "Actor")}{" "}
                  {row.actor_member_id ?? "—"} · {row.policy_version || "—"}
                  {row.ip ? ` · ${row.ip}` : ""}
                </p>
                <p className="mt-1 break-all font-mono text-[10px] text-slate-400">{summarise(row.after)}</p>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <Empty>
          <ScrollText className="mx-auto mb-2 h-6 w-6 text-slate-300" />
          {t("还没有审计记录。", "No audit records yet.")}
        </Empty>
      )}
    </div>
  );
}
