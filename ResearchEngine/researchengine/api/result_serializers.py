"""回测结果的净值、回撤、持仓和执行审计序列化辅助函数。"""

from __future__ import annotations

import pandas as pd

from researchengine.api.schemas import (
    AnnualReturn,
    DrawdownInfo,
    EquityPoint,
    EventFillInfo,
    EventOrderInfo,
    EventPositionSnapshot,
    ExecutionTimelineItem,
    Holding,
    ICPoint,
    IndustryEquityCurve,
    IndustryGroupEquityCurve,
    IndustryGroupPoint,
    LayeredPoint,
    PositionSnapshot,
    RebalanceLog,
    RebalanceTrade,
    RollingIRPoint,
    ValuePoint,
)
from researchengine.api.serializers import equity_to_points


def _layered_equity_to_points(equity: pd.DataFrame) -> list[LayeredPoint]:
    """分层净值宽表转为前端消费的逐日对象。"""
    points = []
    for date, row in equity.iterrows():
        values = {"date": pd.Timestamp(date).strftime("%Y-%m-%d")}
        for number, value in enumerate(row, start=1):
            values[f"layer{number}"] = float(value)
        points.append(LayeredPoint(**values))
    return points


def _value_points(series: pd.Series) -> list[ValuePoint]:
    return [
        ValuePoint(date=pd.Timestamp(date).strftime("%Y-%m-%d"), value=float(value))
        for date, value in series.items() if pd.notna(value)
    ]


def _ic_points(frame: pd.DataFrame) -> list[ICPoint]:
    if frame.empty:
        return []
    return [
        ICPoint(
            date=pd.Timestamp(date).strftime("%Y-%m-%d"),
            value=float(row["value"]),
            sample_size=int(row["sample_size"]),
        )
        for date, row in frame.iterrows() if pd.notna(row["value"])
    ]


def _rolling_ir_points(series: pd.Series, window: int = 60) -> list[RollingIRPoint]:
    return [
        RollingIRPoint(
            date=pd.Timestamp(date).strftime("%Y-%m-%d"), value=float(value),
            window=window, sample_size=window,
        )
        for date, value in series.items() if pd.notna(value)
    ]


def _industry_equity_to_response(curves: dict[str, pd.Series]) -> list[IndustryEquityCurve]:
    return [
        IndustryEquityCurve(industry_code=industry, industry_name=industry, points=_value_points(series))
        for industry, series in sorted(curves.items()) if not series.empty
    ]


def _industry_group_equity_to_response(
    curves: dict[str, pd.DataFrame],
) -> list[IndustryGroupEquityCurve]:
    result = []
    for industry, equity in sorted(curves.items()):
        points = [
            IndustryGroupPoint(
                date=pd.Timestamp(date).strftime("%Y-%m-%d"),
                groups={str(group): float(value) for group, value in row.items() if pd.notna(value)},
            )
            for date, row in equity.iterrows()
        ]
        if points:
            result.append(IndustryGroupEquityCurve(
                industry_code=industry, industry_name=industry, points=points,
            ))
    return result


def _compute_drawdowns(equity: pd.Series) -> list[DrawdownInfo]:
    """从净值序列计算回撤区间明细。"""
    if equity is None or len(equity) < 2:
        return []

    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max

    drawdowns_list = []
    in_drawdown = False
    peak_date = None
    peak_value = None
    trough_date = None
    trough_value = None

    for date, (eq_val, dd_val) in enumerate(zip(equity.items(), drawdown.items())):
        idx, eq = eq_val
        _, dd = dd_val

        if dd < 0 and not in_drawdown:
            # 开始回撤
            in_drawdown = True
            peak_date = idx
            peak_value = eq
            trough_date = idx
            trough_value = eq
        elif dd < 0 and in_drawdown:
            # 回撤中，更新最低点
            if eq < trough_value:
                trough_date = idx
                trough_value = eq
        elif dd >= 0 and in_drawdown:
            # 回撤恢复
            in_drawdown = False
            depth = (trough_value - peak_value) / peak_value
            days = (idx - peak_date).days
            drawdowns_list.append(
                DrawdownInfo(
                    start=str(peak_date.date()),
                    end=str(trough_date.date()),
                    peak=float(peak_value),
                    trough=float(trough_value),
                    recovery=str(idx.date()),
                    depth=float(depth),
                    days=days,
                )
            )

    # 如果到末尾还在回撤中
    if in_drawdown and trough_date is not None and peak_date is not None:
        depth = (trough_value - peak_value) / peak_value
        days = (equity.index[-1] - peak_date).days
        drawdowns_list.append(
            DrawdownInfo(
                start=str(peak_date.date()),
                end=str(trough_date.date()),
                peak=float(peak_value),
                trough=float(trough_value),
                recovery=None,
                depth=float(depth),
                days=days,
            )
        )

    # 只返回最大的前 10 个回撤
    drawdowns_list.sort(key=lambda x: x.depth)
    return drawdowns_list[:10]


def _compute_annual_returns(equity: pd.Series) -> list[AnnualReturn]:
    """从净值序列计算分年收益。"""
    if equity is None or len(equity) < 2:
        return []

    # 按年分组算收益
    years = equity.index.year.unique()
    result = []
    for year in sorted(years):
        year_data = equity[equity.index.year == year]
        if len(year_data) < 2:
            continue
        ret = (year_data.iloc[-1] - year_data.iloc[0]) / year_data.iloc[0]
        result.append(AnnualReturn(year=int(year), return_value=float(ret)))
    return result


