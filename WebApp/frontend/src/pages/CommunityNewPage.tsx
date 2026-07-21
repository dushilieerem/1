import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getStoredUser } from "@/lib/auth";
import {
  SECTION_META,
  createCommunityPost,
  type CommunitySection,
} from "@/lib/communityApi";

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
      <div className="bg-[#f3f5f8] px-4 py-16 text-center text-sm text-slate-500">
        正在跳转登录…
      </div>
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
    <div className="min-h-[calc(100vh-4rem)] bg-[#f3f5f8]">
      <div className="mx-auto max-w-[880px] px-5 py-6">
        <Link to="/community" className="text-sm text-slate-500 hover:text-red-600">
          ← 返回社区
        </Link>

        <form
          onSubmit={onSubmit}
          className="mt-4 overflow-hidden rounded border border-slate-200 bg-white shadow-sm shadow-slate-200/40"
        >
          <div className="border-b border-slate-100 px-5 py-4">
            <h1 className="text-xl font-bold tracking-tight text-slate-900">发布帖子</h1>
          </div>

          <div className="space-y-5 px-5 py-5">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">标题</span>
              <input
                className="w-full rounded border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-red-300 focus:ring-1 focus:ring-red-200"
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
                      className={`rounded border px-3 py-1.5 text-sm transition ${
                        active
                          ? "border-red-200 bg-red-50 font-medium text-red-600"
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

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">正文</span>
              <textarea
                className="min-h-[220px] w-full resize-y rounded border border-slate-200 px-3 py-2.5 text-sm leading-relaxed outline-none focus:border-red-300 focus:ring-1 focus:ring-red-200"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="写下思路、参数与观察结论…"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">
                代码片段
                <span className="ml-1 font-normal text-slate-400">可选</span>
              </span>
              <textarea
                className="min-h-[140px] w-full resize-y rounded border border-slate-200 bg-slate-50 px-3 py-2.5 font-mono text-xs leading-relaxed text-slate-800 outline-none focus:border-red-300 focus:ring-1 focus:ring-red-200"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder={"def my_factor(self):\n    return self.close.pct_change(20)"}
                spellCheck={false}
              />
            </label>

            {err && (
              <p className="rounded border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
                {err}
              </p>
            )}
          </div>

          <div className="flex items-center justify-end gap-3 bg-slate-50 px-5 py-3">
            <Link
              to="/community"
              className="rounded px-4 py-2 text-sm font-medium text-slate-600 hover:bg-white hover:text-slate-900"
            >
              取消
            </Link>
            <button
              type="submit"
              disabled={loading}
              className="rounded bg-red-500 px-5 py-2 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-60"
            >
              {loading ? "发布中…" : "发布"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
