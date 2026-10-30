import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

const Ctx = createContext<(message: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const show = useCallback((next: string) => {
    setMessage(next);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 2200);
  }, []);

  const value = useMemo(() => show, [show]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className={`toast ${message ? "on" : ""}`} role="status" aria-live="polite">{message}</div>
    </Ctx.Provider>
  );
}

export function useToast() {
  return useContext(Ctx);
}
