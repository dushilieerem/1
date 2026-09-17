"""ResearchEngine 的标准日志配置。"""

from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    """配置应用命名空间日志，复用 Uvicorn 已安装的根处理器。"""

    level_name = os.getenv("SVQUANT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logging.getLogger("app").setLevel(level)
