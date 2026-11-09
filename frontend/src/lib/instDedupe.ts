/** 列表按唯一业务主键去重，保留首次出现的顺序。 */
export function dedupeBy<T>(
  items: readonly T[] | null | undefined,
  key: (item: T) => string | number | null | undefined,
): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items || []) {
    const raw = key(item);
    const id = raw == null ? "" : String(raw);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}
