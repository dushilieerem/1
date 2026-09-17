"""因子分组的公共实现。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rank_groups(
    values: pd.DataFrame,
    n_groups: int,
) -> pd.DataFrame:
    """用一次截面排名完成日期×标的分组。

    ``rank(method="first")`` 在每个截面内按列顺序稳定打破并列值，然后
    将排名映射到等宽的名次桶。这样整个分组过程只调用一次 Pandas 的
    ``rank``，不再为每个交易日调用 ``pd.qcut``。

    这是有意选择的快速口径：重复值会按列顺序分散到不同分组，因而不再
    保证与 ``pd.qcut`` 的重复边界处理逐位一致。返回值仍为与 ``values``
    同形状的 1..N 组号，Q1 为因子值最高组，QN 为最低组，缺失值保持为
    ``<NA>``。有效标的少于分组数时，只使用实际可形成的前几组。
    """
    if n_groups < 2:
        raise ValueError(f"n_groups 至少为 2，得到 {n_groups}")
    if values.empty:
        return pd.DataFrame(index=values.index, columns=values.columns, dtype="Int64")

    # 直接在 NumPy 宽数组上做稳定排序。对每行的排序结果只累计有效值，
    # 因而缺失值不会占据名次；stable sort 等价于 Pandas rank(method="first")
    # 的列顺序拆并列行为，但避免额外构造一个中间 DataFrame。
    numeric = values.to_numpy(dtype=float, na_value=np.nan)
    valid = ~np.isnan(numeric)
    order = np.argsort(
        np.where(valid, numeric, np.inf),
        axis=1,
        kind="stable",
    )
    sorted_valid = np.take_along_axis(valid, order, axis=1)
    sorted_ranks = np.cumsum(sorted_valid, axis=1, dtype=float)
    ranks = np.full(numeric.shape, np.nan, dtype=float)
    np.put_along_axis(ranks, order, sorted_ranks, axis=1)
    ranks[~valid] = np.nan

    valid_count = valid.sum(axis=1, dtype=float)[:, None]
    effective_groups = np.minimum(valid_count, float(n_groups))
    safe_count = np.maximum(valid_count, 1.0)

    low_to_high = np.ceil(ranks * effective_groups / safe_count)
    group_values = effective_groups - low_to_high + 1.0
    group_values = np.where(np.isnan(ranks), np.nan, group_values)
    # 分组标签只在引擎内部参与比较/聚合，保留为带 NaN 的 float 宽表，
    # 避免长历史上把数百万单元逐个转换为 Pandas nullable Int64 的额外开销。
    return pd.DataFrame(group_values, index=values.index, columns=values.columns)


def raw_qcut_groups(
    values: pd.DataFrame,
    n_groups: int,
) -> pd.DataFrame:
    """兼容旧名称；实现已经统一改为截面 rank。"""

    return rank_groups(values, n_groups)


__all__ = ["rank_groups", "raw_qcut_groups"]
