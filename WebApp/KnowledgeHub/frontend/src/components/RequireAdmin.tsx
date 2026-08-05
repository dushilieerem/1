import { Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchMe, getStoredUser, type AuthUser } from "@/lib/auth";

export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchMe()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        加载中…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2">
        <p className="text-lg font-semibold">仅管理员可进入知识库平台</p>
        <a href="http://192.168.3.32:9530/" className="text-sm text-sky-700 underline">
          返回 SVQuant
        </a>
      </div>
    );
  }
  return <>{children}</>;
}
