import { BookOpen, Construction, LifeBuoy } from "lucide-react";
import { Link } from "react-router-dom";

/** 顶栏「帮助」：平台文档入口（含 API 说明占位） */
export function HelpPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 sm:py-16 lg:py-20">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-10">
        <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-sm font-medium text-slate-700">
          <LifeBuoy className="h-4 w-4 text-red-600" />
          帮助中心
        </div>
        <h1 className="mt-5 flex items-center gap-2 text-xl font-bold text-slate-900 sm:text-2xl">
          <BookOpen className="h-6 w-6 shrink-0 text-red-600" />
          文档与接口说明
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-600 sm:text-base">
          这里汇总平台使用说明与接口文档入口。OpenAPI / 业务接口说明仍在完善中；当前可先查阅
          KnowledgeHub 侧 API 页。
        </p>

        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50/80 px-4 py-3">
          <p className="inline-flex items-center gap-2 text-sm font-medium text-amber-900">
            <Construction className="h-4 w-4 shrink-0" />
            API 接口文档 · 待开发
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-amber-800/90 sm:text-sm">
            主站内完整接口说明页尚未上线，临时可打开 KnowledgeHub 文档。
          </p>
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:border-slate-300"
          >
            返回首页
          </Link>
          <a
            href="http://127.0.0.1:9531/settings/api"
            className="inline-flex items-center justify-center rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700"
          >
            打开 KnowledgeHub API 文档
          </a>
        </div>
      </div>
    </div>
  );
}

/** @deprecated 旧路由兼容，请用 HelpPage */
export const ApiDocsPlaceholderPage = HelpPage;
