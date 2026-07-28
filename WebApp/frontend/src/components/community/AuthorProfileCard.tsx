import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Loader2, UserCheck, UserPlus } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  followUser,
  getUserProfile,
  unfollowUser,
  type UserProfile,
} from "@/lib/profileApi";
import { AuthorAvatar, PrimaryButton } from "@/components/community/communityUi";

type AnchorRect = { top: number; left: number; bottom: number; width: number };

/**
 * 评论/列表里头像：单击打开资料浮层（实时拉公开主页），可关注或进主页；
 * 双击仍可交给外层做 @ 插入。
 */
export function AuthorAvatarWithCard({
  username,
  name,
  src,
  size = "md",
  onDoubleClick,
}: {
  username?: string | null;
  name: string;
  src?: string | null;
  size?: "sm" | "md" | "lg";
  onDoubleClick?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<AnchorRect | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  if (!username) {
    return (
      <AuthorAvatar
        name={name}
        src={src}
        size={size}
        onDoubleClick={onDoubleClick}
      />
    );
  }

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="inline-flex shrink-0 rounded-full outline-none ring-offset-1 focus-visible:ring-2 focus-visible:ring-red-300"
        title="查看资料"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          const r = btnRef.current?.getBoundingClientRect();
          if (r) {
            setAnchor({
              top: r.top,
              left: r.left,
              bottom: r.bottom,
              width: r.width,
            });
          }
          setOpen(true);
        }}
        onDoubleClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDoubleClick?.();
        }}
      >
        <AuthorAvatar name={name} src={src} size={size} />
      </button>
      {open && username ? (
        <AuthorProfilePopover
          username={username}
          fallbackName={name}
          fallbackAvatar={src}
          anchor={anchor}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

function AuthorProfilePopover({
  username,
  fallbackName,
  fallbackAvatar,
  anchor,
  onClose,
}: {
  username: string;
  fallbackName: string;
  fallbackAvatar?: string | null;
  anchor: AnchorRect | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void getUserProfile(username)
      .then((data) => {
        if (!cancelled) setProfile(data.profile);
      })
      .catch((ex) => {
        if (!cancelled) {
          setErr(ex instanceof Error ? ex.message : String(ex));
          setProfile(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [username]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onDown = (e: MouseEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // 滚动时关掉，避免 fixed 浮层「钉」在屏幕上
    const onScroll = () => onClose();
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [onClose]);

  const display =
    profile?.display_name || profile?.username || fallbackName || username;
  const avatar = profile?.avatar_url ?? fallbackAvatar;
  const uname = profile?.username || username;
  const path = `/u/${encodeURIComponent(uname)}`;

  const style: CSSProperties = (() => {
    const cardW = 300;
    if (!anchor) {
      return { top: "20%", left: "50%", transform: "translateX(-50%)" };
    }
    const left = Math.min(
      Math.max(12, anchor.left),
      window.innerWidth - cardW - 12,
    );
    const spaceBelow = window.innerHeight - anchor.bottom;
    if (spaceBelow < 280 && anchor.top > 280) {
      return { top: Math.max(12, anchor.top - 8), left, transform: "translateY(-100%)" };
    }
    return { top: anchor.bottom + 8, left };
  })();

  const onFollow = async () => {
    if (!profile || profile.is_self) return;
    const me = getStoredUser();
    if (!me) {
      onClose();
      navigate(`/login?next=${encodeURIComponent(path)}`);
      return;
    }
    setBusy(true);
    try {
      const fn = profile.is_following ? unfollowUser : followUser;
      const data = await fn(profile.username);
      setProfile(data.profile);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  };

  const goProfile = () => {
    onClose();
    navigate(path);
  };

  const goFollowList = (kind: "following" | "followers") => {
    onClose();
    navigate(`${path}/${kind}`);
  };

  return createPortal(
    <div className="fixed inset-0 z-[80]">
      <div className="absolute inset-0 bg-slate-900/10" aria-hidden />
      <div
        ref={cardRef}
        role="dialog"
        aria-label={`${display} 的资料`}
        className="absolute w-[300px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-300/40"
        style={style}
      >
        <div className="h-16 bg-gradient-to-br from-slate-600 to-slate-800">
          {profile?.cover_url ? (
            <img
              src={profile.cover_url}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : null}
        </div>
        <div className="px-4 pb-4">
          <div className="-mt-8">
            <AuthorAvatar
              name={display}
              src={avatar}
              size="lg"
              className="!ring-4 !ring-white shadow-sm"
            />
          </div>
          {loading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载资料…
            </div>
          ) : err && !profile ? (
            <p className="mt-3 text-sm text-red-600">{err}</p>
          ) : (
            <>
              <p className="mt-2 text-base font-bold text-slate-900">{display}</p>
              {profile?.headline ? (
                <p className="mt-0.5 line-clamp-2 text-xs text-slate-600">
                  {profile.headline}
                </p>
              ) : null}
              <p className="mt-0.5 text-[11px] text-slate-400">
                @{profile?.username || username}
              </p>
              <div className="mt-3 flex gap-4 text-xs text-slate-500">
                <button
                  type="button"
                  onClick={() => goFollowList("following")}
                  className="hover:text-slate-800"
                >
                  <strong className="tabular-nums text-slate-800">
                    {profile?.following_count ?? 0}
                  </strong>{" "}
                  关注
                </button>
                <button
                  type="button"
                  onClick={() => goFollowList("followers")}
                  className="hover:text-slate-800"
                >
                  <strong className="tabular-nums text-slate-800">
                    {profile?.followers_count ?? 0}
                  </strong>{" "}
                  粉丝
                </button>
                <button
                  type="button"
                  onClick={goProfile}
                  className="hover:text-slate-800"
                >
                  <strong className="tabular-nums text-slate-800">
                    {profile?.post_count ?? 0}
                  </strong>{" "}
                  帖子
                </button>
              </div>
              {profile?.bio ? (
                <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-500">
                  {profile.bio}
                </p>
              ) : null}
              {err ? <p className="mt-2 text-xs text-red-600">{err}</p> : null}
              <div className="mt-3 flex gap-2">
                {!profile?.is_self ? (
                  <PrimaryButton
                    type="button"
                    disabled={busy}
                    onClick={() => void onFollow()}
                    className={
                      profile?.is_following
                        ? "!h-9 !flex-1 !bg-slate-100 !px-2 !text-xs !text-slate-700 !shadow-none hover:!bg-slate-200"
                        : "!h-9 !flex-1 !px-2 !text-xs"
                    }
                  >
                    {profile?.is_following ? (
                      <>
                        <UserCheck className="h-3.5 w-3.5" />
                        已关注
                      </>
                    ) : (
                      <>
                        <UserPlus className="h-3.5 w-3.5" />
                        关注
                      </>
                    )}
                  </PrimaryButton>
                ) : null}
                <button
                  type="button"
                  onClick={goProfile}
                  className={`inline-flex h-9 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 ${
                    profile?.is_self ? "flex-1" : ""
                  }`}
                >
                  查看公开主页
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
