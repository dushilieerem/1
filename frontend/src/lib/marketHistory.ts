export type MarketHistoryRange = { start: string; end: string };

/**
 * 按给定的有界区间逐段加载历史。
 * 空年不能证明更早没有行情：退市股票近年为空，历史中也可能存在缺口。
 * 每次消费一段后才请求下一段，保留渐进展示，并避免取消后的额外请求。
 */
export async function* streamMarketHistory<T extends { bars: readonly unknown[] }>(
  ranges: readonly MarketHistoryRange[],
  fetchRange: (range: MarketHistoryRange) => Promise<T | null>,
  isCancelled: () => boolean = () => false,
): AsyncGenerator<T> {
  for (const range of ranges) {
    if (isCancelled()) return;
    const chunk = await fetchRange(range);
    if (isCancelled()) return;
    if (chunk?.bars?.length) yield chunk;
  }
}
