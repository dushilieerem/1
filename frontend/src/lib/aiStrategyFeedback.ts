/** Basic input guidance; semantic/data-capability validation remains in ResearchEngine. */
export function strategyPromptError(prompt: string): string | null {
  const text = prompt.trim();
  if (Array.from(text).length > 2000) return "策略需求不能超过 2000 字符";
  const meaningful = text.match(/[\p{L}\p{Nd}]/gu) || [];
  if (meaningful.length < 6) {
    return "请补充策略的选股逻辑、调仓周期或权重方式，例如：每20日调仓，买入过去20日动量最高的30只股票，等权持有。";
  }
  return null;
}

export function strategyRejectionMessage(errors: string[]): string {
  const requestReason = errors.find((error) => /^(需求暂不支持|请补充策略需求)：/.test(error));
  if (requestReason) return requestReason;
  if (errors.some((error) => /Raise/.test(error))) {
    return "未能生成可用策略。请确认需求所需的数据字段是否受支持，或补充选股逻辑与调仓规则。具体支持的数据范围请联系管理员确认。";
  }
  return "生成的代码未通过平台可执行性校验，暂时无法送研究。可以重新生成；若仍失败，请将需求和下方错误详情反馈给管理员。";
}
