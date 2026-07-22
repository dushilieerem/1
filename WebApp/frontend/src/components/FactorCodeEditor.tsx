import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView, keymap } from "@codemirror/view";
import { indentWithTab } from "@codemirror/commands";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

/** 浅色 IDE 风高亮（接近常见编译器配色） */
const factorHighlight = HighlightStyle.define([
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

const editorTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    backgroundColor: "#f8fafc",
    borderRadius: "1rem",
    border: "1px solid #e2e8f0",
    overflow: "hidden",
  },
  "&.cm-focused": {
    outline: "2px solid #ddd6fe",
    outlineOffset: "0",
  },
  ".cm-scroller": {
    fontFamily: 'var(--font-mono), ui-monospace, monospace',
    lineHeight: "1.55",
    minHeight: "280px",
  },
  ".cm-content": {
    padding: "12px 0",
    caretColor: "#0f172a",
  },
  ".cm-gutters": {
    backgroundColor: "#f1f5f9",
    color: "#94a3b8",
    border: "none",
    borderRight: "1px solid #e2e8f0",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#e2e8f0",
    color: "#475569",
  },
  ".cm-activeLine": {
    backgroundColor: "rgba(241, 245, 249, 0.9)",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "rgba(196, 181, 253, 0.45) !important",
  },
  ".cm-cursor": {
    borderLeftColor: "#0f172a",
  },
});

type Props = {
  value: string;
  onChange: (value: string) => void;
  className?: string;
};

/** 自定义因子 Python 编辑器：语法高亮 + Tab 缩进 */
export function FactorCodeEditor({ value, onChange, className = "" }: Props) {
  return (
    <div className={`mt-1 overflow-hidden rounded-2xl ${className}`}>
      <CodeMirror
        value={value}
        height="280px"
        extensions={[
          python(),
          keymap.of([indentWithTab]),
          syntaxHighlighting(factorHighlight),
          editorTheme,
          EditorView.lineWrapping,
        ]}
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: true,
          highlightSelectionMatches: false,
          bracketMatching: true,
          autocompletion: false,
          indentOnInput: true,
        }}
        onChange={onChange}
      />
    </div>
  );
}
