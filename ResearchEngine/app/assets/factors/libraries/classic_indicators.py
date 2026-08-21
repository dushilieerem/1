"""从日线 OHLCV 公式迁移的经典技术指标。

仅收录公式完整且可由当前 ``Panel`` 字段复算的指标。每个方法返回该指标
公式中同名的主线；例如 ``macd`` 返回 BAR，``kdj`` 返回 J，``dma`` 返回
短长均线之差 DDD。需要指数行情、分钟数据或缺少完整公式的条目不在此库中。
"""

from __future__ import annotations

import numpy as np

from app.quantcore import FactorLibrary


class ClassicIndicatorLibrary(FactorLibrary):
    """经典日线技术、量价与波动指标。"""

    author = "SVQuant"

    def _sma(self, value, window: int, weight: int = 1):
        """通达信式 SMA：M/N * X + (N-M)/N * SMA[-1]。"""
        return value.ewm(alpha=weight / window, adjust=False).mean()

    def _tr(self):
        previous_close = self.close.shift()
        return pd_concat_max(self.high - self.low, (self.high - previous_close).abs(),
                             (self.low - previous_close).abs())

    def _keltner_bands(self, window: int, atr_window: int, multiplier: float):
        """返回 Keltner 通道上轨、下轨和 EMA 中轨。"""
        middle = self.close.ewm(span=window, adjust=False).mean()
        atr = self._tr().rolling(atr_window).mean()
        offset = multiplier * atr
        return middle + offset, middle - offset, middle

    def _dm(self):
        distance = pd_concat_max((self.high - self.high.shift()).abs(),
                                 (self.low - self.low.shift()).abs())
        current = self.high + self.low
        previous = current.shift()
        dmz = distance.where(current > previous, 0.0)
        dmf = distance.where(current < previous, 0.0)
        return dmz, dmf

    def bbi(self, short1: int = 3, short2: int = 6, long1: int = 12, long2: int = 24):
        """多空指数：四条均线的平均值。"""
        return sum(self.close.rolling(n).mean() for n in (short1, short2, long1, long2)) / 4

    def dma(self, short: int = 10, long: int = 50, smooth: int = 10):
        """平均线差 DDD：短期均线减长期均线。``smooth`` 对应派生线 AMA。"""
        return self.close.rolling(short).mean() - self.close.rolling(long).mean()

    def ma(self, window: int = 5):
        """简单移动平均。"""
        return self.close.rolling(window).mean()

    def expma(self, window: int = 5):
        """指数移动平均。"""
        return self.close.ewm(span=window, adjust=False).mean()

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 柱值 BAR：2 * (DIF - DEA)。"""
        diff = self.close.ewm(span=fast, adjust=False).mean() - self.close.ewm(span=slow, adjust=False).mean()
        dea = diff.ewm(span=signal, adjust=False).mean()
        return 2 * (diff - dea)

    def mtm(self, window: int = 6, smooth: int = 5):
        """动力指标 MTM：收盘价与 N 个交易日前收盘价之差。"""
        return self.close - self.close.shift(window)

    def priceosc(self, short: int = 12, long: int = 26):
        """价格振荡指标。"""
        short_ma = self.close.rolling(short).mean()
        return (short_ma - self.close.rolling(long).mean()) / short_ma

    def trix(self, window: int = 12, smooth: int = 20):
        """三重指数平滑平均的日变动率。"""
        triple = self.close.ewm(span=window, adjust=False).mean()
        triple = triple.ewm(span=window, adjust=False).mean()
        triple = triple.ewm(span=window, adjust=False).mean()
        return triple.pct_change() * 100

    def ddi(self, window: int = 13, smooth: int = 30, weight: int = 10, ma_window: int = 5):
        """方向标准差偏离指数 DDI。"""
        dmz, dmf = self._dm()
        sum_z, sum_f = dmz.rolling(window).sum(), dmf.rolling(window).sum()
        return (sum_z - sum_f) / (sum_z + sum_f)

    def bias(self, window: int = 12):
        """乖离率。"""
        average = self.close.rolling(window).mean()
        return (self.close - average) / average * 100

    def cci(self, window: int = 14):
        """顺势指标。"""
        typical = (self.high + self.low + self.close) / 3
        average = typical.rolling(window).mean()
        deviation = typical.rolling(window).apply(lambda values: np.mean(np.abs(values - values.mean())), raw=True)
        return (typical - average) / (0.015 * deviation)

    def dbcd(self, bias_window: int = 5, lag: int = 16, smooth: int = 76):
        """异同离差乖离率 DBCD。"""
        average = self.close.rolling(bias_window).mean()
        bias = (self.close - average) / average
        return self._sma(bias - bias.shift(lag), smooth)

    def dpo(self, window: int = 20, smooth: int = 6):
        """区间震荡线：收盘价减移动均线。"""
        return self.close - self.close.rolling(window // 2 + 1).mean()

    def kdj(self, window: int = 9, k_window: int = 3, d_window: int = 3):
        """随机指标主线 J。"""
        high, low = self.high.rolling(window).max(), self.low.rolling(window).min()
        rsv = (self.close - low) / (high - low) * 100
        k = self._sma(rsv, k_window)
        d = self._sma(k, d_window)
        return 3 * k - 2 * d

    def roc(self, window: int = 12, smooth: int = 6):
        """变动速率。"""
        return self.close.pct_change(window) * 100

    def rsi(self, window: int = 6):
        """Wilder/通达信式相对强弱指标。"""
        change = self.close.diff()
        numerator = self._sma(change.clip(lower=0), window)
        denominator = self._sma(change.abs(), window)
        return numerator / denominator * 100

    def srdm(self, window: int = 30):
        """动向速度比率。"""
        dmz, dmf = self._dm()
        z, f = dmz.rolling(10).mean(), dmf.rolling(10).mean()
        raw = (z - f) / z.where(z > f, f)
        return self._sma(raw.where((z != 0) | (f != 0), 0.0), window)

    def vroc(self, window: int = 12):
        """成交量变动速率。"""
        return self.volume.pct_change(window) * 100

    def wr(self, window: int = 14):
        """威廉指标。"""
        highest, lowest = self.high.rolling(window).max(), self.low.rolling(window).min()
        return (highest - self.close) / (highest - lowest) * 100

    def cr(self, window: int = 26):
        """能量指标。"""
        middle = (self.high.shift() + self.low.shift() + self.close.shift()) / 3
        return (self.high - middle).rolling(window).sum() / (middle - self.low).rolling(window).sum() * 100

    def psy(self, window: int = 12):
        """心理指标。"""
        return self.close.gt(self.close.shift()).rolling(window).mean() * 100

    def vr_rate(self, window: int = 26):
        """成交量比率。"""
        change = self.close.diff()
        up = self.volume.where(change > 0, 0.0).rolling(window).sum()
        down = self.volume.where(change < 0, 0.0).rolling(window).sum()
        flat = self.volume.where(change == 0, 0.0).rolling(window).sum()
        return (up + flat / 2) / (down + flat / 2) * 100

    def wad(self, smooth: int = 30):
        """威廉聚散指标。"""
        previous = self.close.shift()
        low = pd_concat_min(previous, self.low)
        high = pd_concat_max(previous, self.high)
        daily = (self.close - low).where(self.close > previous, (self.close - high).where(self.close < previous, 0.0))
        return daily.cumsum()

    def mfi(self, window: int = 14):
        """资金流向指标。"""
        typical = (self.high + self.low + self.close) / 3
        flow = typical * self.volume
        positive = flow.where(typical > typical.shift(), 0.0).rolling(window).sum()
        negative = flow.where(typical <= typical.shift(), 0.0).rolling(window).sum()
        return 100 - 100 / (1 + positive / negative)

    def pvt(self):
        """量价趋势指标。"""
        return (self.close.pct_change() * self.volume).cumsum()

    def wvad(self, window: int = 24, smooth: int = 6):
        """威廉变异离散量。"""
        return ((self.close - self.open) / (self.high - self.low) * self.volume).rolling(window).sum()

    def bbiboll(self, window: int = 10, multiplier: float = 3.0):
        """BBI 多空布林线中轨。"""
        return self.bbi().rolling(window).mean()

    def boll(self, window: int = 26, multiplier: float = 2.0):
        """布林线中轨。"""
        return self.close.rolling(window).mean()

    def cdp(self):
        """逆势操作指标中枢 CDP。"""
        return (self.high + self.low + self.close) / 3

    def env(self, window: int = 14, ratio: float = 0.06):
        """ENV 指标中轨。"""
        return self.close.rolling(window).mean()

    def vma(self, window: int = 5):
        """成交量简单移动平均。"""
        return self.volume.rolling(window).mean()

    def vmacd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """成交量 MACD 柱值。"""
        diff = self.volume.ewm(span=fast, adjust=False).mean() - self.volume.ewm(span=slow, adjust=False).mean()
        return 2 * (diff - diff.ewm(span=signal, adjust=False).mean())

    def vosc(self, short: int = 12, long: int = 26):
        """成交量震荡指标。"""
        short_ma = self.volume.rolling(short).mean()
        return (short_ma - self.volume.rolling(long).mean()) / short_ma * 100

    def vstd(self, window: int = 10):
        """成交量标准差。"""
        return self.volume.rolling(window).std(ddof=0)

    def adtm(self, window: int = 23, smooth: int = 8):
        """动态买卖气指标。"""
        previous = self.open.shift()
        dtm = pd_concat_max(self.high - self.open, self.open - previous).where(self.open > previous, 0.0)
        dbm = (self.open - self.low).where(self.open < previous, 0.0)
        stm, sbm = dtm.rolling(window).sum(), dbm.rolling(window).sum()
        return ((stm - sbm) / stm.where(stm > sbm, sbm)).where((stm != 0) | (sbm != 0), 0.0)

    def mi(self, window: int = 12):
        """动量指标的 SMA 平滑值。"""
        return self._sma(self.close - self.close.shift(window), window)

    def rc(self, window: int = 50):
        """变化率指数。"""
        return self.close / self.close.shift(window) * 100

    def srmi(self, window: int = 9):
        """SRMI 修正指标。"""
        reference = self.close.shift(window)
        return (self.close - reference).where(self.close > reference, 0.0) / self.close

    def atr(self, window: int = 14):
        """真实波幅均值。"""
        return self._tr().rolling(window).mean()

    def donchian_position(self, window: int = 20):
        """唐奇安通道位置：收盘价在近期高低区间中的归一化位置。"""
        upper = self.high.rolling(window).max()
        lower = self.low.rolling(window).min()
        return (self.close - lower) / (upper - lower + 1e-10)

    def donchian_width(self, window: int = 20):
        """唐奇安通道宽度：近期高低区间相对收盘价的幅度。"""
        upper = self.high.rolling(window).max()
        lower = self.low.rolling(window).min()
        return (upper - lower) / (self.close.abs() + 1e-10)

    def keltner_position(
        self,
        window: int = 20,
        atr_window: int = 10,
        multiplier: float = 2.0,
    ):
        """肯特纳通道位置：收盘价在 EMA/ATR 通道中的归一化位置。"""
        upper, lower, _ = self._keltner_bands(window, atr_window, multiplier)
        return (self.close - lower) / (upper - lower + 1e-10)

    def keltner_width(
        self,
        window: int = 20,
        atr_window: int = 10,
        multiplier: float = 2.0,
    ):
        """肯特纳通道宽度：ATR 通道相对 EMA 中轨的幅度。"""
        upper, lower, middle = self._keltner_bands(window, atr_window, multiplier)
        return (upper - lower) / (middle.abs() + 1e-10)

    def mass(self, short: int = 9, long: int = 25):
        """梅丝线。"""
        first = (self.high - self.low).rolling(short).mean()
        return (first / first.rolling(short).mean()).rolling(long).sum()

    def std(self, window: int = 26):
        """收盘价总体标准差。"""
        return self.close.rolling(window).std(ddof=0)

    def vhf(self, window: int = 28):
        """纵横指标。"""
        numerator = self.close.rolling(window).max() - self.close.rolling(window).min()
        return numerator / self.close.diff().abs().rolling(window).sum()

    def cvlt(self, window: int = 10):
        """佳庆离散指标。"""
        ema = (self.high - self.low).ewm(span=window, adjust=False).mean()
        return (ema - ema.shift(window)) / ema.shift(window)


def pd_concat_max(*frames):
    """逐单元取最大值，保留日期×标的宽表形状。"""
    result = frames[0]
    for frame in frames[1:]:
        result = result.where(result >= frame, frame)
    return result


def pd_concat_min(*frames):
    """逐单元取最小值，保留日期×标的宽表形状。"""
    result = frames[0]
    for frame in frames[1:]:
        result = result.where(result <= frame, frame)
    return result
