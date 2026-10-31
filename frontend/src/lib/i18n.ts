/** P2-11：轻量国际化框架（中/英），默认中文，不引入第三方依赖。 */

export type Locale = "zh" | "en";

const LOCALE_KEY = "svquant.locale";
const listeners = new Set<(locale: Locale) => void>();

export function normalizeLocale(raw: string | null | undefined): Locale {
  return (raw || "").toLowerCase().startsWith("en") ? "en" : "zh";
}

export function getLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_KEY);
    if (saved) return normalizeLocale(saved);
  } catch {
    /* ignore */
  }
  if (typeof navigator !== "undefined") {
    return normalizeLocale(navigator.language);
  }
  return "zh";
}

export function setLocale(locale: Locale): void {
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch {
    /* ignore */
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
  }
  for (const fn of listeners) fn(locale);
}

export function subscribeLocale(fn: (locale: Locale) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** 双语取词：t("保存", "Save")。 */
export function t(zh: string, en: string, locale: Locale = getLocale()): string {
  return locale === "en" ? en : zh;
}
