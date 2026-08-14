import { useEffect, useState } from "react";

/**
 * 软键盘顶起量：layout 底部被挡的高度（px）。
 * 用于 position:fixed 的输入条 bottom 偏移。
 */
export function useKeyboardInset() {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const sync = () => {
      // 键盘打开时：layout 高度 - 可见高度 - 顶部偏移 = 底部被挡高度
      const blocked = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      setInset(blocked);
      document.documentElement.style.setProperty("--kb-inset", `${blocked}px`);
      document.documentElement.style.setProperty("--app-vvh", `${vv.height}px`);
      document.documentElement.style.setProperty("--app-vv-offset", `${vv.offsetTop}px`);
    };

    sync();
    vv.addEventListener("resize", sync);
    vv.addEventListener("scroll", sync);
    window.addEventListener("resize", sync);
    return () => {
      vv.removeEventListener("resize", sync);
      vv.removeEventListener("scroll", sync);
      window.removeEventListener("resize", sync);
      document.documentElement.style.removeProperty("--kb-inset");
      document.documentElement.style.removeProperty("--app-vvh");
      document.documentElement.style.removeProperty("--app-vv-offset");
    };
  }, []);

  return inset;
}
