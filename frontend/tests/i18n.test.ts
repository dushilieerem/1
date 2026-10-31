import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeLocale, t } from "../src/lib/i18n.ts";

test("normalizeLocale defaults to zh and recognizes en", () => {
  assert.equal(normalizeLocale("en-US"), "en");
  assert.equal(normalizeLocale("EN"), "en");
  assert.equal(normalizeLocale("zh-CN"), "zh");
  assert.equal(normalizeLocale(null), "zh");
});

test("t picks the right language", () => {
  assert.equal(t("保存", "Save", "zh"), "保存");
  assert.equal(t("保存", "Save", "en"), "Save");
});
