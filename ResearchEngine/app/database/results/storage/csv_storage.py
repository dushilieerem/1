"""``CSVStorage`` - 以 CSV 文件保存结果。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.database.results.storage.base import ResultStorage, _factor_values_frame


class CSVStorage(ResultStorage):
    """把结果写入一个目录下的多个 CSV 文件。

    产物：``metrics.csv`` / ``equity_curve.csv`` / ``factor_values.csv`` /
    ``positions.csv`` / ``meta.json``。
    """

    name = "csv"

    def write(self, result, path: str) -> None:
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)

        # 指标
        pd.DataFrame(
            [(k, v) for k, v in result.metrics.items()],
            columns=["name", "value"],
        ).to_csv(out / "metrics.csv", index=False, encoding="utf-8")

        # 净值曲线
        if result.equity_curve is not None:
            result.equity_curve.rename("equity").to_csv(
                out / "equity_curve.csv", encoding="utf-8"
            )

        # 因子值
        if result.factor_values is not None:
            _factor_values_frame(result.factor_values).to_csv(
                out / "factor_values.csv", encoding="utf-8"
            )

        # 持仓
        if result.positions is not None:
            result.positions.to_csv(out / "positions.csv", encoding="utf-8")

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

        fv_file = out / "factor_values.csv"
        if fv_file.exists():
            df = pd.read_csv(fv_file, index_col=0)
            df.index = pd.to_datetime(df.index)
            result.factor_values = df

        pos_file = out / "positions.csv"
        if pos_file.exists():
            df = pd.read_csv(pos_file, index_col=0)
            df.index = pd.to_datetime(df.index)
            result.positions = df

        meta_file = out / "meta.json"
        if meta_file.exists():
            result.meta = json.loads(meta_file.read_text(encoding="utf-8"))

        return result
