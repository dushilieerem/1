import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  FlaskConical,
  History,
  Lightbulb,
  Loader2,
  Newspaper,
  Sparkles,
} from "lucide-react";
import {
  loadGatherHistory,
  loadGatherPackById,
  loadLastGatherPack,
} from "@/lib/gatherHistory";
import type { EvidencePack } from "@/lib/gatherApi";
import {
  runIdea,
  type IdeaBundle,
  type IdeaPreference,
} from "@/lib/ideaApi";
import {
  loadIdeaBundleById,
  loadIdeaBundleByPackId,
  loadIdeaHistory,
  loadLastIdeaBundle,
  pushIdeaHistory,
} from "@/lib/ideaHistory";
import { saveChainIdea } from "@/lib/agentChain";

function resolvePack(packId: string | null): EvidencePack | null {
  if (packId) {
    const byId = loadGatherPackById(packId);
    if (byId) return byId;
  }
  return loadLastGatherPack();
}

function newsHrefFromCitation(
  cid: string,
  item: { url?: string | null; sv_news_id?: number | null } | undefined,
  opts?: { packId?: string; bundleId?: string },
): string | null {
  const m = /^sv_news:(\d+)$/i.exec(cid.trim());
  if (m) {
    const q = new URLSearchParams({ from: "idea" });
    if (opts?.packId) q.set("pack", opts.packId);
    if (opts?.bundleId) q.set("bundle", opts.bundleId);
    return `/news/${m[1]}?${q.toString()}`;
  }
  const u = item?.url;
  if (u && u.startsWith("http")) return u;
  return null;
}

