"""Declared versus implemented lookback-window checks.

The task name is only a label.  The frozen hypothesis and the actual factor
code are the authority; a mismatch must stop before a market test.
"""
from __future__ import annotations

import re

_PRIMARY = (
    re.compile(r'r(\d+)_i,t'),
    # An explicit return formula is the primary window. A hypothesis may also
    # mention a longer volatility/overlay lookback ("过去20个交易日...标准差"),
    # which must not be mistaken for the return horizon.
    re.compile(r'close_i,t-(\d+)'),
    re.compile(r'(\d+)\s*日反转'),
    re.compile(r'过去\s*(\d+)\s*个交易日'),
)


def declared_window(text: str | None) -> int | None:
    value = str(text or '')
    for pattern in _PRIMARY:
        match = pattern.search(value)
        if match:
            return int(match.group(1))
    return None


def implementation_window(code: str | None) -> int | None:
    value = str(code or '')
    match = re.search(r'pct_change\(\s*(\d+)\s*\)', value)
    if match:
        return int(match.group(1))
    match = re.search(r'shift\(\s*(\d+)\s*\)', value)
    if match:
        return int(match.group(1))
    return None


def conflict(name: str | None, hypothesis: str | None, code: str | None) -> str:
    """Return an actionable error when declared windows disagree, else ''."""
    name_window = declared_window(name)
    hypothesis_window = declared_window(hypothesis)
    code_window = implementation_window(code)
    if name_window is not None and hypothesis_window is not None and name_window != hypothesis_window:
        return (f'任务名称写的是 {name_window} 日，冻结研究假设实际是 {hypothesis_window} 日；'
                '请重命名任务或新建任务，不能沿用旧标签')
    if hypothesis_window is not None and code_window is not None and hypothesis_window != code_window:
        return (f'冻结研究假设写的是 {hypothesis_window} 日，实际实现代码是 {code_window} 日；'
                '请修订实现或建立新的研究分支，不能直接进入回测')
    return ''
