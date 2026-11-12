from services.quant_factor.factor_window import conflict, declared_window, implementation_window


def test_declared_and_implemented_windows_are_extracted():
    assert declared_window('Agent 自主研究：1日反转基线 · 1111') == 1
    assert declared_window('对每个交易日 t，令 r4_i,t = close_i,t / close_i,t-4 - 1') == 4
    assert implementation_window('def f(self):\n    return -self.close.pct_change(5)') == 5
    assert implementation_window('def f(self):\n    return self.close / self.close.shift(4) - 1') == 4


def test_name_hypothesis_window_mismatch_is_blocked():
    message = conflict('1日反转基线', '令 r4_i,t = close_i,t / close_i,t-4 - 1', 'self.close.shift(4)')
    assert '名称写的是 1 日' in message
    assert '假设实际是 4 日' in message


def test_hypothesis_code_window_mismatch_is_blocked():
    message = conflict('反转基线', '令 r4_i,t = close_i,t / close_i,t-4 - 1', 'self.close.shift(1)')
    assert '假设写的是 4 日' in message
    assert '实现代码是 1 日' in message


def test_neutral_task_name_and_matching_windows_are_allowed():
    assert conflict('收盘价对成交额隐含均价的偏离', '使用过去 4 个交易日的收益', 'self.close.shift(4)') == ''
    assert conflict('反转基线', 'r4_i,t = close_i,t / close_i,t-4 - 1', 'self.close.shift(1)') != ''


def test_volatility_overlay_is_not_mistaken_for_the_return_horizon():
    hypothesis = ('令 r_i,t = close_i,t / close_i,t-1 - 1；令 sigma_i,t 为截至 t-1 过去 20 个交易日'
                  '日收益 r 的样本标准差；signal_i,t = -r_i,t / (sigma_i,t + 1e-4)')
    assert declared_window('Agent 自主研究：1日反转基线 · 1111') == 1
    assert declared_window(hypothesis) == 1
    assert conflict('Agent 自主研究：1日反转基线 · 1111', hypothesis, 'self.close.pct_change(1)') == ''


def test_composite_multi_window_factor_is_not_rejected_as_single_window_mismatch():
    hypothesis = ('构造1日与3日反转排名等权合成因子：r1=close_{i,t}/close_{i,t-1}-1，'
                  'r3=close_{i,t}/close_{i,t-3}-1，signal=(rank(-r1)+rank(-r3))/2')
    code = ('def f0_factor(self):\n'
            '    a=self.close.shift(1);b=self.close.shift(3)\n'
            '    return -(self.close/a-1).rank(axis=1,pct=True)-(self.close/b-1).rank(axis=1,pct=True)')
    assert conflict('Agent 自主研究：1日反转基线 · 1112', hypothesis, code) == ''


def test_volatility_lookback_plus_raw_window_is_not_rejected():
    hypothesis = 'vol=过去3个交易日收益的标准差；raw=-(close_{i,t}/close_{i,t-3}-1)；signal=raw/vol'
    code = ('def f0_factor(self):\n'
            '    ret=self.close.pct_change(1);vol=ret.rolling(3,min_periods=3).std()\n'
            '    raw=-(self.close/self.close.shift(3)-1);return raw/vol')
    assert conflict('反转基线', hypothesis, code) == ''


def test_parent_window_mention_with_a_new_single_window_is_not_rejected():
    hypothesis = '将父候选的3日反转改为2日反转：r2=close_{i,t}/close_{i,t-2}-1'
    code = 'def f0_factor(self):\n    return -(self.close/self.close.shift(2)-1)'
    assert conflict('反转基线', hypothesis, code) == ''


def test_keyword_period_arguments_are_checked_not_bypassed():
    assert implementation_window('self.close.pct_change(periods=5)') == 5
    assert conflict('反转', '5 日反转：r5=close_{i,t}/close_{i,t-5}-1', 'self.close.pct_change(periods=2)') != ''
