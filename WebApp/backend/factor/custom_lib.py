"""自定义因子库（按用户隔离；方法名 = u{user_id}_{name}）。

研究员在 Web 新增；Postgres 为权威；本文件为同步产物。
检测/回测时把方法体发给 YGQuant ResearchEngine。
"""

from __future__ import annotations

from quantcore import FactorLibrary


class CustomLib(FactorLibrary):
    """用户自定义因子。公共库因子在 momentum/value/technical/… 中。"""

    author = "SVQuant"

