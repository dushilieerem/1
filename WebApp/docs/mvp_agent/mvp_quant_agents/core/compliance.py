"""合规闸：敏感度分类 + 脱敏 + 路由决策。

L3（因子公式/仓位/PnL/权重/原始数据/标的代码）一律禁止出网；
命中 L3 时返回 blocked，由调用方改走本地模型或先脱敏。
逻辑与项目根目录 router_middleware.py 同源，此处内聚进包便于 Agent 直接 import。
"""
from __future__ import annotations
import re

# L3 命中模式：任一命中即视为含专有 alpha，禁止出网
L3_PATTERNS = {
    "factor_formula": r"(?i)(factor|alpha|因子|alpha表达式).{0,40}?(\=|formula|公式|:=)",
    "positions":      r"(?i)(position|持仓|仓位).{0,30}?\d",
    "pnl":            r"(?i)(pnl|盈亏|收益曲线|return).{0,20}?\d",
    "model_weights":  r"(?i)(weight|权重|参数|model).{0,20}?(模型|权重|参数)",
    "raw_data":       r"(?i)(raw|原始数据|原始行情|dataset).{0,20}?",
    "tickers":        r"\b(60\d{4}|00\d{4}|30\d{4}|68\d{4})\b",  # A 股 6 位代码
}
L2_HINTS = ["内部", "internal", "指标", "结论", "摘要", "summary"]


def classify(text: str):
    """返回 (level, hits)。level ∈ {L1, L2, L3}。"""
    hits = [k for k, p in L3_PATTERNS.items() if re.search(p, text or "")]
    if hits:
        return "L3", hits
    if any(w in (text or "") for w in L2_HINTS):
        return "L2", []
    return "L1", []


def scrub(text: str) -> str:
    """L3 字段脱敏：用代号/聚合描述替换，避免真实 alpha 出网。"""
    out = text
    out = re.sub(r"\b(60\d{4}|00\d{4}|30\d{4}|68\d{4})\b", "[标的#]", out)
    out = re.sub(r"(?i)(factor|alpha|因子).{0,40}?(\=|formula|公式|:=).*",
                 "[因子公式#已脱敏]", out)
    out = re.sub(r"(?i)(position|持仓|仓位).{0,30}?\d+", "[仓位#]", out)
    out = re.sub(r"(?i)(pnl|盈亏|收益曲线).{0,20}?\d+", "[pnl#]", out)
    return out


def route(text: str, enforce: bool = True) -> dict:
    """对即将出网的内容做路由决策。"""
    level, hits = classify(text)
    if level == "L3":
        if enforce:
            return {"decision": "blocked", "level": "L3", "hits": hits,
                    "reason": "含专有 alpha，禁止出网；请改走本地模型或先脱敏"}
        return {"decision": "scrubbed", "level": "L3",
                "text": scrub(text), "hits": hits}
    return {"decision": "external_ok", "level": level}
