import assert from "node:assert/strict";
import { test } from "node:test";
import { draftNewerThan } from "../src/lib/autosave.ts";

test("draftNewerThan compares timestamps", () => {
  assert.equal(
    draftNewerThan({ v: 1, savedAt: "2026-10-31T10:00:00Z", data: {} }, "2026-10-31T09:00:00Z"),
    true,
  );
  assert.equal(
    draftNewerThan({ v: 1, savedAt: "2026-10-31T08:00:00Z", data: {} }, "2026-10-31T09:00:00Z"),
    false,
  );
  assert.equal(draftNewerThan(null), false);
  assert.equal(draftNewerThan({ v: 1, savedAt: "bad", data: {} }, "bad"), true);
});
