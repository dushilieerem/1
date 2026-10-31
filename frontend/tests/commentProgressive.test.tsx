import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CommentThread } from "../src/components/community/CommentThread";
import type { CommunityComment } from "../src/lib/communityApi";

afterEach(cleanup);

function makeComments(n: number): CommunityComment[] {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    post_id: 1,
    body: `评论 ${i + 1}`,
    created_at: "2026-10-31T10:00:00Z",
    author: { id: 1, username: "u", display_name: "用户" },
  }));
}

test("长评论楼分批渲染，点击后加载更多（P2-08）", () => {
  const comments = makeComments(65);
  const view = render(
    <MemoryRouter>
      <CommentThread
        comments={comments}
        canInteract={false}
        onNeedLogin={() => {}}
        onCommentsChange={() => {}}
        onSubmitComment={async () => {}}
        onReportComment={() => {}}
      />
    </MemoryRouter>,
  );
  assert.equal(view.container.querySelectorAll('[id^="comment-"]').length, 30);
  const more = view.getByText(/显示更多评论/);
  fireEvent.click(more);
  assert.equal(view.container.querySelectorAll('[id^="comment-"]').length, 60);
});
