"""因子分组的公共实现。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def raw_qcut_groups(
    values: pd.DataFrame,
    n_groups: int,
) -> pd.DataFrame:
    """按每个交易日的原始值使用 ``pd.qcut`` 分组。

    SuperMind/Alphalens 的分组边界由原始因子值决定，而不是由
    ``rank(method="first")`` 强行拆成相同数量。``duplicates="drop"`` 只
    处理重复边界；正常的全精度因子数据不会改变 qcut 结果。完全相等或
    有效值不足以形成任何箱时，使用稳定的列顺序兜底，避免整条回测因
    无法生成信号。

    返回值为与 ``values`` 同形状的 1..N 组号，Q1 为因子值最高组，QN
    为因子值最低组，缺失值保持为 ``<NA>``。
    """
    if n_groups < 2:
        raise ValueError(f"n_groups 至少为 2，得到 {n_groups}")
    if values.empty:
        return pd.DataFrame(index=values.index, columns=values.columns, dtype="Int64")

    # 组装过程使用 NumPy 数组，避免对结果 DataFrame 逐行 ``.loc`` 写入。
    # 后者会在长历史上反复触发 Pandas 的索引对齐和单列设置路径。
    raw_values = values.to_numpy(dtype=float, na_value=np.nan)
    group_values = np.full(raw_values.shape, np.nan, dtype=float)
    for row_number, row in enumerate(raw_values):
        valid_mask = ~np.isnan(row)
        valid_values = row[valid_mask]
        if not valid_values.size:
            continue

        valid = pd.Series(valid_values)
        if valid.empty:
            continue

        labels = pd.qcut(
            valid,
            n_groups,
            labels=False,
            duplicates="drop",
        )
        if labels.isna().any():
            # qcut 在全相等等退化截面上无法生成箱；这不是正常的
            # SuperMind 全精度路径，只作为可重复的保护性兜底。
            ranks = valid.rank(method="first")
            labels = np.ceil(ranks / len(valid) * n_groups).clip(
                upper=n_groups
            ) - 1

        # qcut 的原始标签按因子值从低到高排列；平台约定 Q1 为最高组，
        # 因此将 0..N-1 反向映射为 N..1。
        group_values[row_number, valid_mask] = (
            n_groups - labels.astype("int64").to_numpy()
        )
    return pd.DataFrame(
        group_values, index=values.index, columns=values.columns
    ).astype("Int64")
