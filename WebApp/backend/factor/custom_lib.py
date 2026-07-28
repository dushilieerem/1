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

    def u1_realized_vol_20d(self):
        ret = self.close.pct_change()
        return ret.rolling(20).std()

    def u1_stock_mom_20(self):
        """个股近 20 日累计收益动量（可克隆到因子检测）"""
        return self.close.pct_change(20)

    def u3_realized_vol_20d(self):
        ret = self.close.pct_change()
        return ret.rolling(20).std()

    def u3_RISK_ADJ_MOM_20(self):
        """20日收益/20日波动：风险调整动量"""
        ret = self.close.pct_change(20)
        vol = self.close.pct_change().rolling(20).std()
        return ret / (vol + 1e-8)

    def u4_band_location(self):
        """布林带内位置"""
        mid = self.close.rolling(20).mean()
        sd = self.close.rolling(20).std()
        up = mid + 2 * sd
        dn = mid - 2 * sd
        return (self.close - dn) / (up - dn).replace(0, float("nan"))

    def u4_phantom_gap(self):
        """隔夜幽灵跳空"""
        return self.open / self.close.shift(1) - 1

    def u4_realized_vol_20d(self):
        ret = self.close.pct_change()
        return ret.rolling(20).std()

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

    def u5_realized_vol_20d(self):
        ret = self.close.pct_change()
        return ret.rolling(20).std()

    def u5_RET_20D_OK(self):
        """5日收益示意"""
        return self.csi300.close*(self.close/self.close)

    def u5_RET_5D_DEMO(self):
        """5日收益示意"""
        return self.close.pct_change(5)

    def u5_VOL_RATIO_20(self):
        """成交量相对20日均量比"""
        ma = self.volume.rolling(20).mean()
        return self.volume / ma

    def u6_Oversold_stable_with_momentum(self):
        """
        波谷缩量企稳 + 5日动量（指数择时 × 个股选股）
        修正点：
        1. 指数与个股用 mul(..., axis=0) 严格按日期对齐
        2. 去掉缩量计算中的 .shift(-1)，消除未来函数
        3. 使用向量化方法替代 apply（性能优化）
        """
        lookback = 20
        threshold = -0.15
        volume_shrink_pct = 0.7  # 缩量阈值：比70%的时间都低

        # ==================== 指数层面（择时） ====================
        idx = self.csi1000

        # 1. 超跌
        ret_20_idx = idx.close / idx.close.shift(lookback) - 1
        oversold_idx = (ret_20_idx < threshold).astype(int)

        # 2. 缩量（向量化实现，无未来函数）
        # 方法：用 rolling + apply 但保留当天标签，不加 shift(-1)
        def volume_quantile_func(x):
            if len(x) < lookback + 1:
                return np.nan
            return (x.iloc[:-1] < x.iloc[-1]).sum() / lookback

        volume_quantile_idx = idx.volume.rolling(lookback + 1).apply(
            volume_quantile_func, raw=False
        )
        # 注意：这里没有 .shift(-1)，结果直接对齐到窗口末端（即当天）
        volume_shrink_idx = (volume_quantile_idx > volume_shrink_pct).astype(int)

        # 3. 企稳
        low_3d_idx = idx.low.rolling(3).min()
        low_20d_idx = idx.low.rolling(lookback).min()
        stable_idx = (low_3d_idx >= low_20d_idx).astype(int)

        # 4. 指数环境开关（0/1）
        market_oversold = oversold_idx * volume_shrink_idx * stable_idx

        # ==================== 个股层面（选股） ====================
        # 注意：以下 self.amount, self.low, self.close 必须是个股数据

        # 1. 个股缩量连续分（0~1，越大越缩量）
        # 向量化快速实现：用 rolling + apply（个股数量多时可改用 rank 优化）
        def stock_quantile_func(x):
            if len(x) < lookback + 1:
                return np.nan
            return (x.iloc[:-1] < x.iloc[-1]).sum() / lookback

        volume_quantile_stock = self.amount.rolling(lookback + 1).apply(
            stock_quantile_func, raw=False
        )
        # 缩量分数：分位数越高（越缩量），分数越高
        shrink_score = volume_quantile_stock.fillna(0)  # 直接用分位数作为缩量强度

        # 2. 个股企稳（0/1）
        low_3d_stock = self.low.rolling(3).min()
        low_20d_stock = self.low.rolling(lookback).min()
        stable_stock = (low_3d_stock >= low_20d_stock).astype(int)

        # 3. 个股5日动量（连续正收益，0~∞）
        momentum_5d = self.close.pct_change(5)  # 等价于 close/shift(5)-1
        momentum_score = momentum_5d.clip(lower=0)  # 负值归零，保留正涨幅

        # ==================== 合成 ====================
        # 个股基础分：缩量强度 × 企稳开关
        stock_base_score = shrink_score * stable_stock

        # 指数择时 × 个股基础分 × 动量
        # 关键：使用 mul(..., axis=0) 确保按日期对齐
        score = stock_base_score.mul(market_oversold, axis=0) * momentum_score

        # ==================== 保底逻辑 ====================
        # 如果指数从未触发择时信号，返回纯个股分数（避免无因子值）
        if (market_oversold == 0).all():
            score = stock_base_score * momentum_score

        return score

