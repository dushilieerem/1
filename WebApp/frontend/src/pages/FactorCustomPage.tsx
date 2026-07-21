import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, FlaskConical, Play, Sparkles } from "lucide-react";
import {
  clearFactorCache,
  extractEditableBody,
  extractMethod,
  loadFactors,
  loadLibrarySource,
} from "@/lib/factorCatalog";
import { authHeaders, getStoredUser } from "@/lib/auth";

const TEMPLATES = [
  {
    id: "ret5",
    label: "5日收益",
    name: "RET_5D",
    body: "return self.close.pct_change(5)",
    desc: "近5日涨跌幅",
  },
  {
    id: "ma20",
    label: "20日均线偏离",
    name: "MA_DEV_20",
    body: "ma = self.close.rolling(20).mean()\nreturn self.close / ma - 1",
    desc: "收盘相对20日均线偏离",
  },
  {
    id: "vol20",
    label: "20日波动",
    name: "VOL_20",
    body: "return self.close.pct_change().rolling(20).std()",
    desc: "20日收益波动率",
  },
] as const;

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

export function FactorCustomPage() {
  const navigate = useNavigate();
  const { name: routeName } = useParams<{ name?: string }>();
  const isEdit = Boolean(routeName && routeName !== "new");
  const editName = isEdit ? decodeURIComponent(routeName!) : "";

  const [name, setName] = useState("RET_5D_DEMO");
  const [description, setDescription] = useState("5日收益示意");
  const [body, setBody] = useState("return self.close.pct_change(5)");
  const [tab, setTab] = useState<(typeof MODE_TABS)[number]["id"]>("free");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [trialUniverse, setTrialUniverse] = useState("CSI300");
  const [trialPeriod, setTrialPeriod] = useState("3m");
  const [trialBusy, setTrialBusy] = useState(false);
  const [trialErr, setTrialErr] = useState<string | null>(null);
  const [trialStats, setTrialStats] = useState<TrialStats | null>(null);
  const [testedBody, setTestedBody] = useState<string | null>(null);
  const [testedDesc, setTestedDesc] = useState<string | null>(null);

  useEffect(() => {
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent(isEdit ? `/factor/library/custom/${encodeURIComponent(editName)}` : "/factor/library/custom/new")}`, {
        replace: true,
      });
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
        const editable = extractEditableBody(method);
        if (cancelled) return;
        setName(editName);
        setDescription(meta.description || meta.explain || editName);
        setBody(editable || "return self.close.pct_change(5)");
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

  const preview = useMemo(() => {
    const b = body.trim();
    if (!b) return "";
    if (b.includes("def ")) return b;
    const lines = b
      .split("\n")
      .map((ln) => (ln.trim() ? `    ${ln}` : ln))
      .join("\n");
    return `def ${name || "my_factor"}(self):\n    """${description || name}"""\n${lines}`;
  }, [body, name, description]);

  const trialPassed = Boolean(
    testedBody &&
      testedBody === body.trim() &&
      testedDesc != null &&
      testedDesc === description.trim(),
  );

  const applyTemplate = (t: (typeof TEMPLATES)[number]) => {
    if (!isEdit) setName(t.name);
    setDescription(t.desc);
    setBody(t.body);
    setTab(t.id === "ret5" ? "template" : t.id === "ma20" ? "ma" : "vol");
    setTestedBody(null);
    setTestedDesc(null);
    setTrialStats(null);
  };

  const onModeTab = (id: (typeof MODE_TABS)[number]["id"]) => {
    setTab(id);
    if (id === "template") applyTemplate(TEMPLATES[0]);
    else if (id === "ma") applyTemplate(TEMPLATES[1]);
    else if (id === "vol") applyTemplate(TEMPLATES[2]);
  };

  const insertSnippet = (s: string) => {
    setBody((prev) =>
      prev.trim() ? `${prev}${s.startsWith(".") ? s : `\n${s}`}` : s.startsWith(".") ? `self.close${s}` : s,
    );
    setTestedBody(null);
    setTestedDesc(null);
  };

  const onTrial = async () => {
    setTrialBusy(true);
    setTrialErr(null);
    setErr(null);
    try {
      const res = await fetch("/api/factor/custom/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          body,
          name: name.trim() || "trial_factor",
          universe: trialUniverse,
          period: trialPeriod,
        }),
      });
      const j = await res.json();
      if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
      setTrialStats(j.stats || null);
      setTestedBody(String(j.body || body).trim());
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
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await fetch(isEdit ? `/api/factor/custom/${encodeURIComponent(editName)}` : "/api/factor/custom", {
        method: isEdit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          name,
          body: testedBody || body,
          description,
        }),
      });
      const j = (await res.json()) as { ok?: boolean; error?: string; name?: string };
      if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
      clearFactorCache();
      setMsg(isEdit ? `已更新：${j.name}` : `已写入因子库：${j.name}`);
      setTimeout(() => navigate("/factor/library"), 600);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-violet-50/80 via-white to-rose-50/40">
      <div className="mx-auto max-w-[1280px] px-6 py-8">
        <Link
          to="/factor/library"
          className="mb-4 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 因子库 / {isEdit ? "编辑自定义因子" : "新增自定义因子"}
        </Link>

        {loading ? (
          <p className="text-sm text-slate-500">加载中…</p>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
            <section className="rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-sm backdrop-blur">
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
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-sm outline-none ring-violet-200 focus:ring-2"
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
                计算表达式
                <textarea
                  value={body}
                  onChange={(e) => {
                    setBody(e.target.value);
                    setTestedBody(null);
                    setTestedDesc(null);
                  }}
                  rows={9}
                  className="mt-1 w-full rounded-2xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white px-3 py-3 font-mono text-sm outline-none ring-violet-200 focus:ring-2"
                />
              </label>
            </section>

            <section className="flex flex-col gap-4">
              <div className="rounded-3xl border border-violet-100 bg-gradient-to-br from-violet-50 to-white p-5 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <FlaskConical className="h-4 w-4 text-violet-600" />
                    <h2 className="text-sm font-bold text-slate-900">{isEdit ? "重新检测" : "试算"}</h2>
                  </div>
                  <button
                    type="button"
                    disabled={trialBusy || !body.trim()}
                    onClick={() => void onTrial()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    <Play className="h-3.5 w-3.5" />
                    {trialBusy ? "测试中…" : isEdit ? "重新检测" : "测试"}
                  </button>
                </div>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <select
                    value={trialUniverse}
                    onChange={(e) => setTrialUniverse(e.target.value)}
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
                      onClick={() => setTrialPeriod(d.v)}
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
                {isEdit && (
                  <p className="mb-2 text-[11px] text-slate-500">
                    修改后须重新检测通过再保存；直接返回不会改动库里的原公式。
                  </p>
                )}
                {trialErr && <p className="mb-2 text-xs text-red-600">{trialErr}</p>}
                {trialPassed && (
                  <p className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-600">
                    <CheckCircle2 className="h-3.5 w-3.5" /> 试算通过（RE）
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

              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-rose-500" />
                  <h2 className="text-sm font-bold text-slate-900">公式预览</h2>
                </div>
                <pre className="overflow-x-auto rounded-2xl bg-slate-900 p-4 font-mono text-[12px] leading-relaxed text-rose-100">
                  {preview || "# …"}
                </pre>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs text-slate-500">
                  {isEdit ? "须重新检测通过后再保存到因子库。" : "须试算通过后再提交到因子库。"}
                </p>
                {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
                {msg && <p className="mt-2 text-sm text-emerald-600">{msg}</p>}
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
                        : "提交到因子库"
                      : isEdit
                        ? "请先重新检测通过"
                        : "请先试算通过"}
                </button>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
