import assert from "node:assert/strict";
import test from "node:test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

test("默认（未显式允许）只读，不报错", () => {
  assert.deepEqual(evaluateWriteGuard({}), { enabled: false, fatal: null });
});

test("只设 ALLOW_WRITE 但没有安全库标记时 fail fast", () => {
  const out = evaluateWriteGuard({ INST_E2E_ALLOW_WRITE: "1" });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /INST_E2E_DB=safe/);
});

test("生产库名 svquant 即使设置 ALLOW_WRITE 也拒绝", () => {
  const out = evaluateWriteGuard({
    INST_E2E_ALLOW_WRITE: "1",
    INST_E2E_DB: "svquant",
  });
  assert.equal(out.enabled, false);
  assert.match(out.fatal, /禁止指向生产库/);
});

test("显式 INST_E2E_DB=safe 才允许写库", () => {
  assert.deepEqual(
    evaluateWriteGuard({ INST_E2E_ALLOW_WRITE: "1", INST_E2E_DB: "safe" }),
    { enabled: true, fatal: null },
  );
});

test("库名含 _test / _e2e 视为独立测试库", () => {
  for (const tag of ["svquant_test", "svquant_e2e", "inst_e2e_20261103"]) {
    assert.deepEqual(
      evaluateWriteGuard({ INST_E2E_ALLOW_WRITE: "1", INST_E2E_DB: tag }),
      { enabled: true, fatal: null },
      tag,
    );
  }
});

test("只给安全库标记但未显式允许时仍保持只读", () => {
  assert.deepEqual(evaluateWriteGuard({ INST_E2E_DB: "safe" }), {
    enabled: false,
    fatal: null,
  });
});
