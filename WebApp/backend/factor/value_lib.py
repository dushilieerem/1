"""价值因子库。

估值类因子，衡量股票的便宜/昂贵程度。
"""

from __future__ import annotations

from quantcore import FactorLibrary


class ValueLib(FactorLibrary):
    """价值因子集合。"""

    author = "YGQuant"

    # ==================== 估值比率 ====================

    def ep_ttm(self):
        """EP 因子：滚动市盈率倒数。"""
        return 1.0 / self.pe_ttm

    def ep(self):
        """EP 因子：静态市盈率倒数。RE 无 pe，不可算。"""
        raise NotImplementedError("数据不可用：RE 无 pe 字段，无法计算静态 EP")

    def bp(self):
        """BP 因子：市净率倒数。"""
        return 1.0 / self.pb

    def sp_ttm(self):
        """SP 因子：滚动市销率倒数。"""
        return 1.0 / self.ps_ttm

    def cp_ttm(self):
        """CP 因子：滚动市现率倒数。RE 无 pcf_ttm，不可算。"""
        raise NotImplementedError("数据不可用：RE 无 pcf_ttm 字段，无法计算 CP")

    # ==================== 综合估值 ====================

    def composite_value(self):
        """综合价值因子：EP + BP + SP 等权合成。"""
        ep = 1.0 / self.pe_ttm
        bp = 1.0 / self.pb
        sp = 1.0 / self.ps_ttm
        return (ep + bp + sp) / 3

    def value_vs_growth(self):
        """价值 vs 成长：EP / (1 + 增长率)。缺增长率字段时不可算。"""
        raise NotImplementedError("RE 无增长率字段，无法计算 value_vs_growth")

    def earnings_yield(self):
        """盈利收益率：EP 的 ZSCORE（基于 pe_ttm，字段齐全时可算）。"""
        ep = 1.0 / self.pe_ttm
        return (ep - ep.mean()) / ep.std()

    # ==================== 股息 ====================

    def dividend_yield(self):
        """股息率。RE 无 dv_*，不可算。"""
        raise NotImplementedError("数据不可用：RE 无股息率字段，无法计算 dividend_yield")

    def dividend_cover(self):
        """股息覆盖：净利润 / 分红。缺字段时不可算。"""
        raise NotImplementedError("RE 无净利润/分红字段，无法计算 dividend_cover")

    # ==================== 成长估值 ====================

    def peg(self):
        """PEG：市盈率 / 增长率。缺增长率时不可算。"""
        raise NotImplementedError("RE 无增长率字段，无法计算 peg")

    def ev_ebitda(self):
        """EV/EBITDA 倒数。缺字段时不可算。"""
        raise NotImplementedError("RE 无 EV/EBITDA 字段，无法计算 ev_ebitda")

    # ==================== 市值 ====================

    def ln_cap(self):
        """对数市值。"""
        return self.total_mv.apply(lambda x: -x)

    def small_size(self):
        """小市值：负总市值。"""
        return -self.total_mv
