import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import sql from "highlight.js/lib/languages/sql";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";

let registered = false;

function ensureHljs() {
  if (registered) return;
  hljs.registerLanguage("python", python);
  hljs.registerLanguage("py", python);
  hljs.registerLanguage("javascript", javascript);
  hljs.registerLanguage("js", javascript);
  hljs.registerLanguage("typescript", typescript);
  hljs.registerLanguage("ts", typescript);
  hljs.registerLanguage("sql", sql);
  hljs.registerLanguage("bash", bash);
  hljs.registerLanguage("shell", bash);
  hljs.registerLanguage("json", json);
  registered = true;
}

function detectLang(className: string | null | undefined): string {
  if (!className) return "python";
  const m = /language-([\w+-]+)/i.exec(className);
  return (m?.[1] || "python").toLowerCase();
}

/** 把 HTML 里的 <pre><code> 做语法高亮（阅读态；编辑器存的是纯文本） */
export function highlightHtmlCodeBlocks(html: string): string {
  if (typeof window === "undefined" || !html.includes("<pre")) return html;
  ensureHljs();
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("pre code").forEach((codeEl) => {
    const code = codeEl as HTMLElement;
    // 已有 hljs span 则跳过
    if (code.querySelector(".hljs-keyword, .hljs-string, span.hljs-")) return;
    const raw = code.textContent || "";
    if (!raw.trim()) return;
    const lang = detectLang(code.getAttribute("class"));
    try {
      const result = hljs.getLanguage(lang)
        ? hljs.highlight(raw, { language: lang, ignoreIllegals: true })
        : hljs.highlightAuto(raw);
      code.innerHTML = result.value;
      code.classList.add("hljs");
      if (!/language-/i.test(code.className)) {
        code.classList.add(`language-${result.language || lang}`);
      }
    } catch {
      // keep plain
    }
  });
  return doc.body.innerHTML;
}

/** 单段源码高亮（帖子底部代码片段） */
export function highlightSource(
  source: string,
  language = "python",
): { html: string; language: string } {
  ensureHljs();
  const raw = source || "";
  try {
    const result = hljs.getLanguage(language)
      ? hljs.highlight(raw, { language, ignoreIllegals: true })
      : hljs.highlightAuto(raw);
    return { html: result.value, language: result.language || language };
  } catch {
    const esc = raw
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return { html: esc, language };
  }
}
