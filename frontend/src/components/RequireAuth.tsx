import { Navigate, useLocation } from "react-router-dom";
import { getStoredUser, prepareAuthHandoff } from "@/lib/auth";

/** 未登录只能看首页；受保护路由跳转登录 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = getStoredUser();
  const loc = useLocation();
  if (!user) {
    return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  }
  return <>{children}</>;
}

/** 打开需登录的新标签（带 sessionStorage 登录交接） */
export function openAuthedTab(path: string) {
  prepareAuthHandoff();
  const win = window.open(path, "_blank");
  if (!win) {
    window.location.assign(path);
  }
}
