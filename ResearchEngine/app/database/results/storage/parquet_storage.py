"""``ParquetStorage`` - 大表用 parquet、小文件用 csv/json 保存结果。

相比 :class:`CSVStorage`，将因子值与持仓两个大宽表（日期×标的）以 parquet
二进制列式格式存储，避免 ``to_csv`` 对海量浮点逐格文本化的开销——写入快 10-50x、
文件更小。小文件（metrics / equity_curve）仍用 csv 保持可读，meta 用 json。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.database.results.storage.base import ResultStorage, _factor_values_frame


class ParquetStorage(ResultStorage):
    """把结果写入一个目录：大表 parquet + 小文件 csv/json。

    产物：``metrics.csv`` / ``equity_curve.csv`` / ``factor_values.parquet`` /
    ``positions.parquet`` / ``meta.json``。
    """

    name = "parquet"

    def write(self, result, path: str) -> None:
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)

        # 指标（小表，csv 便于查看）
        pd.DataFrame(
            [(k, v) for k, v in result.metrics.items()],
            columns=["name", "value"],
        ).to_csv(out / "metrics.csv", index=False, encoding="utf-8")

        # 净值曲线（小表，csv）
        if result.equity_curve is not None:
            result.equity_curve.rename("equity").to_csv(
                out / "equity_curve.csv", encoding="utf-8"
            )

        # 因子值（大宽表 -> parquet）
        if result.factor_values is not None:
            _factor_values_frame(result.factor_values).to_parquet(
                out / "factor_values.parquet"
            )

        # 持仓（大宽表 -> parquet）
        if result.positions is not None:
            result.positions.to_parquet(out / "positions.parquet")

        # 元信息
        (out / "meta.json").write_text(
            json.dumps(result.meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read(self, path: str):
        from app.models.results import ResultData

        out = Path(path)
        result = ResultData()

        m_file = out / "metrics.csv"
        if m_file.exists():
            df = pd.read_csv(m_file)
            result.metrics = dict(zip(df["name"], df["value"].astype(float)))

        eq_file = out / "equity_curve.csv"
        if eq_file.exists():
            s = pd.read_csv(eq_file, index_col=0).squeeze("columns")
            s.index = pd.to_datetime(s.index)
            result.equity_curve = s

        fv_file = out / "factor_values.parquet"
        if fv_file.exists():
            df = pd.read_parquet(fv_file)
            df.index = pd.to_datetime(df.index)
            result.factor_values = df

        pos_file = out / "positions.parquet"
        if pos_file.exists():
            df = pd.read_parquet(pos_file)
            df.index = pd.to_datetime(df.index)
            result.positions = df

        meta_file = out / "meta.json"
        if meta_file.exists():
            result.meta = json.loads(meta_file.read_text(encoding="utf-8"))

        return result
