import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  FlaskConical,
  LineChart,
  ShieldCheck,
  Users,
} from "lucide-react";
import { getStoredUser, subscribeAuth } from "@/lib/auth";

const FEATURES = [
  {
    icon: FlaskConical,
    title: "因子研究",
    desc: "内置动量、价值、波动、量价等因子库，支持自定义公式试算与一键检测。",
  },
  {
    icon: BarChart3,
    title: "回测验证",
    desc: "IC、分层收益、净值与回撤一站式报告，参数可复现、结果可对比。",
  },
  {
    icon: LineChart,
    title: "策略实验",
    desc: "从因子到组合，记录每一次研究路径，沉淀可复用的研究资产。",
  },
  {
    icon: Users,
    title: "研究社区",
    desc: "分享因子笔记与策略思路，收藏优质内容，与同路人一起迭代。",
  },
];

export function HomePage() {
  const [user, setUser] = useState(() => getStoredUser());
  useEffect(() => subscribeAuth(() => setUser(getStoredUser())), []);

  const primaryTo = user ? "/factor/library" : "/login?next=/factor/library";
  const detectTo = user ? "/factor/detect" : "/login?next=/factor/detect";

  return (
    <div className="overflow-hidden bg-[#f7f8fa]">
      <section className="relative border-b border-slate-200/80 bg-white">
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -left-24 top-0 h-[480px] w-[480px] rounded-full bg-red-500/5 blur-3xl" />
          <div className="absolute right-0 top-20 h-[420px] w-[420px] rounded-full bg-slate-900/5 blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-[1200px] px-6 pb-20 pt-16 lg:pb-28 lg:pt-24">
          <p className="text-sm font-semibold tracking-wide text-red-600">SVQuant 量化研究平台</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-5xl lg:text-[3.4rem]">
            做可验证的因子研究
            <span className="mt-2 block text-slate-500">从想法到回测，一站完成</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-600">
            面向量化研究员的因子库、检测与社区。统一股票池与回测口径，让每一次结论都能复现、可对比、可沉淀。
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <Link
              to={primaryTo}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-red-700"
            >
              进入因子库
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to={detectTo}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-800 hover:border-slate-300"
            >
              <BarChart3 className="h-4 w-4 text-red-500" />
              开始因子检测
            </Link>
            {!user ? (
              <Link
                to="/register"
                className="inline-flex items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                免费注册
              </Link>
            ) : null}
          </div>

          <div className="mt-14 grid gap-4 sm:grid-cols-3">
            {[
              { k: "统一口径", v: "股票池 · 区间 · 分层规则一致" },
              { k: "私有工作区", v: "自定义因子与检测记录按账号隔离" },
              { k: "研究社区", v: "笔记、问答与热点讨论" },
            ].map((x) => (
              <div key={x.k} className="rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-4">
                <p className="text-sm font-bold text-slate-900">{x.k}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{x.v}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">平台能力</h2>
            <p className="mt-1 text-sm text-slate-500">覆盖研究主链路：选因子 → 检测 → 复盘 → 分享</p>
          </div>
          <Link to={user ? "/community" : "/login?next=/community"} className="text-sm font-medium text-red-600">
            逛社区 →
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-8 px-6 py-14 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-xl">
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              账号级隔离
            </div>
            <h2 className="mt-3 text-2xl font-bold text-slate-900">你的研究默认私有</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              自定义因子、检测项目与历史记录均绑定登录账号。只有主动发到社区的内容才会公开，换账号不会看到他人工作区。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to={primaryTo}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              <BookOpen className="h-4 w-4" />
              打开我的因子库
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
