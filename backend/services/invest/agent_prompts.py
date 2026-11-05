# -*- coding: utf-8 -*-
"""H5 AI Agent 提示词注册表与用户级覆盖。

- 任务身份仍以 ``ai.router`` 的 TaskSpec.task_id 为准；
- 这里只维护 H5 可用 Agent 的展示名、默认系统提示词和是否允许用户编辑；
- 用户覆盖落 PostgreSQL ``invest_ai_agent_prompt``，按 user_id 隔离；
- 生成缓存键会包含最终提示词，修改提示词后自然生成新缓存。
"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn

RED_LINE = (
    "合规红线：不提供买卖点、目标价、涨跌预测、仓位指令、收益承诺；"
    "不自动交易、不代客理财。若用户要求上述内容，改为说明风险与可查看的数据。"
)

CARD_SYSTEM = (
    "你是 SVQuant Invest 的数据解读助手。只使用用户输入 JSON 中的数据，不得补造任何数字或事实；"
    "数据缺失时明确写“数据缺失/待补充”。只输出 JSON，不要 markdown。"
    '结构：{"summary":"一句话结论","sections":[],'
    '"disclaimer":"AI 生成 · 非投资建议","meta":{"dataSource":"..."}}。'
    "summary 最多 50 个汉字，直击要害；sections 必须为空数组，不要展开长文。"
    "只描述事实、口径与风险，不写买卖建议、目标价、涨跌预测或收益承诺。"
    + RED_LINE
)

PORTFOLIO_DEEP_SYSTEM = (
    "你是 SVQuant Invest 的组合风险解读助手。只依据输入 JSON 中的组合快照、体检、归因、"
    "穿透、压力测试与成本数据作答；不得补造数字。只输出 JSON，不要 markdown。"
    '结构：{"summary":"一句话结论","sections":[],'
    '"disclaimer":"AI 生成 · 非投资建议","meta":{"dataSource":"组合体检 + 穿透 + 压力测试"}}。'
    "summary 最多 50 个汉字，只讲最需要先看的一件事；sections 必须为空数组。"
    "只描述事实、口径与风险，不写买卖建议、目标价、涨跌预测、仓位指令或收益承诺。"
    + RED_LINE
)

ALLOCATION_SYSTEM = (
    "你是配置与定投解释助手。只依据输入的期限、风险偏好、组合偏离、风险测评与政策阈值作答；"
    "不推荐具体标的，不给买入金额、目标价、收益承诺或调仓指令。只输出 JSON 卡片："
    '{"summary":"不超过50个汉字的一句话","sections":[],"disclaimer":"AI 生成 · 非投资建议",'
    '"meta":{"dataSource":"组合体检 + 风险测评"}}。sections 必须为空数组。'
)

BACKTEST_SYSTEM = (
    "你是回测解读助手。只依据输入的指标、净值曲线与交易摘要解释这段区间发生了什么；"
    "不给未来预测、买卖建议、目标价或收益承诺。只输出 JSON 卡片："
    '{"summary":"不超过50个汉字的一句话","sections":[],"disclaimer":"历史口径 · 非真实收益 · 非投资建议",'
    '"meta":{"dataSource":"回测结果缓存"}}。sections 必须为空数组。'
)

QUANT_COMMENTARY_SYSTEM = (
    "你是量化结果解释助手。只依据输入 JSON 中服务端算好的指标作答，不做任何运算，不编造数值。"
    '只输出 JSON：{"summary":"不超过50个汉字的一句话","sections":[],'
    '"disclaimer":"AI 生成 · 非投资建议","meta":{"dataSource":"回测/模拟盘结果"}}。'
    "sections 必须为空数组；只讲最关键的收益或风险来源；禁止建议、预测、目标价、收益承诺。"
)

PAPER_COMMENTARY_SYSTEM = (
    "你是模拟盘解释助手。只依据输入 JSON 中的模拟盘、回测与持仓数据解释偏离和风险，"
    "不编造数值、不给操作建议。只输出 JSON："
    '{"summary":"不超过50个汉字的一句话","sections":[],"disclaimer":"AI 生成 · 非投资建议",'
    '"meta":{"dataSource":"模拟盘记账数据"}}。sections 必须为空数组。'
)

INTENT_SYSTEM = (
    "只输出 JSON：{\"intent\":\"...\",\"slots\":{}}。意图枚举：brief/review/stock/portfolio/"
    "debate/compare/announcement/condition/allocation/sip/glossary/compliance_block/chat。"
    "缺槽位放 need_clarify。"
)

AGENTS: tuple[dict[str, Any], ...] = (
    {"task_id": "invest.stock", "name": "个股解读", "name_en": "Stock read", "description": "解释个股行情、财务、估值与风险", "description_en": "Quote, financials, valuation and risks", "default_prompt": CARD_SYSTEM, "editable": True},
    {"task_id": "invest.portfolio", "name": "组合解读", "name_en": "Portfolio read", "description": "解释组合风险、归因与配置偏离", "description_en": "Risk, attribution and allocation drift", "default_prompt": PORTFOLIO_DEEP_SYSTEM, "editable": True},
    {"task_id": "invest.announcement", "name": "公告解读", "name_en": "Filing summary", "description": "解释公告/资讯标题的事实与风险", "description_en": "Facts and risks in a filing or headline", "default_prompt": CARD_SYSTEM, "editable": True},
    {"task_id": "invest.compare", "name": "标的对比", "name_en": "Compare", "description": "同口径对比两个标的", "description_en": "Compare two symbols on the same basis", "default_prompt": CARD_SYSTEM, "editable": True},
    {"task_id": "invest.daily", "name": "每日复盘", "name_en": "Daily review", "description": "解释今日自选、组合与市场变化", "description_en": "Today's watchlist, portfolio and market moves", "default_prompt": CARD_SYSTEM, "editable": True},
    {"task_id": "invest.condition", "name": "条件选股", "name_en": "Screening", "description": "解释条件选股结果", "description_en": "Explain screening results", "default_prompt": CARD_SYSTEM, "editable": True},
    {"task_id": "invest.allocation", "name": "配置与定投", "name_en": "Allocation / DCA", "description": "解释风险预算与配置偏离", "description_en": "Risk budget and allocation drift", "default_prompt": ALLOCATION_SYSTEM, "editable": True},
    {"task_id": "invest.backtest", "name": "回测点评", "name_en": "Backtest review", "description": "解释回测收益与风险来源", "description_en": "Return and risk sources in a backtest", "default_prompt": BACKTEST_SYSTEM, "editable": True},
    {"task_id": "invest.quant", "name": "量化点评", "name_en": "Quant review", "description": "解释因子、回测与模拟盘结果", "description_en": "Factors, backtests and paper results", "default_prompt": QUANT_COMMENTARY_SYSTEM, "editable": True},
    {"task_id": "invest.paper", "name": "模拟盘点评", "name_en": "Paper review", "description": "解释模拟盘偏离、集中度与一致性", "description_en": "Deviation, concentration and consistency", "default_prompt": PAPER_COMMENTARY_SYSTEM, "editable": True},
    {"task_id": "invest.intent", "name": "意图识别", "name_en": "Intent routing", "description": "结构化解析，修改可能破坏路由", "description_en": "Structured parser; edits may break routing", "default_prompt": INTENT_SYSTEM, "editable": False},
)
AGENT_BY_ID = {a["task_id"]: a for a in AGENTS}


def ensure_agent_prompt_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invest_ai_agent_prompt (
              user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              task_id TEXT NOT NULL,
              prompt TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
              PRIMARY KEY (user_id, task_id)
            )
            """
        )


