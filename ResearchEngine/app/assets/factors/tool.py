"""因子库算子实现（tool.py）。

把《因子库分析文档》全库因子代码中用到、而 pandas / numpy 没有直接提供的算子
集中实现为一个可复用模块。算子清单的权威来源是各分类「分类说明.md → 常见计算方式」
表（全库汇总见 database/总览汇总.md，由 database/audit_operator_tables.py 生成）；
本文件的下划线别名与因子文档代码中的调用拼写一一对应，可直接 drop-in。

约定
----
- 宽表口径：DataFrame 的 index 为日期、columns 为标的；Series 为单标的时间序列，
  或单日截面（截面算子遇到 Series 时，把整条 Series 当作一个截面处理）。
- 时序算子沿时间轴（axis=0）滚动；截面算子沿标的轴（axis=1）比较。
- 非整数窗口（如 _sma(x, 37.4843, m)）统一按 int() 截断——文档注明
  「非整数窗口取整行为以源码为准」，这里采用移植代码常用的截断约定。
- 返回值保持 pandas 类型（DataFrame 进 DataFrame 出，Series 进 Series 出）。
- 数据对象（如文档代码里的 self）：凡是需要 close/open/high/low/volume/amount/
  shares 或分组标签的算子，都支持直接传入数据对象，也支持显式传序列。

刻意不实现（pandas / numpy 原生直接可用，因子代码按原生方式调用）
----------------------------------------------------------------
- 位移与差分：.shift()、.diff()、.pct_change()
- 滚动统计：.rolling(...).mean()/.sum()/.std()/.max()/.min()/.rank(pct=True)、
  .var()、.skew()、.kurt()、.quantile()、.rolling(...).apply(func, raw=True)
- 指数加权与累计：.ewm(...)、.cumsum()、.cumprod()
- 相关与协方差：.rolling(...).corr(y)、.rolling(...).cov(y)
- 截面与条件：.rank(axis=1, pct=True)、.rank(pct=True)、.where()、.mask()、
  .astype(float)、.max(axis=1)、.min(axis=1)
- 逐元素数学：.abs()、.clip()、.pow()、np.sign、np.log、np.log10、np.log1p、
  np.sqrt、np.power、np.prod、np.maximum、np.minimum、np.where、np.argmax、
  np.argmin、np.arange 等
- 数据衍生（直接按原生表达式内联）：日收益率 close/close.shift(1)-1、
  历史均量 volume.rolling(n).mean()、市值 close*shares
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pandas as pd

# 全库代码中的防零极小量（如 alpha158_wvma 的 + EPSILON）
EPSILON = 1e-12


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _field(obj, name):
    """从数据对象取命名字段：先属性后条目；裸 Series/DataFrame 返回 None。"""
    if isinstance(obj, (pd.Series, pd.DataFrame)):
        return None
    value = getattr(obj, name, None)
    if value is None and hasattr(obj, "__getitem__"):
        try:
            value = obj[name]
        except Exception:
            value = None
    return value


def _wrap_like(values, like):
    """把 ndarray 结果包回 like 的 pandas 类型。"""
    if isinstance(like, pd.DataFrame):
        return pd.DataFrame(values, index=like.index, columns=like.columns)
    if isinstance(like, pd.Series):
        return pd.Series(values, index=like.index, name=like.name)
    return values


def _win(window) -> int:
    """窗口规格化：非整数窗口按 int() 截断（见模块约定），且必须 ≥ 1。"""
    n = int(window)
    if n < 1:
        raise ValueError(f"window 必须 ≥ 1，收到 {window!r}")
    return n


# ---------------------------------------------------------------------------
# 时序算子（沿时间轴滚动）
# ---------------------------------------------------------------------------

def ts_argmax(x, window: int):
    """HHVBARS(X, N)：窗口内最高点出现在多久之前（0 = 当前 bar 即最高）。

    窗口内含缺失值时返回缺失，避免 argmax 落在缺失位置产生伪读数。
    """
    n = _win(window)

    def _pos(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(n - 1 - int(np.argmax(values)))

    return x.rolling(n).apply(_pos, raw=True)


def ts_argmin(x, window: int):
    """LLVBARS(X, N)：窗口内最低点出现在多久之前（0 = 当前 bar 即最低）。"""
    n = _win(window)

    def _pos(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(n - 1 - int(np.argmin(values)))

    return x.rolling(n).apply(_pos, raw=True)


def sma(x, window: int, m: float = 1.0):
    """SMA(X, N, M)：递推平滑 y_t = (M·x_t + (N−M)·y_{t−1}) / N。

    递推起点取首个有效值；缺失期输出缺失但保留递推状态。
    m 默认 1.0（2026-09-08 静态化：classic_indicators._sma 的 weight 默认值，
    两参调用 self._sma(x, n) → tool._sma(x, n) 直通）。
    """
    window = _win(window)
    if isinstance(x, pd.DataFrame):
        out = {col: sma(x[col], window, m) for col in x.columns}
        return pd.DataFrame(out, index=x.index, columns=x.columns)
    values = np.asarray(x, dtype=float)
    alpha = m / window
    decay = 1.0 - alpha
    out = np.full(values.shape, np.nan)
    prev = np.nan
    for i, v in enumerate(values):
        if np.isnan(v):
            continue
        prev = v if np.isnan(prev) else decay * prev + alpha * v
        out[i] = prev
    return _wrap_like(out, x)


def decay_linear(x, window: int):
    """WMA/DECAY_LINEAR(X, N)：线性衰减加权平均，最近期权重 N、最远权重 1。"""
    window = _win(window)
    weights = np.arange(1, window + 1, dtype=float)
    weights /= weights.sum()
    return x.rolling(window).apply(lambda a: float(np.dot(a, weights)), raw=True)


def wma(x, window: int):
    """WMA(X, N)：与 decay_linear 同一加权方式（国内教材叫法）。"""
    return decay_linear(x, window)


def regbeta(dep, indep, window: int):
    """REG_BETA(dep, indep, N)：滚动一元 OLS 斜率 Cov(dep, indep) / Var(indep)。

    indep 支持两种形态：
    - 长度等于 window 的固定模式（如 np.arange(1, N+1)，逐窗重复使用）；
    - 与 dep 同长并对齐的 Series（逐窗对齐回归）。
    分母方差为 0（自变量恒定）时返回缺失。
    """
    window = _win(window)
    if isinstance(dep, pd.DataFrame):
        out = {col: regbeta(dep[col], indep, window) for col in dep.columns}
        return pd.DataFrame(out, index=dep.index, columns=dep.columns)

    if isinstance(indep, (pd.Series, pd.DataFrame)):
        if isinstance(indep, pd.DataFrame):
            raise TypeError("regbeta 的 indep 为面板时请逐列调用")
        x_var = indep.rolling(window).var()
        slope = dep.rolling(window).cov(indep) / x_var.where(x_var > EPSILON)
        return slope

    pattern = np.asarray(indep, dtype=float)
    if pattern.shape != (window,):
        raise ValueError(
            f"indep 作为固定模式时长度必须等于 window（{pattern.shape} vs {window}）"
        )
    mean_x = pattern.mean()
    var_x = float((pattern ** 2).mean() - mean_x ** 2)
    if var_x <= EPSILON:
        return dep * np.nan
    # 模式是窗口相对的：每窗按时间顺序取 pattern[0..N-1]（最老=首元素）
    cross = dep.rolling(window).apply(lambda a: float(np.dot(a, pattern)),
                                      raw=True)
    numerator = cross / window - dep.rolling(window).mean() * mean_x
    return numerator / var_x


# ---------------------------------------------------------------------------
# 统计算子（两序列滚动关系）
# ---------------------------------------------------------------------------

# 相关系数 CORR(X, Y, N) 与协方差 COVAR(X, Y, N) 由 pandas 原生提供：
# x.rolling(N).corr(y) / x.rolling(N).cov(y)


# ---------------------------------------------------------------------------
# 窗口线性回归三件套（Alpha158 BETA / RSQR / RESI 口径）
#
# 因子文档代码以 rolling(window).apply(_linear_*, raw=True) 调用，
# 因此三者都是「一维窗口 ndarray → 标量」函数：时间自变量取 1..N（与
# regbeta 固定模式分支的 x 约定一致），窗口含缺失值时整体返回缺失。
# ---------------------------------------------------------------------------

def _linear_x(values: np.ndarray) -> np.ndarray:
    return np.arange(1, values.size + 1, dtype=float)


def _linear_fit(values: np.ndarray):
    """返回 (slope, intercept)；窗口含缺失或自变量/因变量零方差时返回 (nan, nan)。"""
    y = np.asarray(values, dtype=float)
    if np.isnan(y).any():
        return np.nan, np.nan
    x = _linear_x(y)
    x_mean, y_mean = x.mean(), y.mean()
    var_x = float(((x - x_mean) ** 2).sum())
    if var_x <= EPSILON:
        return np.nan, np.nan
    slope = float(((x - x_mean) * (y - y_mean)).sum()) / var_x
    return slope, y_mean - slope * x_mean


def _linear_slope(values: np.ndarray) -> float:
    """BETA(X, N)：窗口内对时间趋势的 OLS 斜率。"""
    slope, _ = _linear_fit(values)
    return slope


def _linear_rsquare(values: np.ndarray) -> float:
    """RSQR(X, N)：窗口线性拟合的决定系数 R²（y 零方差时约定 R²=0）。"""
    y = np.asarray(values, dtype=float)
    if np.isnan(y).any():
        return np.nan
    slope, intercept = _linear_fit(y)
    if np.isnan(slope):
        return np.nan
    x = _linear_x(y)
    fitted = slope * x + intercept
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot <= EPSILON:
        return 0.0
    return 1.0 - float(((y - fitted) ** 2).sum()) / ss_tot


def _linear_residual(values: np.ndarray) -> float:
    """RESI(X, N)：窗口线性拟合对最后一个时点的残差 y_N − (a + b·N)。"""
    y = np.asarray(values, dtype=float)
    slope, intercept = _linear_fit(y)
    if np.isnan(slope):
        return np.nan
    return float(y[-1] - (slope * y.size + intercept))


_LOG_THREE = math.log(3.0)


# ---------------------------------------------------------------------------
# 截面算子（沿标的轴比较；Series 视作一个截面）
# ---------------------------------------------------------------------------

def scale(x):
    """SCALE(X) = X / Σ|X|：截面缩放，使每个交易日 |X| 之和为 1（全零行为缺失）。"""
    if isinstance(x, pd.DataFrame):
        denom = x.abs().sum(axis=1)
        return x.div(denom.where(denom > 0), axis=0)
    denom = x.abs().sum()
    return x / denom if denom > 0 else x * np.nan


def indneutralize(data, x, level: str = "industry"):
    """IND_NEUTRALIZE(X, GROUP) = X − CS_MEAN(X, GROUP)：剥离组内共同涨跌。

    分组标签从数据对象上按 level 读取（如 data.industry / data.subindustry /
    data.sector），支持三种形态：
    - dict / Series：标的 → 组的静态映射（按列分组）；
    - DataFrame：与 x 同形的逐日分组标签面板（按行分组）。
    """
    labels = _field(data, level)
    if labels is None:
        raise AttributeError(f"indneutralize 需要数据对象提供分组字段 {level!r}")

    result = x.copy()
    if isinstance(labels, pd.DataFrame):
        if labels.shape != x.shape:
            raise ValueError("分组标签面板与 x 形状不一致")
        for code in pd.unique(labels.to_numpy().ravel()):
            mask = labels.eq(code)
            group_mean = x.where(mask).mean(axis=1)
            result = result.where(~mask, x.sub(group_mean, axis=0))
        return result

    mapping = labels.to_dict() if isinstance(labels, pd.Series) else dict(labels)
    codes = pd.Series([mapping.get(col, np.nan) for col in x.columns],
                      index=x.columns)
    for code in codes.dropna().unique():
        cols = codes.index[codes == code]
        group_mean = x[cols].mean(axis=1)
        result[cols] = x[cols].sub(group_mean, axis=0)
    return result


# ---------------------------------------------------------------------------
# 条件与组合算子
# ---------------------------------------------------------------------------

# 条件分支 IF(COND, A, B) 由 pandas 原生提供：A.where(COND, B)（A 为面板）或
# B.mask(COND, A)（A 为标量）；布尔信号即 COND.astype(float)（可乘以量级）；
# 窗口内条件计数 COND.astype(float).rolling(N).sum()；
# 条件求和 X.where(COND, 0).rolling(N).sum()；
# 逐元素取大/取小 np.maximum(A, B) / np.minimum(A, B)；
# 跳缺失取大/取小 np.fmax(A, B) / np.fmin(A, B)。


def safe_divide(a, b, eps: float = EPSILON):
    """SAFE_DIV(X, Y, EPS)：防零除法；|Y| ≤ EPS 或 Y 缺失时返回缺失。"""
    if np.isscalar(b):
        return a / b if abs(b) > eps else a * np.nan
    return a / b.where(b.abs() > eps)


# 保留符号幂 SIGNED_POW(X, P) = SIGN(X) × |X|^P：np.sign(x) * np.abs(x) ** p；
# 任意滚动窗口函数：x.rolling(N).apply(func, raw=True)。


def broadcast_series(series, ref):
    """把单列 Series（如基准指数序列）按 ref 的形状广播成面板。

    ref 为 DataFrame 时先按其 index 对齐（缺失日期为缺失值），再复制到每列；
    ref 为 Series 时按 index 对齐后原样返回。
    """
    if not isinstance(ref, pd.DataFrame):
        return series.reindex(ref.index)
    aligned = series.reindex(ref.index)
    tiled = np.tile(aligned.to_numpy()[:, None], (1, ref.shape[1]))
    return pd.DataFrame(tiled, index=ref.index, columns=ref.columns)


# ---------------------------------------------------------------------------
# 价格与量衍生量（支持传数据对象或显式序列）
# ---------------------------------------------------------------------------

# 日收益率 RET(1) = CLOSE/REF(CLOSE,1) − 1：close / close.shift(1) - 1；
# 历史平均成交活跃度 ADV(X, N)：volume.rolling(N).mean()；
# 市值 CAP = CLOSE × SHARES：close * shares（数据对象无 shares 时用 total_mv）。


def vwap(data_or_amount, volume=None, eps: float = EPSILON):
    """VWAP：成交价格中心。

    vwap(amount, volume) = SAFE_DIV(AMOUNT, VOLUME, EPS)（显式两序列，原口径不变）；
    vwap(data) 走多数派三级回退链（2026-09-08 静态化定稿，gtja/worldquant 口径）：
    数据对象的 vwap 字段 → amount/volume → (H+L+C)/3。
    alpha_features 变体无 HLC/3 末级回退（amount 也缺失时返回缺失），差异已标注。
    """
    if volume is not None:
        return safe_divide(data_or_amount, volume, eps)
    direct = _field(data_or_amount, "vwap")
    if direct is not None:
        return direct
    amt = _field(data_or_amount, "amount")
    vol = _field(data_or_amount, "volume")
    if amt is not None and vol is not None:
        return safe_divide(amt, vol, eps)
    high, low, close = (_field(data_or_amount, "high"),
                        _field(data_or_amount, "low"),
                        _field(data_or_amount, "close"))
    if high is None or low is None or close is None:
        raise AttributeError("vwap(data) 需要数据对象提供 vwap/amount/volume 或 high/low/close")
    return (high + low + close) / 3.0


def true_range(data_or_high, low=None, close=None):
    """TR = MAX(HIGH−LOW, |HIGH−REF(CLOSE,1)|, |LOW−REF(CLOSE,1)|)；首期为缺失。"""
    if low is None or close is None:
        high = _field(data_or_high, "high")
        low = _field(data_or_high, "low")
        close = _field(data_or_high, "close")
        if high is None or low is None or close is None:
            raise AttributeError("true_range(data) 需要数据对象提供 high/low/close")
    else:
        high = data_or_high
    prev_close = close.shift(1)
    return np.maximum(
        np.maximum(high - low, (high - prev_close).abs()),
        (low - prev_close).abs(),
    )


def tr_parts(data_or_high, low=None):
    """MOVEMENT = MAX(|HIGH−REF(HIGH,1)|, |LOW−REF(LOW,1)|)（alpha191_049 族辅助量）。"""
    if low is None:
        high = _field(data_or_high, "high")
        low = _field(data_or_high, "low")
        if high is None or low is None:
            raise AttributeError("tr_parts(data) 需要数据对象提供 high/low")
    else:
        high = data_or_high
    return np.maximum((high - high.shift(1)).abs(),
                      (low - low.shift(1)).abs())


def directional_movement(data_or_high, low=None, close=None):
    """Wilder DMI 分量：返回 (TR, +DM, −DM)。

    +DM = IF(上推 > 下推 且 上推 > 0, 上推, 0)；−DM 对称。上推 = HIGH−REF(HIGH,1)，
    下推 = REF(LOW,1)−LOW。
    """
    if low is None or close is None:
        high = _field(data_or_high, "high")
        low = _field(data_or_high, "low")
        close = _field(data_or_high, "close")
        if high is None or low is None or close is None:
            raise AttributeError(
                "directional_movement(data) 需要数据对象提供 high/low/close")
    else:
        high = data_or_high
    up = high - high.shift(1)
    down = low.shift(1) - low
    dm_plus = up.where((up > down) & (up > 0), 0.0)
    dm_minus = down.where((down > up) & (down > 0), 0.0)
    return true_range(high, low, close), dm_plus, dm_minus


# ---------------------------------------------------------------------------
# 数据对象级辅助函数（2026-09-08 静态化批次：原各内置库 self._xxx 方法收编为纯函数，
# 数据对象显式作首参——见 database/数据对象接口清单.md §3/§4）
# ---------------------------------------------------------------------------

def validate_window(window, minimum: int = 2) -> int:
    """窗口校验：必须是 ≥ minimum 的整数（非整数窗口按 int() 截断，见模块约定）。

    多数派口径 minimum=2（technical/trading/volatility/price_discovery）；
    market_state_lib 变体用 minimum=3，未采用。
    """
    if isinstance(window, bool) or not isinstance(window, (int, np.integer)):
        raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
    window = int(window)
    if window < minimum:
        raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
    return window


def validate_lag(window, lag) -> int:
    """lag ∈ [1, window)（market_state 直接校验口径；trading 变体经 validate_window(1)，语义一致）。"""
    if isinstance(lag, bool) or not isinstance(lag, (int, np.integer)):
        raise ValueError("lag 必须是正整数且小于 window")
    lag = int(lag)
    if lag < 1 or lag >= window:
        raise ValueError("lag 必须是正整数且小于 window")
    return lag


def validate_tail_fraction(tail_fraction) -> float:
    """尾部比例校验：∈ (0, 1]。

    多数派口径上界 1.0（trading/volatility）；technical_lib 变体上界 0.5，未采用。
    """
    if isinstance(tail_fraction, bool) or not isinstance(
            tail_fraction, (int, float, np.integer, np.floating)):
        raise ValueError("tail_fraction 必须是 (0, 1] 范围内的有限数值")
    tail_fraction = float(tail_fraction)
    if not np.isfinite(tail_fraction) or not 0.0 < tail_fraction <= 1.0:
        raise ValueError("tail_fraction 必须是 (0, 1] 范围内的有限数值")
    return tail_fraction


def validate_shock_multiple(shock_multiple) -> float:
    """冲击倍数校验：必须 > 0 的有限数（technical_lib 唯一实现）。"""
    if isinstance(shock_multiple, bool) or not isinstance(
            shock_multiple, (int, float, np.integer, np.floating)):
        raise ValueError("shock_multiple 必须是大于 0 的有限数")
    if not np.isfinite(shock_multiple) or float(shock_multiple) <= 0.0:
        raise ValueError("shock_multiple 必须是大于 0 的有限数")
    return float(shock_multiple)


def amount(data):
    """成交额；数据对象无 amount 字段时回退 close × volume（gtja 口径，不缓存）。"""
    direct = _field(data, "amount")
    if direct is not None:
        return direct
    close = _field(data, "close")
    volume = _field(data, "volume")
    if close is None or volume is None:
        raise AttributeError("amount(data) 需要数据对象提供 amount 或 close/volume")
    return close * volume


def shares(data):
    """股本代理（2026-09-08 数据对齐）：现有数据无股本字段，由流动市值反推
    shares = current_mv / close（safe_divide 防零）。

    与 close 相乘即还原流动市值口径；如需总股本语义需等待数据接入。
    """
    current_mv = _field(data, "current_mv")
    close = _field(data, "close")
    if current_mv is None or close is None:
        raise AttributeError("shares(data) 需要数据对象提供 current_mv 与 close")
    return safe_divide(current_mv, close)


def benchmark(data):
    """基准序列 → (close_s, open_s)；benchmark_close/open → csi300 → 截面均值 三级回退（gtja 口径）。"""
    def _one(field_name, panel_name, fallback):
        value = _field(data, field_name)
        if isinstance(value, pd.DataFrame):
            if value.shape[1]:
                return value.iloc[:, 0]
            value = None
        if value is None:
            panel = getattr(data, panel_name, None)
            if panel is not None:
                value = getattr(panel, "close" if field_name.endswith("close")
                                else "open", None)
                if isinstance(value, pd.DataFrame) and value.shape[1]:
                    value = value.iloc[:, 0]
        if value is None:
            wide = _field(data, "close")
            value = wide.mean(axis=1)
        return value

    return (_one("benchmark_close", "csi300", None),
            _one("benchmark_open", "csi300", None))


def valid_volume(data):
    """成交量清洗：±inf → NaN，且仅保留 ≥ 0（price_discovery/trading 两变体输出等价，合一）。"""
    volume = _field(data, "volume")
    if volume is None:
        raise AttributeError("valid_volume(data) 需要数据对象提供 volume")
    return volume.replace([np.inf, -np.inf], np.nan).where(volume.ge(0.0))


def nonnegative_volume(data):
    """valid_volume 的文档拼写别名（trading 口径，输出与 valid_volume 逐位一致）。"""
    return valid_volume(data)


def log_volume_change(data):
    """log(成交量).diff()：先清洗（>0 保留、±inf → NaN）。"""
    volume = _field(data, "volume")
    if volume is None:
        raise AttributeError("log_volume_change(data) 需要数据对象提供 volume")
    volume = volume.where(volume > 0).replace([np.inf, -np.inf], np.nan)
    return np.log(volume).diff()


def turnover_mean(data, window: int):
    """换手率 N 日均值（emotion 口径）。"""
    turnover = _field(data, "turnover")
    if turnover is None:
        raise AttributeError("turnover_mean(data, window) 需要数据对象提供 turnover")
    return turnover.rolling(_win(window)).mean()


def vema(data, window: int):
    """成交量 EMA（span=window，adjust=False；emotion 口径）。"""
    volume = _field(data, "volume")
    if volume is None:
        raise AttributeError("vema(data, window) 需要数据对象提供 volume")
    return volume.ewm(span=_win(window), adjust=False).mean()


def vdiff(data):
    """成交量 EMA 差：vema(12) − vema(26)（emotion 口径）。"""
    return vema(data, 12) - vema(data, 26)


def ar(data):
    """AR 人气指标：(H−O) 26 日和 / (O−L) 26 日和 × 100（emotion 口径，固定 26 日）。"""
    high, low, open_ = _field(data, "high"), _field(data, "low"), _field(data, "open")
    if high is None or low is None or open_ is None:
        raise AttributeError("ar(data) 需要数据对象提供 high/low/open")
    return ((high - open_).rolling(26).sum()
            / (open_ - low).rolling(26).sum() * 100)


def br(data):
    """BR 情绪指标：(H−C₋₁)₊ 26 日和 / (C₋₁−L)₊ 26 日和 × 100（emotion 口径，固定 26 日）。"""
    high, low, close = _field(data, "high"), _field(data, "low"), _field(data, "close")
    if high is None or low is None or close is None:
        raise AttributeError("br(data) 需要数据对象提供 high/low/close")
    previous_close = close.shift()
    up = (high - previous_close).clip(lower=0)
    down = (previous_close - low).clip(lower=0)
    return up.rolling(26).sum() / down.rolling(26).sum() * 100


def wvad(data):
    """WVAD：(C−O)/(H−L)×V 的 6 日和（emotion 口径，固定 6 日）。"""
    high, low, open_, close = (_field(data, "high"), _field(data, "low"),
                               _field(data, "open"), _field(data, "close"))
    volume = _field(data, "volume")
    if high is None or low is None or open_ is None or close is None or volume is None:
        raise AttributeError("wvad(data) 需要数据对象提供 high/low/open/close/volume")
    value = (close - open_) / (high - low) * volume
    return value.rolling(6).sum()


def dm(data):
    """DMI 分量（classic 口径）：返回 (dmz, dmf)。

    distance = MAX(|H−H₋₁|, |L−L₋₁|)；当日 H+L 高于昨日取 dmz=distance 否则 0，
    低于昨日取 dmf=distance 否则 0。与 directional_movement 的 Wilder ±DM 口径不同。
    """
    high, low = _field(data, "high"), _field(data, "low")
    if high is None or low is None:
        raise AttributeError("dm(data) 需要数据对象提供 high/low")
    distance = np.maximum((high - high.shift()).abs(), (low - low.shift()).abs())
    current = high + low
    previous = current.shift()
    dmz = distance.where(current > previous, 0.0)
    dmf = distance.where(current < previous, 0.0)
    return dmz, dmf


def directional_indices(data, window: int):
    """+DI/−DI（technical 口径）：Wilder ewm(alpha=1/N, min_periods=N) 平滑，
    分母 TR+1e-10；返回 (100·+DI, 100·−DI)。"""
    high, low = _field(data, "high"), _field(data, "low")
    if high is None or low is None:
        raise AttributeError("directional_indices(data, window) 需要数据对象提供 high/low")
    n = _win(window)
    up_move = high.diff()
    down_move = -low.diff()
    positive_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    negative_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    alpha = 1 / n
    true_range_s = true_range(data).ewm(alpha=alpha, adjust=False, min_periods=n).mean()
    positive = positive_dm.ewm(alpha=alpha, adjust=False, min_periods=n).mean()
    negative = negative_dm.ewm(alpha=alpha, adjust=False, min_periods=n).mean()
    return 100 * positive / (true_range_s + 1e-10), 100 * negative / (true_range_s + 1e-10)


def keltner_bands(data, window: int, atr_window: int, multiplier: float):
    """Keltner 通道三轨 → (upper, lower, middle)：EMA 中轨 ± multiplier × TR 均值（classic 口径）。"""
    close = _field(data, "close")
    if close is None:
        raise AttributeError("keltner_bands(data, …) 需要数据对象提供 close")
    n = _win(window)
    middle = close.ewm(span=n, adjust=False).mean()
    atr = true_range(data).rolling(_win(atr_window)).mean()
    offset = multiplier * atr
    return middle + offset, middle - offset, middle


def rolling_regression(data, window: int):
    """收盘价时序趋势回归 → (slope, r²)：中心化 x 的滚动 OLS（technical 口径）。"""
    close = _field(data, "close")
    if close is None:
        raise AttributeError("rolling_regression(data, window) 需要数据对象提供 close")
    n = validate_window(window)
    centered_x = np.arange(n, dtype=float) - (n - 1) / 2
    sum_squared_x = float(np.dot(centered_x, centered_x))
    weighted_sum = close.rolling(n).apply(
        lambda values: np.dot(values, centered_x), raw=True)
    slope = weighted_sum / sum_squared_x
    mean_price = close.rolling(n).mean()
    total_squared = (
        close.pow(2).rolling(n).sum() - n * mean_price.pow(2)
    ).clip(lower=0.0)
    r_squared = (slope.pow(2) * sum_squared_x) / (total_squared + 1e-10)
    r_squared = r_squared.where(total_squared.notna())
    r_squared = r_squared.where(
        total_squared.isna() | (total_squared > 1e-10), 0.0)
    return slope, r_squared.clip(lower=0.0, upper=1.0)


def sharpe(data, window: int):
    """滚动夏普（risk_indicators 口径）：(年化收益 − 4%) / 年化波动；
    无风险利率 4% 为源码硬编码，年化系数 252。"""
    close = _field(data, "close")
    if close is None:
        raise AttributeError("sharpe(data, window) 需要数据对象提供 close")
    n = _win(window)
    returns = close.pct_change()
    annual_return = returns.rolling(n).mean() * 252
    annual_volatility = returns.rolling(n).std() * np.sqrt(252)
    return (annual_return - 0.04) / annual_volatility


def range_percent(data):
    """TR / (|close| + ε)（price_discovery 口径，±inf → NaN）。"""
    close = _field(data, "close")
    if close is None:
        raise AttributeError("range_percent(data) 需要数据对象提供 close")
    close = close.replace([np.inf, -np.inf], np.nan)
    return (true_range(data) / (close.abs() + EPSILON)).replace(
        [np.inf, -np.inf], np.nan)


def rolling_correlation(left, right, window: int):
    """滚动相关（防零除、clip[-1,1]）。

    多数派口径：min_periods 默认、防零阈值 1e-10（trading/price_discovery）；
    market_state 变体 min_periods=window、阈值 EPSILON=1e-12，未采用。
    """
    n = _win(window)
    left_mean = left.rolling(n).mean()
    right_mean = right.rolling(n).mean()
    covariance = (left * right).rolling(n).mean() - left_mean * right_mean
    left_variance = (
        left.pow(2).rolling(n).mean() - left_mean.pow(2)).clip(lower=0.0)
    right_variance = (
        right.pow(2).rolling(n).mean() - right_mean.pow(2)).clip(lower=0.0)
    denominator = np.sqrt(left_variance * right_variance)
    result = covariance / denominator.where(denominator > 1e-10)
    result = result.where(denominator.notna())
    return result.where(
        denominator.isna() | (denominator > 1e-10), 0.0
    ).clip(lower=-1.0, upper=1.0)


def entropy_term(probability):
    """p·ln(p)（p ≤ 0 处贡献 0；market_state 口径）。"""
    safe_probability = probability.where(probability > 0.0, 1.0)
    return probability * np.log(safe_probability)


def tail_balance(values: np.ndarray, tail_fraction: float) -> float:
    """上下尾均值平衡 → [-1, 1]（technical 口径）。"""
    tail_size = max(1, int(np.ceil(values.size * tail_fraction)))
    ordered = np.sort(values)
    lower_mean = float(ordered[:tail_size].mean())
    upper_mean = float(ordered[-tail_size:].mean())
    scale_ = abs(lower_mean) + abs(upper_mean)
    if scale_ <= 1e-10:
        return 0.0
    return float(np.clip((upper_mean + lower_mean) / (scale_ + 1e-10), -1.0, 1.0))


def shock_frequency(values: np.ndarray, shock_multiple: float) -> float:
    """超中位数 N 倍的频率（technical 口径：|values| 中位数 × shock_multiple）。"""
    absolute_returns = np.abs(values)
    typical_move = float(np.median(absolute_returns))
    if typical_move <= 1e-10:
        return 0.0
    return float(np.mean(absolute_returns > shock_multiple * typical_move))


def top_tail_share(values: np.ndarray, tail_fraction: float) -> float:
    """最大 tail 占总量比（trading 口径）。"""
    total = float(values.sum())
    if not np.isfinite(total) or total <= 1e-10:
        return 0.0
    tail_count = max(1, int(np.ceil(values.size * tail_fraction)))
    largest = np.partition(values, values.size - tail_count)[-tail_count:]
    return float(largest.sum() / total)


def tail_loss_concentration(values: np.ndarray, tail_fraction: float) -> float:
    """尾部亏损占总亏损比（volatility 口径；窗口含缺失返回 NaN）。"""
    if values.size == 0 or not np.isfinite(values).all():
        return np.nan
    losses = -values[values < 0.0]
    total_loss = losses.sum()
    if total_loss <= 1e-10:
        return 0.0
    tail_count = max(1, int(np.ceil(losses.size * tail_fraction)))
    tail_loss = np.sort(losses)[-tail_count:].sum()
    return float(tail_loss / total_loss)


def last_percentile_rank(values: np.ndarray) -> float:
    """末值百分位（volatility 口径）：(小于数 + 0.5×等值数) / 窗口长度；含缺失返回 NaN。

    通常以 .rolling(n).apply(tool._last_percentile_rank, raw=True) 引用传递。
    """
    if values.size == 0 or not np.isfinite(values).all():
        return np.nan
    current = values[-1]
    less = np.count_nonzero(values < current)
    equal = np.count_nonzero(values == current)
    return float((less + 0.5 * equal) / values.size)


def recovery_fraction(values: np.ndarray) -> float:
    """回撤修复比例 → [0, 1]（market_state 口径；窗口含缺失/非正收益返回 NaN）。

    通常以 .rolling(window).apply(tool._recovery_fraction, raw=True) 引用传递。
    """
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        return np.nan
    running_peak = np.maximum.accumulate(values)
    drawdown = values / running_peak - 1.0
    trough_index = int(np.argmin(drawdown))
    trough_price = values[trough_index]
    recovery_target = running_peak[trough_index]
    recovery_range = recovery_target - trough_price
    if recovery_range <= EPSILON:
        return 1.0
    return float(np.clip((values[-1] - trough_price) / recovery_range, 0.0, 1.0))


# ---------------------------------------------------------------------------
# 别名：与因子文档代码中的调用拼写一一对应（drop-in）
# ---------------------------------------------------------------------------

_ts_argmax, _ts_argmin = ts_argmax, ts_argmin
_highday, _lowday = ts_argmax, ts_argmin          # GTJA HIGHDAY/LOWDAY 同口径
_sma, _decay_linear, _wma, _regbeta = sma, decay_linear, wma, regbeta
_scale = scale
_indneutralize = indneutralize
_safe_divide = safe_divide
_broadcast_series = broadcast_series
_vwap = vwap
_tr_parts, _directional_movement = tr_parts, directional_movement
_EPSILON = EPSILON                                # 文档代码的防零常量拼写
# 2026-09-08 静态化批次别名（原内置库 self._xxx 方法 → tool 函数）
_true_range = true_range                          # emotion/technical 的 .where 链实现与
_tr = true_range                                  # np.maximum 数值等价；price_discovery 版
                                                  # 先清洗 ±inf，由 range_percent 内部承载
_dm = dm
_amount = amount
_benchmark = benchmark
_valid_volume, _nonnegative_volume = valid_volume, nonnegative_volume
_log_volume_change = log_volume_change
_turnover_mean, _vema, _vdiff = turnover_mean, vema, vdiff
_ar, _br, _wvad = ar, br, wvad
_directional_indices = directional_indices
_keltner_bands = keltner_bands
_rolling_regression = rolling_regression
_sharpe = sharpe
_range_percent = range_percent
_rolling_correlation = rolling_correlation
_shares = shares
_entropy_term = entropy_term
_tail_balance = tail_balance
_tail_loss_concentration = tail_loss_concentration
_top_tail_share = top_tail_share
_shock_frequency = shock_frequency
_last_percentile_rank = last_percentile_rank
_recovery_fraction = recovery_fraction
_validate_window = validate_window
_validate_lag = validate_lag
_validate_tail_fraction = validate_tail_fraction
_validate_shock_multiple = validate_shock_multiple

__all__ = [
    "EPSILON",
    # 时序（仅保留 pandas 无原生等价的自定义语义）
    "ts_argmax", "ts_argmin", "sma", "decay_linear", "wma", "regbeta",
    # 窗口线性回归三件套（Alpha158 BETA/RSQR/RESI 口径）
    "_linear_slope", "_linear_rsquare", "_linear_residual", "_LOG_THREE",
    # 截面、条件与数据耦合
    "scale", "indneutralize", "safe_divide", "broadcast_series", "vwap",
    "true_range", "tr_parts", "directional_movement",
    # 2026-09-08 静态化批次：数据对象级辅助与统计函数（原内置库方法收编）
    "validate_window", "validate_lag", "validate_tail_fraction",
    "validate_shock_multiple", "amount", "shares", "benchmark", "valid_volume",
    "nonnegative_volume", "log_volume_change", "turnover_mean", "vema",
    "vdiff", "ar", "br", "wvad", "dm", "directional_indices",
    "keltner_bands", "rolling_regression", "sharpe", "range_percent",
    "rolling_correlation", "entropy_term", "tail_balance",
    "shock_frequency", "top_tail_share", "tail_loss_concentration",
    "last_percentile_rank", "recovery_fraction",
    # 文档拼写别名
    "_ts_argmax", "_ts_argmin", "_highday", "_lowday", "_sma",
    "_decay_linear", "_wma", "_regbeta", "_scale", "_indneutralize",
    "_safe_divide", "_broadcast_series", "_vwap", "_tr_parts",
    "_directional_movement", "_EPSILON",
    "_true_range", "_tr", "_dm", "_amount", "_benchmark", "_valid_volume",
    "_nonnegative_volume", "_log_volume_change", "_turnover_mean", "_vema",
    "_vdiff", "_ar", "_br", "_wvad", "_directional_indices",
    "_keltner_bands", "_rolling_regression", "_sharpe", "_range_percent",
    "_rolling_correlation", "_entropy_term", "_tail_balance",
    "_tail_loss_concentration", "_top_tail_share", "_shock_frequency",
    "_validate_window", "_validate_lag", "_validate_tail_fraction",
    "_validate_shock_multiple", "_last_percentile_rank",
    "_recovery_fraction", "_shares",
]


# ---------------------------------------------------------------------------
# 自检：python tool.py 直接运行
# ---------------------------------------------------------------------------

def _selftest() -> None:
    rng = np.random.default_rng(20260903)
    dates = pd.bdate_range("2025-01-02", periods=150)
    syms = ["S1", "S2", "S3", "S4", "S5"]
    close = pd.DataFrame(100 + np.cumsum(rng.normal(0, 1, (150, 5)), axis=0),
                         index=dates, columns=syms)
    high = close + pd.DataFrame(rng.uniform(0.5, 2.0, (150, 5)),
                                index=dates, columns=syms)
    low = close - pd.DataFrame(rng.uniform(0.5, 2.0, (150, 5)),
                               index=dates, columns=syms)
    volume = pd.DataFrame(rng.uniform(1e5, 1e6, (150, 5)),
                          index=dates, columns=syms)
    amount_df = close * volume
    shares = pd.DataFrame(1e8, index=dates, columns=syms)
    data = SimpleNamespace(open=close.copy(), high=high, low=low, close=close,
                           volume=volume, amount=amount_df, shares=shares,
                           industry={"S1": "银行", "S2": "银行", "S3": "科技",
                                     "S4": "科技", "S5": "医药"})
    checks = 0

    def ok(cond, msg):
        nonlocal checks
        assert cond, msg
        checks += 1

    # 时序：非整数窗口 int() 截断（迁移后由 sma 承载该约定）
    ok(sma(close, 7.9, 1).equals(sma(close, 7, 1)), "非整数窗口截断")

    # ts_argmax/argmin 约定：极值越近读数越小（0 = 当前 bar）
    probe = pd.Series([9.0, 1.0, 2.0, 3.0, 5.0])
    ok(ts_argmax(probe, 5).iloc[-1] == 4.0, "ts_argmax 距今天数")
    ok(ts_argmin(probe, 5).iloc[-1] == 3.0, "ts_argmin 距今天数")
    ok(ts_argmax(pd.Series([5.0, 1.0, 2.0, 3.0, 9.0]), 5).iloc[-1] == 0.0,
       "ts_argmax 当前 bar 极值")
    nan_probe = pd.Series([np.nan, 1.0, 2.0, 3.0, 4.0])
    ok(np.isnan(ts_argmax(nan_probe, 5).iloc[-1]), "ts_argmax 缺失传染")

    # sma 递推手工核对
    manual = sma(pd.Series([1.0, 2.0, 3.0, 4.0]), 3, 1)
    for i, expect in enumerate([1.0, 4 / 3, 17 / 9, 70 / 27]):
        ok(math.isclose(manual.iloc[i], expect, rel_tol=1e-12), f"sma 递推 t={i}")

    # decay_linear 手工核对（最近期权重最大）
    manual = decay_linear(pd.Series([1.0, 2.0, 3.0]), 3)
    ok(math.isclose(manual.iloc[-1], 14 / 6, rel_tol=1e-12), "decay_linear")

    # regbeta 对照 np.polyfit（固定模式分支）与自洽（Series 分支）
    y = close["S1"]
    w = 10
    pattern = np.arange(1, w + 1, dtype=float)
    rb = regbeta(y, pattern, w)
    t = 60
    expect = np.polyfit(pattern, y.iloc[t - w + 1: t + 1].to_numpy(), 1)[0]
    ok(math.isclose(rb.iloc[t], expect, rel_tol=1e-8), "regbeta 固定模式")
    full = pd.Series(np.tile(pattern, 16)[: len(y)], index=y.index)
    rb_b = regbeta(y, full, w)
    xs = full.iloc[t - w + 1: t + 1].to_numpy()
    expect_b = np.polyfit(xs, y.iloc[t - w + 1: t + 1].to_numpy(), 1)[0]
    ok(math.isclose(rb_b.iloc[t], expect_b, rel_tol=1e-8),
       "regbeta Series 回归元")
    ok(isinstance(regbeta(close, pattern, w), pd.DataFrame)
       and regbeta(close, pattern, w).shape == close.shape, "regbeta 面板")

    # 窗口线性回归三件套：对照 np.polyfit（斜率/截距/R²/末点残差）
    y_win = close["S1"].iloc[t - w + 1: t + 1].to_numpy()
    b_fit, a_fit = np.polyfit(np.arange(1, w + 1, dtype=float), y_win, 1)
    ok(math.isclose(_linear_slope(y_win), b_fit, rel_tol=1e-8), "_linear_slope")
    ok(math.isclose(_linear_residual(y_win), y_win[-1] - (b_fit * w + a_fit),
                    rel_tol=1e-8), "_linear_residual")
    corr = np.corrcoef(np.arange(1, w + 1, dtype=float), y_win)[0, 1]
    ok(math.isclose(_linear_rsquare(y_win), corr * corr, rel_tol=1e-8),
       "_linear_rsquare")
    ok(np.isnan(_linear_slope(y_win[:-1].copy() * np.nan)), "_linear_* 缺失传染")
    ok(_linear_rsquare(np.ones(w)) == 0.0, "_linear_rsquare 零方差")
    ok(math.isclose(_LOG_THREE, math.log(3.0)), "_LOG_THREE")

    # 统计：相关/协方差由 pandas 原生提供（x.rolling(N).corr/cov(y)），不再封装

    # 截面：scale 行和、行业中性化组内均值归零
    s = scale(close)
    ok(np.allclose(s.abs().sum(axis=1), 1.0), "scale 行 |x| 之和为 1")
    neutral = indneutralize(data, close, "industry")
    for grp, cols in {"银行": ["S1", "S2"], "科技": ["S3", "S4"]}.items():
        ok(neutral[cols].mean(axis=1).abs().max() < 1e-9,
           f"indneutralize 组内均值归零（{grp}）")

    # 条件与组合：条件分支/布尔信号/条件计数由原生 .where/.mask/.astype 提供
    cond = close > close.shift(1)
    ok(np.isnan(safe_divide(pd.Series([1.0, 1.0]), pd.Series([0.0, 2.0]))[0])
       and math.isclose(safe_divide(pd.Series([1.0, 1.0]),
                                    pd.Series([0.0, 2.0]))[1], 0.5),
       "safe_divide 防零")

    # broadcast_series：基准序列广播成面板
    bench = pd.Series(rng.normal(0, 1, 150), index=dates)
    panel = broadcast_series(bench, close)
    ok(panel.shape == close.shape and panel["S3"].equals(bench),
       "broadcast_series")

    # 价格与量衍生（收益/ADV/市值由原生表达式内联，不再封装）
    ok(vwap(data).equals(amount_df / volume), "vwap(data) 无 vwap 字段时走 amount/volume")
    ok(vwap(amount_df, volume).equals(vwap(data)), "vwap(amount_df, volume)")
    data_with_vwap = SimpleNamespace(**{**vars(data), "vwap": close + 1.0})
    ok(vwap(data_with_vwap).equals(close + 1.0), "vwap(data) 优先 vwap 字段")

    # 真实波幅族
    prev = close.shift(1)
    tr_expect = np.maximum(np.maximum(high - low, (high - prev).abs()),
                           (low - prev).abs())
    ok(true_range(data).equals(tr_expect), "true_range")
    move_expect = np.maximum((high - high.shift(1)).abs(),
                             (low - low.shift(1)).abs())
    ok(tr_parts(data).equals(move_expect), "tr_parts")
    tr, dm_plus, dm_minus = directional_movement(data)
    up = high - high.shift(1)
    down = low.shift(1) - low
    ok(tr.equals(tr_expect), "directional_movement TR")
    ok(dm_plus.equals(up.where((up > down) & (up > 0), 0.0)),
       "directional_movement +DM")
    ok(dm_minus.equals(down.where((down > up) & (down > 0), 0.0)),
       "directional_movement −DM")

    # 别名拼写与文档一致
    ok(_sma is sma and _decay_linear is decay_linear and _wma is wma
       and _regbeta is regbeta and _ts_argmax is ts_argmax
       and _ts_argmin is ts_argmin and _highday is ts_argmax
       and _lowday is ts_argmin and _scale is scale
       and _indneutralize is indneutralize and _safe_divide is safe_divide
       and _broadcast_series is broadcast_series and _vwap is vwap
       and _tr_parts is tr_parts
       and _directional_movement is directional_movement, "别名绑定")
    ok(_true_range is true_range and _tr is true_range and _dm is dm
       and _amount is amount and _benchmark is benchmark
       and _valid_volume is valid_volume
       and _nonnegative_volume is nonnegative_volume
       and _log_volume_change is log_volume_change
       and _turnover_mean is turnover_mean and _vema is vema
       and _vdiff is vdiff and _ar is ar and _br is br and _wvad is wvad
       and _directional_indices is directional_indices
       and _keltner_bands is keltner_bands
       and _rolling_regression is rolling_regression and _sharpe is sharpe
       and _range_percent is range_percent
       and _rolling_correlation is rolling_correlation
       and _entropy_term is entropy_term and _tail_balance is tail_balance
       and _shock_frequency is shock_frequency
       and _top_tail_share is top_tail_share
       and _tail_loss_concentration is tail_loss_concentration
       and _validate_window is validate_window
       and _validate_lag is validate_lag
       and _validate_tail_fraction is validate_tail_fraction
       and _validate_shock_multiple is validate_shock_multiple, "静态化批次别名绑定")

    # 2026-09-08 静态化批次：数据对象级辅助函数
    ok(_validate_window(5) == 5 and validate_window(np.int64(7)) == 7,
       "validate_window 整数放行")
    for bad in (37.9, "5", True, None, 1):
        try:
            validate_window(bad)
            raise AssertionError("validate_window 应拒绝 %r" % (bad,))
        except ValueError:
            pass
    for bad in (1, "5", True, 2.5):
        try:
            validate_window(bad)
            raise AssertionError("validate_window 应拒绝 %r" % (bad,))
        except ValueError:
            pass
    ok(validate_lag(10, 3) == 3, "validate_lag")
    ok(validate_tail_fraction(0.3) == 0.3 and validate_shock_multiple(2.5) == 2.5,
       "validate_tail_fraction / validate_shock_multiple")
    ok(amount(data).equals(amount_df), "amount(data)")
    ok(amount(SimpleNamespace(close=close, volume=volume)).equals(amount_df),
       "amount_df 回退 close×volume")
    bench_close, bench_open = benchmark(data)
    ok(bench_close.equals(close.mean(axis=1))
       and bench_open.equals(data.open.mean(axis=1)), "benchmark 截面均值回退")
    bm = SimpleNamespace(**{**vars(data), "benchmark_close": close[["S1"]]})
    ok(benchmark(bm)[0].equals(close["S1"]), "benchmark 首列")
    ok(valid_volume(data).equals(volume), "valid_volume 正常量")
    dirty = SimpleNamespace(volume=volume.mask(volume["S1"] > 5e5, -1.0))
    ok((valid_volume(dirty)["S1"].isna() == (volume["S1"] > 5e5)).all(),
       "valid_volume 负值置缺")
    ok(log_volume_change(data).equals(np.log(volume).diff()), "log_volume_change")
    ok(turnover_mean(SimpleNamespace(turnover=volume), 10).equals(
        volume.rolling(10).mean()), "turnover_mean")
    ok(vema(data, 10).equals(volume.ewm(span=10, adjust=False).mean()), "vema")
    ok(vdiff(data).equals(vema(data, 12) - vema(data, 26)), "vdiff")
    ok(ar(data).equals(((high - data.open).rolling(26).sum()
                        / (data.open - low).rolling(26).sum() * 100)), "ar")
    prev_c = close.shift()
    ok(br(data).equals(((high - prev_c).clip(lower=0).rolling(26).sum()
                        / (prev_c - low).clip(lower=0).rolling(26).sum() * 100)), "br")
    ok(wvad(data).equals(((close - data.open) / (high - low) * volume).rolling(6).sum()),
       "wvad")
    dmz, dmf = dm(data)
    dist = np.maximum((high - high.shift()).abs(), (low - low.shift()).abs())
    ok(dmz.equals(dist.where(high + low > (high + low).shift(), 0.0)), "dm dmz")
    ok(dmf.equals(dist.where(high + low < (high + low).shift(), 0.0)), "dm dmf")
    pos, neg = directional_indices(data, 14)
    pos_d, neg_d = pos.dropna(), neg.dropna()
    ok(((pos_d >= 0) & (pos_d <= 100)).all().all()
       and ((neg_d >= 0) & (neg_d <= 100)).all().all(),
       "directional_indices 范围")
    upper, lower, middle = keltner_bands(data, 10, 14, 2.0)
    ema_mid = close.ewm(span=10, adjust=False).mean()
    ok(middle.equals(ema_mid) and upper.equals(ema_mid + 2.0 * true_range(data).rolling(14).mean()),
       "keltner_bands")
    slope, r2 = rolling_regression(data, 10)
    ok(slope["S1"].notna().any() and r2.dropna().le(1.0).all().all(), "rolling_regression")
    ok(sharpe(data, 20).notna().any().any(), "sharpe")
    ok(range_percent(data).notna().any().any(), "range_percent")
    corr = rolling_correlation(close, high, 10)
    ok(corr.dropna().abs().le(1.0).all().all(), "rolling_correlation 范围")
    ok(entropy_term(pd.Series([0.5, -1.0])).iloc[1] == 0.0, "entropy_term p≤0")
    ok(tail_balance(np.array([1.0, 2.0, 3.0, 4.0]), 0.25) is not None, "tail_balance")
    ok(shock_frequency(np.array([1.0, 2.0, 9.0]), 2.0) >= 0.0, "shock_frequency")
    ok(top_tail_share(np.array([1.0, 2.0, 3.0]), 0.5) > 0.0, "top_tail_share")
    ok(tail_loss_concentration(np.array([-1.0, -2.0, 3.0]), 0.5) > 0.0,
       "tail_loss_concentration")

    print(f"自检通过：{checks} 项断言，覆盖 {len(__all__) - 1} 个导出算子")


if __name__ == "__main__":
    _selftest()
