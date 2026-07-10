"""``ParquetProvider`` - 读取列式存储 Parquet 文件。

    依赖 ``pyarrow``（pandas 读取 parquet 的引擎）。该依赖为**可选**：
    若未安装则在实例化时报错并提示安装。
"""

from __future__ import annotations

from pathlib import Path

from quantcore.data._util import require_optional
from quantcore.data.providers._file_base import _FileProvider


class ParquetProvider(_FileProvider):
    """从本地目录读取每标的一个 Parquet 文件的数据源。"""

    name = "parquet"
    _ext = ".parquet"

    def __init__(self, data_dir) -> None:
        require_optional("pyarrow", "ParquetProvider 需要 pyarrow")
        super().__init__(data_dir)

    def _read_file(self, path: Path):
        import pandas as pd

        return pd.read_parquet(path)