def _display_instrument(symbol: object, stock_names: dict[str, str]) -> tuple[str, str]:
    """将面板代码转换为 API 代码，并查询证券名称。"""
    from researchengine.api.market_data import _market_symbol, _panel_symbol

    panel_symbol = _panel_symbol(str(symbol))
    return _market_symbol(panel_symbol), stock_names[panel_symbol]


def _sample_positions(
    positions: pd.DataFrame | None,
    stock_names: dict[str, str],
    max_snapshots: int = 60,
    top_n: int = 20,
) -> list[PositionSnapshot] | None:
    """对持仓权重进行采样，减少传输量。"""
    if positions is None or len(positions) == 0:
        return None

    # 每隔 N 个点采样一次
    step = max(1, len(positions) // max_snapshots)
    sampled = []

    for idx in range(0, len(positions), step):
        row = positions.iloc[idx]
        date_str = str(positions.index[idx].date()) if hasattr(positions.index[idx], 'date') else str(positions.index[idx])

        # 只取权重最大的 top_n 只
        sorted_row = row.dropna().sort_values(ascending=False)
        top = sorted_row.head(top_n)

        holdings = []
        for sym, weight in top.items():
            symbol, name = _display_instrument(sym, stock_names)
            holdings.append(Holding(symbol=symbol, name=name, weight=float(weight)))
        sampled.append(PositionSnapshot(date=date_str, holdings=holdings))

    return sampled


def _serialize_rebalance_logs(
    logs: pd.DataFrame | None, stock_names: dict[str, str]
) -> list[RebalanceLog] | None:
    """按调仓日期聚合日志，供 Web 端按需展示。"""
    if logs is None or logs.empty:
        return None

    result = []
    for date, trades in logs.groupby(level=0, sort=True):
        serialized_trades = []
        for row in trades.itertuples(index=False):
            symbol, name = _display_instrument(row.symbol, stock_names)
            serialized_trades.append(RebalanceTrade(
                symbol=symbol,
                name=name,
                side=row.side,
                previous_weight=float(row.previous_weight),
                target_weight=float(row.target_weight),
                weight_change=float(row.weight_change),
            ))
        result.append(RebalanceLog(
            date=pd.Timestamp(date).strftime("%Y-%m-%d"),
            trades=serialized_trades,
        ))
    return result


def _serialize_vectorized_execution_timeline(
    logs: pd.DataFrame | None, stock_names: dict[str, str],
) -> list[ExecutionTimelineItem] | None:
    """将向量化目标权重变化映射为统一执行时间线。"""
    rebalance_logs = _serialize_rebalance_logs(logs, stock_names)
    if rebalance_logs is None:
        return None
    return [
        ExecutionTimelineItem(
            timestamp=f"{log.date}T00:00:00",
            type="rebalance",
            payload={"trades": [trade.model_dump() for trade in log.trades]},
        )
        for log in rebalance_logs
    ]


def _serialize_event_execution_timeline(
    orders: list[EventOrderInfo],
    fills: list[EventFillInfo],
    positions: list[EventPositionSnapshot],
    events: list[dict[str, object]],
) -> list[ExecutionTimelineItem] | None:
    """按日频事件顺序合并订单、成交、账户快照与审计事件。"""
    items: list[tuple[str, int, ExecutionTimelineItem]] = []
    event_priority = {
        "SESSION_OPEN": 0,
        "SCHEDULED_CALLBACK": 10,
        "ORDER_REJECTED": 30,
        "FILL": 30,
        "SESSION_CLOSE": 50,
    }
    for event in events:
        timestamp = str(event["timestamp"])
        items.append((timestamp, event_priority.get(str(event["type"]), 20), ExecutionTimelineItem(
            timestamp=timestamp, type="audit", payload=event,
        )))
    for order in orders:
        if order.submitted_at is not None:
            items.append((order.submitted_at, 20, ExecutionTimelineItem(
                timestamp=order.submitted_at, type="order", payload=order.model_dump(),
            )))
    for fill in fills:
        items.append((fill.timestamp, 30, ExecutionTimelineItem(
            timestamp=fill.timestamp, type="fill", payload=fill.model_dump(),
        )))
    for position in positions:
        items.append((position.timestamp, 40, ExecutionTimelineItem(
            timestamp=position.timestamp, type="position", payload=position.model_dump(),
        )))
    return [item for _, _, item in sorted(items, key=lambda entry: (entry[0], entry[1]))] or None


def _compute_equity_with_drawdown(equity: pd.Series) -> list[EquityPoint]:
    """计算净值点序列，包含回撤值。"""
    points = equity_to_points(equity)
    if not points:
        return []

    values = [p["value"] for p in points]
    if not values or values[0] is None:
        return [EquityPoint(date=p["date"], value=0.0, drawdown=0.0) for p in points]

    cummax_val = values[0]
    result = []
    for p, v in zip(points, values):
        if v is None:
            result.append(EquityPoint(date=p["date"], value=0.0, drawdown=0.0))
            continue
        cummax_val = max(cummax_val, v)
        dd = (v - cummax_val) / cummax_val if cummax_val != 0 else 0.0
        result.append(EquityPoint(date=p["date"], value=v, drawdown=dd))
    return result


__all__ = [
    "_layered_equity_to_points",
    "_value_points",
    "_ic_points",
    "_rolling_ir_points",
    "_industry_equity_to_response",
    "_industry_group_equity_to_response",
    "_compute_drawdowns",
    "_compute_annual_returns",
    "_display_instrument",
    "_sample_positions",
    "_serialize_rebalance_logs",
    "_serialize_vectorized_execution_timeline",
    "_serialize_event_execution_timeline",
    "_compute_equity_with_drawdown",
]
