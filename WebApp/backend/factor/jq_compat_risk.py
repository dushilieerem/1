"""聚宽兼容风险因子（第一批）。"""

from __future__ import annotations

import numpy as np

from quantcore import FactorLibrary


class JoinQuantRiskLibrary(FactorLibrary):
    """基于日收益率的聚宽风险类兼容因子。"""

    author = "SVQuant"

    def _returns(self):
        return self.close.pct_change()

    def _sharpe(self, window: int):
        returns = self._returns()
        annual_return = returns.rolling(window).mean() * 252
        annual_volatility = returns.rolling(window).std() * np.sqrt(252)
        return (annual_return - 0.04) / annual_volatility

    def jq_kurtosis20(self):
        """聚宽 Kurtosis20：20 日收益率峰度。"""
        return self._returns().rolling(20).kurt()

    def jq_kurtosis60(self):
        """聚宽 Kurtosis60：60 日收益率峰度。"""
        return self._returns().rolling(60).kurt()

    def jq_kurtosis120(self):
        """聚宽 Kurtosis120：120 日收益率峰度。"""
        return self._returns().rolling(120).kurt()

    def jq_sharpe_ratio_20(self):
        """聚宽 sharpe_ratio_20：20 日滚动年化夏普比率。"""
        return self._sharpe(20)

    def jq_sharpe_ratio_60(self):
        """聚宽 sharpe_ratio_60：60 日滚动年化夏普比率。"""
        return self._sharpe(60)

    def jq_sharpe_ratio_120(self):
        """聚宽 sharpe_ratio_120：120 日滚动年化夏普比率。"""
        return self._sharpe(120)

    def jq_skewness20(self):
        """聚宽 Skewness20：20 日收益率偏度。"""
        return self._returns().rolling(20).skew()

    def jq_skewness60(self):
        """聚宽 Skewness60：60 日收益率偏度。"""
        return self._returns().rolling(60).skew()

    def jq_skewness120(self):
        """聚宽 Skewness120：120 日收益率偏度。"""
        return self._returns().rolling(120).skew()

    def jq_variance20(self):
        """聚宽 Variance20：20 日收益率方差。"""
        return self._returns().rolling(20).var() * 252

    def jq_variance60(self):
        """聚宽 Variance60：60 日收益率方差。"""
        return self._returns().rolling(60).var() * 252

    def jq_variance120(self):
        """聚宽 Variance120：120 日收益率方差。"""
        return self._returns().rolling(120).var() * 252
