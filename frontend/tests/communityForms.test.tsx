import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ReportDialog } from "../src/components/community/ReportDialog";
import { CommentThread } from "../src/components/community/CommentThread";
import { postBodyText } from "../src/lib/communityBodyText";
import { contentLength, lengthError } from "../src/lib/communityLimits";

afterEach(cleanup);

test("富文本正文忽略标签和图片编码，按可见 Unicode 文字限制", () => {
  const image = `<img src="data:image/png;base64,${"a".repeat(30000)}">`;
  assert.equal(contentLength(postBodyText(`<p>${"😀".repeat(20000)}</p>${image}`)), 20000);
  assert.ok(lengthError(postBodyText(`<p>${"中".repeat(20001)}</p>${image}`), 20000, "正文"));
  assert.equal(postBodyText("<p>&amp;😀<strong>中</strong></p>"), "&😀中");
  assert.equal(postBodyText("# 标题\n正文"), "# 标题\n正文");
});

test("举报保留 501 字符、阻止下一步，缩短到 500 后完整提交", async () => {
  const sent: any[] = [];
  const view = render(<ReportDialog open targetType="post" onClose={() => {}} onSubmit={async p => { sent.push(p); }} />);
  const input = view.getByPlaceholderText("补充说明（可选）") as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: "😀".repeat(501) } });
  assert.equal(Array.from(input.value).length, 501);
  assert.match(view.container.textContent!, /已超出 1 字符/);
  assert.equal((view.getByText("下一步") as HTMLButtonElement).disabled, true);
  assert.equal(sent.length, 0);
  fireEvent.change(input, { target: { value: "😀".repeat(500) } });
  fireEvent.click(view.getByText("下一步"));
  fireEvent.click(view.getByText("确认提交"));
  await waitFor(() => assert.equal(sent.length, 1));
  assert.equal(sent[0].detail, "😀".repeat(500));
});

test("评论及回复保留超限内容并阻止发送，边界内容完整提交", async () => {
  const sent: any[] = [];
  const comment: any = { id: 5, post_id: 16, body: "原评论", parent_id: null, author: { id: 2, username: "tester" }, created_at: "2026-10-12" };
  const view = render(<MemoryRouter><CommentThread comments={[comment]} canInteract currentUserId={1} onNeedLogin={() => {}} onCommentsChange={() => {}} onSubmitComment={async p => { sent.push(p); }} /></MemoryRouter>);
  let input = view.getByPlaceholderText("写下你的看法…") as HTMLTextAreaElement;
  for (const replying of [false, true]) {
    if (replying) { fireEvent.click(view.getByText("回复", { exact: true })); input = view.getByPlaceholderText("写下回复…") as HTMLTextAreaElement; }
    const label = replying ? "发表回复" : "发表评论";
    fireEvent.change(input, { target: { value: "中".repeat(2001) } });
    assert.equal(input.value.length, 2001);
    assert.equal((view.getByText(label) as HTMLButtonElement).disabled, true);
    fireEvent.submit(input.closest("form")!);
    assert.equal(sent.length, replying ? 1 : 0);
    fireEvent.change(input, { target: { value: "😀".repeat(2000) } });
    fireEvent.click(view.getByText(label));
    await waitFor(() => assert.equal(sent.length, replying ? 2 : 1));
    assert.equal(sent.at(-1).body, "😀".repeat(2000));
    assert.equal(sent.at(-1).parentId, replying ? 5 : null);
    await waitFor(() => assert.equal(input.value, ""));
  }
});
