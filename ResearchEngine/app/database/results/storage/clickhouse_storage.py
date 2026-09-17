"""``ClickHouseStorage`` - 写入 ClickHouse（远程）。

    依赖 ``clickhouse-driver``，为**可选依赖**，缺省时惰性报错。
"""

from __future__ import annotations

from app.utils.imports import require_optional
from app.database.results.storage.base import ResultStorage


class ClickHouseStorage(ResultStorage):
    """把结果写入 ClickHouse 数据库。"""

    name = "clickhouse"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9000,
        database: str = "svquant",
        user: str = "default",
        password: str = "",
    ) -> None:
        ch = require_optional(
            "clickhouse_driver", "ClickHouseStorage 需要 clickhouse-driver"
        )
        self.client = ch.Client(
            host=host, port=port, database=database,
            user=user, password=password,
        )

    def write(self, result, path: str) -> None:  # pragma: no cover
        # path 作为实验名（experiment_id），用于行级隔离
        exp_id = path
        self.client.execute(
            "CREATE TABLE IF NOT EXISTS experiment_metrics "
            "(experiment String, name String, value Float64) ENGINE = MergeTree() "
            "ORDER BY (experiment, name)"
        )
        rows = [(exp_id, k, float(v)) for k, v in result.metrics.items()]
        if rows:
            self.client.execute(
                "INSERT INTO experiment_metrics (experiment, name, value) VALUES",
                rows,
            )
        # 序列化大对象
        self.client.execute(
            "CREATE TABLE IF NOT EXISTS experiment_artifacts "
            "(experiment String, name String, data String) ENGINE = MergeTree() "
            "ORDER BY (experiment, name)"
        )
        artifacts = [
            (exp_id, name, data)
            for name, data in self._artifacts(result).items()
        ]
        if artifacts:
            self.client.execute(
                "INSERT INTO experiment_artifacts (experiment, name, data) VALUES",
                artifacts,
            )

    def read(self, path: str):  # pragma: no cover
        from app.models.results import ResultData

        exp_id = path
        result = ResultData()
        rows = self.client.execute(
            "SELECT name, value FROM experiment_metrics WHERE experiment = %s",
            (exp_id,),
        )
        result.metrics = {r[0]: float(r[1]) for r in rows}

        rows = self.client.execute(
            "SELECT name, data FROM experiment_artifacts WHERE experiment = %s",
            (exp_id,),
        )
        self._apply_artifacts(result, {r[0]: r[1] for r in rows})
        return result
