import type { ReactNode } from "react";

const PRICE_FIELDS = new Set(["close", "open", "high", "low", "pre_close"]);
const VOL_FIELDS = new Set(["volume", "amount", "turn"]);
const RET_FIELDS = new Set(["ret_1d", "change_ratio", "amplitude", "hl_range"]);

type Tok =
  | { k: "field"; v: string }
  | { k: "method"; name: string; args: string }
  | { k: "num"; v: string }
  | { k: "eps" }
  | { k: "op"; v: string }
  | { k: "punct"; v: string };

function stripOuterParens(s: string): string {
  let t = s.trim();
  while (t.startsWith("(") && t.endsWith(")")) {
    let depth = 0;
    let ok = true;
    for (let i = 0; i < t.length; i++) {
      if (t[i] === "(") depth++;
      else if (t[i] === ")") {
        depth--;
        if (depth === 0 && i < t.length - 1) {
          ok = false;
          break;
        }
      }
    }
    if (!ok || depth !== 0) break;
    t = t.slice(1, -1).trim();
  }
  return t;
}

function splitTopLevel(expr: string, op: string): [string, string] | null {
  let depth = 0;
  for (let i = expr.length - 1; i >= 0; i--) {
    const c = expr[i];
    if (c === ")") depth++;
    else if (c === "(") depth--;
    else if (depth === 0 && c === op) {
      const left = expr.slice(0, i).trim();
      const right = expr.slice(i + 1).trim();
      if (left && right) return [left, right];
    }
  }
  return null;
}

function tokenize(expr: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  const s = expr.trim();

  while (i < s.length) {
    if (/\s/.test(s[i])) {
      i++;
      continue;
    }

    const num = s.slice(i).match(/^\d+(?:\.\d+)?/);
    if (num) {
      out.push({ k: "num", v: num[0] });
      i += num[0].length;
      continue;
    }

    const id = s.slice(i).match(/^[a-zA-Z_]\w*/);
    if (id) {
      const v = id[0];
      if (v === "eps") out.push({ k: "eps" });
      else if (
        PRICE_FIELDS.has(v) ||
        VOL_FIELDS.has(v) ||
        RET_FIELDS.has(v) ||
        /^[a-z]/.test(v)
      ) {
        out.push({ k: "field", v });
      } else {
        out.push({ k: "field", v });
      }
      i += v.length;
      continue;
    }

    if (s[i] === ".") {
      const m = s.slice(i).match(/^\.([a-zA-Z_]\w*)\(([^)]*)\)/);
      if (m) {
        out.push({ k: "method", name: m[1], args: m[2] });
        i += m[0].length;
        continue;
      }
    }

    if ("+-*/".includes(s[i])) {
      out.push({ k: "op", v: s[i] });
      i++;
      continue;
    }

    if ("(),".includes(s[i])) {
      out.push({ k: "punct", v: s[i] });
      i++;
      continue;
    }

    out.push({ k: "punct", v: s[i] });
    i++;
  }

  return out;
}

function fieldClass(name: string): string {
  if (PRICE_FIELDS.has(name)) return "text-rose-700";
  if (VOL_FIELDS.has(name)) return "text-sky-700";
  if (RET_FIELDS.has(name)) return "text-emerald-700";
  return "text-slate-700";
}

function renderTokens(tokens: Tok[]): ReactNode {
  return tokens.map((t, idx) => {
    if (t.k === "field") {
      return (
        <span key={idx} className={`font-semibold ${fieldClass(t.v)}`}>
          {t.v}
        </span>
      );
    }
    if (t.k === "method") {
      return (
        <span key={idx} className="text-violet-700">
          .{t.name}(<span className="text-amber-700 tabular-nums">{t.args}</span>)
        </span>
      );
    }
    if (t.k === "num") {
      return (
        <span key={idx} className="text-amber-700 tabular-nums">
          {t.v}
        </span>
      );
    }
    if (t.k === "eps") {
      return (
        <span key={idx} className="text-slate-500 italic">
          ε
        </span>
      );
    }
    if (t.k === "op") {
      const display = t.v === "*" ? " × " : t.v === "/" ? " ÷ " : ` ${t.v} `;
      return (
        <span key={idx} className="mx-0.5 font-medium text-slate-400">
          {display}
        </span>
      );
    }
    return (
      <span key={idx} className="text-slate-600">
        {t.v}
      </span>
    );
  });
}

function renderExpr(expr: string): ReactNode {
  const raw = expr.trim();
  if (!raw) return null;

  const frac = splitTopLevel(raw, "/");
  if (frac) {
    return (
      <div className="inline-flex flex-col items-stretch">
        <div className="flex justify-center px-3 py-1.5">{renderExpr(frac[0])}</div>
        <div className="mx-2 min-w-[4rem] border-t-[1.5px] border-slate-400" />
        <div className="flex justify-center px-3 py-1.5">{renderExpr(frac[1])}</div>
      </div>
    );
  }

  const inner = stripOuterParens(raw);
  if (inner !== raw) {
    return (
      <span>
        <span className="text-slate-400">(</span>
        {renderExpr(inner)}
        <span className="text-slate-400">)</span>
      </span>
    );
  }

  return (
    <span className="font-mono text-[14px] leading-relaxed tracking-tight">
      {renderTokens(tokenize(raw))}
    </span>
  );
}

export function CodeFormulaPreview({ formula }: { formula: string }) {
  const raw = formula.trim();
  if (!raw) return null;

  return (
    <div className="flex min-h-[4.5rem] items-center justify-center overflow-x-auto rounded-xl bg-gradient-to-br from-slate-50 to-slate-100/80 px-3 py-4">
      {renderExpr(raw)}
    </div>
  );
}
