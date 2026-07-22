import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getStoredUser } from "@/lib/auth";
import {
  SECTION_META,
  createCommunityPost,
  type CommunitySection,
} from "@/lib/communityApi";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  PrimaryButton,
  fieldClassName,
} from "@/components/community/communityUi";

export function CommunityNewPage() {
  const navigate = useNavigate();
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
  const [title, setTitle] = useState("");
  const [section, setSection] = useState<CommunitySection>("strategy");
  const [body, setBody] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent("/community/new")}`, { replace: true });
    }
  }, [user, navigate]);

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
      const data = await createCommunityPost({
        title: title.trim(),
        body: body.trim(),
        section,
        code_snippet: code.trim() || undefined,
      });
      navigate(`/community/post/${data.post.id}`, { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  };

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[880px] px-5 py-6 animate-fade-up">
        <CommunityBackLink />

        <form onSubmit={onSubmit} className="mt-5">
          <CommunityPanel>
            <div className="border-b border-slate-100 bg-gradient-to-r from-red-50/50 to-transparent px-6 py-5">
              <p className="text-xs font-medium tracking-wide text-red-500/90">NEW POST</p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                发布帖子
              </h1>
              <p className="mt-1.5 text-sm text-slate-500">
                写清思路与观察；代码片段可选，方便同事复现。
              </p>
            </div>

            <div className="space-y-8 px-6 py-6">
              <section>
                <h2 className="text-sm font-semibold text-slate-800">基本信息</h2>
                <div className="mt-4 space-y-5">
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-slate-700">
                      标题
                    </span>
                    <input
                      className={fieldClassName()}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      maxLength={120}
                      placeholder="一句话说清你的分享"
                      required
                    />
                  </label>

                  <fieldset>
                    <legend className="mb-2 text-sm font-medium text-slate-700">分区</legend>
                    <div className="flex flex-wrap gap-2">
                      {sections.map((s) => {
                        const active = section === s.id;
                        return (
                          <button
                            key={s.id}
                            type="button"
                            onClick={() => setSection(s.id)}
                            className={`rounded-lg border px-3 py-1.5 text-sm transition ${
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
                    {!isAdmin && (
                      <p className="mt-2 text-xs text-slate-400">官方内容由平台发布。</p>
                    )}
                  </fieldset>
                </div>
              </section>

              <section className="border-t border-slate-100 pt-8">
                <h2 className="text-sm font-semibold text-slate-800">正文</h2>
                <label className="mt-4 block">
                  <textarea
                    className={fieldClassName("min-h-[240px] resize-y leading-relaxed")}
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="写下思路、参数与观察结论…"
                  />
                </label>
              </section>

              <section className="border-t border-slate-100 pt-8">
                <h2 className="text-sm font-semibold text-slate-800">
                  代码片段
                  <span className="ml-1.5 font-normal text-slate-400">可选</span>
                </h2>
                <label className="mt-4 block">
                  <textarea
                    className={fieldClassName(
                      "min-h-[160px] resize-y bg-slate-900/95 font-mono text-xs leading-relaxed text-slate-100 placeholder:text-slate-500 focus:border-red-400 focus:ring-red-200/40",
                    )}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder={"def my_factor(self):\n    return self.close.pct_change(20)"}
                    spellCheck={false}
                  />
                </label>
              </section>

              {err && (
                <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
                  {err}
                </p>
              )}
            </div>

            <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t border-slate-100 bg-white/95 px-6 py-3.5 backdrop-blur-sm">
              <Link
                to="/community"
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
              >
                取消
              </Link>
              <PrimaryButton type="submit" disabled={loading}>
                {loading ? "发布中…" : "发布"}
              </PrimaryButton>
            </div>
          </CommunityPanel>
        </form>
      </div>
    </CommunityPageShell>
  );
}
