const PYTHON_KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break",
  "class", "continue", "def", "del", "elif", "else", "except", "finally",
  "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
  "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);

export function factorNameError(name: string): string | null {
  const value = name.trim();
  if (!value) return "请填写因子代码名";
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
    return "因子代码名仅支持字母、数字和下划线，不能以数字开头";
  }
  if (PYTHON_KEYWORDS.has(value)) return `因子代码名不能使用 Python 关键字：${value}`;
  return null;
}
