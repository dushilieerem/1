"""Cheap request checks before invoking the external generation service."""


def factor_prompt_error(prompt: object, *, max_chars: int = 2000) -> str | None:
    if not isinstance(prompt, str):
        return "请提供文字形式的因子需求"
    text = prompt.strip()
    if len(text) > max_chars:
        return f"因子需求不能超过 {max_chars} 字符"
    if sum(char.isalpha() or char.isdecimal() for char in text) < 6:
        return "请补充因子使用的数据、计算逻辑或周期，例如：根据过去20日收盘价计算收益率。"
    return None
