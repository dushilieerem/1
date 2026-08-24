import { Link } from "react-router-dom";
import { BookOpen, MessageSquare, Search, Settings2 } from "lucide-react";

const STEPS = [
  {
    n: "1",
    title: "建知识库",
    body: "首页或「知识库」页创建集合，选类型与分块策略。可用 Markdown 标题分块或按窗口切。",
    to: "/datasets",
    link: "打开知识库",
  },
  {
    n: "2",
    title: "上传 / 粘贴文档",
    body: "进入某个库 → 上传 md/txt/docx/pdf 或粘贴正文。Word/纪要优先「按编号标题」或「按段落合并」；乱版 PDF 用「固定窗口」。扫描版 PDF 暂不支持。",
    to: "/datasets",
    link: "去上传",
  },
  {
    n: "3",
    title: "启用与停用",
    body: "文档列表可关「启用」。停用后仍保留切片，但检索与问答不再命中该文档。",
    to: "/datasets",
    link: "管理文档",
  },
  {
    n: "4",
    title: "检索测试",
    body: "库详情页进入「检索测试」，用关键词验证是否能搜到片段（有 Embedding 时走 hybrid）。",
    to: "/datasets",
    link: "从库进入检索",
  },
  {
    n: "5",
    title: "聊天问答",
    body: "「聊天」里建应用并关联知识库。提问会先检索再回答；无命中时明确说明未找到，不编造。",
    to: "/chats",
    link: "打开聊天",
  },
] as const;

export function GuidePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">KnowledgeHub 使用说明</h1>
        <p className="mt-1 text-sm text-slate-500">
          管理员操作路径：建库 → 入库解析 → 检索 / 问答。API 细节见同栏「API」。
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
        <p>
          <span className="text-slate-400">前端</span>{" "}
          <code className="text-xs">http://192.168.3.32:9531/</code>
        </p>
        <p className="mt-1">
          <span className="text-slate-400">API</span>{" "}
          <code className="text-xs">http://192.168.3.32:8766/api/kh/*</code>
          （需 admin JWT）
        </p>
        <p className="mt-2 flex flex-wrap gap-2">
          <Link
            to="/settings/api"
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-800"
          >
            <BookOpen className="h-3.5 w-3.5" />
            API 目录（含 search / ask）
          </Link>
          <a
            href="/api/kh/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Swagger
          </a>
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-800">五步上手</h2>
        <ol className="space-y-3">
          {STEPS.map((s) => (
            <li
              key={s.n}
              className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-sm font-bold text-white">
                {s.n}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-900">{s.title}</p>
                <p className="mt-1 text-sm text-slate-600">{s.body}</p>
                <Link
                  to={s.to}
                  className="mt-2 inline-block text-sm text-teal-700 hover:underline"
                >
                  {s.link} →
                </Link>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <Search className="h-4 w-4" />
          检索与问答约定
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
          <li>
            <code className="text-xs">POST /api/kh/search</code>：只返回命中切片，不生成回答。
          </li>
          <li>
            <code className="text-xs">POST /api/kh/ask</code>：必须基于检索片段；无命中不调
            LLM，明确「知识库未找到」。
          </li>
          <li>仅 <code className="text-xs">status=ready</code> 且 <code className="text-xs">enabled=true</code> 的文档参与检索。</li>
        </ul>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <Settings2 className="h-4 w-4" />
          模型与权限
        </h2>
        <p className="mt-2">
          「模型供应商」配置 LLM / Embedding。未配 Embedding 时检索退回关键词。整站仅{" "}
          <strong className="font-medium text-slate-800">admin</strong> 可进。
        </p>
        <p className="mt-2 flex flex-wrap gap-3">
          <Link to="/settings/models" className="text-teal-700 hover:underline">
            模型供应商 →
          </Link>
          <Link to="/chats" className="inline-flex items-center gap-1 text-teal-700 hover:underline">
            <MessageSquare className="h-3.5 w-3.5" />
            聊天 →
          </Link>
        </p>
      </section>
    </div>
  );
}
