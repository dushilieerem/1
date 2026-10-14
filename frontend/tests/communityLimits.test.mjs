import assert from "node:assert/strict";
import test from "node:test";
import { contentLength, lengthError, POST_BODY_LIMIT, COMMENT_LIMIT, REPORT_DETAIL_LIMIT } from "../src/lib/communityLimits.ts";

for (const limit of [POST_BODY_LIMIT, COMMENT_LIMIT, REPORT_DETAIL_LIMIT]) {
  test(`Unicode and boundary validation at ${limit}`, () => {
    for (const char of ["中", "a", "😀"]) {
      const input = `  ${char.repeat(limit)}\n`;
      assert.equal(contentLength(input), limit);
      assert.equal(lengthError(input, limit, "内容"), null);
      assert.match(lengthError(char.repeat(limit + 1), limit, "内容"), /已超出 1 字符/);
    }
    assert.equal(contentLength(" \n\t"), 0);
  });
}
