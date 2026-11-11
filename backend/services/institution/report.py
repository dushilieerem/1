# -*- coding: utf-8 -*-
"""机构端研究报告导出（FR-GLB-02/03、FR-RES-18、GAP-12）。

只做确定性渲染：把研究案、最新版本与证据排成 Markdown，不补造数据。
导出文件必须带演示标识与生成时间；缺失项统一显示「待补充」。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

DIM_EN: dict[str, str] = {
    "industry": "Business & industry",
    "business_model": "Business model",
    "moat": "Moat",
    "financial": "Financial quality",
    "governance": "CEO & governance",
    "valuation": "Valuation & price",
    "evidence": "Evidence & falsifiers",
}

STATUS_ZH: dict[str, str] = {
    "pending_review": "待审核",
    "approved": "已通过",
    "changed": "已变更",
}

DEMO_MARK = "SVQUANT-INST-RESEARCH"


def _text(value: Any, empty: str = "待补充") -> str:
    if value is None:
        return empty
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text or empty


def _cell(value: Any) -> str:
    return _text(value).replace("|", "\\|")


def _pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "待补充"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "待补充"


def _num(value: Any, digits: int = 2, empty: str = "待补充") -> str:
    if value is None:
        return empty
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return empty


def _time(value: Any) -> str:
    if value is None:
        return "待补充"
    if isinstance(value, datetime):
        offset = value.strftime("%z")
        return value.strftime("%Y-%m-%d %H:%M") + (f" (UTC{offset[:3]}:{offset[3:]})" if offset else "")
    return _text(value)


def _bullets(items: Any, empty: str = "待补充") -> list[str]:
    values = [x for x in (items or []) if _text(x, "") != ""]
    return [f"- {_text(x)}" for x in values] or [f"- {empty}"]


def _status(value: Any) -> str:
    key = _text(value, "")
    if not key:
        return "待补充"
    zh = STATUS_ZH.get(key, key)
    return f"{zh}（{key}）" if zh != key else key


def _overview(case: dict[str, Any], version: dict[str, Any] | None) -> list[str]:
    lines = [
        "| 项目 Item | 内容 Content |",
        "| --- | --- |",
        f"| 研究案 Case | {_cell(case.get('case_no'))} |",
        f"| 证券代码 Symbol | {_cell(case.get('symbol'))} |",
        f"| 公司 Company | {_cell(case.get('company_name'))} |",
        f"| 市场 Market | {_cell(case.get('market'))} |",
        f"| 行业 Industry | {_cell(case.get('industry'))} |",
        f"| 研究阶段 Stage | {_cell(case.get('stage'))} |",
        f"| 数据状态 Data status | {_cell(case.get('data_status'))} |",
        f"| 参考价 Ref price | {_num(case.get('ref_price'))} |",
    ]
    if version:
        lines += [
            f"| 版本 Version | v{_cell(version.get('version_no'))} |",
            f"| 版本状态 Review | {_cell(_status(version.get('status')))} |",
            f"| 版本生成时间 Created | {_cell(_time(version.get('created_at')))} |",
        ]
    else:
        lines.append("| 版本 Version | 尚未生成研究版本 |")
    return lines


def _dimensions(version: dict[str, Any] | None) -> list[str]:
    dims = (version or {}).get("six_dim") or []
    if not dims:
        return ["", "> 尚未生成六维研究。", ""]
    lines: list[str] = [""]
    for index, dim in enumerate(dims, start=1):
        key = _text(dim.get("key"), "")
        title = _text(dim.get("title"), key or "维度")
        en = DIM_EN.get(key, "")
        heading = f"### {index}. {title}" + (f" / {en}" if en else "")
        lines += [
            heading,
            "",
            f"- 状态 Status: {_status(dim.get('status'))}",
            f"- 核心问题 Question: {_text(dim.get('question'))}",
            f"- 结论摘要 Summary: {_text(dim.get('summary'))}",
            f"- 分析引擎 Engine: {_text(dim.get('engine') or 'rule')}",
            "- 数据检查 Checks:",
            *["  " + x for x in _bullets(dim.get("checks"))],
        ]
        if dim.get("data_gaps"):
            lines += ["- 数据缺口 Data gaps:", *["  " + x for x in _bullets(dim.get("data_gaps"))]]
        ids = [str(x) for x in (dim.get("evidence_ids") or []) if x is not None]
        lines += [f"- 证据 ID Evidence IDs: {', '.join(ids) if ids else '—'}", ""]
    return lines


def _valuation(version: dict[str, Any] | None) -> list[str]:
    valuation = (version or {}).get("valuation") or {}
    if not valuation:
        return ["", "> 估值参数待补充：未生成估值或缺少财务/股本数据。", ""]
    assumptions = valuation.get("assumptions") or {}
    lines = [
        "",
        "| 参数 Parameter | 数值 Value |",
        "| --- | --- |",
        f"| 收入增速 Revenue growth | {_cell(_pct(assumptions.get('revenue_growth')))} |",
        f"| 现金流利润率 Cash-flow margin | {_cell(_pct(assumptions.get('cash_flow_margin')))} |",
        f"| 折现率 Discount rate | {_cell(_pct(assumptions.get('discount_rate')))} |",
        f"| 永续增长率 Terminal growth | {_cell(_pct(assumptions.get('terminal_growth')))} |",
        f"| 每股价值 · 低估 Low | {_cell(_num(valuation.get('low')))} |",
        f"| 每股价值 · 基准 Base | {_cell(_num(valuation.get('base')))} |",
        f"| 每股价值 · 高估 High | {_cell(_num(valuation.get('high')))} |",
        f"| 股本口径 Shares source | {_cell(valuation.get('shares_source'))} |",
        f"| 方法 Method | {_cell(valuation.get('method'))} |",
        "",
    ]
    note = _text(valuation.get("note"), "")
    if not note and valuation.get("is_demo"):
        note = "演示口径，不是目标价。"
    if note:
        lines += [f"> {note}", ""]
    return lines


def _evidence(evidence: list[dict[str, Any]]) -> list[str]:
    if not evidence:
        return ["", "> 还没有结构化证据。", ""]
    lines = [
        "",
        "| # | 类型 Type | 标题 Title | 来源 Source | 时间 As of | 摘录 Quote |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for ev in evidence:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(ev.get("id")),
                    _cell(ev.get("evidence_type") or "fact"),
                    _cell(ev.get("title")),
                    _cell(ev.get("source")),
                    _cell(ev.get("as_of")),
                    _cell(ev.get("quote")),
                ]
            )
            + " |"
        )
    return [*lines, ""]


def render_research_report(
    *,
    case: dict[str, Any],
    version: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    generated_at: datetime,
) -> str:
    """把研究案渲染成带用途标识的 Markdown 报告。"""
    company = _text(case.get("company_name"))
    symbol = _text(case.get("symbol"))
    lines: list[str] = [
        f"# {company}（{symbol}）公司研究简报 / Company Research Report",
        "",
        f"> **内部研究简报 · 不构成投资建议 / Research use only**（{DEMO_MARK}）",
        f"> 生成时间 Generated at：{_time(generated_at)}",
        "> 本报告由 SVQuant 机构端基于公开数据生成，仅供内部研究使用，不构成投资建议。",
        "> Generated by SVQuant for internal research; not investment advice.",
        "",
        "## 一、基本信息 / Overview",
        "",
        *_overview(case, version),
        "",
        "## 二、结论 / Conclusion",
        "",
        f"{_text((version or {}).get('conclusion'))}",
        "",
        "## 三、六维研究 / Six-dimension research",
        *_dimensions(version),
        "## 四、估值假设 / Valuation assumptions",
        *_valuation(version),
        "## 五、证据 / Evidence",
        *_evidence(evidence),
        "## 六、未解决问题 / Open questions",
        "",
        *_bullets(
            [
                x
                for x in ((version or {}).get("open_questions") or [])
                if not any(
                    h in str(x)
                    for h in (
                        "缺", "未接入", "补数", "数据缺口", "无法", "未获取", "未披露",
                        "未认定", "未返回", "待复核", "待补", "影响 H", "影响 M",
                        "影响 L", "路径", "回填", "只能作线索",
                    )
                )
            ],
            "无。",
        ),
        "",
        "## 七、审核记录 / Review record",
        "",
        f"- 版本状态 Status: {_status((version or {}).get('status'))}",
        f"- 审核人 Reviewer: {_text((version or {}).get('approved_by'), '—')}",
        f"- 审核时间 Reviewed at: {_time((version or {}).get('approved_at'))}",
        "",
        "---",
        "",
        f"> 免责声明 / Disclaimer：报告中的数字来自公开数据与确定性计算；缺失项标注「待补充」，不补造。"
        f" 报告标识 Report marker：{DEMO_MARK}",
        "",
    ]
    return "\n".join(lines)


def report_filename(case: dict[str, Any], version: dict[str, Any] | None) -> str:
    """导出文件名：代码-简称-研究简报-vN.md，去掉路径危险字符。"""
    parts = [
        _text(case.get("symbol"), "case"),
        _text(case.get("company_name"), ""),
        "研究简报",
    ]
    if version and version.get("version_no") is not None:
        parts.append(f"v{version.get('version_no')}")
    raw = "-".join(p for p in parts if p)
    safe = re.sub(r"[\\/:*?\"<>|\s]+", "", raw)
    return f"{safe or 'research-report'}.md"
