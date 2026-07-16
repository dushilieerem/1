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


def _yearly_stats(equity_curve, periods_per_year: int = 252):
    """按自然年统计年化收益 / 最大回撤 / calmar。

    - 年化 = (1 + 当年累计收益)^(periods_per_year / 当年交易日数) - 1
      （完整年份与当年总收益等价；首末不完整年份按实际交易日数年化外推）
    - 回撤 = 当年内的最大回撤（负值，与 ``metrics.max_drawdown`` 口径一致；
      以上一年末净值为峰值种子，跨年下跌计入新年）
    - calmar = 年化 / |回撤|（当年无回撤时为 NaN）

    Parameters
    ----------
    equity_curve : pd.Series
        净值曲线（DatetimeIndex）。
    periods_per_year : int
        年化周期数（默认 252）。

    Returns
    -------
    years : list[int]
        升序年份列表。
    stats : dict[str, list[float]]
        ``{"年化": [...], "回撤": [...], "calmar": [...]}``，按 years 顺序对齐。
    """
    eq = equity_curve.sort_index()
    if isinstance(eq, pd.DataFrame):  # 防御：误传单列 DataFrame
        eq = eq.iloc[:, 0]
    if eq.empty:
        return [], {"年化": [], "回撤": [], "calmar": []}

    years = sorted(set(eq.index.year))
    stats = {"年化": [], "回撤": [], "calmar": []}
    prev_end = None  # 上一年末净值（用于当年收益与跨年回撤种子）
    for y in years:
        sub = eq[eq.index.year == y]
        n = len(sub)
        if n < 2:
            ann = max_dd = calmar = float("nan")
        else:
            start_val = float(sub.iloc[0]) if prev_end is None else prev_end
            end_val = float(sub.iloc[-1])
            total = end_val / start_val - 1.0
            ann = (1.0 + total) ** (periods_per_year / n) - 1.0
            # 当年回撤：以上一年末净值种子，捕获开年即跌
            vals = sub.to_numpy(dtype=float)
            if prev_end is not None:
                vals = np.concatenate([[prev_end], vals])
            running_max = np.maximum.accumulate(vals)
            with np.errstate(invalid="ignore"):
                dd = (vals - running_max) / running_max
            max_dd = float(np.nanmin(dd))
            calmar = ann / abs(max_dd) if max_dd < 0 else float("nan")
        stats["年化"].append(ann)
        stats["回撤"].append(max_dd)
        stats["calmar"].append(calmar)
        if n >= 1:
            prev_end = float(sub.iloc[-1])
    return years, stats


def _draw_yearly_stats_table(ax, years, stats) -> None:
    """在已 ``axis('off')`` 的 ax 上绘制年度统计表。

    行：年化 / 回撤 / calmar；列：年份。数值按正负染色（绿正红负）。
    """
    rows = ["年化", "回撤", "calmar"]

    def _fmt(v, kind):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "—"
        if kind == "calmar":
            return f"{v:.2f}"
        return f"{v * 100:.1f}%"

    cell_text = [
        [_fmt(stats[r][i], r) for i in range(len(years))]
        for r in rows
    ]
    table = ax.table(
        cellText=cell_text,
        rowLabels=rows,
        colLabels=[str(y) for y in years],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.45)

    # 样式：表头/行名 灰底加粗；数据格按正负染色
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if r == 0 or c == -1:  # 列表头行 / 行名列
            cell.set_facecolor("#f0f0f0")
            cell.set_text_props(weight="bold")
        else:  # 数据格：r in 1..3, c in 0..len(years)-1
            val = stats[rows[r - 1]][c]
            if isinstance(val, float) and not np.isnan(val):
                color = "#2ca02c" if val > 0 else "#d62728"
                cell.set_text_props(color=color)


