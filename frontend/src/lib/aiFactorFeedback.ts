/** Basic input guidance; semantic/data-capability validation remains in ResearchEngine. */
export function factorPromptError(prompt: string): string | null {
  const text = prompt.trim();
  if (Array.from(text).length > 2000) return "因子需求不能超过 2000 字符";
  const meaningful = text.match(/[\p{L}\p{Nd}]/gu) || [];
  if (meaningful.length < 6) {
    return "请补充因子使用的数据、计算逻辑或周期，例如：根据过去20日收盘价计算收益率。";
  }
  return null;
}

export function factorRejectionMessage(errors: string[]): string {
  if (errors.some((error) => /Raise/.test(error))) {
    return "未能生成可用因子。请确认需求所需的数据字段是否受支持，或补充数据与计算逻辑。具体支持的数据范围请联系管理员确认。";
  }
  return "生成的代码未通过平台可执行性校验，暂时无法送检测。可以重新生成；若仍失败，请将需求和下方错误详情反馈给管理员。";
}
