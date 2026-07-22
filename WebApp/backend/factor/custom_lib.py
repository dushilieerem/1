"""自定义因子库（按用户隔离；方法名 = u{user_id}_{name}）。

研究员在 Web 新增；Postgres 为权威；本文件为同步产物。
检测/回测时把方法体发给 YGQuant ResearchEngine。
"""

from __future__ import annotations

from quantcore import FactorLibrary


class CustomLib(FactorLibrary):
    """用户自定义因子。公共库因子在 momentum/value/technical/… 中。"""

    author = "SVQuant"

    def u1_EDIT_BEFORE(self):
        """改之后对照·10日收益"""
        return self.close.pct_change(10)

    def u3_RISK_ADJ_MOM_20(self):
        """20日收益/20日波动：风险调整动量"""
        ret = self.close.pct_change(20)
        vol = self.close.pct_change().rolling(20).std()
        return ret / (vol + 1e-8)

    def u5_Oversold_stable_with_momentum(self):
        """波谷缩量企稳 + 5日动量（个股分数）"""
        lookback = 20
        threshold = -0.15

        # 1. 超跌条件
        ret_20 = self.close / self.close.shift(lookback) - 1
        oversold = (ret_20 < threshold).astype(int)

        # 2. 缩量分位数
        def quantile_in_window(x):
            if len(x) < lookback:
                return np.nan
            return (x.iloc[:-1] < x.iloc[-1]).sum() / (len(x) - 1)

        volume_quantile = self.amount.rolling(lookback+1).apply(
            quantile_in_window, raw=False
        ).shift(-1)

        # 3. 企稳条件
        low_3d = self.low.rolling(3).min()
        low_20d = self.low.rolling(lookback).min()
        stable = (low_3d >= low_20d).astype(int)

        # 4. 个股波谷分数
        score = oversold * (1 - volume_quantile.fillna(0)) * stable

        # 5. 5日动量筛选
        momentum_5d = self.close / self.close.shift(5) - 1
        momentum_positive = (momentum_5d > 0.01).astype(int)

        # 6. 最终个股分数
        score_with_momentum = score * momentum_positive

        return score_with_momentum  # 返回 (日期 × 股票) 的DataFrame

    def u5_RET_20D_OK(self):
        """20日涨跌幅"""
        return self.close.pct_change(20)

    def u5_VOL_RATIO_20(self):
        """成交量相对20日均量比"""
        ma = self.volume.rolling(20).mean()
        return self.volume / ma

    def u6_aaaaa(self):
        """5日收益示意"""
        # 今日收盘价 > 昨日收盘价 → 1，否则 → 0
        score = (self.close > self.close.shift(1)).astype(int)
        return score

    def u6_Oversold_stable_with_momentum(self):
        """波谷缩量企稳 + 5日动量（个股分数）"""
        lookback = 20
        threshold = -0.15
    
        # 1. 超跌条件
        ret_20 = self.close / self.close.shift(lookback) - 1
        oversold = (ret_20 < threshold).astype(int)
    
        # 2. 缩量分位数
        def quantile_in_window(x):
            if len(x) < lookback:
                return np.nan
            return (x.iloc[:-1] < x.iloc[-1]).sum() / (len(x) - 1)
    
        volume_quantile = self.amount.rolling(lookback+1).apply(
            quantile_in_window, raw=False
        ).shift(-1)
    
        # 3. 企稳条件
        low_3d = self.low.rolling(3).min()
        low_20d = self.low.rolling(lookback).min()
        stable = (low_3d >= low_20d).astype(int)
    
        # 4. 个股波谷分数
        score = oversold * (1 - volume_quantile.fillna(0)) * stable
    
        # 5. 5日动量筛选
        momentum_5d = self.close / self.close.shift(5) - 1
        momentum_positive = (momentum_5d > 0.01).astype(int)
    
        # 6. 最终个股分数
        score_with_momentum = score * momentum_positive
    
        return score_with_momentum  # 返回 (日期 × 股票) 的DataFrame

