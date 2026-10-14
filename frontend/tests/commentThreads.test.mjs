import assert from "node:assert/strict";
import test from "node:test";
import { groupCommentThreads } from "../src/components/community/commentThreads.ts";

const comment = (id, parent_id = null, extra = {}) => ({
  id, parent_id, post_id: 16, body: `comment ${id}`,
  created_at: "2026-07-22T10:00:00+08:00",
  author: { id, username: `user${id}` }, ...extra,
});

function visibleIds(grouped) {
  return grouped.roots.flatMap((root) => [
    root.id, ...(grouped.repliesByRoot.get(root.id) || []).map((item) => item.id),
  ]).sort((a, b) => a - b);
}

test("FT-003: all 17 comments are reachable, including legacy reply 8 -> 7 -> 5", () => {
  // Relationships captured from post 16; no account details or real comment text.
  const rows = [[5, null], [6, null], [18, 17], [7, 5], [8, 7],
    [9, null], [10, 5], [11, 6], [12, 5], [13, 5], [14, null],
    [15, 9], [16, null], [17, null], [19, 16], [35, null], [37, null]];
  const input = rows.map(([id, parent]) => comment(id, parent));
  const before = structuredClone(input);
  const grouped = groupCommentThreads(input);
  assert.equal(grouped.roots.length, 8);
  assert.equal(grouped.repliesByRoot.get(5).length, 5);
  assert.deepEqual(visibleIds(grouped), input.map((c) => c.id).sort((a, b) => a - b));
  assert.equal(grouped.repliesByRoot.get(5).find((c) => c.id === 8).reply_to.username, "user7");
  assert.deepEqual(input, before, "grouping must not rewrite stored parent IDs");
});

test("modern flat replies keep their explicit reply target and vote/time ordering", () => {
  const target = { id: 3, username: "explicit-target" };
  const grouped = groupCommentThreads([
    comment(1), comment(2, 1, { like_count: 1 }),
    comment(3, 1, { like_count: 3, reply_to: target }),
    comment(4, 1, { like_count: 3, created_at: "2026-07-21T10:00:00+08:00" }),
  ]);
  assert.deepEqual(grouped.repliesByRoot.get(1).map((c) => c.id), [4, 3, 2]);
  assert.deepEqual(grouped.repliesByRoot.get(1)[1].reply_to, target);
});

test("missing parents and malformed cycles never hide or duplicate available comments", () => {
  const input = [comment(1, 99), comment(2, 1), comment(3, 4), comment(4, 3), comment(5, 5)];
  for (const rows of [input, [...input].reverse()]) {
    const grouped = groupCommentThreads(rows);
    assert.deepEqual(visibleIds(grouped), [1, 2, 3, 4, 5]);
    assert.deepEqual(grouped.roots.map((c) => c.id).sort(), [1, 3, 5]);
  }
});

test("deep unordered replies resolve without recursion", () => {
  const input = Array.from({ length: 10000 }, (_, i) => comment(i + 1, i || null)).reverse();
  const grouped = groupCommentThreads(input);
  assert.equal(grouped.roots.length, 1);
  assert.equal(grouped.roots[0].id, 1);
  assert.equal(grouped.repliesByRoot.get(1).length, 9999);
  assert.equal(new Set(visibleIds(grouped)).size, 10000);
});

test("empty input and cross-post parent references", () => {
  assert.deepEqual(visibleIds(groupCommentThreads([])), []);
  const grouped = groupCommentThreads([comment(1), comment(2, 1, { post_id: 99 })]);
  assert.equal(grouped.roots.length, 2);
  assert.equal(grouped.roots.find((c) => c.id === 2).reply_to, undefined);
});
