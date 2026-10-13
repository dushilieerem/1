/** Rich-text posts store HTML; plain Markdown remains source text. */
export function postBodyText(value: string): string {
  const trimmed = value.trim();
  if (!/^</.test(trimmed) || !/<\/[a-z][\w-]*>/i.test(trimmed)) return trimmed;
  const doc = new DOMParser().parseFromString(trimmed, "text/html");
  doc.querySelectorAll("script,style,template").forEach(node => node.remove());
  return (doc.body.textContent || "").trim();
}
