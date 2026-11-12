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


def declared_windows(text: str | None) -> set[int]:
    """All windows named in a field; a composite factor can legitimately use several."""
    value = str(text or '')
    return {int(match.group(1)) for pattern in _PRIMARY for match in pattern.finditer(value)}


def implementation_window(code: str | None) -> int | None:
    windows = implementation_windows(code)
    return min(windows) if windows else None


def implementation_windows(code: str | None) -> set[int]:
    value = str(code or '')
    return {int(x) for x in re.findall(r'(?:pct_change|shift)\(\s*(\d+)\s*\)', value)}


def conflict(name: str | None, hypothesis: str | None, code: str | None) -> str:
    """Return an actionable error only for an unambiguous single-window mismatch."""
    name_windows = declared_windows(name)
    hypothesis_windows = declared_windows(hypothesis)
    code_windows = implementation_windows(code)
    if len(name_windows) == 1 and len(hypothesis_windows) == 1:
        name_window = next(iter(name_windows))
        hypothesis_window = next(iter(hypothesis_windows))
        # A composite implementation may legitimately include the name window
        # even when the hypothesis text also names another window.
        if name_window != hypothesis_window and (not code_windows or name_window not in code_windows):
            return (f'任务名称写的是 {name_window} 日，冻结研究假设实际是 {hypothesis_window} 日；'
                    '请重命名任务或新建任务，不能沿用旧标签')
    if len(hypothesis_windows) == 1 and len(code_windows) == 1:
        hypothesis_window = next(iter(hypothesis_windows))
        code_window = next(iter(code_windows))
        if hypothesis_window != code_window:
            return (f'冻结研究假设写的是 {hypothesis_window} 日，实际实现代码是 {code_window} 日；'
                    '请修订实现或建立新的研究分支，不能直接进入回测')
    # Composite factors (1d+3d, multi-window rank blends) and hypotheses that
    # mention a parent window cannot be represented by one number. Do not
    # reject them with a single-window rule; their evidence still faces every
    # numerical and novelty gate.
    return ''
