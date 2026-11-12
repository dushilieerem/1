import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Camera, Loader2, Trash2 } from "lucide-react";
import { authHeaders, clearSession, getStoredUser } from "@/lib/auth";
import { compressImageFile } from "@/lib/imageCompress";
import {
  getUserProfile,
  updateMyProfile,
  type UserProfile,
} from "@/lib/profileApi";
import {
  AuthorAvatar,
  CommunityPageShell,
  PrimaryButton,
  fieldClassName,
} from "@/components/community/communityUi";

export function CommunityProfileEditPage() {
  const { username = "" } = useParams();
  const navigate = useNavigate();
  const me = getStoredUser();
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [headline, setHeadline] = useState("");
  const [bio, setBio] = useState("");
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);

  const onDeleteAccount = async () => {
    setDeleting(true);
    setErr(null);
    try {
      const res = await fetch("/api/auth/account/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ password: deletePassword, confirm: deleteConfirm }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) throw new Error(data.detail || `注销失败（${res.status}）`);
      clearSession();
      navigate("/login?deleted=1", { replace: true });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  };

  useEffect(() => {
    const uname = me?.username;
    if (!uname) {
      navigate(`/login?next=/u/${encodeURIComponent(username)}/edit`);
      return;
    }
    if (username && uname !== username) {
      navigate(`/u/${encodeURIComponent(uname)}/edit`, { replace: true });
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getUserProfile(uname)
      .then((data) => {
        if (cancelled) return;
        const p = data.profile;
        if (!p.is_self) {
          navigate(`/u/${encodeURIComponent(p.username)}`, { replace: true });
          return;
        }
        setProfile(p);
        setDisplayName(p.display_name || "");
        setHeadline(p.headline || "");
        setBio(p.bio || "");
        setAvatarUrl(p.avatar_url || null);
        setCoverUrl(p.cover_url || null);
      })
      .catch((ex) => {
        if (!cancelled) setErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [me?.username, username, navigate]);

  const pickImage = async (
    file: File | undefined,
    kind: "avatar" | "cover",
  ) => {
    if (!file) return;
    setErr(null);
    try {
      const src = await compressImageFile(file, {
        maxW: kind === "cover" ? 1280 : 320,
        maxH: kind === "cover" ? 480 : 320,
      });
      if (kind === "avatar") setAvatarUrl(src);
      else setCoverUrl(src);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  };

  const onSave = async () => {
    setSaving(true);
    setErr(null);
    try {
      const data = await updateMyProfile({
        display_name: displayName.trim(),
        headline: headline.trim(),
        bio: bio.trim(),
        avatar_url: avatarUrl,
        cover_url: coverUrl,
      });
      navigate(`/u/${encodeURIComponent(data.profile.username)}`);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setSaving(false);
    }
  };

  const previewName = displayName.trim() || profile?.username || "用户";
  const backTo = profile
    ? `/u/${encodeURIComponent(profile.username)}`
    : "/community/me";

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[760px] px-3 py-5 pb-24 sm:px-5 sm:py-10 sm:pb-20">
        <Link
          to={backTo}
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition hover:text-slate-800"
        >
          <ArrowLeft className="h-4 w-4" />
          返回主页
        </Link>
        <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">
          编辑个人资料
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">
          头像、封面与简介会展示在公开主页，访客可见。
        </p>

        {loading ? (
          <div className="mt-10 flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中…
          </div>
        ) : (
          <div className="mt-8 rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <div className="relative h-40 overflow-hidden rounded-t-2xl bg-gradient-to-br from-slate-700 via-slate-600 to-slate-800 sm:h-44">
              {coverUrl ? (
                <img
                  src={coverUrl}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <div
                  className="absolute inset-0 opacity-35"
                  style={{
                    backgroundImage:
                      "radial-gradient(circle at 25% 40%, rgba(248,113,113,0.4), transparent 50%)",
                  }}
                  aria-hidden
                />
              )}
              <button
                type="button"
                onClick={() => coverInputRef.current?.click()}
                className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-lg bg-black/55 px-3 py-1.5 text-xs font-medium text-white backdrop-blur-sm transition hover:bg-black/70"
              >
                <Camera className="h-3.5 w-3.5" />
                更换封面
              </button>
              <input
                ref={coverInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  void pickImage(e.target.files?.[0], "cover");
                  e.target.value = "";
                }}
              />
            </div>

            <div className="px-5 pb-7 sm:px-8">
              <div className="-mt-11 flex items-end gap-4">
                <button
                  type="button"
                  onClick={() => avatarInputRef.current?.click()}
                  className="group relative z-10 shrink-0"
                  title="更换头像"
                >
                  <AuthorAvatar
                    name={previewName}
                    src={avatarUrl}
                    size="xl"
                    className="!ring-4 !ring-white shadow-md"
                  />
                  <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/45 opacity-0 transition group-hover:opacity-100">
                    <Camera className="h-5 w-5 text-white" />
                  </span>
                </button>
                <div className="mb-2 min-w-0 pb-1">
                  <p className="text-sm font-semibold text-slate-800">
                    {previewName}
                  </p>
                  <button
                    type="button"
                    onClick={() => avatarInputRef.current?.click()}
                    className="mt-0.5 text-xs font-medium text-red-600 hover:text-red-500"
                  >
                    点击更换头像
                  </button>
                </div>
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    void pickImage(e.target.files?.[0], "avatar");
                    e.target.value = "";
                  }}
                />
              </div>

              <div className="mt-8 space-y-5 border-t border-slate-100 pt-6">
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium text-slate-500">
                    显示名
                  </span>
                  <input
                    className={fieldClassName()}
                    value={displayName}
                    maxLength={32}
                    onChange={(e) => setDisplayName(e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium text-slate-500">
                    一句话介绍
                  </span>
                  <input
                    className={fieldClassName()}
                    value={headline}
                    maxLength={80}
                    placeholder="例如：量化研究员 · 因子爱好者"
                    onChange={(e) => setHeadline(e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium text-slate-500">
                    个人简介
                  </span>
                  <textarea
                    className={fieldClassName("min-h-[140px] resize-y")}
                    value={bio}
                    maxLength={2000}
                    placeholder="介绍一下自己…"
                    onChange={(e) => setBio(e.target.value)}
                  />
                  <span className="mt-1 block text-right text-[11px] text-slate-400">
                    {bio.length} / 2000
                  </span>
                </label>
              </div>

              <div className="mt-8 rounded-2xl border border-red-100 bg-red-50/50 p-5">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-red-700">
                  <Trash2 className="h-4 w-4" />
                  注销账号
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  注销后个人数据（自选、组合、模拟盘、策略、因子、知识库、通知等）会被删除；
                  已发布的帖子和评论保留，并显示为「已注销用户」。此操作不可恢复。
                </p>
                {!deleteOpen ? (
                  <button
                    type="button"
                    onClick={() => setDeleteOpen(true)}
                    className="mt-3 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50"
                  >
                    我要注销账号
                  </button>
                ) : (
                  <div className="mt-3 space-y-2">
                    <input
                      type="password"
                      className={fieldClassName()}
                      placeholder="登录密码"
                      value={deletePassword}
                      onChange={(e) => setDeletePassword(e.target.value)}
                    />
                    <input
                      className={fieldClassName()}
                      placeholder={`输入用户名 ${me?.username || ""} 或「注销」确认`}
                      value={deleteConfirm}
                      onChange={(e) => setDeleteConfirm(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={deleting}
                        onClick={() => void onDeleteAccount()}
                        className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:opacity-60"
                      >
                        {deleting ? "注销中…" : "确认注销"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setDeleteOpen(false);
                          setDeletePassword("");
                          setDeleteConfirm("");
                        }}
                        className="rounded-lg px-4 py-2 text-sm font-medium text-slate-500 hover:bg-white"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {err ? <p className="mt-4 text-sm text-red-600">{err}</p> : null}

              <div className="mt-8 hidden flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-5 sm:flex">
                <Link
                  to={backTo}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
                >
                  取消
                </Link>
                <PrimaryButton
                  type="button"
                  disabled={saving || !displayName.trim()}
                  onClick={() => void onSave()}
                >
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      保存中…
                    </>
                  ) : (
                    "保存"
                  )}
                </PrimaryButton>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 手机底栏保存 */}
      {!loading && profile ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur-sm sm:hidden">
          <div className="mx-auto flex max-w-[760px] gap-2">
            <Link
              to={backTo}
              className="inline-flex flex-1 items-center justify-center rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600"
            >
              取消
            </Link>
            <PrimaryButton
              type="button"
              disabled={saving || !displayName.trim()}
              onClick={() => void onSave()}
              className="!flex-1"
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  保存中…
                </>
              ) : (
                "保存"
              )}
            </PrimaryButton>
          </div>
        </div>
      ) : null}
    </CommunityPageShell>
  );
}
