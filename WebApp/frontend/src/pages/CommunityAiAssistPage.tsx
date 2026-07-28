import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Copy, Loader2, Sparkles, Wand2 } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  getMyAgentUsage,
  runAgent,
  type AgentFlag,
} from "@/lib/agentApi";
import {
  SECTION_META,
  type CommunitySection,
} from "@/lib/communityApi";
import {
  clearAiAssistInbound,
  peekAiAssistInbound,
  stashAiAssistOutbound,
} from "@/lib/communityAiAssist";
import {
  CommunityPageShell,
  fieldClassName,
} from "@/components/community/communityUi";
import { MarkdownEditor } from "@/components/community/MarkdownEditor";

function sectionLabel(id: CommunitySection) {
  return SECTION_META.find((s) => s.id === id)?.label || id;
}

function htmlToPlain(raw: string): string {
  const s = (raw || "").trim();
  if (!s) return "";
  // 先把块级标签变成换行，再剥标签，避免整段糊成一行
  const withBreaks = s
    .replace(/<\s*br\s*\/?\s*>/gi, "\n")
    .replace(/<\s*\/\s*p\s*>/gi, "\n\n")
    .replace(/<\s*\/\s*div\s*>/gi, "\n")
    .replace(/<\s*\/\s*li\s*>/gi, "\n")
    .replace(/<\s*\/\s*h[1-6]\s*>/gi, "\n\n")
    .replace(/<\s*li[^>]*>/gi, "· ")
    .replace(/<[^>]+>/g, "");
  const decoded = withBreaks
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"');
  return decoded
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

type AiDraft = {
  title: string;
  body: string;
  section: CommunitySection;
};

export function CommunityAiAssistPage() {
  const navigate = useNavigate();
  const [user] = useState(() => getStoredUser());
  const isAdmin = user?.role === "admin";

  const inbound = useMemo(() => peekAiAssistInbound(), []);
  const returnTo = inbound?.returnTo || "/community/new";

  const sections = useMemo(
    () =>
      (SECTION_META.filter((s) => s.id !== "all") as {
        id: CommunitySection;
        label: string;
      }[]).filter((s) => isAdmin || s.id !== "official"),
    [isAdmin],
  );

  const [draftTitle, setDraftTitle] = useState(() => inbound?.title || "");
  const [draftBody, setDraftBody] = useState(() => inbound?.body || "");
  const [draftSection, setDraftSection] = useState<CommunitySection>(
    () => inbound?.section || "strategy",
  );

  const [aiDraft, setAiDraft] = useState<AiDraft | null>(null);
  const [aiFlags, setAiFlags] = useState<AgentFlag[]>([]);
  const [aiHint, setAiHint] = useState<string | null>(null);
  // 仅在未验证 / 冲突时提示用户；已挂平台引用（verified）不刷绿条
  const [dataTrust, setDataTrust] = useState<{
    status?: string;
    summary?: string;
    label?: string;
  } | null>(null);

  const [workTitle, setWorkTitle] = useState("");
  const [workBody, setWorkBody] = useState("");
  const [workSection, setWorkSection] = useState<CommunitySection>(
    () => inbound?.section || "strategy",
  );
  const [applyAiSection, setApplyAiSection] = useState(false);

  const [busy, setBusy] = useState<"quick" | "deep" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<"title" | "body" | null>(null);
  const [quota, setQuota] = useState<{
    remaining: number;
    used_today: number;
    quota_daily: number;
  } | null>(null);

  useEffect(() => {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent("/community/ai-assist")}`, {
        replace: true,
      });
    }
  }, [user, navigate]);

  useEffect(() => {
    if (!user) return;
    void getMyAgentUsage()
      .then((u) =>
        setQuota({
          remaining: u.remaining,
          used_today: u.used_today,
          quota_daily: u.quota_daily,
        }),
      )
      .catch(() => undefined);
  }, [user]);

  const goBack = () => {
    // 未点确认：把左侧初稿写回发帖页，避免内容丢失
    stashAiAssistOutbound({
      title: draftTitle.slice(0, 120),
      body: draftBody,
      section: draftSection,
      code_snippet: inbound?.code_snippet,
      aiAssisted: false,
    });
    clearAiAssistInbound();
    navigate(returnTo);
  };

  const copyText = async (kind: "title" | "body", text: string) => {
    try {
      await navigator.clipboard.writeText(text || "");
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      /* ignore */
    }
  };

  const fillWorkFromDraft = () => {
    setWorkTitle(draftTitle);
    setWorkBody(draftBody);
    setWorkSection(draftSection);
    setApplyAiSection(false);
  };

  const fillWorkFromAi = () => {
    if (!aiDraft) return;
    setWorkTitle(aiDraft.title);
    setWorkBody(aiDraft.body);
    if (applyAiSection) setWorkSection(aiDraft.section);
    else setWorkSection(draftSection);
  };

  const runAssist = async (mode: "quick" | "deep") => {
    setErr(null);
    setAiHint(null);
    setAiFlags([]);
    setBusy(mode);
    try {
      const ctx = {
        title: draftTitle,
        body: draftBody,
        section: draftSection,
        code_snippet: inbound?.code_snippet || "",
        platform_ref: inbound?.platform_ref,
      };
      const data =
        mode === "quick"
          ? await runAgent({
              mode: "single",
              goal: "润色标题与正文",
              skills: ["polish_title", "polish_body"],
              context: ctx,
            })
          : await runAgent({
              mode: "multi",
              crew: "community_post",
              goal: "把草稿整理成可发社区帖",
              context: ctx,
            });

      if (data.usage) {
        setQuota({
          remaining: data.usage.remaining,
          used_today: data.usage.used_today,
          quota_daily: data.usage.quota_daily,
        });
      }
      setAiFlags(data.board?.flags || []);
      const arts = data.board?.artifacts as
        | {
            data_trust?: { status?: string; summary?: string };
            platform_ref?: { label?: string };
          }
        | undefined;
      const st = arts?.data_trust?.status;
      if (st === "unverified" || st === "conflict") {
        setDataTrust({
          status: st,
          summary: arts?.data_trust?.summary,
          label: arts?.platform_ref?.label || inbound?.platform_ref?.label,
        });
      } else {
        setDataTrust(null);
      }

      if (data.status === "blocked" || data.error) {
        setErr(
          data.error ||
            "内容未通过审校，请修改初稿后再试，或先用快速润色。",
        );
        setAiHint(null);
        return;
      }

      const nextSection =
        data.outputs?.section &&
        sections.some((s) => s.id === data.outputs!.section)
          ? (data.outputs.section as CommunitySection)
          : draftSection;

      const next: AiDraft = {
        title:
          data.outputs?.title != null
            ? String(data.outputs.title).slice(0, 120)
            : draftTitle,
        body:
          data.outputs?.body != null ? String(data.outputs.body) : draftBody,
        section: nextSection,
      };
      setAiDraft(next);
      setApplyAiSection(false);

      if (data.status === "needs_review") {
        setAiHint("审校仍有异议，已给出建议稿；请到下方整合区自行调整后再带回。");
      } else {
        setAiHint(mode === "quick" ? "快速润色完成" : "深度审校完成");
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(null);
    }
  };

  const confirmBack = () => {
    stashAiAssistOutbound({
      title: workTitle.slice(0, 120),
      body: workBody,
      section: workSection,
      code_snippet: inbound?.code_snippet,
      aiAssisted: !!aiDraft,
    });
    clearAiAssistInbound();
    navigate(returnTo);
  };

  if (!user) {
    return (
      <CommunityPageShell>
        <p className="py-20 text-center text-sm text-slate-400">跳转登录…</p>
      </CommunityPageShell>
    );
  }

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[1280px] px-4 py-5 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={goBack}
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
          >
            <ArrowLeft className="h-4 w-4" />
            返回发帖页
          </button>
          {quota && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">
              今日已用 {quota.used_today}/{quota.quota_daily}
            </span>
          )}
        </div>

        <header className="mt-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium tracking-wide text-red-500/90">
              SVQUANT AGENT
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
              AI 发帖助手
            </h1>
            <p className="mt-1.5 max-w-xl text-sm text-slate-500">
              左侧写或改初稿，点下方按钮生成 AI 建议；右侧只读可复制。把满意的内容填入底部整合区，确认后带回发帖页。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!!busy || (quota != null && quota.remaining < 2)}
              onClick={() => void runAssist("quick")}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
            >
              {busy === "quick" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4 text-slate-500" />
              )}
              {busy === "quick" ? "润色中…" : "快速润色"}
            </button>
            <button
              type="button"
              disabled={!!busy || (quota != null && quota.remaining < 4)}
              title={
                quota != null && quota.remaining < 4
                  ? `深度审校约需 4 次额度，今日剩余 ${quota.remaining}`
                  : undefined
              }
              onClick={() => void runAssist("deep")}
              className="inline-flex items-center gap-1.5 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
            >
              {busy === "deep" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {busy === "deep" ? "审校中…" : "深度审校"}
            </button>
          </div>
        </header>

        <p className="mt-2 text-xs text-slate-400">
          快速润色：改写标题和正文。深度审校：改写并检查夸大表述，必要时建议分区。
        </p>

        {dataTrust &&
          (dataTrust.status === "unverified" ||
            dataTrust.status === "conflict") && (
          <div
            className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
              dataTrust.status === "conflict"
                ? "border-amber-200 bg-amber-50 text-amber-950"
                : "border-slate-200 bg-slate-50 text-slate-700"
            }`}
          >
            <span className="font-semibold">
              {dataTrust.status === "conflict"
                ? "引用冲突"
                : "指标未经验证"}
            </span>
            {dataTrust.summary ? (
              <span className="mt-0.5 block opacity-90">{dataTrust.summary}</span>
            ) : null}
          </div>
        )}

        {err && (
          <p className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
            {err}
          </p>
        )}
        {aiHint && !err && (
          <p className="mt-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {aiHint}
          </p>
        )}
        {aiFlags.length > 0 && (
          <ul className="mt-2 space-y-1 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
            {aiFlags.map((f, i) => (
              <li key={`${f.code}-${i}`} className="text-xs text-amber-900">
                {f.message || f.code}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {/* 初稿 */}
          <section className="flex max-h-[560px] min-h-[420px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">我的初稿</h2>
                <p className="text-[11px] text-slate-400">可直接在此撰写或修改</p>
              </div>
              <button
                type="button"
                onClick={fillWorkFromDraft}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                用初稿填入下方
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
              <input
                className={fieldClassName("bg-slate-50")}
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                maxLength={120}
                placeholder="标题（可空，让 AI 帮你起）"
              />
              <div className="flex flex-wrap gap-1.5">
                {sections.map((s) => {
                  const active = draftSection === s.id;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setDraftSection(s.id)}
                      className={`rounded-lg border px-2.5 py-1 text-xs ${
                        active
                          ? "border-red-200 bg-red-50 font-medium text-red-600"
                          : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
              <MarkdownEditor
                value={draftBody}
                onChange={setDraftBody}
                className="min-h-0 flex-1"
                minHeightClass="min-h-[260px]"
                placeholder="写下你的初稿…"
              />
            </div>
          </section>

          {/* AI */}
          <section className="flex max-h-[560px] min-h-[420px] flex-col overflow-hidden rounded-2xl border border-red-100 bg-gradient-to-b from-red-50/40 to-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-red-100/80 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-red-700">AI 建议</h2>
                <p className="text-[11px] text-slate-400">只读 · 可复制，不可直接改</p>
                {aiDraft ? (
                  <p className="mt-1 text-xs font-medium text-teal-600">
                    建议分区：{sectionLabel(aiDraft.section)}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  disabled={!aiDraft}
                  onClick={() =>
                    void copyText("title", aiDraft?.title || "")
                  }
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                >
                  <Copy className="h-3 w-3" />
                  {copied === "title" ? "已复制" : "复制标题"}
                </button>
                <button
                  type="button"
                  disabled={!aiDraft}
                  onClick={() =>
                    void copyText(
                      "body",
                      htmlToPlain(aiDraft?.body || "") || aiDraft?.body || "",
                    )
                  }
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                >
                  <Copy className="h-3 w-3" />
                  {copied === "body" ? "已复制" : "复制正文"}
                </button>
                <button
                  type="button"
                  disabled={!aiDraft}
                  onClick={fillWorkFromAi}
                  className="rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-40"
                >
                  用 AI 稿填入下方
                </button>
              </div>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
              {!aiDraft ? (
                <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white/60 px-6 text-center text-sm text-slate-400">
                  点右上角「快速润色」或「深度审校」后，建议会出现在这里
                </div>
              ) : (
                <>
                  <div>
                    <p className="mt-0 text-base font-semibold text-slate-900">
                      {aiDraft.title.trim() || "（无标题）"}
                    </p>
                  </div>
                  {aiDraft.section !== draftSection && (
                    <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-amber-100 bg-amber-50/80 px-3 py-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={applyAiSection}
                        onChange={(e) => setApplyAiSection(e.target.checked)}
                      />
                      <span>
                        填入下方时，一并改用建议分区「
                        {sectionLabel(aiDraft.section)}」
                      </span>
                    </label>
                  )}
                  <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-slate-100 bg-white px-3 py-3 text-sm leading-relaxed whitespace-pre-wrap text-slate-700">
                    {htmlToPlain(aiDraft.body) || "（无正文）"}
                  </div>
                </>
              )}
            </div>
          </section>
        </div>

        {/* 整合区 */}
        <section className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">整合编辑</h2>
              <p className="text-[11px] text-slate-400">
                在此拼成最终稿（默认为空）。可用上方按钮填入初稿或 AI 稿，也可复制后粘贴再改。
              </p>
            </div>
            <button
              type="button"
              onClick={confirmBack}
              className="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
            >
              确认，带回发帖页
            </button>
          </div>
          <div className="space-y-3 p-4">
            <input
              className={fieldClassName()}
              value={workTitle}
              onChange={(e) => setWorkTitle(e.target.value)}
              maxLength={120}
              placeholder="整合后的标题"
            />
            <div className="flex flex-wrap gap-1.5">
              {sections.map((s) => {
                const active = workSection === s.id;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setWorkSection(s.id)}
                    className={`rounded-lg border px-2.5 py-1 text-xs ${
                      active
                        ? "border-red-200 bg-red-50 font-medium text-red-600"
                        : "border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
            <MarkdownEditor
              value={workBody}
              onChange={setWorkBody}
              minHeightClass="min-h-[280px]"
              placeholder="在这里整合初稿与 AI 建议…"
            />
          </div>
        </section>
      </div>
    </CommunityPageShell>
  );
}
