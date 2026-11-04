import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Locale = "zh" | "en";
export type Market = "CN" | "US";

type Value = {
  locale: Locale;
  market: Market;
  setLocale: (next: Locale) => void;
  toggle: () => void;
  t: (zh: string, en: string) => string;
};

const KEY = "svq_invest_locale";
const Ctx = createContext<Value | null>(null);

function readLocale(): Locale {
  try {
    return localStorage.getItem(KEY) === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readLocale);

  const setLocale = (next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
  }, [locale]);

  const value = useMemo<Value>(
    () => ({
      locale,
      market: locale === "en" ? "US" : "CN",
      setLocale,
      toggle: () => setLocale(locale === "en" ? "zh" : "en"),
      t: (zh: string, en: string) => (locale === "en" ? en : zh),
    }),
    [locale],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLocale(): Value {
  const value = useContext(Ctx);
  if (value) return value;
  // 页面在 Provider 外单独渲染时给中文默认值，避免崩溃。
  return {
    locale: "zh",
    market: "CN",
    setLocale: () => undefined,
    toggle: () => undefined,
    t: (zh: string) => zh,
  };
}

/** 给 GET 请求追加市场参数；已有查询串时用 &。 */
export function withMarket(path: string, market: Market): string {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}market=${market}`;
}

export function LocaleToggle({ compact = false }: { compact?: boolean }) {
  const { locale, toggle } = useLocale();
  return (
    <button
      className={`locale-toggle ${compact ? "compact" : ""}`}
      onClick={toggle}
      aria-label={locale === "en" ? "切换到中文" : "Switch to English"}
      title={locale === "en" ? "切换到中文 / Switch to Chinese" : "Switch to English / 切换英文"}
    >
      {locale === "en" ? "中文" : "EN"}
    </button>
  );
}
