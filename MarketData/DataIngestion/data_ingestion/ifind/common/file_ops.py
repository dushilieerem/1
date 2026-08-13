"""iFinD 文件产物的可恢复替换操作。"""

from __future__ import annotations

import time
from pathlib import Path


REPLACE_RETRIES = 61
REPLACE_RETRY_DELAY_SECONDS = 2.0


def replace_with_retry(source: Path, target: Path) -> None:
    """在 Windows 文件短暂占用时等待并重试，失败时保留 source。"""
    for attempt in range(REPLACE_RETRIES):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES - 1:
                raise
            print(
                f"[ifind] 文件暂时被占用，{REPLACE_RETRY_DELAY_SECONDS:g} 秒后重试 "
                f"({attempt + 1}/{REPLACE_RETRIES - 1})：{target}",
                flush=True,
            )
            time.sleep(REPLACE_RETRY_DELAY_SECONDS)
