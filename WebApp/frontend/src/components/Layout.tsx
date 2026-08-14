import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ConfirmProvider } from "./ConfirmDialog";
import { Navbar } from "./Navbar";
import { ScrollToTop } from "./ScrollToTop";
import { fetchMarketDaily, peekPersistedDaily } from "@/lib/marketDataApi";

/** 面板默认标的：任何页面打开后后台预热，保证进 K 线面板有本地缓存可秒开 */
const WARM_SYMBOL = "000001.SZ";

export function Layout() {
  const { pathname } = useLocation();
  const lockShell = pathname.startsWith("/ai/chat");
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches,
  );

  useEffect(() => {
    const m = window.matchMedia("(max-width: 767px)");
    const sync = () => setNarrow(m.matches);
    sync();
    m.addEventListener("change", sync);
    return () => m.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (peekPersistedDaily(WARM_SYMBOL)?.bars?.length) return;
    const d = new Date();
    d.setDate(d.getDate() - 120);
    const start = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    void fetchMarketDaily(WARM_SYMBOL, { start }).catch(() => undefined);
  }, []);

  // 对话页手机端隐藏站级顶栏，避免双汉堡 + 键盘更挤
  const showNavbar = !(lockShell && narrow);

  return (
    <ConfirmProvider>
      <ScrollToTop />
      <div
        className={
          lockShell
            ? "flex h-dvh flex-col overflow-hidden bg-slate-50 max-md:h-[var(--app-vvh,100dvh)] max-md:mt-[var(--app-vv-offset,0px)]"
            : "min-h-screen bg-slate-50"
        }
      >
        {showNavbar ? <Navbar /> : null}
        <main className={lockShell ? "relative min-h-0 flex-1 overflow-hidden" : undefined}>
          <Outlet />
        </main>
      </div>
    </ConfirmProvider>
  );
}
