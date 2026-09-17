"""``app`` 测试：配置、因子加载、端到端实验、结果存储。"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import ConfigManager
from app.services.factor.loader import FactorLoader
from app.services.results.manager import ResultManager
from app.database.results.storage.csv_storage import CSVStorage
from app.database.results.storage.sqlite_storage import SQLiteStorage


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
        "import pandas as pd\nfrom app.services.factor.base import BaseFactor\nclass AlphaTest(BaseFactor):\n    name = 'alpha_test'\n    def compute(self, data):\n        return data['close'].pct_change(5)\n",
        encoding="utf-8",
    )
    loader = FactorLoader(factor_dir=str(tmp_path))
    factor = loader.load("alpha_test")
    assert factor.name == "alpha_test"
    assert "alpha_test" in loader.factors


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

    # 存储只返回数据；业务门面恢复后仍可读指标、再次保存。
    from app.models.results import ResultData

    assert type(loaded) is ResultData
    restored = result.load(str(out))
    assert isinstance(restored, ResultManager)
    assert restored.get_metric("sharpe") == 1.2
    assert restored.storage is result.storage
    restored.save(str(tmp_path / "restored"))


def test_parquet_storage_roundtrip(tmp_path):
    from app.database.results.storage.parquet_storage import ParquetStorage

    eq = pd.Series([1.0, 1.05, 1.1], index=pd.bdate_range("2022-01-03", periods=3))
    fv = pd.DataFrame(
        {"S000": [0.1, 0.2, 0.3], "S001": [0.4, 0.5, 0.6]},
        index=pd.bdate_range("2022-01-03", periods=3),
    )
    pos = pd.DataFrame(
        {"S000": [0.5, 0.5, 0.0], "S001": [-0.5, -0.5, 0.0]},
        index=pd.bdate_range("2022-01-03", periods=3),
    )
    result = ResultManager(
        metrics={"sharpe": 1.2, "ic": 0.05},
        equity_curve=eq,
        factor_values=fv,
        positions=pos,
        storage=ParquetStorage(),
    )
    out = tmp_path / "result"
    result.save(str(out))
    # 大表走 parquet，小文件走 csv/json
    assert (out / "metrics.csv").exists()
    assert (out / "equity_curve.csv").exists()
    assert (out / "factor_values.parquet").exists()
    assert (out / "positions.parquet").exists()
    assert (out / "meta.json").exists()

    loaded = ParquetStorage().read(str(out))
    assert loaded.metrics["sharpe"] == 1.2
    assert loaded.metrics["ic"] == 0.05
    assert len(loaded.equity_curve) == 3
    assert loaded.factor_values.shape == fv.shape
    assert loaded.positions.shape == pos.shape


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
    from app.services.factor.plotting import plot_group_ic

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


# ---------------- IC 分析四联图 ----------------

def test_plot_ic_analysis(tmp_path):
    from app.services.factor.plotting import _daily_ic_series, plot_ic_analysis

    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2022-01-03", periods=120)
    symbols = [f"S{i:03d}" for i in range(30)]
    # 高因子 -> 高收益，IC 为正
    fv = pd.DataFrame(rng.normal(0, 1, (120, 30)), index=dates, columns=symbols)
    fr = fv * 0.2 + pd.DataFrame(
        rng.normal(0, 1, (120, 30)), index=dates, columns=symbols
    )

    png = plot_ic_analysis(fv, fr, tmp_path / "ic_analysis.png", window=60)
    assert png is not None
    assert Path(png).exists()

    # 每日 IC 序列与 IC 指标同口径（截面 corrwith 逐行）
    ic = _daily_ic_series(fv, fr)
    assert len(ic) == 120
    ref = fv.corrwith(fr, axis=1).dropna().mean()
    assert abs(ic.mean() - ref) < 1e-12

    # rank 口径（RankIC）也能出图
    assert plot_ic_analysis(
        fv, fr, tmp_path / "ic_rank.png", method="rank"
    ) is not None

    # 样本不足（空 DataFrame / 不足 2 日）-> None 不报错
    assert plot_ic_analysis(
        pd.DataFrame(), pd.DataFrame(), tmp_path / "none.png"
    ) is None


# ---------------- 收益-回撤图 + 年度统计表 ----------------

def test_plot_equity_drawdown_yearly_table(tmp_path):
    from app.services.factor.plotting import plot_equity_drawdown, _yearly_stats

    # 跨 3 年净值：2017 涨 / 2018 跌 / 2019 涨（确定性日收益）
    dates = pd.bdate_range("2017-01-03", "2019-12-31")
    r = np.where(
        dates.year == 2017, 0.0004,
        np.where(dates.year == 2018, -0.0003, 0.0005),
    )
    eq = pd.Series(np.cumprod(1.0 + r), index=dates)

    # 带年度表出图
    png = plot_equity_drawdown(eq, tmp_path / "ed.png", show_yearly_table=True)
    assert png is not None and Path(png).exists()

    years, stats = _yearly_stats(eq, periods_per_year=252)
    assert years == [2017, 2018, 2019]
    # 方向：涨年正、跌年负
    assert stats["年化"][0] > 0 and stats["年化"][1] < 0 and stats["年化"][2] > 0
    # 非首年用上一年末净值 -> 等比日收益的年化 = (1+r)^252 - 1（与当年交易日数无关）
    assert abs(stats["年化"][1] - (0.9997 ** 252 - 1)) < 1e-9
    assert abs(stats["年化"][2] - (1.0005 ** 252 - 1)) < 1e-9
    # 回撤非正；2018 全年下行 -> 回撤最深
    assert all(v <= 0 for v in stats["回撤"])
    assert stats["回撤"][1] <= stats["回撤"][0] and stats["回撤"][1] <= stats["回撤"][2]
    # calmar = 年化 / |回撤|
    for i in range(3):
        if not np.isnan(stats["calmar"][i]):
            assert abs(stats["calmar"][i] - stats["年化"][i] / abs(stats["回撤"][i])) < 1e-12

    # 关表也能出图
    png2 = plot_equity_drawdown(eq, tmp_path / "ed2.png", show_yearly_table=False)
    assert png2 is not None and Path(png2).exists()

    # 空数据 -> None 不报错
    assert plot_equity_drawdown(pd.Series(dtype=float), tmp_path / "none.png") is None


# ---------------- 组合构建 ----------------

def test_build_factor_portfolio_weights():
    from app.services.factor.portfolio import build_factor_portfolio

    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2022-01-03", periods=10)
    symbols = [f"S{i:03d}" for i in range(20)]
    fv = pd.DataFrame(rng.normal(0, 1, (10, 20)), index=dates, columns=symbols)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (10, 20)), axis=0)),
        index=dates, columns=symbols,
    )
    # 多空对冲：做多 top stock_num + 做空 bottom stock_num，每日权重和 ≈ 0
    _, _, pos = build_factor_portfolio(
        fv, close, rebalance="daily", stock_num=5, long_short=True
    )
    assert (pos.sum(axis=1).abs() < 1e-9).all()
    assert (pos.abs() <= 1.0).all().all()
    # 实际单边持仓 = stock_num 只（多空各 5，共 10 只非零）
    assert (pos.abs().gt(0).sum(axis=1) <= 2 * 5).all()

    # 只做多：做多 top stock_num，每日权重和 ≈ 1
    _, _, pos_long = build_factor_portfolio(
        fv, close, rebalance="daily", stock_num=5, long_short=False
    )
    assert ((pos_long.sum(axis=1) - 1.0).abs() < 1e-9).all()
    assert (pos_long >= 0).all().all()
    # 实际持仓 = stock_num 只
    assert (pos_long.gt(0).sum(axis=1) == 5).all()
