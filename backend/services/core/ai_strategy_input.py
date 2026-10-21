"""Cheap request checks before invoking the external generation service."""


def strategy_prompt_error(prompt: object) -> str | None:
    if not isinstance(prompt, str):
        return "请提供文字形式的策略需求"
    text = prompt.strip()
    if len(text) > 2000:
        return "策略需求不能超过 2000 字符"
    if sum(char.isalpha() or char.isdecimal() for char in text) < 6:
        return "请补充策略的选股逻辑、调仓周期或权重方式，例如：每20日调仓，买入过去20日动量最高的30只股票，等权持有。"
    return None
