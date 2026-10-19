import assert from "node:assert/strict";
import test from "node:test";
import { comparePanelMetric } from "../src/lib/factorPanelSort";
import { factorNameError } from "../src/lib/factorName";

test("指标升降序均将缺失和非有限值放到最后，0仍参与正常排序", () => {
  const rows = [null, 0, -2, 3, undefined, NaN, Infinity];
  for (const direction of ["asc", "desc"] as const) {
    const sorted = [...rows].sort((a, b) => comparePanelMetric(a, b, direction));
    assert.deepEqual(sorted.slice(0, 3), direction === "asc" ? [-2, 0, 3] : [3, 0, -2]);
    assert.ok(sorted.slice(3).every(v => typeof v !== "number" || !Number.isFinite(v)));
  }
});

test("新建、改名及AI送检使用的因子名规则拒绝Python关键字", () => {
  for (const value of ["for", "class", "True", "None", "await", "return"]) {
    assert.match(factorNameError(value)!, /关键字/);
  }
  for (const value of ["my_factor", "_momentum20", "For", "match"]) assert.equal(factorNameError(value), null);
  for (const value of ["", "20day", "a-b", "中文", "bad\nname"]) assert.ok(factorNameError(value));
});
