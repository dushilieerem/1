"""结果可视化。

- :func:`plot_equity_drawdown`：累计收益 - 回撤双轴图
    - 左轴：累计收益（%），``(净值-1)*100``
    - 右轴：回撤（%，正数，越大回撤越深），向上填充（0 在底、贴近 x 轴）
    - x 轴：仅标年份
- :func:`plot_group_ic`：分组 IC 柱状图
    - 按因子值分位分组（Q1=最低 … QN=最高），各组组内 IC 均值
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _rowwise_corr(a, b, mask, min_n: int):
    """按行算 Pearson 相关（仅 mask=True 处参与；样本不足或方差为 0 返回 NaN）。

    a, b : (T, N) float64；mask : (T, N) bool。
    返回长度 T 的 IC 数组（NaN 表示该行该组无有效 IC）。

    注：不使用 ``np.nanmean``，避免空行（该组当日无成员）触发
    ``RuntimeWarning: Mean of empty slice``；改用 masked 求和 + 安全除法，
    空行结果随后由 ``cnt < min_n`` 置为 NaN。
    """
    with np.errstate(all="ignore"):
        cnt = np.sum(mask, axis=1)
        # 安全均值：空行用 1 占位避免 0 除（其结果随后被 cnt<min_n 置 NaN）
        safe_cnt = np.where(cnt > 0, cnt, 1)
        am = np.sum(np.where(mask, a, 0.0), axis=1, keepdims=True) / safe_cnt[:, None]
        bm = np.sum(np.where(mask, b, 0.0), axis=1, keepdims=True) / safe_cnt[:, None]
        ac = np.where(mask, a - am, 0.0)
        bc = np.where(mask, b - bm, 0.0)
        num = np.sum(ac * bc, axis=1)
        den = np.sqrt(np.sum(ac * ac, axis=1) * np.sum(bc * bc, axis=1))
        corr = num / den
        corr[cnt < min_n] = np.nan
        corr[den == 0] = np.nan
    return corr


def plot_equity_drawdown(equity_curve, path, title: str = "累计收益 - 回撤") -> str | None:
    """绘制累计收益-回撤双轴图并保存为 PNG。

    Parameters
    ----------
    equity_curve : pd.Series
        净值曲线（起点 1.0，DatetimeIndex）。
    path : str | Path
        输出 PNG 路径。
    title : str
        图标题。

    Returns
    -------
    str | None
        保存路径；无数据时返回 None。
    """
    import matplotlib

    matplotlib.use("Agg")  # 无界面后端，直接存文件
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    if equity_curve is None or getattr(equity_curve, "empty", True):
        return None

    # 中文字体（Windows 优先微软雅黑/黑体；缺字时回退）
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    eq = equity_curve.sort_index()
    # 累计收益 (%)：净值从 1 起算
    cum_ret = (eq - 1.0) * 100.0
    # 回撤 (%)：取正值，越大回撤越深
    running_max = eq.cummax()
    drawdown = -((eq - running_max) / running_max) * 100.0  # 负回撤取正
    drawdown = drawdown.clip(lower=0.0)

    fig, ax1 = plt.subplots(figsize=(12, 5))

    # 左轴：累计收益
    ax1.plot(eq.index, cum_ret.values, color="#1f77b4", linewidth=1.2, label="累计收益")
    ax1.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax1.set_ylabel("累计收益 (%)", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")

    # 右轴：回撤（正数，向上填充 -> 0 在底贴近 x 轴、越深越上）
    ax2 = ax1.twinx()
    ax2.fill_between(eq.index, 0, drawdown.values, color="#d62728", alpha=0.35)
    ax2.plot(eq.index, drawdown.values, color="#d62728", linewidth=0.8)
    ax2.set_ylabel("回撤 (%)", color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    if drawdown.max() > 0:
        ax2.set_ylim(bottom=0, top=drawdown.max() * 1.1)

    # x 轴只标年份
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.grid(True, axis="y", alpha=0.25)

    ax1.set_title(title)
    fig.tight_layout()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


def plot_group_ic(
    factor_values,
    forward_returns,
    path,
    n_groups: int = 5,
    method: str = "pearson",
    title: str = "分组 IC",
) -> str | None:
    """绘制分组 IC 柱状图：按因子值分位分组，各组组内 IC 均值。

    每个截面按因子值升序分 N 组（Q1=因子值最低 … QN=最高），在组内计算因子值
    与远期收益的截面相关（组内 IC），再对日期取均值，柱状展示——定位因子预测力
    集中在哪些因子值区间。

    Parameters
    ----------
    factor_values : pd.DataFrame
        因子值 ``日期×标的``。
    forward_returns : pd.DataFrame
        远期收益 ``日期×标的``，与 factor_values 对齐（日期/标的取交集）。
    path : str | Path
        输出 PNG 路径。
    n_groups : int
        分组数（默认 5）。
    method : str
        组内相关：``"pearson"``（默认，与 IC 指标一致）或 ``"rank"``（Spearman，小样本更稳）。
    title : str
        图标题。

    Returns
    -------
    str | None
        保存路径；无数据或分组后样本不足时返回 None。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if (
        factor_values is None or forward_returns is None
        or getattr(factor_values, "empty", True) or getattr(forward_returns, "empty", True)
    ):
        return None

    # 中文字体（Windows 优先微软雅黑/黑体；缺字时回退）
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    # 对齐日期/标的
    common_dates = factor_values.index.intersection(forward_returns.index)
    common_symbols = factor_values.columns.intersection(forward_returns.columns)
    fv = factor_values.loc[common_dates, common_symbols]
    fr = forward_returns.loc[common_dates, common_symbols]

    min_per_group = 5  # 组内相关至少需要的样本数
    use_rank = method == "rank"

    # ---- 向量化：一次性算出每日每标的的分组号（无逐日 Python 循环）----
    valid = fv.notna() & fr.notna()
    n_per_day = valid.sum(axis=1).to_numpy()
    # 仅在有效单元格上按行升序排名（method="first" 避免并列跨组）
    ranks = fv.where(valid).rank(axis=1, ascending=True, method="first")
    ranks_np = ranks.to_numpy().astype(float)
    n_np = n_per_day[:, None].astype(float)
    with np.errstate(all="ignore"):
        # 组号 1..n_groups；无效位置为 NaN（后续 mask 自然排除）
        group_np = (ranks_np - 1) * n_groups // n_np + 1
    # 整日有效样本不足 -> 全 NaN（等价原逐日 continue）
    group_np[n_per_day < n_groups * min_per_group, :] = np.nan

    fv_np = fv.to_numpy(dtype="float")
    fr_np = fr.to_numpy(dtype="float")

    group_ic_vals = {g: [] for g in range(1, n_groups + 1)}  # 组号 -> 各日 IC 列表
    for g in range(1, n_groups + 1):
        mask = group_np == g  # (T, N) bool
        if not mask.any():
            continue
        if use_rank:
            # 组内排名（Spearman）：在组内有效值上按行排名
            a = np.where(mask, fv_np, np.nan)
            b = np.where(mask, fr_np, np.nan)
            a = pd.DataFrame(a, index=fv.index, columns=fv.columns).rank(
                axis=1, method="average"
            ).to_numpy()
            b = pd.DataFrame(b, index=fv.index, columns=fv.columns).rank(
                axis=1, method="average"
            ).to_numpy()
        else:
            a, b = fv_np, fr_np
        ic_per_day = _rowwise_corr(a, b, mask, min_per_group)
        valid_ics = ic_per_day[~np.isnan(ic_per_day)]
        group_ic_vals[g].extend(float(x) for x in valid_ics)

    # 各组 IC 取日期均值
    group_ic = {g: sum(v) / len(v) for g, v in group_ic_vals.items() if v}
    if not group_ic:
        return None

    order = sorted(group_ic)
    labels = [f"Q{g}" for g in order]
    values = [group_ic[g] for g in order]
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in values]  # 绿正红负

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        labels, values, color=colors, alpha=0.85,
        edgecolor="black", linewidth=0.5, width=0.6,
    )
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_ylabel("组内 IC 均值")
    ax.set_xlabel("因子值分位组（Q1=最低 … QN=最高）")
    ax.set_title(title)
    # 柱顶/柱底标数值
    span = max(abs(v) for v in values) or 1.0
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            v + (0.04 * span if v >= 0 else -0.04 * span),
            f"{v:.3f}", ha="center",
            va="bottom" if v >= 0 else "top", fontsize=9,
        )
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)
