# -*- coding: utf-8 -*-
"""FR-GLB-02/03、GAP-12：研究简报导出（Markdown）。"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution.report import render_research_report, report_filename  # noqa: E402

CASE = {
    "id": 7,
    "case_no": "RES-2026-007",
    "symbol": "600519.SH",
    "company_name": "贵州茅台",
    "market": "CN",
    "industry": "白酒",
    "stage": "pending_review",
    "data_status": "ready",
    "ref_price": 1680.5,
}

VERSION = {
    "id": 42,
    "version_no": 3,
    "status": "approved",
    "conclusion": "有条件通过",
    "created_at": "2026-11-01T06:00:00+00:00",
    "approved_by": 9,
    "approved_at": "2026-11-01T07:30:00+00:00",
    "six_dim": [
        {
            "key": "valuation",
            "title": "估值与价格",
            "question": "当前价格隐含了什么预期？",
            "status": "done",
            "summary": "PE 分位偏低",
            "checks": ["参考价 1680.50"],
            "counter": ["分位低不等于便宜"],
            "evidence_ids": [11],
        }
    ],
    "valuation": {
        "method": "owner_earnings_proxy",
        "is_demo": True,
        "assumptions": {
            "revenue_growth": 0.06,
            "cash_flow_margin": None,
            "discount_rate": 0.10,
            "terminal_growth": 0.03,
        },
        "low": 90.0,
        "base": 120.0,
        "high": 150.0,
        "shares_source": "total_shares",
        "note": "演示口径，不是目标价",
    },
    "counter_evidence": ["行业分类为当前快照"],
    "open_questions": ["财务三表未接入或未公告"],
}

EVIDENCE = [
    {
        "id": 11,
        "evidence_type": "fact",
        "title": "行情快照",
        "quote": "收盘 1680.50 | 成交额 2.1 亿\n换行",
        "source": "market_data",
        "as_of": "2026-10-31",
    }
]


def _render(**kw):
    payload = {"case": CASE, "version": VERSION, "evidence": EVIDENCE, "generated_at": datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)}
    payload.update(kw)
    return render_research_report(**payload)


def test_report_has_research_mark_and_sections() -> None:
    out = _render()
    assert "贵州茅台" in out
    assert "600519.SH" in out
    assert "SVQUANT-INST-RESEARCH" in out
    assert "SVQUANT-INST-DEMO" not in out
    assert "v3" in out
    assert "有条件通过" in out
    assert "估值与价格" in out
    assert "Valuation & price" in out
    assert "6.00%" in out
    assert "120.00" in out
    # 缺失的现金流利润率必须显示待补充，不能拿 0 顶替
    assert "现金流利润率 Cash-flow margin | 待补充" in out
    assert "已通过（approved）" in out
    assert "财务三表未接入或未公告" in out
    assert "2026-11-01 08:00" in out


def test_report_escapes_table_cells() -> None:
    out = _render()
    assert "1680.50 \\| 成交额 2.1 亿 换行" in out


def test_report_without_version_or_evidence() -> None:
    out = _render(version=None, evidence=[])
    assert "尚未生成研究版本" in out
    assert "尚未生成六维研究" in out
    assert "估值参数待补充" in out
    assert "还没有结构化证据" in out


def test_filename_sanitized() -> None:
    name = report_filename({**CASE, "symbol": "600519 SH/深", "company_name": "贵州 茅台"}, VERSION)
    assert name.endswith(".md")
    assert "/" not in name and " " not in name
    assert "v3" in name
