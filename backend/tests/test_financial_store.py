# -*- coding: utf-8 -*-
"""P1-D01：财务点时选择、校验与 CSV 导入。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data.financial_store import (  # noqa: E402
    read_csv_records,
    select_point_in_time,
    validate_records,
)


def _row(period: str, announce: str, stype: str = "income", **data) -> dict:
    return {
        "symbol": "000001.SZ",
        "report_period": period,
        "announce_date": announce,
        "statement_type": stype,
        "data": data or {"revenue": 1.0},
    }


def test_point_in_time_excludes_future_announcements() -> None:
    rows = [
        _row("2025-12-31", "2026-03-20", revenue=100),
        _row("2026-03-31", "2026-04-25", revenue=120),
    ]
    # 2026-03-01 只能看到 2025 年报尚未披露 → 无可用数据
    assert select_point_in_time(rows, as_of="2026-03-01") == {}
    picked = select_point_in_time(rows, as_of="2026-03-25")
    assert picked["income"]["report_period"] == "2025-12-31"
    picked = select_point_in_time(rows, as_of="2026-05-01")
    assert picked["income"]["report_period"] == "2026-03-31"


def test_validation_rejects_bad_dates_and_duplicates() -> None:
    bad = _row("2026-03-31", "2026-02-01")
    problems = validate_records([bad])
    assert any("公告日早于报告期" in p for p in problems)

    dup = [_row("2026-03-31", "2026-04-25"), _row("2026-03-31", "2026-04-26")]
    assert any("重复记录" in p for p in validate_records(dup))


def test_csv_reader_and_validation(tmp_path) -> None:
    path = tmp_path / "fin.csv"
    path.write_text(
        "symbol,report_period,announce_date,statement_type,revenue,net_profit\n"
        "000001.SZ,2026-03-31,2026-04-25,income,120.5,30.2\n",
        encoding="utf-8",
    )
    records = read_csv_records(str(path))
    assert records[0]["data"]["revenue"] == 120.5
    assert validate_records(records) == []


def test_unknown_statement_type_rejected() -> None:
    problems = validate_records([_row("2026-03-31", "2026-04-25", stype="unknown")])
    assert any("未知报表类型" in p for p in problems)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
