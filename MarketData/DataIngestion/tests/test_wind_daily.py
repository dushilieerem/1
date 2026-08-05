from pathlib import Path
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.wind.daily import (  # noqa: E402
    WIND_DAILY_FIELDS,
    _require_nonempty_panel,
    _wind_data_to_panel,
    download_daily_panels,
)


class _WindData:
    ErrorCode = 0
    Times = ["2024-01-02", "2024-01-03"]
    Data = [[10.0, 11.0], [20.0, 21.0]]


def test_wind_data_to_panel_uses_standard_symbols_and_datetime_index():
    panel = _wind_data_to_panel(_WindData(), ["000001.SZ", "600000.SH"])

    assert list(panel.columns) == ["000001", "600000"]
    assert panel.index.name == "datetime"
    assert panel.loc[pd.Timestamp("2024-01-03"), "600000"] == 21.0


def test_download_rejects_unknown_field_before_connecting(tmp_path):
    with pytest.raises(KeyError, match="不支持的标准字段"):
        download_daily_panels(["000001.SZ"], "2024-01-01", "2024-01-02", tmp_path, ["unknown"])


def test_daily_field_map_covers_required_existing_market_fields():
    assert {"open", "high", "low", "close", "volume", "amount", "turnover"} <= set(WIND_DAILY_FIELDS)


def test_wind_panel_requires_at_least_one_valid_value():
    with pytest.raises(ValueError, match="float_mv.*任何有效值"):
        _require_nonempty_panel(pd.DataFrame({"000001": [None, None]}), "float_mv")

    _require_nonempty_panel(pd.DataFrame({"000001": [None, 1.0]}), "float_mv")
