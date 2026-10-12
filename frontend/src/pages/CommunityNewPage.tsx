import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  SECTION_META,
  createCommunityPost,
  getCommunityPost,
  updateCommunityPost,
  type CommunitySection,
} from "@/lib/communityApi";
import type { CommunityShareDraft } from "@/lib/communityShare";
import { sanitizeFactorShareCode } from "@/lib/communityClone";
import {
  stashAiAssistInbound,
  takeAiAssistOutbound,
} from "@/lib/communityAiAssist";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  PrimaryButton,
  fieldClassName,
} from "@/components/community/communityUi";
import { MarkdownEditor } from "@/components/community/MarkdownEditor";
import { ContentLengthHint } from "@/components/community/ContentLengthHint";
import { POST_BODY_LIMIT, lengthError } from "@/lib/communityLimits";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";

function initialSection(
  raw: string | null,
  isAdmin: boolean,
  draftSection?: CommunitySection,
): CommunitySection {
  const ids = SECTION_META.map((s) => s.id).filter((id) => id !== "all");
  const prefer = draftSection || raw;
  if (prefer && ids.includes(prefer as CommunitySection)) {
    if (prefer === "official" && !isAdmin) return "strategy";
    return prefer as CommunitySection;
  }
  return "strategy";
}

export function CommunityNewPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const askConfirm = useConfirm();
  const { id: editIdRaw } = useParams();
  const editId = Number(editIdRaw || 0);
  const isEdit = Number.isFinite(editId) && editId > 0;
  const [searchParams] = useSearchParams();
  const draft = (location.state || {}) as CommunityShareDraft;
  const [user] = useState(() => getStoredUser());
  const isAdmin = user?.role === "admin";
  const sections = useMemo(
    () =>
      (SECTION_META.filter((s) => s.id !== "all") as {
        id: CommunitySection;
        label: string;
        bar: string;
      }[]).filter((s) => isAdmin || s.id !== "official"),
    [isAdmin],
  );
  const [title, setTitle] = useState(() => (draft.title || "").slice(0, 120));
  const [section, setSection] = useState<CommunitySection>(() =>
    initialSection(searchParams.get("section"), !!isAdmin, draft.section),
  );
  const [body, setBody] = useState(() => draft.body || "");
  const [code, setCode] = useState(() => draft.code_snippet || "");
  const [platformRef] = useState(() => draft.platform_ref);
  const [postStatus, setPostStatus] = useState<"draft" | "published">("published");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const [bootLoading, setBootLoading] = useState(isEdit);
  const [savedEditId, setSavedEditId] = useState(isEdit ? editId : 0);
  const [aiAssisted, setAiAssisted] = useState(false);
  const [savedHint, setSavedHint] = useState("");
  const restoreFromAiRef = useRef(false);
  const fromShare = !!draft.shareDraft && !isEdit;
  const isDraftDoc = postStatus === "draft";
  const workingId = savedEditId > 0 ? savedEditId : isEdit ? editId : 0;
  const busy = loading || draftSaving;

  useEffect(() => {
    const back = takeAiAssistOutbound();
    if (!back) return;
    restoreFromAiRef.current = true;
    setTitle((back.title || "").slice(0, 120));
    setBody(back.body || "");
    if (back.section) setSection(back.section);
    if (back.code_snippet != null) setCode(back.code_snippet);
    if (back.aiAssisted) setAiAssisted(true);
  }, []);

  useEffect(() => {
    if (!user) {
      const next = isEdit
        ? `/community/post/${editId}/edit`
        : "/community/new";
      navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true });
    }
  }, [user, navigate, isEdit, editId]);

  useEffect(() => {
    if (!isEdit || !user) return;
    let cancelled = false;
    setBootLoading(true);
    setErr(null);
    void getCommunityPost(editId, { bump: false })
      .then((data) => {
        if (cancelled) return;
        const p = data.post;
        if (p.author?.id != null && user.id !== p.author.id && user.role !== "admin") {
          throw new Error("只能编辑自己的帖子");
        }
        setPostStatus(p.status === "draft" ? "draft" : "published");
        setSavedEditId(p.id);
        // 从 AI 助手带回时不要用服务端旧稿覆盖
        if (restoreFromAiRef.current) {
          restoreFromAiRef.current = false;
        } else {
          setTitle(p.title || "");
          setSection(p.section);
          setBody(p.body || "");
          setCode(p.code_snippet || "");
        }
      })
      .catch((ex) => {
        if (!cancelled) {
          setErr(ex instanceof Error ? ex.message : String(ex));
        }
      })
      .finally(() => {
        if (!cancelled) setBootLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isEdit, editId, user]);

  useEffect(() => {
    if (!isAdmin && section === "official") {
      setSection("strategy");
    }
  }, [isAdmin, section]);

  if (!user) {
    return (
      <CommunityPageShell>
        <div className="px-4 py-16 text-center text-sm text-slate-500">正在跳转登录…</div>
      </CommunityPageShell>
    );
  }

  const buildPayload = async (status: "draft" | "published") => {
    const raw = code.trim();
    let code_snippet: string | undefined;
    if (raw) {
      // 仅因子帖脱敏；策略帖暂按原文分享
      code_snippet =
        section === "strategy"
          ? raw
          : (await sanitizeFactorShareCode(raw)) || undefined;
    }
    return {
      title: title.trim(),
      body: body.trim(),
      section,
      code_snippet,
      status,
      ...(platformRef ? { platform_ref: platformRef } : {}),
    };
  };

  const save = async (status: "draft" | "published") => {
    setErr(null);
    const bodyError = lengthError(body, POST_BODY_LIMIT, "正文");
    if (bodyError) {
      setErr(bodyError);
      return;
    }
    if (status === "draft") {
      const ok = await askConfirm({
        title: "保存草稿",
        message:
          workingId > 0
            ? "确定将当前内容保存为草稿吗？"
            : "确定保存为草稿吗？保存后将进入该草稿的编辑页。",
        confirmLabel: "保存",
        cancelLabel: "再想想",
      });
      if (!ok) return;
    }
    if (status === "draft") setDraftSaving(true);
    else setLoading(true);
    try {
      const payload = await buildPayload(status);
      // 脱敏后写回编辑器，避免界面仍显示内置实现
      if (payload.code_snippet != null && payload.code_snippet !== code) {
        setCode(payload.code_snippet);
      }
      let data;
      if (workingId > 0) {
        data = await updateCommunityPost(workingId, payload);
      } else {
        data = await createCommunityPost(payload);
        setSavedEditId(data.post.id);
      }
      setPostStatus(data.post.status === "draft" ? "draft" : "published");
      if (status === "draft") {
        const editPath = `/community/post/${data.post.id}/edit`;
        // 已在该草稿编辑页：不跳转，避免整页重载冲掉体验
        if (location.pathname === editPath) {
          setSavedHint("草稿已保存");
          window.setTimeout(() => setSavedHint(""), 2000);
        } else {
          navigate(editPath, { replace: true });
        }
      } else {
        navigate(`/community/post/${data.post.id}`, { replace: true });
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
      setDraftSaving(false);
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await save("published");
  };

  const cancelTo = isDraftDoc
    ? "/community/me?tab=drafts"
    : workingId > 0 && !isDraftDoc
      ? `/community/post/${workingId}`
      : draft.returnTo || "/community";
  const backLabel = isDraftDoc
    ? "返回草稿箱"
    : workingId > 0 && !isDraftDoc
      ? "返回帖子"
      : draft.returnLabel || (fromShare ? "返回报告" : "返回社区");
  const onCancel = () => {
    navigate(cancelTo);
  };

  const openAiAssist = () => {
    const returnTo = workingId
      ? `/community/post/${workingId}/edit`
      : "/community/new";
    stashAiAssistInbound({
      title,
      body,
      section,
      code_snippet: code,
      returnTo,
      platform_ref: platformRef,
    });
    navigate("/community/ai-assist");
  };

  return (
    <CommunityPageShell>
      <div className="mx-auto min-w-0 max-w-[1440px] px-3 py-4 animate-fade-up sm:px-6 lg:px-8 lg:py-5">
        <CommunityBackLink to={cancelTo} label={backLabel} />

        {bootLoading ? (
          <p className="mt-8 text-center text-sm text-slate-500">加载帖子…</p>
        ) : (
          <form onSubmit={onSubmit} className="mt-3 lg:mt-4">
            <CommunityPanel className="min-w-0 overflow-hidden">
              <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-red-50/50 to-transparent px-3 py-3.5 sm:px-6 sm:py-4 lg:gap-4">
                <div className="min-w-0">
                  <p className="text-xs font-medium tracking-wide text-red-500/90">
                    {isDraftDoc
                      ? "DRAFT"
                      : isEdit
                        ? "EDIT POST"
                        : fromShare
                          ? "SHARE TO COMMUNITY"
                          : "NEW POST"}
                  </p>
                  <h1 className="mt-0.5 text-xl font-bold tracking-tight text-slate-900 lg:mt-1 lg:text-2xl">
                    {isDraftDoc
                      ? "编辑草稿"
                      : isEdit
                        ? "编辑帖子"
                        : fromShare
                          ? "分享到社区"
                          : "发布帖子"}
                  </h1>
                  {isDraftDoc ? (
                    <p className="mt-1 hidden text-xs text-slate-500 lg:block">
                      草稿仅自己可见；发布后进入社区 Feed
                    </p>
                  ) : isEdit ? (
                    <p className="mt-1 hidden text-xs text-slate-500 lg:block">
                      保存后仍是同一帖；评论、收藏、浏览数不会清零
                    </p>
                  ) : fromShare ? (
                    <p className="mt-1 hidden text-xs text-slate-500 lg:block">
                      已从报告预填标题、摘要与代码，可再编辑后发布
                    </p>
                  ) : null}
                </div>
                {/* PC：顶栏操作；手机用底部固定栏 */}
                <div className="hidden flex-wrap items-center gap-2 sm:gap-3 lg:flex">
                  <button
                    type="button"
                    onClick={onCancel}
                    className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                  >
                    取消
                  </button>
                  {(isDraftDoc || !isEdit) && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void save("draft")}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                    >
                      {draftSaving
                        ? "保存中…"
                        : savedHint
                          ? savedHint
                          : "存草稿"}
                    </button>
                  )}
                  <PrimaryButton type="submit" disabled={busy || (!!err && isEdit && !title && !isDraftDoc)}>
                    {loading
                      ? "发布中…"
                      : isDraftDoc
                        ? "发布"
                        : isEdit
                          ? "保存修改"
                          : "发布"}
                  </PrimaryButton>
                </div>
              </div>

              {/* 手机：侧栏元数据 → 正文 → 代码；PC：左栏(元数据+代码) | 右栏正文 */}
              <div className="grid min-w-0 gap-0 lg:grid-cols-[360px_minmax(0,1fr)] lg:grid-rows-[auto_minmax(0,1fr)] xl:grid-cols-[400px_minmax(0,1fr)]">
                <aside className="min-w-0 space-y-4 border-b border-slate-100 bg-slate-50/40 p-3 sm:space-y-5 sm:p-6 lg:col-start-1 lg:row-start-1 lg:border-b-0 lg:border-r lg:p-6">
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-slate-700">
                      标题
                    </span>
                    <input
                      className={fieldClassName("bg-white text-base")}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      maxLength={120}
                      placeholder="一句话说清你的分享"
                      required={!isDraftDoc}
                    />
                  </label>

                  <fieldset>
                    <legend className="mb-1.5 text-sm font-medium text-slate-700">
                      分区
                    </legend>
                    <div className="flex flex-wrap gap-1.5 lg:gap-2">
                      {sections.map((s) => {
                        const active = section === s.id;
                        return (
                          <button
                            key={s.id}
                            type="button"
                            onClick={() => setSection(s.id)}
                            className={`rounded-lg border px-2.5 py-1.5 text-xs transition lg:px-3 lg:py-2 lg:text-sm ${
                              active
                                ? "border-red-200 bg-red-50 font-medium text-red-600 shadow-sm shadow-red-100"
                                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                            }`}
                          >
                            {s.label}
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>

                  <div className="rounded-xl border border-red-100 bg-gradient-to-br from-red-50/80 to-white p-3.5 shadow-sm sm:p-4">
                    <p className="text-[11px] font-medium tracking-wide text-red-500/90">
                      AI 辅助
                    </p>
                    <h3 className="mt-0.5 text-sm font-semibold text-slate-900">
                      发帖助手
                    </h3>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={openAiAssist}
                      className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-red-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      <Sparkles className="h-4 w-4" />
                      打开 AI 发帖助手
                    </button>
                    {aiAssisted && (
                      <p className="mt-2 text-xs text-amber-700">
                        已使用过 AI 辅助，仍可继续手工修改
                      </p>
                    )}
                  </div>

                  {err && (
                    <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
                      {err}
                    </p>
                  )}
                </aside>

                <section className="flex min-h-0 min-w-0 flex-col border-b border-slate-100 p-3 sm:p-6 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:min-h-[min(720px,78vh)] lg:border-b-0 lg:p-6">
                  <h2 className="mb-2.5 text-sm font-semibold text-slate-800 lg:mb-3">
                    正文
                  </h2>
                  <MarkdownEditor
                    value={body}
                    onChange={setBody}
                    className="min-h-0 flex-1"
                    minHeightClass="min-h-[220px] lg:min-h-[min(620px,68vh)]"
                    placeholder="直接写正文；可粘贴图片，选中文字后点链接可加网址"
                  />
                  <ContentLengthHint value={body} limit={POST_BODY_LIMIT} label="正文（Markdown 源文）" />
                </section>

                <div className="min-w-0 bg-slate-50/40 p-3 sm:p-6 lg:col-start-1 lg:row-start-2 lg:border-r lg:border-slate-100 lg:p-6">
                  <div className="mb-1.5 flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium text-slate-700">
                      代码片段
                    </span>
                    <span className="hidden text-[11px] text-slate-400 sm:inline">
                      可选 · 按发帖分区克隆（因子区→因子检测 / 策略区→策略研究）
                    </span>
                    <span className="text-[11px] text-slate-400 sm:hidden">可选</span>
                  </div>
                  <div className="h-[200px] min-w-0 w-full max-w-full lg:h-[360px]">
                    <FactorCodeEditor
                      value={code}
                      onChange={setCode}
                      variant="dark"
                      height="100%"
                      className="h-full max-w-full rounded-xl"
                    />
                  </div>
                </div>
              </div>
            </CommunityPanel>

            {/* 手机：底部固定操作栏 */}
            <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur-sm lg:hidden">
              <div className="mx-auto flex max-w-[1440px] items-center gap-2">
                <button
                  type="button"
                  onClick={onCancel}
                  className="shrink-0 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600"
                >
                  取消
                </button>
                {(isDraftDoc || !isEdit) && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void save("draft")}
                    className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-60"
                  >
                    {draftSaving ? "保存中…" : savedHint || "存草稿"}
                  </button>
                )}
                <PrimaryButton
                  type="submit"
                  disabled={busy || (!!err && isEdit && !title && !isDraftDoc)}
                  className="min-w-0 flex-1"
                >
                  {loading
                    ? "发布中…"
                    : isDraftDoc
                      ? "发布"
                      : isEdit
                        ? "保存"
                        : "发布"}
                </PrimaryButton>
              </div>
            </div>
            <div className="h-[4.5rem] lg:hidden" aria-hidden />
          </form>
        )}
      </div>
    </CommunityPageShell>
  );
}
