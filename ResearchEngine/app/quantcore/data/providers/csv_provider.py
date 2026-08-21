"""``CSVDataProvider`` - 读取本地 CSV 文件。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.quantcore.data.interface import IDataProvider
from app.quantcore.data.providers._file_base import _FileProvider


class CSVDataProvider(_FileProvider):
    """从本地目录读取每标的一个 CSV 文件的数据源。

    示例文件 ``600000.csv``::

        date,open,high,low,close,volume
        2020-01-02,12.1,12.3,12.0,12.2,100000
        2020-01-03,12.2,12.5,12.1,12.4,120000
    """

    name = "csv"
    _ext = ".csv"

    def _read_file(self, path: Path) -> pd.DataFrame:
        return pd.read_csv(path)
