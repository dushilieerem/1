import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView, keymap, placeholder as cmPlaceholder } from "@codemirror/view";
import { indentWithTab } from "@codemirror/commands";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

/** 浅色 IDE 风高亮 */
const lightHighlight = HighlightStyle.define([
  { tag: t.keyword, color: "#7c3aed", fontWeight: "600" },
  { tag: t.comment, color: "#16a34a" },
  { tag: t.string, color: "#2563eb" },
  { tag: t.number, color: "#2563eb" },
  { tag: t.bool, color: "#7c3aed" },
  { tag: t.null, color: "#7c3aed" },
  { tag: t.operator, color: "#64748b" },
  { tag: t.definition(t.variableName), color: "#1d4ed8" },
  { tag: t.function(t.variableName), color: "#1d4ed8" },
  { tag: t.propertyName, color: "#0f766e" },
  { tag: t.variableName, color: "#0f172a" },
  { tag: t.punctuation, color: "#64748b" },
  { tag: t.meta, color: "#64748b" },
]);

const darkHighlight = HighlightStyle.define([
  { tag: t.keyword, color: "#c4b5fd", fontWeight: "600" },
  { tag: t.comment, color: "#86efac", fontStyle: "italic" },
  { tag: t.string, color: "#7dd3fc" },
  { tag: t.number, color: "#fcd34d" },
  { tag: t.bool, color: "#c4b5fd" },
  { tag: t.null, color: "#c4b5fd" },
  { tag: t.operator, color: "#94a3b8" },
  { tag: t.definition(t.variableName), color: "#93c5fd" },
  { tag: t.function(t.variableName), color: "#93c5fd" },
  { tag: t.propertyName, color: "#5eead4" },
  { tag: t.variableName, color: "#e2e8f0" },
  { tag: t.punctuation, color: "#94a3b8" },
  { tag: t.meta, color: "#94a3b8" },
  { tag: t.self, color: "#f9a8d4" },
]);

const lightTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    height: "100%",
    backgroundColor: "#ffffff",
    borderRadius: "0.5rem",
    border: "1px solid #e2e8f0",
  },
  "&.cm-focused": {
    outline: "2px solid #bfdbfe",
    outlineOffset: "0",
  },
  ".cm-scroller": {
    fontFamily: "var(--font-mono), ui-monospace, monospace",
    lineHeight: "1.55",
    backgroundColor: "#ffffff",
    overflow: "auto !important",
  },
  ".cm-content": {
    padding: "12px 0",
    caretColor: "#0f172a",
    minHeight: "100%",
  },
  ".cm-gutters": {
    backgroundColor: "#f8fafc",
    color: "#94a3b8",
    border: "none",
    borderRight: "1px solid #e2e8f0",
    minWidth: "2.75rem",
  },
  ".cm-lineNumbers .cm-gutterElement": {
    padding: "0 10px 0 8px",
    minWidth: "2rem",
    textAlign: "right",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#e2e8f0",
    color: "#475569",
  },
  ".cm-activeLine": {
    backgroundColor: "rgba(241, 245, 249, 0.9)",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "rgba(147, 197, 253, 0.45) !important",
  },
  ".cm-cursor": {
    borderLeftColor: "#0f172a",
  },
  ".cm-placeholder": {
    color: "#94a3b8",
  },
});

const darkTheme = EditorView.theme(
  {
    "&": {
      fontSize: "13px",
      height: "100%",
      backgroundColor: "#0f172a !important",
      borderRadius: "0",
      border: "none",
      overflow: "hidden",
      color: "#e2e8f0",
    },
    "&.cm-focused": {
      outline: "none",
    },
    ".cm-scroller": {
      fontFamily: "var(--font-mono), ui-monospace, monospace",
      lineHeight: "1.6",
      backgroundColor: "#0f172a !important",
      overflow: "auto !important",
    },
    ".cm-content": {
      padding: "10px 0",
      caretColor: "#f8fafc",
      color: "#e2e8f0",
      minHeight: "100%",
    },
    ".cm-gutters": {
      backgroundColor: "#020617 !important",
      color: "#64748b",
      border: "none",
      borderRight: "1px solid #1e293b",
      minWidth: "2.5rem",
    },
    ".cm-lineNumbers .cm-gutterElement": {
      padding: "0 8px 0 10px",
      minWidth: "2rem",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "#1e293b",
      color: "#cbd5e1",
    },
    ".cm-activeLine": {
      backgroundColor: "rgba(51, 65, 85, 0.45)",
    },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
      backgroundColor: "rgba(239, 68, 68, 0.32) !important",
    },
    ".cm-cursor": {
      borderLeftColor: "#f8fafc",
    },
    ".cm-placeholder": {
      color: "#64748b",
      fontStyle: "italic",
    },
  },
  { dark: true },
);

type Props = {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  height?: string;
  variant?: "light" | "dark";
  readOnly?: boolean;
};

/** Python 编辑器：语法高亮 + 行号 + Tab 缩进 */
export function FactorCodeEditor({
  value,
  onChange,
  className = "",
  height = "280px",
  variant = "light",
  readOnly = false,
}: Props) {
  const dark = variant === "dark";
  return (
    <div
      className={`min-h-0 ${
        dark
          ? "overflow-hidden rounded-xl border border-slate-800 bg-slate-950 shadow-inner"
          : "h-full overflow-hidden rounded-lg"
      } ${className}`}
      style={{
        background: dark ? "#0f172a" : "#ffffff",
        height: height === "100%" ? "100%" : undefined,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {dark && (
        <div className="flex shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-3 py-1.5">
          <span className="text-[11px] font-medium tracking-wide text-slate-400">
            PYTHON
          </span>
          <span className="text-[10px] text-slate-600">高亮 · 行号</span>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        <CodeMirror
          value={value}
          height={height === "100%" ? "100%" : height}
          style={{ height: "100%" }}
          theme={dark ? "dark" : "light"}
          editable={!readOnly}
          extensions={[
            python(),
            keymap.of([indentWithTab]),
            syntaxHighlighting(dark ? darkHighlight : lightHighlight),
            dark ? darkTheme : lightTheme,
            EditorView.lineWrapping,
            cmPlaceholder("def my_factor(self):\n    return self.close.pct_change(20)"),
            ...(readOnly ? [EditorView.editable.of(false)] : []),
          ]}
          basicSetup={{
            lineNumbers: true,
            foldGutter: false,
            highlightActiveLine: !readOnly,
            highlightSelectionMatches: false,
            bracketMatching: true,
            autocompletion: false,
            indentOnInput: true,
          }}
          onChange={readOnly ? () => undefined : onChange}
        />
      </div>
    </div>
  );
}
