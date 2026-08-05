import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { fetchApiOutline, type ApiCatalog, type ApiEndpointDoc } from "@/lib/api";

const METHOD_COLOR: Record<string, string> = {
  GET: "bg-sky-100 text-sky-800",
  POST: "bg-emerald-100 text-emerald-800",
  PUT: "bg-amber-100 text-amber-900",
  DELETE: "bg-rose-100 text-rose-800",
};

function EndpointRow({ ep }: { ep: ApiEndpointDoc }) {
  const [open, setOpen] = useState(false);
  const planned = ep.status === "planned";
  return (
    <div className={`border-b border-slate-100 last:border-0 ${planned ? "opacity-60" : ""}`}>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50"
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`w-16 shrink-0 rounded px-2 py-0.5 text-center text-xs font-bold ${
            METHOD_COLOR[ep.method] || "bg-slate-100"
          }`}
        >
          {ep.method}
        </span>
        <code className="min-w-0 flex-1 truncate text-sm text-slate-800">{ep.path}</code>
        <span className="hidden max-w-xs truncate text-sm text-slate-500 sm:inline">
          {ep.summary}
        </span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${
            planned ? "bg-slate-100 text-slate-500" : "bg-emerald-50 text-emerald-700"
          }`}
        >
          {planned ? "待接" : "已就绪"}
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
        )}
      </button>
      {open ? (
        <div className="space-y-3 border-t border-slate-50 bg-slate-50/80 px-4 py-3 text-sm">
          <p className="text-slate-700 sm:hidden">{ep.summary}</p>
          <div>
            <p className="text-xs font-medium text-slate-500">请求体示例</p>
            <pre className="mt-1 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
              {ep.request == null
                ? "（无 body）"
                : JSON.stringify(ep.request, null, 2)}
            </pre>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500">返回示例</p>
            <pre className="mt-1 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
              {ep.responseExample == null
                ? "—"
                : JSON.stringify(ep.responseExample, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ApiDocsPage() {
  const [data, setData] = useState<ApiCatalog | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void fetchApiOutline()
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const ready = data?.endpoints.filter((e) => e.status === "ready").length ?? 0;
  const total = data?.endpoints.length ?? 0;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">{data?.title || "KnowledgeHub API"}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {data?.note ||
              "供 SVQuant 自有 AI 调用。问答必须基于检索片段，禁止无依据编造。"}
          </p>
        </div>
        {data ? (
          <div className="flex items-center gap-2 text-xs">
            <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
              {data.version}
            </span>
            <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-700">
              已就绪 {ready}/{total}
            </span>
          </div>
        ) : null}
      </div>

      {err ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}

      {data ? (
        <>
          <div className="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
            <p>
              <span className="text-slate-400">Base</span>{" "}
              <code>{data.baseUrl}</code>
            </p>
            <p className="mt-1">
              <span className="text-slate-400">鉴权</span>{" "}
              <code className="text-xs">{data.auth}</code>
            </p>
            <p className="mt-2">
              <a
                className="inline-flex items-center rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-800"
                href="/api/kh/docs"
                target="_blank"
                rel="noreferrer"
              >
                打开 Swagger 测试页（Try it out）
              </a>
              <span className="ml-2 text-xs text-slate-400">
                或直接访问 http://192.168.3.32:8766/api/kh/docs
              </span>
            </p>
            <p className="mt-1 text-xs text-slate-400">
              新接口写入 <code>store.api_catalog()</code> 后会出现在本页与 Swagger。
            </p>
          </div>

          <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="border-b border-slate-100 bg-slate-50 px-4 py-2 text-xs font-medium text-slate-500">
              default · 点击展开请求 / 返回示例
            </div>
            {data.endpoints.map((ep) => (
              <EndpointRow key={ep.id} ep={ep} />
            ))}
          </div>
        </>
      ) : !err ? (
        <p className="mt-6 text-sm text-slate-400">加载中…</p>
      ) : null}
    </div>
  );
}
