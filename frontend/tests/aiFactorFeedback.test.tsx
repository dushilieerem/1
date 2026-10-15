import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { cleanup, render } from "@testing-library/react";
import { factorPromptError, factorRejectionMessage } from "../src/lib/aiFactorFeedback";
import { AiFactorExplanation } from "../src/components/AiFactorExplanation";

afterEach(cleanup);

test("空白、简短回复及纯标点要求补充需求，合理公式不会被拦截", () => {
  for (const prompt of ["", "   \n ", "好", "你好！", "！！！？？？？？？", "😀😀😀😀😀😀"]) {
    assert.match(factorPromptError(prompt)!, /补充/);
  }
  for (const prompt of ["生成20日动量因子", "close / close.shift(20) - 1", "14日RSI"]) {
    assert.equal(factorPromptError(prompt), null);
  }
  assert.match(factorPromptError("中".repeat(2001))!, /2000/);
});

test("代码被拒提供处理方向，不把Raise直接断言为平台缺少数据", () => {
  const message = factorRejectionMessage(["不允许的代码结构：Raise"]);
  assert.match(message, /确认/);
  assert.doesNotMatch(message, /不支持逐笔|平台没有/);
  assert.match(factorRejectionMessage(["只允许调用白名单中的面板方法"]), /暂时无法送检测/);
  assert.match(factorRejectionMessage([]), /重新生成/);
});

test("说明展示服务返回的计算假设与注意事项，缺失说明时不捏造数据规则", () => {
  const draft = { factor_name: "vol", factor_code: "code", description: "20日波动率", used_fields: [], used_library_methods: [], assumptions: ["至少21个收盘价观察值"], warnings: ["分母为0时保留空值"] };
  const view = render(<AiFactorExplanation draft={draft} />);
  assert.ok(view.getByText("至少21个收盘价观察值"));
  assert.ok(view.getByText("分母为0时保留空值"));
  view.rerender(<AiFactorExplanation draft={{ ...draft, description: "", assumptions: [], warnings: [] }} />);
  assert.ok(view.getByText(/未提供因子说明/));
  assert.equal(view.queryByText("至少21个收盘价观察值"), null);
});