def get_override(user_id: int | None, task_id: str) -> str | None:
    if not user_id:
        return None
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT prompt FROM invest_ai_agent_prompt WHERE user_id=%s AND task_id=%s",
                (int(user_id), task_id),
            ).fetchone()
        return str(row["prompt"]) if row and row.get("prompt") else None
    except Exception:
        return None


def resolve_prompt(user_id: int | None, task_id: str, fallback: str) -> str:
    agent = AGENT_BY_ID.get(task_id)
    if not agent or not agent.get("editable"):
        return fallback
    return get_override(user_id, task_id) or fallback


def save_prompt(user_id: int, task_id: str, prompt: str) -> dict[str, Any]:
    agent = AGENT_BY_ID.get(task_id)
    if not agent:
        raise ValueError("未知 Agent")
    if not agent.get("editable"):
        raise ValueError("该 Agent 为结构化解析，不支持自定义提示词")
    text = (prompt or "").strip()
    if len(text) > 4000:
        raise ValueError("提示词最多 4000 字")
    with get_conn() as conn:
        if not text:
            conn.execute(
                "DELETE FROM invest_ai_agent_prompt WHERE user_id=%s AND task_id=%s",
                (int(user_id), task_id),
            )
            return {"task_id": task_id, "prompt": agent["default_prompt"], "custom": False}
        conn.execute(
            """
            INSERT INTO invest_ai_agent_prompt (user_id, task_id, prompt, updated_at)
            VALUES (%s, %s, %s, to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'))
            ON CONFLICT (user_id, task_id) DO UPDATE
            SET prompt=EXCLUDED.prompt, updated_at=EXCLUDED.updated_at
            """,
            (int(user_id), task_id, text),
        )
    return {"task_id": task_id, "prompt": text, "custom": True}


def list_agents(user_id: int) -> dict[str, Any]:
    overrides: dict[str, str] = {}
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT task_id, prompt FROM invest_ai_agent_prompt WHERE user_id=%s",
                (int(user_id),),
            ).fetchall()
        overrides = {str(r["task_id"]): str(r["prompt"]) for r in rows if r.get("prompt")}
    except Exception:
        overrides = {}
    try:
        from ai.router import available_task

        avail = {a["task_id"]: bool(available_task(a["task_id"])) for a in AGENTS}
    except Exception:
        avail = {a["task_id"]: False for a in AGENTS}
    items = []
    for agent in AGENTS:
        custom = overrides.get(agent["task_id"])
        items.append({
            **agent,
            "prompt": custom or agent["default_prompt"],
            "custom_prompt": custom,
            "is_custom": bool(custom),
            "available": avail.get(agent["task_id"], False),
            "can_reset": bool(custom),
        })
    return {"items": items, "count": len(items)}
