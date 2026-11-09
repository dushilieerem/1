/**
 * 同一次“创建并启动”的 F0 请求身份。
 *
 * 服务端按 idempotency_key 复用已接受的 run；页面重试必须复用同一个键，
 * 否则“服务端已接受但响应丢失”会再起一次模型调用/扣费。
 * 只在启动确认成功后清除；草稿不生成键。
 */

const memoryKeys = new Map<string, string>();

const PREFIX = 'svquant:factor:f0-start:';

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function key(topicId: string, branchId: string): string {
  return PREFIX + topicId + ':' + branchId;
}

export function getOrCreateStartKey(
  storage: StorageLike,
  topicId: string,
  branchId: string,
  makeKey: () => string,
): string {
  const k = key(topicId, branchId);
  const remembered = memoryKeys.get(k);
  if (remembered) return remembered;
  try {
    const existing = storage.getItem(k);
    if (existing) { memoryKeys.set(k, existing); return existing; }
    const next = makeKey();
    memoryKeys.set(k, next);
    storage.setItem(k, next);
    return next;
  } catch {
    // 存储不可用时在本页面内保留身份；刷新后的恢复仍由服务端在途锁保护。
    const next = memoryKeys.get(k) || makeKey();
    memoryKeys.set(k, next);
    return next;
  }
}

export function clearStartKey(storage: StorageLike, topicId: string, branchId: string): void {
  memoryKeys.delete(key(topicId, branchId));
  try {
    storage.removeItem(key(topicId, branchId));
  } catch {
    // 清理失败不影响已确认的启动。
  }
}
