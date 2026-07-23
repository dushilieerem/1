import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, FlaskConical, Play, Sparkles } from "lucide-react";
import {
  clearFactorCache,
  extractDefName,
  extractMethod,
  loadFactors,
  loadLibrarySource,
  toLogicalMethodBody,
} from "@/lib/factorCatalog";
import { authHeaders, getStoredUser } from "@/lib/auth";
import { openOrCreateForFactor, createDetectProjectForClone, openDetectInNewTab, periodToStartEnd } from "@/lib/detectStore";
import { ygBacktestFactor } from "@/lib/ygApi";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";

export type CommunityCloneState = {
  communityClone?: boolean;
  postId?: number;
  title?: string;
  body?: string;
  name?: string;
  description?: string;
};

function wrapFullDef(name: string, desc: string, bodyLines: string): string {
  const indented = bodyLines
    .split("\n")
    .map((ln) => (ln.trim() ? `    ${ln}` : ln))
    .join("\n");
  return `def ${name}(self):\n    """${desc}"""\n${indented}`;
}

const TEMPLATES = [
  {
    id: "ret5",
    label: "5日收益",
    name: "RET_5D",
    desc: "近5日涨跌幅",
    code: wrapFullDef("RET_5D", "近5日涨跌幅", "return self.close.pct_change(5)"),
  },
  {
    id: "ma20",
    label: "20日均线偏离",
    name: "MA_DEV_20",
    desc: "收盘相对20日均线偏离",
    code: wrapFullDef(
      "MA_DEV_20",
      "收盘相对20日均线偏离",
      "ma = self.close.rolling(20).mean()\nreturn self.close / ma - 1",
    ),
  },
  {
    id: "vol20",
    label: "20日波动",
    name: "VOL_20",
    desc: "20日收益波动率",
    code: wrapFullDef(
      "VOL_20",
      "20日收益波动率",
      "return self.close.pct_change().rolling(20).std()",
    ),
  },
] as const;

const DEFAULT_CODE = wrapFullDef("RET_5D_DEMO", "5日收益示意", "return self.close.pct_change(5)");

const MODE_TABS = [
  { id: "template" as const, label: "多日收益" },
  { id: "ma" as const, label: "均线偏离" },
  { id: "vol" as const, label: "波动率" },
  { id: "free" as const, label: "自由表达式" },
];

const FIELD_GROUPS: { title: string; tone: string; items: string[] }[] = [
  { title: "价格", tone: "bg-rose-50 text-rose-700 ring-rose-200", items: ["self.close", "self.open", "self.high", "self.low"] },
  { title: "量额", tone: "bg-amber-50 text-amber-700 ring-amber-200", items: ["self.volume", "self.amount"] },
  {
    title: "方法",
    tone: "bg-violet-50 text-violet-700 ring-violet-200",
    items: [".pct_change(5)", ".rolling(20).mean()", ".rolling(20).std()", ".shift(1)"],
  },
];

type TrialStats = {
  ic?: number | null;
  rank_ic?: number | null;
  sharpe?: number | null;
  annual_return?: number | null;
  max_drawdown?: number | null;
  turnover?: number | null;
};

function numOrNull(x: unknown): number | null {
  if (x == null) return null;
  const v = Number(x);
  return Number.isFinite(v) ? v : null;
}

