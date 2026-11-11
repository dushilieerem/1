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
