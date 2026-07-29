"""标准 Parquet 面板的发布前质量检查。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def inspect_panels(panels_dir: Path, *, metadata_dir: Path | None = None) -> dict:
    """检查标准字段面板的日历、证券列和缺失率。"""
    if not panels_dir.is_dir():
        raise FileNotFoundError(f"面板目录不存在：{panels_dir}")

    assets: list[dict] = []
    issues: list[dict] = []
    baseline_index: pd.DatetimeIndex | None = None

    for path in sorted(panels_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        index = pd.DatetimeIndex(pd.to_datetime(frame.index))
        duplicate_dates = int(index.duplicated().sum())
        monotonic = index.is_monotonic_increasing
        if baseline_index is None:
            baseline_index = index
        elif not index.equals(baseline_index):
            issues.append({"field": path.stem, "type": "calendar_mismatch"})
        if duplicate_dates or not monotonic:
            issues.append({
                "field": path.stem,
                "type": "date_integrity",
                "duplicate_dates": duplicate_dates,
                "monotonic_increasing": monotonic,
            })

        invalid_symbols = [str(column) for column in frame.columns if not str(column).zfill(6).isdigit()]
        if invalid_symbols:
            issues.append({
                "field": path.stem,
                "type": "invalid_symbol_columns",
                "count": len(invalid_symbols),
                "examples": invalid_symbols[:10],
            })
        cells = frame.shape[0] * frame.shape[1]
        assets.append({
            "field": path.stem,
            "rows": frame.shape[0],
            "symbol_count": frame.shape[1],
            "date_range": [index.min().date().isoformat(), index.max().date().isoformat()] if len(index) else None,
            "missing_rate": round(float(frame.isna().sum().sum() / cells), 8) if cells else None,
        })

    manifests = []
    if metadata_dir:
        manifests = [
            name for name in ("data_manifest.yaml", "data_manifest.json", "wind_daily_manifest.json")
            if (metadata_dir / name).is_file()
        ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panels_dir": str(panels_dir),
        "field_count": len(assets),
        "manifest_files": manifests,
        "assets": assets,
        "issue_count": len(issues),
        "issues": issues,
    }


def _parse_args() -> argparse.Namespace:
    market_data_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels-dir", type=Path, default=market_data_root / "current" / "panels")
    parser.add_argument("--metadata-dir", type=Path, default=market_data_root / "current" / "metadata")
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = inspect_panels(args.panels_dir, metadata_dir=args.metadata_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已检查 {report['field_count']} 个面板：问题 {report['issue_count']}，清单 {report['manifest_files']}")


if __name__ == "__main__":
    main()
