"""技术因子库。

技术分析类因子，基于价格形态和技术指标。
"""

from __future__ import annotations

import numpy as np

from quantcore import FactorLibrary


class TechnicalLib(FactorLibrary):
    """技术因子集合。"""

    author = "SVQuant"

    # ==================== 均线 ====================

    def sma_5(self, window: int = 5):
        """5 日均线乖离率：（收盘价 - 均线）/ 均线。"""
        ma = self.close.rolling(window).mean()
        return (self.close - ma) / ma

    def sma_20(self, window: int = 20):
        """20 日均线乖离率。"""
        ma = self.close.rolling(window).mean()
        return (self.close - ma) / ma

    def sma_60(self, window: int = 60):
        """60 日均线乖离率。"""
        ma = self.close.rolling(window).mean()
        return (self.close - ma) / ma

    def ma_cross(self, fast: int = 5, slow: int = 20):
        """均线交叉：短期均线 / 长期均线 - 1。"""
        ma_fast = self.close.rolling(fast).mean()
        ma_slow = self.close.rolling(slow).mean()
        return ma_fast / ma_slow - 1

    def ma_distance(self, fast: int = 5, slow: int = 20):
        """均线距离：(短期 - 长期) / 长期。"""
        ma_fast = self.close.rolling(fast).mean()
        ma_slow = self.close.rolling(slow).mean()
        return (ma_fast - ma_slow) / ma_slow

    # ==================== RSI ====================

    def rsi_6(self, window: int = 6):
        """6 日 RSI。"""
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    def rsi_14(self, window: int = 14):
        """14 日 RSI。"""
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    def rsi_24(self, window: int = 24):
        """24 日 RSI。"""
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    # ==================== MACD ====================

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 因子。"""
        ema_fast = self.close.ewm(span=fast).mean()
        ema_slow = self.close.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        return dif - dea

    def macd_signal(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 信号线：DIF - DEA 的归一化。"""
        ema_fast = self.close.ewm(span=fast).mean()
        ema_slow = self.close.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        return (dif - dea) / (dif.abs().mean() + 1e-10)

    def macd_cross(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 金叉死叉信号。"""
        ema_fast = self.close.ewm(span=fast).mean()
        ema_slow = self.close.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        hist = dif - dea
        cross = hist.rolling(2).apply(lambda x: x.iloc[-1] - x.iloc[0], raw=True)
        return cross

    # ==================== 布林带 ====================

    def bollinger_position(self, window: int = 20, n_std: float = 2.0):
        """布林带位置：（收盘价 - 下轨）/（上轨 - 下轨）。"""
        mid = self.close.rolling(window).mean()
        std = self.close.rolling(window).std()
        upper = mid + n_std * std
        lower = mid - n_std * std
        return (self.close - lower) / (upper - lower + 1e-10)

    def bollinger_width(self, window: int = 20, n_std: float = 2.0):
        """布林带宽度：（上轨 - 下轨）/ 中轨。"""
        mid = self.close.rolling(window).mean()
        std = self.close.rolling(window).std()
        return (2 * n_std * std) / mid

    def bollinger_breakout(self, window: int = 20, n_std: float = 2.0):
        """布林带突破：收盘价超出上轨为 1，低于下轨为 -1，否则 0。"""
        mid = self.close.rolling(window).mean()
        std = self.close.rolling(window).std()
        upper = mid + n_std * std
        lower = mid - n_std * std
        breakout = (self.close > upper).astype(float) - (self.close < lower).astype(float)
        return breakout

    # ==================== 随机指标 ====================

    def kdj_k(self, window: int = 9):
        """KDJ K 值。"""
        hh = self.high.rolling(window).max()
        ll = self.low.rolling(window).min()
        return (self.close - ll) / (hh - ll + 1e-10) * 100

    def kdj_d(self, window: int = 9, k_smooth: int = 3):
        """KDJ D 值。"""
        hh = self.high.rolling(window).max()
        ll = self.low.rolling(window).min()
        k = (self.close - ll) / (hh - ll + 1e-10) * 100
        return k.rolling(k_smooth).mean()

    def stoch_rsi(self, window: int = 14):
        """随机 RSI。"""
        rsi = self.rsi_14(window=window)
        hh = rsi.rolling(window).max()
        ll = rsi.rolling(window).min()
        return (rsi - ll) / (hh - ll + 1e-10)

    def cci(self, window: int = 20):
        """商品通道指数：典型价格偏离其平均值的程度。"""
        typical_price = (self.high + self.low + self.close) / 3
        mean = typical_price.rolling(window).mean()
        mean_deviation = typical_price.rolling(window).apply(
            lambda values: np.mean(np.abs(values - values.mean())), raw=True
        )
        return (typical_price - mean) / (0.015 * mean_deviation + 1e-10)

    def williams_r(self, window: int = 14):
        """Williams %R：收盘价在近期高低区间中的位置。"""
        highest_high = self.high.rolling(window).max()
        lowest_low = self.low.rolling(window).min()
        return -100 * (highest_high - self.close) / (highest_high - lowest_low + 1e-10)

    def aroon_up(self, window: int = 26):
        """Aroon Up：距离近期最高价出现时间的趋势强度。"""
        periods_since_high = self.high.rolling(window).apply(
            lambda values: np.argmax(values[::-1]), raw=True
        )
        return 100 * (window - 1 - periods_since_high) / (window - 1)

    def aroon_down(self, window: int = 26):
        """Aroon Down：距离近期最低价出现时间的趋势强度。"""
        periods_since_low = self.low.rolling(window).apply(
            lambda values: np.argmin(values[::-1]), raw=True
        )
        return 100 * (window - 1 - periods_since_low) / (window - 1)

    def dpo(self, window: int = 20):
        """去趋势价格振荡器：移位收盘价减去当期均线。"""
        displacement = window // 2 + 1
        return self.close.shift(displacement) - self.close.rolling(window).mean()

    def chande_momentum_oscillator(self, window: int = 20):
        """Chande 动量振荡器：窗口内涨跌价格变动的归一化差。"""
        delta = self.close.diff()
        up_sum = delta.clip(lower=0).rolling(window).sum()
        down_sum = (-delta.clip(upper=0)).rolling(window).sum()
        return 100 * (up_sum - down_sum) / (up_sum + down_sum + 1e-10)

    def ultimate_oscillator(self, short: int = 7, medium: int = 14, long: int = 28):
        """终极振荡器：多周期买压与真实波幅的加权动量。"""
        previous_close = self.close.shift()
        minimum = self.low.where(self.low <= previous_close, previous_close)
        maximum = self.high.where(self.high >= previous_close, previous_close)
        buying_pressure = self.close - minimum
        true_range = maximum - minimum

        def average(window: int):
            return buying_pressure.rolling(window).sum() / (
                true_range.rolling(window).sum() + 1e-10
            )

        return 100 * (4 * average(short) + 2 * average(medium) + average(long)) / 7

    def fisher_transform(self, window: int = 10):
        """费舍尔变换：滚动中点价格归一化后的非线性振荡器。"""
        midpoint = (self.high + self.low) / 2
        lowest = midpoint.rolling(window).min()
        highest = midpoint.rolling(window).max()
        price_range = highest - lowest
        normalized = (
            2 * (midpoint - lowest) / (price_range + 1e-10) - 1
        ).where(price_range > 0, 0.0)
        normalized = normalized.clip(-0.999999, 0.999999)
        return 0.5 * np.log((1 + normalized) / (1 - normalized))

    def ease_of_movement(self, window: int = 14, volume_divisor: float = 100000000.0):
        """简化移动容易度：价格位移相对成交量和振幅的滚动均值。"""
        distance_moved = ((self.high + self.low) / 2).diff()
        box_ratio = (self.volume / volume_divisor) / (
            self.high - self.low + 1e-10
        )
        one_period = distance_moved / (box_ratio + 1e-10)
        return one_period.rolling(window).mean()

    def relative_vigor_index(self, window: int = 10):
        """相对活力指数：收盘—开盘动量相对高低价区间的平滑比值。"""
        close_open = self.close - self.open
        high_low = self.high - self.low
        numerator = (
            close_open
            + 2 * close_open.shift(1)
            + 2 * close_open.shift(2)
            + close_open.shift(3)
        ) / 6
        denominator = (
            high_low
            + 2 * high_low.shift(1)
            + 2 * high_low.shift(2)
            + high_low.shift(3)
        ) / 6
        return numerator.rolling(window).mean() / (
            denominator.rolling(window).mean() + 1e-10
        )

    def awesome_oscillator(self, fast: int = 5, slow: int = 34):
        """奇妙振荡器：短长周期中间价均线之差。"""
        midpoint = (self.high + self.low) / 2
        return midpoint.rolling(fast).mean() - midpoint.rolling(slow).mean()

    def balance_of_power(self):
        """平衡交易力量：收盘开盘差相对当日高低价区间。"""
        return (self.close - self.open) / (self.high - self.low + 1e-10)

    def choppiness_index(self, window: int = 14):
        """混沌指标：衡量市场处于震荡还是方向性趋势。"""
        true_range_sum = self._true_range().rolling(window).sum()
        price_range = self.high.rolling(window).max() - self.low.rolling(window).min()
        ratio = (true_range_sum / (price_range + 1e-10)).clip(lower=1e-10)
        return 100 * np.log10(ratio) / np.log10(window)

    def elder_force_index(self, window: int = 13):
        """艾达尔强力指数：成交量加权收盘价变动的指数平滑值。"""
        raw_force = self.close.diff() * self.volume
        return raw_force.ewm(span=window, adjust=False).mean()

    def coppock_curve(self, short: int = 11, long: int = 14, smooth: int = 10):
        """科波克曲线：两段收益率之和的线性加权平滑。"""
        rate_of_change = self.close.pct_change(short) * 100 + self.close.pct_change(long) * 100
        weights = np.arange(1, smooth + 1, dtype=float)
        return rate_of_change.rolling(smooth).apply(
            lambda values: np.dot(values, weights) / weights.sum(), raw=True
        )

    def true_strength_index(self, long: int = 25, short: int = 13):
        """真实强度指数：双重平滑价格动量相对绝对动量的比值。"""
        momentum = self.close.diff()
        smooth_momentum = momentum.ewm(span=long, adjust=False).mean().ewm(
            span=short, adjust=False
        ).mean()
        smooth_absolute = momentum.abs().ewm(span=long, adjust=False).mean().ewm(
            span=short, adjust=False
        ).mean()
        return 100 * smooth_momentum / (smooth_absolute + 1e-10)

    def relative_volatility_index(self, window: int = 10, smooth: int = 14):
        """相对波动指数：按价格方向分配滚动波动率后进行平滑。"""
        volatility = self.close.rolling(window).std(ddof=0)
        direction = self.close.diff()
        upside = volatility.where(direction > 0, 0.0)
        downside = volatility.where(direction < 0, 0.0)
        upside = upside.ewm(span=smooth, adjust=False).mean()
        downside = downside.ewm(span=smooth, adjust=False).mean()
        return 100 * upside / (upside + downside + 1e-10)

    def vortex_indicator(self, window: int = 14):
        """涡旋指标差：上行与下行涡旋线之差。"""
        previous_low = self.low.shift()
        previous_high = self.high.shift()
        positive_movement = (self.high - previous_low).abs()
        negative_movement = (self.low - previous_high).abs()
        true_range = self._true_range()
        true_range_sum = true_range.rolling(window).sum()
        positive = positive_movement.rolling(window).sum() / (true_range_sum + 1e-10)
        negative = negative_movement.rolling(window).sum() / (true_range_sum + 1e-10)
        return positive - negative

    def _true_range(self):
        previous_close = self.close.shift()
        first = self.high - self.low
        second = (self.high - previous_close).abs()
        third = (self.low - previous_close).abs()
        result = first.where(first >= second, second)
        return result.where(result >= third, third)

    def _directional_indices(self, window: int):
        up_move = self.high.diff()
        down_move = -self.low.diff()
        positive_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        negative_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        alpha = 1 / window
        true_range = self._true_range().ewm(alpha=alpha, adjust=False, min_periods=window).mean()
        positive = positive_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
        negative = negative_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
        return 100 * positive / (true_range + 1e-10), 100 * negative / (true_range + 1e-10)

    def positive_directional_index(self, window: int = 14):
        """正向方向指标：Wilder 平滑后的上行方向运动强度。"""
        positive, _ = self._directional_indices(window)
        return positive

    def negative_directional_index(self, window: int = 14):
        """负向方向指标：Wilder 平滑后的下行方向运动强度。"""
        _, negative = self._directional_indices(window)
        return negative

    def average_directional_index(self, window: int = 14):
        """平均趋向指标：趋势强度，不区分涨跌方向。"""
        positive, negative = self._directional_indices(window)
        dx = 100 * (positive - negative).abs() / (positive + negative + 1e-10)
        return dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    def accumulation_distribution(self):
        """累积/派发线：按收盘位置加权累计成交量。"""
        multiplier = ((self.close - self.low) - (self.high - self.close)) / (
            self.high - self.low + 1e-10
        )
        return (multiplier * self.volume).cumsum()

    # ==================== 价格形态 ====================

    def price_pattern_doji(self):
        """十字星形态。"""
        body = (self.open - self.close).abs()
        shadow = self.high - self.low
        return (body / (shadow + 1e-10) < 0.1).astype(float)

    def price_pattern_hammer(self):
        """锤子线形态。"""
        body = (self.open - self.close).abs()
        lower_shadow = self.close - self.low
        upper_shadow = self.high - self.open
        return ((lower_shadow > body * 2) & (upper_shadow < body * 0.5)).astype(float)

    # ==================== 趋势质量与路径风险 ====================

    def kaufman_efficiency_ratio(self, window: int = 10):
        """Kaufman 路径效率：净价格变化与实际路径长度之比。"""
        window = self._validate_window(window)
        net_change = self.close.diff(window).abs()
        path_length = self.close.diff().abs().rolling(window).sum()
        return (net_change / (path_length + 1e-10)).clip(lower=0.0, upper=1.0)

    def normalized_linear_regression_slope(self, window: int = 20):
        """归一化滚动线性回归斜率：斜率除以滚动均价绝对值。"""
        slope, _ = self._rolling_regression(window)
        mean_price = self.close.rolling(window).mean()
        return slope / (mean_price.abs() + 1e-10)

    def regression_r_squared(self, window: int = 20):
        """滚动线性回归拟合优度 R²，衡量趋势路径的稳定程度。"""
        _, r_squared = self._rolling_regression(window)
        return r_squared

    def ulcer_index(self, window: int = 14):
        """Ulcer Index：滚动回撤百分比平方均值的平方根。"""
        window = self._validate_window(window)
        rolling_max = self.close.rolling(window).max()
        drawdown_pct = 100 * (self.close - rolling_max) / (rolling_max.abs() + 1e-10)
        return drawdown_pct.pow(2).rolling(window).mean().pow(0.5)

    # ==================== 日内结构与流动性状态 ====================

    def overnight_gap_follow_through(self, window: int = 10):
        """隔夜跳空延续：跳空方向与当日盘中收益方向一致性的滚动均值。"""
        window = self._validate_window(window)
        previous_close = self.close.shift()
        gap = (self.open - previous_close) / (previous_close.abs() + 1e-10)
        intraday_return = (self.close - self.open) / (self.open.abs() + 1e-10)
        gap_direction = gap.gt(0).astype(float) - gap.lt(0).astype(float)
        continuation = (gap_direction * intraday_return).where(
            gap.notna() & intraday_return.notna()
        )
        return continuation.rolling(window).mean()

    def range_expansion_persistence(self, window: int = 10, baseline: int = 60):
        """区间扩张持续性：近期真实区间高于基准区间均值的比例。"""
        window = self._validate_window(window)
        baseline = self._validate_window(baseline)
        true_range = self._true_range()
        baseline_range = true_range.rolling(baseline).mean()
        expanded = true_range.gt(baseline_range).where(
            true_range.notna() & baseline_range.notna()
        )
        return expanded.astype(float).rolling(window).mean()

    def directional_range_balance(self, window: int = 14):
        """方向性区间平衡：上涨与下跌方向真实区间的净平衡强度。"""
        window = self._validate_window(window)
        previous_close = self.close.shift()
        true_range = self._true_range()
        change = self.close - previous_close
        direction = change.gt(0).astype(float) - change.lt(0).astype(float)
        signed_range = (direction * true_range).where(
            change.notna() & true_range.notna()
        )
        numerator = signed_range.rolling(window).sum()
        denominator = true_range.rolling(window).sum()
        result = numerator / (denominator + 1e-10)
        result = result.where(denominator.notna())
        return result.where(denominator.isna() | (denominator > 1e-10), 0.0).clip(
            lower=-1.0, upper=1.0
        )

    def volume_impact_score(self, window: int = 20):
        """成交额冲击：单位成交额承载的绝对收益滚动均值。"""
        window = self._validate_window(window)
        returns = self.close.pct_change(fill_method=None)
        if "amount" in self.fields:
            traded_value = self.amount
        else:
            traded_value = self.close.abs() * self.volume
        traded_value = traded_value.where(traded_value > 0)
        impact = returns.abs() / traded_value
        return impact.rolling(window).mean()

    # ==================== 收益序列与价格形态状态 ====================

    def return_autocorrelation(self, window: int = 20, lag: int = 1):
        """收益一阶自相关：衡量窗口内收益的延续或反转关系。"""
        window = self._validate_window(window)
        lag = self._validate_window(lag, minimum=1)
        if lag >= window:
            raise ValueError("lag 必须小于 window")

        returns = self.close.pct_change(fill_method=None).replace(
            [np.inf, -np.inf], np.nan
        )
        lagged = returns.shift(lag)
        current_mean = returns.rolling(window).mean()
        lagged_mean = lagged.rolling(window).mean()
        covariance = (
            (returns * lagged).rolling(window).mean()
            - current_mean * lagged_mean
        )
        current_variance = (
            returns.pow(2).rolling(window).mean() - current_mean.pow(2)
        )
        lagged_variance = (
            lagged.pow(2).rolling(window).mean() - lagged_mean.pow(2)
        )
        denominator = np.sqrt(
            current_variance.clip(lower=0.0) * lagged_variance.clip(lower=0.0)
        )
        result = covariance / denominator.where(denominator > 1e-10)
        result = result.where(denominator.notna())
        return result.where(
            denominator.isna() | (denominator > 1e-10), 0.0
        ).clip(lower=-1.0, upper=1.0)

    def gain_loss_asymmetry(self, window: int = 20):
        """收益非对称性：窗口内上涨收益与下跌收益总量的对数比。"""
        window = self._validate_window(window)
        returns = self.close.pct_change(fill_method=None).replace(
            [np.inf, -np.inf], np.nan
        )
        gains = returns.clip(lower=0.0).rolling(window).sum()
        losses = (-returns.clip(upper=0.0)).rolling(window).sum()
        result = np.log((gains + 1e-10) / (losses + 1e-10))
        return result.where(gains.notna() & losses.notna())

    def wick_reversal_pressure(self, window: int = 10):
        """影线反转压力：下影线相对上影线的滚动不平衡。"""
        window = self._validate_window(window)
        body_top = self.open.where(self.open >= self.close, self.close)
        body_bottom = self.open.where(self.open <= self.close, self.close)
        upper_shadow = (self.high - body_top).clip(lower=0.0)
        lower_shadow = (body_bottom - self.low).clip(lower=0.0)
        price_range = self.high - self.low
        valid_range = price_range.notna() & price_range.ge(0.0)
        safe_range = price_range.where(price_range > 0.0, 1e-10)
        pressure = ((lower_shadow - upper_shadow) / safe_range).where(valid_range)
        return pressure.rolling(window).mean()

    def overnight_gap_share(self, window: int = 20):
        """隔夜跳空占比：隔夜跳空绝对幅度占真实区间总量的比例。"""
        window = self._validate_window(window)
        previous_close = self.close.shift()
        gap_size = (self.open - previous_close).abs()
        true_range = self._true_range()
        numerator = gap_size.rolling(window).sum()
        denominator = true_range.rolling(window).sum()
        result = numerator / (denominator + 1e-10)
        result = result.where(numerator.notna() & denominator.notna())
        return result.where(
            denominator.isna() | (denominator > 1e-10), 0.0
        ).clip(lower=0.0, upper=1.0)

    @staticmethod
    def _validate_window(window: int, minimum: int = 2) -> int:
        if isinstance(window, bool) or not isinstance(window, (int, np.integer)):
            raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
        window = int(window)
        if window < minimum:
            raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
        return window

    def _rolling_regression(self, window: int):
        window = self._validate_window(window)
        centered_x = np.arange(window, dtype=float) - (window - 1) / 2
        sum_squared_x = float(np.dot(centered_x, centered_x))
        weighted_sum = self.close.rolling(window).apply(
            lambda values: np.dot(values, centered_x), raw=True
        )
        slope = weighted_sum / sum_squared_x
        mean_price = self.close.rolling(window).mean()
        total_squared = (
            self.close.pow(2).rolling(window).sum()
            - window * mean_price.pow(2)
        ).clip(lower=0.0)
        r_squared = (slope.pow(2) * sum_squared_x) / (total_squared + 1e-10)
        r_squared = r_squared.where(total_squared.notna())
        r_squared = r_squared.where(
            total_squared.isna() | (total_squared > 1e-10),
            0.0,
        )
        return slope, r_squared.clip(lower=0.0, upper=1.0)
