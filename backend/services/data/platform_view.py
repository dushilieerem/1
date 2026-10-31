# -*- coding: utf-8 -*-
"""独立数据平台（svquant-data）只读视图解析。

业务只认 SVQUANT_DATA_VIEW；路径由数据平台物化，不在业务里拼接 release。
未配置时返回 None，兼容旧 MARKETDATA_DIR 部署。
"""
from __future__ import annotations

from pathlib import Path

from services.core.env_config import env


def materialized_ifind_root() -> Path | None:
    root = (env("SVQUANT_DATA_ROOT", "") or "").strip()
    view = (env("SVQUANT_DATA_VIEW", "") or "").strip()
    if not root or not view:
        return None
    base = Path(root) / "views" / view
    # 容器内优先用指向 /marketdata 的物化；宿主机用普通物化
    for name in ("materialized-container", "materialized"):
        candidate = base / name / "ifind"
        if candidate.exists():
            return candidate
    return None
