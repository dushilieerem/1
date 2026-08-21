import { useEffect, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  CandlestickChart,
  FlaskConical,
  LineChart,
  Newspaper,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { getStoredUser, subscribeAuth } from "@/lib/auth";
import { listCommunityPosts, type CommunityPost } from "@/lib/communityApi";
import {
  AnimatedEquityChart,
  AnimatedLayerChart,
  CommunityAreaSpark,
  CommunityHBarSpark,
  SoftMeshBackground,
} from "@/components/landing/LandingVisuals";

type Entry = {
  icon: ComponentType<{ className?: string }>;
  title: string;
  line: string;
  desc: string;
  to: string;
  needAuth: boolean;
};

const MODULES: Entry[] = [
  {
    icon: CandlestickChart,
    title: "行情数据",
    line: "K线与自选",
    desc: "看盘与自选组合，把研究建立在真实行情之上。",
    to: "/data/kline",
    needAuth: true,
  },
  {
    icon: FlaskConical,
    title: "因子研究",
    line: "因子库与 AI",
    desc: "内置与自定义因子，也可用 AI 快速起草新想法。",
    to: "/factor/library",
    needAuth: true,
  },
  {
    icon: BarChart3,
    title: "检测报告",
    line: "IC / 分层 / 净值",
    desc: "查看历次检测结果，可复现、可对比。",
    to: "/factor/detect",
    needAuth: true,
  },
  {
    icon: LineChart,
    title: "策略研究",
    line: "组合与回测",
    desc: "从因子到组合，记录研究路径与关键参数。",
    to: "/strategy/research",
    needAuth: true,
  },
  {
    icon: Newspaper,
    title: "资讯中心",
    line: "市场与政策",
    desc: "聚合研报与政策动态，补全研究上下文。",
    to: "/news",
    needAuth: false,
  },
  {
    icon: Users,
    title: "研究社区",
    line: "分享与讨论",
    desc: "发布因子笔记与策略思路，和同路人一起迭代。",
    to: "/community",
    needAuth: false,
  },
];

const SAMPLE_BACKTESTS = [
  {
    name: "动量分层多空",
    ret: "+33.8%",
    to: "/community/post/66",
    kind: "area" as const,
  },
  {
    name: "价值增强组合",
    ret: "+12.7%",
    to: "/community/post/67",
    kind: "hbar" as const,
  },
] as const;

const DEMO_POSTS = [
  {
    id: "demo1",
    title: "欢迎来到 SVQuant 研究社区，分享你的因子笔记",
    author: "SVQuant",
    initial: "S",
  },
  {
    id: "demo2",
    title: "价值因子在沪深300 上的分层表现摘要",
    author: "研究员A",
    initial: "A",
  },
  {
    id: "demo3",
    title: "短期动量策略回测思路与参数记录",
    author: "量化B",
    initial: "B",
  },
] as const;

function formatPostTime(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function AvatarBubble({
  name,
  url,
  initial,
}: {
  name: string;
  url?: string | null;
  initial?: string;
}) {
  const letter = (initial || name || "?").trim().slice(0, 1).toUpperCase();
  if (url) {
    return (
      <img
        src={url}
        alt=""
        className="h-8 w-8 shrink-0 rounded-full object-cover ring-1 ring-slate-200"
      />
    );
  }
  return (
    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-rose-100 to-sky-100 text-xs font-semibold text-slate-700 ring-1 ring-slate-200/80">
      {letter}
    </span>
  );
}

export function HomePage() {
  const [user, setUser] = useState(() => getStoredUser());
  const [posts, setPosts] = useState<CommunityPost[]>([]);

  useEffect(() => subscribeAuth(() => setUser(getStoredUser())), []);

  useEffect(() => {
    let cancelled = false;
    listCommunityPosts({ sort: "newest", limit: 6 })
      .then((res) => {
        if (!cancelled) setPosts(res.items || []);
      })
      .catch(() => {
        if (!cancelled) setPosts([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const gate = (path: string, needAuth: boolean) =>
    needAuth && !user ? `/login?next=${encodeURIComponent(path)}` : path;

  const primaryTo = gate("/factor/library", true);

  return (
    <div className="overflow-hidden bg-[#f5f8fc]">
      <section className="relative overflow-hidden">
        <SoftMeshBackground />
        <div className="relative mx-auto grid max-w-[1160px] items-stretch gap-8 px-4 pb-8 pt-10 sm:gap-10 sm:px-6 sm:pb-10 sm:pt-14 lg:grid-cols-[0.95fr_1.05fr] lg:gap-12 lg:pb-12 lg:pt-16">
          <div className="flex flex-col justify-center">
            <p className="font-display landing-hero-title text-4xl font-bold tracking-tight text-slate-900 sm:text-6xl lg:text-[4.5rem] lg:leading-[1.05]">
              SVQuant
            </p>
            <h1 className="font-display landing-hero-sub mt-3 text-xl font-semibold text-slate-800 sm:mt-4 sm:text-3xl">
              从想法到回测
            </h1>
            <p className="landing-hero-cta mt-3 max-w-md text-[15px] leading-relaxed text-slate-600 sm:mt-4 sm:text-lg">
              数据、因子、检测、策略、资讯与社区协同，把每一次结论做可验证、可对比。
            </p>
            <div className="landing-hero-cta mt-6 flex flex-wrap items-center gap-3 sm:mt-8 sm:gap-4">
              <Link
                to={primaryTo}
                className="landing-wiggle-hover inline-flex items-center gap-2 rounded-xl bg-red-600 px-6 py-3 text-sm font-semibold text-white shadow-[0_14px_34px_-14px_rgba(220,38,38,0.7)] transition hover:bg-red-700 sm:px-7 sm:py-3.5"
              >
                进入因子库
                <ArrowRight className="h-4 w-4" />
              </Link>
              {!user ? (
                <Link
                  to="/register"
                  className="text-sm font-semibold text-slate-600 transition hover:text-red-600"
                >
                  免费注册
                </Link>
              ) : (
                <Link
                  to="/community"
                  className="text-sm font-semibold text-slate-600 transition hover:text-red-600"
                >
                  逛社区
                </Link>
              )}
            </div>
          </div>

          <div className="landing-hero-visual flex min-h-[260px] flex-col gap-3 sm:min-h-[320px] lg:min-h-[360px]">
            <AnimatedEquityChart title="示例：策略净值 vs 基准" />
            <AnimatedLayerChart title="示例：因子分层累计收益" />
          </div>
        </div>
      </section>

      <section className="relative bg-white/60">
        <div className="mx-auto max-w-[1160px] px-6 pb-16 pt-10 lg:pb-20 lg:pt-12">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900">
            平台能力
          </h2>
          <p className="mt-3 max-w-xl text-base text-slate-600">
            看数据、写因子、跑检测、做策略，再把有效想法沉淀到社区。
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map((item) => (
              <Link
                key={item.title}
                to={gate(item.to, item.needAuth)}
                className="landing-card-hover group rounded-2xl border border-slate-200/90 bg-[#f5f8fc] p-6 transition"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-slate-800 to-slate-600 text-white transition duration-300 group-hover:from-red-600 group-hover:to-rose-500">
                  <item.icon className="h-5 w-5 transition group-hover:scale-110" />
                </div>
                <h3 className="font-display mt-4 text-lg font-semibold text-slate-900">
                  {item.title}
                </h3>
                <p className="mt-1 text-sm font-medium text-red-600">{item.line}</p>
                <p className="mt-3 text-[15px] leading-relaxed text-slate-600">{item.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="relative border-t border-slate-200/50">
        <div className="relative mx-auto max-w-[1160px] px-6 py-14 lg:py-16">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div className="max-w-2xl">
              <h2 className="font-display text-2xl font-semibold text-slate-900 sm:text-3xl">
                <span className="text-red-600">SVQuant</span> 研究社区
              </h2>
              <p className="mt-2 text-[15px] leading-relaxed text-slate-600">
                分享因子笔记与策略思路，浏览优质回测结果，和同路人一起打磨研究。
              </p>
            </div>
            <Link
              to="/community"
              className="inline-flex items-center gap-1 text-sm font-semibold text-red-600 hover:text-red-700"
            >
              进入社区
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          <div className="grid items-stretch gap-6 lg:grid-cols-2">
            <div className="flex min-h-[360px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_12px_36px_-28px_rgba(15,23,42,0.28)] lg:min-h-[420px]">
              <div className="shrink-0 border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-700">
                最新帖子
              </div>
              <ul className="flex min-h-0 flex-1 flex-col divide-y divide-slate-100">
                {posts.length > 0
                  ? posts.map((p) => {
                      const name =
                        p.author?.display_name || p.author?.username || "用户";
                      return (
                        <li key={p.id} className="flex min-h-0 flex-1">
                          <Link
                            to={`/community/post/${p.id}`}
                            className="flex w-full items-center gap-3 px-4 py-3.5 transition hover:bg-slate-50"
                          >
                            <AvatarBubble name={name} url={p.author?.avatar_url} />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-[15px] font-medium text-slate-900">
                                {p.title}
                              </p>
                              <p className="mt-0.5 text-xs text-slate-500">{name}</p>
                            </div>
                            <span className="shrink-0 font-mono text-xs text-slate-400">
                              {formatPostTime(p.created_at)}
                            </span>
                          </Link>
                        </li>
                      );
                    })
                  : DEMO_POSTS.map((p) => (
                      <li key={p.id} className="flex min-h-0 flex-1">
                        <Link
                          to="/community"
                          className="flex w-full items-center gap-3 px-4 py-3.5 transition hover:bg-slate-50"
                        >
                          <AvatarBubble name={p.author} initial={p.initial} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-[15px] font-medium text-slate-900">
                              {p.title}
                            </p>
                            <p className="mt-0.5 text-xs text-slate-500">{p.author}</p>
                          </div>
                        </Link>
                      </li>
                    ))}
              </ul>
            </div>

            <div className="flex min-h-[360px] flex-col lg:min-h-[420px]">
              <p className="mb-3 shrink-0 text-sm font-medium text-slate-500">优质回测</p>
              <div className="flex min-h-0 flex-1 flex-col gap-3">
                {SAMPLE_BACKTESTS.map((s) =>
                  s.kind === "area" ? (
                    <CommunityAreaSpark
                      key={s.name}
                      title={s.name}
                      ret={s.ret}
                      ctaTo={s.to}
                      onGate={(path) => gate(path, false)}
                    />
                  ) : (
                    <CommunityHBarSpark
                      key={s.name}
                      title={s.name}
                      ret={s.ret}
                      ctaTo={s.to}
                      onGate={(path) => gate(path, false)}
                    />
                  ),
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden border-t border-slate-200/50">
        <SoftMeshBackground tone="mist" />
        <div className="relative mx-auto flex max-w-[1160px] flex-col items-start justify-between gap-8 px-6 py-16 lg:flex-row lg:items-center">
          <div className="max-w-xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700">
              <ShieldCheck className="h-4 w-4" />
              可验证
            </div>
            <h2 className="font-display mt-4 text-3xl font-semibold text-slate-900">
              把研究做成可复现
            </h2>
            <p className="mt-3 text-base leading-relaxed text-slate-600">
              从因子库开始，或先看文档了解数据与接口口径。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to={primaryTo}
              className="landing-wiggle-hover inline-flex items-center gap-2 rounded-xl bg-red-600 px-6 py-3 text-sm font-semibold text-white hover:bg-red-700"
            >
              <Sparkles className="h-4 w-4" />
              开始研究
            </Link>
            <Link
              to={gate("/help", true)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 hover:border-slate-300"
            >
              <BookOpen className="h-4 w-4" />
              查看文档
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
