import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type InstLocale = "zh" | "en";
export type InstMarket = "CN" | "US";

type Value = {
  locale: InstLocale;
  market: InstMarket;
  setLocale: (next: InstLocale) => void;
  toggle: () => void;
  t: (zh: string, en: string) => string;
};

const KEY = "svquant_inst_locale";
const InstLocaleContext = createContext<Value | null>(null);

function readLocale(): InstLocale {
  try {
    const raw = localStorage.getItem(KEY);
    return raw === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}

export function InstLocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<InstLocale>(readLocale);

  const setLocale = (next: InstLocale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
  };

  const value = useMemo<Value>(
    () => ({
      locale,
      market: locale === "zh" ? "CN" : "US",
      setLocale,
      toggle: () => setLocale(locale === "zh" ? "en" : "zh"),
      t: (zh: string, en: string) => (locale === "zh" ? zh : en),
    }),
    [locale],
  );

  return <InstLocaleContext.Provider value={value}>{children}</InstLocaleContext.Provider>;
}

export function useInstLocale(): Value {
  const value = useContext(InstLocaleContext);
  if (!value) {
    // 页面在 Provider 外被单独渲染时给中文默认值，避免崩溃。
    return {
      locale: "zh",
      market: "CN",
      setLocale: () => undefined,
      toggle: () => undefined,
      t: (zh: string) => zh,
    };
  }
  return value;
}
