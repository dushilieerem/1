import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { cleanup, render } from "@testing-library/react";
import { strategyPromptError, strategyRejectionMessage } from "../src/lib/aiStrategyFeedback";
import { AiStrategyExplanation } from "../src/components/AiStrategyExplanation";

afterEach(cleanup);

test("空白、简短回复及纯标点要求补充需求，合理策略描述不会被拦截", () => {
  for (const prompt of ["", "   \n ", "好", "你好！", "！！！？？？？？？", "😀😀😀😀😀😀"]) {
    assert.match(strategyPromptError(prompt)!, /补充/);
  }
  for (const prompt of ["生成20日动量策略", "每5日调仓买入RSI最低10只", "动量Top30等权"]) {
    assert.equal(strategyPromptError(prompt), null);
  }
  assert.match(strategyPromptError("中".repeat(2001))!, /2000/);
});

test("代码被拒提供处理方向，不把Raise直接断言为平台缺少数据", () => {
  const message = strategyRejectionMessage(["不允许的代码结构：Raise"]);
  assert.match(message, /确认/);
  assert.doesNotMatch(message, /不支持逐笔|平台没有/);
  assert.match(strategyRejectionMessage(["只允许调用白名单中的面板方法"]), /暂时无法送研究/);
  assert.match(strategyRejectionMessage([]), /重新生成/);
});

test("服务明确返回能力边界或补充需求时，页面直接展示原因", () => {
  for (const message of ["需求暂不支持：只有日频价量数据，没有逐笔撤单字段", "请补充策略需求：请说明调仓周期与持仓方式"]) {
    assert.equal(strategyRejectionMessage([message]), message);
  }
});

test("说明展示服务返回的选股假设与注意事项，缺失说明时不捏造数据规则", () => {
  const draft = { strategy_name: "mom", strategy_code: "code", description: "20日动量Top30", used_fields: [], assumptions: ["至少21个收盘价观察值"], warnings: ["停牌期间不顺延调仓"] };
  const view = render(<AiStrategyExplanation draft={draft} />);
  assert.ok(view.getByText("至少21个收盘价观察值"));
  assert.ok(view.getByText("停牌期间不顺延调仓"));
  view.rerender(<AiStrategyExplanation draft={{ ...draft, description: "", assumptions: [], warnings: [] }} />);
  assert.ok(view.getByText(/未提供策略说明/));
  assert.equal(view.queryByText("至少21个收盘价观察值"), null);
});
