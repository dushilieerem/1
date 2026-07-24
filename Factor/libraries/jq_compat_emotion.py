"""聚宽兼容情绪因子。"""

from __future__ import annotations

from quantcore import FactorLibrary


class JoinQuantEmotionLibrary(FactorLibrary):
    """由量价、成交额和换手率计算的聚宽情绪因子。"""

    author = "SVQuant"

    def _vema(self, window: int):
        return self.volume.ewm(span=window, adjust=False).mean()

    def _turnover_mean(self, window: int):
        return self.turnover.rolling(window).mean()

    def _wvad(self):
        value = (self.close - self.open) / (self.high - self.low) * self.volume
        return value.rolling(6).sum()

    def _true_range(self):
        previous_close = self.close.shift()
        first = self.high - self.low
        second = (self.high - previous_close).abs()
        third = (self.low - previous_close).abs()
        result = first.where(first >= second, second)
        return result.where(result >= third, third)

    def _ar(self):
        return (
            (self.high - self.open).rolling(26).sum()
            / (self.open - self.low).rolling(26).sum()
            * 100
        )

    def _br(self):
        previous_close = self.close.shift()
        up = (self.high - previous_close).clip(lower=0)
        down = (previous_close - self.low).clip(lower=0)
        return up.rolling(26).sum() / down.rolling(26).sum() * 100

    def _vdiff(self):
        return self._vema(12) - self._vema(26)

    def jq_ar(self):
        """聚宽 AR：26 日人气指标。"""
        return self._ar()

    def jq_arbr(self):
        """聚宽 ARBR：AR 与 BR 的差。"""
        return self._ar() - self._br()

    def jq_atr6(self):
        """聚宽 ATR6：6 日真实振幅均值。"""
        return self._true_range().rolling(6).mean()

    def jq_atr14(self):
        """聚宽 ATR14：14 日真实振幅均值。"""
        return self._true_range().rolling(14).mean()

    def jq_br(self):
        """聚宽 BR：26 日意愿指标。"""
        return self._br()

    def jq_davol5(self):
        """聚宽 DAVOL5：5 日与 120 日平均换手率之比。"""
        return self._turnover_mean(5) / self._turnover_mean(120)

    def jq_davol10(self):
        """聚宽 DAVOL10：10 日与 120 日平均换手率之比。"""
        return self._turnover_mean(10) / self._turnover_mean(120)

    def jq_davol20(self):
        """聚宽 DAVOL20：20 日与 120 日平均换手率之比。"""
        return self._turnover_mean(20) / self._turnover_mean(120)

    def jq_mawvad(self):
        """聚宽 MAWVAD：WVAD 的 6 日移动均值。"""
        return self._wvad().rolling(6).mean()

    def jq_money_flow_20(self):
        """聚宽 money_flow_20：20 日典型价格资金流量。"""
        typical_price = (self.high + self.low + self.close) / 3
        return (typical_price * self.volume).rolling(20).sum()

    def jq_psy(self):
        """聚宽 PSY：12 日上涨天数占比。"""
        return (self.close.diff() > 0).rolling(12).mean() * 100

    def jq_turnover_volatility(self):
        """聚宽 turnover_volatility：20 日换手率标准差。"""
        return self.turnover.rolling(20).std()

    def jq_tvma6(self):
        """聚宽 TVMA6：6 日成交金额移动均值。"""
        return self.amount.rolling(6).mean()

    def jq_tvma20(self):
        """聚宽 TVMA20：20 日成交金额移动均值。"""
        return self.amount.rolling(20).mean()

    def jq_tvstd6(self):
        """聚宽 TVSTD6：6 日成交金额标准差。"""
        return self.amount.rolling(6).std()

    def jq_tvstd20(self):
        """聚宽 TVSTD20：20 日成交金额标准差。"""
        return self.amount.rolling(20).std()

    def jq_vdea(self):
        """聚宽 VDEA：VDIFF 的 9 日指数移动均线。"""
        return self._vdiff().ewm(span=9, adjust=False).mean()

    def jq_vdiff(self):
        """聚宽 VDIFF：12 日与 26 日成交量 EMA 之差。"""
        return self._vdiff()

    def jq_vema5(self):
        """聚宽 VEMA5：5 日成交量指数移动均线。"""
        return self._vema(5)

    def jq_vema10(self):
        """聚宽 VEMA10：10 日成交量指数移动均线。"""
        return self._vema(10)

    def jq_vema12(self):
        """聚宽 VEMA12：12 日成交量指数移动均线。"""
        return self._vema(12)

    def jq_vema26(self):
        """聚宽 VEMA26：26 日成交量指数移动均线。"""
        return self._vema(26)

    def jq_vmacd(self):
        """聚宽 VMACD：成交量 MACD 柱值。"""
        return self._vdiff() - self.jq_vdea()

    def jq_vol5(self):
        """聚宽 VOL5：5 日平均换手率。"""
        return self._turnover_mean(5)

    def jq_vol10(self):
        """聚宽 VOL10：10 日平均换手率。"""
        return self._turnover_mean(10)

    def jq_vol20(self):
        """聚宽 VOL20：20 日平均换手率。"""
        return self._turnover_mean(20)

    def jq_vol60(self):
        """聚宽 VOL60：60 日平均换手率。"""
        return self._turnover_mean(60)

    def jq_vol120(self):
        """聚宽 VOL120：120 日平均换手率。"""
        return self._turnover_mean(120)

    def jq_vol240(self):
        """聚宽 VOL240：240 日平均换手率。"""
        return self._turnover_mean(240)

    def jq_vosc(self):
        """聚宽 VOSC：成交量震荡指标。"""
        return (self._vema(12) - self._vema(26)) / self._vema(12) * 100

    def jq_vr(self):
        """聚宽 VR：成交量比率。"""
        change = self.close.diff()
        up = self.volume.where(change > 0, 0.0)
        down = self.volume.where(change < 0, 0.0)
        flat = self.volume.where(change == 0, 0.0)
        return (up.rolling(26).sum() + flat.rolling(26).sum() / 2) / (
            down.rolling(26).sum() + flat.rolling(26).sum() / 2
        )

    def jq_vroc6(self):
        """聚宽 VROC6：6 日成交量变动速率。"""
        return self.volume.pct_change(6) * 100

    def jq_vroc12(self):
        """聚宽 VROC12：12 日成交量变动速率。"""
        return self.volume.pct_change(12) * 100

    def jq_vstd10(self):
        """聚宽 VSTD10：10 日成交量标准差。"""
        return self.volume.rolling(10).std()

    def jq_vstd20(self):
        """聚宽 VSTD20：20 日成交量标准差。"""
        return self.volume.rolling(20).std()

    def jq_wvad(self):
        """聚宽 WVAD：6 日威廉变异离散量。"""
        return self._wvad()
