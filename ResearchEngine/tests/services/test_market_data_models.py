"""MarketData 业务域模型与研究数据视图测试。"""

from __future__ import annotations

import pandas as pd

from app.models.market_data import MarketDataRelease
from app.services.data.engine import DataEngine
from app.services.data.panel import ResearchDataPanel


def _frame(value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"000001.SZ": [value]}, index=pd.to_datetime(["2026-08-21"])
    )


def test_release_groups_current_business_domain_fields_without_wrapping_dataframe():
    close, pb_mrq, status = _frame(10.0), _frame(1.5), pd.DataFrame(
        {"000001.SZ": ["涨停"]}, index=pd.to_datetime(["2026-08-21"])
    )
    release = MarketDataRelease.from_panels(
        {"close": close, "pb_mrq": pb_mrq, "up_and_down_status": status},
        data_version="ifind-sync-20260821-025851",
    )

    assert release.stock.close is close
    assert release.basic.pb_mrq is pb_mrq
    assert release.status.up_and_down_status is status
    assert release.fields["close"] is close


def test_research_data_panel_keeps_flat_factor_fields_as_native_dataframe():
    close = _frame(10.0)
    panel = ResearchDataPanel(MarketDataRelease.from_panels({"close": close}))

    assert panel.stock.close is close
    assert panel.close is close
    pd.testing.assert_frame_equal(panel.close.pct_change(), close.pct_change())


def test_data_engine_exposes_research_data_without_changing_get_panels_contract():
    class Provider:
        data_version = "release-1"

        def get_bars(self, *_args, **_kwargs):
            raise NotImplementedError

        def get_universe(self, *_args, **_kwargs):
            return []

        def get_symbols(self):
            return ["000001.SZ"]

        def get_panels(self, *_args, **_kwargs):
            return {"close": _frame(10.0), "pb_mrq": _frame(1.5)}

    data = DataEngine(Provider()).get_research_data()

    assert data.release.data_version == "release-1"
    assert data.stock.close.equals(_frame(10.0))
    assert data.basic.pb_mrq.equals(_frame(1.5))
