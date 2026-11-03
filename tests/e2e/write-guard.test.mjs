import assert from "node:assert/strict";
import test from "node:test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

test("默认（未开人工开关）只读，不报错", () => {
  assert.deepEqual(evaluateWriteGuard(), { enabled: false, fatal: null, dbName: null });
  assert.deepEqual(evaluateWriteGuard({ allowWrite: false }), {
    enabled: false,
    fatal: null,
    dbName: null,
  });
});

test("服务端报生产库 svquant → fatal", () => {
  const out = evaluateWriteGuard({
    allowWrite: true,
    guardResponse: { db_name: "svquant", writable: false },
  });
  assert.equal(out.enabled, false);
  assert.equal(out.dbName, "svquant");
  assert.match(out.fatal, /不是独立测试库/);
});

test("服务端报 svquant 但谎称 writable → 仍 fatal", () => {
  const out = evaluateWriteGuard({
    allowWrite: true,
    guardResponse: { db_name: "svquant", writable: true },
  });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /不是独立测试库/);
});

test("服务端报 svquant_test → enabled", () => {
  assert.deepEqual(
    evaluateWriteGuard({
      allowWrite: true,
      guardResponse: { db_name: "svquant_test", writable: true },
    }),
    { enabled: true, fatal: null, dbName: "svquant_test" },
  );
});

test("服务端报 *_e2e 库 → enabled", () => {
  assert.equal(
    evaluateWriteGuard({
      allowWrite: true,
      guardResponse: { db_name: "inst_e2e_20261103", writable: true },
    }).enabled,
    true,
  );
});

test("guard 请求失败（null）→ fatal", () => {
  const out = evaluateWriteGuard({ allowWrite: true, guardResponse: null });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /端点不可达/);
});

test("guard 返回 HTTP 错误 → fatal", () => {
  const out = evaluateWriteGuard({
    allowWrite: true,
    guardResponse: { error: "HTTP 500" },
  });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /HTTP 500/);
});

test("guard 缺失 db_name → fatal", () => {
  const out = evaluateWriteGuard({
    allowWrite: true,
    guardResponse: { writable: true },
  });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /未返回 db_name/);
});

test("服务端判定不可写 → fatal", () => {
  const out = evaluateWriteGuard({
    allowWrite: true,
    guardResponse: { db_name: "svquant_test", writable: false },
  });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /不可写/);
});

test("INST_E2E_EXPECT_DB 不一致 → fatal；一致 → enabled", () => {
  const mismatch = evaluateWriteGuard({
    allowWrite: true,
    guardResponse: { db_name: "svquant_test", writable: true },
    expectDb: "svquant_e2e",
  });
  assert.equal(mismatch.enabled, false);
  assert.match(mismatch.fatal, /不一致/);

  assert.equal(
    evaluateWriteGuard({
      allowWrite: true,
      guardResponse: { db_name: "svquant_test", writable: true },
      expectDb: "svquant_test",
    }).enabled,
    true,
  );
});
