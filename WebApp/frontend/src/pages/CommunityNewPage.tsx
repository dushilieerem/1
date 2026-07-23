import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { getStoredUser } from "@/lib/auth";
import {
  SECTION_META,
  createCommunityPost,
  getCommunityPost,
  updateCommunityPost,
  type CommunitySection,
} from "@/lib/communityApi";
import type { CommunityShareDraft } from "@/lib/communityShare";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  PrimaryButton,
  fieldClassName,
} from "@/components/community/communityUi";
import { MarkdownEditor } from "@/components/community/MarkdownEditor";
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
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootLoading, setBootLoading] = useState(isEdit);
  const fromShare = !!draft.shareDraft && !isEdit;

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
        setTitle(p.title || "");
        setSection(p.section);
        setBody(p.body || "");
        setCode(p.code_snippet || "");
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

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const payload = {
        title: title.trim(),
        body: body.trim(),
        section,
        code_snippet: code.trim() || undefined,
      };
      const data = isEdit
        ? await updateCommunityPost(editId, payload)
        : await createCommunityPost(payload);
      navigate(`/community/post/${data.post.id}`, { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  };

  const cancelTo = isEdit ? `/community/post/${editId}` : "/community";

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[1440px] px-4 py-5 animate-fade-up sm:px-6 lg:px-8">
        <CommunityBackLink to={cancelTo} />

        {bootLoading ? (
          <p className="mt-8 text-center text-sm text-slate-500">加载帖子…</p>
        ) : (
          <form onSubmit={onSubmit} className="mt-4">
            <CommunityPanel className="overflow-hidden">
              <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-100 bg-gradient-to-r from-red-50/50 to-transparent px-5 py-4 sm:px-6">
                <div>
                  <p className="text-xs font-medium tracking-wide text-red-500/90">
                    {isEdit
                      ? "EDIT POST"
                      : fromShare
                        ? "SHARE TO COMMUNITY"
                        : "NEW POST"}
                  </p>
                  <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                    {isEdit ? "编辑帖子" : fromShare ? "分享到社区" : "发布帖子"}
                  </h1>
                  {isEdit ? (
                    <p className="mt-1 text-xs text-slate-500">
                      保存后仍是同一帖；评论、收藏、浏览数不会清零
                    </p>
                  ) : fromShare ? (
                    <p className="mt-1 text-xs text-slate-500">
                      已从报告预填标题、摘要与代码，可再编辑后发布
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-3">
                  <Link
                    to={cancelTo}
                    className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                  >
                    取消
                  </Link>
                  <PrimaryButton type="submit" disabled={loading || !!err && isEdit && !title}>
                    {loading ? "保存中…" : isEdit ? "保存修改" : "发布"}
                  </PrimaryButton>
                </div>
              </div>

              <div className="grid gap-0 lg:grid-cols-[360px_minmax(0,1fr)] xl:grid-cols-[400px_minmax(0,1fr)]">
                <aside className="space-y-5 border-b border-slate-100 bg-slate-50/40 p-5 sm:p-6 lg:border-b-0 lg:border-r">
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
                      required
                    />
                  </label>

                  <fieldset>
                    <legend className="mb-1.5 text-sm font-medium text-slate-700">
                      分区
                    </legend>
                    <div className="flex flex-wrap gap-2">
                      {sections.map((s) => {
                        const active = section === s.id;
                        return (
                          <button
                            key={s.id}
                            type="button"
                            onClick={() => setSection(s.id)}
                            className={`rounded-lg border px-3 py-2 text-sm transition ${
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

                  <div>
                    <div className="mb-1.5 flex items-baseline justify-between gap-2">
                      <span className="text-sm font-medium text-slate-700">
                        代码片段
                      </span>
                      <span className="text-[11px] text-slate-400">
                        可选 · 克隆到因子检测 / 策略研究
                      </span>
                    </div>
                    <FactorCodeEditor
                      value={code}
                      onChange={setCode}
                      variant="dark"
                      height="360px"
                      className="rounded-xl"
                    />
                  </div>

                  {err && (
                    <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
                      {err}
                    </p>
                  )}
                </aside>

                <section className="flex min-h-[min(720px,78vh)] flex-col p-5 sm:p-6">
                  <h2 className="mb-3 text-sm font-semibold text-slate-800">正文</h2>
                  <MarkdownEditor
                    value={body}
                    onChange={setBody}
                    className="min-h-0 flex-1"
                    minHeightClass="min-h-[min(620px,68vh)]"
                    placeholder="直接写正文；可粘贴图片，选中文字后点链接可加网址"
                  />
                </section>
              </div>

              <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t border-slate-100 bg-white/95 px-5 py-3.5 backdrop-blur-sm sm:px-6">
                <Link
                  to={cancelTo}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                >
                  取消
                </Link>
                <PrimaryButton type="submit" disabled={loading}>
                  {loading ? "保存中…" : isEdit ? "保存修改" : "发布"}
                </PrimaryButton>
              </div>
            </CommunityPanel>
          </form>
        )}
      </div>
    </CommunityPageShell>
  );
}
