"""批量回测 repository 层验收。"""

from app.repositories.factor_backtest import FactorBacktestRepository


def test_repository_exposes_batch_persistence_without_leaking_sqlite_to_api():
    assert hasattr(FactorBacktestRepository, "create_batch")
    assert hasattr(FactorBacktestRepository, "record_factor")
    assert not hasattr(FactorBacktestRepository, "connect")
