import assert from "node:assert/strict";
import test from "node:test";
import { dedupeBy } from "../src/lib/instDedupe.ts";

test("dedupeBy keeps first occurrence by business key", () => {
  const rows = [
    { id: 1, symbol: "600519.SH" },
    { id: 2, symbol: "600519.SH" },
    { id: 3, symbol: "000001.SZ" },
  ];
  assert.deepEqual(dedupeBy(rows, (x) => x.symbol).map((x) => x.id), [1, 3]);
});

test("dedupeBy drops null keys and tolerates empty input", () => {
  assert.deepEqual(dedupeBy([{ id: null }, { id: 1 }], (x) => x.id), [{ id: 1 }]);
  assert.deepEqual(dedupeBy(null, (x: { id: number }) => x.id), []);
});