def plot_equity_drawdown(
    equity_curve,
    path,
    title: str = "累计收益 - 回撤",
    periods_per_year: int = 252,
    show_yearly_table: bool = True,
    benchmark=None,
) -> str | None:
    """绘制累计收益-回撤双轴图，并在下方附年度统计表（年化/回撤/calmar × 年份）。

    Parameters
    ----------
    equity_curve : pd.Series
        净值曲线（起点 1.0，DatetimeIndex）。
    path : str | Path
        输出 PNG 路径。
    title : str
        图标题。
    periods_per_year : int
        年化周期数（默认 252），用于年度年化收益换算。
    show_yearly_table : bool
        是否绘制下方年度统计表（默认 True）。

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

    # 上图 + 下表：gridspec 控制高度比（无表时退化为单图）
    has_table = show_yearly_table
    fig = plt.figure(figsize=(12, 7.8 if has_table else 5.0))
    if has_table:
        gs = fig.add_gridspec(2, 1, height_ratios=[3.2, 1.0], hspace=0.25)
        ax1 = fig.add_subplot(gs[0])
        ax_t = fig.add_subplot(gs[1])
    else:
        ax1 = fig.add_subplot(111)
        ax_t = None

    # 左轴：累计收益
    ax1.plot(eq.index, cum_ret.values, color="#1f77b4", linewidth=1.2, label="累计收益")
    # 基准（可选）：叠加累计收益虚线，起点对齐 0
    if benchmark is not None and not getattr(benchmark, "empty", True):
        bench = benchmark.sort_index().reindex(eq.index).ffill()
        bench_cum = (bench - 1.0) * 100.0
        ax1.plot(
            bench_cum.index, bench_cum.values, color="#ff7f0e",
            linewidth=1.0, linestyle="--", label="基准(市值加权)",
        )
    ax1.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax1.set_ylabel("累计收益 (%)", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.legend(loc="upper left", fontsize=9)

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

    # 下方年度统计表
    if ax_t is not None:
        ax_t.axis("off")
        years, stats = _yearly_stats(eq, periods_per_year=periods_per_year)
        if years:
            _draw_yearly_stats_table(ax_t, years, stats)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
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


def _daily_ic_series(factor_values, forward_returns, method: str = "pearson") -> pd.Series:
    """每日截面 IC 序列（与 IC 指标同口径：截面相关，逐行计算）。

    Parameters
    ----------
    factor_values, forward_returns : pd.DataFrame
        因子值 / 远期收益 ``日期×标的``，取日期/标的交集。
    method : str
        ``"pearson"``（默认，与 IC 指标一致）或 ``"rank"``（RankIC 口径）。

    Returns
    -------
    pd.Series
        每日 IC，索引为日期；NaN 行已丢弃。无数据返回空 Series。
    """
    if (
        factor_values is None or forward_returns is None
        or getattr(factor_values, "empty", True) or getattr(forward_returns, "empty", True)
    ):
        return pd.Series(dtype=float)
    common_dates = factor_values.index.intersection(forward_returns.index)
    common_symbols = factor_values.columns.intersection(forward_returns.columns)
    fv = factor_values.loc[common_dates, common_symbols]
    fr = forward_returns.loc[common_dates, common_symbols]
    if method == "rank":
        fv = fv.rank(axis=1)
        fr = fr.rank(axis=1)
    return fv.corrwith(fr, axis=1).dropna()


def plot_ic_analysis(
    factor_values,
    forward_returns,
    path,
    window: int = 60,
    method: str = "pearson",
    bins: int = 50,
    title: str = "IC 分析",
) -> "str | None":
    """绘制 IC 分析四联图：日频 IC / 累计 IC / IC 分布 / 滚动 IR（window 日）。

    每日 IC = 因子值与远期收益的截面相关（与 IC 指标同口径）；滚动 IR =
    滚动 window 日 IC 均值 / 标准差。

    Parameters
    ----------
    factor_values, forward_returns : pd.DataFrame
        因子值 / 远期收益 ``日期×标的``，取日期/标的交集。
    path : str | Path
        输出 PNG 路径。
    window : int
        滚动 IR 窗口（默认 60 交易日）。
    method : str
        ``"pearson"``（默认，与 IC 指标一致）或 ``"rank"``（RankIC 口径）。
    bins : int
        分布图柱数。
    title : str
        总标题。

    Returns
    -------
    str | None
        保存路径；IC 样本不足（< 2 日）返回 None。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    ic = _daily_ic_series(factor_values, forward_returns, method=method)
    if len(ic) < 2:
        return None

    # 中文字体（Windows 优先微软雅黑/黑体；缺字时回退）
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    cum = ic.cumsum()
    mean_ic = float(ic.mean())
    rolling_ir = (ic.rolling(window).mean() / ic.rolling(window).std()).dropna()

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax1, ax2, ax3, ax4 = axes.ravel()
    fig.suptitle(title, fontsize=14)

    # 1) 日频 IC
    ax1.plot(ic.index, ic.values, color="#1f77b4", linewidth=0.8)
    ax1.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax1.axhline(
        mean_ic, color="#ff7f0e", linewidth=1.0, linestyle=":",
        label=f"均值 {mean_ic:.3f}",
    )
    ax1.set_title("日频 IC")
    ax1.set_ylabel("IC")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.25)
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 2) 累计 IC
    ax2.plot(cum.index, cum.values, color="#2ca02c", linewidth=1.0)
    ax2.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax2.set_title("累计 IC")
    ax2.set_ylabel("累计 IC")
    ax2.grid(True, alpha=0.25)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 3) IC 分布
    ax3.hist(
        ic.values, bins=bins, color="#9467bd", alpha=0.85,
        edgecolor="black", linewidth=0.3,
    )
    ax3.axvline(
        mean_ic, color="#ff7f0e", linewidth=1.0, linestyle=":",
        label=f"均值 {mean_ic:.3f}",
    )
    ax3.set_title("IC 分布")
    ax3.set_xlabel("IC")
    ax3.set_ylabel("频数")
    ax3.legend(loc="upper right", fontsize=8)
    ax3.grid(True, alpha=0.25)

    # 4) 滚动 IR（window 日）
    if len(rolling_ir) > 0:
        ax4.plot(rolling_ir.index, rolling_ir.values, color="#d62728", linewidth=0.8)
        ax4.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    else:
        ax4.text(
            0.5, 0.5, f"样本不足（需 ≥ {window} 日有效 IC）",
            ha="center", va="center", transform=ax4.transAxes, fontsize=10,
        )
    ax4.set_title(f"滚动 IR（{window}日）")
    ax4.set_ylabel("IR")
    ax4.grid(True, alpha=0.25)
    ax4.xaxis.set_major_locator(mdates.YearLocator())
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.tight_layout(rect=[0, 0, 1, 0.97])

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


