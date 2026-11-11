# -*- coding: utf-8 -*-
"""M01：视图 → PG 服务表的字段映射与清洗。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data import view_loader as loader  # noqa: E402


def test_period_and_day() -> None:
    assert loader._period("20250331") == "2025Q1"
    assert loader._period("20251231") == "2025Q4"
    assert loader._period("bad") == "bad"
    assert loader._iso_day("20260417") == "2026-04-17"
    assert loader._iso_day(None) is None


def test_clean_nan_to_none() -> None:
    assert loader._clean(float("nan")) is None
    assert loader._clean(1.5) == 1.5
    assert loader._clean(None) is None


def test_income_single_quarter_to_ytd() -> None:
    import math

    import pandas as pd

    frame = pd.DataFrame(
        {
            "symbol": ["600519.SH"] * 4 + ["000001.SZ"],
            "m_timetag": ["20260331", "20260630", "20260930", "20250630", "20260630"],
            "revenue": [100.0, 120.0, None, 80.0, 50.0],
            "oper_profit": [50.0, 60.0, None, 30.0, 20.0],
            "net_profit_excl_min_int_inc": [40.0, 45.0, None, 20.0, 10.0],
            "gross_margin": [90.0, 88.0, 87.0, 85.0, None],
        }
    )
    out = loader._to_ytd(frame)
    assert out["revenue"].iloc[:4].tolist()[:2] == [100.0, 220.0]
    assert math.isnan(out["revenue"].iloc[2])
    assert out["revenue"].iloc[3] == 80.0  # 新财年重新累计
    assert out["revenue"].iloc[4] == 50.0
    assert math.isclose(out["gross_profit"].iloc[1], 220.0 * 0.88)
    assert math.isnan(out["gross_profit"].iloc[4])


def test_annual_only_rows_stay_null_for_single_quarter_fields() -> None:
    import math

    import pandas as pd

    frame = pd.DataFrame(
        {
            "symbol": ["600519.SH", "600519.SH"],
            "m_timetag": ["20141231", "20151231"],
            "revenue": [1.004e10, 9.71e9],  # 实为 Q4 单季
            "oper_profit": [6.79e9, 5.86e9],
            "net_profit_excl_min_int_inc": [4.66e9, 4.08e9],
            "gross_margin": [92.59, 92.23],
        }
    )
    out = loader._to_ytd(frame)
    assert all(math.isnan(v) for v in out["revenue"])
    assert all(math.isnan(v) for v in out["net_profit_excl_min_int_inc"])
    assert all(math.isnan(v) for v in out["gross_profit"])


def test_valuation_frame_maps_and_filters(monkeypatch) -> None:
    import pyarrow as pa

    table = pa.table(
        {
            "date": ["2026-10-30", "2026-10-01"],
            "symbol": ["600519.SH", "600519.SH"],
            "pe_ttm": [21.3, 22.0],
            "pb_mrq": [6.9, 7.0],
            "pcf_operating_cash_flow_ttm": [14.6, 15.0],
            "dividend_yield_ttm": [3.73, 3.8],
            "float_mv": [None, 1.0],
            "total_mv": [1.74e12, 1.8e12],
        }
    )
    monkeypatch.setattr(loader, "view_root", lambda: Path("/tmp/view"))
    monkeypatch.setattr(loader, "_read", lambda *a, **k: table)
    frame = loader.valuation_frame("2026-10-01", "2026-10-30", ["600519.SH"])
    assert len(frame) == 2
    assert "pcf_ocf_ttm" in frame.columns
    assert loader._clean(frame.iloc[0]["float_mv"]) is None


def _write_parquet(path: Path, columns: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)


def test_read_fills_symbol_from_filename(tmp_path: Path) -> None:
    """免费源一股一文件；部分新文件（如 BSE）没有 Symbol 列，代码只在文件名里。"""
    base = tmp_path / "free" / "financial_balance"
    _write_parquet(
        base / "000001.SZ.parquet",
        {"Symbol": ["000001.SZ"], "m_timetag": ["20260630"], "m_anntime": ["20260801"]},
    )
    _write_parquet(
        base / "920157.BJ.parquet",
        {"m_timetag": ["20260630"], "m_anntime": ["20260801"]},
    )

    table = loader._read(
        tmp_path,
        "financial_balance",
        ["Symbol", "m_timetag", "m_anntime"],
        domain="free",
        symbol_from_filename=True,
    )
    assert set(table["Symbol"].to_pylist()) == {"000001.SZ", "920157.BJ"}


def test_read_without_flag_leaves_symbol_null(tmp_path: Path) -> None:
    base = tmp_path / "free" / "financial_balance"
    _write_parquet(
        base / "000001.SZ.parquet",
        {"Symbol": ["000001.SZ"], "m_timetag": ["20260630"]},
    )
    _write_parquet(base / "920157.BJ.parquet", {"m_timetag": ["20260630"]})

    table = loader._read(
        tmp_path, "financial_balance", ["Symbol", "m_timetag"], domain="free"
    )
    assert sorted(table["Symbol"].to_pylist(), key=str) == ["000001.SZ", None]


def test_iso_day_treats_nan_as_missing() -> None:
    """财务源里公告日可能是 NaN；不能写成字符串 "nan"，否则 DATE 列整批 COPY 失败。"""
    import math

    assert loader._iso_day(float("nan")) is None
    assert loader._iso_day(None) is None
    assert loader._iso_day("") is None
    assert loader._iso_day(20240625) == "2024-06-25"
    assert loader._iso_day(20240625.0) == "2024-06-25"
    assert loader._iso_day("20240625") == "2024-06-25"
    assert not math.isnan(0)  # 文档化：数学 NaN 只来自 float