export function FactorCustomPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const communityState = (location.state || {}) as CommunityCloneState;
  const fromCommunity = Boolean(communityState.communityClone);
  const { name: routeName } = useParams<{ name?: string }>();
  const isEdit = Boolean(routeName && routeName !== "new");
  const editName = isEdit ? decodeURIComponent(routeName!) : "";

  const [name, setName] = useState(
    fromCommunity && communityState.name ? communityState.name : "RET_5D_DEMO",
  );
  const [description, setDescription] = useState(
    fromCommunity && communityState.description
      ? communityState.description
      : "5日收益示意",
  );
  const [body, setBody] = useState(
    fromCommunity && communityState.body ? communityState.body : DEFAULT_CODE,
  );
  const [tab, setTab] = useState<(typeof MODE_TABS)[number]["id"]>("free");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [savedName, setSavedName] = useState<string | null>(null);
  const [detectBusy, setDetectBusy] = useState(false);

  const [trialUniverse, setTrialUniverse] = useState("CSI300");
  const [trialPeriod, setTrialPeriod] = useState("3m");
  const [trialBusy, setTrialBusy] = useState(false);
  const [trialErr, setTrialErr] = useState<string | null>(null);
  const [trialStats, setTrialStats] = useState<TrialStats | null>(null);
  const [testedBody, setTestedBody] = useState<string | null>(null);
  const [testedDesc, setTestedDesc] = useState<string | null>(null);

  useEffect(() => {
    if (!getStoredUser()) {
      navigate(
        `/login?next=${encodeURIComponent(
          isEdit
            ? `/factor/library/custom/${encodeURIComponent(editName)}`
            : "/factor/library/custom/new",
        )}`,
        { replace: true },
      );
    }
  }, [navigate, isEdit, editName]);

  useEffect(() => {
    if (!isEdit) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void (async () => {
      try {
        const factors = await loadFactors(true);
        const meta = factors.find((f) => f.library === "custom_lib" && f.name === editName);
        if (!meta) throw new Error(`未找到自定义因子：${editName}`);
        const src = await loadLibrarySource(meta.libraryFile);
        const method = extractMethod(src, meta.methodName || editName);
        const logical = toLogicalMethodBody(method.trim() || DEFAULT_CODE, editName);
        if (cancelled) return;
        setName(editName);
        setDescription(meta.description || meta.explain || editName);
        setBody(logical);
        setTab("free");
        setTestedBody(null);
        setTestedDesc(null);
        setTrialStats(null);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isEdit, editName]);

  const defName = useMemo(() => extractDefName(body), [body]);
  const nameMatch = Boolean(name.trim() && defName && defName === name.trim());
  const nameMismatchHint = useMemo(() => {
    const code = name.trim();
    if (!body.trim()) return null;
    if (!defName) return "请写完整函数：以 def 函数名(self): 开头";
    if (!code) return "请填写因子代码";
    if (defName !== code) return `因子代码「${code}」与 def 函数名「${defName}」不一致`;
    return null;
  }, [body, name, defName]);

  const preview = useMemo(() => body.trim(), [body]);

  const trialPassed = Boolean(
    testedBody &&
      testedBody === body.trim() &&
      testedDesc != null &&
      testedDesc === description.trim() &&
      nameMatch,
  );

  const canTrial = Boolean(body.trim() && name.trim() && nameMatch && !trialBusy);

  const applyTemplate = (t: (typeof TEMPLATES)[number]) => {
    if (!isEdit) setName(t.name);
    setDescription(t.desc);
    setBody(t.code);
    setTab(t.id === "ret5" ? "template" : t.id === "ma20" ? "ma" : "vol");
    setTestedBody(null);
    setTestedDesc(null);
    setTrialStats(null);
    setTrialErr(null);
  };

  const onModeTab = (id: (typeof MODE_TABS)[number]["id"]) => {
    setTab(id);
    if (id === "template") applyTemplate(TEMPLATES[0]);
    else if (id === "ma") applyTemplate(TEMPLATES[1]);
    else if (id === "vol") applyTemplate(TEMPLATES[2]);
  };

  const insertSnippet = (s: string) => {
    setBody((prev) => {
      const snippet = s.startsWith(".") ? (prev.includes("self.close") ? s : `self.close${s}`) : s;
      if (!prev.trim()) return snippet;
      return `${prev.replace(/\s*$/, "")}\n    ${snippet}`;
    });
    setTestedBody(null);
    setTestedDesc(null);
  };

  const onTrial = async () => {
    if (nameMismatchHint) {
      setTrialErr(nameMismatchHint);
      return;
    }
    setTrialBusy(true);
    setTrialErr(null);
    setErr(null);
    try {
      const code = body.trim();
      const factorName = name.trim();
      const { start, end } = periodToStartEnd(trialPeriod);
      // 与因子检测「进行检测」同一条 RE 接口；默认 core 更快
      const res = await ygBacktestFactor({
        factor_code: code,
        factor_name: factorName,
        portfolio_type: "long_short",
        universe: trialUniverse,
        start,
        end,
        filter_limit_up: true,
        filter_suspended: true,
        benchmark: trialUniverse,
        groups: 5,
        rebalance_days: 20,
        commission_rate: 0.0003,
        stamp_tax: 0.001,
        slippage_rate: 0.001,
        analysis_level: "core",
      });
      if (res.error != null && String(res.error).trim() !== "") {
        throw new Error(String(res.error));
      }
      // 仅以 RE 返回 error===null 为通过（见 06-research-api.md）；不再加额外指标判断
      const metrics = res.metrics || {};
      const fa = res.factor_analysis || {};
      setTrialStats({
        ic: numOrNull(metrics.ic) ?? numOrNull(fa.ic_mean),
        rank_ic: numOrNull(metrics.rank_ic) ?? numOrNull(fa.rank_ic_mean),
        sharpe: numOrNull(metrics.sharpe),
        annual_return: numOrNull(metrics.annual_return),
        max_drawdown: numOrNull(metrics.max_drawdown),
        turnover: numOrNull(metrics.turnover),
      });
      setTestedBody(code);
      setTestedDesc(description.trim());
    } catch (e) {
      setTrialErr(e instanceof Error ? e.message : String(e));
      setTestedBody(null);
      setTestedDesc(null);
      setTrialStats(null);
    } finally {
      setTrialBusy(false);
    }
  };

  const onSubmit = async () => {
    if (!trialPassed) {
      setErr(isEdit ? "请先点「测试」重新试算通过后再保存" : "请先点「测试」试算通过后再提交");
      return;
    }
    if (nameMismatchHint) {
      setErr(nameMismatchHint);
      return;
    }
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await fetch(
        isEdit ? `/api/factor/custom/${encodeURIComponent(editName)}` : "/api/factor/custom",
        {
          method: isEdit ? "PUT" : "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            name,
            body: testedBody || body,
            description,
          }),
        },
      );
      const j = (await res.json()) as { ok?: boolean; error?: string; name?: string };
      if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
      clearFactorCache();
      const saved = j.name || name.trim();
      setMsg(isEdit ? `已更新：${saved}` : `已写入自定义因子库：${saved}`);
      if (fromCommunity && !isEdit) {
        setSavedName(saved);
      } else {
        setTimeout(() => navigate("/factor/library"), 600);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const goDetect = async () => {
    const factorName = savedName || name.trim();
    if (!factorName) return;
    setDetectBusy(true);
    setErr(null);
    try {
      const title = description.trim() || factorName;
      const p = fromCommunity
        ? await createDetectProjectForClone(factorName, title)
        : await openOrCreateForFactor(factorName, title);
      openDetectInNewTab(p.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDetectBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-violet-50/80 via-white to-rose-50/40">
      <div className="mx-auto max-w-[1280px] px-6 py-8">
        <Link
          to={fromCommunity && communityState.postId
            ? `/community/post/${communityState.postId}`
            : "/factor/library"}
          className="mb-4 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" />{" "}
          {fromCommunity
            ? "社区 / 社区自定义因子"
            : `因子库 / ${isEdit ? "编辑自定义因子" : "新增自定义因子"}`}
        </Link>

        {loading ? (
          <p className="text-sm text-slate-500">加载中…</p>
        ) : (
          <div className="grid min-w-0 gap-5 lg:grid-cols-[1.2fr_0.8fr]">
            <section className="min-w-0 rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-sm backdrop-blur">
              <div className="mb-5 flex flex-wrap gap-2">
                {MODE_TABS.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => onModeTab(m.id)}
                    className={`rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                      tab === m.id
                        ? "bg-slate-900 text-white shadow"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              <div className="mb-4 grid gap-3 sm:grid-cols-2">
                <label className="block text-xs font-medium text-slate-500">
                  因子代码
                  {isEdit && (
                    <span className="ml-1 font-normal text-slate-400">（入库后不可改）</span>
                  )}
                  <input
                    value={name}
                    disabled={isEdit}
                    onChange={(e) => {
                      setName(e.target.value);
                      setTestedBody(null);
                      setTestedDesc(null);
                    }}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 font-mono text-sm outline-none ring-violet-200 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-70"
                  />
                </label>
                <label className="block text-xs font-medium text-slate-500">
                  简介
                  <input
                    value={description}
                    onChange={(e) => {
                      setDescription(e.target.value);
                      setTestedDesc(null);
                    }}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none ring-violet-200 focus:ring-2"
                  />
                </label>
              </div>

              <p className="mb-2 text-xs font-semibold text-slate-500">可用字段（点击插入）</p>
              <div className="mb-4 space-y-2.5">
                {FIELD_GROUPS.map((g) => (
                  <div key={g.title}>
                    <p className="mb-1 text-[11px] font-medium text-slate-400">{g.title}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {g.items.map((it) => (
                        <button
                          key={it}
                          type="button"
                          onClick={() => insertSnippet(it)}
                          className={`rounded-lg px-2 py-1 font-mono text-[11px] ring-1 ring-inset ${g.tone}`}
                        >
                          {it}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <label className="block text-xs font-medium text-slate-500">
                完整函数（须含 def，函数名与因子代码一致）
                <FactorCodeEditor
                  value={body}
                  onChange={(v) => {
                    setBody(v);
                    setTestedBody(null);
                    setTestedDesc(null);
                    setTrialErr(null);
                  }}
                />
              </label>
              {nameMismatchHint && <p className="mt-2 text-xs text-amber-700">{nameMismatchHint}</p>}
              {nameMatch && (
                <p className="mt-2 text-xs text-emerald-600">函数名与因子代码一致：{defName}</p>
              )}
            </section>

            <section className="flex min-w-0 flex-col gap-4">
              <div className="rounded-3xl border border-violet-100 bg-gradient-to-br from-violet-50 to-white p-5 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <FlaskConical className="h-4 w-4 text-violet-600" />
                    <h2 className="text-sm font-bold text-slate-900">{isEdit ? "重新检测" : "试算"}</h2>
                  </div>
                  <button
                    type="button"
                    disabled={!canTrial}
                    onClick={() => void onTrial()}
                    title={nameMismatchHint || undefined}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    <Play className="h-3.5 w-3.5" />
                    {trialBusy ? "测试中…" : isEdit ? "重新检测" : "测试"}
                  </button>
                </div>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <select
                    value={trialUniverse}
                    onChange={(e) => {
                      setTrialUniverse(e.target.value);
                      setTestedBody(null);
                      setTestedDesc(null);
                    }}
                    className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs"
                  >
                    <option value="CSI300">沪深300</option>
                    <option value="CSI500">中证500</option>
                    <option value="CSI1000">中证1000</option>
                    <option value="SSE50">上证50</option>
                  </select>
                  {[
                    { v: "3m", label: "近3月" },
                    { v: "1y", label: "近1年" },
                    { v: "3y", label: "近3年" },
                  ].map((d) => (
                    <button
                      key={d.v}
                      type="button"
                      onClick={() => {
                        setTrialPeriod(d.v);
                        setTestedBody(null);
                        setTestedDesc(null);
                      }}
                      className={`h-8 rounded-lg px-2.5 text-xs font-semibold ${
                        trialPeriod === d.v
                          ? "bg-slate-900 text-white"
                          : "bg-white text-slate-600 ring-1 ring-slate-200"
                      }`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
                {trialErr && <p className="mb-2 text-xs text-red-600">{trialErr}</p>}
                {trialPassed && (
                  <p className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-600">
                    <CheckCircle2 className="h-3.5 w-3.5" /> 试算通过
                  </p>
                )}
                {trialStats && (
                  <div className="mb-3 grid grid-cols-3 gap-2 text-[11px]">
                    {[
                      ["IC", trialStats.ic],
                      ["Sharpe", trialStats.sharpe],
                      ["年化", trialStats.annual_return],
                    ].map(([k, v]) => (
                      <div key={String(k)} className="rounded-lg bg-white/80 px-2 py-1.5 ring-1 ring-violet-100">
                        <p className="text-slate-400">{k}</p>
                        <p className="font-mono font-semibold text-slate-800">
                          {v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(4)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="min-w-0 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-rose-500" />
                  <h2 className="text-sm font-bold text-slate-900">公式预览</h2>
                </div>
                <pre className="max-h-72 max-w-full overflow-auto rounded-2xl bg-slate-900 p-4 font-mono text-[12px] leading-relaxed whitespace-pre text-rose-100">
                  {preview || "# …"}
                </pre>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs text-slate-500">
                  {fromCommunity
                    ? "社区克隆：试算通过后写入你的自定义因子库，再可跳转因子检测（点检测后才保存检测记录）。"
                    : isEdit
                      ? "须重新检测通过后再保存到因子库。"
                      : "须试算通过后再提交到因子库。"}
                </p>
                {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
                {msg && <p className="mt-2 text-sm text-emerald-600">{msg}</p>}
                {!savedName && (
                  <button
                    type="button"
                    disabled={busy || !name.trim() || !body.trim() || !trialPassed}
                    onClick={() => void onSubmit()}
                    className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                  >
                    <Play className="h-4 w-4" />
                    {busy
                      ? isEdit
                        ? "保存中…"
                        : "提交中…"
                      : trialPassed
                        ? isEdit
                          ? "保存到因子库"
                          : "提交到自定义因子库"
                        : isEdit
                          ? "请先重新检测通过"
                          : "请先试算通过"}
                  </button>
                )}
                {savedName && fromCommunity && (
                  <button
                    type="button"
                    disabled={detectBusy}
                    onClick={() => void goDetect()}
                    className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-red-500 py-3 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-50"
                  >
                    <FlaskConical className="h-4 w-4" />
                    {detectBusy ? "打开检测…" : `去因子检测（已选 ${savedName}）`}
                  </button>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