def plot_layered_equity(
    layered_equity_df,
    path,
    title: str = "分层回测累计收益",
    benchmark=None,
) -> str | None:
    """绘制分层回测各组累计收益曲线（Q1 最低组 … QN 最高组），可选叠基准。

    Parameters
    ----------
    layered_equity_df : pd.DataFrame
        :func:`researchengine.layered.layered_equity` 的输出，列名 ``Q1..QN``，起点 1.0。
    path : str | Path
        输出 PNG 路径。
    title : str
        图标题。
    benchmark : pd.Series, optional
        基准净值曲线（起点 1.0），叠加为虚线。

    Returns
    -------
    str | None
        保存路径；空数据返回 None。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    if layered_equity_df is None or getattr(layered_equity_df, "empty", True):
        return None
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    df = layered_equity_df.sort_index()
    n = len(df.columns)
    colors = plt.cm.viridis(np.linspace(0.05, 0.85, n))

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, col in enumerate(df.columns):
        cum = (df[col] - 1.0) * 100.0
        ax.plot(df.index, cum.values, color=colors[i], linewidth=1.0, label=col)
    if benchmark is not None and not getattr(benchmark, "empty", True):
        bench = benchmark.sort_index().reindex(df.index).ffill()
        ax.plot(
            bench.index, ((bench - 1.0) * 100.0).values,
            color="gray", linewidth=1.0, linestyle="--", label="基准",
        )
    ax.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax.set_ylabel("累计收益 (%)")
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=9, ncol=max(1, (n // 5) + 1))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_long_short(
    equity_curve,
    path,
    title: str = "多空累计收益 - 回撤",
    periods_per_year: int = 252,
) -> str | None:
    """绘制多空组合累计收益 - 回撤图（不附年度表）。委托 :func:`plot_equity_drawdown`。

    Parameters
    ----------
    equity_curve : pd.Series
        多空组合净值曲线（起点 1.0，DatetimeIndex）。
    path, title : 见 :func:`plot_equity_drawdown`。
    periods_per_year : int
        年化周期数（透传，用于年度统计；本图默认不画表故不生效）。

    Returns
    -------
    str | None
        保存路径；空数据返回 None。
    """
    return plot_equity_drawdown(
        equity_curve, path, title=title,
        periods_per_year=periods_per_year, show_yearly_table=False,
    )


def plot_industry_ic_ir(
    industry_df,
    path,
    title: str = "分行业 IC / IR",
) -> str | None:
    """绘制分行业 IC / IR 柱状图（IC 正绿负红，IR 同色，上下双图）。

    Parameters
    ----------
    industry_df : pd.DataFrame
        :func:`researchengine.riskmodel.industry_ic_ir` 的输出，
        列 ``[industry, ic, ir, n_obs]``。
    path : str | Path
        输出 PNG 路径。
    title : str
        图标题。

    Returns
    -------
    str | None
        空数据返回 None。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if industry_df is None or getattr(industry_df, "empty", True) or len(industry_df) == 0:
        return None
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    df = industry_df.sort_values("ic", ascending=True).reset_index(drop=True)
    labels = df["industry"].astype(str).tolist()
    ic = df["ic"].to_numpy()
    ir = df["ir"].to_numpy()
    ic_colors = ["#2ca02c" if v >= 0 else "#d62728" for v in ic]
    ir_colors = ["#2ca02c" if (not np.isnan(v) and v >= 0) else "#d62728" for v in ir]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(max(8, len(labels) * 0.55), 6), sharex=True,
    )
    ax1.bar(labels, ic, color=ic_colors)
    ax1.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax1.set_ylabel("IC")
    ax1.set_title(title)
    ax1.grid(True, axis="y", alpha=0.25)

    ax2.bar(labels, np.nan_to_num(ir, nan=0.0), color=ir_colors)
    ax2.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax2.set_ylabel("IR")
    ax2.grid(True, axis="y", alpha=0.25)
    plt.setp(ax2.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    fig.tight_layout()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_ff3_attribution(
    reg,
    path,
    title: str = "三因子归因",
) -> str | None:
    """绘制三因子归因图：alpha(年化) + 各因子 beta 系数柱，标注 t 值与显著性。

    显著性：``|t|>2.58`` 标 ``**``，``|t|>1.96`` 标 ``*``。标题含 R² 与样本数。

    Parameters
    ----------
    reg : dict
        :func:`researchengine.riskmodel.ff3_regression` 的输出。
    path : str | Path
        输出 PNG 路径。
    title : str
        图标题。

    Returns
    -------
    str | None
        回归无有效结果（``n_obs=0`` 或 alpha 为 NaN）返回 None。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if reg is None or reg.get("n_obs", 0) == 0 or np.isnan(reg.get("alpha", float("nan"))):
        return None
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    labels = ["alpha(年化)", "β_MKT", "β_SMB", "β_HML"]
    vals = [reg["alpha"], reg["beta_mkt"], reg["beta_smb"], reg["beta_hml"]]
    tvals = [reg["t_alpha"], reg["t_beta_mkt"], reg["t_beta_smb"], reg["t_beta_hml"]]

    def _sig(t):
        if np.isnan(t):
            return ""
        if abs(t) > 2.58:
            return "**"
        if abs(t) > 1.96:
            return "*"
        return ""

    sigs = [_sig(t) for t in tvals]
    colors = ["#ff7f0e", "#1f77b4", "#2ca02c", "#d62728"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, vals, color=colors)
    span = max(vals) - min(vals) if max(vals) != min(vals) else 1.0
    for b, v, t, s in zip(bars, vals, tvals, sigs):
        yt = v + span * 0.02 if v >= 0 else v - span * 0.02
        ax.text(
            b.get_x() + b.get_width() / 2, yt,
            f"{v:.3f}\n(t={t:.1f}){s}", ha="center",
            va="bottom" if v >= 0 else "top", fontsize=9,
        )
    ax.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax.set_ylabel("系数")
    r2 = reg.get("r_squared", float("nan"))
    ax.set_title(f"{title}  (R²={r2:.3f}, n={reg['n_obs']})")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return str(out)
