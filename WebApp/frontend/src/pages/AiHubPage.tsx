import { Link } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  FlaskConical,
  Lightbulb,
  LineChart,
  MessageSquare,
  Newspaper,
} from "lucide-react";

const MODULES = [
  {
    to: "/ai/chat",
    title: "SV 助手",
    desc: "多模型对话：问平台用法、读代码、梳理研究思路。",
    icon: MessageSquare,
    iconBg: "bg-sky-100 text-sky-600",
  },
  {
    to: "/ai/gather",
    title: "信息搜集",
    desc: "用自然语言问题检索资讯、研报、论文、帖子，做出资料汇总。",
    icon: Newspaper,
    iconBg: "bg-emerald-100 text-emerald-600",
  },
  {
    to: "/ai/idea",
    title: "研究假设",
    desc: "把资料汇总收成可转因子的研究假设，并给出建议回测窗。",
    icon: Lightbulb,
    iconBg: "bg-amber-100 text-amber-700",
  },
  {
    to: "/ai/factor",
    title: "因子草稿",
    desc: "把假设写成平台可回测的日频因子代码，人确认后再往下走。",
    icon: FlaskConical,
    iconBg: "bg-violet-100 text-violet-700",
  },
  {
    to: "/ai/factor-backtest",
    title: "回测报告",
    desc: "雏形：把因子参数发给平台回测，整理成报告。",
    icon: LineChart,
    iconBg: "bg-sky-100 text-sky-800",
  },
  {
    to: "/ai/factor-eval",
    title: "评价入库",
    desc: "雏形：根据回测报告给出入库建议，不自动写入库。",
    icon: BadgeCheck,
    iconBg: "bg-emerald-100 text-emerald-800",
  },
] as const;

export function AiHubPage() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-[#f6f8fb]">
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-14">
        <div className="text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80">
            <Bot className="h-7 w-7 text-sky-600" />
          </div>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-sky-600/80">
            SVQuant AI
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
            选择一个智能模块
          </h1>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-slate-500">
            搜集 → 假设 → 因子草稿 → 回测报告 → 评价入库。前两步是主路径；后三步可点开试用，确认后再往下传。
          </p>
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m) => {
            const Icon = m.icon;
            return (
              <Link
                key={m.to}
                to={m.to}
                className="group relative flex flex-col rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200/80 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-sky-200"
              >
                <div
                  className={`inline-flex h-11 w-11 items-center justify-center rounded-xl ${m.iconBg}`}
                >
                  <Icon className="h-5 w-5" />
                </div>
                <h2 className="mt-4 text-lg font-semibold text-slate-900">{m.title}</h2>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-500">{m.desc}</p>
                <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-sky-700">
                  进入
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
