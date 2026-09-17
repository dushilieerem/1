"""组合调仓意图记录。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rebalance_logs_from_targets(target_weights: pd.DataFrame) -> pd.DataFrame:
    """由目标权重生成调仓日志，仅保留实际发生权重变化的标的。"""
    columns = ["symbol", "side", "previous_weight", "target_weight", "weight_change"]
    if target_weights is None or target_weights.empty:
        return pd.DataFrame(columns=columns)

    effective = target_weights.ffill().fillna(0.0)
    previous = effective.shift(1).fillna(0.0)
    changes = effective - previous
    changed_mask = changes.to_numpy(dtype=float) != 0.0
    row_numbers, column_numbers = np.nonzero(changed_mask)
    if not len(row_numbers):
        return pd.DataFrame(columns=columns)

    previous_values = previous.to_numpy(dtype=float)[row_numbers, column_numbers]
    target_values = effective.to_numpy(dtype=float)[row_numbers, column_numbers]
    change_values = changes.to_numpy(dtype=float)[row_numbers, column_numbers]
    result = pd.DataFrame(
        {
            "symbol": target_weights.columns.to_numpy()[column_numbers].astype(str),
            "side": np.where(change_values > 0.0, "buy", "sell"),
            "previous_weight": previous_values,
            "target_weight": target_values,
            "weight_change": change_values,
        },
        index=target_weights.index.to_numpy()[row_numbers],
    )
    result.index.name = "date"
    return result[columns]
