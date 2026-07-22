"""``FactorEngine`` 与计算后端的测试。"""

import numpy as np
import pandas as pd

from quantcore import BaseFactor, FactorEngine, FactorLibrary, FieldParquetProvider
from quantcore import DataEngine
from quantcore import CSVDataProvider
from quantcore.factor.base import library_factors


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


class _RelativeStrength(FactorLibrary):
    def relative_to_csi300(self):
        return self.close.pct_change().sub(self.csi300.close.pct_change(), axis=0)


def test_factor_library_accesses_csi300_close(tmp_path):
    dates = pd.bdate_range("2022-01-03", periods=3)
    pd.DataFrame({"datetime": dates, "A": [10.0, 11.0, 12.0]}).to_parquet(
        tmp_path / "close.parquet", index=False
    )
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    pd.DataFrame(
        {"000300_close": [100.0, 105.0, 110.0], "000300_open": [100.0, 105.0, 110.0],
         "000300_high": [100.0, 105.0, 110.0], "000300_low": [100.0, 105.0, 110.0],
         "000300_volume": [1.0, 1.0, 1.0]},
        index=dates,
    ).to_parquet(benchmark / "index_000300.parquet")

    library = _RelativeStrength()
    engine = FactorEngine()
    for factor in library_factors(library).values():
        engine.register(factor)

    values = engine.compute(
        "relative_to_csi300", DataEngine(FieldParquetProvider(tmp_path)), ["A"]
    )
    assert np.isclose(values["A"].iloc[-1], 12 / 11 - 110 / 105)
