"""``FactorEngine`` 与计算后端的测试。"""

import numpy as np
import pandas as pd

from quantcore import BaseFactor, FactorEngine
from quantcore import DataEngine
from quantcore import CSVDataProvider


class _Momentum(BaseFactor):
    name = "mom"
    params = {"window": 2}

    def compute(self, data) -> pd.DataFrame:
        return data.close.pct_change(self.params["window"])


def _make_data(tmp_path):
    dates = pd.bdate_range("2022-01-03", periods=6)
    for sym, prices in [
        ("A", [10, 11, 12, 13, 14, 15]),
        ("B", [20, 19, 18, 17, 16, 15]),
    ]:
        pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": prices, "high": prices, "low": prices,
            "close": prices, "volume": [100] * 6,
        }).to_csv(tmp_path / f"{sym}.csv", index=False)
    return DataEngine(CSVDataProvider(tmp_path))


def test_factor_engine_compute(tmp_path):
    engine = _make_data(tmp_path)
    fe = FactorEngine()
    fe.register(_Momentum())
    wide = fe.compute("mom", engine, ["A", "B"])
    assert set(wide.columns) == {"A", "B"}
    # pct_change(2)：最后一行 A = 15/13 - 1
    assert np.isclose(wide["A"].iloc[-1], 15 / 13 - 1)
    # B 下跌，最后一行应为负
    assert wide["B"].iloc[-1] < 0


def test_factor_engine_register_type_check():
    fe = FactorEngine()
    try:
        fe.register("not a factor")  # type: ignore
    except TypeError:
        return
    raise AssertionError("应拒绝非 BaseFactor 子类")


def test_factor_engine_missing_factor():
    fe = FactorEngine()
    try:
        fe.compute("nope", None, [])
    except KeyError:
        return
    raise AssertionError("应报 KeyError")
