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

/** 同一业务主键只保留最新一条；recency 用可排序字符串（ISO 时间 + 补零 id）。 */
export function latestByKey<T>(
  items: readonly T[] | null | undefined,
  key: (item: T) => string | number | null | undefined,
  recency: (item: T) => string,
): T[] {
  const latest = new Map<string, { score: string; item: T }>();
  for (const item of items || []) {
    const raw = key(item);
    const id = raw == null ? "" : String(raw);
    if (!id) continue;
    const score = recency(item);
    const prev = latest.get(id);
    if (!prev || score > prev.score) latest.set(id, { score, item });
  }
  return [...latest.values()].map((x) => x.item);
}
