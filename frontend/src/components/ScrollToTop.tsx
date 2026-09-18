import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/** 路由切换时滚到页面顶部，避免从首页长页跳转后停在中间/底部。 */
export function ScrollToTop() {
  const { pathname, search } = useLocation();

  useEffect(() => {
    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [pathname, search]);

  return null;
}
