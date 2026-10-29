"""AI 策略转写（聚宽 → SVQuant）的廉价输入校验。

核心能力判断在 ResearchEngine；本层只挡明显无效的请求，避免把空代码、
超大文本或结构错误的上下文转发给计算服务。
"""

from __future__ import annotations

MAX_CODE_CHARS = 200_000


def strategy_transcription_error(body: object) -> str | None:
    if not isinstance(body, dict):
        return "请求体必须是 JSON 对象"
    code = body.get("code")
    if not isinstance(code, str):
        return "请粘贴聚宽策略代码"
    text = code.strip()
    if not text:
        return "请粘贴聚宽策略代码"
    if len(text) > MAX_CODE_CHARS:
        return f"策略代码不能超过 {MAX_CODE_CHARS:,} 字符，请拆分后再转写"
    context = body.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, dict):
        return "context 必须是 JSON 对象"
    accepted = context.get("accepted_degradations", [])
    if not isinstance(accepted, list) or any(not isinstance(item, str) for item in accepted):
        return "accepted_degradations 必须是字符串数组"
    report_only = context.get("report_only", False)
    if not isinstance(report_only, bool):
        return "report_only 必须是布尔值"
    return None
