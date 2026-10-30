import { createContext, useContext } from "react";
import type { InstSession } from "@/lib/instAuth";

/** 机构会话上下文：由 InstLayout 注入，页面只读 */
export const InstSessionContext = createContext<InstSession | null>(null);

export function useInstSession(): InstSession {
  const session = useContext(InstSessionContext);
  if (!session) {
    throw new Error("useInstSession 必须在 InstLayout 内使用");
  }
  return session;
}
