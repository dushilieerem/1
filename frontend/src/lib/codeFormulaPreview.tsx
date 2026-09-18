import type { ReactNode } from "react";

/**
 * 因子公式预览：按 Python 源码展示，保留换行。
 * 不再把 `/` 画成分数线（多语句 / return / 赋值会被拆坏）。
 */

function isStatementLike(formula: string): boolean {
  const t = formula.trim();
  if (!t) return false;
  if (t.includes("\n")) return true;
  if (/\breturn\b/.test(t)) return true;
  if (/\bdef\b/.test(t)) return true;
  // 赋值语句（排除 ==）
  if (/(?<![=!<>])=(?!=)/.test(t)) return true;
  return false;
}

function highlightLine(line: string, keyBase: string): ReactNode {
  // 粗粒度高亮：关键字 / 数字 / self.字段 / 方法调用
  const parts: ReactNode[] = [];
  const re =
    /(\b(?:return|def|lambda|for|in|if|else|True|False|None|import|from)\b)|(\b\d+(?:\.\d+)?\b)|(self\.\w+)|(\.\w+\()|(\#[^\n]*)|([^\s#]+|\s+)/g;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(line)) !== null) {
    const [full, kw, num, field, method, comment, other] = m;
    const key = `${keyBase}-${i++}`;
    if (kw) {
      parts.push(
        <span key={key} className="font-semibold text-violet-700">
          {kw}
        </span>,
      );
    } else if (num) {
      parts.push(
        <span key={key} className="tabular-nums text-amber-700">
          {num}
        </span>,
      );
    } else if (field) {
      parts.push(
        <span key={key} className="font-medium text-rose-700">
          {field}
        </span>,
      );
    } else if (method) {
      parts.push(
        <span key={key} className="text-sky-700">
          {method}
        </span>,
      );
    } else if (comment) {
      parts.push(
        <span key={key} className="text-slate-400 italic">
          {comment}
        </span>,
      );
    } else {
      parts.push(
        <span key={key} className="text-slate-700">
          {other ?? full}
        </span>,
      );
    }
  }
  return parts.length ? parts : line;
}

function CodeBlock({ formula }: { formula: string }) {
  const lines = formula.replace(/\r\n/g, "\n").split("\n");
  return (
    <pre className="m-0 max-h-64 overflow-auto rounded-xl bg-slate-50 px-4 py-3 text-left font-mono text-[12.5px] leading-6 text-slate-800 ring-1 ring-slate-200/80">
      {lines.map((line, idx) => (
        <div key={idx} className="whitespace-pre">
          {line.length ? highlightLine(line, `L${idx}`) : "\u00a0"}
        </div>
      ))}
    </pre>
  );
}

/** 极简单行表达式：仅做符号着色，不做分数排版 */
function SimpleExpr({ formula }: { formula: string }) {
  return (
    <div className="overflow-x-auto rounded-xl bg-gradient-to-br from-slate-50 to-slate-100/80 px-4 py-3 text-center font-mono text-[13px] leading-relaxed">
      {highlightLine(formula.trim(), "e")}
    </div>
  );
}

export function CodeFormulaPreview({ formula }: { formula: string }) {
  const raw = formula.trim();
  if (!raw) return null;
  if (isStatementLike(raw)) return <CodeBlock formula={raw} />;
  return <SimpleExpr formula={raw} />;
}
