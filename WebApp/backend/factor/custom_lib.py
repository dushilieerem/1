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

    def u5_aaaa(self):
        """5日收益示意"""
        return self.close - self.close.rolling(5).mean()

    def u5_VOL_RATIO_20(self):
        """成交量相对20日均量比"""
        ma = self.volume.rolling(20).mean()
        return self.volume / ma

