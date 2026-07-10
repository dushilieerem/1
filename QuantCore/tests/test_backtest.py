"""``BacktestEngine`` 各组件的测试。"""

import pandas as pd

from quantcore import (
    BacktestEngine,
    CSVDataProvider,
    DataEngine,
    MatchingEngine,
    Order,
    Portfolio,
    TransactionCost,
)


# ---------------- TransactionCost ----------------

def test_transaction_cost_min_commission():
    cost = TransactionCost(commission_rate=0.001, min_commission=5.0, slippage_rate=0.002)
    order = Order(symbol="A", direction=1, quantity=10, order_type="market")
    # trade_value = 10 * 10 = 100 -> commission = max(0.1, 5) = 5, slippage = 0.2
    commission, slippage = cost.calculate(order, fill_price=10.0)
    assert commission == 5.0
    assert slippage == 0.2


def test_transaction_cost_normal():
    cost = TransactionCost(commission_rate=0.001, min_commission=0.0, slippage_rate=0.0)
    order = Order(symbol="A", direction=1, quantity=100, order_type="market")
    commission, slippage = cost.calculate(order, fill_price=10.0)
    assert commission == 1.0  # 1000 * 0.001
    assert slippage == 0.0


# ---------------- MatchingEngine ----------------

def test_matching_market():
    m = MatchingEngine()
    order = Order(symbol="A", direction=1, quantity=100, order_type="market")
    bar = pd.Series({"open": 9, "high": 11, "low": 9, "close": 10}, name="2022-01-04")
    fills = m.match(order, bar)
    assert len(fills) == 1
    assert fills[0].fill_price == 10
    assert order.status == "filled"


def test_matching_limit_filled():
    m = MatchingEngine()
    order = Order(symbol="A", direction=1, quantity=100, order_type="limit", price=10.0)
    bar = pd.Series({"open": 9, "high": 11, "low": 9.5, "close": 10}, name="2022-01-04")
    fills = m.match(order, bar)
    assert len(fills) == 1
    assert fills[0].fill_price == 10.0


def test_matching_limit_not_filled():
    m = MatchingEngine()
    order = Order(symbol="A", direction=1, quantity=100, order_type="limit", price=8.0)
    bar = pd.Series({"open": 10, "high": 11, "low": 9.5, "close": 10}, name="2022-01-04")
    fills = m.match(order, bar)
    assert fills == []


# ---------------- Portfolio ----------------

def test_portfolio_buy_sell():
    from quantcore import Fill
    from datetime import datetime

    pf = Portfolio(initial_capital=1_000_000.0)
    cost = TransactionCost(commission_rate=0.001, min_commission=0.0, slippage_rate=0.0)

    # 买入 100 @ 10  (trade_value=1000, commission=1.0)
    order = Order(symbol="A", direction=1, quantity=100, order_type="market")
    comm, slip = cost.calculate(order, 10.0)
    pf.update(Fill(order.order_id, "A", 1, 10.0, 100, datetime(2022, 1, 4), comm, slip))
    assert pf.cash == 1_000_000 - 1000 - 1.0
    assert pf.positions["A"].quantity == 100
    assert pf.positions["A"].avg_price == 10.0

    # 盯市到 12
    pf.update_prices({"A": 12.0})
    assert pf.market_value() == 1200

    # 卖出 50 @ 12  (trade_value=600, commission=0.6)
    order2 = Order(symbol="A", direction=-1, quantity=50, order_type="market")
    comm2, slip2 = cost.calculate(order2, 12.0)
    pf.update(Fill(order2.order_id, "A", -1, 12.0, 50, datetime(2022, 1, 5), comm2, slip2))
    assert pf.positions["A"].quantity == 50
    assert pf.cash == 1_000_000 - 1000 - 1.0 + 600 - 0.6


# ---------------- BacktestEngine.run ----------------

def test_backtest_run(tmp_path):
    dates = pd.bdate_range("2022-01-03", periods=5)
    for sym, prices in [("A", [10, 11, 12, 13, 14]), ("B", [10, 9, 8, 7, 6])]:
        pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": prices, "high": prices, "low": prices,
            "close": prices, "volume": [100] * 5,
        }).to_csv(tmp_path / f"{sym}.csv", index=False)

    engine = DataEngine(CSVDataProvider(tmp_path))
    bt = BacktestEngine(
        data_engine=engine,
        cost_model=TransactionCost(commission_rate=0, min_commission=0, slippage_rate=0),
        initial_capital=100_000.0,
    )

    def strategy(bar, portfolio):
        # 仅首日买入 A 100 股
        if not portfolio.positions and portfolio.cash > 1000:
            return [Order(symbol="A", direction=1, quantity=100, order_type="market")]
        return []

    result = bt.run(strategy, universe=["A", "B"])
    assert len(result.equity_curve) == 5
    assert len(result.fills) == 1
    # 持有 A，最终权益 = 现金 + 100*14
    assert result.equity_curve.iloc[-1] > 100_000
