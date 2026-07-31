"""日频 EventEngine 的核心时序与 A 股规则测试。"""

import pandas as pd

from quantcore.backtest.event import EventBacktestConfig, EventBacktestEngine


def _panels():
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
    return {
        "open": pd.DataFrame({"A": [10.0, 11.0, 12.0]}, index=dates),
        "high": pd.DataFrame({"A": [10.0, 11.0, 12.0]}, index=dates),
        "low": pd.DataFrame({"A": [10.0, 11.0, 12.0]}, index=dates),
        "close": pd.DataFrame({"A": [10.5, 11.5, 12.5]}, index=dates),
    }


def test_before_open_only_sees_previous_close_and_fills_at_current_open():
    seen = []

    class Strategy:
        def initialize(self, context):
            def rebalance(ctx):
                seen.append(ctx.data.history(["A"], ["close"], 2)["close"].index.tolist())
                if ctx.current_dt.date().isoformat() == "2024-01-03":
                    ctx.orders.target_quantity("A", 100)

            context.schedule.daily(rebalance)

    result = EventBacktestEngine(_panels(), EventBacktestConfig(initial_capital=10_000)).run(Strategy())

    assert seen[0] == []
    assert seen[1] == [pd.Timestamp("2024-01-02")]
    assert result.fills[0].timestamp == pd.Timestamp("2024-01-03").to_pydatetime()
    assert result.fills[0].price == 11.0


def test_t_plus_one_and_lot_size_rejections_are_audited():
    class Strategy:
        def initialize(self, context):
            def trade(ctx):
                if ctx.current_dt.date().isoformat() == "2024-01-02":
                    ctx.orders.target_quantity("A", 50)
                if ctx.current_dt.date().isoformat() == "2024-01-03":
                    ctx.orders.target_quantity("A", 100)
                    ctx.orders.close("A")

            context.schedule.daily(trade)

    result = EventBacktestEngine(_panels(), EventBacktestConfig(initial_capital=10_000)).run(Strategy())
    rejected = {order.reason_code for order in result.orders if order.status == "rejected"}

    assert "LOT_SIZE" in rejected
    assert "T_PLUS_ONE" in rejected
    assert len(result.fills) == 1


def test_limit_up_rejects_buy():
    panels = _panels()
    panels["limit_up"] = pd.DataFrame({"A": [False, True, False]}, index=panels["close"].index)

    class Strategy:
        def initialize(self, context):
            def trade(ctx):
                if ctx.current_dt.date().isoformat() == "2024-01-03":
                    ctx.orders.target_value("A", 1_100)

            context.schedule.daily(trade)

    result = EventBacktestEngine(panels, EventBacktestConfig(initial_capital=10_000)).run(Strategy())

    assert result.orders[0].reason_code == "LIMIT_UP"


def test_weekly_and_monthly_callbacks_follow_trading_calendar():
    dates = pd.DatetimeIndex(["2024-01-31", "2024-02-01", "2024-02-05"])
    panels = {
        field: pd.DataFrame({"A": [10.0, 10.0, 10.0]}, index=dates)
        for field in ("open", "high", "low", "close")
    }
    calls = []

    class Strategy:
        def initialize(self, context):
            context.schedule.weekly(lambda ctx: calls.append(("weekly", ctx.current_dt.date())), weekday=0)
            context.schedule.monthly(lambda ctx: calls.append(("monthly", ctx.current_dt.date())), trading_day=1)

    EventBacktestEngine(panels).run(Strategy())

    assert calls == [("monthly", pd.Timestamp("2024-01-31").date()), ("monthly", pd.Timestamp("2024-02-01").date()), ("weekly", pd.Timestamp("2024-02-05").date())]


def test_donchian_style_signal_uses_previous_close_and_target_value():
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=dates)
    panels = {field: close.copy() for field in ("open", "high", "low", "close")}

    class DonchianStyleStrategy:
        def initialize(self, context):
            def rebalance(ctx):
                history = ctx.data.history(["A"], ["close", "high"], 3)
                if len(history["close"]) == 3 and history["close"].iloc[-1, 0] > history["high"].iloc[:-1, 0].max():
                    ctx.orders.target_value("A", 2_000)

            context.schedule.daily(rebalance)

    result = EventBacktestEngine(panels, EventBacktestConfig(initial_capital=10_000)).run(DonchianStyleStrategy())

    assert result.fills[0].timestamp == dates[3].to_pydatetime()
    assert result.fills[0].quantity == 100


def test_portfolio_average_cost_tracks_open_fills_and_clears_after_exit():
    seen = []

    class Strategy:
        def initialize(self, context):
            def trade(ctx):
                if ctx.current_dt.date().isoformat() == "2024-01-02":
                    ctx.orders.target_quantity("A", 100)
                elif ctx.current_dt.date().isoformat() == "2024-01-03":
                    seen.append(ctx.portfolio.average_cost("A"))
                elif ctx.current_dt.date().isoformat() == "2024-01-04":
                    ctx.orders.close("A")

            context.schedule.daily(trade)

    result = EventBacktestEngine(_panels(), EventBacktestConfig(initial_capital=10_000)).run(Strategy())

    assert seen == [10.0]
    assert result.position_snapshots[-1].positions["A"] == 0
