import assert from 'node:assert/strict';
import test from 'node:test';
import { clearStartKey, getOrCreateStartKey } from '../src/lib/factorStartRequest.ts';

function memoryStorage(): Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> {
  const data = new Map<string, string>();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

test('响应丢失后重试复用同一个 F0 幂等键', async () => {
  const storage = memoryStorage();
  const server = new Map<string, string>();
  let runs = 0;
  const start = async (key: string) => {
    if (!server.has(key)) {
      runs += 1;
      server.set(key, 'run-1');
    }
    // 第一次请求服务端已写入，但客户端响应丢失。
    throw new Error('response lost');
  };
  const key1 = getOrCreateStartKey(storage, 't1', 'b1', () => 'k-1');
  await assert.rejects(() => start(key1));
  const key2 = getOrCreateStartKey(storage, 't1', 'b1', () => 'k-2');
  assert.equal(key1, key2);
  assert.equal(runs, 1, '同一逻辑启动只能产生一个服务端 run');
  assert.equal(server.get(key2), 'run-1');
});

test('确认启动成功后清除，下一次人工启动使用新键', () => {
  const storage = memoryStorage();
  const key1 = getOrCreateStartKey(storage, 't1', 'b1', () => 'k-1');
  clearStartKey(storage, 't1', 'b1');
  const key2 = getOrCreateStartKey(storage, 't1', 'b1', () => 'k-2');
  assert.notEqual(key1, key2);
});

test('草稿路径不生成启动键', () => {
  const storage = memoryStorage();
  assert.equal(storage.getItem('svquant:factor:f0-start:t1:b1'), null);
});


test('浏览器存储不可用时同一页面仍复用启动身份',()=>{
 const unavailable={getItem(){throw Error('disabled')},setItem(){throw Error('disabled')},removeItem(){throw Error('disabled')}};
 let i=0;const first=getOrCreateStartKey(unavailable,'no-storage-topic','branch',()=>String(++i));
 assert.equal(getOrCreateStartKey(unavailable,'no-storage-topic','branch',()=>String(++i)),first);
 clearStartKey(unavailable,'no-storage-topic','branch');
 assert.notEqual(getOrCreateStartKey(unavailable,'no-storage-topic','branch',()=>String(++i)),first);
});