export function AgentIdeaPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const packId = searchParams.get("pack");
  const bundleIdQ = searchParams.get("bundle");
  const pack = useMemo(() => resolvePack(packId), [packId]);
  const packHistory = useMemo(() => loadGatherHistory(), []);
  const [ideaHistTick, setIdeaHistTick] = useState(0);
  const ideaHistory = useMemo(
    () => loadIdeaHistory(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ideaHistTick],
  );

  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [bundle, setBundle] = useState<IdeaBundle | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);

  const topic = String(pack?.query?.topic || "").trim();
  const itemCount = pack?.items?.length ?? 0;
  const itemById = useMemo(() => {
    const m = new Map<string, NonNullable<EvidencePack["items"]>[number]>();
    for (const it of pack?.items || []) m.set(it.id, it);
    return m;
  }, [pack]);

  // 从资讯返回 / 刷新：恢复最近一次 IdeaBundle
  useEffect(() => {
    if (busy) return;
    let restored: IdeaBundle | null = null;
    if (bundleIdQ) restored = loadIdeaBundleById(bundleIdQ);
    if (!restored && pack?.pack_id) {
      restored = loadIdeaBundleByPackId(pack.pack_id);
    }
    if (!restored && !packId && !bundleIdQ) {
      restored = loadLastIdeaBundle();
    }
    if (restored) {
      setBundle(restored);
      restoredRef.current = true;
      // URL 补齐 pack，便于再点资讯
      if (restored.pack_id && packId !== restored.pack_id && !packId) {
        const next = new URLSearchParams(searchParams);
        next.set("pack", restored.pack_id);
        if (restored.bundle_id) next.set("bundle", restored.bundle_id);
        setSearchParams(next, { replace: true });
      }
    } else if (packId && restoredRef.current === false) {
      // 换了从未生成过的包：清空右侧
      setBundle(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pack?.pack_id, bundleIdQ, packId]);

  async function onGenerate() {
    if (!pack || itemCount === 0 || busy) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setErr(null);
    setBundle(null);
    try {
      const pref: IdeaPreference = {
        focus: "factor",
        note: note.trim().slice(0, 200) || undefined,
      };
      const out = await runIdea(
        {
          pack,
          preference: pref,
          max_ideas: 5,
        },
        ac.signal,
      );
      setBundle(out);
      pushIdeaHistory({
        bundle_id: out.bundle_id,
        pack_id: out.pack_id || pack.pack_id,
        topic: topic || pack.digest?.slice(0, 40) || out.pack_id,
        idea_count: out.ideas?.length ?? 0,
        idea_mode: out.stats?.idea_mode,
        finishedAt: new Date().toISOString(),
        preference: pref,
        bundle: out,
      });
      setIdeaHistTick((n) => n + 1);
      const next = new URLSearchParams();
      next.set("pack", out.pack_id || pack.pack_id);
      next.set("bundle", out.bundle_id);
      setSearchParams(next, { replace: true });
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const statusLabel = busy ? "Running" : bundle ? "Ready" : "Idle";
  const modeLabel = (() => {
    const m = bundle?.stats?.idea_mode;
    if (m === "llm") return "LLM";
    if (m === "rule_fallback") return "规则回退";
    if (m === "empty") return "空证据";
    return m || "—";
  })();

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f0f3f8] text-slate-800 lg:flex-row">
      <aside className="flex max-h-[42vh] w-full shrink-0 flex-col border-b border-slate-200/90 bg-white lg:max-h-none lg:h-full lg:w-[22rem] lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
            <Lightbulb className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-semibold text-slate-900">
              研究假设 Agent
            </div>
            <div className="text-sm text-slate-500">资料汇总 → 可转因子的研究假设</div>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
          {pack ? (
            <>
              <div>
                <div className="text-sm font-medium text-slate-700">来源证据包</div>
                <div className="mt-2 rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-700 ring-1 ring-slate-100">
                  <div className="font-mono text-xs text-slate-400">
                    {pack.pack_id}
                  </div>
                  <div className="mt-1 line-clamp-3">
                    {topic || pack.digest?.slice(0, 80) || "（无主题回显）"}
                  </div>
                  <div className="mt-2 text-xs text-slate-500">
                    {itemCount} 条证据 · {pack.stats?.digest_mode || "—"}
                    {pack.stats?.source_counts
                      ? ` · 资讯${pack.stats.source_counts.news ?? 0}/研报${pack.stats.source_counts.report ?? 0}/论文${pack.stats.source_counts.paper ?? 0}/帖子${pack.stats.source_counts.post ?? 0}`
                      : ""}
                  </div>
                </div>
              </div>
              {(pack.gaps || []).length > 0 && (
                <div className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-100">
                  <div className="font-medium">证据缺口</div>
                  <ul className="mt-1 list-disc pl-4">
                    {pack.gaps.slice(0, 6).map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <label className="text-sm font-medium text-slate-700">
                  补充约束（可选）
                </label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value.slice(0, 200))}
                  rows={2}
                  placeholder="例如：偏日频量价可检验方向"
                  className="mt-2 w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-amber-300 focus:ring-2 focus:ring-amber-100"
                />
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
              尚未载入证据包。请先在「信息搜集」生成结果，或从下方历史选择。
            </div>
          )}

          {ideaHistory.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-sm font-medium text-slate-700">
                <History className="h-3.5 w-3.5" />
                本机假设历史
              </div>
              <ul className="mt-2 space-y-2">
                {ideaHistory.slice(0, 6).map((h) => (
                  <li key={h.bundle_id}>
                    <button
                      type="button"
                      onClick={() => {
                        setErr(null);
                        setBundle(h.bundle);
                        navigate(
                          `/ai/idea?pack=${encodeURIComponent(h.pack_id)}&bundle=${encodeURIComponent(h.bundle_id)}`,
                        );
                      }}
                      className={`w-full rounded-xl border px-3 py-2 text-left text-sm hover:border-amber-200 hover:bg-amber-50/40 ${
                        bundle?.bundle_id === h.bundle_id
                          ? "border-amber-300 bg-amber-50/50"
                          : "border-slate-100 bg-slate-50"
                      }`}
                    >
                      <div className="line-clamp-2 font-medium text-slate-800">
                        {h.topic}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-400">
                        {h.idea_count} 条 · {h.idea_mode || "—"} ·{" "}
                        {h.bundle_id.slice(0, 16)}…
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {packHistory.length > 0 && (
            <div>
              <div className="text-sm font-medium text-slate-700">本机会话证据包</div>
              <ul className="mt-2 space-y-2">
                {packHistory.slice(0, 6).map((h) => (
                  <li key={h.pack_id}>
                    <button
                      type="button"
                      onClick={() => {
                        setErr(null);
                        const prev = loadIdeaBundleByPackId(h.pack_id);
                        setBundle(prev);
                        const q = new URLSearchParams({ pack: h.pack_id });
                        if (prev?.bundle_id) q.set("bundle", prev.bundle_id);
                        navigate(`/ai/idea?${q.toString()}`);
                      }}
                      className={`w-full rounded-xl border px-3 py-2 text-left text-sm hover:border-amber-200 hover:bg-amber-50/40 ${
                        pack?.pack_id === h.pack_id
                          ? "border-amber-300 bg-amber-50/50"
                          : "border-slate-100 bg-slate-50"
                      }`}
                    >
                      <div className="line-clamp-2 font-medium text-slate-800">
                        {h.topic}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-400">
                        {h.returned ?? "—"} 条 · {h.pack_id.slice(0, 18)}…
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="border-t border-slate-100 px-5 py-4">
          <button
            type="button"
            disabled={!pack || itemCount === 0 || busy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => void onGenerate()}
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {busy ? "生成中…" : "生成研究假设"}
          </button>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <Link to="/ai" className="text-slate-500 hover:text-slate-800">
              ← AI 主页
            </Link>
            <Link to="/ai/gather" className="text-slate-500 hover:text-slate-800">
              信息搜集
            </Link>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-slate-200/80 bg-white/80 px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => navigate("/ai")}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            返回 AI 主页
          </button>
          <span
            className={`rounded-full px-3 py-1 text-sm font-medium ${
              busy
                ? "bg-amber-50 text-amber-700"
                : bundle
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {statusLabel}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-8">
          {err && (
            <div className="mx-auto mb-4 max-w-5xl rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800 ring-1 ring-rose-100">
              {err}
            </div>
          )}

          {!pack && !busy && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white text-amber-600 shadow-sm ring-1 ring-slate-200/80">
                <Lightbulb className="h-8 w-8" />
              </div>
              <h2 className="mt-5 text-2xl font-semibold text-slate-900">
                先准备证据包
              </h2>
              <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-500">
                本页只消费搜集产出的资料包，输出给因子草稿的假设（含建议回测窗）。
              </p>
              <Link
                to="/ai/gather"
                className="mt-6 inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
              >
                <Newspaper className="h-4 w-4" />
                去信息搜集
              </Link>
            </div>
          )}

          {pack && !bundle && !busy && !err && (
            <div className="mx-auto flex max-w-lg flex-col items-center justify-center py-16 text-center">
              <Lightbulb className="h-10 w-10 text-amber-500" />
              <p className="mt-4 text-base text-slate-600">
                左侧确认证据包与偏好后，点击「生成研究假设」
              </p>
            </div>
          )}

          {busy && (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <Loader2 className="h-8 w-8 animate-spin text-amber-500" />
              <p className="mt-4 text-base">正在基于证据包生成研究假设…</p>
            </div>
          )}

          {bundle && !busy && (
            <div className="mx-auto w-full max-w-5xl space-y-6">
              <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                <span className="rounded-full bg-white px-3 py-1 font-mono text-xs ring-1 ring-slate-200">
                  {bundle.bundle_id}
                </span>
                <span>{modeLabel}</span>
                <span>{bundle.ideas?.length ?? 0} 条假设</span>
                <span>{bundle.stats?.elapsed_ms ?? "—"} ms</span>
              </div>

              {(bundle.gaps || []).length > 0 && (
                <section className="rounded-2xl bg-amber-50 px-5 py-4 text-sm text-amber-900 ring-1 ring-amber-100">
                  <div className="font-semibold">缺口</div>
                  <ul className="mt-2 list-disc pl-5">
                    {bundle.gaps.map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </section>
              )}

              <ul className="space-y-4">
                {(bundle.ideas || []).map((idea) => (
                  <li
                    key={idea.id}
                    className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200/80 sm:p-6"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <h3 className="text-base font-semibold text-slate-900 sm:text-lg">
                        {idea.title}
                      </h3>
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            idea.convertible
                              ? "bg-amber-50 text-amber-800"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {idea.convertible ? "可转因子草稿" : "暂不转因子"}
                        </span>
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            idea.confidence === "high"
                              ? "bg-emerald-50 text-emerald-700"
                              : idea.confidence === "mid"
                                ? "bg-sky-50 text-sky-700"
                                : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {idea.confidence}
                        </span>
                      </div>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed text-slate-700 sm:text-base">
                      {idea.thesis}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(idea.citation_ids || []).map((cid) => {
                        const it = itemById.get(cid);
                        const href = newsHrefFromCitation(cid, it, {
                          packId: bundle.pack_id || pack?.pack_id,
                          bundleId: bundle.bundle_id,
                        });
                        const title = it?.title;
                        const external = !!href && href.startsWith("http");
                        return href ? (
                          external ? (
                            <a
                              key={cid}
                              href={href}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-full bg-slate-50 px-2.5 py-1 font-mono text-xs text-amber-800 ring-1 ring-slate-200 hover:bg-amber-50"
                              title={title}
                            >
                              {cid}
                            </a>
                          ) : (
                            <Link
                              key={cid}
                              to={href}
                              className="rounded-full bg-slate-50 px-2.5 py-1 font-mono text-xs text-amber-800 ring-1 ring-slate-200 hover:bg-amber-50"
                              title={title}
                            >
                              {cid}
                            </Link>
                          )
                        ) : (
                          <span
                            key={cid}
                            className="rounded-full bg-slate-50 px-2.5 py-1 font-mono text-xs text-slate-500 ring-1 ring-slate-200"
                          >
                            {cid}
                          </span>
                        );
                      })}
                    </div>
                    {idea.validity && (
                      <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-100">
                        <div className="font-medium text-slate-700">
                          建议可能更好的时段
                          <span className="ml-1 font-normal text-slate-400">
                            （仅分析，下游回测可不采用）
                          </span>
                        </div>
                        {(idea.validity.suggested_start ||
                          idea.validity.suggested_end) && (
                          <div className="mt-1">
                            <span className="font-mono">
                              {idea.validity.suggested_start || "?"} ~{" "}
                              {idea.validity.suggested_end || "?"}
                            </span>
                            {idea.validity.oos_split
                              ? ` · 样本外参考 ${idea.validity.oos_split}`
                              : ""}
                            {idea.validity.regime
                              ? ` · ${idea.validity.regime}`
                              : ""}
                          </div>
                        )}
                        {idea.validity.why_window && (
                          <div className="mt-1">{idea.validity.why_window}</div>
                        )}
                        {idea.validity.decay_notes && (
                          <div className="mt-1 text-slate-500">
                            {idea.validity.decay_notes}
                          </div>
                        )}
                      </div>
                    )}
                    {idea.factor_prompt && (
                      <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-900 px-3 py-2 text-xs leading-relaxed text-slate-100">
                        {idea.factor_prompt}
                      </pre>
                    )}
                    <div className="mt-4 text-sm text-slate-600">
                      <span className="font-medium text-slate-800">下一步：</span>
                      {idea.suggested_next}
                    </div>
                    {(idea.risk_notes || []).length > 0 && (
                      <ul className="mt-2 list-disc pl-5 text-xs text-slate-500">
                        {idea.risk_notes.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    )}
                    <div className="mt-4">
                      <button
                        type="button"
                        disabled={idea.convertible === false}
                        title={
                          idea.convertible === false
                            ? "这条更偏事件或叙事，暂不适合写成日频量价因子"
                            : "交给因子草稿 Agent"
                        }
                        onClick={() => {
                          saveChainIdea(idea, {
                            pack_id: bundle.pack_id || pack?.pack_id,
                            bundle_id: bundle.bundle_id,
                          });
                          navigate("/ai/factor");
                        }}
                        className="inline-flex items-center gap-1.5 rounded-full bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <FlaskConical className="h-4 w-4" />
                        转成因子草稿 →
                      </button>
                    </div>
                  </li>
                ))}
              </ul>

              {(bundle.warnings || []).length > 0 && (
                <p className="text-xs text-slate-400">
                  {bundle.warnings.join(" · ")}
                </p>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
