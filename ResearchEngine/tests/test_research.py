"""``ResearchEngine`` 测试：配置、因子加载、端到端实验、结果存储。"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from quantcore import CSVDataProvider
from researchengine import (
    ConfigManager,
    Experiment,
    ExperimentManager,
    FactorLoader,
    ResultManager,
    CSVStorage,
    SQLiteStorage,
)


# ---------------- ConfigManager ----------------

def test_config_yaml(tmp_path):
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text("benchmark: CSI500\ncommission: 0.0003\n", encoding="utf-8")
    cfg = ConfigManager(config_path=str(cfg_path))
    assert cfg.get("benchmark") == "CSI500"
    assert cfg.get("commission") == 0.0003
    assert cfg.get("missing", "def") == "def"


def test_config_set_get_nested():
    cfg = ConfigManager()
    cfg.set("data.dir", "./data")
    assert cfg.get("data.dir") == "./data"
    assert cfg.to_dict()["data"] == {"dir": "./data"}


# ---------------- FactorLoader ----------------

def test_factor_loader_load(tmp_path):
    (tmp_path / "alpha_test.py").write_text(
        "import pandas as pd\n"
        "from quantcore import BaseFactor\n"
        "class AlphaTest(BaseFactor):\n"
        "    name = 'alpha_test'\n"
        "    def compute(self, data):\n"
        "        return data['close'].pct_change(5)\n",
        encoding="utf-8",
    )
    loader = FactorLoader(factor_dir=str(tmp_path))
    factor = loader.load("alpha_test")
    assert factor.name == "alpha_test"
    assert "alpha_test" in loader.factors


# ---------------- 端到端实验 ----------------

def _gen_data(tmp_path, n_symbols=5, days=80, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=days)
    symbols = [f"S{i:03d}" for i in range(n_symbols)]
    for sym in symbols:
        drift = rng.uniform(0.1, 0.3) / 252
        vol = rng.uniform(0.2, 0.4) / np.sqrt(252)
        mom = rng.uniform(0.03, 0.08)
        rets = np.zeros(days)
        for t in range(1, days):
            hist = rets[max(0, t - 20):t].mean()
            rets[t] = drift + mom * hist + rng.normal(0, vol)
        close = 20 * np.exp(np.cumsum(rets))
        pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": close, "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": rng.integers(1000, 9999, days),
        }).to_csv(tmp_path / f"{sym}.csv", index=False)
    pd.DataFrame({"pool": ["CSI500"], "symbols": [";".join(symbols)]}).to_csv(
        tmp_path / "universe.csv", index=False
    )
    return symbols


def test_experiment_end_to_end(tmp_path):
    symbols = _gen_data(tmp_path)
    config = ConfigManager()
    config.set("data_dir", str(tmp_path))
    config.set("rebalance", "monthly")
    config.set("n_groups", 5)
    config.set("long_short", True)
    config.set("ic_horizon", 5)
    config.set("storage", "csv")
    config.set("output_path", str(tmp_path / "out"))

    # 直接用 Alpha101 因子
    from quantcore import BaseFactor

    class Mom(BaseFactor):
        name = "mom"
        def compute(self, data):
            return data.close.pct_change(20)

    exp = Experiment(
        factor=Mom(), universe="CSI500",
        start_date="2022-01-03", end_date="2024-12-31",
        config=config,
    )
    result = exp.run()
    assert result.equity_curve is not None
    assert len(result.equity_curve) > 20
    assert "sharpe" in result.metrics
    assert "ic" in result.metrics
    assert "annual_return" in result.metrics
    # 结果已保存
    assert (tmp_path / "out" / "metrics.csv").exists()


def test_experiment_manager_run_all(tmp_path):
    _gen_data(tmp_path)
    config = ConfigManager()
    config.set("data_dir", str(tmp_path))
    config.set("output_path", str(tmp_path / "out"))

    from quantcore import BaseFactor

    class Mom(BaseFactor):
        name = "mom"
        def compute(self, data):
            return data.close.pct_change(20)

    mgr = ExperimentManager()
    mgr.create(Mom(), "CSI500", "2022-01-03", "2024-12-31", config)
    results = mgr.run_all()
    assert "mom" in results
    assert results["mom"].equity_curve is not None


# ---------------- 结果存储 ----------------

def test_csv_storage_roundtrip(tmp_path):
    eq = pd.Series([1.0, 1.05, 1.1], index=pd.bdate_range("2022-01-03", periods=3))
    result = ResultManager(
        metrics={"sharpe": 1.2, "ic": 0.05},
        equity_curve=eq,
        storage=CSVStorage(),
    )
    out = tmp_path / "result"
    result.save(str(out))
    assert (out / "metrics.csv").exists()
    assert (out / "equity_curve.csv").exists()

    loaded = CSVStorage().read(str(out))
    assert loaded.metrics["sharpe"] == 1.2
    assert loaded.metrics["ic"] == 0.05
    assert len(loaded.equity_curve) == 3


def test_sqlite_storage_roundtrip(tmp_path):
    eq = pd.Series([1.0, 1.05, 1.1], index=pd.bdate_range("2022-01-03", periods=3))
    result = ResultManager(
        metrics={"sharpe": 1.2, "calmar": 0.9},
        equity_curve=eq,
        storage=SQLiteStorage(),
    )
    db = str(tmp_path / "r.db")
    result.save(db)
    loaded = SQLiteStorage().read(db)
    assert loaded.metrics["sharpe"] == 1.2
    assert loaded.metrics["calmar"] == 0.9
    assert len(loaded.equity_curve) == 3


# ---------------- 分组 IC 图 ----------------

def test_plot_group_ic(tmp_path):
    from researchengine.plotting import plot_group_ic

    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2022-01-03", periods=40)
    symbols = [f"S{i:03d}" for i in range(30)]
    # 因子值 + 含信号的远期收益：高因子 -> 高收益，组内 IC 为正
    fv = pd.DataFrame(rng.normal(0, 1, (40, 30)), index=dates, columns=symbols)
    fr = fv * 0.2 + pd.DataFrame(
        rng.normal(0, 1, (40, 30)), index=dates, columns=symbols
    )

    png = plot_group_ic(fv, fr, tmp_path / "group_ic.png", n_groups=5)
    assert png is not None
    assert Path(png).exists()

    # 样本不足（5 标的分 5 组，每组 1 只）应返回 None 不报错
    small_fv = fv.iloc[:, :5]
    small_fr = fr.iloc[:, :5]
    assert plot_group_ic(
        small_fv, small_fr, tmp_path / "none.png", n_groups=5
    ) is None
