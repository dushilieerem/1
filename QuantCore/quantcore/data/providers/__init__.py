"""具体数据源实现（各自实现 ``IDataProvider``）。

依据 ``docs/04-features/FEAT-001-quantcore-core/04-class-design.md`` DataEngine 节，包含五个 provider：

- :class:`CSVDataProvider`       - 读取本地 CSV 文件
- :class:`ParquetProvider`       - 读取列式存储 Parquet 文件
- :class:`ClickHouseProvider`    - 查询分布式数据库 ClickHouse
- :class:`AkShareProvider`       - A 股实时/历史数据（AkShare）
- :class:`WindProvider`          - 万得金融终端
"""

from quantcore.data.providers.akshare_provider import AkShareProvider
from quantcore.data.providers.clickhouse_provider import ClickHouseProvider
from quantcore.data.providers.csv_provider import CSVDataProvider
from quantcore.data.providers.field_parquet_provider import FieldParquetProvider
from quantcore.data.providers.parquet_provider import ParquetProvider
from quantcore.data.providers.wide_csv_provider import WideCSVProvider
from quantcore.data.providers.wind_provider import WindProvider

__all__ = [
    "CSVDataProvider",
    "ParquetProvider",
    "FieldParquetProvider",
    "WideCSVProvider",
    "ClickHouseProvider",
    "AkShareProvider",
    "WindProvider",
]
