# -*- coding: utf-8 -*-
"""P1-D01/D02/D03/D07/D08：本地 marketdata 读取与指标计算。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data import indicators  # noqa: E402
from services.data import marketdata_store as md  # noqa: E402

HAS_DATA = (md.data_root() / "data_manifest.yaml").exists()


def test_symbol_normalization() -> None:
    assert md.normalize_symbol("000001") == "000001.SZ"
    assert md.normalize_symbol("600000.sh") == "600000.SH"
    assert md.normalize_symbol("830799") == "830799.BJ"
    with pytest.raises(ValueError):
        md.normalize_symbol("abc")


def _bars() -> list[dict]:
    out = []
    price = 10.0
    for i in range(40):
        price += 0.1 if i % 3 else -0.05
        out.append(
            {
                "date": f"2026-01-{i + 1:02d}",
                "open": price - 0.02,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
                "volume": 1000 + i,
            }
        )
    return out


def test_indicators_lengths_and_values() -> None:
    bars = _bars()
    out = indicators.compute(bars, indicators=["ma", "macd", "rsi", "boll", "kdj", "atr"])
    assert set(out["series"]) >= {"ma5", "macd_dif", "rsi6", "boll_mid", "kdj_k", "atr"}
    for name, series in out["series"].items():
        assert len(series) == len(bars), name
    # 第 20 根之后 MA5 必然有值
    assert out["series"]["ma5"][-1] is not None
    assert 0 <= out["series"]["rsi6"][-1] <= 100


def test_unknown_indicator_rejected() -> None:
    with pytest.raises(ValueError):
        indicators.compute(_bars(), indicators=["foo"])


@pytest.mark.skipif(not HAS_DATA, reason="本机无 marketdata release")
def test_minute_and_fundamentals_read() -> None:
    minute = md.minute_bars("000001.SZ", start="2026-09-10", end="2026-09-10", limit_days=1)
    assert minute["frequency"] == "1m"
    assert minute["count"] > 0
    assert {"time", "open", "close", "volume"} <= set(minute["items"][0])
    assert minute.get("data_version")

    fund = md.fundamentals("000001.SZ", start="2026-10-01")
    assert fund["count"] > 0
    assert "pe_ttm" in fund["items"][0]


@pytest.mark.skipif(not HAS_DATA, reason="本机无 marketdata release")
def test_index_catalog_from_release() -> None:
    cat = md.index_catalog()
    assert cat["count"] >= 2
    assert any(x["code"].startswith("000300") for x in cat["items"])
