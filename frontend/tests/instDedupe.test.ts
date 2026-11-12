import assert from "node:assert/strict";
import test from "node:test";
import { dedupeBy, latestByKey } from "../src/lib/instDedupe.ts";

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

test("latestByKey keeps the newest row per stock and breaks timestamp ties by id", () => {
  const rows = [
    { id: 10, symbol: "600519.SH", updated_at: "2026-11-01T10:00:00", flow: "buy" },
    { id: 12, symbol: "600519.SH", updated_at: "2026-11-01T10:00:00", flow: "exit" },
    { id: 11, symbol: "000001.SZ", updated_at: "2026-11-02T09:00:00", flow: "buy" },
  ];
  const picked = latestByKey(
    rows,
    (x) => x.symbol,
    (x) => `${x.updated_at}|${String(x.id).padStart(12, "0")}`,
  );
  assert.deepEqual(picked.map((x) => x.id), [12, 11]);
});

test("latestByKey drops null keys and tolerates empty input", () => {
  assert.deepEqual(
    latestByKey([{ id: 1, symbol: null }, { id: 2, symbol: "000001.SZ" }], (x) => x.symbol, (x) => x.id),
    [{ id: 2, symbol: "000001.SZ" }],
  );
  assert.deepEqual(latestByKey(null, (x: { id: number }) => x.id, (x: { id: number }) => x.id), []);
});
