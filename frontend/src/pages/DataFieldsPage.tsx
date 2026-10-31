import { useEffect, useMemo, useState } from "react";
import { FIELD_GROUPS } from "@/data/marketFieldCatalog";

type FieldSample = {
  ok?: boolean;
  data_version?: string | null;
  generated_at?: string | null;
  fields?: Record<string, unknown>;
  error?: string;
};

export function DataFieldsPage() {
  const [navId, setNavId] = useState(FIELD_GROUPS[0]?.id || "basic");
  const [sample, setSample] = useState<FieldSample | null>(null);
  const [sampleErr, setSampleErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/market-data/fields/samples", { cache: "no-store" })
      .then(async (res) => {
        const data = (await res.json().catch(() => ({}))) as FieldSample;
        if (cancelled) return;
        if (!res.ok || data.ok === false) {
          setSampleErr(data.error || `HTTP ${res.status}`);
          return;
        }
        setSample(data);
      })
      .catch((e) => {
        if (!cancelled) setSampleErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const group = useMemo(
    () => FIELD_GROUPS.find((g) => g.id === navId) || null,
    [navId],
  );

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-white">
      <div className="mx-auto flex max-w-[1440px] gap-0 lg:gap-8 px-0 lg:px-6 lg:py-6">
        <aside className="w-full shrink-0 border-b border-slate-200 bg-white lg:w-56 lg:border-b-0 lg:border-r lg:pr-4">
          <div className="px-4 py-4 lg:px-2 lg:pt-1">
            <div className="mb-2 px-2 text-xs font-semibold tracking-wide text-slate-400">
              数据文档
            </div>
            <nav className="space-y-0.5">
              {FIELD_GROUPS.map((g) => {
                const active = navId === g.id;
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => setNavId(g.id)}
                    className={`flex w-full rounded px-2 py-1.5 text-left text-sm leading-snug ${
                      active
                        ? "bg-sky-50 font-medium text-sky-700"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    {g.title}
                  </button>
                );
              })}
            </nav>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-2 lg:py-1">
          <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {sampleErr ? (
              <span className="text-amber-700">样例数据暂不可用：{sampleErr}</span>
            ) : sample ? (
              <span>
                数据版本 <code className="font-mono">{sample.data_version || "未知"}</code>
                {sample.generated_at ? ` · 生成于 ${sample.generated_at}` : ""}
                {sample.fields?.symbol ? (
                  <>
                    {" "}· 样例（{String(sample.fields.symbol)}，
                    {String(sample.fields.date || "最新")}）：PE{" "}
                    {String(sample.fields.pe_ttm ?? "—")} / PB{" "}
                    {String(sample.fields.pb_mrq ?? "—")}
                  </>
                ) : null}
              </span>
            ) : (
              "正在加载样例数据…"
            )}
          </div>
          {group ? (
            <article>
              <h1 className="mb-4 border-b border-slate-200 pb-3 text-2xl font-bold tracking-tight text-slate-900">
                {group.title}
              </h1>
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs font-medium text-slate-500">
                    <tr>
                      <th className="whitespace-nowrap px-3 py-2.5">字段</th>
                      <th className="whitespace-nowrap px-3 py-2.5">来源</th>
                      <th className="min-w-[280px] px-3 py-2.5">定义</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {group.fields.map((f) => (
                      <tr key={f.key} className="align-top hover:bg-slate-50/70">
                        <td className="px-3 py-3">
                          <div className="font-medium text-slate-900">
                            {f.nameZh}
                          </div>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                            {f.key}
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                          {f.source}
                        </td>
                        <td className="px-3 py-3 leading-relaxed text-slate-700">
                          {f.definition}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          ) : null}
        </main>
      </div>
    </div>
  );
}
