# -*- coding: utf-8 -*-
"""手机端 Invest AI 任务（ADR-037 TaskSpec）。

合规基线（与 `SVQuant-AI-Agent能力清单交付文档.md` 一致）：
- 只给信息、解释与风险，不给买卖点、目标价、涨跌预测、仓位指令、收益承诺。
- 不自动交易、不代客理财；命中红线走固定话术，不进入模型自由发挥。
- 输出必须带口径（dataSource）与非投资建议声明，由前端卡片协议渲染。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest, TaskSpec, register

PROMPT_VERSION = "invest-v1"

RED_LINE = (
    "合规红线：不提供买卖点、目标价、涨跌预测、仓位指令、收益承诺；"
    "不自动交易、不代客理财。若用户要求上述内容，改为说明风险与可查看的数据。"
)


def _strip(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _load(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip(raw))
    except (json.JSONDecodeError, IndexError, ValueError) as exc:
        raise AiBadOutput("Invest AI 返回不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise AiBadOutput("Invest AI 返回不是 JSON 对象")
    return data


def validate_intent(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    intent = str(data.get("intent") or "").strip()
    allowed = {
        "brief",
        "review",
        "stock",
        "portfolio",
        "debate",
        "compare",
        "announcement",
        "condition",
        "allocation",
        "sip",
        "glossary",
        "compliance_block",
        "chat",
    }
    if intent not in allowed:
        raise AiBadOutput("Invest AI 返回了未知意图")
    data["intent"] = intent
    slots = data.get("slots")
    data["slots"] = slots if isinstance(slots, dict) else {}
    return data


def validate_vision(raw: str, request: TaskRequest) -> dict[str, Any]:
    """识图只返回可编辑文字，不返回交易结论。"""
    text = _strip(raw).strip().strip('"').strip("'")
    if not text:
        raise AiBadOutput("识图结果为空")
    return {"text": text[:500]}


def validate_card(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    if not str(data.get("summary") or "").strip():
        raise AiBadOutput("Invest AI 卡片缺少 summary")
    sections = data.get("sections")
    data["sections"] = sections if isinstance(sections, list) else []
    data.setdefault("disclaimer", "AI 生成 · 非投资建议")
    meta = data.get("meta")
    data["meta"] = meta if isinstance(meta, dict) else {}
    data["meta"].setdefault("dataSource", "演示数据")
    return data


_STOCK_DIMENSIONS = (
    ("fundamental", "基本面"),
    ("profitability", "盈利"),
    ("valuation", "估值"),
    ("risk", "风险"),
    ("capital", "资金"),
)


def validate_stock_deep(raw: str, request: TaskRequest) -> dict[str, Any]:
    """个股页五维分析：必须返回 summary + 五个固定维度，缺项直接判定失败。"""
    data = validate_card(raw, request)
    by_key: dict[str, dict[str, Any]] = {}
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        key = str(section.get("key") or "").strip()
        if key not in dict(_STOCK_DIMENSIONS):
            continue
        blocks: list[dict[str, Any]] = []
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "").strip()
            if kind == "paragraph":
                text = str(block.get("text") or "").strip()
                if text:
                    blocks.append({"type": "paragraph", "text": text[:1200]})
            elif kind == "bullets":
                items = [str(x).strip() for x in (block.get("items") or []) if str(x).strip()]
                if items:
                    blocks.append({"type": "bullets", "items": items[:5]})
        body = str(section.get("body") or "").strip()
        if not body:
            body = next((b["text"] for b in blocks if b.get("type") == "paragraph"), "")
        if not body:
            continue
        if not blocks:
            blocks = [{"type": "paragraph", "text": body}]
        items = []
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            k = str(item.get("k") or "").strip()
            v = str(item.get("v") or "").strip()
            if k and v:
                items.append({"k": k, "v": v})
        by_key[key] = {
            "key": key,
            "title": dict(_STOCK_DIMENSIONS)[key],
            "body": body,
            "blocks": blocks,
            "items": items[:2],
        }
    missing = [title for key, title in _STOCK_DIMENSIONS if key not in by_key]
    if missing:
        raise AiBadOutput("个股五维分析缺少：" + "、".join(missing))
    data["sections"] = [by_key[key] for key, _ in _STOCK_DIMENSIONS]
    data["meta"].setdefault("dataSource", "行情 + 财务 + 估值 + 资金流")
    return data


_DIAGNOSIS_SECTIONS = (
    ("company", "一、公司是什么来头"),
    ("performance", "二、最近一期业绩怎么样"),
    ("valuation", "三、当前估值贵不贵"),
    ("capital", "四、资金面什么信号"),
    ("institution", "五、机构怎么看"),
    ("highlights", "六、核心亮点与风险"),
    ("conclusion", "七、综合结论"),
)


def validate_stock_diagnosis(raw: str, request: TaskRequest) -> dict[str, Any]:
    """AI 管家个股诊断：7 个问句式板块，缺项直接失败。"""
    data = validate_card(raw, request)
    by_key: dict[str, dict[str, Any]] = {}
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        key = str(section.get("key") or "").strip()
        if key not in dict(_DIAGNOSIS_SECTIONS):
            continue
        blocks: list[dict[str, Any]] = []
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "").strip()
            if kind == "paragraph":
                text = str(block.get("text") or "").strip()
                if text:
                    blocks.append({"type": "paragraph", "text": text[:1600]})
            elif kind == "bullets":
                items = [str(x).strip() for x in (block.get("items") or []) if str(x).strip()]
                if items:
                    blocks.append({"type": "bullets", "items": items[:6]})
        body = str(section.get("body") or "").strip()
        if not body:
            body = next((b["text"] for b in blocks if b.get("type") == "paragraph"), "")
        if not body:
            continue
        if not blocks:
            blocks = [{"type": "paragraph", "text": body}]
        by_key[key] = {"key": key, "title": dict(_DIAGNOSIS_SECTIONS)[key], "body": body, "blocks": blocks, "items": []}
    missing = [title for key, title in _DIAGNOSIS_SECTIONS if key not in by_key]
    if missing:
        raise AiBadOutput("AI 管家个股诊断缺少：" + "、".join(missing))
    data["sections"] = [by_key[key] for key, _ in _DIAGNOSIS_SECTIONS]
    data["meta"].setdefault("dataSource", "行情 + 财务 + 估值 + 资金流 + 公开资讯")
    return data


INTENT_TASK = register(
    TaskSpec(
        task_id="invest.intent",
        description="Invest 意图路由与槽位抽取",
        temperature=0.1,
        max_tokens=800,
        timeout_sec=60,
        executors=("local",),
        validator=validate_intent,
    )
)

_DAILY_SECTIONS = (
    ("market", "一、大盘概览"),
    ("structure", "二、市场结构"),
    ("portfolio", "三、我的组合"),
    ("moves", "四、关注标的异动"),
    ("why", "五、今天为什么"),
    ("watch", "六、后续盯什么"),
)
_DAILY_REQUIRED = {"market", "structure", "portfolio"}


def validate_daily_review(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = validate_card(raw, request)
    by_key: dict[str, dict[str, Any]] = {}
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        key = str(section.get("key") or "").strip()
        if key not in dict(_DAILY_SECTIONS):
            continue
        blocks: list[dict[str, Any]] = []
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "").strip()
            if kind == "paragraph":
                text = str(block.get("text") or "").strip()
                if text:
                    blocks.append({"type": "paragraph", "text": text[:1200]})
            elif kind == "bullets":
                items = [str(x).strip() for x in (block.get("items") or []) if str(x).strip()]
                if items:
                    blocks.append({"type": "bullets", "items": items[:6]})
        body = str(section.get("body") or "").strip()
        if not body:
            body = next((b["text"] for b in blocks if b.get("type") == "paragraph"), "")
        if not body:
            body = next((str(b["items"][0]) for b in blocks if b.get("type") == "bullets" and b.get("items")), "")
        if not body:
            continue
        if not blocks:
            blocks = [{"type": "paragraph", "text": body}]
        by_key[key] = {"key": key, "title": dict(_DAILY_SECTIONS)[key], "body": body, "blocks": blocks, "items": []}
    missing = [title for key, title in _DAILY_SECTIONS if key in _DAILY_REQUIRED and key not in by_key]
    if missing:
        raise AiBadOutput("今日复盘缺少：" + "、".join(missing))
    data["sections"] = [by_key[key] for key, _ in _DAILY_SECTIONS if key in by_key]
    data["meta"].setdefault("dataSource", "首页 + 组合 + 自选 + 资讯")
    return data


DAILY_TASK = register(
    TaskSpec(
        task_id="invest.daily",
        description="Invest 今日复盘：市场 → 结构 → 组合 → 异动 → 原因 → 跟踪点",
        temperature=0.3,
        max_tokens=6000,
        timeout_sec=180,
        executors=("local",),
        validator=validate_daily_review,
    )
)

STOCK_TASK = register(
    TaskSpec(
        task_id="invest.stock",
        description="Invest AI 管家个股诊断：7 个问句式板块",
        temperature=0.25,
        max_tokens=6500,
        timeout_sec=180,
        executors=("local",),
        validator=validate_stock_diagnosis,
    )
)

STOCK_DEEP_TASK = register(
    TaskSpec(
        task_id="invest.stock_deep",
        description="Invest 个股五维分析：基本面、盈利、估值、风险、资金",
        temperature=0.25,
        max_tokens=5000,
        timeout_sec=180,
        executors=("local",),
        validator=validate_stock_deep,
    )
)

_PORTFOLIO_SECTIONS = (
    ("score", "一、结论与风险分"),
    ("structure", "二、结构风险（越线项）"),
    ("today", "三、今日影响"),
    ("stress", "四、压力测试"),
    ("deviation", "五、目标偏离"),
    ("limits", "六、观察与局限"),
)


def validate_portfolio_risk(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = validate_card(raw, request)
    by_key: dict[str, dict[str, Any]] = {}
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        key = str(section.get("key") or "").strip()
        if key not in dict(_PORTFOLIO_SECTIONS):
            continue
        blocks: list[dict[str, Any]] = []
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "").strip()
            if kind == "paragraph":
                text = str(block.get("text") or "").strip()
                if text:
                    blocks.append({"type": "paragraph", "text": text[:1200]})
            elif kind == "bullets":
                items = [str(x).strip() for x in (block.get("items") or []) if str(x).strip()]
                if items:
                    blocks.append({"type": "bullets", "items": items[:6]})
        body = str(section.get("body") or "").strip()
        if not body:
            body = next((b["text"] for b in blocks if b.get("type") == "paragraph"), "")
        if not body:
            body = next((str(b["items"][0]) for b in blocks if b.get("type") == "bullets" and b.get("items")), "")
        if not body:
            continue
        if not blocks:
            blocks = [{"type": "paragraph", "text": body}]
        by_key[key] = {"key": key, "title": dict(_PORTFOLIO_SECTIONS)[key], "body": body, "blocks": blocks, "items": []}
    missing = [title for key, title in _PORTFOLIO_SECTIONS if key not in by_key]
    if missing:
        raise AiBadOutput("组合风险缺少：" + "、".join(missing))
    data["sections"] = [by_key[key] for key, _ in _PORTFOLIO_SECTIONS]
    data["meta"].setdefault("dataSource", "组合体检 + 归因 + 压力测试")
    return data


PORTFOLIO_TASK = register(
    TaskSpec(
        task_id="invest.portfolio",
        description="Invest 组合风险：风险分、越线项、今日影响、压力测试与偏离",
        temperature=0.25,
        max_tokens=6500,
        timeout_sec=180,
        executors=("local",),
        validator=validate_portfolio_risk,
    )
)

ANNOUNCEMENT_TASK = register(
    TaskSpec(
        task_id="invest.announcement",
        description="Invest 公告/业绩会要点：发生了什么 / 影响 / 关注",
        temperature=0.25,
        max_tokens=2000,
        timeout_sec=90,
        executors=("local",),
        validator=validate_card,
    )
)

BACKTEST_TASK = register(
    TaskSpec(
        task_id="invest.backtest",
        description="Invest 回测解读：收益来源、回撤特征与风格风险，不预测未来",
        temperature=0.25,
        max_tokens=6000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

ALLOCATION_TASK = register(
    TaskSpec(
        task_id="invest.allocation",
        description="Invest 配置/定投解释：期限、风险偏好与组合偏离的风险预算说明",
        temperature=0.25,
        max_tokens=2600,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

CONDITION_TASK = register(
    TaskSpec(
        task_id="invest.condition",
        description="Invest 自然语言条件选股解析",
        temperature=0.1,
        max_tokens=1200,
        timeout_sec=60,
        executors=("local",),
        validator=lambda raw, req: _load(raw),
    )
)


VISION_TASK = register(
    TaskSpec(
        task_id="invest.vision",
        description="Invest 截图识图：从图片提取股票名/代码/条件/价格，填入输入框",
        temperature=0.0,
        max_tokens=400,
        timeout_sec=60,
        executors=("local",),
        validator=validate_vision,
    )
)

COMPARE_TASK = register(
    TaskSpec(
        task_id="invest.compare",
        description="Invest 多标的对比：同口径差异、各自风险（不判断谁更好）",
        temperature=0.25,
        max_tokens=2600,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

PAPER_TASK = register(
    TaskSpec(
        task_id="invest.paper",
        description="Invest 模拟盘点评：仓位、集中度、回撤，只解释不调仓",
        temperature=0.3,
        max_tokens=2400,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

QUANT_TASK = register(
    TaskSpec(
        task_id="invest.quant",
        description="Invest 量化解释：因子得分、选股口径与模拟盘信号说明",
        temperature=0.2,
        max_tokens=2400,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

__all__ = [
    "ALLOCATION_TASK",
    "BACKTEST_TASK",
    "ANNOUNCEMENT_TASK",
    "CONDITION_TASK",
    "COMPARE_TASK",
    "PAPER_TASK",
    "QUANT_TASK",
    "DAILY_TASK",
    "INTENT_TASK",
    "PORTFOLIO_TASK",
    "PROMPT_VERSION",
    "RED_LINE",
    "STOCK_TASK",
    "VISION_TASK",
    "validate_card",
    "validate_intent",
    "validate_vision",
]
